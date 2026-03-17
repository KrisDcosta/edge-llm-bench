#!/usr/bin/env bash
# requantize_imatrix.sh — Re-quantize all 5 GGUF variants using importance matrices.
#
# Takes the full-precision F16 model as source and applies the per-variant
# importance matrix to produce calibrated quantizations. The resulting models
# have the same quantization type but better weight distribution for on-device tasks.
#
# Usage:
#   bash scripts/requantize_imatrix.sh                # all 5 variants
#   bash scripts/requantize_imatrix.sh Q4_K_M Q8_0   # specific variants
#   bash scripts/requantize_imatrix.sh --force        # overwrite existing files
#
# Prerequisites:
#   - llama-quantize binary (build from llama.cpp alongside llama-imatrix)
#     Build: cmake --build build --target llama-quantize -j8
#   - F16 base model: local-models/llama3_2_3b_gguf/F16.gguf
#   - Importance matrices: data/imatrix_*.dat (run run_imatrix.sh first)
#
# Output:
#   local-models/llama3_2_3b_gguf/Q2_K-imatrix.gguf
#   local-models/llama3_2_3b_gguf/Q3_K_M-imatrix.gguf
#   local-models/llama3_2_3b_gguf/Q4_K_M-imatrix.gguf
#   local-models/llama3_2_3b_gguf/Q6_K-imatrix.gguf
#   local-models/llama3_2_3b_gguf/Q8_0-imatrix.gguf
#
# Runtime: ~10-20 min per variant on CPU.
#
# Why F16 as source?
#   llama-quantize needs a high-precision source to apply the imatrix; using
#   the already-quantized model would compound quantization errors.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${PROJECT_ROOT}/data"
MODELS_DIR="${PROJECT_ROOT}/local-models/llama3_2_3b_gguf"

F16_MODEL="${MODELS_DIR}/F16.gguf"

# ---------------------------------------------------------------------------
# Locate llama-quantize binary
# ---------------------------------------------------------------------------
find_llama_quantize() {
    if [ -n "${LLAMA_QUANTIZE:-}" ] && [ -x "$LLAMA_QUANTIZE" ]; then
        echo "$LLAMA_QUANTIZE"
        return
    fi
    if command -v llama-quantize &>/dev/null; then
        command -v llama-quantize
        return
    fi
    local candidates=(
        "${PROJECT_ROOT}/../llama.cpp/build/bin/llama-quantize"
        "${HOME}/llama.cpp/build/bin/llama-quantize"
        "/usr/local/bin/llama-quantize"
    )
    for c in "${candidates[@]}"; do
        if [ -x "$c" ]; then
            echo "$c"
            return
        fi
    done
    echo ""
}

LLAMA_QUANTIZE=$(find_llama_quantize)
if [ -z "$LLAMA_QUANTIZE" ]; then
    echo "ERROR: llama-quantize not found." >&2
    echo "  Build: cd ~/llama.cpp && cmake --build build --target llama-quantize -j8" >&2
    echo "  Or set: export LLAMA_QUANTIZE=/path/to/llama-quantize" >&2
    exit 1
fi
echo "  Using: $LLAMA_QUANTIZE"

# ---------------------------------------------------------------------------
# Config — bash 3.2 compatible (quant type name = variant name for all 5)
# ---------------------------------------------------------------------------
ALL_VARIANTS="Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"
N_THREADS=$(sysctl -n hw.logicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
VARIANTS=""
FORCE=0

for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS="$VARIANTS $arg" ;;
        *) echo "Unknown argument: $arg" >&2; exit 1 ;;
    esac
done

if [ -z "$VARIANTS" ]; then
    VARIANTS="$ALL_VARIANTS"
fi
VARIANTS="${VARIANTS# }"

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "=== imatrix Re-quantization ==="
echo "  Source:   $F16_MODEL"
echo "  Variants: $VARIANTS"
echo "  Threads:  $N_THREADS"
echo ""

if [ ! -f "$F16_MODEL" ]; then
    echo "ERROR: F16 base model not found: $F16_MODEL" >&2
    echo "  Download from HuggingFace:" >&2
    echo "    huggingface-cli download bartowski/Llama-3.2-3B-Instruct-GGUF \\" >&2
    echo "      --include '*F16*' --local-dir ${MODELS_DIR}" >&2
    exit 1
fi
echo "  ✓ F16 model found ($(du -sh "$F16_MODEL" | cut -f1))"

# Check imatrix files exist
MISSING=""
for VARIANT in $VARIANTS; do
    if [ ! -f "${DATA_DIR}/imatrix_${VARIANT}.dat" ]; then
        MISSING="$MISSING $VARIANT"
    fi
done

if [ -n "$MISSING" ]; then
    echo "ERROR: Missing imatrix files for:$MISSING" >&2
    echo "  Run: bash scripts/run_imatrix.sh${MISSING}" >&2
    exit 1
fi
echo "  ✓ All imatrix .dat files found"
echo ""

# ---------------------------------------------------------------------------
# Re-quantize each variant
# ---------------------------------------------------------------------------
TOTAL=$(echo "$VARIANTS" | wc -w | tr -d ' ')
IDX=0

for VARIANT in $VARIANTS; do
    IDX=$((IDX + 1))
    echo "=== [${IDX}/${TOTAL}] Re-quantizing: ${VARIANT} with imatrix ==="

    IMATRIX_FILE="${DATA_DIR}/imatrix_${VARIANT}.dat"
    OUTPUT_MODEL="${MODELS_DIR}/${VARIANT}-imatrix.gguf"
    # Quantization type name = variant name (Q4_K_M, Q2_K, etc.)
    QUANT_TYPE="$VARIANT"

    if [ -f "$OUTPUT_MODEL" ] && [ "$FORCE" -eq 0 ]; then
        echo "  Already exists: $OUTPUT_MODEL (use --force to overwrite)"
        continue
    fi

    echo "  imatrix: $IMATRIX_FILE"
    echo "  quant:   $QUANT_TYPE"
    echo "  output:  $OUTPUT_MODEL"
    echo "  Started: $(date '+%H:%M:%S')"

    # llama-quantize usage: [--imatrix file] model-f32.gguf [model-quant.gguf] type [nthreads]
    # Note: nthreads is a positional arg at the end, not a flag
    "$LLAMA_QUANTIZE" \
        --imatrix "$IMATRIX_FILE" \
        "$F16_MODEL" \
        "$OUTPUT_MODEL" \
        "$QUANT_TYPE" \
        "$N_THREADS" \
        2>&1 | tee "${DATA_DIR}/requantize_${VARIANT}.log"

    echo "  Finished: $(date '+%H:%M:%S')"

    if [ -f "$OUTPUT_MODEL" ]; then
        SIZE=$(du -sh "$OUTPUT_MODEL" | cut -f1)
        echo "  ✓ Output: $OUTPUT_MODEL (${SIZE})"
    else
        echo "  ERROR: Output not created"
    fi
    echo ""
done

echo "=== Re-quantization complete ==="
echo ""
echo "Generated imatrix models:"
for VARIANT in "${VARIANTS[@]}"; do
    f="${MODELS_DIR}/${VARIANT}-imatrix.gguf"
    if [ -f "$f" ]; then
        echo "  ✓ $f ($(du -sh "$f" | cut -f1))"
    else
        echo "  ✗ $f (MISSING)"
    fi
done
echo ""
echo "Next steps:"
echo "  1. Push to device:"
for VARIANT in "${VARIANTS[@]}"; do
    echo "       adb push ${MODELS_DIR}/${VARIANT}-imatrix.gguf /data/local/tmp/"
done
echo ""
echo "  2. Run perplexity eval:"
echo "       bash scripts/run_perplexity_full.sh --imatrix"
echo ""
echo "  3. Run quality eval:"
echo "       python3 scripts/quality_eval.py --dataset data/arc_easy_100.yaml --tag arc_easy --imatrix"
echo "       python3 scripts/quality_eval.py --dataset data/boolq_100.yaml --tag boolq --imatrix"
