#!/usr/bin/env python3
"""
run_x86_benchmark.py — Run llama.cpp benchmarks natively on x86 Windows.

Covers three benchmark types:
  1. TPS (throughput)   — llama-bench: prefill + decode tokens/s across all quants
  2. Perplexity         — llama-perplexity: WikiText-2 PPL per quant
  3. Quality (accuracy) — llama-cli: ARC-Easy / BoolQ / TruthfulQA exact-match via quality_eval.py

Usage:
    python3 scripts/run_x86_benchmark.py --all
    python3 scripts/run_x86_benchmark.py --tps
    python3 scripts/run_x86_benchmark.py --perplexity
    python3 scripts/run_x86_benchmark.py --quality
    python3 scripts/run_x86_benchmark.py --tps --variants Q4_K_M Q5_K_M Q6_K
    python3 scripts/run_x86_benchmark.py --all --threads 8

Output:
    results/x86_tps_results.json
    results/x86_perplexity_results.json
    results/x86_quality_results.json  (delegates to quality_eval.py)
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

LLAMA_BIN_DIR = Path("C:/temp/llama.cpp/build/bin/Release")
LLAMA_BENCH   = LLAMA_BIN_DIR / "llama-bench.exe"
LLAMA_PPL     = LLAMA_BIN_DIR / "llama-perplexity.exe"
LLAMA_CLI     = LLAMA_BIN_DIR / "llama-completion.exe"

MODELS_DIR = Path("C:/temp/llama3_2_3b_gguf")

RESULTS_DIR = PROJECT_ROOT / "results"
RESULTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

ALL_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q4_K_S", "Q5_K_M", "Q6_K"]

def model_path(variant: str) -> Path:
    return MODELS_DIR / f"{variant}.gguf"

def available_variants() -> list[str]:
    return [v for v in ALL_VARIANTS if model_path(v).exists()]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")

def run(cmd: list, timeout: int = 600) -> tuple[int, str, str]:
    """Run a subprocess; return (returncode, stdout, stderr)."""
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return result.returncode, result.stdout, result.stderr

def cpu_info() -> str:
    """Return a one-line CPU description."""
    try:
        if sys.platform == "win32":
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            name, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return name.strip()
    except Exception:
        pass
    return platform.processor() or "unknown"

# ---------------------------------------------------------------------------
# 1. TPS benchmark  (llama-bench)
# ---------------------------------------------------------------------------

def run_tps(variants: list[str], threads: int) -> dict:
    """
    Run llama-bench for each variant.

    llama-bench output (CSV-like) columns:
        model, size, params, backend, ngl, n_batch, n_ubatch, type_k, type_v,
        n_threads, n_gpu_layers, test, t/s

    We run two tests per model: pp (prompt processing / prefill) and tg (token generation / decode).
    -pg 512,128 means: prefill 512 tokens, generate 128 tokens.
    """
    print(f"\n{'='*60}")
    print(f"TPS BENCHMARK  ({len(variants)} variants, {threads} threads)")
    print(f"{'='*60}")

    results = {}
    for variant in variants:
        mpath = model_path(variant)
        print(f"\n[{ts()}] {variant}  ({mpath.name})")

        cmd = [
            str(LLAMA_BENCH),
            "-m", str(mpath),
            "-t", str(threads),
            "--n-gpu-layers", "0",   # CPU only
            "-p", "512",             # prefill tokens
            "-n", "128",             # generation tokens
            "-r", "3",               # repetitions for stable mean
            "--output", "jsonl",
        ]

        try:
            rc, stdout, stderr = run(cmd, timeout=600)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after 600s")
            results[variant] = {"status": "timeout"}
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            results[variant] = {"status": f"error: {e}"}
            continue

        if rc != 0:
            print(f"  FAILED (rc={rc})")
            print(f"  stderr: {stderr[:400]}")
            results[variant] = {"status": f"failed rc={rc}", "stderr": stderr[:400]}
            continue

        # Parse JSONL output — llama-bench emits one JSON object per test run
        prefill_tps_list = []
        decode_tps_list  = []

        for line in stdout.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            test = rec.get("n_prompt", 0), rec.get("n_gen", 0)
            tps  = rec.get("avg_ts", rec.get("t/s", None))
            if tps is None:
                continue

            if rec.get("n_prompt", 0) > 0 and rec.get("n_gen", 0) == 0:
                prefill_tps_list.append(float(tps))
            elif rec.get("n_gen", 0) > 0 and rec.get("n_prompt", 0) == 0:
                decode_tps_list.append(float(tps))
            # mixed pp+tg: llama-bench logs pp and tg separately — handled above

        # Fallback: parse the human-readable table if JSONL empty
        if not prefill_tps_list and not decode_tps_list:
            prefill_tps_list, decode_tps_list = _parse_bench_table(stdout)

        prefill_tps = sum(prefill_tps_list) / len(prefill_tps_list) if prefill_tps_list else None
        decode_tps  = sum(decode_tps_list)  / len(decode_tps_list)  if decode_tps_list  else None

        results[variant] = {
            "status":      "ok",
            "prefill_tps": round(prefill_tps, 2) if prefill_tps else None,
            "decode_tps":  round(decode_tps,  2) if decode_tps  else None,
            "threads":     threads,
            "raw_stdout":  stdout,
        }

        print(f"  prefill: {prefill_tps:.1f} t/s" if prefill_tps else "  prefill: N/A")
        print(f"  decode:  {decode_tps:.1f} t/s"  if decode_tps  else "  decode:  N/A")

    return results


def _parse_bench_table(stdout: str):
    """
    Fallback parser for llama-bench human-readable output.

    Table lines look like:
        | Q4_K_M ... | pp 512 |  ... | 1234.56 ± 12.34 |
        | Q4_K_M ... | tg 128 |  ... |   45.67 ± 0.89  |
    """
    prefill = []
    decode  = []
    for line in stdout.splitlines():
        # Match rows that contain t/s value
        m = re.search(r"\|\s*(pp\s*\d+|tg\s*\d+).*?\|\s*([\d.]+)\s*±", line)
        if not m:
            # Try plain "t/s" number at end of pipe-delimited row
            m = re.search(r"\|\s*(pp\s*\d+|tg\s*\d+).*?\|\s*([\d.]+)\s*\|", line)
        if m:
            test_type = m.group(1).strip()
            tps_val   = float(m.group(2))
            if test_type.startswith("pp"):
                prefill.append(tps_val)
            else:
                decode.append(tps_val)
    return prefill, decode


# ---------------------------------------------------------------------------
# 2. Perplexity benchmark  (llama-perplexity)
# ---------------------------------------------------------------------------

def run_perplexity(variants: list[str], threads: int) -> dict:
    """
    Run llama-perplexity on WikiText-2 sample for each variant.
    Uses the same corpus already in data/ (wikitext2_sample.txt).
    """
    corpus = PROJECT_ROOT / "data" / "wikitext2_sample.txt"
    if not corpus.exists():
        print(f"ERROR: WikiText-2 corpus not found at {corpus}")
        print("Run: python3 scripts/download_wikitext2.py")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"PERPLEXITY BENCHMARK  ({len(variants)} variants)")
    print(f"Corpus: {corpus} ({corpus.stat().st_size:,} bytes)")
    print(f"{'='*60}")

    results = {}
    for variant in variants:
        mpath = model_path(variant)
        print(f"\n[{ts()}] {variant}  ({mpath.name})")

        cmd = [
            str(LLAMA_PPL),
            "-m", str(mpath),
            "-f", str(corpus),
            "-t", str(threads),
            "--seed", "42",
            "--n-gpu-layers", "0",
        ]

        try:
            rc, stdout, stderr = run(cmd, timeout=1200)
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after 1200s")
            results[variant] = {"status": "timeout"}
            continue
        except Exception as e:
            print(f"  ERROR: {e}")
            results[variant] = {"status": f"error: {e}"}
            continue

        combined = stdout + stderr

        # Parse PPL from: "Final estimate: PPL = 8.1234 +/- 0.0456"
        m = re.search(r"Final estimate:\s*PPL\s*=\s*([\d.]+)", combined)
        if m:
            ppl = float(m.group(1))
            results[variant] = {"status": "ok", "perplexity": ppl}
            print(f"  PPL = {ppl:.4f}")
        else:
            # Try intermediate lines: "[10]8.1234..."
            m2 = re.findall(r"\[\d+\]\s*([\d.]+)", combined)
            if m2:
                ppl = float(m2[-1])
                results[variant] = {"status": "ok_partial", "perplexity": ppl}
                print(f"  PPL ≈ {ppl:.4f} (partial)")
            else:
                print(f"  PARSE FAIL (rc={rc})")
                print(f"  last 5 lines: {combined.splitlines()[-5:]}")
                results[variant] = {"status": "parse_failure", "stderr": combined[-600:]}

    return results


# ---------------------------------------------------------------------------
# 3. Quality eval  (delegates to quality_eval.py)
# ---------------------------------------------------------------------------

def run_quality(variants: list[str], threads: int, datasets: list[str]) -> None:
    """
    Delegate to quality_eval.py with --x86 flag for each dataset × variant.
    Results are written by quality_eval.py to results/quality_scores.json.
    """
    print(f"\n{'='*60}")
    print(f"QUALITY EVALUATION  (datasets: {', '.join(datasets)})")
    print(f"{'='*60}")

    quality_script = SCRIPT_DIR / "quality_eval.py"
    if not quality_script.exists():
        print(f"ERROR: {quality_script} not found")
        return

    dataset_map = {
        "arc_easy":    PROJECT_ROOT / "data" / "arc_easy_100.yaml",
        "boolq":       PROJECT_ROOT / "data" / "boolq_100.yaml",
        "arc_challenge": PROJECT_ROOT / "data" / "arc_challenge_100.yaml",
        "truthfulqa":  PROJECT_ROOT / "data" / "truthfulqa_100.yaml",
    }

    for dataset_tag in datasets:
        dataset_path = dataset_map.get(dataset_tag)
        if not dataset_path or not dataset_path.exists():
            print(f"  [{dataset_tag}] SKIP — dataset file not found")
            continue

        print(f"\n  Dataset: {dataset_tag}")
        cmd = [
            sys.executable, str(quality_script),
            "--dataset", str(dataset_path),
            "--tag", f"x86_{dataset_tag}",
            "--x86",
            "--x86-llama-cli", str(LLAMA_CLI),
            "--x86-models-dir", str(MODELS_DIR),
            "--threads", str(threads),
        ] + variants

        rc = subprocess.call(cmd)
        if rc != 0:
            print(f"  quality_eval.py exited with rc={rc}")


# ---------------------------------------------------------------------------
# Save results
# ---------------------------------------------------------------------------

def save_results(filename: str, data: dict, meta: dict) -> Path:
    out = RESULTS_DIR / filename
    # Merge with existing results so partial runs don't lose previous variants
    if out.exists():
        try:
            existing = json.loads(out.read_text())
            merged = existing.get("results", {})
            merged.update(data)
            data = merged
        except (json.JSONDecodeError, KeyError):
            pass
    payload = {"meta": meta, "results": data}
    out.write_text(json.dumps(payload, indent=2))
    print(f"\nSaved: {out}")
    return out


# ---------------------------------------------------------------------------
# Print summary table
# ---------------------------------------------------------------------------

def print_tps_table(results: dict) -> None:
    print(f"\n{'='*60}")
    print(f"{'Variant':<12} {'Prefill (t/s)':>15} {'Decode (t/s)':>14}")
    print(f"{'-'*12} {'-'*15} {'-'*14}")
    for variant, r in results.items():
        if r.get("status") == "ok":
            pre = f"{r['prefill_tps']:.1f}" if r.get("prefill_tps") else "N/A"
            dec = f"{r['decode_tps']:.1f}"  if r.get("decode_tps")  else "N/A"
        else:
            pre = dec = r.get("status", "?")
        print(f"{variant:<12} {pre:>15} {dec:>14}")


def print_ppl_table(results: dict) -> None:
    print(f"\n{'='*60}")
    print(f"{'Variant':<12} {'Perplexity':>12} {'Status':>12}")
    print(f"{'-'*12} {'-'*12} {'-'*12}")
    for variant, r in results.items():
        ppl = f"{r['perplexity']:.4f}" if r.get("perplexity") else "N/A"
        print(f"{variant:<12} {ppl:>12} {r.get('status','?'):>12}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="x86 llama.cpp benchmark runner")
    p.add_argument("--all",        action="store_true", help="Run TPS + perplexity + quality")
    p.add_argument("--tps",        action="store_true", help="Run TPS benchmark only")
    p.add_argument("--perplexity", action="store_true", help="Run perplexity benchmark only")
    p.add_argument("--quality",    action="store_true", help="Run quality eval only")
    p.add_argument("--variants",   nargs="+", default=None,
                   help="Variants to benchmark (default: all available)")
    p.add_argument("--threads",    type=int, default=max(1, os.cpu_count() // 2),
                   help="CPU threads to use (default: half of logical cores)")
    p.add_argument("--datasets",   nargs="+",
                   default=["arc_easy", "arc_challenge", "boolq", "truthfulqa"],
                   help="Quality eval datasets (default: arc_easy boolq truthfulqa)")
    p.add_argument("--dry-run",    action="store_true",
                   help="Print commands without running them")
    return p.parse_args()


def main():
    args = parse_args()

    if not any([args.all, args.tps, args.perplexity, args.quality]):
        print("Specify at least one of: --all  --tps  --perplexity  --quality")
        sys.exit(1)

    # Validate binaries
    for binary in [LLAMA_BENCH, LLAMA_PPL, LLAMA_CLI]:
        if not binary.exists():
            print(f"ERROR: binary not found: {binary}")
            sys.exit(1)

    variants = args.variants or available_variants()
    if not variants:
        print(f"ERROR: no GGUF models found in {MODELS_DIR}")
        sys.exit(1)

    # Filter to only models that exist on disk
    missing = [v for v in variants if not model_path(v).exists()]
    if missing:
        print(f"WARNING: skipping variants not found on disk: {missing}")
        variants = [v for v in variants if model_path(v).exists()]

    threads = args.threads

    meta = {
        "timestamp":  datetime.now().isoformat(),
        "cpu":        cpu_info(),
        "platform":   platform.platform(),
        "threads":    threads,
        "variants":   variants,
        "models_dir": str(MODELS_DIR),
    }

    print(f"CPU:      {meta['cpu']}")
    print(f"Platform: {meta['platform']}")
    print(f"Threads:  {threads}")
    print(f"Variants: {', '.join(variants)}")

    if args.dry_run:
        print("\n[dry-run] Would run:", "TPS" if args.tps or args.all else "",
              "PPL" if args.perplexity or args.all else "",
              "Quality" if args.quality or args.all else "")
        return

    # --- TPS ---
    if args.all or args.tps:
        tps_results = run_tps(variants, threads)
        print_tps_table(tps_results)
        # Strip raw stdout before saving to keep JSON readable
        for r in tps_results.values():
            r.pop("raw_stdout", None)
        save_results("x86_tps_results.json", tps_results, meta)

    # --- Perplexity ---
    if args.all or args.perplexity:
        ppl_results = run_perplexity(variants, threads)
        print_ppl_table(ppl_results)
        save_results("x86_perplexity_results.json", ppl_results, meta)

    # --- Quality ---
    if args.all or args.quality:
        run_quality(variants, threads, args.datasets)

    print(f"\nDone. Results written to {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
