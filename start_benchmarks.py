#!/usr/bin/env python3
"""Start all quality evaluation benchmarks in sequence."""
import subprocess
import sys
from pathlib import Path
import time

PROJECT_ROOT = Path("/Users/krisdcosta/291_EAI")
sys.path.insert(0, str(PROJECT_ROOT))

datasets = [
    ("arc_easy", "data/arc_easy_100.yaml"),
    ("arc_challenge", "data/arc_challenge_100.yaml"),
    ("boolq", "data/boolq_100.yaml"),
    ("hellaswag", "data/hellaswag_100.yaml"),
    ("mmlu", "data/mmlu_100.yaml"),
    ("truthfulqa", "data/truthfulqa_100.yaml"),
]
variants = ["Q2_K", "Q4_K_M", "Q6_K", "Q8_0"]

print("="*70)
print("QUALITY EVALUATION BENCHMARKS - M4 MAC")
print("="*70)
print(f"Datasets: {len(datasets)}")
print(f"Variants: {len(variants)} per dataset")
print(f"Total inferences: {len(datasets) * len(variants) * 100}")
print(f"Variants: {', '.join(variants)}")
print()
print("Starting benchmarks...")
print("="*70)

start_time = time.time()

for i, (dataset_name, dataset_path) in enumerate(datasets, 1):
    print(f"\n[{i}/{len(datasets)}] {dataset_name.upper()}")
    print("-" * 70)

    cmd = [
        sys.executable,
        str(PROJECT_ROOT / "scripts" / "quality_eval_m4_local.py"),
        "--dataset", str(PROJECT_ROOT / dataset_path),
        "--tag", dataset_name,
    ] + variants

    try:
        result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
        if result.returncode == 0:
            elapsed = time.time() - start_time
            print(f"✓ {dataset_name} completed (elapsed: {elapsed/60:.1f}m)")
        else:
            print(f"✗ {dataset_name} failed with exit code {result.returncode}")
    except KeyboardInterrupt:
        print("\nBenchmarks interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"✗ {dataset_name} failed: {e}")

elapsed_total = time.time() - start_time
print("\n" + "="*70)
print("BENCHMARKS COMPLETED")
print("="*70)
print(f"Total time: {elapsed_total/60:.1f} minutes ({elapsed_total/3600:.1f} hours)")
print(f"Results: {PROJECT_ROOT / 'results' / 'quality_metrics_m4.json'}")
