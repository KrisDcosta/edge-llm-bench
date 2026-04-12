#!/bin/bash
# ================================================================
# pixel_cliff_sweep.sh — Fine-grained KV-cache cliff sweep on Pixel 6a
#
# Sweeps ctx 1024→2048 at 13 granular points to pinpoint the exact
# cliff threshold per variant. Runs via ADB.
#
# Usage: bash scripts/pixel_cliff_sweep.sh [VARIANT ...]
#   bash scripts/pixel_cliff_sweep.sh                   # all 5 variants
#   bash scripts/pixel_cliff_sweep.sh Q6_K Q3_K_M       # specific
#
# Output: results/pixel_cliff_sweep_{timestamp}/cliff_{VARIANT}.jsonl
# ================================================================

set -euo pipefail

DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"

# Fine-grained ctx sweep around the known cliff at ~1400–1550
CTX_SIZES=(1024 1100 1200 1250 1300 1350 1400 1450 1500 1550 1600 1800 2048)

# All 7 Llama variants
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

NUM_TRIALS=3
OUTPUT_TOKENS=32   # short output; we only need TPS, not content
TIMEOUT_S=300      # 5 min per trial (safe for ctx=2048 + slow variants)
PROMPT="Explain the transformer architecture and its role in modern natural language processing."

RESULTS_DIR="results/pixel_cliff_sweep_$(date +%Y%m%d_%H%M%S)"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }

# ----------------------------------------------------------------
# Parse variant args
# ----------------------------------------------------------------
if [ $# -gt 0 ]; then
    VARIANTS=("$@")
else
    VARIANTS=("${ALL_VARIANTS[@]}")
fi

# ----------------------------------------------------------------
# Preflight
# ----------------------------------------------------------------
log "===== Pixel KV-Cache Cliff Sweep ====="
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : $NUM_TRIALS per point"
log "Output   : $RESULTS_DIR"
log ""

if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ ERROR: No Android device found."
    exit 1
fi
log "✅ Device connected"

# Verify binary on device
if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "❌ ERROR: ${LLAMA_BIN} not found on device."
    exit 1
fi

# ----------------------------------------------------------------
# Main sweep
# ----------------------------------------------------------------
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"

    # Verify model on device
    if ! adb shell "ls ${MODEL_PATH} 2>/dev/null" | grep -q ".gguf"; then
        log "⚠️  SKIP $VARIANT — model not found on device at ${MODEL_PATH}"
        continue
    fi

    log ""
    log "━━━━━━━━━━━━━━━━━━━━━━━━ $VARIANT ━━━━━━━━━━━━━━━━━━━━━━━━"
    OUTPUT_FILE="${RESULTS_DIR}/cliff_${VARIANT}.jsonl"
    > "$OUTPUT_FILE"

    for CTX in "${CTX_SIZES[@]}"; do
        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$((CURRENT_RUN + 1))
            ELAPSED=$(( $(date +%s) - START_S ))
            ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED ))

            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && echo '' | ${LLAMA_BIN} \
                -m ${MODEL_PATH} \
                -c ${CTX} \
                -n ${OUTPUT_TOKENS} \
                -p '${PROMPT}' \
                -t 4 2>&1" 2>/dev/null || echo "ERROR")

            # Parse decode TPS from llama_perf_context_print eval time line
            DECODE_TPS=$(echo "$RAW" | grep -E "llama_perf_context_print:.*eval time" \
                | grep -v "prompt" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1)

            # Fallback: look for eval_tps in any "tokens per second" line after "eval time"
            if [ -z "$DECODE_TPS" ] || [ "$DECODE_TPS" = "0" ]; then
                DECODE_TPS=$(echo "$RAW" | grep -E "eval time" | grep -v "prompt" \
                    | grep -oE "[0-9]+\.[0-9]+" | tail -1 || echo "0")
            fi
            [ -z "$DECODE_TPS" ] && DECODE_TPS="0"

            PREFILL_TPS=$(echo "$RAW" | grep -E "prompt eval time" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1 || echo "0")
            [ -z "$PREFILL_TPS" ] && PREFILL_TPS="0"

            echo "{\"variant\":\"${VARIANT}\",\"context\":${CTX},\"trial\":${TRIAL},\"decode_tps\":${DECODE_TPS},\"prefill_tps\":${PREFILL_TPS},\"device\":\"Pixel6a\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
                >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s] $VARIANT ctx=${CTX} t=${TRIAL} → ${DECODE_TPS} t/s"
        done
    done

    log "  ✅ Saved: $OUTPUT_FILE"
done

# ----------------------------------------------------------------
# Cliff summary
# ----------------------------------------------------------------
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━ CLIFF ANALYSIS ━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 - "$RESULTS_DIR" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

for fpath in sorted(glob.glob(f"{sys.argv[1]}/cliff_*.jsonl")):
    variant = fpath.split("/cliff_")[-1].replace(".jsonl", "")
    data = [json.loads(l) for l in open(fpath) if l.strip()]
    ctx_tps = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps", 0)) > 0:
            ctx_tps[d["context"]].append(float(d["decode_tps"]))

    print(f"\n{variant}:")
    prev = None
    for ctx in sorted(ctx_tps):
        avg = sum(ctx_tps[ctx]) / len(ctx_tps[ctx])
        drop = f"  ← DROP {(prev-avg)/prev*100:.0f}%" if prev and (prev-avg)/prev > 0.10 else ""
        print(f"  ctx={ctx:5d}: {avg:5.2f} t/s (n={len(ctx_tps[ctx])}){drop}")
        prev = avg
PYEOF

log ""
log "===== Cliff Sweep Complete — Results: $RESULTS_DIR ====="
