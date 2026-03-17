#!/bin/bash
#
# M4 Mac Metal GPU Benchmark Script
# Benchmarks all 7 GGUF variants on M4 Mac using Metal backend
# Run from 291_EAI directory: bash scripts/benchmark_m4_mac.sh
#

set -e

# Configuration
MODELS_DIR="local-models/llama3_2_3b_gguf"
RESULTS_DIR="results/m4_mac_metal_$(date +%Y%m%d_%H%M%S)"
TIMESTAMP=$(date +%Y-%m-%dT%H:%M:%S)

# Parameters
VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CTX_SIZES=(256 512 1024 2048)
NUM_TRIALS=15
OUTPUT_TOKENS=128
PROMPT="The future of artificial intelligence is"

# Check if models directory exists
if [ ! -d "$MODELS_DIR" ]; then
    echo "ERROR: Models directory not found: $MODELS_DIR"
    echo "Make sure you're in the 291_EAI directory"
    exit 1
fi

# Create results directory
mkdir -p "$RESULTS_DIR"
echo "Results will be saved to: $RESULTS_DIR"
echo ""

# Check if llama-cli is available
if ! command -v llama-cli &> /dev/null; then
    echo "ERROR: llama-cli not found. Install with: brew install llama.cpp"
    exit 1
fi

echo "==================================================================="
echo "M4 Mac Metal Benchmark"
echo "Start Time: $TIMESTAMP"
echo "Models: $MODELS_DIR"
echo "Results: $RESULTS_DIR"
echo "Variants: ${VARIANTS[@]}"
echo "Contexts: ${CTX_SIZES[@]}"
echo "Trials per config: $NUM_TRIALS"
echo "==================================================================="
echo ""

# Track progress
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0

# Main benchmark loop
for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="$MODELS_DIR/Llama-3.2-3B-Instruct-${VARIANT}.gguf"

    # Check if model exists
    if [ ! -f "$MODEL_PATH" ]; then
        echo "⚠️  SKIP: $MODEL_PATH not found"
        continue
    fi

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Benchmarking: $VARIANT"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for CTX in "${CTX_SIZES[@]}"; do
        echo ""
        echo "  Context: $CTX tokens | Trials: $NUM_TRIALS"

        # Create JSONL output file for this config
        OUTPUT_FILE="$RESULTS_DIR/m4_${VARIANT}_ctx${CTX}.jsonl"
        > "$OUTPUT_FILE"  # Clear file

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$((CURRENT_RUN + 1))
            PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))

            # Run benchmark and capture output
            BENCH_OUTPUT=$(llama-cli \
                -m "$MODEL_PATH" \
                -c "$CTX" \
                -n "$OUTPUT_TOKENS" \
                -p "$PROMPT" \
                -t 4 \
                --log-format json \
                2>/dev/null || echo "{}")

            # Extract TPS if available, otherwise estimate
            TPS=$(echo "$BENCH_OUTPUT" | grep -o '"tokens_per_second_tokens":[0-9.]*' | cut -d: -f2 || echo "0")
            if [ -z "$TPS" ] || [ "$TPS" = "0" ]; then
                # Fallback: parse from text output if JSON unavailable
                TPS=$(echo "$BENCH_OUTPUT" | grep -i "tokens/s" | head -1 | grep -o '[0-9.]*' | head -1 || echo "0")
            fi

            # Create result record
            RESULT=$(cat <<EOF
{
  "variant": "$VARIANT",
  "context_length": $CTX,
  "trial": $TRIAL,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "device": "M4 Mac",
  "backend": "Metal",
  "model_size_gb": 3.2,
  "output_tokens": $OUTPUT_TOKENS,
  "decode_tps": $TPS,
  "raw_output": $(echo "$BENCH_OUTPUT" | jq -R .)
}
EOF
            )

            echo "$RESULT" >> "$OUTPUT_FILE"

            # Progress indicator
            echo -n "    Trial $TRIAL/$NUM_TRIALS ($PROGRESS%) "
            if [ "$TPS" != "0" ]; then
                echo "✓ $TPS tok/s"
            else
                echo "⚠ (check output)"
            fi
        done

        # Summary for this context
        echo "  ✓ Completed: $OUTPUT_FILE"
    done

    echo ""
done

echo ""
echo "==================================================================="
echo "✅ Benchmark Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Results saved to: $RESULTS_DIR"
echo "Total runs: $CURRENT_RUN / $TOTAL_RUNS"
echo "End time: $(date +%Y-%m-%dT%H:%M:%S)"
echo ""

# List all result files
echo "Result files:"
ls -lh "$RESULTS_DIR"/*.jsonl 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'

echo ""
echo "Next steps:"
echo "  1. Check results: cat $RESULTS_DIR/m4_*.jsonl | head -5"
echo "  2. Copy to results: cp -r $RESULTS_DIR results/"
echo "  3. Analyze: python3 analysis/generate_figures.py results/"
echo "==================================================================="
