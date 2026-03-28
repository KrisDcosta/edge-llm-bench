#!/bin/bash
# Download Qwen 2.5 1.5B GGUF variants and run M4 TPS sweep
set -e
MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
RESULTS_DIR="results/qwen_tps_$(date +%Y%m%d_%H%M%S)"
LOG="$RESULTS_DIR/../qwen_sweep.log"
mkdir -p "$MODELS_DIR" "$RESULTS_DIR"

VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CTX_SIZES=(256 512 1024 2048)
NUM_TRIALS=10
OUTPUT_TOKENS=128
PROMPT="The future of artificial intelligence is"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "========================================"
log "Qwen 2.5 1.5B TPS Sweep — M4 Mac Metal"
log "Step 1: Download models"
log "Step 2: Run TPS benchmark"
log "========================================"

# Step 1: Download models via huggingface_hub
log "Downloading Qwen2.5-1.5B-Instruct GGUF variants..."
python3 << 'PYEOF'
from huggingface_hub import hf_hub_download
import os, sys

repo = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
models_dir = "local-models/qwen2_5_1_5b_gguf"
os.makedirs(models_dir, exist_ok=True)

# Map our variant names to Qwen's file naming convention
variant_files = {
    "Q2_K":   "qwen2.5-1.5b-instruct-q2_k.gguf",
    "Q3_K_M": "qwen2.5-1.5b-instruct-q3_k_m.gguf",
    "Q4_K_S": "qwen2.5-1.5b-instruct-q4_k_s.gguf",
    "Q4_K_M": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
    "Q5_K_M": "qwen2.5-1.5b-instruct-q5_k_m.gguf",
    "Q6_K":   "qwen2.5-1.5b-instruct-q6_k.gguf",
    "Q8_0":   "qwen2.5-1.5b-instruct-q8_0.gguf",
}

for variant, filename in variant_files.items():
    dest = os.path.join(models_dir, f"Qwen2.5-1.5B-Instruct-{variant}.gguf")
    if os.path.exists(dest) and os.path.getsize(dest) > 100_000:
        print(f"  ✓ {variant} already exists ({os.path.getsize(dest)//1_000_000} MB)")
        continue
    try:
        print(f"  ⬇  Downloading {variant} ({filename})...", flush=True)
        path = hf_hub_download(
            repo_id=repo,
            filename=filename,
            local_dir=models_dir,
            local_dir_use_symlinks=False,
        )
        # Rename to our standard naming
        if path != dest:
            os.rename(path, dest)
        size_mb = os.path.getsize(dest) // 1_000_000
        print(f"  ✅ {variant} downloaded ({size_mb} MB) → {dest}")
    except Exception as e:
        print(f"  ⚠  {variant} failed: {e}")
        # Try bartowski mirror
        try:
            repo2 = "bartowski/Qwen2.5-1.5B-Instruct-GGUF"
            fn2 = f"Qwen2.5-1.5B-Instruct-{variant}.gguf"
            path = hf_hub_download(repo_id=repo2, filename=fn2,
                                   local_dir=models_dir, local_dir_use_symlinks=False)
            if path != dest:
                os.rename(path, dest)
            print(f"  ✅ {variant} downloaded from bartowski ({os.path.getsize(dest)//1_000_000} MB)")
        except Exception as e2:
            print(f"  ✗  {variant} failed both sources: {e2}")
PYEOF

log "Download phase complete. Starting TPS sweep..."

# Step 2: TPS benchmark (same logic as Llama sweep)
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="$MODELS_DIR/Qwen2.5-1.5B-Instruct-${VARIANT}.gguf"
    if [ ! -f "$MODEL_PATH" ]; then
        log "⚠ SKIP: $MODEL_PATH not found"
        continue
    fi
    log ""
    log "━━━━━━━━━━━━━━━━━━ $VARIANT ━━━━━━━━━━━━━━━━━━"

    for CTX in "${CTX_SIZES[@]}"; do
        OUTPUT_FILE="$RESULTS_DIR/qwen_${VARIANT}_ctx${CTX}.jsonl"
        > "$OUTPUT_FILE"
        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$((CURRENT_RUN + 1))
            PROGRESS=$((CURRENT_RUN * 100 / TOTAL_RUNS))
            BENCH_TEMP="/tmp/qwen_bench_$$_${VARIANT}_${CTX}_${TRIAL}.txt"

            llama-cli -m "$MODEL_PATH" -c "$CTX" -n "$OUTPUT_TOKENS" \
                -p "$PROMPT" -t 4 > "$BENCH_TEMP" 2>&1 &
            LLAMA_PID=$!
            for i in {1..20}; do
                kill -0 $LLAMA_PID 2>/dev/null || break
                sleep 1
            done
            kill -9 $LLAMA_PID 2>/dev/null || true
            wait $LLAMA_PID 2>/dev/null || true

            BENCH_OUTPUT=$(cat "$BENCH_TEMP")
            rm -f "$BENCH_TEMP"

            TPS=$(echo "$BENCH_OUTPUT" | grep -oE "Generation: [0-9]+\.[0-9]+" | cut -d: -f2 | tr -d ' ' || echo "0")
            if [ -z "$TPS" ] || [ "$TPS" = "0" ]; then
                TPS=$(echo "$BENCH_OUTPUT" | grep -oE "[0-9]+\.[0-9]+ t/s" | tail -1 | cut -d' ' -f1 || echo "0")
            fi

            echo "{\"variant\":\"$VARIANT\",\"context_length\":$CTX,\"trial\":$TRIAL,\"decode_tps\":$TPS,\"device\":\"M4 Mac\",\"backend\":\"Metal\",\"model\":\"Qwen2.5-1.5B\",\"timestamp\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" >> "$OUTPUT_FILE"
            echo -n "  [ctx=$CTX t=$TRIAL $PROGRESS%] $TPS t/s  "
            [ "$((TRIAL % 5))" = "0" ] && echo "" || true
        done
        echo ""
        log "  ✅ ctx=$CTX done → $OUTPUT_FILE"
    done
done

log ""
log "========================================"
log "✅ Qwen 2.5 1.5B sweep complete!"
log "Results in: $RESULTS_DIR"
log "========================================"

# Quick summary
python3 -c "
import json, glob
from collections import defaultdict
files = glob.glob('$RESULTS_DIR/*.jsonl')
ctx_variant = defaultdict(lambda: defaultdict(list))
for f in files:
    with open(f) as fp:
        for line in fp:
            try:
                r = json.loads(line)
                ctx_variant[r['variant']][r['context_length']].append(r['decode_tps'])
            except: pass
print('Variant     | ctx=256 | ctx=512 | ctx=1024 | ctx=2048')
print('-' * 52)
for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:
    if v not in ctx_variant: continue
    row = f'{v:<11} |'
    for ctx in [256,512,1024,2048]:
        vals = ctx_variant[v].get(ctx,[])
        avg = sum(vals)/len(vals) if vals else 0
        row += f' {avg:6.1f}  |'
    print(row)
"
