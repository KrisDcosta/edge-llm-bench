#!/usr/bin/env bash
# Build llama.cpp for Android ARM64
# Prerequisites:
#   1. Android NDK installed (install via Android Studio > SDK Manager > SDK Tools > NDK)
#   2. cmake installed (brew install cmake)
#   3. llama.cpp cloned in vendor/llama.cpp (git clone --depth 1 https://github.com/ggml-org/llama.cpp.git vendor/llama.cpp)
#
# Usage:
#   ./scripts/build_llamacpp_android.sh
#
# Output:
#   vendor/llama.cpp/build-android/bin/llama-cli  (ARM64 binary)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LLAMA_CPP_DIR="$PROJECT_ROOT/vendor/llama.cpp"

# --- Find Android NDK ---
ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"

# Try common NDK locations
NDK_DIR=""
if [ -d "$ANDROID_HOME/ndk" ]; then
    # Use the latest installed NDK version
    NDK_DIR=$(ls -d "$ANDROID_HOME/ndk"/*/ 2>/dev/null | sort -V | tail -1)
fi

if [ -z "$NDK_DIR" ] || [ ! -d "$NDK_DIR" ]; then
    echo "ERROR: Android NDK not found."
    echo ""
    echo "Install NDK via Android Studio:"
    echo "  1. Open Android Studio"
    echo "  2. Go to Settings > Languages & Frameworks > Android SDK > SDK Tools"
    echo "  3. Check 'NDK (Side by side)' and click Apply"
    echo ""
    echo "Or set ANDROID_NDK_HOME environment variable to your NDK path."
    exit 1
fi

# Allow override via env var
NDK_DIR="${ANDROID_NDK_HOME:-$NDK_DIR}"
TOOLCHAIN="$NDK_DIR/build/cmake/android.toolchain.cmake"

if [ ! -f "$TOOLCHAIN" ]; then
    echo "ERROR: NDK toolchain not found at: $TOOLCHAIN"
    exit 1
fi

echo "Using NDK: $NDK_DIR"
echo "Toolchain: $TOOLCHAIN"

# --- Check prerequisites ---
if [ ! -d "$LLAMA_CPP_DIR" ]; then
    echo "ERROR: llama.cpp not found at $LLAMA_CPP_DIR"
    echo "Clone it: git clone --depth 1 https://github.com/ggml-org/llama.cpp.git $LLAMA_CPP_DIR"
    exit 1
fi

command -v cmake >/dev/null 2>&1 || { echo "ERROR: cmake not found. Install: brew install cmake"; exit 1; }

# --- Build ---
BUILD_DIR="$LLAMA_CPP_DIR/build-android"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

echo ""
echo "=== Building llama.cpp for Android ARM64 ==="
echo ""

cmake -S "$LLAMA_CPP_DIR" -B "$BUILD_DIR" \
    -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN" \
    -DANDROID_ABI=arm64-v8a \
    -DANDROID_PLATFORM=android-26 \
    -DANDROID_STL=c++_shared \
    -DCMAKE_BUILD_TYPE=Release \
    -DGGML_OPENMP=OFF \
    -DGGML_LLAMAFILE=OFF \
    2>&1

cmake --build "$BUILD_DIR" --config Release -j$(sysctl -n hw.ncpu) -- llama-cli llama-bench 2>&1

# --- Verify output ---
LLAMA_CLI="$BUILD_DIR/bin/llama-cli"
LLAMA_BENCH="$BUILD_DIR/bin/llama-bench"

if [ -f "$LLAMA_CLI" ]; then
    echo ""
    echo "=== Build successful ==="
    echo "llama-cli: $LLAMA_CLI"
    file "$LLAMA_CLI"
    ls -lh "$LLAMA_CLI"
else
    echo "ERROR: llama-cli not found at expected location"
    echo "Check build output above for errors"
    exit 1
fi

if [ -f "$LLAMA_BENCH" ]; then
    echo "llama-bench: $LLAMA_BENCH"
    file "$LLAMA_BENCH"
fi

# --- Find libc++_shared.so ---
LIBCPP=$(find "$NDK_DIR" -name "libc++_shared.so" -path "*/arm64-v8a/*" | head -1)
if [ -n "$LIBCPP" ]; then
    echo "libc++_shared.so: $LIBCPP"
    cp "$LIBCPP" "$BUILD_DIR/bin/"
    echo "Copied to build dir for adb push"
else
    echo "WARNING: libc++_shared.so not found — may need to push it manually"
fi

echo ""
echo "=== Next steps ==="
echo "1. Push to device:"
echo "   adb push $LLAMA_CLI /data/local/tmp/"
echo "   adb push $BUILD_DIR/bin/libc++_shared.so /data/local/tmp/"
echo ""
echo "2. Push a GGUF model:"
echo "   adb push /path/to/model.gguf /data/local/tmp/"
echo ""
echo "3. Run on device:"
echo "   adb shell 'cd /data/local/tmp && LD_LIBRARY_PATH=. ./llama-cli -m model.gguf -p \"Hello\" -n 32'"
