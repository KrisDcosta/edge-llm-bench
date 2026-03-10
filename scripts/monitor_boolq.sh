#!/bin/bash
# Monitor BoolQ re-run progress every 15 minutes and auto-update Pareto plot on completion

set -e
cd /Users/krisdcosta/291_EAI

RESULTS_FILE="results/quality_scores.json"
VARIANTS=("Q2_K" "Q3_K_M" "Q4_K_M" "Q6_K" "Q8_0" "F16")
CHECK_INTERVAL=900  # 15 minutes in seconds

echo "==================================================================="
echo "BoolQ Re-run Monitor (15-min intervals)"
echo "==================================================================="
echo "Results file: $RESULTS_FILE"
echo "Check interval: $((CHECK_INTERVAL / 60)) minutes"
echo ""
echo "Started at: $(date)"
echo "==================================================================="
echo ""

# Function to extract accuracy from JSON for a specific variant+tag
get_accuracy() {
    local variant=$1
    local tag=$2
    python3 << PYTHON
import json
import sys

try:
    with open('$RESULTS_FILE', 'r') as f:
        data = json.load(f)
    
    # Find the result for this variant and tag
    for result in data:
        if result.get('variant') == '$variant' and result.get('tag') == '$tag':
            acc = result.get('accuracy_pct')
            status = result.get('status', 'unknown')
            return f"{acc:.1f}% ({status})" if acc is not None else "RUNNING"
    
    return "NOT_STARTED"
except:
    return "ERROR"
PYTHON
}

# Function to check if all variants are done
all_done() {
    for variant in "${VARIANTS[@]}"; do
        acc=$(get_accuracy "$variant" "boolq")
        if [[ "$acc" == "RUNNING" ]] || [[ "$acc" == "NOT_STARTED" ]]; then
            return 1  # Not done
        fi
    done
    return 0  # All done
}

# Main monitoring loop
iteration=0
while true; do
    iteration=$((iteration + 1))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] Check #$iteration"
    echo ""
    
    # Show progress for each variant
    echo "Progress:"
    for variant in "${VARIANTS[@]}"; do
        acc=$(get_accuracy "$variant" "boolq")
        printf "  %-10s: %s\n" "$variant" "$acc"
    done
    echo ""
    
    # Check if all done
    if all_done; then
        echo "✓ ALL VARIANTS COMPLETE!"
        echo ""
        echo "Triggering Pareto plot update..."
        python3 analysis/generate_figures.py 2>&1 | grep -E "(fig|Pareto|error|Error)" || true
        echo ""
        echo "==================================================================="
        echo "✓ BoolQ re-run COMPLETE and Pareto plot updated!"
        echo "  Next step: Update report (report.tex) with new accuracy data"
        echo "  Then: recompile PDF with 'pdflatex report/report.tex'"
        echo "==================================================================="
        break
    fi
    
    # Wait for next check
    echo "Next check in $((CHECK_INTERVAL / 60)) minutes (Ctrl+C to stop)..."
    echo ""
    sleep $CHECK_INTERVAL
done
