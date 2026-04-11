#!/usr/bin/env bash
# run_perplexity.sh — Run llama-perplexity on device for all GGUF variants.
#
# Measures WikiText-2 test perplexity per quantization level.
# Standard benchmark corpus (same as GPTQ/AWQ papers) — allows cross-paper comparison.
#
# Usage:
#   ./scripts/run_perplexity.sh              # all feasible variants (incl. F16)
#   ./scripts/run_perplexity.sh Q4_K_M       # one variant
#   ./scripts/run_perplexity.sh Q2_K Q4_K_M  # specific variants
#
# Prerequisites:
#   - data/wikitext2_sample.txt exists (run: python3 scripts/download_wikitext2.py)
#   - llama-perplexity binary pushed to /data/local/tmp/
#   - All GGUF models pushed to /data/local/tmp/
#   - adb connected (USB or WiFi)
#
# Output:
#   results/perplexity_scores.json — JSON keyed by variant with perplexity + status

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DEVICE_DIR="/data/local/tmp"
LLAMA_PPL="$DEVICE_DIR/llama-perplexity"
CORPUS_LOCAL="$PROJECT_ROOT/data/wikitext2_sample.txt"
CORPUS_DEVICE="$DEVICE_DIR/wikitext2_sample.txt"
OUTPUT_FILE="$PROJECT_ROOT/results/perplexity_scores.json"

# Find adb
ADB="${ADB:-}"
if [ -z "$ADB" ]; then
    if command -v adb &>/dev/null; then
        ADB="adb"
    elif [ -f "$HOME/Library/Android/sdk/platform-tools/adb" ]; then
        ADB="$HOME/Library/Android/sdk/platform-tools/adb"
    else
        echo "ERROR: adb not found. Add platform-tools to PATH or set ADB=/path/to/adb."
        exit 1
    fi
fi

# --- Verify prerequisites ---
echo "=== Perplexity Evaluation Setup ==="
echo ""

if [ ! -f "$CORPUS_LOCAL" ]; then
    echo "ERROR: WikiText-2 sample not found at $CORPUS_LOCAL"
    echo "Run: python3 scripts/download_wikitext2.py"
    exit 1
fi
CORPUS_BYTES=$(wc -c < "$CORPUS_LOCAL")
echo "  Corpus: $CORPUS_LOCAL ($CORPUS_BYTES bytes)"

if ! "$ADB" devices | grep -q "device$"; then
    echo "ERROR: No Android device connected."
    exit 1
fi

if ! "$ADB" shell "ls $LLAMA_PPL 2>/dev/null" | grep -q "llama-perplexity"; then
    echo "ERROR: llama-perplexity not found at $LLAMA_PPL on device."
    echo ""
    echo "Build it and push:"
    echo "  ./scripts/build_llamacpp_android.sh      # rebuild (includes llama-perplexity)"
    echo "  adb push vendor/llama.cpp/build-android/bin/llama-perplexity $DEVICE_DIR/"
    echo "  adb shell chmod +x $DEVICE_DIR/llama-perplexity"
    exit 1
fi
echo "  Binary: $LLAMA_PPL (found on device)"

echo -n "  Pushing corpus to device... "
"$ADB" push "$CORPUS_LOCAL" "$CORPUS_DEVICE" >/dev/null
echo "OK"
echo ""

# --- Determine variants to evaluate ---
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_M Q6_K Q8_0 F16)
if [ $# -gt 0 ]; then
    VARIANTS=("$@")
else
    VARIANTS=("${ALL_VARIANTS[@]}")
fi

echo "=== Running Perplexity Evaluation ==="
echo "  Variants: ${VARIANTS[*]}"
echo ""

# Temp file to collect results as newline-delimited key=value pairs
TMPFILE=$(mktemp /tmp/ppl_results.XXXXXX)
trap 'rm -f "$TMPFILE"' EXIT

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="$DEVICE_DIR/Llama-3.2-3B-Instruct-${VARIANT}.gguf"

    echo -n "  [$VARIANT] checking model on device... "
    if ! "$ADB" shell "ls $MODEL_PATH 2>/dev/null" | grep -q ".gguf"; then
        echo "SKIP (not found on device)"
        echo "${VARIANT}=null:skipped_not_on_device" >> "$TMPFILE"
        continue
    fi
    echo "found"

    # F16 needs a longer timeout; perplexity is one forward pass per token (no sampling)
    if [ "$VARIANT" = "F16" ]; then
        TIMEOUT=1800
        echo "  [$VARIANT] NOTE: F16 perplexity may take 15-30 minutes (forward pass per token, no generation)"
    else
        TIMEOUT=600
    fi

    echo -n "  [$VARIANT] running llama-perplexity (timeout=${TIMEOUT}s)... "

    PPL_CMD="LD_LIBRARY_PATH=$DEVICE_DIR $LLAMA_PPL -m $MODEL_PATH -f $CORPUS_DEVICE --seed 42 -t 4 2>&1"
    OUTPUT=""
    if OUTPUT=$("$ADB" shell "$PPL_CMD" 2>&1); then
        # Parse: "Final estimate: PPL = 8.1234 +/- 0.0456"
        PPL_VALUE=$(echo "$OUTPUT" | grep -oP "Final estimate: PPL = \K[0-9]+\.[0-9]+" | tail -1 || true)
        if [ -n "$PPL_VALUE" ]; then
            echo "PPL=$PPL_VALUE"
            echo "${VARIANT}=${PPL_VALUE}:success" >> "$TMPFILE"
        else
            echo "PARSE_FAIL"
            echo "  Last 5 lines of output:"
            echo "$OUTPUT" | tail -5 | sed 's/^/    /'
            echo "${VARIANT}=null:parse_failure" >> "$TMPFILE"
        fi
    else
        echo "TIMEOUT or ERROR"
        echo "${VARIANT}=null:timeout_or_error" >> "$TMPFILE"
    fi
done

echo ""
echo "=== Results Summary ==="
while IFS= read -r line; do
    VARIANT="${line%%=*}"
    REST="${line#*=}"
    PPL="${REST%%:*}"
    STATUS="${REST#*:}"
    printf "  %-10s  PPL=%-12s [%s]\n" "$VARIANT" "$PPL" "$STATUS"
done < "$TMPFILE"

# Write JSON via Python to handle null/float cleanly
echo ""
echo -n "Writing $OUTPUT_FILE... "
mkdir -p "$(dirname "$OUTPUT_FILE")"

python3 - "$TMPFILE" "$OUTPUT_FILE" "$CORPUS_BYTES" << 'PYEOF'
import json, sys
from pathlib import Path

tmpfile, output_file_str, corpus_bytes = sys.argv[1], sys.argv[2], int(sys.argv[3])
output_path = Path(output_file_str)

# Load existing results (to merge/update)
existing = {}
if output_path.exists():
    try:
        existing = json.loads(output_path.read_text())
    except Exception:
        pass

# Parse results from tmpfile
with open(tmpfile) as f:
    for raw_line in f:
        line = raw_line.strip()
        if not line:
            continue
        variant, rest = line.split("=", 1)
        ppl_str, status = rest.rsplit(":", 1)
        ppl = float(ppl_str) if ppl_str != "null" else None

        if variant not in existing:
            existing[variant] = {}
        existing[variant]["perplexity"] = ppl
        existing[variant]["perplexity_status"] = status
        existing[variant]["corpus"] = "wikitext2_sample"
        existing[variant]["corpus_bytes"] = corpus_bytes

output_path.write_text(json.dumps(existing, indent=2))
print(f"saved {len(existing)} variant(s) to {output_path}")
PYEOF

echo ""
echo "=== Perplexity evaluation complete ==="
echo "Output: $OUTPUT_FILE"
echo ""
echo "Next: python3 scripts/quality_eval.py --all"
