#!/usr/bin/env python3
"""
Update the Pareto plot (fig6) with new BoolQ accuracy data instead of custom QA.

This script:
1. Reads BoolQ results from results/quality_scores.json
2. Reads decode throughput from benchmark results
3. Regenerates fig6_pareto_efficiency_quality.png with new accuracy data
4. Updates the report reference if needed
"""

import json
import sys
from pathlib import Path

def extract_boolq_accuracy():
    """Extract BoolQ accuracy for all variants from quality_scores.json"""
    results_file = Path("results/quality_scores.json")

    if not results_file.exists():
        print("ERROR: results/quality_scores.json not found")
        return None

    with open(results_file) as f:
        data = json.load(f)

    accuracy_by_variant = {}
    # data is a dict with keys like "boolq:Q2_K", "boolq:Q4_K_M", etc.
    for key in data:
        if key.startswith('boolq:'):
            entry = data[key]
            variant = entry.get('variant')
            acc = entry.get('accuracy_pct')
            if variant and acc is not None:
                accuracy_by_variant[variant] = acc

    if not accuracy_by_variant:
        print("ERROR: No BoolQ results found in quality_scores.json")
        return None

    print(f"✓ Found BoolQ accuracy for {len(accuracy_by_variant)} variants:")
    for variant, acc in sorted(accuracy_by_variant.items()):
        print(f"  {variant}: {acc:.1f}%")

    return accuracy_by_variant

def get_decode_tps():
    """Extract decode throughput from main benchmark results"""
    # Look for the latest comprehensive JSONL file
    results_dir = Path("results")
    jsonl_files = list(results_dir.glob("run-*.jsonl"))
    
    if not jsonl_files:
        print("ERROR: No JSONL benchmark files found in results/")
        return None
    
    # Use the most recent file
    latest_jsonl = max(jsonl_files, key=lambda p: p.stat().st_mtime)
    print(f"✓ Using benchmark file: {latest_jsonl.name}")
    
    # Aggregate decode TPS by variant (mean across trials)
    tps_by_variant = {}
    
    with open(latest_jsonl) as f:
        for line in f:
            record = json.loads(line)
            if record.get('status') != 'success':
                continue
            
            variant = record.get('model', {}).get('quant_bits')
            if variant is None:
                continue
            
            # Map bits to variant name
            bit_to_variant = {2: 'Q2_K', 3: 'Q3_K_M', 4: 'Q4_K_M', 6: 'Q6_K', 8: 'Q8_0', 16: 'F16'}
            variant_name = bit_to_variant.get(variant)
            
            if variant_name:
                decode_tps = record.get('metrics', {}).get('decode_tps')
                if decode_tps:
                    if variant_name not in tps_by_variant:
                        tps_by_variant[variant_name] = []
                    tps_by_variant[variant_name].append(decode_tps)
    
    # Compute means
    decode_tps_mean = {v: sum(tpss) / len(tpss) for v, tpss in tps_by_variant.items()}
    
    if not decode_tps_mean:
        print("ERROR: No decode TPS found in benchmark results")
        return None
    
    print(f"✓ Found decode TPS for {len(decode_tps_mean)} variants:")
    for variant in sorted(decode_tps_mean.keys()):
        print(f"  {variant}: {decode_tps_mean[variant]:.2f} tok/s")
    
    return decode_tps_mean

def regenerate_pareto_plot(accuracy_by_variant, decode_tps_mean):
    """Regenerate the Pareto plot with new data"""
    import matplotlib.pyplot as plt
    import numpy as np
    
    # Prepare data
    variants = sorted(set(list(accuracy_by_variant.keys()) + list(decode_tps_mean.keys())))
    accuracy = [accuracy_by_variant.get(v, 0) for v in variants]
    tps = [decode_tps_mean.get(v, 0) for v in variants]
    
    # Create figure
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Plot points
    colors = {'Q2_K': 'red', 'Q3_K_M': 'orange', 'Q4_K_M': 'green', 
              'Q6_K': 'purple', 'Q8_0': 'blue', 'F16': 'gray'}
    
    for variant, acc, t in zip(variants, accuracy, tps):
        color = colors.get(variant, 'black')
        ax.scatter(t, acc, s=200, c=color, alpha=0.7, edgecolors='black', linewidth=2, label=variant)
        ax.annotate(variant, (t, acc), xytext=(5, 5), textcoords='offset points', fontsize=9)
    
    # Highlight Pareto frontier
    pareto_indices = []
    for i in range(len(variants)):
        is_dominated = False
        for j in range(len(variants)):
            if i != j:
                # Point j dominates point i if j is better on both axes
                if tps[j] >= tps[i] and accuracy[j] >= accuracy[i]:
                    if tps[j] > tps[i] or accuracy[j] > accuracy[i]:
                        is_dominated = True
                        break
        if not is_dominated:
            pareto_indices.append(i)
    
    pareto_variants = [variants[i] for i in pareto_indices]
    print(f"\n✓ Pareto frontier: {pareto_variants}")
    
    # Labels and styling
    ax.set_xlabel('Decode Throughput (tokens/s)', fontsize=12)
    ax.set_ylabel('BoolQ Accuracy (%)', fontsize=12)
    ax.set_title('Efficiency-Accuracy Pareto Frontier (BoolQ 100-question eval)', fontsize=13)
    ax.grid(True, alpha=0.3)
    ax.set_ylim([0, 110])
    
    # Save
    output_path = Path("figures/fig6_pareto_efficiency_quality_UPDATED.png")
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    print(f"\n✓ Updated Pareto plot saved to: {output_path}")
    
    return output_path

def main():
    print("=" * 70)
    print("Updating Pareto Plot with BoolQ Accuracy Data")
    print("=" * 70)
    print()
    
    # Extract BoolQ accuracy
    accuracy = extract_boolq_accuracy()
    if not accuracy:
        sys.exit(1)
    print()
    
    # Extract decode TPS
    tps = get_decode_tps()
    if not tps:
        sys.exit(1)
    print()
    
    # Regenerate plot
    try:
        output_path = regenerate_pareto_plot(accuracy, tps)
        print()
        print("=" * 70)
        print("✓ SUCCESS: Pareto plot updated with BoolQ accuracy data")
        print("=" * 70)
        return 0
    except Exception as e:
        print(f"\nERROR during plot generation: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
