#!/usr/bin/env bash
# ============================================================
# pixel_quality.sh  —  LLM quality benchmarks on Pixel 6a
#                       ARC-Challenge, HellaSwag, MMLU, BoolQ
#
# Runs quality_eval.py (existing script) for all 7 K-quant
# variants against 4 standard benchmark datasets.
# Results are appended to results/quality_scores.json.
#
# Usage:
#   bash scripts/bench/pixel_quality.sh              # all 4 benchmarks × 7 variants
#   bash scripts/bench/pixel_quality.sh arc_challenge  # single benchmark
#   bash scripts/bench/pixel_quality.sh --dry-run    # show commands, don't run
#
# Valid benchmark names: arc_challenge  arc_easy  hellaswag  mmlu  boolq  truthfulqa
#
# Prerequisites:
#   - Benchmark YAML files at data/*.yaml
#   - All GGUF model files at /data/local/tmp/ on device
#   - llama-completion at /data/local/tmp/llama-completion on device
#
# Output:  results/quality_scores.json  (cumulative across runs)
#          results/pixel_quality_{ts}.log
# Runtime: ~3-4 h  (4 benchmarks × 7 variants × 100 questions each)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
ALL_BENCHMARKS=(arc_challenge arc_easy hellaswag mmlu boolq truthfulqa)
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
DEVICE_DIR="/data/local/tmp"
MODEL_PREFIX="Llama-3.2-3B-Instruct"

TS=$(date +%Y%m%d_%H%M%S)
LOGFILE="results/pixel_quality_${TS}.log"
mkdir -p results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

DRY_RUN=0
BENCHMARKS=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        arc_challenge|arc_easy|hellaswag|mmlu|boolq|truthfulqa) BENCHMARKS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n  Valid: arc_challenge arc_easy hellaswag mmlu boolq truthfulqa --dry-run\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#BENCHMARKS[@]} -eq 0 ] && BENCHMARKS=("${ALL_BENCHMARKS[@]}")

hr
log "Pixel 6a  —  Quality Benchmarks"
log "Benchmarks : ${BENCHMARKS[*]}"
log "Variants   : ${ALL_VARIANTS[*]}"
log "Results    : results/quality_scores.json"
log "Log        : ${LOGFILE}"
[ "$DRY_RUN" -eq 1 ] && log "  *** DRY RUN — commands will be shown but not executed ***"
hr

# ── Preflight ────────────────────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No Android device connected."; exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "✅ Device: ${DEVICE_ID}"

# Check benchmark YAML files
MISSING_YAML=0
for B in "${BENCHMARKS[@]}"; do
    if [ ! -f "data/${B}_100.yaml" ]; then
        log "  ❌ Missing: data/${B}_100.yaml"
        MISSING_YAML=$((MISSING_YAML + 1))
    else
        Q_COUNT=$(grep -c "^- " "data/${B}_100.yaml" 2>/dev/null || echo "?")
        log "  ✅ data/${B}_100.yaml  (${Q_COUNT} questions)"
    fi
done
[ "$MISSING_YAML" -gt 0 ] && log "❌ FATAL: $MISSING_YAML YAML file(s) missing." && exit 1

# Check model files on device
MISSING_MODELS=0
for V in "${ALL_VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ❌ Missing on device: ${MODEL_PREFIX}-${V}.gguf"
        MISSING_MODELS=$((MISSING_MODELS + 1))
    fi
done
[ "$MISSING_MODELS" -gt 0 ] && log "❌ FATAL: $MISSING_MODELS model(s) missing from device." && exit 1
log "✅ All 7 model(s) present on device"
log ""

# ── Run benchmarks ───────────────────────────────────────────
START_S=$(date +%s)
TOTAL=$(( ${#BENCHMARKS[@]} * ${#ALL_VARIANTS[@]} ))
CURRENT=0

for BENCH in "${BENCHMARKS[@]}"; do
    YAML="data/${BENCH}_100.yaml"
    log ""
    log "━━━ ${BENCH} ━━━  (${YAML})"

    for V in "${ALL_VARIANTS[@]}"; do
        CURRENT=$(( CURRENT + 1 ))
        ELAPSED=$(( $(date +%s) - START_S ))
        [ "$CURRENT" -gt 1 ] \
            && ETA=$(( ELAPSED * TOTAL / CURRENT - ELAPSED )) \
            || ETA=0

        CMD="python3 scripts/quality_eval.py --dataset ${YAML} --tag ${BENCH} ${V}"
        log "  [${CURRENT}/${TOTAL} eta=${ETA}s]  ${BENCH}:${V}"

        if [ "$DRY_RUN" -eq 1 ]; then
            log "    DRY RUN: $CMD"
            continue
        fi

        if $CMD 2>&1 | while IFS= read -r line; do
            log "    $line"
        done; then
            log "  ✅ ${BENCH}:${V} done"
        else
            log "  ⚠️  ${BENCH}:${V} exited non-zero — partial result may be in quality_scores.json"
        fi
    done

    log "  ✅ ${BENCH} complete"
done

log ""
hr
log "QUALITY SUMMARY"
hr

python3 - "${BENCHMARKS[@]}" << 'PYEOF'
import json, sys
from pathlib import Path

benchmarks = sys.argv[1:]
if not benchmarks:
    benchmarks = ["arc_challenge","arc_easy","hellaswag","mmlu","boolq","truthfulqa"]

scores_file = Path("results/quality_scores.json")
if not scores_file.exists():
    print("  No results/quality_scores.json found — run quality_eval.py first")
    sys.exit(0)

data     = json.loads(scores_file.read_text())
variants = ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
avail_b  = [b for b in benchmarks if any(f"{b}:{v}" in data for v in variants)]

if not avail_b:
    print("  No matching results found for requested benchmarks.")
    sys.exit(0)

# Header
header = f"  {'Variant':<10}" + "".join(f"  {b[:12]:>12}" for b in avail_b)
print(header)
print("  " + "-" * (10 + 14 * len(avail_b)))

for v in variants:
    row = f"  {v:<10}"
    for b in avail_b:
        key = f"{b}:{v}"
        if key in data:
            acc = data[key].get("accuracy_pct", 0)
            n   = data[key].get("n_questions", "?")
            row += f"  {acc:10.1f}%"
        else:
            row += f"  {'N/A':>12}"
    print(row)
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  log: ${LOGFILE}"
hr
