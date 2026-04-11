#!/bin/bash
# ================================================================
# pixel_qwen_tps.sh — Qwen 2.5 1.5B TPS sweep on Pixel 6a via ADB
#
# Pushes Qwen models to device (if needed) then runs 7-variant
# TPS benchmark across 4 context lengths.
#
# Usage: bash scripts/pixel_qwen_tps.sh
#
# Prerequisites:
#   - Qwen models at local-models/qwen2_5_1_5b_gguf/ on Mac
#   - llama-completion binary at /data/local/tmp/ on device
#   - ~10 GB free storage on device (/data/local/tmp/)
#
# Output: results/pixel_qwen_tps_{timestamp}/qwen_{VARIANT}_ctx{CTX}.jsonl
# ================================================================

set -euo pipefail

DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
LOCAL_MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
MODEL_PREFIX="Qwen2.5-1.5B-Instruct"

VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CTX_SIZES=(256 512 1024 2048)
NUM_TRIALS=5
OUTPUT_TOKENS=64
PROMPT="The future of artificial intelligence is"

RESULTS_DIR="results/pixel_qwen_tps_$(date +%Y%m%d_%H%M%S)"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }

# ----------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------
log "===== Pixel 6a Qwen 2.5 1.5B TPS Sweep ====="

if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ ERROR: No Android device found."
    exit 1
fi
log "✅ Device connected"

if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "❌ ERROR: ${LLAMA_BIN} not found on device. Push llama-completion first."
    exit 1
fi

# ----------------------------------------------------------------
# Push models not yet on device
# ----------------------------------------------------------------
log ""
log "Checking Qwen models on device..."
for VARIANT in "${VARIANTS[@]}"; do
    MODEL_LOCAL="${LOCAL_MODELS_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    MODEL_DEVICE="${DEVICE_DIR}/Qwen2.5-1.5B-Instruct-${VARIANT}.gguf"

    if ! adb shell "ls ${MODEL_DEVICE} 2>/dev/null" | grep -q ".gguf"; then
        if [ -f "$MODEL_LOCAL" ]; then
            SIZE_MB=$(( $(wc -c < "$MODEL_LOCAL") / 1000000 ))
            log "  ⬆  Pushing $VARIANT (${SIZE_MB} MB)..."
            adb push "$MODEL_LOCAL" "$MODEL_DEVICE"
            log "  ✅ $VARIANT pushed"
        else
            log "  ⚠️  $VARIANT: not on device AND not in local-models/. Will skip."
        fi
    else
        log "  ✅ $VARIANT already on device"
    fi
done

# ----------------------------------------------------------------
# Main sweep
# ----------------------------------------------------------------
log ""
log "Starting TPS sweep — ${#VARIANTS[@]} variants × ${#CTX_SIZES[@]} contexts × ${NUM_TRIALS} trials"

TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_DEVICE="${DEVICE_DIR}/Qwen2.5-1.5B-Instruct-${VARIANT}.gguf"

    if ! adb shell "ls ${MODEL_DEVICE} 2>/dev/null" | grep -q ".gguf"; then
        log "⚠️  SKIP $VARIANT — not on device"
        continue
    fi

    log ""
    log "━━━━━━━━━━━━━━━━━━━━━━━━ $VARIANT ━━━━━━━━━━━━━━━━━━━━━━━━"

    for CTX in "${CTX_SIZES[@]}"; do
        OUTPUT_FILE="${RESULTS_DIR}/qwen_${VARIANT}_ctx${CTX}.jsonl"
        > "$OUTPUT_FILE"

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$((CURRENT_RUN + 1))
            ELAPSED=$(( $(date +%s) - START_S ))
            ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED ))

            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && echo '' | ${LLAMA_BIN} \
                -m ${MODEL_DEVICE} \
                -c ${CTX} \
                -n ${OUTPUT_TOKENS} \
                -p '${PROMPT}' \
                -t 4 2>&1" 2>/dev/null || echo "ERROR")

            DECODE_TPS=$(echo "$RAW" | grep -E "llama_perf_context_print:.*eval time" \
                | grep -v "prompt" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1)
            [ -z "$DECODE_TPS" ] && DECODE_TPS="0"

            PREFILL_TPS=$(echo "$RAW" | grep -E "prompt eval time" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1 || echo "0")
            [ -z "$PREFILL_TPS" ] && PREFILL_TPS="0"

            echo "{\"variant\":\"${VARIANT}\",\"context_length\":${CTX},\"trial\":${TRIAL},\"decode_tps\":${DECODE_TPS},\"prefill_tps\":${PREFILL_TPS},\"device\":\"Pixel6a\",\"model\":\"Qwen2.5-1.5B\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
                >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s] $VARIANT ctx=${CTX} t=${TRIAL} → ${DECODE_TPS} t/s"
        done
    done
done

# ----------------------------------------------------------------
# Summary table
# ----------------------------------------------------------------
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━ RESULTS SUMMARY ━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 - "$RESULTS_DIR" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

data = defaultdict(lambda: defaultdict(list))
for f in glob.glob(f"{sys.argv[1]}/*.jsonl"):
    for line in open(f):
        try:
            r = json.loads(line)
            if float(r.get("decode_tps", 0)) > 0:
                data[r["variant"]][r["context_length"]].append(float(r["decode_tps"]))
        except: pass

print(f"{'Variant':<10} {'ctx=256':>8} {'ctx=512':>8} {'ctx=1024':>9} {'ctx=2048':>9}")
print("-" * 46)
for v in ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]:
    if v not in data: continue
    row = f"{v:<10}"
    for ctx in [256, 512, 1024, 2048]:
        vals = data[v].get(ctx, [])
        avg = sum(vals)/len(vals) if vals else 0
        row += f" {avg:8.2f}"
    print(row)
PYEOF

log ""
log "===== Qwen TPS Sweep Complete — Results: $RESULTS_DIR ====="
