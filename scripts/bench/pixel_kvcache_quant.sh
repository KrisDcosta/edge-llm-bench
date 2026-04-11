#!/usr/bin/env bash
# ============================================================
# pixel_kvcache_quant.sh  —  KV-cache quantization test
#                             Pixel 6a · CPU (4 threads) · via ADB
#
# PURPOSE: Test whether Q8_0 KV-cache quantization (-ctk q8_0 -ctv q8_0)
# mitigates the Q2_K decode throughput cliff observed at ctx=768+.
#
# METHODOLOGY: Filled-context sweep identical to pixel_llama_cliff_filled.sh —
# prompt length = ctx - OUTPUT_TOKENS so the KV cache is fully populated.
# Compares Q2_K, Q3_K_M, Q4_K_M with and without KV quantization.
#
# CTX sweep : 256 512 768 1024 1200 1300 1400 1500 1600 1800 2048
# Trials    : 5 per (variant, ctx, kv_quant) combination
# Output    : 64 tokens
#
# JSONL fields: {variant, context, trial, kv_quant, decode_tps}
#
# Usage:
#   bash scripts/bench/pixel_kvcache_quant.sh
#   bash scripts/bench/pixel_kvcache_quant.sh Q2_K Q4_K_M  # subset
#
# Output:  results/pixel_kvcache_quant_{ts}/kvcache_{VARIANT}.jsonl
# Runtime: ~6-8 h  (3 variants × 11 ctx × 2 kv modes × 5 trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_M)
CTX_SIZES=(256 512 768 1024 1200 1300 1400 1500 1600 1800 2048)
NUM_TRIALS=5
OUTPUT_TOKENS=64
THREADS=4

# Seed paragraph for dynamic prompt generation.
# Llama tokenizer averages ~1.3 chars/token.
SEED_TEXT="The transformer architecture fundamentally changed natural language processing by introducing self-attention mechanisms that allow models to relate different positions of a sequence when computing a representation. Unlike recurrent networks, transformers process sequences in parallel and use positional encodings to maintain order information. Each transformer block consists of a multi-head attention layer followed by a feed-forward network, with layer normalization and residual connections enabling stable training of deep models. The key innovation is the attention mechanism itself: for each token, attention computes a weighted sum of all other token representations, where weights are determined by learned query and key projections. This allows long-range dependencies to be captured in a single layer. Modern large language models scale this architecture to billions of parameters across dozens of layers, using grouped-query attention and other efficiency improvements to reduce memory requirements during inference."

generate_prompt() {
    local target_tokens=$1
    local target_chars=$(( target_tokens * 13 / 10 ))
    local text=""
    while [ ${#text} -lt $target_chars ]; do
        text="${text} ${SEED_TEXT}"
    done
    echo "${text:0:$target_chars}"
}

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_kvcache_quant_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

VARIANTS=()
for arg in "$@"; do
    case "$arg" in
        Q2_K|Q3_K_M|Q4_K_M) VARIANTS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=("${ALL_VARIANTS[@]}")

hr
log "Pixel 6a  —  KV-Cache Quantization Test  (CPU, ${THREADS} threads)"
log "Methodology : filled_context — prompt length ~= ctx - ${OUTPUT_TOKENS} tokens"
log "Variants    : ${VARIANTS[*]}"
log "Contexts    : ${CTX_SIZES[*]}"
log "Trials      : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
log "KV modes    : default (f16)  and  q8_0 (-ctk q8_0 -ctv q8_0)"
log "Results     : ${RESULTS_DIR}"
hr

# ── Preflight: device ─────────────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "FATAL: No Android device connected. Connect USB and enable debugging."
    exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "Device: ${DEVICE_ID}"

# ── Preflight: binary ─────────────────────────────────────────
if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "FATAL: ${LLAMA_BIN} not found on device."
    exit 1
fi
log "llama-completion found on device"

# ── Preflight: models ─────────────────────────────────────────
MISSING=0
for V in "${VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  Missing on device: ${MODEL_PREFIX}-${V}.gguf"
        MISSING=$((MISSING + 1))
    fi
done
[ "$MISSING" -gt 0 ] && log "FATAL: $MISSING model(s) missing from device." && exit 1
log "All ${#VARIANTS[@]} model(s) present on device"
log ""

# ── Main sweep ────────────────────────────────────────────────
# KV modes: "default" = no extra flags; "q8_0" = -ctk q8_0 -ctv q8_0
KV_MODES=(default q8_0)
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * ${#KV_MODES[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/kvcache_${VARIANT}.jsonl"
    > "$OUTPUT_FILE"

    log ""
    log "=== ${VARIANT} ==="

    for KV_MODE in "${KV_MODES[@]}"; do
        if [ "$KV_MODE" = "q8_0" ]; then
            KV_FLAGS="-ctk q8_0 -ctv q8_0"
        else
            KV_FLAGS=""
        fi

        log "  --- kv_quant=${KV_MODE} ---"

        for CTX in "${CTX_SIZES[@]}"; do
            PROMPT_TOKENS=$(( CTX - OUTPUT_TOKENS ))
            PROMPT=$(generate_prompt "$PROMPT_TOKENS")

            for TRIAL in $(seq 1 $NUM_TRIALS); do
                CURRENT_RUN=$(( CURRENT_RUN + 1 ))
                ELAPSED=$(( $(date +%s) - START_S ))
                if [ "$CURRENT_RUN" -gt 1 ]; then
                    ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED ))
                else
                    ETA=0
                fi

                RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
                    echo '' | ${LLAMA_BIN} \
                    -m ${MODEL_PATH} \
                    -c ${CTX} \
                    -n ${OUTPUT_TOKENS} \
                    -t ${THREADS} \
                    ${KV_FLAGS} \
                    -p '${PROMPT}' 2>&1" 2>/dev/null || echo "ADB_ERROR")

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

                if [ "$RAW" = "ADB_ERROR" ]; then
                    log "  WARNING: ADB error  variant=${VARIANT} kv=${KV_MODE} ctx=${CTX} trial=${TRIAL}"
                fi
                if [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ]; then
                    log "  WARNING: Small output (${RAW_BYTES}B)  kv=${KV_MODE} ctx=${CTX} trial=${TRIAL}"
                fi

                printf '{"variant":"%s","context":%d,"prompt_tokens_approx":%d,"trial":%d,"kv_quant":"%s","decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","methodology":"filled_context","model":"%s","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
                    "$VARIANT" "$CTX" "$PROMPT_TOKENS" "$TRIAL" "$KV_MODE" \
                    "$DECODE" "$PREFILL" "$RAW_BYTES" \
                    "${MODEL_PREFIX}-${VARIANT}" "$THREADS" "$OUTPUT_TOKENS" \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

                log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  kv=${KV_MODE}  ctx=${CTX}  trial=${TRIAL}  decode=${DECODE} t/s"
            done
        done
    done

    log "  Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

log ""
hr
log "KV-CACHE QUANTIZATION ANALYSIS  —  Pixel 6a"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys, statistics
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:]
ctxs_all    = [256, 512, 768, 1024, 1200, 1300, 1400, 1500, 1600, 1800, 2048]

for variant in requested:
    paths = glob.glob(f"{results_dir}/kvcache_{variant}.jsonl")
    if not paths:
        continue
    data = [json.loads(l) for l in open(paths[0]) if l.strip()]

    # bucket by (kv_quant, context)
    by_kv_ctx = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps", 0)) > 0:
            by_kv_ctx[(d["kv_quant"], d["context"])].append(float(d["decode_tps"]))

    print(f"\n{'='*72}")
    print(f"  {variant}  [methodology: filled_context, KV quant comparison]")
    print(f"{'='*72}")
    print(f"  {'ctx':>6}  {'default':>12}  {'q8_0':>12}  {'delta':>10}")
    print(f"  {'-'*6}  {'-'*12}  {'-'*12}  {'-'*10}")

    for ctx in ctxs_all:
        d_vals = by_kv_ctx.get(("default", ctx), [])
        q_vals = by_kv_ctx.get(("q8_0",   ctx), [])
        d_str = f"{statistics.mean(d_vals):.2f}" if d_vals else "  N/A"
        q_str = f"{statistics.mean(q_vals):.2f}" if q_vals else "  N/A"
        if d_vals and q_vals:
            mu_d = statistics.mean(d_vals)
            mu_q = statistics.mean(q_vals)
            delta = (mu_q - mu_d) / mu_d * 100 if mu_d > 0 else 0.0
            cliff_note = ""
            # flag if q8_0 recovers >5% relative to default
            if delta > 5.0:
                cliff_note = "  <- MITIGATION"
            print(f"  {ctx:6d}  {d_str:>12}  {q_str:>12}  {delta:+9.1f}%{cliff_note}")
        else:
            print(f"  {ctx:6d}  {d_str:>12}  {q_str:>12}  {'N/A':>10}")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
