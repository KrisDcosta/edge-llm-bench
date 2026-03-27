#!/usr/bin/env bash
# ============================================================
# pixel_wikitext_ppl.sh  —  WikiText-2 perplexity evaluation
#                            Pixel 6a · CPU (4 threads) · via ADB
#
# Runs llama-perplexity on the full WikiText-2 test corpus
# for all 7 K-quant variants.  Results are written to device
# and extracted to results/pixel_wikitext_ppl_{ts}/ppl_{V}.json
#
# Usage:
#   bash scripts/bench/pixel_wikitext_ppl.sh              # all 7 variants
#   bash scripts/bench/pixel_wikitext_ppl.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/pixel_wikitext_ppl.sh --resume      # skip completed
#
# Prerequisites:
#   - data/wikitext2_full.txt on Mac  (run: python3 scripts/download_wikitext2.py)
#   - llama-perplexity binary at /data/local/tmp/ on device
#   - All GGUF model files at /data/local/tmp/ on device
#
# Output:  results/pixel_wikitext_ppl_{ts}/ppl_{VARIANT}.json
#          (also raw txt on device at /data/local/tmp/ppl_full_{VARIANT}.txt)
# Runtime: ~60-90 min per variant on Pixel 6a
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_PPL="${DEVICE_DIR}/llama-perplexity"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CORPUS_LOCAL="data/wikitext2_full.txt"
CORPUS_DEVICE="${DEVICE_DIR}/wikitext2_full.txt"
CTX_SIZE=512
THREADS=4
COOLDOWN_S=60   # between variants to avoid thermal throttling

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_wikitext_ppl_${TS}"
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
log "Pixel 6a  —  WikiText-2 Perplexity  (ctx=${CTX_SIZE}, ${THREADS} threads)"
log "Variants : ${VARIANTS[*]}"
log "Results  : ${RESULTS_DIR}"
hr

# ── Preflight ────────────────────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No Android device connected."; exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "✅ Device: ${DEVICE_ID}"

if ! adb shell "ls ${LLAMA_PPL} 2>/dev/null" | grep -q "llama-perplexity"; then
    log "❌ FATAL: llama-perplexity not found at ${LLAMA_PPL} on device."
    log "   Build with Android NDK and push: adb push llama-perplexity ${DEVICE_DIR}/"
    exit 1
fi
log "✅ llama-perplexity found on device"

if [ ! -f "$CORPUS_LOCAL" ]; then
    log "❌ FATAL: WikiText-2 corpus not found at ${CORPUS_LOCAL}"
    log "   Run: python3 scripts/download_wikitext2.py"
    exit 1
fi
CORPUS_SIZE=$(wc -c < "$CORPUS_LOCAL" | tr -d ' ')
log "✅ Corpus: ${CORPUS_LOCAL}  (${CORPUS_SIZE} bytes ≈ $(( CORPUS_SIZE / 5 )) tokens)"

MISSING=0
for V in "${VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ❌ Missing on device: ${MODEL_PREFIX}-${V}.gguf"; MISSING=$((MISSING+1))
    fi
done
[ "$MISSING" -gt 0 ] && log "❌ FATAL: $MISSING model(s) missing from device." && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present"

# Push corpus once
log ""
log "Pushing corpus to device..."
adb push "$CORPUS_LOCAL" "$CORPUS_DEVICE" 2>/dev/null
log "✅ Corpus pushed to ${CORPUS_DEVICE}"
log ""

# ── Perplexity runs ──────────────────────────────────────────
START_S=$(date +%s)
TOTAL=${#VARIANTS[@]}
IDX=0

for VARIANT in "${VARIANTS[@]}"; do
    IDX=$(( IDX + 1 ))
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/ppl_${VARIANT}.json"
    RAW_DEVICE="${DEVICE_DIR}/ppl_full_${VARIANT}.txt"
    RAW_LOCAL="${RESULTS_DIR}/ppl_raw_${VARIANT}.txt"

    # Resumability: skip if JSON result already exists
    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        log "  ⏩ SKIP $VARIANT — result already at ${OUTPUT_FILE}"
        continue
    fi

    log ""
    log "━━━ [${IDX}/${TOTAL}] ${VARIANT} ━━━"
    log "  Started: $(date)"
    log "  Model  : ${MODEL_PATH}"
    log "  Output : ${RAW_DEVICE}  (on device)"

    # Run perplexity synchronously — output tee'd to device file
    # This can take 60-90 minutes per variant
    adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
        ${LLAMA_PPL} \
        -m ${MODEL_PATH} \
        -f ${CORPUS_DEVICE} \
        --ctx-size ${CTX_SIZE} \
        -t ${THREADS} \
        2>&1 | tee ${RAW_DEVICE}" 2>/dev/null || \
        log "  ⚠️  Non-zero exit from llama-perplexity — checking output..."

    log "  Finished: $(date)"

    # Pull raw output to Mac for archiving
    adb pull "${RAW_DEVICE}" "${RAW_LOCAL}" 2>/dev/null || \
        log "  ⚠️  Could not pull raw output — result may still be on device"

    # Extract PPL value from device output
    PPL_LINE=$(adb shell "grep -E 'Final estimate' ${RAW_DEVICE} 2>/dev/null" || true)
    if [ -z "$PPL_LINE" ]; then
        # Try pulling and parsing locally
        PPL_LINE=$(grep -E "Final estimate" "${RAW_LOCAL}" 2>/dev/null | head -1 || true)
    fi

    if [ -n "$PPL_LINE" ]; then
        PPL_VALUE=$(printf '%s\n' "$PPL_LINE" | grep -oE "[0-9]+\.[0-9]+" | tail -1 || echo "null")
        log "  ✅ PPL = ${PPL_VALUE}  (${PPL_LINE})"
    else
        PPL_VALUE="null"
        log "  ❌ Could not extract PPL — check ${RAW_LOCAL}"
    fi

    # Also grab the per-chunk PPL trace for uncertainty analysis
    CHUNKS_LINE=$(grep -c "Perplexity of token" "${RAW_LOCAL}" 2>/dev/null || echo "0")

    # Save JSON result
    printf '{"variant":"%s","ppl":%s,"ctx_size":%d,"corpus":"wikitext2_full","corpus_bytes":%d,"threads":%d,"device":"Pixel6a","model":"%s","raw_local":"%s","n_chunks":%s,"ts":"%s"}\n' \
        "$VARIANT" "$PPL_VALUE" "$CTX_SIZE" "$CORPUS_SIZE" "$THREADS" \
        "${MODEL_PREFIX}-${VARIANT}" "$RAW_LOCAL" "$CHUNKS_LINE" \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$OUTPUT_FILE"

    log "  ✅ Saved ${OUTPUT_FILE}"

    # Cooldown between variants (avoid thermal throttling)
    if [ "$IDX" -lt "$TOTAL" ]; then
        log "  Cooling down ${COOLDOWN_S}s before next variant..."
        sleep "$COOLDOWN_S"
    fi
done

log ""
hr
log "PERPLEXITY SUMMARY  —  Pixel 6a  —  WikiText-2 (ctx=${CTX_SIZE})"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

print(f"\n{'Variant':<12}  {'PPL':>8}  {'Status'}")
print("-" * 40)

baseline = None
for variant in requested:
    paths = glob.glob(f"{results_dir}/ppl_{variant}.json")
    if not paths:
        print(f"  {variant:<12}  {'N/A':>8}  (not run)")
        continue
    try:
        d = json.loads(open(paths[0]).read())
        ppl = d.get("ppl")
        if ppl is None or ppl == "null":
            print(f"  {variant:<12}  {'FAILED':>8}")
            continue
        ppl = float(ppl)
        if baseline is None:
            baseline = ppl
        delta = f"  +{ppl-baseline:.2f} vs Q8_0" if variant != "Q8_0" and baseline else ""
        print(f"  {variant:<12}  {ppl:8.3f}{delta}")
    except Exception as e:
        print(f"  {variant:<12}  ERROR: {e}")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
log "Pull all raw outputs: adb pull ${DEVICE_DIR}/ppl_full_*.txt ${RESULTS_DIR}/"
hr
