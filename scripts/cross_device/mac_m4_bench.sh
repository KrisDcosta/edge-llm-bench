#!/usr/bin/env bash
# =============================================================================
# mac_m4_bench.sh — Cross-device benchmark script for Apple Silicon (M4, Metal)
#
# Usage:
#   bash scripts/cross_device/mac_m4_bench.sh \
#       --model-dir local-models/llama3_2_3b_gguf/ \
#       [--output-dir results/] \
#       [--variants Q2_K,Q3_K_M,Q4_K_M,Q4_K_S,Q5_K_M,Q6_K,Q8_0] \
#       [--ctx-sizes 256,1024,2048]
#
# Requirements:
#   - llama-cli or llama-bench on PATH
#     Install: brew install llama.cpp
#     Or build from source with Metal:
#       git clone https://github.com/ggml-org/llama.cpp
#       cd llama.cpp && cmake -B build -DLLAMA_METAL=ON
#       cmake --build build --config Release -j8
#       export PATH=$PATH:$(pwd)/build/bin
#   - GGUF model files in --model-dir
#     Filename pattern: *<VARIANT>*.gguf  (case-insensitive)
#     e.g. Llama-3.2-3B-Instruct-Q4_K_M.gguf
#
# Output:
#   results/crossdev_mac_m4_<TIMESTAMP>.jsonl  — one JSON record per trial
#
# Notes:
#   - -ngl 99  offloads all layers to Metal GPU (M4)
#   - -t 8     thread count (optimal for M4 10-core with Metal acceleration)
#   - 10 measurement trials + 2 warmups per variant×context cell
#   - Warmup records written with is_warmup=true so they can be filtered
#   - Context sizes: 256, 1024, 2048 (512 skipped for cross-device time savings)
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
MODEL_DIR=""
OUTPUT_DIR="results"
VARIANTS_ARG="Q2_K,Q3_K_M,Q4_K_S,Q4_K_M,Q5_K_M,Q6_K,Q8_0"
CTX_SIZES_ARG="256,1024,2048"
N_TRIALS=10
N_WARMUP=2
N_PREDICT=128
N_THREADS=8
N_GPU_LAYERS=99   # offload all layers to Metal

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model-dir)  MODEL_DIR="$2";     shift 2 ;;
        --output-dir) OUTPUT_DIR="$2";    shift 2 ;;
        --variants)   VARIANTS_ARG="$2";  shift 2 ;;
        --ctx-sizes)  CTX_SIZES_ARG="$2"; shift 2 ;;
        --help|-h)
            head -40 "$0" | grep "^#" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "ERROR: Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done

# ---------------------------------------------------------------------------
# Validate arguments
# ---------------------------------------------------------------------------
if [[ -z "$MODEL_DIR" ]]; then
    echo "ERROR: --model-dir is required." >&2
    echo "Usage: $0 --model-dir /path/to/gguf/models [options]" >&2
    exit 1
fi

if [[ ! -d "$MODEL_DIR" ]]; then
    echo "ERROR: Model directory not found: $MODEL_DIR" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Locate llama binary (prefer llama-cli, fall back to llama-bench)
# ---------------------------------------------------------------------------
LLAMA_BIN=""
if command -v llama-cli &>/dev/null; then
    LLAMA_BIN="llama-cli"
elif command -v llama-bench &>/dev/null; then
    LLAMA_BIN="llama-bench"
else
    echo "ERROR: Neither llama-cli nor llama-bench found on PATH." >&2
    echo "" >&2
    echo "Install options:" >&2
    echo "  Option 1 (recommended, macOS): brew install llama.cpp" >&2
    echo "  Option 2 (build from source with Metal):" >&2
    echo "    git clone https://github.com/ggml-org/llama.cpp" >&2
    echo "    cd llama.cpp" >&2
    echo "    cmake -B build -DLLAMA_METAL=ON" >&2
    echo "    cmake --build build --config Release -j8" >&2
    echo "    export PATH=\$PATH:\$(pwd)/build/bin" >&2
    exit 1
fi

echo "Binary: $LLAMA_BIN ($(command -v "$LLAMA_BIN"))"
LLAMA_VERSION=$("$LLAMA_BIN" --version 2>&1 | head -1 || echo "unknown")
echo "Version: $LLAMA_VERSION"

# ---------------------------------------------------------------------------
# Collect device information
# ---------------------------------------------------------------------------
DEVICE_MODEL=$(sysctl -n hw.model 2>/dev/null || echo "unknown")
DEVICE_MEM_BYTES=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
DEVICE_MEM_GB=$(python3 -c "print(round(${DEVICE_MEM_BYTES} / 1073741824, 1))" 2>/dev/null || echo "unknown")
echo "Device: $DEVICE_MODEL  (${DEVICE_MEM_GB} GB RAM)"

# ---------------------------------------------------------------------------
# Setup output file
# ---------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUTPUT_DIR"
OUTFILE="${OUTPUT_DIR}/crossdev_mac_m4_${TIMESTAMP}.jsonl"

# ---------------------------------------------------------------------------
# Parse comma-separated args into arrays
# ---------------------------------------------------------------------------
IFS=',' read -ra VARIANTS  <<< "$VARIANTS_ARG"
IFS=',' read -ra CTX_SIZES <<< "$CTX_SIZES_ARG"

# Quant-bits lookup
declare -A QBITS=(
    [Q2_K]=2 [Q3_K_S]=3 [Q3_K_M]=3
    [Q4_K_S]=4 [Q4_K_M]=4
    [Q5_K_S]=5 [Q5_K_M]=5
    [Q6_K]=6 [Q8_0]=8 [F16]=16
)

# Standard benchmark prompt (qa_short_001 from prompt-suite-v1.yaml)
# Use $'...' quoting so \n is interpreted as a real newline by the shell
BENCH_PROMPT=$'Answer with only the capital city name.\n\nQuestion: What is the capital of France?'

# ---------------------------------------------------------------------------
# Python helper: parse a single run's llama.cpp output into a JSONL record
# Reads JSON blob from stdin (env vars passed as arguments).
# ---------------------------------------------------------------------------
write_record() {
    local llama_output="$1"
    local run_id="$2"
    local variant="$3"
    local ctx="$4"
    local trial_idx="$5"
    local is_warmup="$6"
    local model_file="$7"
    local model_hash="$8"
    local quant_bits="$9"
    local t_start="${10}"
    local t_end="${11}"

    python3 - \
        "$llama_output" "$run_id" "$variant" "$ctx" "$trial_idx" "$is_warmup" \
        "$model_file" "$model_hash" "$quant_bits" "$t_start" "$t_end" \
        "$DEVICE_MODEL" "$DEVICE_MEM_GB" "$LLAMA_VERSION" \
        >> "$OUTFILE" <<'PYEOF'
import sys
import re
import json

(llama_out, run_id, variant, ctx, trial_idx, is_warmup,
 model_file, model_hash, quant_bits, t_start, t_end,
 device_model, mem_gb, llama_version) = sys.argv[1:]

text = llama_out

def pf(pat, s):
    m = re.search(pat, s)
    return float(m.group(1)) if m else None

def pi(pat, s):
    m = re.search(pat, s)
    return int(m.group(1)) if m else None

prompt_eval_ms     = pf(r"prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*\d+", text)
prompt_eval_tokens = pi(r"prompt eval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s*tokens?", text)
prompt_eval_tps    = pf(r"prompt eval time\s*=.*?([\d.]+)\s*tokens per second", text)
eval_ms            = pf(r"\beval time\s*=\s*([\d.]+)\s*ms\s*/\s*\d+\s*runs?", text)
eval_tokens        = pi(r"\beval time\s*=\s*[\d.]+\s*ms\s*/\s*(\d+)\s*runs?", text)
eval_tps           = pf(r"\beval time\s*=.*?([\d.]+)\s*tokens per second", text)
total_ms           = pf(r"total time\s*=\s*([\d.]+)\s*ms", text)
load_ms            = pf(r"load time\s*=\s*([\d.]+)\s*ms", text)

valid = (prompt_eval_ms is not None and eval_ms is not None and total_ms is not None)

ttft_s    = prompt_eval_ms / 1000.0 if prompt_eval_ms is not None else None
prefill_s = ttft_s
gen_s     = eval_ms / 1000.0 if eval_ms is not None else None
e2e_s     = total_ms / 1000.0 if total_ms is not None else None

gen_over_prefill = gen_s / prefill_s if (prefill_s and gen_s and prefill_s > 0) else None
prefill_frac     = prefill_s / e2e_s if (prefill_s and e2e_s and e2e_s > 0) else None
gen_frac         = gen_s / e2e_s     if (gen_s and e2e_s and e2e_s > 0)     else None

t_start_f = float(t_start)
t_end_f   = float(t_end)

# TTFT approximation: t_request_start + prefill latency
t_first_token = (t_start_f + prefill_s) if prefill_s is not None else None

status = "success" if valid else "failed"
failure = None if valid else {
    "code": "PARSE_ERROR",
    "stage": "inference",
    "message": "Could not parse required timing fields from llama.cpp output",
    "retryable": True
}

record = {
    "record_version": "1.0",
    "run_id": run_id,
    "status": status,
    "device": {
        "manufacturer": "Apple",
        "model": device_model,
        "platform": "macos",
        "backend": "metal",
        "memory_gb": mem_gb,
        # Fields kept for schema compatibility with Android baseline
        "android_version": "N/A",
        "build_fingerprint": f"{device_model}-macos"
    },
    "build": {
        "framework": "llama.cpp",
        "framework_version": llama_version,
        "gguf_variant": variant
    },
    "model": {
        "name": f"Llama-3.2-3B-Instruct-{variant}",
        "artifact_hash": model_hash if model_hash != "null" else None,
        "quant_bits": int(quant_bits)
    },
    "trial": {
        "prompt_id": "qa_short_001",
        "context_length": int(ctx),
        "output_length": 128,
        "trial_index": int(trial_idx),
        "is_warmup": is_warmup.lower() == "true"
    },
    "timing_s": {
        "t_request_start":      t_start_f,
        "t_model_forward_start":t_start_f,
        "t_first_token":        t_first_token,
        "t_last_token":         t_end_f
    },
    "tokens": {
        "input_tokens":  prompt_eval_tokens,
        "output_tokens": eval_tokens
    },
    "metrics": {
        "ttft_s":          ttft_s,
        "prefill_s":       prefill_s,
        "prefill_tps":     prompt_eval_tps,
        "gen_s":           gen_s,
        "decode_tps":      eval_tps,
        "e2e_s":           e2e_s,
        "gen_over_prefill":gen_over_prefill,
        "prefill_frac":    prefill_frac,
        "gen_frac":        gen_frac
    },
    "resources": {
        "peak_rss_mb":              None,
        "battery_start_pct":        None,
        "battery_end_pct":          None,
        "battery_drop_pct":         None,
        "battery_drop_per_1k_tokens":None,
        "temperature_c":            None
    },
    "failure": failure
}

print(json.dumps(record))
PYEOF
}

# ---------------------------------------------------------------------------
# Main benchmark loop
# ---------------------------------------------------------------------------
TOTAL_CELLS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} ))
TOTAL_RUNS=$(( TOTAL_CELLS * (N_WARMUP + N_TRIALS) ))

echo ""
echo "========================================"
echo "Benchmark plan:"
echo "  Variants:      ${VARIANTS[*]}"
echo "  Context sizes: ${CTX_SIZES[*]}"
echo "  Trials/cell:   $N_TRIALS (+ $N_WARMUP warmups)"
echo "  Output tokens: $N_PREDICT"
echo "  GPU layers:    $N_GPU_LAYERS (Metal)"
echo "  Threads:       $N_THREADS"
echo "  Total runs:    $TOTAL_RUNS"
echo "  Output file:   $OUTFILE"
echo "========================================"
echo ""

CELL_NUM=0

for VARIANT in "${VARIANTS[@]}"; do
    # Find model file for this variant (case-insensitive search)
    MODEL_FILE=$(find "$MODEL_DIR" -maxdepth 2 -iname "*${VARIANT}*.gguf" 2>/dev/null | head -1 || true)

    if [[ -z "$MODEL_FILE" ]]; then
        echo "WARNING: No GGUF file found for variant ${VARIANT} in ${MODEL_DIR} — skipping." >&2
        continue
    fi

    echo "=== Variant: $VARIANT ==="
    echo "    File: $MODEL_FILE"

    # MD5 hash for artifact traceability
    MODEL_HASH=$(md5 -q "$MODEL_FILE" 2>/dev/null || md5sum "$MODEL_FILE" 2>/dev/null | awk '{print $1}' || echo "null")
    QBITS_VAL="${QBITS[$VARIANT]:-4}"

    for CTX in "${CTX_SIZES[@]}"; do
        CELL_NUM=$(( CELL_NUM + 1 ))
        echo "  [Cell $CELL_NUM/$TOTAL_CELLS] ctx=$CTX"

        for TRIAL_IDX in $(seq 0 $(( N_WARMUP + N_TRIALS - 1 ))); do
            if (( TRIAL_IDX < N_WARMUP )); then
                IS_WARMUP="true"
                LABEL="warmup-${TRIAL_IDX}"
            else
                IS_WARMUP="false"
                LABEL="trial-$(( TRIAL_IDX - N_WARMUP ))"
            fi

            RUN_ID="mac_m4_${TIMESTAMP}_${VARIANT}_ctx${CTX}_${LABEL}"
            echo -n "    ${LABEL}... "

            # Capture wall-clock start (nanoseconds)
            T_START_NS=$(python3 -c "import time; print(int(time.time()*1e9))")

            # Run inference; capture stderr+stdout (llama.cpp writes timings to stderr)
            LLAMA_OUT=$( \
                "$LLAMA_BIN" \
                    --model          "$MODEL_FILE" \
                    --ctx-size       "$CTX" \
                    --n-predict      "$N_PREDICT" \
                    --threads        "$N_THREADS" \
                    --n-gpu-layers   "$N_GPU_LAYERS" \
                    --prompt         "$BENCH_PROMPT" \
                    --log-disable \
                    --no-display-prompt \
                    2>&1 \
            ) || true

            T_END_NS=$(python3 -c "import time; print(int(time.time()*1e9))")

            # Convert nanoseconds to fractional seconds
            T_START_S=$(python3 -c "print(${T_START_NS} / 1e9)")
            T_END_S=$(python3 -c "print(${T_END_NS} / 1e9)")

            # Write record to JSONL
            write_record \
                "$LLAMA_OUT" "$RUN_ID" "$VARIANT" "$CTX" \
                "$TRIAL_IDX" "$IS_WARMUP" \
                "$MODEL_FILE" "$MODEL_HASH" "$QBITS_VAL" \
                "$T_START_S" "$T_END_S"

            # Print quick summary from the last written record
            LAST_LINE=$(tail -1 "$OUTFILE" 2>/dev/null || true)
            LAST_STATUS=$(echo "$LAST_LINE" | python3 -c \
                "import json,sys; r=json.load(sys.stdin); print(r.get('status','?'))" 2>/dev/null || echo "?")
            if [[ "$LAST_STATUS" == "success" ]]; then
                LAST_TPS=$(echo "$LAST_LINE" | python3 -c \
                    "import json,sys; r=json.load(sys.stdin); \
                     v=r['metrics']['decode_tps']; print(f'{v:.1f}' if v else 'N/A')" 2>/dev/null || echo "?")
                echo "ok (decode ${LAST_TPS} tok/s)"
            else
                echo "FAILED"
            fi
        done  # trial

        echo ""
    done  # ctx
    echo ""
done  # variant

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
N_SUCCESS=$(python3 -c \
    "import json; lines=open('${OUTFILE}').readlines(); \
     s=sum(1 for l in lines if l.strip() and json.loads(l).get('status')=='success' and not json.loads(l)['trial']['is_warmup']); \
     print(s)" 2>/dev/null || echo "?")

echo "========================================"
echo "Benchmark complete."
echo "  Records written: $(wc -l < "$OUTFILE" | tr -d ' ')"
echo "  Successful (non-warmup): $N_SUCCESS"
echo "  Output: $OUTFILE"
echo ""
echo "Next step:"
echo "  python3 scripts/cross_device/parse_crossdev_results.py $OUTFILE"
echo "========================================"
