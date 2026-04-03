#!/usr/bin/env bash
# ============================================================
# pixel_llama_cliff_filled.sh  —  KV-cache cliff sweep with FILLED context
#                                  Pixel 6a · CPU (4 threads) · via ADB
#
# METHODOLOGY: Uses a prompt of ~(N-64) tokens so the KV cache is
# actually populated at each context size.  This is the correct approach
# for measuring KV-cache throughput sensitivity.  The original cliff sweep
# (pixel_llama_cliff.sh) used a short ~15-token prompt, so the cache was
# never filled and no cliff was measurable.
#
# NOTE: The device binary outputs stats as:
#   common_perf_print: prompt eval time = ... X.XX tokens per second
#   common_perf_print:        eval time = ... X.XX tokens per second
# All parsing in this script uses this correct prefix.
#
# Usage:
#   bash scripts/bench/pixel_llama_cliff_filled.sh              # all 7 variants
#   bash scripts/bench/pixel_llama_cliff_filled.sh Q6_K Q3_K_M  # subset
#   bash scripts/bench/pixel_llama_cliff_filled.sh --resume      # skip completed
#
# Output:  results/pixel_llama_cliff_filled_{ts}/cliff_filled_{VARIANT}.jsonl
# Runtime: ~8-10 h  (7 variants × 11 ctx × 3 trials; prefill cost is higher)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CTX_SIZES=(256 512 768 1024 1200 1300 1400 1500 1600 1800 2048)
NUM_TRIALS=3
OUTPUT_TOKENS=64
THREADS=4

# Seed paragraph for dynamic prompt generation.
# Llama tokenizer averages ~1.3 chars/token; generate_prompt() uses this ratio.
SEED_TEXT="The transformer architecture fundamentally changed natural language processing by introducing self-attention mechanisms that allow models to relate different positions of a sequence when computing a representation. Unlike recurrent networks, transformers process sequences in parallel and use positional encodings to maintain order information. Each transformer block consists of a multi-head attention layer followed by a feed-forward network, with layer normalization and residual connections enabling stable training of deep models. The key innovation is the attention mechanism itself: for each token, attention computes a weighted sum of all other token representations, where weights are determined by learned query and key projections. This allows long-range dependencies to be captured in a single layer. Modern large language models scale this architecture to billions of parameters across dozens of layers, using grouped-query attention and other efficiency improvements to reduce memory requirements during inference."

# generate_prompt TARGET_TOKENS
# Repeats SEED_TEXT until the character count covers the target and trims.
generate_prompt() {
    local target_tokens=$1
    local target_chars=$(( target_tokens * 13 / 10 ))   # 1.3 chars/token estimate
    local text=""
    while [ ${#text} -lt $target_chars ]; do
        text="${text} ${SEED_TEXT}"
    done
    echo "${text:0:$target_chars}"
}

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_llama_cliff_filled_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

RESUME=0
VARIANTS=()
i=1
while [ $i -le $# ]; do
    arg="${!i}"
    case "$arg" in
        --resume) RESUME=1 ;;
        --trials)
            i=$(( i + 1 ))
            NUM_TRIALS="${!i}" ;;
        --trials=*) NUM_TRIALS="${arg#--trials=}" ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
    i=$(( i + 1 ))
done
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=("${ALL_VARIANTS[@]}")

hr
log "Pixel 6a  —  Llama 3.2 3B KV-Cache Cliff Sweep (FILLED CONTEXT)  (CPU, ${THREADS} threads)"
log "Methodology : filled_context — prompt length ≈ ctx - ${OUTPUT_TOKENS} tokens"
log "Variants    : ${VARIANTS[*]}"
log "Contexts    : ${CTX_SIZES[*]}"
log "Trials      : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
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

# ── Model inventory on device ─────────────────────────────────
MISSING=0
for V in "${VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ❌ Missing on device: ${MODEL_PREFIX}-${V}.gguf"
        MISSING=$((MISSING + 1))
    fi
done
[ "$MISSING" -gt 0 ] && log "❌ FATAL: $MISSING model(s) missing from device." && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present on device"
log ""

# ── Main sweep ─────────────────────────────────────────────────
EXPECTED_LINES=$(( ${#CTX_SIZES[@]} * NUM_TRIALS ))
TOTAL_RUNS=$(( ${#VARIANTS[@]} * EXPECTED_LINES ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/cliff_filled_${VARIANT}.jsonl"

    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        DONE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
        if [ "$DONE" -ge "$EXPECTED_LINES" ]; then
            log "  ⏩ SKIP $VARIANT — already complete (${DONE} rows)"
            CURRENT_RUN=$(( CURRENT_RUN + EXPECTED_LINES ))
            continue
        fi
        log "  ↩  RESUME $VARIANT — ${DONE}/${EXPECTED_LINES} done; re-running"
    fi

    log ""
    log "━━━ ${VARIANT} ━━━"
    > "$OUTPUT_FILE"

    for CTX in "${CTX_SIZES[@]}"; do
        # Prompt length = ctx - OUTPUT_TOKENS, so the KV cache is filled at decode time
        PROMPT_TOKENS=$(( CTX - OUTPUT_TOKENS ))
        PROMPT=$(generate_prompt "$PROMPT_TOKENS")
        PROMPT_CHARS=${#PROMPT}

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$(( CURRENT_RUN + 1 ))
            ELAPSED=$(( $(date +%s) - START_S ))
            [ "$CURRENT_RUN" -gt 1 ] \
                && ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED )) \
                || ETA=0

            # Run via ADB — LD_LIBRARY_PATH must be exported before llama-completion
            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
                echo '' | ${LLAMA_BIN} \
                -m ${MODEL_PATH} \
                -c ${CTX} \
                -n ${OUTPUT_TOKENS} \
                -t ${THREADS} \
                -p '${PROMPT}' 2>&1" 2>/dev/null || echo "ADB_ERROR")

            RAW_BYTES=${#RAW}

            # Parse from "common_perf_print:" lines (correct prefix for this binary)
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
                log "  ⚠️  ADB error  ctx=${CTX} t=${TRIAL}"
            [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ] && \
                log "  ⚠️  Small output (${RAW_BYTES}B)  ctx=${CTX} t=${TRIAL} — binary may have failed"

            printf '{"variant":"%s","context":%d,"prompt_tokens_approx":%d,"trial":%d,"decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","methodology":"filled_context","model":"%s","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
                "$VARIANT" "$CTX" "$PROMPT_TOKENS" "$TRIAL" "$DECODE" "$PREFILL" "$RAW_BYTES" \
                "${MODEL_PREFIX}-${VARIANT}" "$THREADS" "$OUTPUT_TOKENS" \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  ctx=${CTX}  prompt_tok≈${PROMPT_TOKENS}  t=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
        done
    done

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

log ""
hr
log "CLIFF ANALYSIS (FILLED CONTEXT)  —  Pixel 6a (CPU)"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

for variant in requested:
    paths = glob.glob(f"{results_dir}/cliff_filled_{variant}.jsonl")
    if not paths:
        continue
    data  = [json.loads(l) for l in open(paths[0]) if l.strip()]
    ctx_d = defaultdict(list)
    ctx_p = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps",  0)) > 0:
            ctx_d[d["context"]].append(float(d["decode_tps"]))
        if float(d.get("prefill_tps", 0)) > 0:
            ctx_p[d["context"]].append(float(d["prefill_tps"]))

    valid = sum(len(v) for v in ctx_d.values())
    print(f"\n{'='*72}")
    print(f"  {variant}  ({valid}/{len(data)} valid)  [methodology: filled_context]")
    print(f"{'='*72}")

    baseline = None
    peak_tps  = 0.0
    peak_ctx  = None
    cliff_ctx = None

    ctxs = sorted(ctx_d)
    rows = []
    for ctx in ctxs:
        avg  = sum(ctx_d[ctx]) / len(ctx_d[ctx])
        pavg = (sum(ctx_p[ctx]) / len(ctx_p[ctx])) if ctx_p.get(ctx) else 0
        if baseline is None:
            baseline = avg
        pct_from_baseline = (avg - baseline) / baseline * 100 if baseline else 0
        if avg > peak_tps:
            peak_tps = avg
            peak_ctx = ctx
        if cliff_ctx is None and baseline and (baseline - avg) / baseline > 0.10:
            cliff_ctx = ctx
        rows.append((ctx, avg, pavg, len(ctx_d[ctx]), pct_from_baseline))

    prev_avg = None
    for ctx, avg, pavg, n, pct_base in rows:
        step_note = ""
        if prev_avg is not None and prev_avg > 0 and (prev_avg - avg) / prev_avg > 0.10:
            step_note = f"  ← CLIFF {(prev_avg - avg) / prev_avg * 100:.0f}%"
        print(f"  ctx={ctx:5d}:  decode={avg:6.2f} t/s  prefill={pavg:6.1f} t/s"
              f"  ({pct_base:+.1f}% vs baseline)  (n={n}){step_note}")
        prev_avg = avg

    print()
    print(f"  Peak TPS context  : ctx={peak_ctx}  ({peak_tps:.2f} t/s)")
    if cliff_ctx is not None:
        print(f"  Cliff onset       : ctx={cliff_ctx}  (first >10% drop from ctx={ctxs[0]} baseline)")
    else:
        print(f"  Cliff onset       : none detected (no single >10% drop from baseline)")
    if baseline and baseline > 0:
        final_avg = rows[-1][1]
        print(f"  Total drop        : {(baseline - final_avg) / baseline * 100:.1f}%  "
              f"(ctx={ctxs[0]} → ctx={ctxs[-1]})")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
