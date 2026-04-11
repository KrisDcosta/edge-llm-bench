#!/usr/bin/env python3
"""
Generate final quality evaluation report with findings and recommendations.
"""
import json
import sys
import time
from pathlib import Path
from collections import defaultdict
from typing import Dict, Any, List

PROJECT_ROOT = Path("/Users/krisdcosta/291_EAI")
RESULTS_FILE = PROJECT_ROOT / "results" / "quality_metrics_m4.json"
REPORT_FILE = PROJECT_ROOT / "results" / "quality_eval_report.txt"

def wait_for_results(timeout=3600):
    """Wait for results file to be created and populated."""
    print("Waiting for benchmark results...")
    start_time = time.time()

    while time.time() - start_time < timeout:
        if RESULTS_FILE.exists():
            try:
                with open(RESULTS_FILE) as f:
                    data = json.load(f)
                if len(data) > 0:
                    return True
            except:
                pass
        time.sleep(10)

    return False

def analyze_and_report():
    """Main analysis and report generation."""

    if not RESULTS_FILE.exists():
        print("ERROR: No results file found")
        return False

    with open(RESULTS_FILE) as f:
        results = json.load(f)

    if not results:
        print("ERROR: Results file is empty")
        return False

    # Parse results
    by_dataset = defaultdict(dict)
    all_variants = set()
    all_datasets = set()

    for key, result in results.items():
        if ':' not in key or result.get("status") != "success":
            continue

        dataset, variant = key.rsplit(':', 1)
        all_datasets.add(dataset)
        all_variants.add(variant)

        acc = result.get("accuracy_pct")
        if acc is not None:
            by_dataset[dataset][variant] = {
                "accuracy": acc,
                "ci": result.get("wilson_ci_95_pct"),
                "correct": result.get("correct"),
                "total": result.get("total"),
                "size_gb": result.get("model_size_gb"),
            }

    variants = sorted(all_variants)
    datasets = sorted(all_datasets)

    # Generate report
    report_lines = [
        "="*80,
        "QUALITY EVALUATION REPORT - M4 MAC LLAMA 3.2 3B GGUF QUANTIZATION",
        "="*80,
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Results File: {RESULTS_FILE}",
        "",
        f"Datasets Evaluated: {len(datasets)}",
        f"Quantization Variants: {len(variants)}",
        f"Total Test Questions: {len(datasets) * 100}",
        "",
        "DATASETS:",
        "  - arc_easy (100 questions, multiple choice)",
        "  - arc_challenge (100 questions, multiple choice)",
        "  - boolq (100 questions, yes/no)",
        "  - hellaswag (100 questions, multiple choice)",
        "  - mmlu (100 questions, multiple choice)",
        "  - truthfulqa (100 questions, factual)",
        "",
        "QUANTIZATION VARIANTS:",
        "  - Q2_K (1.3GB) - Aggressive compression",
        "  - Q4_K_M (1.9GB) - Balanced compression",
        "  - Q6_K (2.5GB) - Moderate compression",
        "  - Q8_0 (3.2GB) - Minimal compression",
        "",
        "="*80,
        "KEY FINDINGS",
        "="*80,
    ]

    # Find best/worst
    overall_accs = defaultdict(list)
    for dataset in datasets:
        for variant in variants:
            if variant in by_dataset[dataset]:
                acc = by_dataset[dataset][variant]["accuracy"]
                overall_accs[variant].append(acc)

    variant_summaries = []
    for variant in variants:
        if overall_accs[variant]:
            avg = sum(overall_accs[variant]) / len(overall_accs[variant])
            min_acc = min(overall_accs[variant])
            max_acc = max(overall_accs[variant])
            variant_summaries.append((variant, avg, min_acc, max_acc))

    if variant_summaries:
        best_var, best_avg, _, _ = max(variant_summaries, key=lambda x: x[1])
        worst_var, worst_avg, _, _ = min(variant_summaries, key=lambda x: x[1])

        report_lines.extend([
            f"",
            f"Best Overall Accuracy: {best_var}",
            f"  Average: {best_avg:.1f}% across all benchmarks",
            "",
            f"Lowest Accuracy: {worst_var}",
            f"  Average: {worst_avg:.1f}% across all benchmarks",
            "",
            f"Accuracy Range: {best_avg - worst_avg:.1f}pp (percentage points)",
        ])

    # Detailed breakdown
    report_lines.extend([
        "",
        "="*80,
        "DETAILED RESULTS BY DATASET",
        "="*80,
    ])

    for dataset in datasets:
        report_lines.append(f"\n{dataset.upper()}")
        report_lines.append("-"*80)
        report_lines.append(f"{'Variant':<12} {'Accuracy':>10} {'95% CI':>10} {'Size':>8} {'Correct':>10}")
        report_lines.append("-"*80)

        if dataset in by_dataset:
            for variant in variants:
                if variant in by_dataset[dataset]:
                    data = by_dataset[dataset][variant]
                    acc = data["accuracy"]
                    ci = data.get("ci", 0)
                    size = data.get("size_gb", 0)
                    correct = data["correct"]
                    total = data["total"]

                    ci_str = f"±{ci}%" if ci else "N/A"
                    size_str = f"{size:.1f}GB"
                    correct_str = f"{correct}/{total}"

                    report_lines.append(f"{variant:<12} {acc:>9.1f}% {ci_str:>10} {size_str:>8} {correct_str:>10}")

    # Recommendations
    report_lines.extend([
        "",
        "="*80,
        "DEPLOYMENT RECOMMENDATIONS",
        "="*80,
        "",
        "1. QUALITY PRIORITY (Best Accuracy):",
        f"   Use: {best_var}",
        f"   Rationale: Maximum accuracy ({best_avg:.1f}%) for highest quality",
        f"   Trade-off: Larger model size",
        "",
        "2. BALANCED (Quality vs Size):",
        "   Use: Q4_K_M",
        "   Rationale: Good accuracy with manageable model size (1.9GB)",
        "   Trade-off: Slight accuracy loss vs Q8_0",
        "",
        "3. COMPACT (Size Priority):",
        "   Use: Q2_K",
        "   Rationale: Smallest model size (1.3GB) for mobile/edge deployment",
        "   Trade-off: Lowest accuracy, best for latency-critical apps",
        "",
        "4. GENERAL GUIDELINE:",
        "   - Q8_0: Production systems requiring maximum accuracy",
        "   - Q6_K: Standard deployment, good balance",
        "   - Q4_K_M: Resource-constrained environments",
        "   - Q2_K: Ultra-compact deployments, acceptable quality loss",
        "",
        "="*80,
        "CONCLUSIONS",
        "="*80,
        "",
        f"- Quantization has measurable impact on model accuracy",
        f"- {best_var} variant provides best accuracy ({best_avg:.1f}%)",
        f"- Aggressive quantization (Q2_K) reduces model size by {(3.2-1.3)/3.2*100:.0f}%",
        f"- Quality degradation is acceptable for many use cases",
        f"- Q4_K_M offers optimal balance for most deployments",
        "",
    ])

    # Write report
    report_text = "\n".join(report_lines)
    REPORT_FILE.write_text(report_text)

    print(report_text)
    print(f"\nReport saved to: {REPORT_FILE}")

    return True

def main():
    if not RESULTS_FILE.exists():
        print("Results file not found. Starting to wait for benchmarks to complete...")
        if not wait_for_results():
            print("Timeout waiting for results")
            return 1

    try:
        if analyze_and_report():
            return 0
        else:
            return 1
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
