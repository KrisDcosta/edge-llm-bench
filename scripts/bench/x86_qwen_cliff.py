#!/usr/bin/env python3
"""
x86_qwen_cliff.py  —  KV-cache context-length cliff sweep for x86 (Windows/Linux)
                       Qwen 2.5 1.5B Instruct · llama-completion(.exe) · CPU

PURPOSE
-------
Measures how decode throughput changes as context length grows from 256 to 2048
tokens. On ARM (Pixel 6a) we already confirmed that Q2_K has a -48% "cliff" at
ctx≈512 and Q3_K_M is cliff-immune. This script replicates that same test on
x86 (AVX2) for Qwen 2.5 1.5B so we can verify:
  a) The non-monotonic throughput ordering (Q2_K fastest → Q6_K slowest) holds.
  b) The cliff context threshold follows the same L2-cache formula:
       cliff_ctx ≈ L2_cache / (2 × n_layers × n_kv_heads × head_dim × 2B)
     For Qwen 2.5 1.5B (28 layers, 8 KV heads, head_dim=64):
       cliff_ctx ≈ 1.25 MB / (2 × 28 × 8 × 64 × 2) = ~1,760 tokens  (rough estimate)
  c) Results are comparable to the Llama x86 cliff already in the dataset.

METHODOLOGY — FILLED CONTEXT
-----------------------------
For each target context size N, the prompt is (N - 64) tokens long. This means
the KV cache is actually *populated* during decode. A short prompt would leave
the cache mostly empty and mask the cliff entirely. This mirrors the methodology
used in pixel_qwen_cliff_filled.sh and x86_llama_cliff.py.

USAGE
-----
  # All 7 variants, auto-detect thread count (Windows):
  py -3 scripts/bench/x86_qwen_cliff.py

  # Specific variants only:
  py -3 scripts/bench/x86_qwen_cliff.py --variants Q2_K Q3_K_M Q4_K_M

  # Resume a partial run (skips variants already complete):
  py -3 scripts/bench/x86_qwen_cliff.py --resume

  # Override thread count:
  py -3 scripts/bench/x86_qwen_cliff.py --threads 8

  # Override binary path:
  py -3 scripts/bench/x86_qwen_cliff.py --bin C:/path/to/llama-completion.exe

OUTPUT
------
  results/x86_qwen_cliff_{timestamp}/cliff_filled_{VARIANT}.jsonl
  Each line is one JSON record: (variant, context, trial, decode_tps, prefill_tps, …)
  Schema matches x86_llama_cliff.py so prepare_dataset.py ingests both identically.

RUNTIME ESTIMATE
----------------
  7 variants × 11 contexts × 5 trials = 385 runs.
  Qwen 2.5 1.5B is smaller than Llama 3.2 3B, roughly 1.5–2× faster.
  Estimated: ~3–5 hours total. Each variant ~25–40 min.

PREREQUISITES
-------------
  1. llama-completion.exe at C:/temp/llama.cpp/build/bin/Release/
     (same binary used for x86_llama_cliff.py — no rebuild needed)
  2. Qwen GGUF files at C:/temp/qwen2_5_1_5b_gguf/
     Named: Qwen2.5-1.5B-Instruct-Q2_K.gguf  (and Q3_K_M, Q4_K_S, etc.)
     If missing, run the download block at the bottom of this docstring.

DOWNLOAD MODELS (one-time, needs WiFi)
---------------------------------------
  pip install huggingface_hub
  python3 -c "
  from huggingface_hub import hf_hub_download
  import os
  os.makedirs('C:/temp/qwen2_5_1_5b_gguf', exist_ok=True)
  for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:
      hf_hub_download(
          'bartowski/Qwen2.5-1.5B-Instruct-GGUF',
          f'Qwen2.5-1.5B-Instruct-{v}.gguf',
          local_dir='C:/temp/qwen2_5_1_5b_gguf')
  "

AFTER RUNNING
-------------
  Copy the results/ directory back to the Mac, then:
    python3 scripts/prepare_dataset.py       # rebuilds all parquets
    python3 scripts/bake_dashboard_data.py   # rebuilds dashboard JSON
  The cross-device heatmap will then show context-sensitive Qwen x86 values.
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

# ── Configuration ─────────────────────────────────────────────────────────────
# Path to the llama-completion binary. Update if your build is elsewhere.
LLAMA_BIN  = Path("C:/temp/llama.cpp/build/bin/Release/llama-completion.exe")

# Directory containing Qwen2.5-1.5B-Instruct-{VARIANT}.gguf files.
MODELS_DIR = Path("C:/temp/qwen2_5_1_5b_gguf")

# Model filename prefix (combined with variant: e.g. "Qwen2.5-1.5B-Instruct-Q4_K_M.gguf")
MODEL_PREFIX = "Qwen2.5-1.5B-Instruct"

# The 7 standard K-quant variants we benchmark.
ALL_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]

# Context sizes that span the KV-cache cliff region.
# Mirrors x86_llama_cliff.py exactly so results are directly comparable.
CTX_SIZES = [256, 512, 768, 1024, 1200, 1300, 1400, 1500, 1600, 1800, 2048]

# Number of decode trials per (variant, context) cell.
# n=5 is sufficient for publishable mean ± CI with reasonable runtime.
NUM_TRIALS = 5

# Tokens generated per trial. Small enough to be fast; large enough to measure
# steady-state decode throughput beyond the initial prefill cost.
OUTPUT_TOKENS = 64

# Default thread count: half of logical CPUs is typically optimal on x86
# because hyperthreading siblings share execution units with llama.cpp workloads.
DEFAULT_THREADS = max(1, os.cpu_count() // 2)

# Where results are written (relative to repo root).
PROJECT_ROOT = Path(__file__).parent.parent.parent
RESULTS_BASE = PROJECT_ROOT / "results"

# Seed text for building prompts of arbitrary length.
# English prose averages ~1.3 chars per Qwen token, similar to Llama.
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
CHARS_PER_TOKEN = 1.3  # approximate chars per token for Qwen tokenizer

# ── Helpers ───────────────────────────────────────────────────────────────────

def ts_log() -> str:
    """Return current time as HH:MM:SS for log lines."""
    return datetime.now().strftime("%H:%M:%S")

def utc_iso() -> str:
    """Return current UTC time in ISO 8601 format for JSON records."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def generate_prompt(target_tokens: int) -> str:
    """Build a prompt string approximately target_tokens tokens long.

    We repeat the seed text until we have enough characters, then truncate.
    The exact token count will vary slightly due to tokenizer differences,
    but this is within ±5% which is acceptable for fill methodology.
    """
    target_chars = int(target_tokens * CHARS_PER_TOKEN)
    text = SEED_TEXT
    while len(text) < target_chars:
        text += " " + SEED_TEXT
    return text[:target_chars]

def parse_tps(output: str) -> tuple[float, float]:
    """Extract (prefill_tps, decode_tps) from llama-completion stderr.

    llama.cpp prints performance stats to stderr in lines like:
      llama_perf_context_print:   prompt eval time =  1234.5 ms / 500 tokens (2.47 ms/t, 405.2 t/s)
      llama_perf_context_print:          eval time =  4567.8 ms /  64 tokens (71.4 ms/t,  14.0 t/s)

    We match "tokens per second" values from those lines.
    """
    prefill = 0.0
    decode  = 0.0

    # Try the structured prefix first (llama.cpp ≥b3)
    for prefix in ("llama_perf_context_print:", "common_perf_print:"):
        m = re.search(
            rf"{re.escape(prefix)}.*?prompt eval time.*?([\d.]+)\s*tokens per second",
            output, re.IGNORECASE
        )
        if m:
            prefill = float(m.group(1))
            break

    for prefix in ("llama_perf_context_print:", "common_perf_print:"):
        # Match "eval time" but NOT "prompt eval time"
        m = re.search(
            rf"{re.escape(prefix)}(?!.*prompt)\s*eval time.*?([\d.]+)\s*tokens per second",
            output, re.IGNORECASE
        )
        if m:
            decode = float(m.group(1))
            break

    # Fallback: grab all "tokens per second" values in order — first=prefill, second=decode
    if prefill == 0.0 or decode == 0.0:
        vals = re.findall(r"([\d.]+)\s*tokens per second", output)
        if len(vals) >= 2:
            if prefill == 0.0: prefill = float(vals[0])
            if decode  == 0.0: decode  = float(vals[1])
        elif len(vals) == 1 and decode == 0.0:
            decode = float(vals[0])

    return prefill, decode

def model_path(variant: str) -> Path:
    """Return the full path for a given variant's GGUF file."""
    return MODELS_DIR / f"{MODEL_PREFIX}-{variant}.gguf"

def available_variants() -> list[str]:
    """Return only those variants whose GGUF files are present on disk."""
    return [v for v in ALL_VARIANTS if model_path(v).exists()]

# ── Single trial ──────────────────────────────────────────────────────────────

def run_trial(variant: str, ctx: int, trial: int, threads: int, prompt: str) -> dict:
    """Run one llama-completion inference and return a measurement record.

    Calls llama-completion with:
      -c ctx        → KV cache size (allocates the full context window)
      -n OUTPUT_TOKENS → tokens to generate
      --temp 0.0    → greedy decoding (deterministic, no sampling overhead)
      -no-cnv       → disable chat-template wrapping
      -p prompt     → the filled-context prompt

    Returns a dict matching the x86_llama_cliff.py schema so that
    prepare_dataset.py can ingest both files with the same logic.
    """
    cmd = [
        str(LLAMA_BIN),
        "-m", str(model_path(variant)),
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
            timeout=300,   # 5-minute hard timeout per trial
        )
        combined = result.stdout + result.stderr
        prefill_tps, decode_tps = parse_tps(combined)
        raw_bytes = len(combined.encode())
    except subprocess.TimeoutExpired:
        print(f"    TIMEOUT at ctx={ctx} trial={trial}")
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
        # Tag this as Qwen so prepare_dataset.py assigns model=Qwen
        "model":                f"Qwen2.5-1.5B-Instruct-{variant}",
        "threads":              threads,
        "n_output_tokens":      OUTPUT_TOKENS,
        "ts":                   utc_iso(),
    }

# ── Summary printout ──────────────────────────────────────────────────────────

def print_summary(results_dir: Path, variants: list[str]) -> None:
    """Print a cliff analysis table after the sweep completes.

    Shows decode TPS at each context length, % change from baseline (ctx=256),
    and flags any drop >10% between consecutive context sizes as a cliff.
    """
    from collections import defaultdict

    print(f"\n{'='*72}")
    print("CLIFF ANALYSIS (FILLED CONTEXT) — x86 CPU — Qwen 2.5 1.5B")
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
        print(f"  {'ctx':>6}  {'decode':>10}  {'prefill':>10}  {'Δ from ctx=256':>15}  n")
        print(f"  {'-'*6}  {'-'*10}  {'-'*10}  {'-'*15}  -")

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
                cliff = f"  ← CLIFF {(prev_avg - avg) / prev_avg * 100:.0f}%"
            print(f"  {ctx:>6}  {avg:>9.2f}  {pavg:>9.1f}  {pct_base:>+13.1f}%  {len(ctx_d[ctx])}{cliff}")
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

    print(f"\n{'='*72}")
    print("Next steps:")
    print("  1. Copy results/ back to the Mac repo")
    print("  2. python3 scripts/prepare_dataset.py")
    print("  3. python3 scripts/bake_dashboard_data.py")
    print("  The cross-device heatmap will then show context-sensitive Qwen x86 values.")
    print(f"{'='*72}\n")

# ── Main sweep ────────────────────────────────────────────────────────────────

def run_sweep(variants: list[str], threads: int, resume: bool) -> Path:
    """Run the full cliff sweep and return the results directory path."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = RESULTS_BASE / f"x86_qwen_cliff_{ts}"
    results_dir.mkdir(parents=True, exist_ok=True)

    expected_per_variant = len(CTX_SIZES) * NUM_TRIALS  # 11 × 5 = 55
    total_runs   = len(variants) * expected_per_variant
    current_run  = 0
    start        = time.time()

    print(f"\n{'='*72}")
    print(f"x86 Qwen 2.5 1.5B  —  KV-Cache Cliff Sweep (filled context)")
    print(f"  Variants : {', '.join(variants)}")
    print(f"  Contexts : {CTX_SIZES}")
    print(f"  Trials   : {NUM_TRIALS}  |  Output tokens: {OUTPUT_TOKENS}")
    print(f"  Threads  : {threads}")
    print(f"  Results  : {results_dir}")
    print(f"{'='*72}\n")

    for variant in variants:
        output_file = results_dir / f"cliff_filled_{variant}.jsonl"

        # Resume: skip this variant if its output file is already complete.
        if resume and output_file.exists():
            done = sum(1 for l in output_file.read_text().splitlines() if l.strip())
            if done >= expected_per_variant:
                print(f"[{ts_log()}] SKIP {variant} — already complete ({done} rows)")
                current_run += expected_per_variant
                continue
            print(f"[{ts_log()}] RESUME {variant} — {done}/{expected_per_variant} done")
            output_file.unlink()  # restart the variant from scratch

        print(f"\n[{ts_log()}] ─── {variant} ───")
        fh = output_file.open("w")

        for ctx in CTX_SIZES:
            # Build a prompt that fills (ctx - OUTPUT_TOKENS) tokens so the
            # KV cache is populated during decode (filled-context methodology).
            prompt_tokens = ctx - OUTPUT_TOKENS
            prompt = generate_prompt(prompt_tokens)

            for trial in range(1, NUM_TRIALS + 1):
                current_run += 1
                elapsed = time.time() - start
                # ETA: assume uniform time per run
                eta = int(elapsed * total_runs / current_run - elapsed) if current_run > 1 else 0

                rec = run_trial(variant, ctx, trial, threads, prompt)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()  # flush after each trial so data is safe if interrupted

                status = "OK" if rec["decode_tps"] > 0 else "FAIL"
                print(
                    f"  [{current_run:>4}/{total_runs}  eta={eta//60}m{eta%60:02d}s]"
                    f"  ctx={ctx:<5}  t={trial}"
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

# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="x86 Qwen 2.5 1.5B KV-cache cliff sweep (filled-context methodology)"
    )
    p.add_argument(
        "--variants", nargs="+", default=None,
        help="Variants to run (default: all available on disk)"
    )
    p.add_argument(
        "--threads", type=int, default=DEFAULT_THREADS,
        help=f"CPU thread count (default: {DEFAULT_THREADS} — half of logical CPUs)"
    )
    p.add_argument(
        "--resume", action="store_true",
        help="Skip variants whose output file already has the expected row count"
    )
    p.add_argument(
        "--bin", type=Path, default=LLAMA_BIN,
        help=f"Path to llama-completion binary (default: {LLAMA_BIN})"
    )
    p.add_argument(
        "--ctx-sizes", nargs="+", type=int, default=None,
        help="Override context sizes (e.g. --ctx-sizes 256 512 1024 2048)"
    )
    p.add_argument(
        "--trials", type=int, default=None,
        help=f"Trials per (variant, context) cell (default: {NUM_TRIALS})"
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Allow --bin to override the default binary path
    global LLAMA_BIN, CTX_SIZES, NUM_TRIALS
    LLAMA_BIN = args.bin

    if not LLAMA_BIN.exists():
        print(f"ERROR: binary not found at {LLAMA_BIN}")
        print(f"       Build llama.cpp or set --bin to the correct path.")
        sys.exit(1)

    if args.ctx_sizes:
        CTX_SIZES = sorted(args.ctx_sizes)
    if args.trials:
        NUM_TRIALS = args.trials

    # Determine which variants to run
    variants = args.variants or available_variants()
    if not variants:
        print(f"ERROR: no Qwen GGUF files found in {MODELS_DIR}")
        print(f"       Run the download snippet in the docstring at the top of this file.")
        sys.exit(1)

    # Warn about missing models but continue with what's available
    missing = [v for v in variants if not model_path(v).exists()]
    if missing:
        print(f"WARNING: skipping (not on disk): {missing}")
        variants = [v for v in variants if model_path(v).exists()]

    if not variants:
        print("ERROR: no models available after filtering missing files.")
        sys.exit(1)

    results_dir = run_sweep(variants, args.threads, args.resume)
    print_summary(results_dir, variants)


if __name__ == "__main__":
    main()
