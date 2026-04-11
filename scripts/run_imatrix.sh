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
#   - llama-imatrix binary (brew install llama.cpp — includes all binaries)
#   - Calibration corpus: data/wikitext2_full.txt (run download_wikitext2.py first)
#   - Source GGUF models in local-models/llama3_2_3b_gguf/
#
# Output:
#   data/imatrix_Q2_K.dat, data/imatrix_Q3_K_M.dat, ...
#
# Each .dat file is used by requantize_imatrix.sh to produce calibrated GGUFs.
# Runtime: ~10 min per variant with Metal GPU on Apple Silicon.
#
# Compatible with bash 3.2+ (macOS default — no associative arrays used).

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${PROJECT_ROOT}/data"
MODELS_DIR="${PROJECT_ROOT}/local-models/llama3_2_3b_gguf"
CORPUS="${DATA_DIR}/wikitext2_full.txt"

# ---------------------------------------------------------------------------
# Locate llama-imatrix binary
# ---------------------------------------------------------------------------
find_llama_imatrix() {
    if [ -n "${LLAMA_IMATRIX:-}" ] && [ -x "$LLAMA_IMATRIX" ]; then
        echo "$LLAMA_IMATRIX"; return
    fi
    if command -v llama-imatrix >/dev/null 2>&1; then
        command -v llama-imatrix; return
    fi
    for c in \
        /opt/homebrew/bin/llama-imatrix \
        /usr/local/bin/llama-imatrix \
        "${HOME}/llama.cpp/build/bin/llama-imatrix" \
        "${PROJECT_ROOT}/../llama.cpp/build/bin/llama-imatrix"
    do
        if [ -x "$c" ]; then echo "$c"; return; fi
    done
    echo ""
}

LLAMA_IMATRIX=$(find_llama_imatrix)
if [ -z "$LLAMA_IMATRIX" ]; then
    echo "ERROR: llama-imatrix not found." >&2
    echo "  Install: brew install llama.cpp" >&2
    echo "  Or set: export LLAMA_IMATRIX=/path/to/llama-imatrix" >&2
    exit 1
fi
echo "  Using: $LLAMA_IMATRIX"

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ALL_VARIANTS="Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"

# Number of calibration chunks (each chunk = ctx-size tokens)
# 128 chunks × 512 tokens = 65,536 tokens for calibration
N_CHUNKS=128
CTX_SIZE=512
N_THREADS=$(sysctl -n hw.logicalcpu 2>/dev/null || nproc 2>/dev/null || echo 4)

# ---------------------------------------------------------------------------
# Parse arguments — bash 3.2 compatible (no declare -A)
# ---------------------------------------------------------------------------
VARIANTS=""
for arg in "$@"; do
    case "$arg" in
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS="$VARIANTS $arg" ;;
        *) echo "Unknown variant: $arg. Valid: Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0" >&2; exit 1 ;;
    esac
done
if [ -z "$VARIANTS" ]; then
    VARIANTS="$ALL_VARIANTS"
fi
VARIANTS="${VARIANTS# }"  # strip leading space

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------
echo "=== imatrix Generation ==="
echo "  Variants: $VARIANTS"
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

# Count variants
TOTAL=$(echo "$VARIANTS" | wc -w | tr -d ' ')
IDX=0

# ---------------------------------------------------------------------------
# Generate imatrix for each variant
# ---------------------------------------------------------------------------
for VARIANT in $VARIANTS; do
    IDX=$((IDX + 1))
    echo "=== [${IDX}/${TOTAL}] Generating imatrix: ${VARIANT} ==="

    # Model file name = variant name + .gguf (e.g. Q4_K_M.gguf)
    MODEL_FILE="${MODELS_DIR}/${VARIANT}.gguf"
    OUTPUT_FILE="${DATA_DIR}/imatrix_${VARIANT}.dat"
    LOG_FILE="${DATA_DIR}/imatrix_${VARIANT}.log"

    if [ ! -f "$MODEL_FILE" ]; then
        echo "  SKIP: Model not found: $MODEL_FILE"
        continue
    fi

    if [ -f "$OUTPUT_FILE" ]; then
        echo "  Already exists: $OUTPUT_FILE (delete to regenerate)"
        continue
    fi

    echo "  Model:   $MODEL_FILE"
    echo "  Output:  $OUTPUT_FILE"
    echo "  Started: $(date '+%H:%M:%S')"

    "$LLAMA_IMATRIX" \
        -m "$MODEL_FILE" \
        -f "$CORPUS" \
        -o "$OUTPUT_FILE" \
        --chunks "$N_CHUNKS" \
        --ctx-size "$CTX_SIZE" \
        -t "$N_THREADS" \
        2>&1 | tee "$LOG_FILE"

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
for VARIANT in $VARIANTS; do
    f="${DATA_DIR}/imatrix_${VARIANT}.dat"
    if [ -f "$f" ]; then
        SIZE=$(wc -c < "$f")
        echo "  ✓ $f (${SIZE} bytes)"
    else
        echo "  ✗ $f (MISSING)"
    fi
done
echo ""
echo "Next: bash scripts/requantize_imatrix.sh"
