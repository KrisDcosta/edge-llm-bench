#!/usr/bin/env bash
# Push all GGUF model variants + llama.cpp binaries to Android device.
#
# Usage:
#   ./scripts/push_models_to_device.sh [VARIANT...]
#   ./scripts/push_models_to_device.sh all        # push everything
#   ./scripts/push_models_to_device.sh bins        # push binaries only
#   ./scripts/push_models_to_device.sh Q4_K_M     # push one model
#
# Requires: adb connected, llama.cpp built at vendor/llama.cpp/build-android/
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/vendor/llama.cpp/build-android/bin"
MODEL_DIR="$PROJECT_ROOT/local-models/llama3_2_3b_gguf"
DEVICE_DIR="/data/local/tmp"       # used by benchmark pipeline + app auto-discovery
DEVICE_DOWNLOAD="/sdcard/Download" # visible to Android file picker as fallback

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

# Verify device connected
DEVICE_LINE=$("$ADB" devices | grep -v "^List" | grep "device$" | head -1 || true)
if [ -z "$DEVICE_LINE" ]; then
    echo "ERROR: No Android device connected."
    echo "  1. Connect Pixel 6a via USB"
    echo "  2. Enable USB debugging (Settings > Developer options > USB debugging)"
    echo "  3. Accept the 'Allow USB debugging' prompt on device"
    exit 1
fi
echo "Device found: $DEVICE_LINE"
echo ""

push_bins() {
    echo "=== Pushing binaries ==="
    if [ ! -d "$BUILD_DIR" ]; then
        echo "ERROR: Build dir not found at $BUILD_DIR"
        echo "Run: ./scripts/build_llamacpp_android.sh"
        exit 1
    fi

    for bin_file in "$BUILD_DIR/llama-completion" "$BUILD_DIR/llama-bench"; do
        if [ -f "$bin_file" ]; then
            fname=$(basename "$bin_file")
            echo -n "  $fname ... "
            "$ADB" push "$bin_file" "$DEVICE_DIR/$fname"
            "$ADB" shell chmod +x "$DEVICE_DIR/$fname"
            echo "OK"
        fi
    done

    echo -n "  shared libraries ... "
    for so_file in "$BUILD_DIR"/*.so; do
        [ -f "$so_file" ] || continue
        fname=$(basename "$so_file")
        "$ADB" push "$so_file" "$DEVICE_DIR/$fname"
    done
    echo "OK"
    echo ""
}

push_model() {
    local variant="$1"
    local local_path="$MODEL_DIR/$variant.gguf"
    local device_path="$DEVICE_DIR/Llama-3.2-3B-Instruct-$variant.gguf"

    if [ ! -f "$local_path" ]; then
        echo "  [$variant] SKIP — not found at $local_path"
        return 0
    fi

    # Check if already on device (by size)
    local local_size
    local_size=$(du -k "$local_path" | cut -f1)
    local device_size
    device_size=$("$ADB" shell "stat -c %s '$device_path' 2>/dev/null || echo 0" 2>/dev/null | tr -d '\r' || echo "0")
    device_size_kb=$((device_size / 1024))

    if [ "$device_size_kb" -gt 0 ] && [ "$device_size_kb" -ge "$((local_size - 100))" ]; then
        echo "  [$variant] Already on device ($(du -sh "$local_path" | cut -f1))"
        return 0
    fi

    echo -n "  [$variant] Pushing $(du -sh "$local_path" | cut -f1) → $device_path ... "
    "$ADB" push "$local_path" "$device_path"
    echo "OK"

    # Also copy to /sdcard/Download/ so Android file picker can see it
    # (the app's auto-discovery reads from /data/local/tmp/ directly,
    #  but the file picker Browse button needs the file in user-accessible storage)
    local download_path="$DEVICE_DOWNLOAD/Llama-3.2-3B-Instruct-$variant.gguf"
    echo -n "  [$variant] Symlinking to Downloads (for file picker) ... "
    "$ADB" shell "cp '$device_path' '$download_path' 2>/dev/null || true" && echo "OK" || echo "SKIP (storage not writable)"
}

# --- Parse arguments ---
if [ $# -eq 0 ]; then
    echo "Usage: $0 [bins | all | VARIANT...]"
    echo "  bins      — push binaries and .so files only"
    echo "  all       — push everything (bins + all downloaded models)"
    echo "  VARIANT   — push specific model(s): Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"
    exit 1
fi

# All 7 research variants + F16 (OOM expected but needed to document RQ5)
# push_model() skips gracefully if local file doesn't exist yet
FEASIBLE_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0 F16)

push_bins_needed=false
variants_to_push=()

for arg in "$@"; do
    case "$arg" in
        bins)
            push_bins_needed=true
            ;;
        all)
            push_bins_needed=true
            variants_to_push=("${FEASIBLE_VARIANTS[@]}")
            break
            ;;
        *)
            variants_to_push+=("$arg")
            ;;
    esac
done

# Always push bins if pushing models (they may have changed)
if [ "${#variants_to_push[@]}" -gt 0 ]; then
    push_bins_needed=true
fi

if $push_bins_needed; then
    push_bins
fi

if [ "${#variants_to_push[@]}" -gt 0 ]; then
    echo "=== Pushing models ==="
    for v in "${variants_to_push[@]}"; do
        push_model "$v"
    done
    echo ""
fi

echo "=== Done ==="
echo ""
echo "Verify binaries work:"
echo "  $ADB shell 'LD_LIBRARY_PATH=$DEVICE_DIR $DEVICE_DIR/llama-completion --version'"
echo ""
echo "Run smoke test:"
echo "  python3 scripts/benchmark_runner.py --smoke"
echo ""
echo "Run full benchmark:"
echo "  python3 scripts/benchmark_runner.py --all"
