#!/usr/bin/env python3
"""
Run quality evaluation benchmarks for all datasets sequentially.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
datasets = [
    ("arc_easy", "data/arc_easy_100.yaml"),
    ("arc_challenge", "data/arc_challenge_100.yaml"),
    ("boolq", "data/boolq_100.yaml"),
    ("hellaswag", "data/hellaswag_100.yaml"),
    ("mmlu", "data/mmlu_100.yaml"),
    ("truthfulqa", "data/truthfulqa_100.yaml"),
]
variants = ["Q2_K", "Q4_K_M", "Q6_K", "Q8_0"]

def run_benchmark(dataset_name, dataset_path):
    """Run benchmark for a single dataset."""
    print(f"\n{'='*60}")
    print(f"Running {dataset_name}...")
    print(f"{'='*60}")

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "quality_eval_m4_local.py"),
        "--dataset", str(PROJECT_ROOT / dataset_path),
        "--tag", dataset_name,
    ] + variants

    try:
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True, text=True)
        print(f"{dataset_name} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: {dataset_name} failed with exit code {e.returncode}")
        return False
    except Exception as e:
        print(f"ERROR: {dataset_name} failed with exception: {e}")
        return False

def main():
    print("Starting quality evaluation benchmarks...")
    print(f"Datasets: {', '.join(d[0] for d in datasets)}")
    print(f"Variants: {', '.join(variants)}")

    results = {}
    for dataset_name, dataset_path in datasets:
        results[dataset_name] = run_benchmark(dataset_name, dataset_path)

    print(f"\n{'='*60}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*60}")
    for dataset_name, success in results.items():
        status = "✓ COMPLETED" if success else "✗ FAILED"
        print(f"{dataset_name:<20} {status}")

    results_file = PROJECT_ROOT / "results" / "quality_metrics_m4.json"
    if results_file.exists():
        print(f"\nResults saved to: {results_file}")
    else:
        print(f"\nWARNING: Results file not found at {results_file}")

    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    sys.exit(main())
