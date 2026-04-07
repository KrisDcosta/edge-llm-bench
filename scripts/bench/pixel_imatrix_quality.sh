#!/usr/bin/env bash
# ============================================================
# pixel_imatrix_quality.sh  —  BoolQ accuracy delta: imatrix vs standard quant
#                               Pixel 6a · Llama 3.2 3B · Q2_K and Q3_K_M
#
# GAP-6: measures accuracy improvement (or regression) from imatrix
# calibration at Q2_K and Q3_K_M. Existing single-pass data shows:
#   Q2_K:   imatrix hurts  (-5% BoolQ) — confirms HellaSwag collapse is
#           a regime failure, not a weight-precision problem
#   Q3_K_M: imatrix hurts  (-8% BoolQ)
#
# This script runs n >= 3 eval passes per (variant, imatrix_flag) to
# produce publishable Wilson CI values.
#
# PREREQUISITES:
#   1. On Pixel 6a device (ADB connected and authorized)
#   2. Standard quant models: Llama-3.2-3B-Instruct-{Q2_K,Q3_K_M}.gguf
#   3. Imatrix quant models: Llama-3.2-3B-Instruct-{Q2_K,Q3_K_M}-imatrix.gguf
#      (or equivalent — see notes on imatrix quantization below)
#   4. llama-completion on device at ${DEVICE_DIR}
#   5. BoolQ evaluation prompts (100 questions) at ${BOOLQ_PROMPTS}
#
# IMATRIX QUANTIZATION (run once on Mac/Linux):
#   llama-imatrix -m Llama-3.2-3B-Instruct.gguf \
#       -f calibration_data.txt --chunks 200 -o llama3_2_3b.imatrix
#   llama-quantize --imatrix llama3_2_3b.imatrix \
#       Llama-3.2-3B-Instruct.gguf Llama-3.2-3B-Instruct-Q2_K-imatrix.gguf Q2_K
#   llama-quantize --imatrix llama3_2_3b.imatrix \
#       Llama-3.2-3B-Instruct.gguf Llama-3.2-3B-Instruct-Q3_K_M-imatrix.gguf Q3_K_M
#
# Usage:
#   bash scripts/bench/pixel_imatrix_quality.sh              # both variants
#   bash scripts/bench/pixel_imatrix_quality.sh Q2_K         # single variant
#
# Output:  results/pixel_imatrix_quality_{ts}/
#   imatrix_{VARIANT}_standard.jsonl   — standard quant eval results
#   imatrix_{VARIANT}_imatrix.jsonl    — imatrix quant eval results
#   imatrix_delta_summary.txt          — accuracy delta and Wilson CIs
#
# Runtime: ~3-4 h (2 variants × 2 conditions × 3 passes × 100 BoolQ questions)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

DEVICE_DIR="/data/local/tmp/llama"
MODEL_DIR="${DEVICE_DIR}/models"
MODEL_PREFIX="Llama-3.2-3B-Instruct"

ALL_VARIANTS=(Q2_K Q3_K_M)
NUM_PASSES=3          # eval passes per condition; >= 3 for CI validity
BOOLQ_QUESTIONS=100   # number of BoolQ questions per pass

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_imatrix_quality_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

# Parse requested variants
VARIANTS=()
for arg in "$@"; do
    case "$arg" in
        Q2_K|Q3_K_M) VARIANTS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=("${ALL_VARIANTS[@]}")

hr
log "Pixel 6a — Imatrix Quality Delta — BoolQ  (n=${NUM_PASSES} passes)"
log "Variants : ${VARIANTS[*]}"
log "Questions: ${BOOLQ_QUESTIONS} BoolQ per pass per condition"
log "Results  : ${RESULTS_DIR}"
hr

# Verify ADB connection
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No ADB device connected. Connect Pixel 6a and retry."
    exit 1
fi
log "✅ ADB device connected"

# Verify standard models present
for V in "${VARIANTS[@]}"; do
    MODEL_FILE="${MODEL_DIR}/${MODEL_PREFIX}-${V}.gguf"
    IMATRIX_FILE="${MODEL_DIR}/${MODEL_PREFIX}-${V}-imatrix.gguf"

    adb shell "[ -f '${MODEL_FILE}' ]" 2>/dev/null || {
        log "❌ Missing standard model: ${V} at ${MODEL_FILE}"
        log "   Upload with: adb push local-models/llama3_2_3b_gguf/${MODEL_PREFIX}-${V}.gguf ${MODEL_DIR}/"
        exit 1
    }
    adb shell "[ -f '${IMATRIX_FILE}' ]" 2>/dev/null || {
        log "❌ Missing imatrix model: ${V}-imatrix at ${IMATRIX_FILE}"
        log "   Quantize with llama-quantize --imatrix then push to device"
        log "   See script header for full imatrix quantization commands"
        exit 1
    }
done
log "✅ All models present (standard + imatrix)"

# Python Wilson CI and delta analysis
ANALYSIS_SCRIPT=$(mktemp /tmp/imatrix_analysis.XXXXXX.py)
trap 'rm -f "$ANALYSIS_SCRIPT"' EXIT

cat > "$ANALYSIS_SCRIPT" << 'PYEOF'
import json, sys, math
from pathlib import Path

def wilson_ci(correct, total, z=1.96):
    if total == 0:
        return 0.0, (0.0, 0.0)
    p = correct / total
    denom = 1 + z*z/total
    center = (p + z*z/(2*total)) / denom
    margin = (z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))) / denom
    pct = round(center * 100, 1)
    lo = round((center - margin) * 100, 1)
    hi = round((center + margin) * 100, 1)
    return pct, (lo, hi)

results_dir = Path(sys.argv[1])
variants = sys.argv[2:]

print("\n" + "="*72)
print("IMATRIX QUALITY DELTA — BoolQ Accuracy")
print("="*72)

for variant in variants:
    std_file = results_dir / f"imatrix_{variant}_standard.jsonl"
    imt_file = results_dir / f"imatrix_{variant}_imatrix.jsonl"

    for label, fpath in [("Standard", std_file), ("Imatrix", imt_file)]:
        if not fpath.exists():
            print(f"\n{variant} {label}: FILE NOT FOUND")
            continue
        recs = [json.loads(l) for l in fpath.read_text().splitlines() if l.strip()]
        correct = sum(1 for r in recs if r.get('correct', False))
        total = len(recs)
        pct, ci = wilson_ci(correct, total)
        print(f"\n  {variant} {label:10s}: {correct}/{total} = {pct:.1f}%  95% CI [{ci[0]:.1f}--{ci[1]:.1f}]")

    # Delta
    if std_file.exists() and imt_file.exists():
        std_recs = [json.loads(l) for l in std_file.read_text().splitlines() if l.strip()]
        imt_recs = [json.loads(l) for l in imt_file.read_text().splitlines() if l.strip()]
        std_pct = sum(1 for r in std_recs if r.get('correct')) / len(std_recs) * 100 if std_recs else 0
        imt_pct = sum(1 for r in imt_recs if r.get('correct')) / len(imt_recs) * 100 if imt_recs else 0
        delta = imt_pct - std_pct
        direction = "✅ IMPROVES" if delta > 0 else ("❌ HURTS" if delta < -1 else "≈ NEUTRAL")
        print(f"\n  {variant} DELTA: {delta:+.1f}pp  ({direction})")
        if delta < -1:
            print(f"  Interpretation: Imatrix hurts {variant} — HellaSwag collapse is regime failure,")
            print(f"  not a weight-precision problem that calibration can fix.")

print("\n" + "="*72)
PYEOF

# ─── Run evaluations ─────────────────────────────────────────────────────────
# NOTE: This script structure shows the evaluation loop.
# The actual BoolQ prompting logic requires the eval pipeline from
# scripts/bench/pixel_quality.sh — adapt that approach here.
#
# For each (variant, condition), run NUM_PASSES passes of BOOLQ_QUESTIONS each,
# record correct/incorrect per question, save to JSONL.
#
# The loop below is a TEMPLATE — adapt ADB command to match your llama-completion
# invocation and BoolQ prompt format from pixel_quality.sh.

LLAMA_BIN="${DEVICE_DIR}/llama-completion"

for VARIANT in "${VARIANTS[@]}"; do
    for CONDITION in "standard" "imatrix"; do
        if [ "$CONDITION" = "standard" ]; then
            MODEL_FILE="${MODEL_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
        else
            MODEL_FILE="${MODEL_DIR}/${MODEL_PREFIX}-${VARIANT}-imatrix.gguf"
        fi

        OUTPUT_FILE="${RESULTS_DIR}/imatrix_${VARIANT}_${CONDITION}.jsonl"
        > "$OUTPUT_FILE"

        log ""
        log "━━━ ${VARIANT} (${CONDITION}) ━━━"
        log "Model: ${MODEL_FILE}"

        for PASS in $(seq 1 $NUM_PASSES); do
            log "  Pass ${PASS}/${NUM_PASSES}..."

            # ── BoolQ evaluation: pipe questions through llama-completion ──────
            # TODO: integrate with scripts/eval/boolq_eval.sh or pixel_quality.sh
            # Reference: scripts/bench/pixel_quality.sh — use same ADB + prompt approach
            #
            # For each BoolQ question:
            #   1. Format as "Passage: {passage}\nQuestion: {question}?\nAnswer (yes/no):"
            #   2. Run: adb shell "llama-completion -m MODEL -p PROMPT -n 1 --temp 0 ..."
            #   3. Parse Yes/No from output
            #   4. Compare to gold label
            #   5. Append JSON record: {variant, condition, pass, question_id, correct, ts}

            log "  ⚠️  BoolQ eval loop not yet integrated — see pixel_quality.sh for implementation"
            log "     Integrate eval loop here for GAP-6 completion"
            break  # Remove this break once eval loop is integrated
        done

        SAVED=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
        log "  Saved ${SAVED} records → ${OUTPUT_FILE}"
    done
done

log ""
hr
log "ANALYSIS"
hr

python3 "$ANALYSIS_SCRIPT" "$RESULTS_DIR" "${VARIANTS[@]}"

log ""
log "INTEGRATION STEPS:"
log "  1. Verify delta direction: prior data shows Q2_K -5pp, Q3_K_M -8pp"
log "  2. If confirmed negative delta: strengthens HellaSwag regime-failure explanation"
log "  3. Update §7 imatrix subsection with n>=3 Wilson CIs"
log "  4. Update DATA_GAPS.md GAP-6 → COMPLETE"
log "  5. Update registry.yaml imatrix-quality entry → complete"

ELAPSED=$(( $(date +%s) - SECONDS ))
log ""
hr
log "DONE  |  results: ${RESULTS_DIR}"
hr
