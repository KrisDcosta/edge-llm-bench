#!/usr/bin/env bash
# ============================================================
# m4_llama_tps.sh  —  Llama 3.2 3B baseline TPS sweep
#                      M4 Mac · Metal GPU · uses llama-bench
#
# Measures prefill and decode throughput at 4 representative
# context lengths.  Uses llama-bench natively: no parsing hacks.
#
# Usage:
#   bash scripts/bench/m4_llama_tps.sh              # all 7 variants
#   bash scripts/bench/m4_llama_tps.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/m4_llama_tps.sh --resume      # skip completed
#
# Output:  results/m4_llama_tps_{ts}/tps_{VARIANT}.jsonl
# Runtime: ~45 min  (7 variants × 4 ctx × 10 trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

MODELS_DIR="local-models/llama3_2_3b_gguf"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
# PP tokens for each context: half context for prefill, 128 tokens generation
# ctx:   256   512  1024  2048
PP_TOKENS=(128  256   512  1024)
TG_TOKENS=128
NUM_TRIALS=10
NGL=99
THREADS=4

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/m4_llama_tps_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

RESUME=0
VARIANTS=()
for arg in "$@"; do
    case "$arg" in
        --resume) RESUME=1 ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS+=("$arg") ;;
        *) printf 'Unknown arg: %s\n' "$arg" >&2; exit 1 ;;
    esac
done
[ ${#VARIANTS[@]} -eq 0 ] && VARIANTS=("${ALL_VARIANTS[@]}")

hr
log "M4 Mac  —  Llama 3.2 3B Baseline TPS Sweep  (Metal GPU, llama-bench)"
log "Host     : $(hostname)"
log "Variants : ${VARIANTS[*]}"
log "PP sizes : ${PP_TOKENS[*]}  |  TG: ${TG_TOKENS}  |  Trials: ${NUM_TRIALS}"
log "Results  : ${RESULTS_DIR}"
hr

if ! command -v llama-bench &>/dev/null; then
    log "❌ FATAL: llama-bench not found."; exit 1
fi

MISSING=0
for V in "${VARIANTS[@]}"; do
    [ -f "${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf" ] || { log "  ❌ Missing: ${V}"; MISSING=$((MISSING+1)); }
done
[ "$MISSING" -gt 0 ] && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present"
log ""

# ── Write Python helpers to temp files (avoids pipe+heredoc stdin conflict) ──
PARSE_SCRIPT=$(mktemp /tmp/bench_parse.XXXXXX.py)
SUMMARY_SCRIPT=$(mktemp /tmp/bench_summary.XXXXXX.py)
trap 'rm -f "$PARSE_SCRIPT" "$SUMMARY_SCRIPT"' EXIT

cat > "$PARSE_SCRIPT" << 'PYEOF'
import json, sys, statistics, datetime

variant      = sys.argv[1]
model_prefix = sys.argv[2]
ngl          = int(sys.argv[3])
threads      = int(sys.argv[4])

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
        "variant":   variant,
        "n_prompt":  np,
        "n_gen":     ng,
        "test_type": "pp" if ng == 0 else "tg",
        "tps_mean":  round(mean_ts, 4),
        "tps_std":   round(std_ts, 4),
        "n_trials":  len(samples),
        "device":    "M4Mac",
        "backend":   "Metal",
        "model":     f"{model_prefix}-{variant}",
        "ngl":       ngl,
        "threads":   threads,
        "ts":        datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
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
    if not paths:
        continue
    for line in open(paths[0]):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        if d.get('test_type') == 'pp':
            pp_map[variant][d['n_prompt']] = d['tps_mean']
        else:
            tg_dict[variant] = d['tps_mean']

pp_sizes = [128, 256, 512, 1024]
print(f"\n  {'Variant':<10}  " + "  ".join(f"pp{p:>5}" for p in pp_sizes) + "  tg128")
print("  " + "-" * 70)
for v in requested:
    if v not in pp_map:
        continue
    row = f"  {v:<10}  "
    for p in pp_sizes:
        ts = pp_map[v].get(p, 0)
        row += f"{ts:6.1f}   " if ts else "   N/A   "
    row += f"  {tg_dict.get(v, 0):6.1f}"
    print(row)
PYEOF

EXPECTED_LINES=$(( ${#PP_TOKENS[@]} + 1 ))  # 4 pp rows + 1 tg row = 5
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
    > "$OUTPUT_FILE"

    # Build argument list: -p 128,256,512,1024 and -n TG_TOKENS
    PP_ARG=$(IFS=,; echo "${PP_TOKENS[*]}")

    # Run all context sizes in one llama-bench call
    BENCH_JSON=$(llama-bench \
        -m  "$MODEL_PATH" \
        -p  "$PP_ARG" \
        -n  "$TG_TOKENS" \
        -r  "$NUM_TRIALS" \
        -ngl "$NGL" \
        -t  "$THREADS" \
        -o  jsonl 2>/dev/null) || true

    # Parse each row and save
    printf '%s\n' "$BENCH_JSON" | python3 "$PARSE_SCRIPT" "$VARIANT" "$MODEL_PREFIX" "$NGL" "$THREADS" \
        >> "$OUTPUT_FILE"

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

log ""
hr
log "TPS SUMMARY  —  M4 Mac (Metal)  —  Llama 3.2 3B"
hr

python3 "$SUMMARY_SCRIPT" "$RESULTS_DIR" "${VARIANTS[@]}"

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
