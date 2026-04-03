#!/usr/bin/env bash
# ============================================================
# pixel_fa_mitigation.sh  —  Flash Attention probe + cliff sweep
#                             Pixel 6a · CPU (4 threads) · via ADB
#
# STEP 1 (probe): Runs a 1-token test with Q4_K_M and the -fa flag.
#   - If the binary exits cleanly and produces perf output  → FA supported
#   - If the output contains "error", "unsupported", or "unknown option"
#     (or the binary produces < 200 bytes of output)       → FA not supported
#
# STEP 2 (sweep): If FA is supported, runs the filled-context cliff sweep
# (ctx=256..2048, same methodology as pixel_llama_cliff_filled.sh) for
# Q2_K, Q3_K_M, Q4_K_M with -fa enabled.  5 trials per (variant, ctx).
#
# If FA is unsupported: logs the result and exits cleanly.
#
# JSONL fields: {variant, context, trial, fa_enabled, decode_tps}
#
# Usage:
#   bash scripts/bench/pixel_fa_mitigation.sh
#
# Output:  results/pixel_fa_mitigation_{ts}/fa_{VARIANT}.jsonl
# Runtime: ~4-5 h  (3 variants × 11 ctx × 5 trials) if FA supported
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
VARIANTS=(Q2_K Q3_K_M Q4_K_M)
PROBE_VARIANT="Q4_K_M"
CTX_SIZES=(256 512 768 1024 1200 1300 1400 1500 1600 1800 2048)
NUM_TRIALS=5
OUTPUT_TOKENS=64
THREADS=4
PROBE_CTX=256
PROBE_PROMPT="Hello"

# Seed paragraph for prompt generation (~1.3 chars/token)
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
RESULTS_DIR="results/pixel_fa_mitigation_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

hr
log "Pixel 6a  —  Flash Attention Mitigation Test  (CPU, ${THREADS} threads)"
log "Step 1    : probe -fa support with ${PROBE_VARIANT} at ctx=${PROBE_CTX}"
log "Step 2    : if supported, run filled-context cliff sweep with -fa"
log "Variants  : ${VARIANTS[*]}"
log "Contexts  : ${CTX_SIZES[*]}"
log "Trials    : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
log "Results   : ${RESULTS_DIR}"
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

# ── Preflight: probe model ────────────────────────────────────
PROBE_MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${PROBE_VARIANT}.gguf"
if ! adb shell "ls ${PROBE_MODEL_PATH} 2>/dev/null" | grep -q ".gguf"; then
    log "FATAL: Probe model ${MODEL_PREFIX}-${PROBE_VARIANT}.gguf not found on device."
    exit 1
fi
log "Probe model ${MODEL_PREFIX}-${PROBE_VARIANT}.gguf present"

# ── STEP 1: Flash Attention probe ────────────────────────────
log ""
log "--- STEP 1: probing -fa flag support ---"

PROBE_RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
    echo '' | ${LLAMA_BIN} \
    -m ${PROBE_MODEL_PATH} \
    -c ${PROBE_CTX} \
    -n 1 \
    -t ${THREADS} \
    -fa \
    -p '${PROBE_PROMPT}' 2>&1" 2>/dev/null || echo "ADB_ERROR")

FA_SUPPORTED=0
FA_REASON=""

if [ "$PROBE_RAW" = "ADB_ERROR" ]; then
    FA_REASON="ADB command failed during probe"
elif printf '%s\n' "$PROBE_RAW" | grep -qiE "unknown option|unrecognized|invalid option|error.*-fa|not supported|unsupported"; then
    FA_REASON="binary reported -fa as unknown/unsupported option"
elif [ ${#PROBE_RAW} -lt 200 ]; then
    FA_REASON="probe output too short (${#PROBE_RAW} bytes) — binary likely errored"
elif printf '%s\n' "$PROBE_RAW" | grep -qE "common_perf_print:.*eval time"; then
    FA_SUPPORTED=1
    FA_REASON="common_perf_print output detected — FA appears functional"
else
    FA_REASON="no perf output detected; assuming -fa not supported (output: ${#PROBE_RAW} bytes)"
fi

# Record probe result
printf '{"probe":"fa_support","fa_supported":%s,"reason":"%s","probe_variant":"%s","probe_ctx":%d,"raw_bytes":%d,"ts":"%s"}\n' \
    "$FA_SUPPORTED" "$FA_REASON" "$PROBE_VARIANT" "$PROBE_CTX" "${#PROBE_RAW}" \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "${RESULTS_DIR}/fa_probe.jsonl"

if [ "$FA_SUPPORTED" -eq 0 ]; then
    log ""
    log "Flash Attention NOT SUPPORTED: ${FA_REASON}"
    log ""
    log "The -fa flag is not functional on this binary build."
    log "This is a common outcome for CPU-only builds of llama.cpp;"
    log "Flash Attention typically requires GPU (CUDA/Metal) backends."
    log "Exiting cleanly — no sweep data to collect."
    log ""
    log "Probe result written to: ${RESULTS_DIR}/fa_probe.jsonl"
    hr
    log "DONE  |  FA not supported — sweep skipped  |  results: ${RESULTS_DIR}"
    hr
    exit 0
fi

log "Flash Attention SUPPORTED: ${FA_REASON}"
log "Proceeding to filled-context cliff sweep with -fa ..."
log ""

# ── Preflight: all sweep models ───────────────────────────────
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

# ── STEP 2: Filled-context cliff sweep with -fa ───────────────
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/fa_${VARIANT}.jsonl"
    > "$OUTPUT_FILE"

    log "=== ${VARIANT} ==="

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
                -fa \
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
                log "  WARNING: ADB error  variant=${VARIANT} ctx=${CTX} trial=${TRIAL}"
            fi
            if [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ]; then
                log "  WARNING: Small output (${RAW_BYTES}B)  ctx=${CTX} trial=${TRIAL}"
            fi

            printf '{"variant":"%s","context":%d,"prompt_tokens_approx":%d,"trial":%d,"fa_enabled":true,"decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","methodology":"filled_context","model":"%s","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
                "$VARIANT" "$CTX" "$PROMPT_TOKENS" "$TRIAL" \
                "$DECODE" "$PREFILL" "$RAW_BYTES" \
                "${MODEL_PREFIX}-${VARIANT}" "$THREADS" "$OUTPUT_TOKENS" \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  ctx=${CTX}  trial=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
        done
    done

    log "  Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
    log ""
done

log ""
hr
log "FLASH ATTENTION CLIFF ANALYSIS  —  Pixel 6a"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:]

for variant in requested:
    paths = glob.glob(f"{results_dir}/fa_{variant}.jsonl")
    if not paths:
        continue
    data = [json.loads(l) for l in open(paths[0]) if l.strip()]
    ctx_d = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps", 0)) > 0:
            ctx_d[d["context"]].append(float(d["decode_tps"]))

    valid = sum(len(v) for v in ctx_d.values())
    print(f"\n{'='*72}")
    print(f"  {variant}  ({valid}/{len(data)} valid)  [FA enabled, filled_context]")
    print(f"{'='*72}")

    baseline = None
    prev_avg = None
    for ctx in sorted(ctx_d):
        avg = sum(ctx_d[ctx]) / len(ctx_d[ctx])
        if baseline is None:
            baseline = avg
        pct_base = (avg - baseline) / baseline * 100 if baseline else 0
        step_note = ""
        if prev_avg is not None and prev_avg > 0 and (prev_avg - avg) / prev_avg > 0.10:
            step_note = f"  <- CLIFF {(prev_avg - avg) / prev_avg * 100:.0f}%"
        print(f"  ctx={ctx:5d}:  decode={avg:6.2f} t/s  ({pct_base:+.1f}% vs baseline)  (n={len(ctx_d[ctx])}){step_note}")
        prev_avg = avg
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
