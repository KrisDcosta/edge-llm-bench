#!/usr/bin/env python3
"""
Analyze quality evaluation results and generate summary statistics.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

PROJECT_ROOT = Path("/Users/krisdcosta/291_EAI")
RESULTS_FILE = PROJECT_ROOT / "results" / "quality_metrics_m4.json"

def load_results() -> Dict[str, Any]:
    """Load results from JSON file."""
    if not RESULTS_FILE.exists():
        print(f"ERROR: Results file not found at {RESULTS_FILE}")
        sys.exit(1)

    with open(RESULTS_FILE) as f:
        return json.load(f)

def analyze_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze results and extract summary statistics."""

    # Group by dataset and variant
    by_dataset = defaultdict(dict)
    by_variant = defaultdict(dict)

    for key, result in results.items():
        if ':' not in key:
            continue

        tag, variant = key.rsplit(':', 1)

        if result.get("status") != "success":
            continue

        accuracy = result.get("accuracy_pct")
        ci = result.get("wilson_ci_95_pct")
        model_size = result.get("model_size_gb", 0)
        correct = result.get("correct", 0)
        total = result.get("total", 0)

        by_dataset[tag][variant] = {
            "accuracy": accuracy,
            "ci": ci,
            "correct": correct,
            "total": total,
        }

        by_variant[variant][tag] = {
            "accuracy": accuracy,
            "ci": ci,
            "correct": correct,
            "total": total,
            "model_size_gb": model_size,
        }

    return {
        "by_dataset": dict(by_dataset),
        "by_variant": dict(by_variant),
        "datasets": sorted(by_dataset.keys()),
        "variants": sorted(by_variant.keys()),
    }

def print_summary(analysis: Dict[str, Any]) -> None:
    """Print comprehensive summary."""

    print("\n" + "="*80)
    print("QUALITY EVALUATION RESULTS SUMMARY - M4 MAC")
    print("="*80)

    by_dataset = analysis["by_dataset"]
    by_variant = analysis["by_variant"]
    datasets = analysis["datasets"]
    variants = analysis["variants"]

    # 1. Per-Dataset Summary
    print("\n1. ACCURACY BY DATASET AND VARIANT")
    print("-"*80)

    for dataset in datasets:
        print(f"\n{dataset.upper()}:")
        variant_accs = by_dataset.get(dataset, {})

        for variant in variants:
            data = variant_accs.get(variant, {})
            if data:
                acc = data.get("accuracy")
                ci = data.get("ci")
                correct = data.get("correct")
                total = data.get("total")
                ci_str = f" ± {ci}%" if ci else ""
                print(f"  {variant:<10}  {acc:>6.1f}%{ci_str:<10}  ({correct:>3}/{total:>3})")

    # 2. Per-Variant Summary
    print("\n" + "="*80)
    print("2. ACCURACY BY VARIANT (ACROSS ALL DATASETS)")
    print("-"*80)
    print(f"{'Variant':<10} {'Size (GB)':>10} {'Avg Acc':>10} {'Min':>8} {'Max':>8}")
    print("-"*80)

    variant_stats = {}
    for variant in variants:
        var_data = by_variant.get(variant, {})
        accs = [d.get("accuracy", 0) for d in var_data.values() if d.get("accuracy") is not None]

        if accs:
            avg_acc = sum(accs) / len(accs)
            min_acc = min(accs)
            max_acc = max(accs)
            model_size = var_data.get(list(var_data.keys())[0], {}).get("model_size_gb", 0)

            variant_stats[variant] = {
                "avg": avg_acc,
                "min": min_acc,
                "max": max_acc,
                "size": model_size,
                "accuracies": accs,
            }

            print(f"{variant:<10} {model_size:>10.1f} {avg_acc:>10.1f} {min_acc:>8.1f} {max_acc:>8.1f}")

    # 3. Accuracy Degradation Analysis
    print("\n" + "="*80)
    print("3. ACCURACY DEGRADATION vs QUANTIZATION")
    print("-"*80)

    # Compare against F16 (full precision reference)
    if 'Q8_0' in variant_stats:  # Q8_0 is closest to full precision
        ref_variant = 'Q8_0'
        ref_stats = variant_stats[ref_variant]

        print(f"Reference variant: {ref_variant} (Size: {ref_stats['size']:.1f}GB)")
        print(f"{'Variant':<10} {'Size (GB)':>10} {'Avg Acc':>10} {'Δ vs Ref':>12} {'Efficiency':>12}")
        print("-"*80)

        for variant in sorted(variants):
            stats = variant_stats.get(variant, {})
            if stats:
                size = stats["size"]
                avg = stats["avg"]
                delta = avg - ref_stats["avg"]
                efficiency = avg / size if size > 0 else 0  # Acc per GB
                delta_str = f"{delta:+.1f}pp" if delta else "ref"

                print(f"{variant:<10} {size:>10.1f} {avg:>10.1f} {delta_str:>12} {efficiency:>12.2f}")

    # 4. Best/Worst Variants per Benchmark
    print("\n" + "="*80)
    print("4. BEST & WORST PERFORMING VARIANTS PER BENCHMARK")
    print("-"*80)

    for dataset in datasets:
        variant_accs = by_dataset.get(dataset, {})
        accs_list = [(v, d.get("accuracy", 0)) for v, d in variant_accs.items()]

        if accs_list:
            best = max(accs_list, key=lambda x: x[1])
            worst = min(accs_list, key=lambda x: x[1])

            print(f"\n{dataset}:")
            print(f"  Best:  {best[0]:<10} {best[1]:.1f}%")
            print(f"  Worst: {worst[0]:<10} {worst[1]:.1f}%")
            if best[1] > 0 and worst[1] > 0:
                degradation = 100 * (1 - worst[1]/best[1])
                print(f"  Degradation: {degradation:.1f}%")

    # 5. Recommendations
    print("\n" + "="*80)
    print("5. DEPLOYMENT RECOMMENDATIONS")
    print("-"*80)

    best_overall = max(variant_stats.items(), key=lambda x: x[1]["avg"])
    best_compact = min(variant_stats.items(), key=lambda x: x[1]["size"])
    best_efficiency = max(variant_stats.items(), key=lambda x: x[1]["avg"]/x[1]["size"] if x[1]["size"] > 0 else 0)

    print(f"\nBest Accuracy: {best_overall[0]}")
    print(f"  Average accuracy: {best_overall[1]['avg']:.1f}%")
    print(f"  Model size: {best_overall[1]['size']:.1f}GB")

    print(f"\nMost Compact: {best_compact[0]}")
    print(f"  Model size: {best_compact[1]['size']:.1f}GB")
    print(f"  Average accuracy: {best_compact[1]['avg']:.1f}%")

    print(f"\nBest Efficiency (Acc/GB): {best_efficiency[0]}")
    efficiency_ratio = best_efficiency[1]["avg"] / best_efficiency[1]["size"] if best_efficiency[1]["size"] > 0 else 0
    print(f"  Efficiency: {efficiency_ratio:.2f}% per GB")
    print(f"  Model size: {best_efficiency[1]['size']:.1f}GB")

    print("\n" + "="*80)

def export_summary_json(analysis: Dict[str, Any]) -> None:
    """Export summary analysis to JSON."""

    summary = {
        "metadata": {
            "benchmarks": list(analysis["datasets"]),
            "variants": list(analysis["variants"]),
        },
        "by_dataset": analysis["by_dataset"],
        "by_variant": analysis["by_variant"],
    }

    summary_file = PROJECT_ROOT / "results" / "quality_summary.json"
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\nSummary JSON exported to: {summary_file}")

def main():
    if not RESULTS_FILE.exists():
        print(f"ERROR: Results file not found at {RESULTS_FILE}")
        print("\nPlease run the benchmarks first:")
        print(f"  python3 start_benchmarks.py")
        return 1

    try:
        results = load_results()
        analysis = analyze_results(results)

        if not analysis["datasets"]:
            print("ERROR: No valid results found in results file")
            return 1

        print_summary(analysis)
        export_summary_json(analysis)

        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
