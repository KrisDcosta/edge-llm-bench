#!/bin/bash
#
# M4 Mac CPU Benchmark Script (Comparison baseline)
# Benchmarks all 7 GGUF variants on M4 Mac using CPU ONLY (no Metal GPU)
# Run from 291_EAI directory: bash scripts/benchmark_m4_mac_cpu.sh
#
# Use this to compare CPU vs GPU performance on the same M4 hardware

set -e

# Configuration
MODELS_DIR="local-models/llama3_2_3b_gguf"
RESULTS_DIR="results/m4_mac_cpu_$(date +%Y%m%d_%H%M%S)"
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
echo "M4 Mac CPU Benchmark (GPU disabled for comparison)"
echo "Start Time: $TIMESTAMP"
echo "Models: $MODELS_DIR"
echo "Results: $RESULTS_DIR"
echo "Variants: ${VARIANTS[@]}"
echo "Contexts: ${CTX_SIZES[@]}"
echo "Trials per config: $NUM_TRIALS"
echo "Note: -ngl 0 disables GPU, forces CPU-only computation"
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
    echo "📊 Benchmarking: $VARIANT (CPU only)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    for CTX in "${CTX_SIZES[@]}"; do
        echo ""
        echo "  Context: $CTX tokens | Trials: $NUM_TRIALS"

        # Create JSONL output file for this config
        OUTPUT_FILE="$RESULTS_DIR/m4_cpu_${VARIANT}_ctx${CTX}.jsonl"
        > "$OUTPUT_FILE"  # Clear file

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$((CURRENT_RUN + 1))
            PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))

            # Run benchmark with timeout wrapper
            # Save output to temp file, kill after timeout to avoid interactive mode
            # CPU will be slower, so use 30 second timeout
            BENCH_TEMP="/tmp/bench_$$_${VARIANT}_${CTX}_${TRIAL}.txt"
            llama-cli \
                -m "$MODEL_PATH" \
                -c "$CTX" \
                -n "$OUTPUT_TOKENS" \
                -p "$PROMPT" \
                -t 4 \
                -ngl 0 \
                > "$BENCH_TEMP" 2>&1 &
            LLAMA_PID=$!

            # Wait up to 30 seconds for inference to complete
            for i in {1..30}; do
                if ! kill -0 $LLAMA_PID 2>/dev/null; then
                    break
                fi
                sleep 1
            done

            # Kill if still running
            kill -9 $LLAMA_PID 2>/dev/null || true
            wait $LLAMA_PID 2>/dev/null || true

            # Read output
            BENCH_OUTPUT=$(cat "$BENCH_TEMP")
            rm -f "$BENCH_TEMP"

            # Extract Generation TPS from output: [ Prompt: XX.X t/s | Generation: YY.Y t/s ]
            # We want the Generation rate (decoding speed), not Prompt rate (encoding speed)
            TPS=$(echo "$BENCH_OUTPUT" | grep -oE "Generation: [0-9]+\.[0-9]+" | cut -d: -f2 | tr -d ' ' || echo "0")

            # Fallback: if Generation not found, try last t/s value
            if [ -z "$TPS" ] || [ "$TPS" = "0" ]; then
                TPS=$(echo "$BENCH_OUTPUT" | grep -oE "[0-9]+\.[0-9]+ t/s" | tail -1 | cut -d' ' -f1 || echo "0")
            fi

            # Final fallback: any decimal number
            if [ -z "$TPS" ] || [ "$TPS" = "0" ]; then
                TPS=$(echo "$BENCH_OUTPUT" | grep -oE "[0-9]+\.[0-9]+" | tail -1 || echo "0")
            fi

            # Create result record
            RESULT=$(cat <<EOF
{
  "variant": "$VARIANT",
  "context_length": $CTX,
  "trial": $TRIAL,
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "device": "M4 Mac",
  "backend": "CPU",
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
echo "✅ CPU Benchmark Complete!"
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
echo "  1. Compare GPU vs CPU: diff <(ls results/m4_mac_metal_*/m4_*.jsonl) <(ls results/m4_mac_cpu_*/m4_cpu_*.jsonl)"
echo "  2. Generate comparison: python3 analysis/compare_gpu_vs_cpu.py results/m4_mac_metal_*/ results/m4_mac_cpu_*/"
echo "==================================================================="
