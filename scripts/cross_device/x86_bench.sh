#!/usr/bin/env bash
# =============================================================================
# x86_bench.sh — Cross-device benchmark script for x86_64 Linux (CPU/AVX2)
#
# Targets: HP Pavilion or equivalent x86_64 desktop/laptop running Linux
#
# Usage:
#   bash scripts/cross_device/x86_bench.sh \
#       --model-dir local-models/llama3_2_3b_gguf/ \
#       [--output-dir results/] \
#       [--variants Q2_K,Q3_K_M,Q4_K_M,Q4_K_S,Q5_K_M,Q6_K,Q8_0] \
#       [--ctx-sizes 256,1024,2048]
#
# Requirements:
#   - llama-cli on PATH (CPU-only build with AVX2)
#     Build from source:
#       git clone https://github.com/ggml-org/llama.cpp
#       cd llama.cpp
#       make GGML_AVX2=1 -j$(nproc)
#       export PATH=$PATH:$(pwd)
#     Or with cmake:
#       cmake -B build -DGGML_AVX2=ON
#       cmake --build build --config Release -j$(nproc)
#       export PATH=$PATH:$(pwd)/build/bin
#   - GGUF model files in --model-dir
#     Filename pattern: *<VARIANT>*.gguf  (case-insensitive)
#
# Output:
#   results/crossdev_x86_<TIMESTAMP>.jsonl  — one JSON record per trial
#
# Notes:
#   - CPU-only inference — NO -ngl flag (no GPU offload)
#   - -t 8 threads (suitable for 6-8 core x86 laptop/desktop)
#   - 10 measurement trials + 2 warmups per variant×context cell
#   - Context sizes: 256, 1024, 2048 (512 skipped for cross-device time savings)
#   - AVX2 required for acceptable performance; script warns if not detected
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
            head -45 "$0" | grep "^#" | sed 's/^# \{0,1\}//'
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
# Locate llama-cli binary (CPU build, no GPU)
# ---------------------------------------------------------------------------
LLAMA_BIN=""
if command -v llama-cli &>/dev/null; then
    LLAMA_BIN="llama-cli"
elif command -v llama.cpp &>/dev/null; then
    LLAMA_BIN="llama.cpp"
else
    echo "ERROR: llama-cli not found on PATH." >&2
    echo "" >&2
    echo "Build llama.cpp with AVX2 support:" >&2
    echo "  git clone https://github.com/ggml-org/llama.cpp" >&2
    echo "  cd llama.cpp" >&2
    echo "  make GGML_AVX2=1 -j\$(nproc)" >&2
    echo "  export PATH=\$PATH:\$(pwd)" >&2
    echo "" >&2
    echo "Or with cmake:" >&2
    echo "  cmake -B build -DGGML_AVX2=ON" >&2
    echo "  cmake --build build --config Release -j\$(nproc)" >&2
    echo "  export PATH=\$PATH:\$(pwd)/build/bin" >&2
    exit 1
fi

echo "Binary: $LLAMA_BIN ($(command -v "$LLAMA_BIN"))"
LLAMA_VERSION=$("$LLAMA_BIN" --version 2>&1 | head -1 || echo "unknown")
echo "Version: $LLAMA_VERSION"

# ---------------------------------------------------------------------------
# Check for AVX2 support
# ---------------------------------------------------------------------------
if [[ -f /proc/cpuinfo ]]; then
    if grep -qm1 avx2 /proc/cpuinfo 2>/dev/null; then
        echo "AVX2: detected (good)"
    else
        echo "WARNING: AVX2 not detected in /proc/cpuinfo." >&2
        echo "         Inference will be significantly slower without AVX2." >&2
        echo "         Ensure llama.cpp was compiled with GGML_AVX2=1." >&2
    fi
else
    echo "WARNING: /proc/cpuinfo not found — cannot verify AVX2 support." >&2
    echo "         This script is intended for x86_64 Linux." >&2
fi

# ---------------------------------------------------------------------------
# Collect device information (Linux-specific)
# ---------------------------------------------------------------------------
ARCH=$(uname -m 2>/dev/null || echo "unknown")
CPU_MODEL=$(grep "model name" /proc/cpuinfo 2>/dev/null | head -1 | cut -d: -f2 | sed 's/^ *//' || echo "unknown")
MEM_TOTAL=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
MEM_GB=$(python3 -c "print(round(${MEM_TOTAL} / 1048576, 1))" 2>/dev/null || echo "unknown")
KERNEL=$(uname -r 2>/dev/null || echo "unknown")
HOSTNAME_VAL=$(hostname 2>/dev/null || echo "unknown")

echo "Device: $HOSTNAME_VAL ($ARCH)"
echo "CPU:    $CPU_MODEL"
echo "RAM:    ${MEM_GB} GB"

# ---------------------------------------------------------------------------
# Setup output file
# ---------------------------------------------------------------------------
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$OUTPUT_DIR"
OUTFILE="${OUTPUT_DIR}/crossdev_x86_${TIMESTAMP}.jsonl"

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
# Python helper: parse a single run's output and append a JSONL record
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
        "$HOSTNAME_VAL" "$ARCH" "$CPU_MODEL" "$MEM_GB" "$KERNEL" "$LLAMA_VERSION" \
        >> "$OUTFILE" <<'PYEOF'
import sys
import re
import json

(llama_out, run_id, variant, ctx, trial_idx, is_warmup,
 model_file, model_hash, quant_bits, t_start, t_end,
 hostname, arch, cpu_model, mem_gb, kernel, llama_version) = sys.argv[1:]

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
        "manufacturer": hostname,
        "model": f"{arch} / {cpu_model}",
        "platform": "linux",
        "backend": "cpu_avx2",
        "arch": arch,
        "cpu_model": cpu_model,
        "memory_gb": mem_gb,
        "kernel": kernel,
        # Fields kept for schema compatibility with Android baseline
        "android_version": "N/A",
        "build_fingerprint": f"{hostname}-linux-x86"
    },
    "build": {
        "framework": "llama.cpp",
        "framework_version": llama_version,
        "gguf_variant": variant
    },
    "model": {
        "name": f"Llama-3.2-3B-Instruct-{variant}",
        "artifact_hash": model_hash if model_hash not in ("null", "") else None,
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
        "t_request_start":       t_start_f,
        "t_model_forward_start": t_start_f,
        "t_first_token":         t_first_token,
        "t_last_token":          t_end_f
    },
    "tokens": {
        "input_tokens":  prompt_eval_tokens,
        "output_tokens": eval_tokens
    },
    "metrics": {
        "ttft_s":           ttft_s,
        "prefill_s":        prefill_s,
        "prefill_tps":      prompt_eval_tps,
        "gen_s":            gen_s,
        "decode_tps":       eval_tps,
        "e2e_s":            e2e_s,
        "gen_over_prefill": gen_over_prefill,
        "prefill_frac":     prefill_frac,
        "gen_frac":         gen_frac
    },
    "resources": {
        "peak_rss_mb":               None,
        "battery_start_pct":         None,
        "battery_end_pct":           None,
        "battery_drop_pct":          None,
        "battery_drop_per_1k_tokens":None,
        "temperature_c":             None
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
echo "  Mode:          CPU-only (no -ngl; AVX2)"
echo "  Threads:       $N_THREADS"
echo "  Total runs:    $TOTAL_RUNS"
echo "  Output file:   $OUTFILE"
echo "========================================"
echo ""

CELL_NUM=0

for VARIANT in "${VARIANTS[@]}"; do
    # Find model file (case-insensitive)
    MODEL_FILE=$(find "$MODEL_DIR" -maxdepth 2 -iname "*${VARIANT}*.gguf" 2>/dev/null | head -1 || true)

    if [[ -z "$MODEL_FILE" ]]; then
        echo "WARNING: No GGUF file found for variant ${VARIANT} in ${MODEL_DIR} — skipping." >&2
        continue
    fi

    echo "=== Variant: $VARIANT ==="
    echo "    File: $MODEL_FILE"

    # MD5/SHA256 hash for artifact traceability
    MODEL_HASH=$(md5sum "$MODEL_FILE" 2>/dev/null | awk '{print $1}' || echo "null")
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

            RUN_ID="x86_${TIMESTAMP}_${VARIANT}_ctx${CTX}_${LABEL}"
            echo -n "    ${LABEL}... "

            # Wall-clock start
            T_START_S=$(python3 -c "import time; print(time.time())")

            # Run inference (CPU-only — no -ngl flag)
            LLAMA_OUT=$( \
                "$LLAMA_BIN" \
                    --model          "$MODEL_FILE" \
                    --ctx-size       "$CTX" \
                    --n-predict      "$N_PREDICT" \
                    --threads        "$N_THREADS" \
                    --prompt         "$BENCH_PROMPT" \
                    --log-disable \
                    --no-display-prompt \
                    2>&1 \
            ) || true

            T_END_S=$(python3 -c "import time; print(time.time())")

            # Write JSONL record
            write_record \
                "$LLAMA_OUT" "$RUN_ID" "$VARIANT" "$CTX" \
                "$TRIAL_IDX" "$IS_WARMUP" \
                "$MODEL_FILE" "$MODEL_HASH" "$QBITS_VAL" \
                "$T_START_S" "$T_END_S"

            # Quick status line
            LAST_STATUS=$(tail -1 "$OUTFILE" | python3 -c \
                "import json,sys; r=json.load(sys.stdin); print(r.get('status','?'))" 2>/dev/null || echo "?")
            if [[ "$LAST_STATUS" == "success" ]]; then
                LAST_TPS=$(tail -1 "$OUTFILE" | python3 -c \
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
N_RECORDS=$(wc -l < "$OUTFILE" | tr -d ' ')
N_SUCCESS=$(python3 -c \
    "import json
lines = open('${OUTFILE}').readlines()
n = sum(1 for l in lines if l.strip() and
        json.loads(l).get('status')=='success' and
        not json.loads(l)['trial']['is_warmup'])
print(n)" 2>/dev/null || echo "?")

echo "========================================"
echo "Benchmark complete."
echo "  Records written:          $N_RECORDS"
echo "  Successful (non-warmup):  $N_SUCCESS"
echo "  Output: $OUTFILE"
echo ""
echo "Next step:"
echo "  python3 scripts/cross_device/parse_crossdev_results.py $OUTFILE"
echo "========================================"
