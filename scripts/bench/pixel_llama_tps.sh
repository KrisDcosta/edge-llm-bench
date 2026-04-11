#!/usr/bin/env bash
# ============================================================
# pixel_llama_tps.sh  —  Llama 3.2 3B baseline TPS sweep
#                         Pixel 6a · CPU (4 threads) · via ADB
#
# Measures decode and prefill throughput at 4 representative
# context lengths for all 7 K-quant variants.
# 10 trials per point → mean ± std for the paper's Table 1.
#
# Usage:
#   bash scripts/bench/pixel_llama_tps.sh              # all 7 variants
#   bash scripts/bench/pixel_llama_tps.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/pixel_llama_tps.sh --resume      # skip completed
#
# Output:  results/pixel_llama_tps_{ts}/tps_{VARIANT}.jsonl
# Runtime: ~2 h  (7 variants × 4 ctx × 10 trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CTX_SIZES=(256 512 1024 2048)
NUM_TRIALS=10
OUTPUT_TOKENS=64
THREADS=4
PROMPT="The future of artificial intelligence is"

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_llama_tps_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

RESUME=0
VARIANTS=()
for arg in "$@"; do
    case "$arg" in
        --resume) RESUME=1 ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=("${ALL_VARIANTS[@]}")

hr
log "Pixel 6a  —  Llama 3.2 3B Baseline TPS Sweep  (CPU, ${THREADS} threads)"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
log "Results  : ${RESULTS_DIR}"
hr

if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No Android device connected."; exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "✅ Device: ${DEVICE_ID}"

if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "❌ FATAL: ${LLAMA_BIN} not found on device."; exit 1
fi
log "✅ llama-completion found"

MISSING=0
for V in "${VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ❌ Missing on device: ${MODEL_PREFIX}-${V}.gguf"; MISSING=$((MISSING+1))
    fi
done
[ "$MISSING" -gt 0 ] && log "❌ FATAL: $MISSING model(s) missing from device." && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present"
log ""

EXPECTED_LINES=$(( ${#CTX_SIZES[@]} * NUM_TRIALS ))
TOTAL_RUNS=$(( ${#VARIANTS[@]} * EXPECTED_LINES ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/tps_${VARIANT}.jsonl"

    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        DONE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
        if [ "$DONE" -ge "$EXPECTED_LINES" ]; then
            log "  ⏩ SKIP $VARIANT — already complete (${DONE} rows)"
            CURRENT_RUN=$(( CURRENT_RUN + EXPECTED_LINES ))
            continue
        fi
    fi

    log ""
    log "━━━ ${VARIANT} ━━━"
    > "$OUTPUT_FILE"

    for CTX in "${CTX_SIZES[@]}"; do
        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$(( CURRENT_RUN + 1 ))
            ELAPSED=$(( $(date +%s) - START_S ))
            [ "$CURRENT_RUN" -gt 1 ] \
                && ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED )) \
                || ETA=0

            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
                echo '' | ${LLAMA_BIN} \
                -m ${MODEL_PATH} \
                -c ${CTX} \
                -n ${OUTPUT_TOKENS} \
                -p '${PROMPT}' \
                -t ${THREADS} 2>&1" 2>/dev/null || echo "ADB_ERROR")

            RAW_BYTES=${#RAW}

            PREFILL=$(printf '%s\n' "$RAW" \
                | grep -E "common_perf_print:.*prompt eval time" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1 || echo "0")
            DECODE=$(printf '%s\n' "$RAW" \
                | grep -E "common_perf_print:.*eval time" \
                | grep -v "prompt" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1 || echo "0")
            [ -z "$PREFILL" ] && PREFILL="0"
            [ -z "$DECODE"  ] && DECODE="0"

            [[ "$RAW" == "ADB_ERROR" ]] && log "  ⚠️  ADB error ctx=${CTX} t=${TRIAL}"

            printf '{"variant":"%s","context":%d,"trial":%d,"decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","model":"%s","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
                "$VARIANT" "$CTX" "$TRIAL" "$DECODE" "$PREFILL" "$RAW_BYTES" \
                "${MODEL_PREFIX}-${VARIANT}" "$THREADS" "$OUTPUT_TOKENS" \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  ctx=${CTX}  t=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
        done
    done

    log "  ✅ Saved ${OUTPUT_FILE}"
done

log ""
hr
log "TPS SUMMARY  —  Pixel 6a (CPU)  —  Llama 3.2 3B"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys, statistics
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
ctx_list    = [256, 512, 1024, 2048]

print(f"\n{'Variant':<10}  " + "  ".join(f"ctx={c:5d}" for c in ctx_list))
print("-" * (10 + 11 * len(ctx_list)))

for variant in requested:
    paths = glob.glob(f"{results_dir}/tps_{variant}.jsonl")
    if not paths:
        continue
    data   = [json.loads(l) for l in open(paths[0]) if l.strip()]
    ctx_d  = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps", 0)) > 0:
            ctx_d[d["context"]].append(float(d["decode_tps"]))

    row = f"{variant:<10}  "
    for c in ctx_list:
        vals = ctx_d.get(c, [])
        if vals:
            mu  = statistics.mean(vals)
            sd  = statistics.stdev(vals) if len(vals) > 1 else 0
            row += f"{mu:5.2f}±{sd:.2f}  "
        else:
            row += "   N/A    "
    print(row)
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
