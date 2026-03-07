#!/usr/bin/env bash
# smoke_test.sh — Quick on-device inference check for Phase 0 validation.
#
# Runs one prompt through llama-cli on device and prints key metrics.
# Does NOT use the Python runner — raw adb for maximum simplicity.
#
# Usage:
#   ./scripts/smoke_test.sh [gguf_variant]
#
# Examples:
#   ./scripts/smoke_test.sh               # uses Q4_K_M (default)
#   ./scripts/smoke_test.sh Q2_K
#
# Prerequisites:
#   - adb connected to Pixel 6a
#   - /data/local/tmp/llama-cli pushed to device
#   - /data/local/tmp/<variant>.gguf pushed to device

set -euo pipefail

VARIANT="${1:-Q4_K_M}"
DEVICE_DIR="/data/local/tmp"
# llama.cpp b1+ uses llama-completion for single-shot inference
# (llama-cli is now interactive chat only)
LLAMA_CLI="$DEVICE_DIR/llama-completion"
MODEL="$DEVICE_DIR/Llama-3.2-3B-Instruct-${VARIANT}.gguf"
PROMPT="Answer in one sentence: What is the capital of France?"
N_TOKENS=32
CTX=256

echo "=== llama.cpp Smoke Test ==="
echo "Variant : $VARIANT"
echo "Model   : $MODEL"
echo ""

# Verify device
if ! adb devices | grep -q "device$"; then
    echo "ERROR: No Android device connected."
    exit 1
fi

# Verify binary
if ! adb shell "ls $LLAMA_CLI 2>/dev/null"; then
    echo "ERROR: llama-cli not found at $LLAMA_CLI on device."
    echo "Build and push first: ./scripts/build_llamacpp_android.sh"
    exit 1
fi

# Verify model
if ! adb shell "ls $MODEL 2>/dev/null"; then
    echo "ERROR: Model not found at $MODEL on device."
    echo "Push it: adb push local-models/llama3_2_3b_gguf/${VARIANT}.gguf $MODEL"
    exit 1
fi

echo "Running inference (--n-predict $N_TOKENS, --ctx-size $CTX)..."
echo ""

# Run and capture output
OUTPUT=$(adb shell \
    "LD_LIBRARY_PATH=$DEVICE_DIR $LLAMA_CLI \
    -m $MODEL \
    -c $CTX \
    -n $N_TOKENS \
    --temp 0.0 \
    --seed 42 \
    -t 4 \
    -no-cnv \
    -p \"$PROMPT\" 2>&1")

echo "=== Raw Output ==="
echo "$OUTPUT"
echo ""

# Extract and print key metrics
# llama.cpp b1+ uses common_perf_print: prefix (older: llama_perf_context_print:)
echo "=== Key Metrics ==="
echo "$OUTPUT" | grep -E "load time|prompt eval time|eval time|total time" | \
    sed 's/common_perf_print://;s/llama_perf_context_print://' | sed 's/^[[:space:]]*/  /'

# Check if timings were found
if echo "$OUTPUT" | grep -q "eval time"; then
    echo ""
    echo "Smoke test PASSED — timings found in output."
    echo ""
    echo "Next step: python scripts/benchmark_runner.py --smoke"
else
    echo ""
    echo "WARNING: Timing output not found. Check output above."
    echo "The model may have loaded but not completed generation."
    exit 1
fi
