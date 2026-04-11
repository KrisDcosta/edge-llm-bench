#!/usr/bin/env bash
# run_perplexity_full.sh — Run llama-perplexity on all 5 variants using the full
# WikiText-2 test corpus. Results are written to device storage and extracted
# by parse_perplexity_results.sh.
#
# Prerequisites:
#   1. Device connected via ADB (USB or WiFi)
#   2. Full corpus at data/wikitext2_full.txt (run download_wikitext2.py first)
#   3. All 5 GGUF models at /data/local/tmp/ on device
#   4. llama-perplexity binary at /data/local/tmp/llama-perplexity on device
#
# Usage:
#   bash scripts/run_perplexity_full.sh                # all 5 variants
#   bash scripts/run_perplexity_full.sh Q4_K_M Q8_0   # specific variants
#   bash scripts/run_perplexity_full.sh --imatrix      # imatrix variants
#
# Output files (on device):
#   /data/local/tmp/ppl_full_{VARIANT}.txt  — raw llama-perplexity output
#
# After completion, extract results on host:
#   bash scripts/parse_perplexity_results.sh
#
# Notes:
#   - BusyBox-safe: uses grep -E (not grep -P, which BusyBox doesn't support)
#   - Run sequentially to avoid OOM; each variant ~60-90 min on Pixel 6a
#   - Context size 512 matches llama.cpp standard PPL eval methodology
#   - Full corpus (~285K tokens) produces statistically valid fine-grained comparisons

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEVICE_DIR="/data/local/tmp"
CORPUS_LOCAL="data/wikitext2_full.txt"
CORPUS_DEVICE="${DEVICE_DIR}/wikitext2_full.txt"
LLAMA_PPL="${DEVICE_DIR}/llama-perplexity"
CTX_SIZE=512
N_THREADS=4

# Model filename prefix (consistent across all variants)
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS="Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"

# ---------------------------------------------------------------------------
# Parse arguments — bash 3.2 compatible (no declare -A)
# ---------------------------------------------------------------------------
USE_IMATRIX=0
VARIANTS=""

for arg in "$@"; do
    case "$arg" in
        --imatrix) USE_IMATRIX=1 ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS="$VARIANTS $arg" ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

if [ -z "$VARIANTS" ]; then
    VARIANTS="$ALL_VARIANTS"
fi
VARIANTS="${VARIANTS# }"

SUFFIX=""
if [ "$USE_IMATRIX" -eq 1 ]; then
    SUFFIX="-imatrix"
    echo "=== imatrix variant perplexity evaluation ==="
else
    echo "=== Original variant perplexity evaluation ==="
fi

# ---------------------------------------------------------------------------
# ADB helper
# ---------------------------------------------------------------------------
ADB="${ADB:-$(which adb 2>/dev/null || echo "$HOME/Library/Android/sdk/platform-tools/adb")}"

adb_shell() {
    "$ADB" shell "$@"
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo ""
echo "[preflight] Checking ADB connection..."
if ! "$ADB" devices 2>/dev/null | grep -q "device$"; then
    echo "ERROR: No Android device connected. Connect USB and enable USB debugging." >&2
    exit 1
fi
echo "  ✓ Device connected"

echo "[preflight] Checking corpus file..."
if [ ! -f "$CORPUS_LOCAL" ]; then
    echo "ERROR: Full corpus not found at $CORPUS_LOCAL"
    echo "  Run: python3 scripts/download_wikitext2.py"
    exit 1
fi
CORPUS_SIZE=$(wc -c < "$CORPUS_LOCAL")
echo "  ✓ Corpus found: $CORPUS_LOCAL (${CORPUS_SIZE} bytes, ~$((CORPUS_SIZE/5)) tokens)"

echo "[preflight] Checking llama-perplexity on device..."
if ! adb_shell "ls ${LLAMA_PPL} 2>/dev/null" | grep -q "llama-perplexity"; then
    echo "ERROR: llama-perplexity not found at ${LLAMA_PPL} on device" >&2
    echo "  Push it: adb push /path/to/llama-perplexity /data/local/tmp/" >&2
    exit 1
fi
echo "  ✓ llama-perplexity found on device"

echo "[preflight] Pushing corpus to device..."
"$ADB" push "$CORPUS_LOCAL" "$CORPUS_DEVICE" 2>/dev/null
echo "  ✓ Corpus pushed to ${CORPUS_DEVICE}"

# ---------------------------------------------------------------------------
# Run perplexity for each variant
# ---------------------------------------------------------------------------
TOTAL=$(echo "$VARIANTS" | wc -w | tr -d ' ')
IDX=0

for VARIANT in $VARIANTS; do
    IDX=$((IDX + 1))
    echo ""
    echo "=== [${IDX}/${TOTAL}] Running perplexity: ${VARIANT}${SUFFIX} ==="

    # Build model filename: Llama-3.2-3B-Instruct-{VARIANT}[-imatrix].gguf
    if [ "$USE_IMATRIX" -eq 1 ]; then
        MODEL_FILE="${MODEL_PREFIX}-${VARIANT}-imatrix.gguf"
    else
        MODEL_FILE="${MODEL_PREFIX}-${VARIANT}.gguf"
    fi

    MODEL_PATH="${DEVICE_DIR}/${MODEL_FILE}"
    OUTPUT_FILE="${DEVICE_DIR}/ppl_full_${VARIANT}${SUFFIX}.txt"

    # Check model on device
    if ! adb_shell "ls ${MODEL_PATH} 2>/dev/null" | grep -q ".gguf"; then
        echo "  SKIP: Model not found on device: ${MODEL_PATH}"
        continue
    fi
    echo "  Model:  ${MODEL_PATH}"
    echo "  Output: ${OUTPUT_FILE}"
    echo "  Started at: $(date '+%H:%M:%S')"

    # Run llama-perplexity in background on device, redirect to file
    # Note: We run synchronously (no &) to avoid OOM from parallel runs
    adb_shell "LD_LIBRARY_PATH=${DEVICE_DIR} ${LLAMA_PPL} \
        -m ${MODEL_PATH} \
        -f ${CORPUS_DEVICE} \
        --ctx-size ${CTX_SIZE} \
        -t ${N_THREADS} \
        2>&1 | tee ${OUTPUT_FILE}"

    echo "  Finished at: $(date '+%H:%M:%S')"

    # Quick extraction check (BusyBox-safe grep -E)
    PPL_LINE=$(adb_shell "grep -E 'Final estimate' ${OUTPUT_FILE} 2>/dev/null" || true)
    if [ -n "$PPL_LINE" ]; then
        echo "  Result: ${PPL_LINE}"
    else
        echo "  WARNING: Could not find 'Final estimate' in output. Check ${OUTPUT_FILE} on device."
    fi

    # Cool-down between variants to avoid thermal throttling
    if [ "$IDX" -lt "$TOTAL" ]; then
        echo "  Cooling down 60s before next variant..."
        sleep 60
    fi
done

echo ""
echo "=== All perplexity runs complete ==="
echo ""
echo "To extract results:"
echo "  bash scripts/parse_perplexity_results.sh"
echo ""
echo "Or manually:"
for VARIANT in $VARIANTS; do
    echo "  adb shell \"grep -E 'Final estimate' ${DEVICE_DIR}/ppl_full_${VARIANT}${SUFFIX}.txt\""
done
