#!/usr/bin/env bash
# ============================================================
# m4_qwen_cliff.sh  —  Qwen 2.5 1.5B KV-cache cliff sweep
#                       M4 Mac · Metal GPU · uses llama-bench
#
# Uses llama-bench (the official benchmark binary).
# Method: pp-only + pg combined → derive gen_tps per context.
# See m4_llama_cliff.sh for detailed methodology notes.
#
# Usage:
#   bash scripts/bench/m4_qwen_cliff.sh              # all 7 variants
#   bash scripts/bench/m4_qwen_cliff.sh Q6_K Q3_K_M  # subset
#   bash scripts/bench/m4_qwen_cliff.sh --resume      # skip completed
#
# Output:  results/m4_qwen_cliff_{ts}/cliff_{VARIANT}.jsonl
# Runtime: ~2-3 h  (7 variants × 13 ctx × 5 trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
MODEL_PREFIX="Qwen2.5-1.5B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
CTX_SIZES=(1024 1100 1200 1250 1300 1350 1400 1450 1500 1550 1600 1800 2048)
# 128 tokens gives a stable decode window for derived generation TPS.
# The previous 32-token window produced high-CV rows, zero decode rows, and
# impossible derived TPS spikes when pp-only and pp+tg timings were subtracted.
TG_TOKENS=128
NUM_TRIALS=5
NGL=99
THREADS=4

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/m4_qwen_cliff_${TS}"
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
log "M4 Mac  —  Qwen 2.5 1.5B KV-Cache Cliff Sweep  (Metal GPU, llama-bench)"
log "Host     : $(hostname)"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS}  |  TG tokens: ${TG_TOKENS}  |  ngl: ${NGL}"
log "Results  : ${RESULTS_DIR}"
hr

if ! command -v llama-bench &>/dev/null; then
    log "❌ FATAL: llama-bench not found.  Install: brew install llama.cpp"; exit 1
fi

MISSING=0
for V in "${VARIANTS[@]}"; do
    [ -f "${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf" ] || {
        log "  ❌ Missing: ${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf"
        MISSING=$((MISSING+1))
    }
done
[ "$MISSING" -gt 0 ] && log "❌ FATAL: $MISSING model(s) missing." && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present"
log ""

# ── Python parser (same logic as llama cliff, adapted for Qwen) ──
PARSER="/tmp/m4qwen_parse_$$.py"
cat > "$PARSER" << 'PYEOF'
import json, sys, statistics, datetime

n_prompt = int(sys.argv[1])
n_gen    = int(sys.argv[2])
variant  = sys.argv[3]
ctx      = int(sys.argv[4])
model_prefix = sys.argv[5]
ngl      = int(sys.argv[6])
threads  = int(sys.argv[7])

rows = [json.loads(l) for l in sys.stdin if l.strip().startswith('{')]

pp_row = next((r for r in rows if r.get('n_prompt')==n_prompt and r.get('n_gen')==0), None)
pg_row = next((r for r in rows if r.get('n_prompt')==n_prompt and r.get('n_gen')==n_gen), None)

if not pp_row or not pg_row:
    print(json.dumps({"variant":variant,"context":ctx,"decode_tps":0,"prefill_tps":0,"error":"missing_rows"}))
    sys.exit(0)

pp_samples = pp_row.get('samples_ts', [pp_row.get('avg_ts', 0)])
pg_samples = pg_row.get('samples_ts', [pg_row.get('avg_ts', 0)])
n = min(len(pp_samples), len(pg_samples))

gen_list = []
pre_list = list(pp_samples[:n])
for i in range(n):
    pp_ts, combined_ts = pp_samples[i], pg_samples[i]
    if pp_ts <= 0 or combined_ts <= 0: continue
    gen_time = (n_prompt + n_gen) / combined_ts - n_prompt / pp_ts
    if gen_time > 0:
        gen_list.append(n_gen / gen_time)

out = {
    "variant":     variant,
    "context":     ctx,
    "n_prompt":    n_prompt,
    "n_gen":       n_gen,
    "prefill_tps": round(statistics.mean(pre_list), 4) if pre_list else 0,
    "prefill_std": round(statistics.stdev(pre_list), 4) if len(pre_list) > 1 else 0,
    "decode_tps":  round(statistics.mean(gen_list), 4) if gen_list else 0,
    "decode_std":  round(statistics.stdev(gen_list), 4) if len(gen_list) > 1 else 0,
    "n_trials":    len(gen_list),
    "device":      "M4Mac",
    "backend":     "Metal",
    "model":       f"{model_prefix}-{variant}",
    "ngl":         ngl,
    "threads":     threads,
    "ts":          datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
}
print(json.dumps(out))
PYEOF

EXPECTED_LINES=${#CTX_SIZES[@]}
START_S=$(date +%s)
TOTAL_VARIANTS=${#VARIANTS[@]}
V_IDX=0

for VARIANT in "${VARIANTS[@]}"; do
    V_IDX=$(( V_IDX + 1 ))
    MODEL_PATH="${MODELS_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/cliff_${VARIANT}.jsonl"
    MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)

    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        DONE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
        if [ "$DONE" -ge "$EXPECTED_LINES" ]; then
            log "  ⏩ SKIP $VARIANT — already complete (${DONE} rows)"
            continue
        fi
    fi

    log ""
    log "━━━ [${V_IDX}/${TOTAL_VARIANTS}] ${VARIANT}  (${MODEL_SIZE}) ━━━"
    > "$OUTPUT_FILE"

    CTX_IDX=0
    for CTX in "${CTX_SIZES[@]}"; do
        CTX_IDX=$(( CTX_IDX + 1 ))
        PP_TOKENS=$(( CTX - TG_TOKENS ))
        ELAPSED=$(( $(date +%s) - START_S ))

        BENCH_JSON=$(llama-bench \
            -m  "$MODEL_PATH" \
            -p  "$PP_TOKENS" \
            -pg "${PP_TOKENS},${TG_TOKENS}" \
            -r  "$NUM_TRIALS" \
            -ngl "$NGL" \
            -t  "$THREADS" \
            -o  jsonl 2>/dev/null) || true

        RESULT=$(printf '%s\n' "$BENCH_JSON" | \
            python3 "$PARSER" \
                "$PP_TOKENS" "$TG_TOKENS" \
                "$VARIANT" "$CTX" \
                "$MODEL_PREFIX" "$NGL" "$THREADS" 2>/dev/null) || \
            RESULT="{\"variant\":\"${VARIANT}\",\"context\":${CTX},\"decode_tps\":0,\"prefill_tps\":0,\"error\":\"parse_failed\"}"

        printf '%s\n' "$RESULT" >> "$OUTPUT_FILE"

        DECODE=$(printf '%s\n' "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{d.get(\"decode_tps\",0):.2f}')" 2>/dev/null || echo "?")
        PREFILL=$(printf '%s\n' "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{d.get(\"prefill_tps\",0):.1f}')" 2>/dev/null || echo "?")

        log "  [ctx=${CTX} ${CTX_IDX}/${EXPECTED_LINES} elapsed=${ELAPSED}s]  ${VARIANT}  PP=${PP_TOKENS}+TG=${TG_TOKENS}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
    done

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

rm -f "$PARSER"

log ""
hr
log "CLIFF ANALYSIS  —  M4 Mac (Metal)  —  Qwen 2.5 1.5B"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys
results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
ctxs = [1024,1100,1200,1250,1300,1350,1400,1450,1500,1550,1600,1800,2048]

for variant in requested:
    paths = glob.glob(f"{results_dir}/cliff_{variant}.jsonl")
    if not paths: continue
    rows = [json.loads(l) for l in open(paths[0]) if l.strip()]
    ctx_map = {r['context']: r for r in rows}
    prev = None
    print(f"\n  {variant}:")
    for c in ctxs:
        r = ctx_map.get(c)
        d = float(r.get('decode_tps', 0)) if r else 0
        p = float(r.get('prefill_tps', 0)) if r else 0
        cliff = " ← CLIFF" if prev and d > 0 and (prev-d)/prev > 0.10 else ""
        print(f"    ctx={c:5d}:  decode={d:6.2f}  prefill={p:6.1f}{cliff}")
        if d > 0: prev = d
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
