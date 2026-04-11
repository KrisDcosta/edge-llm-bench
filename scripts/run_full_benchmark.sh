#!/usr/bin/env bash
# run_full_benchmark.sh — Full pipeline: push models → smoke test → full sweep → validate → figures
#
# Run this ONCE the Pixel 6a is connected via USB with USB debugging enabled.
#
# Usage:
#   ./scripts/run_full_benchmark.sh          # full sweep (all planned experiments)
#   ./scripts/run_full_benchmark.sh --smoke  # smoke test only
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Find adb
ADB="${ADB:-}"
if [ -z "$ADB" ]; then
    if command -v adb &>/dev/null; then
        ADB="adb"
    elif [ -f "$HOME/Library/Android/sdk/platform-tools/adb" ]; then
        ADB="$HOME/Library/Android/sdk/platform-tools/adb"
    elif [ -n "${ANDROID_HOME:-}" ] && [ -f "$ANDROID_HOME/platform-tools/adb" ]; then
        ADB="$ANDROID_HOME/platform-tools/adb"
    else
        echo "ERROR: adb not found. Set ADB=/path/to/adb or add platform-tools to PATH."
        exit 1
    fi
fi

SMOKE_ONLY=false
if [ "${1:-}" = "--smoke" ]; then
    SMOKE_ONLY=true
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║   Edge LLM Benchmark — Full Pipeline                    ║"
echo "║   Pixel 6a × Llama 3.2 3B GGUF × llama.cpp             ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# --- Step 0: Verify device ---
echo "[0/5] Verifying device connection..."
DEVICE_LINE=$("$ADB" devices | grep -v "^List" | grep "device$" | head -1 || true)
if [ -z "$DEVICE_LINE" ]; then
    echo ""
    echo "ERROR: No Android device connected."
    echo ""
    echo "To fix:"
    echo "  1. Connect Pixel 6a via USB cable"
    echo "  2. Enable USB debugging (Settings → Developer options → USB debugging)"
    echo "  3. Accept 'Allow USB debugging' prompt on device screen"
    echo "  4. Re-run this script"
    echo ""
    exit 1
fi
MODEL_NAME=$("$ADB" shell getprop ro.product.model 2>/dev/null | tr -d '\r')
ANDROID_VER=$("$ADB" shell getprop ro.build.version.release 2>/dev/null | tr -d '\r')
echo "  Device: $MODEL_NAME (Android $ANDROID_VER)"
echo ""

# --- Step 1: Push binaries + models ---
echo "[1/5] Pushing binaries and models to device..."
"$SCRIPT_DIR/push_models_to_device.sh" all
echo ""

# --- Step 2: Smoke test ---
echo "[2/5] Running smoke test (Q4_K_M, ctx=256, 1 trial)..."
SMOKE_OUT=$(python3 "$SCRIPT_DIR/benchmark_runner.py" --smoke 2>&1)
echo "$SMOKE_OUT"

# Validate smoke result
SMOKE_FILE=$(ls -t "$PROJECT_ROOT/results/smoke-"*.jsonl 2>/dev/null | head -1)
if [ -z "$SMOKE_FILE" ]; then
    echo "ERROR: No smoke result file found!"
    exit 1
fi
python3 "$SCRIPT_DIR/validate_results.py" "$SMOKE_FILE"
echo "  Smoke test PASSED — schema valid ✓"
echo ""

if $SMOKE_ONLY; then
    echo "Smoke-only mode: done."
    exit 0
fi

# --- Step 3: Full benchmark sweep ---
echo "[3/5] Running full benchmark sweep (this takes ~2-3 hours)..."
echo "      Experiments: Q2_K/Q3_K_M/Q4_K_M/Q6_K/Q8_0 × ctx 256/512/1024 × 3 prompts × 5 trials"
echo "      Plus F16 (expected OOM)"
echo "      Keep device connected, screen plugged in (or at least charging)"
echo ""

python3 "$SCRIPT_DIR/benchmark_runner.py" --all
echo ""

# --- Step 4: Validate results ---
echo "[4/5] Validating all results..."
LATEST_RUN=$(ls -t "$PROJECT_ROOT/results/run-"*.jsonl 2>/dev/null | head -1)
if [ -z "$LATEST_RUN" ]; then
    echo "WARNING: No run-*.jsonl file found. Benchmark may have failed."
else
    python3 "$SCRIPT_DIR/validate_results.py" "$LATEST_RUN"
    echo "  Validation passed ✓"
fi
echo ""

# --- Step 5: Generate figures ---
echo "[5/5] Generating figures from real results..."
if [ -n "$LATEST_RUN" ]; then
    python3 "$PROJECT_ROOT/analysis/generate_figures.py" "$LATEST_RUN"
    echo ""
    echo "Figures saved to: $PROJECT_ROOT/figures/"
    ls "$PROJECT_ROOT/figures/"
fi
echo ""

echo "╔══════════════════════════════════════════════════════════╗"
echo "║   PIPELINE COMPLETE                                      ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Results:  $LATEST_RUN"
echo "Figures:  $PROJECT_ROOT/figures/"
echo ""
echo "Next: Review figures/ and update the report."
