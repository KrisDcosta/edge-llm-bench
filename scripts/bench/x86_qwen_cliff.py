#!/usr/bin/env python3
"""
x86_qwen_cliff.py  —  Qwen 2.5 1.5B KV-cache cliff sweep
                       x86_64 CPU · AVX2 · uses llama-bench

Measures decode TPS at 11 context lengths to detect KV-cache cliff behaviour.
Method: pp-only + pg combined run per context → derive decode TPS.

Key change from v1: TG_TOKENS raised from 32 → 128.
  On a fast x86 (i5-1235U at ~20 t/s), 32 tokens = ~1.6s decode window.
  Any OS scheduling jitter (Windows Defender, background updates) dominates.
  128 tokens = ~6.4s window → CV typically < 15% instead of 50–80%.

Prerequisites:
  1. llama-bench binary — set LLAMA_BENCH_PATH or add to PATH.
     Default search locations:
       C:\\temp\\llama.cpp\\build\\bin\\Release\\llama-bench.exe
       C:\\temp\\llama.cpp\\build\\bin\\Release\\llama-bench
       /tmp/llama.cpp/build/bin/llama-bench

  2. Qwen GGUF models in local-models/qwen2_5_1_5b_gguf/ (project root)
     OR set QWEN_MODELS_DIR env var.

     If models are missing, download with:
       pip install huggingface_hub
       python -c "
       from huggingface_hub import hf_hub_download; import os
       os.makedirs('local-models/qwen2_5_1_5b_gguf', exist_ok=True)
       for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:
           hf_hub_download('bartowski/Qwen2.5-1.5B-Instruct-GGUF',
               f'Qwen2.5-1.5B-Instruct-{v}.gguf',
               local_dir='local-models/qwen2_5_1_5b_gguf')
       "

Usage:
  py -3 scripts/bench/x86_qwen_cliff.py              # all 7 variants
  py -3 scripts/bench/x86_qwen_cliff.py Q4_K_M Q8_0  # subset
  py -3 scripts/bench/x86_qwen_cliff.py --resume      # skip completed
  py -3 scripts/bench/x86_qwen_cliff.py --threads 8   # override thread count

Output:  results/x86_qwen_cliff_<HOSTNAME>_<ts>/cliff_<VARIANT>.jsonl
Runtime: ~4-6 h  (7 variants x 11 ctx x 5 trials, TG=128 on mid-range x86)
"""

import argparse
import datetime
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import sys
import time

# ── Configuration ─────────────────────────────────────────────────────────────

ALL_VARIANTS  = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]

# Matches Pixel 6a cliff sweep context points for direct cross-device comparison.
# Starts at 256 to capture the low-context baseline and early cliff onset.
CTX_SIZES     = [256, 512, 768, 1024, 1200, 1300, 1400, 1500, 1600, 1800, 2048]

# 128 tokens gives ~6s decode window on i5-1235U → CV < 15% (was 32 → CV 50-80%)
TG_TOKENS     = 128

NUM_TRIALS    = 5
NGL           = 0        # CPU only
MODEL_PREFIX  = "Qwen2.5-1.5B-Instruct"

# ── Helpers ───────────────────────────────────────────────────────────────────

def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    return line


def hr():
    log("=" * 72)


def find_llama_bench():
    if "LLAMA_BENCH_PATH" in os.environ:
        p = os.environ["LLAMA_BENCH_PATH"]
        if os.path.isfile(p):
            return p
    candidates = [
        r"C:\temp\llama.cpp\build\bin\Release\llama-bench.exe",
        r"C:\temp\llama.cpp\build\bin\Release\llama-bench",
        "/tmp/llama.cpp/build/bin/llama-bench",
        "/tmp/llama.cpp/build/bin/llama-bench.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    found = shutil.which("llama-bench") or shutil.which("llama-bench.exe")
    if found:
        return found
    return None


def find_models_dir():
    if "QWEN_MODELS_DIR" in os.environ:
        return os.environ["QWEN_MODELS_DIR"]
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.normpath(os.path.join(script_dir, "..", ".."))
    local = os.path.join(project_root, "local-models", "qwen2_5_1_5b_gguf")
    if os.path.isdir(local):
        return local
    return r"C:\temp\qwen2_5_1_5b_gguf"


def run_llama_bench(llama_bench, model_path, pp_tokens, tg_tokens, trials, ngl, threads):
    """Run llama-bench and return stdout as string."""
    cmd = [
        llama_bench,
        "-m",  model_path,
        "-p",  str(pp_tokens),
        "-pg", f"{pp_tokens},{tg_tokens}",
        "-r",  str(trials),
        "-ngl", str(ngl),
        "-t",  str(threads),
        "-o",  "jsonl",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        return result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return ""
    except Exception:
        return ""


def parse_bench_output(output, pp_tokens, tg_tokens, variant, ctx, threads):
    """Parse llama-bench jsonl output → cliff record."""
    rows = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    pp_row = next((r for r in rows
                   if r.get("n_prompt") == pp_tokens and r.get("n_gen") == 0), None)
    pg_row = next((r for r in rows
                   if r.get("n_prompt") == pp_tokens and r.get("n_gen") == tg_tokens), None)

    if not pp_row or not pg_row:
        return {
            "variant": variant, "context": ctx,
            "decode_tps": 0, "prefill_tps": 0,
            "error": "missing_rows",
        }

    pp_samples = pp_row.get("samples_ts", [pp_row.get("avg_ts", 0)])
    pg_samples = pg_row.get("samples_ts", [pg_row.get("avg_ts", 0)])
    n = min(len(pp_samples), len(pg_samples))

    gen_list = []
    pre_list = list(pp_samples[:n])
    for i in range(n):
        pp_ts       = pp_samples[i]
        combined_ts = pg_samples[i]
        if pp_ts <= 0 or combined_ts <= 0:
            continue
        gen_time = (pp_tokens + tg_tokens) / combined_ts - pp_tokens / pp_ts
        if gen_time > 0:
            gen_list.append(tg_tokens / gen_time)

    return {
        "variant":     variant,
        "context":     ctx,
        "n_prompt":    pp_tokens,
        "n_gen":       tg_tokens,
        "prefill_tps": round(statistics.mean(pre_list), 4) if pre_list else 0,
        "prefill_std": round(statistics.stdev(pre_list), 4) if len(pre_list) > 1 else 0,
        "decode_tps":  round(statistics.mean(gen_list), 4) if gen_list else 0,
        "decode_std":  round(statistics.stdev(gen_list), 4) if len(gen_list) > 1 else 0,
        "n_trials":    len(gen_list),
        "device":      socket.gethostname(),
        "arch":        "x86_64",
        "backend":     "CPU",
        "model":       f"{MODEL_PREFIX}-{variant}",
        "ngl":         NGL,
        "threads":     threads,
        "ts":          datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "cliff_sweep",
    }


def print_cliff_summary(results_dir, variants):
    print()
    hr()
    log(f"CLIFF ANALYSIS  —  x86 CPU  —  Qwen 2.5 1.5B")
    hr()
    for variant in variants:
        path = os.path.join(results_dir, f"cliff_{variant}.jsonl")
        if not os.path.isfile(path):
            continue
        rows = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except Exception:
                        pass
        ctx_map = {r["context"]: r for r in rows}
        print(f"\n  {variant}:")
        prev = None
        for c in CTX_SIZES:
            r = ctx_map.get(c)
            d = float(r.get("decode_tps", 0)) if r else 0
            p = float(r.get("prefill_tps", 0)) if r else 0
            std = float(r.get("decode_std", 0)) if r else 0
            cv = f"  CV={std/d:.0%}" if d > 0 else ""
            cliff = "  <- CLIFF" if prev and d > 0 and (prev - d) / prev > 0.10 else ""
            print(f"    ctx={c:5d}:  decode={d:6.2f}±{std:.2f}{cv}  prefill={p:6.1f}{cliff}")
            if d > 0:
                prev = d


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="x86 Qwen 2.5 1.5B KV-cache cliff sweep")
    parser.add_argument("variants", nargs="*", help="Variants to run (default: all 7)")
    parser.add_argument("--resume",  action="store_true", help="Skip already-complete variants")
    parser.add_argument("--threads", type=int, default=None, help="Thread count (default: nproc)")
    args = parser.parse_args()

    variants = args.variants if args.variants else ALL_VARIANTS
    for v in variants:
        if v not in ALL_VARIANTS:
            print(f"ERROR: Unknown variant '{v}'. Choose from: {ALL_VARIANTS}", file=sys.stderr)
            sys.exit(1)

    threads = args.threads or os.cpu_count() or 4

    llama_bench = find_llama_bench()
    if not llama_bench:
        print("FATAL: llama-bench not found.", file=sys.stderr)
        print("  Set LLAMA_BENCH_PATH=<path to llama-bench.exe>", file=sys.stderr)
        sys.exit(1)

    models_dir = find_models_dir()
    missing = []
    for v in variants:
        p = os.path.join(models_dir, f"{MODEL_PREFIX}-{v}.gguf")
        if not os.path.isfile(p):
            missing.append(p)
    if missing:
        print("FATAL: Missing model files:", file=sys.stderr)
        for m in missing:
            print(f"  {m}", file=sys.stderr)
        print("\nDownload with pip install huggingface_hub then see docstring.", file=sys.stderr)
        sys.exit(1)

    host = socket.gethostname()[:12]
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    script_dir   = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.normpath(os.path.join(script_dir, "..", ".."))
    results_dir  = os.path.join(project_root, "results", f"x86_qwen_cliff_{host}_{ts}")
    os.makedirs(results_dir, exist_ok=True)

    hr()
    log(f"x86 CPU  —  Qwen 2.5 1.5B KV-Cache Cliff Sweep  (v2: TG={TG_TOKENS})")
    log(f"Host     : {socket.gethostname()}  (x86_64)")
    log(f"Binary   : {llama_bench}")
    log(f"Models   : {models_dir}")
    log(f"Threads  : {threads}  (ngl=0, CPU only)")
    log(f"Variants : {variants}")
    log(f"Contexts : {CTX_SIZES}")
    log(f"Trials   : {NUM_TRIALS}  |  TG tokens: {TG_TOKENS}")
    log(f"Results  : {results_dir}")
    hr()

    start_s = time.time()
    n_ctx   = len(CTX_SIZES)

    for v_idx, variant in enumerate(variants, 1):
        model_path  = os.path.join(models_dir, f"{MODEL_PREFIX}-{variant}.gguf")
        output_file = os.path.join(results_dir, f"cliff_{variant}.jsonl")
        model_gb    = os.path.getsize(model_path) / 1e9

        if args.resume and os.path.isfile(output_file):
            done = sum(1 for _ in open(output_file) if _.strip())
            if done >= n_ctx:
                log(f"  SKIP {variant} — complete ({done} rows)")
                continue

        log("")
        log(f"=== [{v_idx}/{len(variants)}] {variant}  ({model_gb:.1f} GB) ===")

        with open(output_file, "w") as out_f:
            for ctx_idx, ctx in enumerate(CTX_SIZES, 1):
                pp_tokens = ctx - TG_TOKENS
                if pp_tokens <= 0:
                    log(f"  [ctx={ctx}] SKIP — ctx too small for TG_TOKENS={TG_TOKENS}")
                    continue
                elapsed = int(time.time() - start_s)

                raw = run_llama_bench(
                    llama_bench, model_path,
                    pp_tokens, TG_TOKENS,
                    NUM_TRIALS, NGL, threads,
                )

                record = parse_bench_output(
                    raw, pp_tokens, TG_TOKENS,
                    variant, ctx, threads,
                )

                out_f.write(json.dumps(record) + "\n")
                out_f.flush()

                d   = record.get("decode_tps", 0)
                std = record.get("decode_std", 0)
                p   = record.get("prefill_tps", 0)
                cv  = f"  CV={std/d:.0%}" if d > 0 else ""
                err = record.get("error", "")
                status = f"decode={d:.2f}±{std:.2f}{cv}  prefill={p:.1f}" if not err else f"ERROR: {err}"
                log(f"  [ctx={ctx} {ctx_idx}/{n_ctx} elapsed={elapsed}s]  {variant}  {status}")

        rows = sum(1 for _ in open(output_file) if _.strip())
        log(f"  Saved {output_file}  ({rows} rows)")

    print_cliff_summary(results_dir, variants)

    elapsed = int(time.time() - start_s)
    log("")
    hr()
    log(f"DONE  |  runtime: {elapsed//60}m {elapsed%60}s  |  results: {results_dir}")
    log(f"Next: git add results/x86_qwen_cliff_*  &&  git push")
    hr()


if __name__ == "__main__":
    main()
