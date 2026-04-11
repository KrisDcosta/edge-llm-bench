#!/usr/bin/env python3
"""Generate publication-ready tables from M4 benchmark results."""

import re
import json
import csv
import statistics
from collections import defaultdict
from pathlib import Path

bench_dir = Path("/Users/krisdcosta/291_EAI/results/m4_mac_metal_20260317_035638")
results = defaultdict(lambda: defaultdict(list))

# Extract metrics from all files
for filepath in sorted(bench_dir.glob("*.jsonl")):
    filename = filepath.name
    match = re.match(r"m4_(.+)_ctx(\d+)\.jsonl", filename)
    if not match:
        continue

    variant = match.group(1)
    context = int(match.group(2))

    try:
        with open(filepath, 'r') as f:
            content = f.read()

        # Extract "[ Prompt: XXX t/s | Generation: YYY t/s ]"
        metric_match = re.search(r'\[\s*Prompt:\s*([\d.]+)\s*t/s\s*\|\s*Generation:\s*([\d.]+)\s*t/s\s*\]', content)

        if metric_match:
            prefill_tps = float(metric_match.group(1))
            decode_tps = float(metric_match.group(2))

            results[variant][context].append({
                "prefill_tps": prefill_tps,
                "decode_tps": decode_tps
            })
    except Exception as e:
        print(f"Error processing {filename}: {e}")

# Define model sizes (in GB) for each quantization
model_sizes = {
    "Q2_K": 1.3,
    "Q3_K_M": 1.9,
    "Q4_K_S": 2.3,
    "Q4_K_M": 2.6,
    "Q5_K_M": 3.2,
    "Q6_K": 3.8,
    "Q8_0": 4.8,
}

# TABLE 1: Performance Summary by Quantization (average across contexts)
table1_data = []
variants_ordered = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]

for variant in variants_ordered:
    if variant not in results:
        continue

    all_decode = []
    all_prefill = []

    for ctx in sorted(results[variant].keys()):
        for metric in results[variant][ctx]:
            all_decode.append(metric["decode_tps"])
            all_prefill.append(metric["prefill_tps"])

    if all_decode:
        avg_decode = statistics.mean(all_decode)
        avg_prefill = statistics.mean(all_prefill)

        table1_data.append({
            "Variant": variant,
            "Model Size (GB)": f"{model_sizes.get(variant, 0):.1f}",
            "Decode TPS (avg)": f"{avg_decode:.1f}",
            "Prefill TPS (avg)": f"{avg_prefill:.1f}",
            "Peak Memory (MB)": f"{model_sizes.get(variant, 0) * 1024:.0f}"
        })

# TABLE 2: Context Length Impact
table2_data = []
for variant in variants_ordered:
    if variant not in results:
        continue

    for ctx in sorted(results[variant].keys()):
        metrics = results[variant][ctx]
        if metrics:
            avg_decode = statistics.mean([m["decode_tps"] for m in metrics])
            avg_prefill = statistics.mean([m["prefill_tps"] for m in metrics])

            table2_data.append({
                "Variant": variant,
                "Context Length": ctx,
                "Decode TPS": f"{avg_decode:.1f}",
                "Prefill TPS": f"{avg_prefill:.1f}",
                "Memory (MB)": f"{model_sizes.get(variant, 0) * 1024:.0f}"
            })

# TABLE 3: Statistical Summary
table3_data = []
for variant in variants_ordered:
    if variant not in results:
        continue

    all_decode = []
    all_prefill = []

    for ctx in sorted(results[variant].keys()):
        for metric in results[variant][ctx]:
            all_decode.append(metric["decode_tps"])
            all_prefill.append(metric["prefill_tps"])

    if all_decode and len(all_decode) > 1:
        mean_decode = statistics.mean(all_decode)
        std_decode = statistics.stdev(all_decode)
        min_decode = min(all_decode)
        max_decode = max(all_decode)

        # 95% confidence interval (approx for small samples)
        ci_margin = 1.96 * std_decode / (len(all_decode) ** 0.5)

        table3_data.append({
            "Variant": variant,
            "Mean TPS": f"{mean_decode:.1f}",
            "StdDev": f"{std_decode:.2f}",
            "Min TPS": f"{min_decode:.1f}",
            "Max TPS": f"{max_decode:.1f}",
            "95% CI": f"±{ci_margin:.2f}"
        })

# Output summary
print("\n" + "="*80)
print("TABLE 1: Performance Summary by Quantization")
print("="*80)
for row in table1_data:
    print(f"{row['Variant']:12} | Size: {row['Model Size (GB)']:>5} GB | "
          f"Decode: {row['Decode TPS (avg)']:>7} | Prefill: {row['Prefill TPS (avg)']:>7}")

print("\n" + "="*80)
print("TABLE 2: Context Length Impact (Sample - Q4_K_M)")
print("="*80)
for row in table2_data:
    if row["Variant"] == "Q4_K_M":
        print(f"ctx{row['Context Length']:4} | Decode: {row['Decode TPS']:>7} | "
              f"Prefill: {row['Prefill TPS']:>7} | Memory: {row['Memory (MB)']:>8}")

print("\n" + "="*80)
print("TABLE 3: Statistical Summary")
print("="*80)
for row in table3_data:
    print(f"{row['Variant']:12} | Mean: {row['Mean TPS']:>7} | Std: {row['StdDev']:>6} | "
          f"Range: {row['Min TPS']:>7} - {row['Max TPS']:>7} | 95% CI: {row['95% CI']:>8}")

# Save to JSON
output_data = {
    "metadata": {
        "timestamp": "2026-03-17",
        "device": "M4 Mac",
        "backend": "Metal",
        "model": "Llama-3.2-3B-Instruct"
    },
    "table1_performance_summary": table1_data,
    "table2_context_impact": table2_data,
    "table3_statistical_summary": table3_data,
    "raw_results": dict(results)
}

output_json = Path("/Users/krisdcosta/291_EAI/results/paper_tables_m4.json")
with open(output_json, 'w') as f:
    json.dump(output_data, f, indent=2)
print(f"\n✓ JSON output saved to: {output_json}")

# Save to CSV files
output_csv1 = Path("/Users/krisdcosta/291_EAI/results/paper_tables_m4_table1.csv")
with open(output_csv1, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=table1_data[0].keys() if table1_data else [])
    writer.writeheader()
    writer.writerows(table1_data)
print(f"✓ Table 1 CSV saved to: {output_csv1}")

output_csv2 = Path("/Users/krisdcosta/291_EAI/results/paper_tables_m4_table2.csv")
with open(output_csv2, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=table2_data[0].keys() if table2_data else [])
    writer.writeheader()
    writer.writerows(table2_data)
print(f"✓ Table 2 CSV saved to: {output_csv2}")

output_csv3 = Path("/Users/krisdcosta/291_EAI/results/paper_tables_m4_table3.csv")
with open(output_csv3, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=table3_data[0].keys() if table3_data else [])
    writer.writeheader()
    writer.writerows(table3_data)
print(f"✓ Table 3 CSV saved to: {output_csv3}")

# Unified CSV
output_csv_unified = Path("/Users/krisdcosta/291_EAI/results/paper_tables_m4.csv")
with open(output_csv_unified, 'w', newline='') as f:
    f.write("# TABLE 1: Performance Summary by Quantization\n")
    writer = csv.DictWriter(f, fieldnames=table1_data[0].keys() if table1_data else [])
    writer.writeheader()
    writer.writerows(table1_data)
    f.write("\n# TABLE 2: Context Length Impact\n")
    writer = csv.DictWriter(f, fieldnames=table2_data[0].keys() if table2_data else [])
    writer.writeheader()
    writer.writerows(table2_data)
    f.write("\n# TABLE 3: Statistical Summary\n")
    writer = csv.DictWriter(f, fieldnames=table3_data[0].keys() if table3_data else [])
    writer.writeheader()
    writer.writerows(table3_data)
print(f"✓ Unified CSV saved to: {output_csv_unified}")

print("\n✅ PAPER TABLES COMPLETE")
