#!/usr/bin/env python3
"""
run_q8_all_benchmarks.py
Run every x86 benchmark for Q8_0 and also patch in missing BoolQ for all variants.

Run this AFTER the cliff sweep finishes.

Usage:
    py -3 scripts/run_q8_all_benchmarks.py
    py -3 scripts/run_q8_all_benchmarks.py --skip-boolq   # Q8 only
    py -3 scripts/run_q8_all_benchmarks.py --threads 8
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT       = Path(__file__).parent.parent
SCRIPTS    = ROOT / "scripts"
MODELS_DIR = Path("C:/temp/llama3_2_3b_gguf")
Q8_MODEL   = MODELS_DIR / "Q8_0.gguf"
ALL_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]

DATA_DIR = ROOT / "data"

def run(cmd, label):
    print(f"\n{'='*64}")
    print(f"RUNNING: {label}")
    print(f"{'='*64}")
    rc = subprocess.call([sys.executable] + cmd)
    if rc != 0:
        print(f"WARNING: {label} exited with rc={rc}")
    return rc

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--threads",      type=int, default=6)
    p.add_argument("--skip-boolq",   action="store_true",
                   help="Skip BoolQ catchup for existing variants")
    p.add_argument("--skip-quality", action="store_true",
                   help="Skip all quality eval (TPS + PPL only)")
    return p.parse_args()

def main():
    args = parse_args()

    if not Q8_MODEL.exists():
        print(f"ERROR: Q8_0.gguf not found at {Q8_MODEL}")
        print("Run: py -3 scripts/download_q8.py")
        sys.exit(1)

    t = str(args.threads)

    # ------------------------------------------------------------------ #
    # 1. TPS for Q8_0
    # ------------------------------------------------------------------ #
    run([str(SCRIPTS / "run_x86_benchmark.py"),
         "--tps", "--variants", "Q8_0", "--threads", t],
        "TPS — Q8_0")

    # ------------------------------------------------------------------ #
    # 2. Perplexity for Q8_0
    # ------------------------------------------------------------------ #
    run([str(SCRIPTS / "run_x86_benchmark.py"),
         "--perplexity", "--variants", "Q8_0", "--threads", t],
        "Perplexity — Q8_0")

    if args.skip_quality:
        print("\nDone (--skip-quality set, skipping all quality eval).")
        return

    qe = str(SCRIPTS / "quality_eval.py")
    q8 = ["Q8_0"]
    all_v = ALL_VARIANTS

    # ------------------------------------------------------------------ #
    # 3. Quality eval — Q8_0 on all four datasets
    # ------------------------------------------------------------------ #
    for dataset, tag in [
        ("arc_easy_100.yaml",       "x86_arc_easy"),
        ("arc_challenge_100.yaml",  "x86_arc_challenge"),
        ("boolq_100.yaml",          "x86_boolq"),
        ("truthfulqa_100.yaml",     "x86_truthfulqa"),
    ]:
        path = DATA_DIR / dataset
        if not path.exists():
            print(f"SKIP {dataset} — file not found at {path}")
            continue
        run([qe, "--x86", "--dataset", str(path), "--tag", tag,
             "--threads", t] + q8,
            f"Quality {tag} — Q8_0")

    # ------------------------------------------------------------------ #
    # 4. BoolQ catchup for all other variants (was never run)
    # ------------------------------------------------------------------ #
    if not args.skip_boolq:
        boolq_path = DATA_DIR / "boolq_100.yaml"
        if boolq_path.exists():
            other_variants = [v for v in ALL_VARIANTS if v != "Q8_0"]
            run([qe, "--x86", "--dataset", str(boolq_path),
                 "--tag", "x86_boolq", "--threads", t] + other_variants,
                "Quality x86_boolq — all other variants (catchup)")
        else:
            print(f"\nSKIP BoolQ catchup — {boolq_path} not found")

    print("\nAll done. Results in results/")

if __name__ == "__main__":
    main()
