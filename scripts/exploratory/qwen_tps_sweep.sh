#!/bin/bash
# Qwen 2.5 1.5B GGUF K-quant TPS sweep on M4 Mac Metal GPU
# Downloads models from HuggingFace and runs throughput benchmark

set -e

MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
RESULTS_DIR="results/qwen_tps_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

echo "=== Qwen 2.5 1.5B TPS Benchmark Setup ==="
echo "Models directory: $MODELS_DIR"
echo "Results will be saved to: $RESULTS_DIR"
echo ""

# Benchmark Qwen 2.5 1.5B GGUF variants (already downloaded)
VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

echo "Verifying Qwen 2.5 1.5B GGUF variants..."
for VARIANT in "${VARIANTS[@]}"; do
    MODEL_FILE="Qwen2.5-1.5B-Instruct-${VARIANT}.gguf"
    MODEL_PATH="$MODELS_DIR/$MODEL_FILE"

    if [ -f "$MODEL_PATH" ]; then
        SIZE=$(du -h "$MODEL_PATH" | cut -f1)
        echo "  ✓ $MODEL_FILE ($SIZE)"
    else
        echo "  ✗ $MODEL_FILE not found"
    fi
done

echo ""
echo "=== Running TPS Benchmark ==="
echo "Contexts: 256, 512, 1024, 2048 — 5 trials each"
echo "Output: 128 tokens per trial (20s timeout)"
echo ""

# Run TPS benchmark for each variant
for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="$MODELS_DIR/Qwen2.5-1.5B-Instruct-${VARIANT}.gguf"

    if [ ! -f "$MODEL_PATH" ]; then
        echo "⚠️  SKIP: $VARIANT not found ($MODEL_PATH)"
        continue
    fi
    
    echo "📊 Benchmarking: $VARIANT"
    OUTPUT_FILE="$RESULTS_DIR/qwen_${VARIANT}_tps.jsonl"
    > "$OUTPUT_FILE"
    
    for CTX in 256 512 1024 2048; do
        for TRIAL in {1..5}; do
            BENCH_TEMP="/tmp/qwen_bench_${VARIANT}_ctx${CTX}_trial${TRIAL}.txt"
            
            llama-cli \
                -m "$MODEL_PATH" \
                -c "$CTX" \
                -n 128 \
                -p "The future of AI is" \
                -t 4 \
                > "$BENCH_TEMP" 2>&1 &
            LLAMA_PID=$!
            
            # Wait 20s (Qwen 1.5B is faster than Llama 3.2 3B)
            for i in {1..20}; do
                if ! kill -0 $LLAMA_PID 2>/dev/null; then break; fi
                sleep 1
            done
            kill -9 $LLAMA_PID 2>/dev/null || true
            
            BENCH_OUTPUT=$(cat "$BENCH_TEMP")
            rm -f "$BENCH_TEMP"
            
            # Extract Generation TPS
            TPS=$(echo "$BENCH_OUTPUT" | grep -oE "Generation: [0-9]+\.[0-9]+" | cut -d: -f2 | tr -d ' ' || echo "0")
            if [ -z "$TPS" ] || [ "$TPS" = "0" ]; then
                TPS=$(echo "$BENCH_OUTPUT" | grep -oE "[0-9]+\.[0-9]+ t/s" | tail -1 | cut -d' ' -f1 || echo "0")
            fi
            
            RESULT="{\"variant\":\"$VARIANT\",\"context\":$CTX,\"trial\":$TRIAL,\"decode_tps\":$TPS,\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}"
            echo "$RESULT" >> "$OUTPUT_FILE"
            
            echo "  ctx=$CTX trial=$TRIAL: $TPS t/s"
        done
    done
done

echo ""
echo "✅ Qwen 2.5 TPS Benchmark Complete!"
echo "Results: $RESULTS_DIR"
