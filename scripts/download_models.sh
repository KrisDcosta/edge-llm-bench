#!/usr/bin/env bash
# Download Llama 3.2 3B GGUF model variants from HuggingFace.
#
# Usage:
#   ./scripts/download_models.sh [VARIANT...]
#
# Examples:
#   ./scripts/download_models.sh Q4_K_M             # download one variant
#   ./scripts/download_models.sh Q2_K Q4_K_M Q6_K   # download multiple
#   ./scripts/download_models.sh all                  # download all feasible variants
#
# Models saved to: local-models/llama3_2_3b_gguf/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST_DIR="$PROJECT_ROOT/local-models/llama3_2_3b_gguf"
HF_REPO="bartowski/Llama-3.2-3B-Instruct-GGUF"
BASE_URL="https://huggingface.co/$HF_REPO/resolve/main"

declare -A VARIANTS
VARIANTS["Q2_K"]="Llama-3.2-3B-Instruct-Q2_K.gguf"
VARIANTS["Q3_K_M"]="Llama-3.2-3B-Instruct-Q3_K_M.gguf"
VARIANTS["Q4_K_M"]="Llama-3.2-3B-Instruct-Q4_K_M.gguf"
VARIANTS["Q6_K"]="Llama-3.2-3B-Instruct-Q6_K.gguf"
VARIANTS["Q8_0"]="Llama-3.2-3B-Instruct-Q8_0.gguf"

FEASIBLE_VARIANTS=("Q2_K" "Q3_K_M" "Q4_K_M" "Q6_K" "Q8_0")

mkdir -p "$DEST_DIR"

download_variant() {
    local variant="$1"
    local filename="${VARIANTS[$variant]:-}"
    if [ -z "$filename" ]; then
        echo "ERROR: Unknown variant '$variant'"
        return 1
    fi

    local dest="$DEST_DIR/$variant.gguf"
    local url="$BASE_URL/$filename"

    if [ -f "$dest" ]; then
        echo "[$variant] Already exists: $dest ($(du -sh "$dest" | cut -f1))"
        return 0
    fi

    echo "[$variant] Downloading $filename..."
    echo "  URL: $url"
    echo "  Dest: $dest"

    # Use -C - to resume interrupted downloads
    curl -fSL --retry 5 --retry-delay 10 -C - "$url" -o "$dest" 2>&1

    if [ $? -eq 0 ] && [ -f "$dest" ]; then
        size=$(du -sh "$dest" | cut -f1)
        hash=$(shasum -a 256 "$dest" | cut -c1-16)
        echo "[$variant] Done: $size  SHA256: $hash..."
        # Update manifest
        echo "  Update artifacts/manifest.yaml with sha256: $hash for $variant"
    else
        echo "[$variant] FAILED"
        rm -f "$dest"
        return 1
    fi
}

# Parse arguments
if [ $# -eq 0 ]; then
    echo "Usage: $0 [VARIANT... | all]"
    echo "Available: ${!VARIANTS[*]}"
    exit 1
fi

targets=()
for arg in "$@"; do
    if [ "$arg" = "all" ]; then
        targets=("${FEASIBLE_VARIANTS[@]}")
        break
    else
        targets+=("$arg")
    fi
done

echo "=== Downloading ${#targets[@]} GGUF variant(s) ==="
echo "Destination: $DEST_DIR"
echo ""

failed=0
for v in "${targets[@]}"; do
    download_variant "$v" || ((failed++))
done

echo ""
echo "=== Done === (${#targets[@]} attempted, $failed failed)"
echo ""
echo "Next: push models to device:"
for v in "${targets[@]}"; do
    local_path="$DEST_DIR/$v.gguf"
    device_path="/data/local/tmp/Llama-3.2-3B-Instruct-$v.gguf"
    [ -f "$local_path" ] && echo "  adb push $local_path $device_path"
done
