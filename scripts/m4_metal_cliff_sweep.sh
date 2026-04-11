#!/bin/bash
# ================================================================
# m4_metal_cliff_sweep.sh — Fine-grained KV-cache cliff sweep on M4 Mac
#
# Runs with -ngl 99 (Metal GPU backend) for all 7 Llama variants.
# Contrast with existing kv_cache_cliff_sweep.sh which runs CPU-only.
#
# NOTE: The existing kv_cache_cliff_20260320 data used NO -ngl flag
# (CPU mode). This script produces proper Metal GPU cliff data.
#
# Usage: bash scripts/m4_metal_cliff_sweep.sh [VARIANT ...]
#   bash scripts/m4_metal_cliff_sweep.sh              # all 7 variants
#   bash scripts/m4_metal_cliff_sweep.sh Q6_K Q3_K_M # specific
#
# Output: results/m4_metal_cliff_{timestamp}/cliff_{VARIANT}.jsonl
# ================================================================

set -euo pipefail

MODELS_DIR="local-models/llama3_2_3b_gguf"
MODEL_PREFIX="Llama-3.2-3B-Instruct"

CTX_SIZES=(1024 1100 1200 1250 1300 1350 1400 1450 1500 1550 1600 1800 2048)
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
NUM_TRIALS=5
OUTPUT_TOKENS=32
NGL=99   # offload all layers to Metal GPU
PROMPT="Explain the transformer architecture and its role in modern natural language processing."

RESULTS_DIR="results/m4_metal_cliff_$(date +%Y%m%d_%H%M%S)"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }

# Parse variant args
if [ $# -gt 0 ]; then
    VARIANTS=("$@")
else
    VARIANTS=("${ALL_VARIANTS[@]}")
fi

# Preflight
log "===== M4 Mac Metal KV-Cache Cliff Sweep ====="
log "Backend  : Metal GPU (-ngl ${NGL})"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS} per point"
log "Output   : $RESULTS_DIR"
log ""

if ! command -v llama-cli &>/dev/null; then
    log "❌ ERROR: llama-cli not found. Install: brew install llama.cpp"
    exit 1
fi

TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${MODELS_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"

    if [ ! -f "$MODEL_PATH" ]; then
        log "⚠️  SKIP $VARIANT — model not found at $MODEL_PATH"
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
            BENCH_TEMP="/tmp/m4cliff_${VARIANT}_${CTX}_${TRIAL}_$$.txt"

            # Run synchronously — --single-turn exits naturally after one generation
            llama-cli \
                -m "$MODEL_PATH" \
                -c "$CTX" \
                -n "$OUTPUT_TOKENS" \
                -p "$PROMPT" \
                -t 4 \
                -ngl "$NGL" \
                --single-turn < /dev/null > "$BENCH_TEMP" 2>&1 || true

            RAW=$(cat "$BENCH_TEMP")
            rm -f "$BENCH_TEMP"

            # Parse decode TPS from output
            # M4 llama-cli uses: "[ Prompt: X.X t/s | Generation: Y.Y t/s ]"
            DECODE_TPS=$(echo "$RAW" | grep -oE "\[ Prompt.*Generation: [0-9]+\.[0-9]+" \
                | grep -oE "Generation: [0-9]+\.[0-9]+" \
                | cut -d: -f2 | tr -d ' ' || echo "0")

            # Fallback: try the grep pattern for "t/s" anywhere
            if [ -z "$DECODE_TPS" ] || [ "$DECODE_TPS" = "0" ]; then
                DECODE_TPS=$(echo "$RAW" | grep -oE "[0-9]+\.[0-9]+ t/s" | tail -1 | cut -d' ' -f1 || echo "0")
            fi
            [ -z "$DECODE_TPS" ] && DECODE_TPS="0"

            PREFILL_TPS=$(echo "$RAW" | grep -E "prompt eval time" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1 || echo "0")
            [ -z "$PREFILL_TPS" ] && PREFILL_TPS="0"

            echo "{\"variant\":\"${VARIANT}\",\"context\":${CTX},\"trial\":${TRIAL},\"decode_tps\":${DECODE_TPS},\"prefill_tps\":${PREFILL_TPS},\"device\":\"M4Mac\",\"backend\":\"Metal\",\"ngl\":${NGL},\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" \
                >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s] $VARIANT ctx=${CTX} t=${TRIAL} → ${DECODE_TPS} t/s"
        done
    done

    log "  ✅ Saved: $OUTPUT_FILE"
done

# Cliff analysis
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
        print(f"  ctx={ctx:5d}: {avg:6.2f} t/s (n={len(ctx_tps[ctx])}){drop}")
        prev = avg
PYEOF

log ""
log "===== M4 Metal Cliff Sweep Complete — Results: $RESULTS_DIR ====="
