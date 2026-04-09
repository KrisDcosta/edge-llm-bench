#!/usr/bin/env bash
# ============================================================
# x86_qwen_tps.sh  —  Qwen 2.5 1.5B baseline TPS sweep
#                      x86_64 CPU  ·  uses llama-bench
#
# Measures prefill and decode throughput at 4 representative
# context lengths on x86 hardware (Linux or Windows+Git Bash).
# Uses CPU inference (no GPU layers).
#
# Prerequisites:
#   1. llama-bench binary in PATH or LLAMA_BENCH_PATH set
#      - Linux:   build from source (see setup below)
#      - Windows: download pre-built from llama.cpp releases
#   2. GGUF models in local-models/qwen2_5_1_5b_gguf/
#      - Run the download snippet in step 2 below
#
# Quick setup (Linux / WSL / Git Bash):
#   # 1. Build llama.cpp (one-time, ~5 min — skip if already done for Llama):
#   git clone https://github.com/ggerganov/llama.cpp /tmp/llama.cpp
#   cmake -B /tmp/llama.cpp/build -DGGML_AVX2=ON /tmp/llama.cpp
#   cmake --build /tmp/llama.cpp/build --config Release -j$(nproc)
#   export LLAMA_BENCH_PATH=/tmp/llama.cpp/build/bin/llama-bench
#
#   # 2. Download Qwen models (needs WiFi, ~0.6-2.0 GB each):
#   pip install huggingface_hub
#   python3 -c "
#   from huggingface_hub import hf_hub_download
#   import os; os.makedirs('local-models/qwen2_5_1_5b_gguf', exist_ok=True)
#   for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:
#       hf_hub_download('bartowski/Qwen2.5-1.5B-Instruct-GGUF',
#           f'Qwen2.5-1.5B-Instruct-{v}.gguf',
#           local_dir='local-models/qwen2_5_1_5b_gguf')
#   "
#
#   # 3. Run benchmark (no WiFi needed after step 2):
#   bash scripts/bench/x86_qwen_tps.sh
#
# Usage:
#   bash scripts/bench/x86_qwen_tps.sh              # all 7 variants
#   bash scripts/bench/x86_qwen_tps.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/x86_qwen_tps.sh --threads 8   # override thread count
#   bash scripts/bench/x86_qwen_tps.sh --resume      # skip completed variants
#
# Output:  results/x86_qwen_tps_{HOSTNAME}_{ts}/tps_{VARIANT}.jsonl
# Runtime: ~15-30 min  (7 variants × 4 ctx × 5 trials — Qwen is smaller than Llama)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
MODEL_PREFIX="Qwen2.5-1.5B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

# x86 CPU context: half the context for prefill, 128 tokens generated
# ctx:   256   512  1024  2048
PP_TOKENS=(128  256   512  1024)
TG_TOKENS=128
NUM_TRIALS=5     # matches Llama x86 collection methodology
NGL=0            # CPU ONLY — no GPU layers
THREADS=$(nproc 2>/dev/null || echo 4)   # auto-detect logical cores

# Detect llama-bench binary
if [ -n "${LLAMA_BENCH_PATH:-}" ]; then
    LLAMA_BENCH="$LLAMA_BENCH_PATH"
elif command -v llama-bench &>/dev/null; then
    LLAMA_BENCH="llama-bench"
elif [ -f "/tmp/llama.cpp/build/bin/llama-bench" ]; then
    LLAMA_BENCH="/tmp/llama.cpp/build/bin/llama-bench"
elif [ -f "./llama-bench" ]; then
    LLAMA_BENCH="./llama-bench"
elif [ -f "./llama-bench.exe" ]; then
    LLAMA_BENCH="./llama-bench.exe"
else
    echo "❌ FATAL: llama-bench not found. Set LLAMA_BENCH_PATH or add to PATH."
    echo "   See setup instructions at top of this script."
    exit 1
fi

HOST=$(hostname | cut -c1-12)
TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/x86_qwen_tps_${HOST}_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

# Parse args
RESUME=0
VARIANTS=()
for arg in "$@"; do
    case "$arg" in
        --resume)  RESUME=1 ;;
        --threads) shift; THREADS="$1" ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=("${ALL_VARIANTS[@]}")

hr
log "x86 CPU  —  Qwen 2.5 1.5B Baseline TPS Sweep"
log "Host     : $(hostname)  (x86_64)"
log "Binary   : $LLAMA_BENCH"
log "Threads  : ${THREADS} (ngl=0, CPU only)"
log "Variants : ${VARIANTS[*]}"
log "PP sizes : ${PP_TOKENS[*]}  |  TG: ${TG_TOKENS}  |  Trials: ${NUM_TRIALS}"
log "Results  : ${RESULTS_DIR}"
hr

# Verify models exist
MISSING=0
for V in "${VARIANTS[@]}"; do
    MODEL="${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf"
    if [ ! -f "$MODEL" ]; then
        log "  ❌ Missing model: $MODEL"
        MISSING=$((MISSING+1))
    fi
done
if [ "$MISSING" -gt 0 ]; then
    log ""
    log "Download missing models with:"
    log "  python3 -c \""
    log "  from huggingface_hub import hf_hub_download; import os"
    log "  os.makedirs('local-models/qwen2_5_1_5b_gguf', exist_ok=True)"
    log "  for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:"
    log "      hf_hub_download('bartowski/Qwen2.5-1.5B-Instruct-GGUF',"
    log "          f'Qwen2.5-1.5B-Instruct-{v}.gguf',"
    log "          local_dir='local-models/qwen2_5_1_5b_gguf')\""
    exit 1
fi
log "✅ All ${#VARIANTS[@]} model(s) present"

# Python helpers (temp files to avoid heredoc+pipe stdin conflict)
PARSE_SCRIPT=$(mktemp /tmp/x86_bench_parse.XXXXXX.py)
SUMMARY_SCRIPT=$(mktemp /tmp/x86_bench_summary.XXXXXX.py)
trap 'rm -f "$PARSE_SCRIPT" "$SUMMARY_SCRIPT"' EXIT

cat > "$PARSE_SCRIPT" << 'PYEOF'
import json, sys, statistics, datetime, platform

variant      = sys.argv[1]
model_prefix = sys.argv[2]
threads      = int(sys.argv[3])

for line in sys.stdin:
    line = line.strip()
    if not line.startswith('{'): continue
    try:
        d = json.loads(line)
    except Exception:
        continue

    np, ng  = d.get('n_prompt', 0), d.get('n_gen', 0)
    samples = d.get('samples_ts', [d.get('avg_ts', 0)])
    mean_ts = statistics.mean(samples) if samples else 0
    std_ts  = statistics.stdev(samples) if len(samples) > 1 else 0

    out = {
        "variant":    variant,
        "n_prompt":   np,
        "n_gen":      ng,
        "test_type":  "pp" if ng == 0 else "tg",
        "tps_mean":   round(mean_ts, 4),
        "tps_std":    round(std_ts, 4),
        "n_trials":   len(samples),
        "device":     platform.node(),
        "arch":       "x86_64",
        "backend":    "CPU",
        "cpu_brand":  platform.processor(),
        "model":      f"{model_prefix}-{variant}",
        "ngl":        0,
        "threads":    threads,
        "ts":         datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "methodology": "standard",
    }
    print(json.dumps(out))
PYEOF

cat > "$SUMMARY_SCRIPT" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
pp_map  = defaultdict(dict)
tg_dict = defaultdict(float)

for variant in requested:
    paths = glob.glob(f"{results_dir}/tps_{variant}.jsonl")
    if not paths: continue
    for line in open(paths[0]):
        if not line.strip(): continue
        try: d = json.loads(line)
        except: continue
        if d.get('test_type') == 'pp':
            pp_map[variant][d['n_prompt']] = d['tps_mean']
        else:
            tg_dict[variant] = d['tps_mean']

pp_sizes = [128, 256, 512, 1024]
print(f"\n  {'Variant':<10}  " + "  ".join(f"pp{p:>5}" for p in pp_sizes) + "  tg128")
print("  " + "-" * 70)
for v in requested:
    if v not in pp_map: continue
    row = f"  {v:<10}  "
    for p in pp_sizes:
        ts = pp_map[v].get(p, 0)
        row += f"{ts:6.2f}   " if ts else "   N/A   "
    row += f"  {tg_dict.get(v, 0):6.2f}"
    print(row)
PYEOF

EXPECTED_LINES=$(( ${#PP_TOKENS[@]} + 1 ))  # 4 pp + 1 tg
START_S=$(date +%s)
V_IDX=0

for VARIANT in "${VARIANTS[@]}"; do
    V_IDX=$(( V_IDX + 1 ))
    MODEL_PATH="${MODELS_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/tps_${VARIANT}.jsonl"

    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        DONE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
        if [ "$DONE" -ge "$EXPECTED_LINES" ]; then
            log "  ⏩ SKIP $VARIANT — complete (${DONE} rows)"
            continue
        fi
    fi

    log ""
    log "━━━ [${V_IDX}/${#VARIANTS[@]}] ${VARIANT} ━━━"
    MODEL_GB=$(du -sh "$MODEL_PATH" 2>/dev/null | cut -f1 || echo "?")
    log "  Model: $MODEL_PATH  (${MODEL_GB})"
    > "$OUTPUT_FILE"

    PP_ARG=$(IFS=,; echo "${PP_TOKENS[*]}")

    BENCH_JSON=$("$LLAMA_BENCH" \
        -m  "$MODEL_PATH" \
        -p  "$PP_ARG" \
        -n  "$TG_TOKENS" \
        -r  "$NUM_TRIALS" \
        -ngl "$NGL" \
        -t  "$THREADS" \
        -o  jsonl 2>/dev/null) || true

    printf '%s\n' "$BENCH_JSON" | python3 "$PARSE_SCRIPT" "$VARIANT" "$MODEL_PREFIX" "$THREADS" \
        >> "$OUTPUT_FILE"

    ROWS=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
    log "  ✅ Saved ${OUTPUT_FILE}  (${ROWS} rows)"

    # Extract and display tg (decode) TPS for quick reference
    TG_TPS=$(python3 -c "
import json
for line in open('${OUTPUT_FILE}'):
    d = json.loads(line.strip())
    if d.get('test_type') == 'tg':
        print(f'decode TPS: {d[\"tps_mean\"]:.2f} tok/s')
" 2>/dev/null || true)
    [ -n "$TG_TPS" ] && log "  → ${TG_TPS}"
done

log ""
hr
log "TPS SUMMARY  —  x86 CPU  —  Qwen 2.5 1.5B  (${THREADS} threads)"
hr
python3 "$SUMMARY_SCRIPT" "$RESULTS_DIR" "${VARIANTS[@]}"

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
log "Next: copy results/ back to the Mac repo, then integrate with:"
log "  python3 scripts/prepare_dataset.py   # rebuilds all parquets"
log "  python3 scripts/bake_dashboard_data.py  # rebuilds dashboard JSON"
hr
