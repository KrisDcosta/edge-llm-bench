#!/bin/bash
# FIXED: BoolQ monitoring - corrected JSON parsing for dict-based structure

set -e
cd /Users/krisdcosta/291_EAI

RESULTS_FILE="results/quality_scores.json"
VARIANTS=("Q2_K" "Q3_K_M" "Q4_K_M" "Q6_K" "Q8_0" "F16")
CHECK_INTERVAL=900  # 15 minutes

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║           BoolQ Evaluation → Pareto Update Pipeline (FIXED)          ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""
echo "Started: $(date)"
echo ""

# Function to get accuracy for a variant (FIXED for dict-based JSON)
get_accuracy() {
    local variant=$1
    python3 << PYTHON 2>/dev/null || echo "ERROR"
import json
try:
    with open('$RESULTS_FILE', 'r') as f:
        data = json.load(f)
    
    # JSON is a dict with keys like "boolq:Q2_K"
    key = f"boolq:$variant"
    if key in data:
        acc = data[key].get('accuracy_pct')
        if acc is not None:
            print(f"{acc:.1f}")
        else:
            print("RUNNING")
    else:
        print("NOT_STARTED")
except:
    print("ERROR")
PYTHON
}

# Function to check if all variants are done
all_done() {
    for variant in "${VARIANTS[@]}"; do
        acc=$(get_accuracy "$variant")
        if [[ "$acc" == "RUNNING" ]] || [[ "$acc" == "NOT_STARTED" ]] || [[ "$acc" == "ERROR" ]]; then
            return 1
        fi
    done
    return 0
}

# Monitoring loop
iteration=0
while true; do
    iteration=$((iteration + 1))
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    
    clear
    echo "╔══════════════════════════════════════════════════════════════════════╗"
    echo "║ BoolQ Re-run Monitor [$TIMESTAMP]                           Check #$iteration"
    echo "╚══════════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Show progress
    echo "Variant Accuracy (BoolQ 100-question):"
    echo "────────────────────────────────────────"
    
    done_count=0
    for variant in "${VARIANTS[@]}"; do
        acc=$(get_accuracy "$variant")
        
        # Format output with progress indicator
        if [[ "$acc" == "RUNNING" ]]; then
            printf "  %-10s  [████░░░░] %-8s  🔄 IN PROGRESS\n" "$variant" "$acc"
        elif [[ "$acc" == "NOT_STARTED" ]]; then
            printf "  %-10s  [░░░░░░░░░] %-8s  ⏳ WAITING\n" "$variant" "$acc"
        elif [[ "$acc" == "ERROR" ]]; then
            printf "  %-10s  [████████░] %-8s  ⚠️  ERROR\n" "$variant" "$acc"
        else
            printf "  %-10s  [████████░] %-8s  ✓ DONE\n" "$variant" "$acc"
            done_count=$((done_count + 1))
        fi
    done
    
    echo ""
    echo "Progress: $done_count/${#VARIANTS[@]} variants complete"
    echo ""
    
    # Check if all done
    if all_done; then
        echo "═══════════════════════════════════════════════════════════════════════"
        echo "✓✓✓ ALL VARIANTS COMPLETE! ✓✓✓"
        echo "═══════════════════════════════════════════════════════════════════════"
        echo ""
        echo "Starting Pareto plot update..."
        echo ""
        
        # Run the Pareto update script
        if python3 scripts/update_pareto_with_boolq.py; then
            echo ""
            echo "═══════════════════════════════════════════════════════════════════════"
            echo "✓ PIPELINE COMPLETE"
            echo "═══════════════════════════════════════════════════════════════════════"
            echo ""
            echo "Next Steps:"
            echo "───────────"
            echo ""
            echo "1. Review the updated Pareto plot:"
            echo "   open figures/fig6_pareto_efficiency_quality_UPDATED.png"
            echo ""
            echo "2. Update the report (report/report.tex):"
            echo "   • Section RQ4: Replace custom QA accuracy with BoolQ results"
            echo "   • Update Table 1 with new accuracy %"
            echo "   • Update Figure 6 caption with BoolQ reference"
            echo ""
            echo "3. Recompile the PDF:"
            echo "   cd report && pdflatex report.tex && cd .."
            echo ""
            break
        else
            echo ""
            echo "✗ ERROR: Pareto plot update failed"
            break
        fi
    fi
    
    # Show next check time
    NEXT_CHECK=$((CHECK_INTERVAL / 60))
    echo "Next check: $(date -v+${NEXT_CHECK}M '+%H:%M:%S')"
    echo ""
    echo "Press Ctrl+C to stop monitoring"
    echo ""
    
    sleep $CHECK_INTERVAL
done
