#!/bin/bash
# ================================================================
# kv_cache_cliff_sweep.sh — Granular KV-cache cliff characterization
# M4 Mac Metal GPU
#
# Sweeps ctx 1200–1600 at fine granularity to pinpoint the exact
# cliff location per variant. Captures powermetrics for bandwidth.
# Run from edge-llm-bench directory: bash scripts/kv_cache_cliff_sweep.sh
# ================================================================

set -e

MODELS_DIR="local-models/llama3_2_3b_gguf"
RESULTS_DIR="results/kv_cache_cliff_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"

# Fine-grained context sweep around the known cliff at ~1400-1500
CTX_SIZES=(1024 1100 1200 1250 1300 1350 1400 1450 1500 1550 1600 1800 2048)
# Focus on the variants that show the cliff most clearly
VARIANTS=(Q4_K_M Q6_K Q8_0)
NUM_TRIALS=5
OUTPUT_TOKENS=64
PROMPT="Explain the significance of the transformer architecture in modern natural language processing and its impact"

TIMESTAMP=$(date +%Y-%m-%dT%H:%M:%S)
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0

echo "==================================================================="
echo "KV-Cache Cliff Granularity Sweep — M4 Mac Metal GPU"
echo "Start: $TIMESTAMP"
echo "Variants: ${VARIANTS[*]}"
echo "Contexts: ${CTX_SIZES[*]}"
echo "Trials: $NUM_TRIALS | Total runs: $TOTAL_RUNS"
echo "Results: $RESULTS_DIR"
echo "==================================================================="

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="$MODELS_DIR/Llama-3.2-3B-Instruct-${VARIANT}.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        echo "⚠️  SKIP: $MODEL_PATH not found"
        continue
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📊 Variant: $VARIANT"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    OUTPUT_FILE="$RESULTS_DIR/cliff_${VARIANT}.jsonl"
    > "$OUTPUT_FILE"

    for CTX in "${CTX_SIZES[@]}"; do
        echo "  Context $CTX tokens..."

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$((CURRENT_RUN + 1))
            PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))

            BENCH_TEMP="/tmp/cliff_$$_${VARIANT}_${CTX}_${TRIAL}.txt"

            llama-cli \
                -m "$MODEL_PATH" \
                -c "$CTX" \
                -n "$OUTPUT_TOKENS" \
                -p "$PROMPT" \
                -t 4 \
                > "$BENCH_TEMP" 2>&1 &
            LLAMA_PID=$!

            # Wait up to 30 seconds
            for i in {1..30}; do
                if ! kill -0 $LLAMA_PID 2>/dev/null; then break; fi
                sleep 1
            done
            kill -9 $LLAMA_PID 2>/dev/null || true
            wait $LLAMA_PID 2>/dev/null || true

            BENCH_OUTPUT=$(cat "$BENCH_TEMP")
            rm -f "$BENCH_TEMP"

            # Extract both prefill TPS and decode TPS
            PREFILL_TPS=$(echo "$BENCH_OUTPUT" | grep -oE "Prompt: [0-9]+\.[0-9]+" | cut -d' ' -f2 | tr -d ' ' || echo "0")
            DECODE_TPS=$(echo "$BENCH_OUTPUT" | grep -oE "Generation: [0-9]+\.[0-9]+" | cut -d' ' -f2 | tr -d ' ' || echo "0")

            # Fallback
            if [ -z "$DECODE_TPS" ] || [ "$DECODE_TPS" = "0" ]; then
                DECODE_TPS=$(echo "$BENCH_OUTPUT" | grep -oE "[0-9]+\.[0-9]+ t/s" | tail -1 | cut -d' ' -f1 || echo "0")
            fi

            cat >> "$OUTPUT_FILE" << JSONEOF
{"variant":"$VARIANT","context":$CTX,"trial":$TRIAL,"prefill_tps":${PREFILL_TPS:-0},"decode_tps":${DECODE_TPS:-0},"ts":"$(date -u +%Y-%m-%dT%H:%M:%SZ)"}
JSONEOF

            echo -n "    [ctx=$CTX trial=$TRIAL $PROGRESS%] decode=$DECODE_TPS t/s"
            if [ -n "$PREFILL_TPS" ] && [ "$PREFILL_TPS" != "0" ]; then
                echo " prefill=$PREFILL_TPS t/s"
            else
                echo ""
            fi
        done
    done

    echo "  ✅ Saved: $OUTPUT_FILE"
done

echo ""
echo "==================================================================="
echo "✅ KV-Cache Cliff Sweep Complete!"
echo "Results: $RESULTS_DIR"

# Print cliff analysis
echo ""
echo "=== CLIFF ANALYSIS ==="
python3 << 'PYEOF'
import json, os, glob

result_files = sorted(glob.glob("results/kv_cache_cliff_*/*.jsonl"))
if not result_files:
    print("No results files found yet")
    exit()

for fpath in result_files:
    variant = os.path.basename(fpath).replace("cliff_","").replace(".jsonl","")
    data = []
    with open(fpath) as f:
        for line in f:
            line = line.strip()
            if line:
                try: data.append(json.loads(line))
                except: pass

    if not data: continue

    from collections import defaultdict
    ctx_tps = defaultdict(list)
    for d in data:
        if d.get("decode_tps", 0) > 0:
            ctx_tps[d["context"]].append(d["decode_tps"])

    print(f"\n{variant}:")
    prev_tps = None
    for ctx in sorted(ctx_tps.keys()):
        vals = ctx_tps[ctx]
        avg = sum(vals)/len(vals)
        drop = ""
        if prev_tps:
            pct = (prev_tps - avg) / prev_tps * 100
            if pct > 10:
                drop = f" ← DROP {pct:.0f}%"
        print(f"  ctx={ctx:4d}: {avg:.1f} t/s (n={len(vals)}){drop}")
        prev_tps = avg
PYEOF

echo "==================================================================="
