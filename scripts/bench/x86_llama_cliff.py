#!/usr/bin/env python3
"""
x86_llama_cliff.py — KV-cache context-length cliff sweep for x86 (Windows/Linux)
                      Llama 3.2 3B · llama-completion.exe · CPU

METHODOLOGY (filled-context):
    For each context size N, the prompt is ~(N - OUTPUT_TOKENS) tokens long,
    so the KV cache is actually populated during decode. This is the correct
    approach for measuring KV-cache throughput sensitivity — using a short
    prompt leaves the cache mostly empty and no cliff is visible.

    Mirrors pixel_llama_cliff_filled.sh exactly so results are directly
    comparable across devices.

Usage:
    py -3 scripts/bench/x86_llama_cliff.py                         # all variants
    py -3 scripts/bench/x86_llama_cliff.py --variants Q4_K_M Q6_K  # subset
    py -3 scripts/bench/x86_llama_cliff.py --resume                 # skip complete
    py -3 scripts/bench/x86_llama_cliff.py --threads 8

Output:
    results/x86_llama_cliff_{ts}/cliff_filled_{VARIANT}.jsonl
    One JSON record per (variant, context, trial).
    Schema matches pixel_llama_cliff_filled results for cross-device comparison.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLAMA_BIN  = Path("C:/temp/llama.cpp/build/bin/Release/llama-completion.exe")
MODELS_DIR = Path("C:/temp/llama3_2_3b_gguf")

ALL_VARIANTS   = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
CTX_SIZES      = [256, 512, 768, 1024, 1200, 1300, 1400, 1500, 1600, 1800, 2048]
NUM_TRIALS     = 3
OUTPUT_TOKENS  = 64
DEFAULT_THREADS = max(1, os.cpu_count() // 2)

PROJECT_ROOT = Path(__file__).parent.parent.parent
RESULTS_BASE = PROJECT_ROOT / "results"

# Seed text for generating prompts of arbitrary token length.
# Llama tokenizer averages ~1.3 chars/token.
SEED_TEXT = (
    "The transformer architecture fundamentally changed natural language processing "
    "by introducing self-attention mechanisms that allow models to relate different "
    "positions of a sequence when computing a representation. Unlike recurrent "
    "networks, transformers process sequences in parallel and use positional encodings "
    "to maintain order information. Each transformer block consists of a multi-head "
    "attention layer followed by a feed-forward network, with layer normalization and "
    "residual connections enabling stable training of deep models. The key innovation "
    "is the attention mechanism itself: for each token, attention computes a weighted "
    "sum of all other token representations, where weights are determined by learned "
    "query and key projections. This allows long-range dependencies to be captured in "
    "a single layer. Modern large language models scale this architecture to billions "
    "of parameters across dozens of layers, using grouped-query attention and other "
    "efficiency improvements to reduce memory requirements during inference."
)

CHARS_PER_TOKEN = 1.3  # approximate for English / Llama tokenizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ts_log() -> str:
    return datetime.now().strftime("%H:%M:%S")

def utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_prompt(target_tokens: int) -> str:
    target_chars = int(target_tokens * CHARS_PER_TOKEN)
    text = SEED_TEXT
    while len(text) < target_chars:
        text += " " + SEED_TEXT
    return text[:target_chars]

def parse_tps(output: str) -> tuple[float, float]:
    """Return (prefill_tps, decode_tps) from llama-completion stderr output."""
    prefill = 0.0
    decode  = 0.0

    # llama.cpp b3+ prefix: "llama_perf_context_print:" or "common_perf_print:"
    for prefix in ("llama_perf_context_print:", "common_perf_print:"):
        m = re.search(
            rf"{re.escape(prefix)}.*?prompt eval time.*?([\d.]+)\s*tokens per second",
            output, re.IGNORECASE
        )
        if m:
            prefill = float(m.group(1))
            break

    for prefix in ("llama_perf_context_print:", "common_perf_print:"):
        # match "eval time" but NOT "prompt eval time"
        m = re.search(
            rf"{re.escape(prefix)}(?!.*prompt)\s*eval time.*?([\d.]+)\s*tokens per second",
            output, re.IGNORECASE
        )
        if m:
            decode = float(m.group(1))
            break

    # Fallback: grab all "tokens per second" values — first=prefill, second=decode
    if prefill == 0.0 or decode == 0.0:
        vals = re.findall(r"([\d.]+)\s*tokens per second", output)
        if len(vals) >= 2 and prefill == 0.0:
            prefill = float(vals[0])
        if len(vals) >= 2 and decode == 0.0:
            decode = float(vals[1])
        elif len(vals) == 1 and decode == 0.0:
            decode = float(vals[0])

    return prefill, decode

def model_path(variant: str) -> Path:
    return MODELS_DIR / f"{variant}.gguf"

def available_variants() -> list[str]:
    return [v for v in ALL_VARIANTS if model_path(v).exists()]

# ---------------------------------------------------------------------------
# Single trial
# ---------------------------------------------------------------------------

def run_trial(
    variant: str,
    ctx: int,
    trial: int,
    threads: int,
    prompt: str,
) -> dict:
    mpath = model_path(variant)
    cmd = [
        str(LLAMA_BIN),
        "-m", str(mpath),
        "-c", str(ctx),
        "-n", str(OUTPUT_TOKENS),
        "--temp", "0.0",
        "--seed", "42",
        "-t", str(threads),
        "-no-cnv",
        "--no-display-prompt",
        "-co", "off",
        "-p", prompt,
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            text=True,
            timeout=300,
        )
        combined = result.stdout + result.stderr
        prefill_tps, decode_tps = parse_tps(combined)
        raw_bytes = len(combined.encode())
    except subprocess.TimeoutExpired:
        prefill_tps, decode_tps, raw_bytes = 0.0, 0.0, 0
    except Exception as e:
        print(f"    ERROR: {e}")
        prefill_tps, decode_tps, raw_bytes = 0.0, 0.0, 0

    return {
        "variant":              variant,
        "context":              ctx,
        "prompt_tokens_approx": ctx - OUTPUT_TOKENS,
        "trial":                trial,
        "decode_tps":           round(decode_tps,  3),
        "prefill_tps":          round(prefill_tps, 3),
        "raw_bytes":            raw_bytes,
        "device":               "x86",
        "backend":              "CPU",
        "methodology":          "filled_context",
        "model":                f"Llama-3.2-3B-Instruct-{variant}",
        "threads":              threads,
        "n_output_tokens":      OUTPUT_TOKENS,
        "ts":                   utc_iso(),
    }

# ---------------------------------------------------------------------------
# Analysis summary
# ---------------------------------------------------------------------------

def print_summary(results_dir: Path, variants: list[str]) -> None:
    from collections import defaultdict

    print(f"\n{'='*72}")
    print("CLIFF ANALYSIS (FILLED CONTEXT) — x86 CPU")
    print(f"{'='*72}")

    for variant in variants:
        path = results_dir / f"cliff_filled_{variant}.jsonl"
        if not path.exists():
            continue
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        ctx_d: dict[int, list] = defaultdict(list)
        ctx_p: dict[int, list] = defaultdict(list)
        for r in rows:
            if r["decode_tps"]  > 0: ctx_d[r["context"]].append(r["decode_tps"])
            if r["prefill_tps"] > 0: ctx_p[r["context"]].append(r["prefill_tps"])

        valid = sum(len(v) for v in ctx_d.values())
        print(f"\n{variant}  ({valid}/{len(rows)} valid)")
        print(f"  {'ctx':>6}  {'decode':>10}  {'prefill':>10}  {'Δ from baseline':>16}  n")
        print(f"  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*16}  -")

        baseline = None
        prev_avg = None
        ctxs = sorted(ctx_d)
        for ctx in ctxs:
            avg  = sum(ctx_d[ctx]) / len(ctx_d[ctx])
            pavg = sum(ctx_p[ctx]) / len(ctx_p[ctx]) if ctx_p.get(ctx) else 0.0
            if baseline is None:
                baseline = avg
            pct_base = (avg - baseline) / baseline * 100 if baseline else 0.0
            cliff = ""
            if prev_avg and prev_avg > 0 and (prev_avg - avg) / prev_avg > 0.10:
                cliff = f"  <- CLIFF {(prev_avg - avg)/prev_avg*100:.0f}%"
            print(f"  {ctx:>6}  {avg:>9.2f}  {pavg:>9.1f}  {pct_base:>+14.1f}%  {len(ctx_d[ctx])}{cliff}")
            prev_avg = avg

        if baseline and ctxs:
            final = sum(ctx_d[ctxs[-1]]) / len(ctx_d[ctxs[-1]])
            drop  = (baseline - final) / baseline * 100
            cliff_ctx = None
            for i in range(1, len(ctxs)):
                prev = sum(ctx_d[ctxs[i-1]]) / len(ctx_d[ctxs[i-1]])
                curr = sum(ctx_d[ctxs[i]])   / len(ctx_d[ctxs[i]])
                if prev > 0 and (prev - curr) / prev > 0.10:
                    cliff_ctx = ctxs[i]
                    break
            cliff_str = f"  cliff onset: ctx={cliff_ctx}" if cliff_ctx else "  no cliff detected"
            print(f"\n  Total drop ctx={ctxs[0]}→{ctxs[-1]}: {drop:.1f}%{cliff_str}")

# ---------------------------------------------------------------------------
# Main sweep
# ---------------------------------------------------------------------------

def run_sweep(variants: list[str], threads: int, resume: bool) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = RESULTS_BASE / f"x86_llama_cliff_{ts}"
    results_dir.mkdir(parents=True, exist_ok=True)

    expected_per_variant = len(CTX_SIZES) * NUM_TRIALS
    total_runs = len(variants) * expected_per_variant
    current_run = 0
    start = time.time()

    print(f"\n{'='*72}")
    print(f"x86 Llama 3.2 3B  —  KV-Cache Cliff Sweep (filled context)")
    print(f"  Variants : {', '.join(variants)}")
    print(f"  Contexts : {CTX_SIZES}")
    print(f"  Trials   : {NUM_TRIALS}  |  Output tokens: {OUTPUT_TOKENS}")
    print(f"  Threads  : {threads}")
    print(f"  Results  : {results_dir}")
    print(f"{'='*72}\n")

    for variant in variants:
        output_file = results_dir / f"cliff_filled_{variant}.jsonl"

        if resume and output_file.exists():
            done = sum(1 for l in output_file.read_text().splitlines() if l.strip())
            if done >= expected_per_variant:
                print(f"[{ts_log()}] SKIP {variant} — already complete ({done} rows)")
                current_run += expected_per_variant
                continue
            print(f"[{ts_log()}] RESUME {variant} — {done}/{expected_per_variant} done")
            output_file.unlink()

        print(f"\n[{ts_log()}] --- {variant} ---")
        fh = output_file.open("w")

        for ctx in CTX_SIZES:
            prompt_tokens = ctx - OUTPUT_TOKENS
            prompt = generate_prompt(prompt_tokens)

            for trial in range(1, NUM_TRIALS + 1):
                current_run += 1
                elapsed = time.time() - start
                eta = int(elapsed * total_runs / current_run - elapsed) if current_run > 1 else 0

                rec = run_trial(variant, ctx, trial, threads, prompt)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()

                status = "OK" if rec["decode_tps"] > 0 else "FAIL"
                print(
                    f"  [{current_run:>4}/{total_runs} eta={eta}s]"
                    f"  ctx={ctx:<5} t={trial}"
                    f"  decode={rec['decode_tps']:>6.2f} t/s"
                    f"  prefill={rec['prefill_tps']:>6.1f} t/s"
                    f"  [{status}]"
                )

        fh.close()
        rows = sum(1 for l in output_file.read_text().splitlines() if l.strip())
        print(f"[{ts_log()}]   Saved {output_file.name}  ({rows} rows)")

    elapsed_total = time.time() - start
    print(f"\n[{ts_log()}] DONE  |  runtime: {int(elapsed_total//60)}m {int(elapsed_total%60)}s")
    return results_dir

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="x86 KV-cache context-length cliff sweep")
    p.add_argument("--variants", nargs="+", default=None,
                   help="Variants to sweep (default: all available)")
    p.add_argument("--threads",  type=int, default=DEFAULT_THREADS,
                   help=f"CPU threads (default: {DEFAULT_THREADS})")
    p.add_argument("--resume",   action="store_true",
                   help="Skip variants whose output file already has all rows")
    p.add_argument("--ctx-sizes", nargs="+", type=int, default=None,
                   help="Override context sizes (e.g. --ctx-sizes 256 512 1024 2048)")
    return p.parse_args()


def main():
    args = parse_args()

    if not LLAMA_BIN.exists():
        print(f"ERROR: binary not found: {LLAMA_BIN}")
        sys.exit(1)

    variants = args.variants or available_variants()
    if not variants:
        print(f"ERROR: no GGUF models found in {MODELS_DIR}")
        sys.exit(1)

    missing = [v for v in variants if not model_path(v).exists()]
    if missing:
        print(f"WARNING: skipping (not on disk): {missing}")
        variants = [v for v in variants if model_path(v).exists()]

    if args.ctx_sizes:
        global CTX_SIZES
        CTX_SIZES = sorted(args.ctx_sizes)

    results_dir = run_sweep(variants, args.threads, args.resume)
    print_summary(results_dir, variants)


if __name__ == "__main__":
    main()
