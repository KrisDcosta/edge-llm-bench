#!/usr/bin/env bash
# ============================================================
# pixel_threads_q4km.sh  —  Q4_K_M thread scaling benchmark
#                            Pixel 6a · CPU · via ADB
#
# METHODOLOGY: Measures decode throughput at ctx=256 (filled context)
# across threads=1,2,4,8 to characterize P-core vs LITTLE-core behavior
# and establish single-threaded vs multi-threaded baseline for mechanistic
# analysis (NEON dequant overhead, L2 cache effects).
#
# FILLED CONTEXT: prompt length = 256 - 64 = 192 tokens so the KV cache
# is populated at decode time. 64 output tokens measured for decode TPS.
#
# Usage:
#   bash scripts/bench/pixel_threads_q4km.sh                    # all 4 thread counts
#   bash scripts/bench/pixel_threads_q4km.sh --resume            # skip completed
#
# Output:  results/pixel_threads_q4km_{ts}/threads_{1,2,4,8}.jsonl
# Runtime: ~2.25 h  (4 thread counts × 15 trials × ~2 min/run)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
VARIANT="Q4_K_M"
CTX=256
THREAD_COUNTS=(1 2 4 8)
NUM_TRIALS=15
OUTPUT_TOKENS=64

# Seed paragraph for dynamic prompt generation.
SEED_TEXT="The transformer architecture fundamentally changed natural language processing by introducing self-attention mechanisms that allow models to relate different positions of a sequence when computing a representation. Unlike recurrent networks, transformers process sequences in parallel and use positional encodings to maintain order information. Each transformer block consists of a multi-head attention layer followed by a feed-forward network, with layer normalization and residual connections enabling stable training of deep models. The key innovation is the attention mechanism itself: for each token, attention computes a weighted sum of all other token representations, where weights are determined by learned query and key projections. This allows long-range dependencies to be captured in a single layer. Modern large language models scale this architecture to billions of parameters across dozens of layers, using grouped-query attention and other efficiency improvements to reduce memory requirements during inference."

# generate_prompt TARGET_TOKENS
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
RESULTS_DIR="results/pixel_threads_q4km_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

RESUME=0
i=1
while [ $i -le $# ]; do
    arg="${!i}"
    case "$arg" in
        --resume) RESUME=1 ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
    i=$(( i + 1 ))
done

hr
log "Pixel 6a  —  ${VARIANT} Thread Scaling (CPU, ctx=${CTX})"
log "Methodology : filled_context — prompt length = ${CTX} - ${OUTPUT_TOKENS} = $(( CTX - OUTPUT_TOKENS )) tokens"
log "Variant     : ${VARIANT}"
log "Context     : ${CTX}"
log "Thread counts: ${THREAD_COUNTS[*]}"
log "Trials      : ${NUM_TRIALS} per thread count  |  Output tokens: ${OUTPUT_TOKENS}"
log "Results     : ${RESULTS_DIR}"
hr

# ── Preflight: device + binary ────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No Android device connected. Connect USB and enable debugging."; exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "✅ Device: ${DEVICE_ID}"

if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "❌ FATAL: ${LLAMA_BIN} not found on device."; exit 1
fi
log "✅ llama-completion found on device"

# ── Model check ───────────────────────────────────────────────
MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
if ! adb shell "ls ${MODEL_PATH} 2>/dev/null" | grep -q ".gguf"; then
    log "❌ FATAL: ${MODEL_PATH} not found on device."; exit 1
fi
log "✅ ${VARIANT} model present on device"
log ""

# ── Prompt generation ──────────────────────────────────────────
PROMPT_TOKENS=$(( CTX - OUTPUT_TOKENS ))
PROMPT=$(generate_prompt "$PROMPT_TOKENS")
PROMPT_CHARS=${#PROMPT}
log "Generated prompt: ${PROMPT_CHARS} chars ≈ ${PROMPT_TOKENS} tokens"
log ""

# ── Main sweep: threads ────────────────────────────────────────
EXPECTED_LINES=$(( NUM_TRIALS ))
TOTAL_RUNS=$(( ${#THREAD_COUNTS[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for THREADS in "${THREAD_COUNTS[@]}"; do
    OUTPUT_FILE="${RESULTS_DIR}/threads_${THREADS}.jsonl"

    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        DONE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
        if [ "$DONE" -ge "$EXPECTED_LINES" ]; then
            log "  ⏩ SKIP threads=${THREADS} — already complete (${DONE} rows)"
            CURRENT_RUN=$(( CURRENT_RUN + EXPECTED_LINES ))
            continue
        fi
        log "  ↩  RESUME threads=${THREADS} — ${DONE}/${EXPECTED_LINES} done; re-running"
    fi

    log ""
    log "━━━ threads=${THREADS} ━━━"
    > "$OUTPUT_FILE"

    for TRIAL in $(seq 1 $NUM_TRIALS); do
        CURRENT_RUN=$(( CURRENT_RUN + 1 ))
        ELAPSED=$(( $(date +%s) - START_S ))
        [ "$CURRENT_RUN" -gt 1 ] \
            && ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED )) \
            || ETA=0

        # Run via ADB
        RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
            echo '' | ${LLAMA_BIN} \
            -m ${MODEL_PATH} \
            -c ${CTX} \
            -n ${OUTPUT_TOKENS} \
            -t ${THREADS} \
            -p '${PROMPT}' 2>&1" 2>/dev/null || echo "ADB_ERROR")

        RAW_BYTES=${#RAW}

        # Parse from "common_perf_print:" lines
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

        # Warn on error or tiny output
        [[ "$RAW" == "ADB_ERROR" ]] && \
            log "  ⚠️  ADB error  t=${TRIAL}"
        [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ] && \
            log "  ⚠️  Small output (${RAW_BYTES}B)  t=${TRIAL} — binary may have failed"

        printf '{"variant":"%s","context":%d,"prompt_tokens_approx":%d,"threads":%d,"trial":%d,"decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","methodology":"filled_context","model":"%s","n_output_tokens":%d,"ts":"%s"}\n' \
            "$VARIANT" "$CTX" "$PROMPT_TOKENS" "$THREADS" "$TRIAL" "$DECODE" "$PREFILL" "$RAW_BYTES" \
            "${MODEL_PREFIX}-${VARIANT}" "$OUTPUT_TOKENS" \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

        log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  threads=${THREADS}  t=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
    done

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

log ""
hr
log "THREAD SCALING ANALYSIS  —  ${VARIANT} @ ctx=${CTX}  (Pixel 6a CPU)"
hr

python3 - "$RESULTS_DIR" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

results_dir = sys.argv[1]

# Read all thread count files
threads_data = {}
for threads in [1, 2, 4, 8]:
    paths = glob.glob(f"{results_dir}/threads_{threads}.jsonl")
    if not paths:
        continue
    data = [json.loads(l) for l in open(paths[0]) if l.strip()]
    decode_tps = [float(d.get("decode_tps", 0)) for d in data if float(d.get("decode_tps", 0)) > 0]
    if decode_tps:
        threads_data[threads] = decode_tps

variant = "Q4_K_M"
print(f"\n{'='*72}")
print(f"  {variant}  Thread Scaling (ctx=256, filled context)")
print(f"{'='*72}\n")

# Print stats for each thread count
baseline_tps = None
for threads in sorted(threads_data.keys()):
    tps_list = threads_data[threads]
    mean = sum(tps_list) / len(tps_list)
    std = (sum((x - mean)**2 for x in tps_list) / len(tps_list))**0.5

    if baseline_tps is None:
        baseline_tps = mean

    scaling = (mean / baseline_tps - 1) * 100 if baseline_tps > 0 else 0
    speedup = mean / baseline_tps if baseline_tps > 0 else 0

    print(f"  threads={threads:1d}:  {mean:6.2f} ± {std:.2f} t/s  "
          f"({speedup:5.2f}x baseline, {scaling:+6.1f}%)  (n={len(tps_list)})")

if threads_data:
    print(f"\n  Note: 'baseline' = threads=1 ({threads_data[1][0] if 1 in threads_data else 'N/A':.2f} t/s)")
    print(f"        'speedup' = mean TPS / threads=1 mean")

PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
