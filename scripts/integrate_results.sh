#!/bin/bash
#
# integrate_results.sh
#
# Comprehensive workflow to:
# 1. Pull results from device (if connected)
# 2. Parse new PPL and quality eval results
# 3. Generate figures
# 4. Compile report
#
# Usage:
#   ./scripts/integrate_results.sh                    # Full workflow
#   ./scripts/integrate_results.sh --skip-device      # Skip adb pull
#   ./scripts/integrate_results.sh --ppl-only         # Just PPL integration
#   ./scripts/integrate_results.sh --quality-only     # Just quality eval integration

set -e

PHASE="${1:---all}"
SKIP_DEVICE=false

# Parse arguments
for arg in "$@"; do
    case "$arg" in
        --skip-device) SKIP_DEVICE=true ;;
        --ppl-only) PHASE="ppl" ;;
        --quality-only) PHASE="quality" ;;
        --all) PHASE="all" ;;
    esac
done

echo "================================================"
echo "Results Integration Workflow"
echo "Phase: $PHASE | Skip Device Pull: $SKIP_DEVICE"
echo "================================================"

# Step 1: Pull from device (if connected and not skipped)
if [ "$SKIP_DEVICE" = "false" ]; then
    echo ""
    echo "Step 1: Pulling results from device..."
    if adb shell ls /data/local/tmp/ppl_full_*.txt > /dev/null 2>&1; then
        echo "  ✓ Device connected and results found"
        adb pull /data/local/tmp/ppl_full_*.txt results/
        adb pull /data/local/tmp/ppl_*_imatrix.txt results/ 2>/dev/null || true
        echo "  ✓ Results pulled from device"
    else
        echo "  ! Device not connected or no PPL files found"
        echo "  Continuing with local files..."
    fi
else
    echo "Step 1: Skipping device pull (--skip-device)"
fi

# Step 2: Parse and integrate PPL results
if [ "$PHASE" = "all" ] || [ "$PHASE" = "ppl" ]; then
    echo ""
    echo "Step 2: Parsing full-corpus PPL results..."
    if python3 scripts/parse_ppl_full.py results/; then
        echo "  ✓ PPL results integrated"
    else
        echo "  ! PPL integration failed (may need to check files manually)"
    fi
fi

# Step 3: Quality eval integration (checks for new quality_scores.json entries)
if [ "$PHASE" = "all" ] || [ "$PHASE" = "quality" ]; then
    echo ""
    echo "Step 3: Verifying quality eval results..."
    if [ -f "results/quality_scores.json" ]; then
        # Count entries
        num_entries=$(python3 -c "import json; d=json.load(open('results/quality_scores.json')); print(len(d))" 2>/dev/null || echo "?")
        echo "  ✓ Quality scores file found ($num_entries entries)"
    else
        echo "  ! Quality scores not yet created"
    fi
fi

# Step 4: Generate figures
if [ "$PHASE" = "all" ]; then
    echo ""
    echo "Step 4: Generating publication figures..."
    if python3 analysis/generate_figures.py results/ 2>&1 | head -20; then
        echo "  ✓ Figures generated in figures/"
    else
        echo "  ! Figure generation had issues (check output above)"
    fi
fi

# Step 5: Compile report
if [ "$PHASE" = "all" ]; then
    echo ""
    echo "Step 5: Compiling final report..."
    cd report
    if pdflatex -interaction=nonstopmode report.tex > /tmp/pdflatex1.log 2>&1; then
        if pdflatex -interaction=nonstopmode report.tex > /tmp/pdflatex2.log 2>&1; then
            echo "  ✓ Report compiled: report.pdf"
        else
            echo "  ! Second pdflatex pass failed (check report.pdf anyway)"
        fi
    else
        echo "  ! First pdflatex pass failed"
        tail -20 /tmp/pdflatex1.log
    fi
    cd ..
fi

# Summary
echo ""
echo "================================================"
echo "Results Integration Complete"
echo "================================================"
echo ""
echo "Next steps:"
echo "  1. Review figures in figures/"
echo "  2. Check results in results/perplexity_scores.json"
echo "  3. View final report at report/report.pdf"
echo ""
