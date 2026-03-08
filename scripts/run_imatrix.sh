#!/usr/bin/env bash
# run_imatrix.sh — Generate importance matrices for all 5 GGUF quantization variants.
#
# The importance matrix (imatrix) captures which weights matter most for the
# calibration corpus, enabling smarter quantization in the re-quantization step.
#
# Usage:
#   bash scripts/run_imatrix.sh                # all 5 variants
#   bash scripts/run_imatrix.sh Q4_K_M Q8_0   # specific variants
#
# Prerequisites:
#   - llama-imatrix binary available (build from llama.cpp or download prebuilt)
#     Build: cd llama.cpp && cmake -B build && cmake --build build --target llama-imatrix -j8
#     Binary: build/bin/llama-imatrix
#   - Calibration corpus: data/wikitext2_full.txt (run download_wikitext2.py first)
#   - Source GGUF models in local-models/llama3_2_3b_gguf/
#
# Output:
#   data/imatrix_Q2_K.dat
#   data/imatrix_Q3_K_M.dat
#   data/imatrix_Q4_K_M.dat
#   data/imatrix_Q6_K.dat
#   data/imatrix_Q8_0.dat
#
# Each .dat file is used by requantize_imatrix.sh to produce calibrated GGUFs.
# Runtime: ~15-30 min per variant on CPU (host machine).
#
# Note: imatrix is computed using the source quantized model (not F16) because
# we want to learn which weights the specific quantization level most distorts.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${PROJECT_ROOT}/data"
MODELS_DIR="${PROJECT_ROOT}/local-models/llama3_2_3b_gguf"
CORPUS="${DATA_DIR}/wikitext2_full.txt"

# ---------------------------------------------------------------------------
# Locate llama-imatrix binary
# ---------------------------------------------------------------------------
find_llama_imatrix() {
    # Check environment variable
    if [ -n "${LLAMA_IMATRIX:-}" ] && [ -x "$LLAMA_IMATRIX" ]; then
        echo "$LLAMA_IMATRIX"
        return
    fi
    # Check PATH
    if command -v llama-imatrix &>/dev/null; then
        command -v llama-imatrix
        return
    fi
    # Check common build locations relative to project
    local candidates=(
        "${PROJECT_ROOT}/../llama.cpp/build/bin/llama-imatrix"
        "${HOME}/llama.cpp/build/bin/llama-imatrix"
        "/usr/local/bin/llama-imatrix"
        "$(dirname "$0")/../../llama.cpp/build/bin/llama-imatrix"
    )
    for c in "${candidates[@]}"; do
        if [ -x "$c" ]; then
            echo "$c"
            return
        fi
    done
    echo ""
}

LLAMA_IMATRIX=$(find_llama_imatrix)
if [ -z "$LLAMA_IMATRIX" ]; then
    echo "ERROR: llama-imatrix not found." >&2
    echo "  Build it: cd ~/llama.cpp && cmake -B build && cmake --build build --target llama-imatrix -j8" >&2
    echo "  Or set: export LLAMA_IMATRIX=/path/to/llama-imatrix" >&2
    exit 1
fi
echo "  Using: $LLAMA_IMATRIX"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ALL_VARIANTS=("Q2_K" "Q3_K_M" "Q4_K_M" "Q6_K" "Q8_0")

declare -A MODEL_FILES
MODEL_FILES["Q2_K"]="Q2_K.gguf"
MODEL_FILES["Q3_K_M"]="Q3_K_M.gguf"
MODEL_FILES["Q4_K_M"]="Q4_K_M.gguf"
MODEL_FILES["Q6_K"]="Q6_K.gguf"
MODEL_FILES["Q8_0"]="Q8_0.gguf"

# Number of calibration chunks (each chunk = ctx-size tokens)
# 128 chunks × 512 tokens = 65,536 tokens for calibration
N_CHUNKS=128
CTX_SIZE=512
N_THREADS=$(sysctl -n hw.logicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------
VARIANTS=()
for arg in "$@"; do
    case "$arg" in
        Q2_K|Q3_K_M|Q4_K_M|Q6_K|Q8_0) VARIANTS+=("$arg") ;;
        *) echo "Unknown variant: $arg. Valid: Q2_K Q3_K_M Q4_K_M Q6_K Q8_0" >&2; exit 1 ;;
    esac
done
if [ ${#VARIANTS[@]} -eq 0 ]; then
    VARIANTS=("${ALL_VARIANTS[@]}")
fi

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "=== imatrix Generation ==="
echo "  Variants: ${VARIANTS[*]}"
echo "  Corpus:   $CORPUS"
echo "  Chunks:   $N_CHUNKS × $CTX_SIZE tokens = $((N_CHUNKS * CTX_SIZE)) calibration tokens"
echo "  Threads:  $N_THREADS"
echo ""

if [ ! -f "$CORPUS" ]; then
    echo "ERROR: Corpus not found: $CORPUS"
    echo "  Run: python3 scripts/download_wikitext2.py"
    exit 1
fi

mkdir -p "$DATA_DIR"

# ---------------------------------------------------------------------------
# Generate imatrix for each variant
# ---------------------------------------------------------------------------
TOTAL=${#VARIANTS[@]}
IDX=0

for VARIANT in "${VARIANTS[@]}"; do
    IDX=$((IDX + 1))
    echo "=== [${IDX}/${TOTAL}] Generating imatrix: ${VARIANT} ==="

    MODEL_FILE="${MODELS_DIR}/${MODEL_FILES[$VARIANT]}"
    OUTPUT_FILE="${DATA_DIR}/imatrix_${VARIANT}.dat"

    if [ ! -f "$MODEL_FILE" ]; then
        echo "  SKIP: Model not found: $MODEL_FILE"
        continue
    fi

    if [ -f "$OUTPUT_FILE" ]; then
        echo "  Already exists: $OUTPUT_FILE (use --force or delete to regenerate)"
        continue
    fi

    echo "  Model:  $MODEL_FILE"
    echo "  Output: $OUTPUT_FILE"
    echo "  Started: $(date '+%H:%M:%S')"

    "$LLAMA_IMATRIX" \
        -m "$MODEL_FILE" \
        -f "$CORPUS" \
        -o "$OUTPUT_FILE" \
        --chunks "$N_CHUNKS" \
        --ctx-size "$CTX_SIZE" \
        -t "$N_THREADS" \
        --no-gpu-layers 0 \
        2>&1 | tee "${DATA_DIR}/imatrix_${VARIANT}.log"

    echo "  Finished: $(date '+%H:%M:%S')"

    if [ -f "$OUTPUT_FILE" ]; then
        SIZE=$(wc -c < "$OUTPUT_FILE")
        echo "  ✓ Output: $OUTPUT_FILE (${SIZE} bytes)"
    else
        echo "  ERROR: Output file not created"
    fi

    echo ""
done

echo "=== imatrix generation complete ==="
echo ""
echo "Generated files:"
for VARIANT in "${VARIANTS[@]}"; do
    f="${DATA_DIR}/imatrix_${VARIANT}.dat"
    if [ -f "$f" ]; then
        echo "  ✓ $f ($(wc -c < "$f") bytes)"
    else
        echo "  ✗ $f (MISSING)"
    fi
done
echo ""
echo "Next: bash scripts/requantize_imatrix.sh"
