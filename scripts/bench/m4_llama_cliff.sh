#!/usr/bin/env bash
# ============================================================
# m4_llama_cliff.sh  —  Llama 3.2 3B KV-cache cliff sweep
#                        M4 Mac · Metal GPU · uses llama-bench
#
# Uses llama-bench (the official benchmark binary) instead of
# llama-cli to avoid interactive-mode and stdin issues.
#
# Method: for each context point C, runs:
#   1. pp-only test  (-p PP_TOKENS)          → measures prefill_tps
#   2. pg combined   (-pg PP_TOKENS,TG_TOKENS) → measures combined time
# Then derives: gen_tps = TG / (total_time - PP/prefill_tps)
#
# Usage:
#   bash scripts/bench/m4_llama_cliff.sh              # all 7 variants
#   bash scripts/bench/m4_llama_cliff.sh Q6_K Q3_K_M  # subset
#   bash scripts/bench/m4_llama_cliff.sh --resume      # skip completed
#
# Output:  results/m4_llama_cliff_{ts}/cliff_{VARIANT}.jsonl
# Runtime: ~3-4 h  (7 variants × 13 ctx × 5 trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
MODELS_DIR="local-models/llama3_2_3b_gguf"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

# Fine-grained cliff sweep: 13 points around the known cliff (1400–1550)
# Stored as TOTAL context lengths; prompt tokens = CTX - TG_TOKENS
CTX_SIZES=(1024 1100 1200 1250 1300 1350 1400 1450 1500 1550 1600 1800 2048)
TG_TOKENS=32          # generation tokens per trial
NUM_TRIALS=5          # repetitions per context point (llama-bench -r)
NGL=99                # Metal: offload all layers
THREADS=4

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/m4_llama_cliff_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

# ── Logging: stdout + file, no tee pipes ─────────────────────
log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

# ── Argument parsing ─────────────────────────────────────────
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

# ── Preflight ────────────────────────────────────────────────
hr
log "M4 Mac  —  Llama 3.2 3B KV-Cache Cliff Sweep  (Metal GPU, llama-bench)"
log "Host     : $(hostname)"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS}  |  TG tokens: ${TG_TOKENS}  |  ngl: ${NGL}"
log "Method   : pp-only + pg combined → derive gen_tps = TG/(total_t - PP/pp_ts)"
log "Results  : ${RESULTS_DIR}"
hr

if ! command -v llama-bench &>/dev/null; then
    log "❌ FATAL: llama-bench not found.  Install: brew install llama.cpp"; exit 1
fi
LLAMA_VER=$(llama-bench 2>&1 | grep "build:" | head -1 || echo "unknown")
log "✅ llama-bench: $(which llama-bench)  |  ${LLAMA_VER}"

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

# ── Python helper for llama-bench JSONL parsing ──────────────
# Writes a helper script we call per variant
PARSER="/tmp/m4cliff_parse_$$.py"
cat > "$PARSER" << 'PYEOF'
#!/usr/bin/env python3
"""
Parse llama-bench JSONL output and derive gen_tps from combined timing.

Usage: python3 parse.py <n_prompt> <n_gen> <variant> <ctx> <trial_i> <results_jsonl>

Reads llama-bench JSONL from stdin (one JSON per line, pp row then pg row).
Prints one JSONL result line to stdout.
"""
import json, sys, statistics

n_prompt = int(sys.argv[1])
n_gen    = int(sys.argv[2])
variant  = sys.argv[3]
ctx      = int(sys.argv[4])
device   = sys.argv[5]
ngl      = int(sys.argv[6])
threads  = int(sys.argv[7])

rows = []
for line in sys.stdin:
    line = line.strip()
    if line.startswith('{'):
        try:
            rows.append(json.loads(line))
        except:
            pass

# Find pp-only row and pg row
pp_row = next((r for r in rows if r.get('n_prompt')==n_prompt and r.get('n_gen')==0), None)
pg_row = next((r for r in rows if r.get('n_prompt')==n_prompt and r.get('n_gen')==n_gen), None)

if not pp_row or not pg_row:
    # Fallback: emit zeros
    out = {
        "variant": variant, "context": ctx, "n_prompt": n_prompt, "n_gen": n_gen,
        "prefill_tps": 0, "prefill_std": 0,
        "decode_tps": 0, "decode_std": 0,
        "n_trials": 0, "device": device, "backend": "Metal",
        "model": f"Llama-3.2-3B-Instruct-{variant}", "ngl": ngl, "threads": threads,
        "error": "missing_rows"
    }
    print(json.dumps(out))
    sys.exit(0)

# Per-sample computation for accuracy
pp_samples  = pp_row.get('samples_ts', [pp_row.get('avg_ts', 0)])
pg_samples  = pg_row.get('samples_ts', [pg_row.get('avg_ts', 0)])

n = min(len(pp_samples), len(pg_samples))
gen_tps_list  = []
prefill_list  = list(pp_samples[:n])

for i in range(n):
    pp_ts       = pp_samples[i]
    combined_ts = pg_samples[i]
    if pp_ts <= 0 or combined_ts <= 0:
        continue
    total_time  = (n_prompt + n_gen) / combined_ts
    pp_time     = n_prompt / pp_ts
    gen_time    = total_time - pp_time
    if gen_time <= 0:
        continue
    gen_tps_list.append(n_gen / gen_time)

prefill_mean = statistics.mean(prefill_list) if prefill_list else 0
prefill_std  = statistics.stdev(prefill_list) if len(prefill_list) > 1 else 0
decode_mean  = statistics.mean(gen_tps_list) if gen_tps_list else 0
decode_std   = statistics.stdev(gen_tps_list) if len(gen_tps_list) > 1 else 0

import datetime
out = {
    "variant":      variant,
    "context":      ctx,
    "n_prompt":     n_prompt,
    "n_gen":        n_gen,
    "prefill_tps":  round(prefill_mean, 4),
    "prefill_std":  round(prefill_std,  4),
    "decode_tps":   round(decode_mean,  4),
    "decode_std":   round(decode_std,   4),
    "n_trials":     len(gen_tps_list),
    "device":       device,
    "backend":      "Metal",
    "model":        f"Llama-3.2-3B-Instruct-{variant}",
    "ngl":          ngl,
    "threads":      threads,
    "ts":           datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
}
print(json.dumps(out))
PYEOF

# ── Main sweep ───────────────────────────────────────────────
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
        log "  ↩  RESUME $VARIANT — ${DONE}/${EXPECTED_LINES} done; re-running"
    fi

    log ""
    log "━━━ [${V_IDX}/${TOTAL_VARIANTS}] ${VARIANT}  (${MODEL_SIZE}) ━━━"
    > "$OUTPUT_FILE"

    CTX_IDX=0
    for CTX in "${CTX_SIZES[@]}"; do
        CTX_IDX=$(( CTX_IDX + 1 ))
        PP_TOKENS=$(( CTX - TG_TOKENS ))
        ELAPSED=$(( $(date +%s) - START_S ))

        # Run llama-bench: pp-only then pg combined in ONE call
        # -p PP_TOKENS   → pp-only test (measures prefill TPS)
        # -pg PP,TG      → combined (measures total time with filled KV)
        BENCH_JSON=$(llama-bench \
            -m  "$MODEL_PATH" \
            -p  "$PP_TOKENS" \
            -pg "${PP_TOKENS},${TG_TOKENS}" \
            -r  "$NUM_TRIALS" \
            -ngl "$NGL" \
            -t  "$THREADS" \
            -o  jsonl 2>/dev/null) || true

        # Parse and derive gen_tps
        RESULT=$(printf '%s\n' "$BENCH_JSON" | \
            python3 "$PARSER" \
                "$PP_TOKENS" "$TG_TOKENS" \
                "$VARIANT" "$CTX" \
                "M4Mac" "$NGL" "$THREADS" 2>/dev/null) || \
            RESULT="{\"variant\":\"${VARIANT}\",\"context\":${CTX},\"decode_tps\":0,\"prefill_tps\":0,\"error\":\"parse_failed\"}"

        printf '%s\n' "$RESULT" >> "$OUTPUT_FILE"

        # Extract for display
        DECODE=$(printf '%s\n' "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{d.get(\"decode_tps\",0):.2f}')" 2>/dev/null || echo "?")
        PREFILL=$(printf '%s\n' "$RESULT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{d.get(\"prefill_tps\",0):.1f}')" 2>/dev/null || echo "?")

        log "  [ctx=${CTX} ${CTX_IDX}/${EXPECTED_LINES} elapsed=${ELAPSED}s]  ${VARIANT}  PP=${PP_TOKENS}+TG=${TG_TOKENS}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
    done

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

rm -f "$PARSER"

# ── Cliff analysis ───────────────────────────────────────────
log ""
hr
log "CLIFF ANALYSIS  —  M4 Mac (Metal)  —  Llama 3.2 3B"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

print(f"\n  {'Variant':<10}  ", end="")
for c in [1024,1100,1200,1250,1300,1350,1400,1450,1500,1550,1600,1800,2048]:
    print(f"ctx={c:5d}  ", end="")
print()

for variant in requested:
    paths = glob.glob(f"{results_dir}/cliff_{variant}.jsonl")
    if not paths: continue
    rows = [json.loads(l) for l in open(paths[0]) if l.strip()]
    ctx_map = {r['context']: r for r in rows}

    print(f"\n  {variant:<10}  ", end="")
    prev = None
    for c in [1024,1100,1200,1250,1300,1350,1400,1450,1500,1550,1600,1800,2048]:
        r = ctx_map.get(c)
        if r:
            d = float(r.get('decode_tps', 0))
            if d > 0:
                cliff = " ↓" if prev and (prev-d)/prev > 0.10 else "  "
                print(f"{d:5.1f}{cliff}  ", end="")
                prev = d
            else:
                print(f"{'ERR':>8}  ", end="")
        else:
            print(f"{'N/A':>8}  ", end="")
    print()
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
