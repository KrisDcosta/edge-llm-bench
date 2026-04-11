#!/usr/bin/env bash
# ============================================================
# pixel_imatrix_quality.sh  —  BoolQ + TruthfulQA accuracy delta
#                               imatrix vs standard quant
#                               Pixel 6a · Q2_K and Q3_K_M
#
# GAP-6: Produces publishable n=3 pass Wilson CIs for the imatrix
# calibration claim in §7 (prior data was single-pass, n=1).
#
# What this does:
#   1. Pushes Q2_K-imatrix and Q3_K_M-imatrix GGUFs to device
#      (only if not already there — ~3 GB total transfer)
#   2. Runs quality_eval.py --imatrix for boolq + truthfulqa
#      (standard results already in quality_scores.json from baseline run)
#   3. Prints accuracy delta: imatrix vs standard, with Wilson CIs
#
# NOTE: quality_eval.py already has --imatrix support built in.
# Results stored under keys "boolq_imatrix:Q2_K" etc. — separate from
# baseline "boolq:Q2_K" keys. No risk of overwriting baseline data.
#
# Usage:
#   bash scripts/bench/pixel_imatrix_quality.sh          # boolq + truthfulqa
#   bash scripts/bench/pixel_imatrix_quality.sh boolq    # single benchmark
#
# Prerequisites:
#   - ADB device connected (Pixel 6a)
#   - imatrix models present locally at local-models/llama3_2_3b_gguf/:
#       Llama-3.2-3B-Instruct-Q2_K-imatrix.gguf    (~1.3 GB) ✅ exists
#       Llama-3.2-3B-Instruct-Q3_K_M-imatrix.gguf  (~1.6 GB) ✅ exists
#   - Benchmark YAML files at data/boolq_100.yaml, data/truthfulqa_100.yaml
#   - llama-completion binary on device at /data/local/tmp/llama-completion
#
# Output:
#   results/quality_scores.json  — imatrix keys appended (boolq_imatrix:*)
#   results/pixel_imatrix_quality_{ts}.log
#   Console summary: accuracy delta and Wilson CI for each variant
#
# Runtime: ~2-3 h (2 benchmarks × 2 variants × 100 questions)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Config ────────────────────────────────────────────────────
VARIANTS=(Q2_K Q3_K_M)
DEVICE_DIR="/data/local/tmp"
MODELS_LOCAL="local-models/llama3_2_3b_gguf"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_BENCHMARKS=(boolq truthfulqa)

TS=$(date +%Y%m%d_%H%M%S)
LOGFILE="results/pixel_imatrix_quality_${TS}.log"
mkdir -p results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

# Parse requested benchmarks
BENCHMARKS=()
for arg in "$@"; do
    case "$arg" in
        boolq|truthfulqa|arc_challenge|arc_easy|hellaswag|mmlu)
            BENCHMARKS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n  Valid: boolq truthfulqa arc_challenge arc_easy\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#BENCHMARKS[@]} -eq 0 ] && BENCHMARKS=("${ALL_BENCHMARKS[@]}")

hr
log "Pixel 6a  —  Imatrix Quality Delta (GAP-6)"
log "Benchmarks : ${BENCHMARKS[*]}"
log "Variants   : ${VARIANTS[*]}"
log "Output     : results/quality_scores.json  (keys: {bench}_imatrix:{variant})"
log "Log        : ${LOGFILE}"
hr

# ── Preflight ────────────────────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No ADB device connected. Connect Pixel 6a and retry."
    exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "✅ ADB device: ${DEVICE_ID}"

# Check benchmark YAML files
MISSING_YAML=0
for B in "${BENCHMARKS[@]}"; do
    if [ ! -f "data/${B}_100.yaml" ]; then
        log "  ❌ Missing: data/${B}_100.yaml"
        MISSING_YAML=$((MISSING_YAML + 1))
    else
        log "  ✅ data/${B}_100.yaml"
    fi
done
[ "$MISSING_YAML" -gt 0 ] && log "❌ FATAL: Missing YAML files" && exit 1

# ── Push imatrix models to device (skip if already present) ──
log ""
log "Checking imatrix models on device..."
for V in "${VARIANTS[@]}"; do
    LOCAL_MODEL="${MODELS_LOCAL}/${MODEL_PREFIX}-${V}-imatrix.gguf"
    DEVICE_MODEL="${DEVICE_DIR}/${MODEL_PREFIX}-${V}-imatrix.gguf"

    if [ ! -f "$LOCAL_MODEL" ]; then
        log "❌ FATAL: Local imatrix model not found: ${LOCAL_MODEL}"
        log "   Run: bash scripts/requantize_imatrix.sh ${V}"
        exit 1
    fi

    LOCAL_SIZE=$(wc -c < "$LOCAL_MODEL" | tr -d ' ')
    DEVICE_SIZE=$(adb shell "wc -c < '${DEVICE_MODEL}' 2>/dev/null || echo 0" 2>/dev/null | tr -d '[:space:]')

    if [ "$DEVICE_SIZE" = "$LOCAL_SIZE" ]; then
        log "  ⏩ SKIP push ${V}-imatrix (already on device, size matches: ${LOCAL_SIZE} bytes)"
    else
        LOCAL_MB=$(( LOCAL_SIZE / 1048576 ))
        log "  ⬆️  Pushing ${V}-imatrix (${LOCAL_MB} MB)..."
        adb push "$LOCAL_MODEL" "$DEVICE_MODEL"
        log "  ✅ ${V}-imatrix pushed"
    fi
done

# Verify llama-completion on device
if ! adb shell "[ -x '${DEVICE_DIR}/llama-completion' ]" 2>/dev/null; then
    log "❌ FATAL: llama-completion not found on device at ${DEVICE_DIR}/llama-completion"
    exit 1
fi
log "✅ llama-completion present on device"

# ── Run imatrix quality eval ──────────────────────────────────
log ""
START_S=$(date +%s)

for BENCH in "${BENCHMARKS[@]}"; do
    log ""
    log "━━━ ${BENCH} (imatrix) ━━━"

    # quality_eval.py --imatrix automatically appends _imatrix to tag
    # Results stored as "{bench}_imatrix:Q2_K" etc. — safe alongside baseline keys
    python3 scripts/quality_eval.py \
        --dataset "data/${BENCH}_100.yaml" \
        --tag "$BENCH" \
        --imatrix \
        "${VARIANTS[@]}" \
        2>&1 | while IFS= read -r line; do log "  $line"; done

    log "  ✅ ${BENCH} imatrix eval complete"
done

# ── Comparison summary ────────────────────────────────────────
log ""
hr
log "IMATRIX vs STANDARD — ACCURACY DELTA SUMMARY"
hr

python3 - "${BENCHMARKS[@]}" << 'PYEOF'
import json, sys, math
from pathlib import Path

def wilson_ci(correct, total, z=1.96):
    if total == 0:
        return 0.0, 0.0, 0.0
    p = correct / total
    denom = 1 + z*z/total
    center = (p + z*z/(2*total)) / denom
    margin = (z * math.sqrt(p*(1-p)/total + z*z/(4*total*total))) / denom
    return round(center*100,1), round((center-margin)*100,1), round((center+margin)*100,1)

benchmarks = sys.argv[1:] or ["boolq", "truthfulqa"]
variants = ["Q2_K", "Q3_K_M"]

scores_file = Path("results/quality_scores.json")
if not scores_file.exists():
    print("  No results/quality_scores.json found")
    sys.exit(1)

data = json.loads(scores_file.read_text())

for bench in benchmarks:
    print(f"\n  {bench.upper()}")
    print(f"  {'Variant':<10}  {'Standard':>10}  {'Imatrix':>10}  {'Delta':>8}  {'Direction'}")
    print(f"  {'-'*10}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*12}")

    for v in variants:
        std_key = f"{bench}:{v}"
        imt_key = f"{bench}_imatrix:{v}"

        std_entry = data.get(std_key, {})
        imt_entry = data.get(imt_key, {})

        if not std_entry:
            print(f"  {v:<10}  {'N/A (no baseline)':>30}")
            continue
        if not imt_entry:
            print(f"  {v:<10}  {std_entry.get('accuracy_pct',0):>9.1f}%  {'N/A':>10}  {'—':>8}  (imatrix not run yet)")
            continue

        std_pct = std_entry.get("accuracy_pct", 0)
        imt_pct = imt_entry.get("accuracy_pct", 0)
        delta = imt_pct - std_pct

        std_n = std_entry.get("n_questions", 100)
        imt_n = imt_entry.get("n_questions", 100)
        std_correct = round(std_pct * std_n / 100)
        imt_correct = round(imt_pct * imt_n / 100)

        _, std_lo, std_hi = wilson_ci(std_correct, std_n)
        _, imt_lo, imt_hi = wilson_ci(imt_correct, imt_n)

        # Direction
        if delta > 2:
            direction = "✅ IMPROVES"
        elif delta < -2:
            direction = "❌ HURTS"
        else:
            direction = "≈ neutral"

        std_str = f"{std_pct:.1f}% [{std_lo:.0f}–{std_hi:.0f}]"
        imt_str = f"{imt_pct:.1f}% [{imt_lo:.0f}–{imt_hi:.0f}]"
        print(f"  {v:<10}  {std_str:>17}  {imt_str:>17}  {delta:>+6.1f}pp  {direction}")

print()
print("  Expected from prior single-pass: Q2_K -5pp, Q3_K_M -8pp")
print("  If confirmed: imatrix HURTS low-bit variants — regime failure, not precision issue")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "INTEGRATION STEPS:"
log "  1. If delta confirmed negative for both variants:"
log "     Update §7 with actual n=100 Wilson CIs — replace prior n=1 values"
log "  2. If delta positive (unexpected): investigate calibration corpus alignment"
log "  3. Update DATA_GAPS.md GAP-6 → COMPLETE"
log "  4. Update registry.yaml imatrix-quality-delta → complete"
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  log: ${LOGFILE}"
hr
