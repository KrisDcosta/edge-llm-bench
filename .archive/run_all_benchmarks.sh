#!/bin/bash
set -e

cd /Users/krisdcosta/291_EAI

echo "Starting quality evaluation benchmarks for all datasets..."
echo "Variants: Q2_K Q4_K_M Q6_K Q8_0"
echo ""

for ds in arc_easy arc_challenge boolq hellaswag mmlu truthfulqa; do
    echo "======================================"
    echo "Running $ds..."
    echo "======================================"
    python3 scripts/quality_eval_m4_local.py \
        --dataset "data/${ds}_100.yaml" \
        --tag "$ds" \
        Q2_K Q4_K_M Q6_K Q8_0 2>&1
    echo "$ds completed"
    echo ""
done

echo "======================================"
echo "All benchmarks completed!"
echo "Results saved to: results/quality_metrics_m4.json"
echo "======================================"
