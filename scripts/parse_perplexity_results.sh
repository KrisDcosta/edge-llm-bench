#!/usr/bin/env bash
# parse_perplexity_results.sh — Extract PPL values from device output files
# and update results/perplexity_scores.json on the host.
#
# Usage:
#   bash scripts/parse_perplexity_results.sh           # original variants
#   bash scripts/parse_perplexity_results.sh --imatrix # imatrix variants
#   bash scripts/parse_perplexity_results.sh --all     # both
#
# Notes:
#   - Uses grep -E (BusyBox-safe, not grep -P)
#   - Reads from /data/local/tmp/ppl_full_{VARIANT}[_imatrix].txt on device
#   - Updates results/perplexity_scores.json (merges, does not overwrite)
#   - Also creates results/perplexity_scores_imatrix.json for imatrix results

set -euo pipefail

DEVICE_DIR="/data/local/tmp"
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RESULTS_DIR="${PROJECT_ROOT}/results"
SCORES_FILE="${RESULTS_DIR}/perplexity_scores.json"
IMATRIX_SCORES_FILE="${RESULTS_DIR}/perplexity_scores_imatrix.json"
ALL_VARIANTS=("Q2_K" "Q3_K_M" "Q4_K_M" "Q6_K" "Q8_0")

ADB="${ADB:-$(which adb 2>/dev/null || echo "$HOME/Library/Android/sdk/platform-tools/adb")}"

# ---------------------------------------------------------------------------
# Parse args
# ---------------------------------------------------------------------------
DO_ORIGINAL=1
DO_IMATRIX=0

for arg in "$@"; do
    case "$arg" in
        --imatrix) DO_ORIGINAL=0; DO_IMATRIX=1 ;;
        --all)     DO_ORIGINAL=1; DO_IMATRIX=1 ;;
    esac
done

# ---------------------------------------------------------------------------
# Helper: extract PPL from device file
# ---------------------------------------------------------------------------
extract_ppl() {
    local output_file="$1"
    # BusyBox-safe: grep -E then awk to extract the number
    # "Final estimate: PPL = 9.7553 +/- 0.0612"
    local line
    line=$("$ADB" shell "grep -E 'Final estimate' ${output_file} 2>/dev/null" || true)
    if [ -z "$line" ]; then
        echo ""
        return
    fi
    # Extract just the PPL value using awk
    echo "$line" | awk -F'= ' '{print $2}' | awk '{print $1}'
}

# ---------------------------------------------------------------------------
# Helper: update JSON file with new PPL value
# ---------------------------------------------------------------------------
update_json() {
    local json_file="$1"
    local variant="$2"
    local ppl="$3"
    local suffix="$4"  # "" or "_imatrix"

    mkdir -p "$RESULTS_DIR"

    # Read existing JSON or start fresh
    if [ -f "$json_file" ]; then
        existing=$(cat "$json_file")
    else
        existing="{}"
    fi

    # Use Python for reliable JSON manipulation
    python3 - <<PYEOF
import json, sys

existing = json.loads('''${existing}''')
variant = "${variant}"
ppl = "${ppl}"
suffix = "${suffix}"

key = variant + suffix  # e.g. "Q4_K_M" or "Q4_K_M_imatrix"

if ppl and ppl != "":
    try:
        ppl_float = float(ppl.split()[0])  # handle "+/-" in same line
        existing[key] = {
            "perplexity": round(ppl_float, 4),
            "perplexity_status": "success",
            "corpus": "wikitext2_full",
            "tokens_approx": 285000,
        }
        print(f"  Updated {key}: PPL = {ppl_float:.4f}")
    except ValueError:
        print(f"  WARNING: Could not parse PPL value: {ppl!r}", file=sys.stderr)
else:
    print(f"  WARNING: No PPL found for {key}", file=sys.stderr)

with open("${json_file}", "w") as f:
    json.dump(existing, f, indent=2)
PYEOF
}

# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------
echo "=== Parsing perplexity results from device ==="
echo ""

if [ "$DO_ORIGINAL" -eq 1 ]; then
    echo "--- Original variants ---"
    for VARIANT in "${ALL_VARIANTS[@]}"; do
        OUTPUT_FILE="${DEVICE_DIR}/ppl_full_${VARIANT}.txt"
        printf "  %-10s ... " "$VARIANT"

        # Check file exists on device
        if ! "$ADB" shell "ls ${OUTPUT_FILE} 2>/dev/null" | grep -q ".txt"; then
            echo "SKIP (file not found: ${OUTPUT_FILE})"
            continue
        fi

        PPL=$(extract_ppl "$OUTPUT_FILE")
        if [ -z "$PPL" ]; then
            echo "MISSING (no 'Final estimate' in output)"
            # Show last few lines for debugging
            echo "    Last lines:"
            "$ADB" shell "tail -5 ${OUTPUT_FILE} 2>/dev/null" | sed 's/^/      /'
        else
            echo "PPL = $PPL"
            update_json "$SCORES_FILE" "$VARIANT" "$PPL" ""
        fi
    done
    echo ""
    echo "  Saved to: $SCORES_FILE"
fi

if [ "$DO_IMATRIX" -eq 1 ]; then
    echo ""
    echo "--- imatrix variants ---"
    for VARIANT in "${ALL_VARIANTS[@]}"; do
        OUTPUT_FILE="${DEVICE_DIR}/ppl_full_${VARIANT}-imatrix.txt"
        printf "  %-15s ... " "${VARIANT}-imatrix"

        if ! "$ADB" shell "ls ${OUTPUT_FILE} 2>/dev/null" | grep -q ".txt"; then
            echo "SKIP (file not found)"
            continue
        fi

        PPL=$(extract_ppl "$OUTPUT_FILE")
        if [ -z "$PPL" ]; then
            echo "MISSING"
        else
            echo "PPL = $PPL"
            update_json "$IMATRIX_SCORES_FILE" "$VARIANT" "$PPL" "_imatrix"
        fi
    done
    echo ""
    echo "  Saved to: $IMATRIX_SCORES_FILE"
fi

echo ""
echo "=== Done. Next steps ==="
echo "  python3 scripts/update_report_perplexity.py  # inject new PPL into report Table 1"
echo "  python3 analysis/generate_figures.py <jsonl>  # regenerate figures"
