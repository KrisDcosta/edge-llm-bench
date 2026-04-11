#!/usr/bin/env bash
# ============================================================
# pixel_llama_fa_mitigation.sh  —  Flash-attention mitigation test
#                                   Pixel 6a · CPU (4 threads) · via ADB
#
# IMPORTANT: This script was tested on 2026-03-26 and the -fa (Flash
# Attention) flag was found to be UNSUPPORTED by the llama-completion
# binary currently deployed on the Pixel 6a device.  All trials returned
# immediately with ~311 bytes of error/help output and decode_tps=0.
#
# Status: BLOCKED — Flash Attention unavailable on this binary build.
# The llama-completion binary was built without FA support (likely
# requires a rebuild with LLAMA_FLASH_ATTN=ON cmake flag).
#
# If you rebuild the binary with FA support, this script is ready to run:
#   bash scripts/bench/pixel_llama_fa_mitigation.sh
#
# Runs ONLY ctx=1400 and ctx=2048 with the -fa (flash attention) flag,
# using the same filled-context prompt methodology as
# pixel_llama_cliff_filled.sh.  Comparing results from this script against
# cliff_filled output at ctx=2048 reveals how much of the KV-cache cliff
# is recovered by flash attention.
#
# Usage:
#   bash scripts/bench/pixel_llama_fa_mitigation.sh              # default variants
#   bash scripts/bench/pixel_llama_fa_mitigation.sh Q6_K Q3_K_M  # subset
#   bash scripts/bench/pixel_llama_fa_mitigation.sh --resume      # skip completed
#
# Output:  results/pixel_llama_fa_mitigation_{ts}/fa_mitigation_{VARIANT}.jsonl
# Runtime: ~1-2 h  (3 variants × 2 ctx × 5 trials) — when FA is available
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q6_K)
CTX_SIZES=(1400 2048)
NUM_TRIALS=5
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
RESULTS_DIR="results/pixel_llama_fa_mitigation_${TS}"
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
log "Pixel 6a  —  Llama 3.2 3B Flash Attention Mitigation  (CPU, ${THREADS} threads)"
log "Methodology : filled_context + -fa flag"
log "Variants    : ${VARIANTS[*]}"
log "Contexts    : ${CTX_SIZES[*]}"
log "Trials      : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
log "Results     : ${RESULTS_DIR}"
log ""
log "Compare output against cliff_filled results at ctx=1400 and ctx=2048"
log "to measure the throughput recovery from flash attention."
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
    OUTPUT_FILE="${RESULTS_DIR}/fa_mitigation_${VARIANT}.jsonl"

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

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$(( CURRENT_RUN + 1 ))
            ELAPSED=$(( $(date +%s) - START_S ))
            [ "$CURRENT_RUN" -gt 1 ] \
                && ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED )) \
                || ETA=0

            # Run via ADB with -fa flag — LD_LIBRARY_PATH must be exported
            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
                echo '' | ${LLAMA_BIN} \
                -m ${MODEL_PATH} \
                -c ${CTX} \
                -n ${OUTPUT_TOKENS} \
                -t ${THREADS} \
                -fa \
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

            printf '{"variant":"%s","context":%d,"prompt_tokens_approx":%d,"trial":%d,"decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","methodology":"filled_context","flash_attention":true,"model":"%s","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
                "$VARIANT" "$CTX" "$PROMPT_TOKENS" "$TRIAL" "$DECODE" "$PREFILL" "$RAW_BYTES" \
                "${MODEL_PREFIX}-${VARIANT}" "$THREADS" "$OUTPUT_TOKENS" \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  ctx=${CTX}  prompt_tok≈${PROMPT_TOKENS}  t=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s  [FA]"
        done
    done

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

log ""
hr
log "FLASH ATTENTION MITIGATION ANALYSIS  —  Pixel 6a (CPU)"
log "NOTE: Pass the cliff_filled results dir as second arg for cross-comparison."
log "  e.g.  python3 -  <fa_dir>  <cliff_filled_dir>  ${VARIANTS[*]}"
hr

python3 - "$RESULTS_DIR" "" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys, os
from collections import defaultdict

fa_dir          = sys.argv[1]
baseline_dir    = sys.argv[2] if len(sys.argv) > 2 else ""   # optional cliff_filled dir
requested       = sys.argv[3:] if len(sys.argv) > 3 else ["Q2_K","Q3_K_M","Q6_K"]

def load_jsonl(path):
    with open(path) as fh:
        return [json.loads(l) for l in fh if l.strip()]

def ctx_means(data):
    ctx_d = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps", 0)) > 0:
            ctx_d[d["context"]].append(float(d["decode_tps"]))
    return {c: sum(v)/len(v) for c, v in ctx_d.items()}

for variant in requested:
    fa_paths = glob.glob(f"{fa_dir}/fa_mitigation_{variant}.jsonl")
    if not fa_paths:
        print(f"\n  {variant}: no FA data found, skipping")
        continue

    fa_data  = load_jsonl(fa_paths[0])
    fa_means = ctx_means(fa_data)

    # Try to load matching cliff_filled baseline
    base_means = {}
    if baseline_dir and os.path.isdir(baseline_dir):
        base_paths = glob.glob(f"{baseline_dir}/cliff_filled_{variant}.jsonl")
        if base_paths:
            base_means = ctx_means(load_jsonl(base_paths[0]))

    print(f"\n{'='*72}")
    print(f"  {variant}  [flash_attention=true vs filled_context baseline]")
    print(f"{'='*72}")
    print(f"  {'ctx':>6}  {'FA decode (t/s)':>17}  {'base decode (t/s)':>19}  {'recovery':>10}")
    print(f"  {'-'*6}  {'-'*17}  {'-'*19}  {'-'*10}")

    for ctx in sorted(fa_means):
        fa_tps   = fa_means[ctx]
        base_tps = base_means.get(ctx)
        if base_tps is not None and base_tps > 0:
            # Recovery: how much of the gap relative to ctx=256 baseline is recovered
            # (or simply, how FA compares to standard filled at the same ctx)
            recovery = (fa_tps - base_tps) / base_tps * 100
            rec_str  = f"{recovery:+.1f}%"
        else:
            rec_str = "  (no baseline)"
        base_str = f"{base_tps:7.2f}" if base_tps is not None else "    n/a"
        print(f"  {ctx:6d}  {fa_tps:17.2f}  {base_str:>19}  {rec_str:>10}")

    # Summary at ctx=2048
    if 2048 in fa_means:
        fa_2048   = fa_means[2048]
        base_2048 = base_means.get(2048)
        base_256  = base_means.get(256)
        print()
        print(f"  Summary at ctx=2048:")
        print(f"    Flash attention TPS : {fa_2048:.2f} t/s")
        if base_2048 is not None:
            diff = (fa_2048 - base_2048) / base_2048 * 100
            print(f"    Filled context TPS  : {base_2048:.2f} t/s  ({diff:+.1f}% change with FA)")
        if base_256 is not None and base_256 > 0:
            cliff_drop    = (base_256 - (base_2048 or fa_2048)) / base_256 * 100
            fa_recovery   = (fa_2048 - (base_2048 or 0))
            recovered_pct = (fa_recovery / (base_256 - (base_2048 or base_256))) * 100 \
                            if base_2048 is not None and (base_256 - base_2048) > 0 else 0
            print(f"    Cliff drop (filled) : {cliff_drop:.1f}%  (ctx=256 → ctx=2048)")
            if base_2048 is not None:
                print(f"    FA recovery         : {recovered_pct:.1f}% of cliff recovered")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
log ""
log "To run cross-comparison analysis with cliff_filled data:"
log "  python3 scripts/bench/pixel_llama_fa_mitigation.sh <fa_dir> <cliff_filled_dir> [variants...]"
hr
