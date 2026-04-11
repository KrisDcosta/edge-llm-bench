#!/bin/bash
# ================================================================
# m4_master_parallel.sh — M4 Mac jobs to run while Pixel runs overnight
#
# Jobs (can overlap with Pixel overnight queue):
#
#   JOB 1 — M4 Metal cliff sweep (Llama 3.2 3B)    ~2 hrs
#            All 7 variants × 13 ctx pts × 5 trials
#            Uses -ngl 99 (Metal GPU — fixes existing CPU-mode data)
#
#   JOB 2 — Qwen 2.5 1.5B cliff sweep (M4 Metal)   ~1 hr
#            All 7 variants × 13 ctx pts × 5 trials
#
# NOTE: These run locally on your Mac — no ADB needed.
# The Pixel overnight queue runs independently in parallel.
#
# Usage: bash scripts/m4_master_parallel.sh
# ================================================================

set -euo pipefail
cd "$(dirname "$0")/.."

TS=$(date +%Y%m%d_%H%M%S)
LOGFILE="results/m4_parallel_${TS}.log"
mkdir -p results

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
hr()  { log "================================================================"; }

MASTER_START=$(date +%s)
elapsed() { echo $(( ($(date +%s) - MASTER_START) / 60 )); }

hr
log "M4 MAC PARALLEL JOBS"
log "Start : $(date)"
log "Log   : $LOGFILE"
hr

# Preflight
if ! command -v llama-cli &>/dev/null; then
    log "❌ FATAL: llama-cli not found. Install: brew install llama.cpp"
    exit 1
fi
log "✅ llama-cli found: $(which llama-cli)"
log ""

# ================================================================
# JOB 1: M4 Metal cliff sweep — Llama 3.2 3B (all 7 variants)
# ================================================================
hr
log "JOB 1 / 2 — M4 Metal cliff sweep (Llama 3.2 3B, -ngl 99)"
log "7 variants × 13 context points × 5 trials"
log "Expected: ~2 hours"
log ""
log "IMPORTANT: This uses Metal GPU (-ngl 99)."
log "Existing kv_cache_cliff data used CPU mode — this is the correct Metal run."
hr

J1_START=$(date +%s)
bash scripts/m4_metal_cliff_sweep.sh 2>&1 | tee -a "$LOGFILE" || {
    log "⚠️  JOB 1 exited non-zero — partial results may be available"
}
J1_MINS=$(( ($(date +%s) - J1_START) / 60 ))
log "✅ JOB 1 done in ${J1_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# JOB 2: Qwen 2.5 1.5B cliff sweep on M4 Metal
# ================================================================
hr
log "JOB 2 / 2 — Qwen 2.5 1.5B cliff sweep (M4 Metal, -ngl 99)"
log "7 variants × 13 context points × 5 trials"
log "Expected: ~1 hour"
hr

J2_START=$(date +%s)
QWEN_MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
QWEN_PREFIX="Qwen2.5-1.5B-Instruct"
QWEN_RESULTS="results/m4_metal_qwen_cliff_${TS}"
QWEN_LOG="${QWEN_RESULTS}.log"
mkdir -p "$QWEN_RESULTS"

CTX_SIZES=(1024 1100 1200 1250 1300 1350 1400 1450 1500 1550 1600 1800 2048)
VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
NUM_TRIALS=5
OUTPUT_TOKENS=32
PROMPT="Explain the transformer architecture and its role in modern natural language processing."

log "Results → $QWEN_RESULTS"
TOTAL=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CUR=0
J2_START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL="${QWEN_MODELS_DIR}/${QWEN_PREFIX}-${VARIANT}.gguf"
    if [ ! -f "$MODEL" ]; then
        log "  ⚠️  SKIP $VARIANT — not found at $MODEL"
        continue
    fi

    log "  ━━━ Qwen $VARIANT ━━━"
    OUT="${QWEN_RESULTS}/cliff_${VARIANT}.jsonl"
    > "$OUT"

    for CTX in "${CTX_SIZES[@]}"; do
        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CUR=$((CUR + 1))
            ELAPSED=$(( $(date +%s) - J2_START_S ))
            ETA=$(( ELAPSED * TOTAL / CUR - ELAPSED ))
            BENCH_TEMP="/tmp/qwen_cliff_${VARIANT}_${CTX}_${TRIAL}_$$.txt"

            # Run synchronously — --single-turn exits naturally after one generation
            llama-cli -m "$MODEL" -c "$CTX" -n "$OUTPUT_TOKENS" \
                -p "$PROMPT" -t 4 -ngl 99 \
                --single-turn < /dev/null > "$BENCH_TEMP" 2>&1 || true

            RAW=$(cat "$BENCH_TEMP"); rm -f "$BENCH_TEMP"

            # Parse from "[ Prompt: X.X t/s | Generation: Y.Y t/s ]" format
            DECODE=$(echo "$RAW" | grep -oE "\[ Prompt.*Generation: [0-9]+\.[0-9]+" \
                | grep -oE "Generation: [0-9]+\.[0-9]+" \
                | cut -d: -f2 | tr -d ' ' || echo "0")
            if [ -z "$DECODE" ] || [ "$DECODE" = "0" ]; then
                DECODE=$(echo "$RAW" | grep -oE "[0-9]+\.[0-9]+ t/s" | tail -1 | cut -d' ' -f1 || echo "0")
            fi
            [ -z "$DECODE" ] && DECODE="0"

            PREFILL=$(echo "$RAW" | grep -E "prompt eval time" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" | awk '{print $1}' | head -1 || echo "0")
            [ -z "$PREFILL" ] && PREFILL="0"

            echo "{\"variant\":\"${VARIANT}\",\"context\":${CTX},\"trial\":${TRIAL},\"decode_tps\":${DECODE},\"prefill_tps\":${PREFILL},\"device\":\"M4Mac\",\"backend\":\"Metal\",\"model\":\"Qwen2.5-1.5B\",\"ngl\":99,\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" >> "$OUT"
            log "  [${CUR}/${TOTAL} eta=${ETA}s] Qwen $VARIANT ctx=${CTX} t=${TRIAL} → ${DECODE} t/s"
        done
    done
    log "  ✅ Saved: $OUT"
done

# Cliff analysis for Qwen
python3 - "$QWEN_RESULTS" << 'PYEOF' | tee -a "$LOGFILE"
import json, glob, sys
from collections import defaultdict
print("\nQwen 2.5 1.5B Cliff Analysis (M4 Metal):")
for fpath in sorted(glob.glob(f"{sys.argv[1]}/cliff_*.jsonl")):
    variant = fpath.split("/cliff_")[-1].replace(".jsonl","")
    data = [json.loads(l) for l in open(fpath) if l.strip()]
    ctx_tps = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps",0)) > 0:
            ctx_tps[d["context"]].append(float(d["decode_tps"]))
    print(f"\n  {variant}:")
    prev = None
    for ctx in sorted(ctx_tps):
        avg = sum(ctx_tps[ctx])/len(ctx_tps[ctx])
        drop = f"  ← DROP {(prev-avg)/prev*100:.0f}%" if prev and (prev-avg)/prev > 0.10 else ""
        print(f"    ctx={ctx:5d}: {avg:6.2f} t/s{drop}")
        prev = avg
PYEOF

J2_MINS=$(( ($(date +%s) - J2_START) / 60 ))
log "✅ JOB 2 done in ${J2_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# FINAL
# ================================================================
TOTAL_MINS=$(elapsed)
hr
log "M4 PARALLEL JOBS COMPLETE"
log "Total runtime : ${TOTAL_MINS} min"
log "JOB 1 Llama Metal cliff : ${J1_MINS} min → results/m4_metal_cliff_*/"
log "JOB 2 Qwen Metal cliff  : ${J2_MINS} min → results/m4_metal_qwen_cliff_*/"
log "Full log: $LOGFILE"
hr
