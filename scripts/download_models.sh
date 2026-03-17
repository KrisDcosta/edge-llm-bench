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
# Compatible with bash 3.2+ (macOS default)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEST_DIR="$PROJECT_ROOT/local-models/llama3_2_3b_gguf"

BARTOWSKI="https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main"
UNSLOTH="https://huggingface.co/unsloth/Llama-3.2-3B-Instruct-GGUF/resolve/main"

# Returns "BASE_URL FILENAME" for a given variant (bash 3.2 compatible — no declare -A)
get_variant_info() {
    case "$1" in
        Q2_K)   echo "$UNSLOTH  Llama-3.2-3B-Instruct-Q2_K.gguf" ;;
        Q3_K_M) echo "$UNSLOTH  Llama-3.2-3B-Instruct-Q3_K_M.gguf" ;;
        Q4_K_S) echo "$BARTOWSKI  Llama-3.2-3B-Instruct-Q4_K_S.gguf" ;;
        Q4_K_M) echo "$BARTOWSKI  Llama-3.2-3B-Instruct-Q4_K_M.gguf" ;;
        Q5_K_M) echo "$BARTOWSKI  Llama-3.2-3B-Instruct-Q5_K_M.gguf" ;;
        Q6_K)   echo "$BARTOWSKI  Llama-3.2-3B-Instruct-Q6_K.gguf" ;;
        Q8_0)   echo "$BARTOWSKI  Llama-3.2-3B-Instruct-Q8_0.gguf" ;;
        F16)    echo "$BARTOWSKI  Llama-3.2-3B-Instruct-f16.gguf" ;;
        *)      echo "" ;;
    esac
}

# 7 research variants (ordered by bits-per-weight)
FEASIBLE_VARIANTS="Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"

mkdir -p "$DEST_DIR"

download_variant() {
    local variant="$1"
    local info
    info="$(get_variant_info "$variant")"

    if [ -z "$info" ]; then
        echo "ERROR: Unknown variant '$variant'. Known: $FEASIBLE_VARIANTS F16"
        return 1
    fi

    local base_url filename url dest
    base_url="$(echo "$info" | awk '{print $1}')"
    filename="$(echo "$info" | awk '{print $2}')"
    url="$base_url/$filename"
    dest="$DEST_DIR/$variant.gguf"

    if [ -f "$dest" ]; then
        echo "[$variant] Already exists: $(du -sh "$dest" | cut -f1)  →  $dest"
        return 0
    fi

    echo "[$variant] Downloading $filename ..."
    echo "  URL : $url"
    echo "  Dest: $dest"

    # -C - resumes interrupted downloads; --retry 5 handles transient failures
    if curl -fSL --retry 5 --retry-delay 10 -C - "$url" -o "$dest"; then
        local size hash
        size="$(du -sh "$dest" | cut -f1)"
        hash="$(shasum -a 256 "$dest" | cut -c1-16)"
        echo "[$variant] Done: $size   SHA256: ${hash}..."
    else
        echo "[$variant] FAILED — removing partial file"
        rm -f "$dest"
        return 1
    fi
}

# ── Parse arguments ────────────────────────────────────────────────────────────

if [ $# -eq 0 ]; then
    echo "Usage: $0 [VARIANT... | all]"
    echo "Available: $FEASIBLE_VARIANTS  (also F16 but unusable on 6 GB)"
    echo ""
    echo "New variants: Q4_K_S (~1.8 GB) and Q5_K_M (~2.2 GB)"
    exit 1
fi

targets=""
for arg in "$@"; do
    if [ "$arg" = "all" ]; then
        targets="$FEASIBLE_VARIANTS"
        break
    else
        targets="$targets $arg"
    fi
done
targets="${targets# }"  # trim leading space

target_count=0
for v in $targets; do target_count=$((target_count + 1)); done

echo "=== Downloading $target_count GGUF variant(s) ==="
echo "Destination: $DEST_DIR"
echo ""

failed=0
for v in $targets; do
    download_variant "$v" || failed=$((failed + 1))
    echo ""
done

echo "=== Done === ($target_count attempted, $failed failed)"
echo ""
echo "Next — push models to device:"
for v in $targets; do
    local_path="$DEST_DIR/$v.gguf"
    device_path="/data/local/tmp/Llama-3.2-3B-Instruct-$v.gguf"
    [ -f "$local_path" ] && echo "  adb push \"$local_path\" \"$device_path\""
done
echo ""
echo "Or use the helper script:"
echo "  ./scripts/push_models_to_device.sh all"
