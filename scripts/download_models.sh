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
# Primary repo: bartowski (Q4_K_M, Q6_K, Q8_0, f16)
# Fallback repo: unsloth (Q2_K, Q3_K_M — not in bartowski)
BARTOWSKI_URL="https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main"
UNSLOTH_URL="https://huggingface.co/unsloth/Llama-3.2-3B-Instruct-GGUF/resolve/main"

# Map: variant → "URL|filename" (| separator)
declare -A VARIANT_URLS
VARIANT_URLS["Q2_K"]="$UNSLOTH_URL|Llama-3.2-3B-Instruct-Q2_K.gguf"
VARIANT_URLS["Q3_K_M"]="$UNSLOTH_URL|Llama-3.2-3B-Instruct-Q3_K_M.gguf"
VARIANT_URLS["Q4_K_M"]="$BARTOWSKI_URL|Llama-3.2-3B-Instruct-Q4_K_M.gguf"
VARIANT_URLS["Q6_K"]="$BARTOWSKI_URL|Llama-3.2-3B-Instruct-Q6_K.gguf"
VARIANT_URLS["Q8_0"]="$BARTOWSKI_URL|Llama-3.2-3B-Instruct-Q8_0.gguf"
VARIANT_URLS["F16"]="$BARTOWSKI_URL|Llama-3.2-3B-Instruct-f16.gguf"

FEASIBLE_VARIANTS=("Q2_K" "Q3_K_M" "Q4_K_M" "Q6_K" "Q8_0")
# VARIANTS map for backward compatibility
declare -A VARIANTS
for key in "${!VARIANT_URLS[@]}"; do
    VARIANTS["$key"]="${VARIANT_URLS[$key]##*|}"
done

mkdir -p "$DEST_DIR"

download_variant() {
    local variant="$1"
    local url_and_file="${VARIANT_URLS[$variant]:-}"
    if [ -z "$url_and_file" ]; then
        echo "ERROR: Unknown variant '$variant'"
        return 1
    fi

    local base_url="${url_and_file%%|*}"
    local filename="${url_and_file##*|}"
    local dest="$DEST_DIR/$variant.gguf"
    local url="$base_url/$filename"

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
