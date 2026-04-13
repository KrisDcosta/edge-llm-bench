#!/usr/bin/env bash
# ============================================================
# m4_cpu_qwen_cliff.sh  —  Qwen 2.5 1.5B KV-cache cliff sweep
#                           M4 Mac · CPU only (ngl=0) · uses llama-bench
#
# PURPOSE: Characterise KV-cache cliff behaviour for Qwen 2.5 1.5B on
# M4 Mac CPU (no Metal GPU offloading).  Complements:
#   - m4_qwen_cliff.sh    (Metal GPU, ngl=99)
#   - m4_cpu_cliff.sh     (Llama 3.2 3B on M4 CPU)
#   - x86_qwen_cliff.py   (Qwen on x86 CPU)
#
# Qwen 2.5 1.5B is a smaller model (1.5B params vs 3B for Llama), so
# KV-cache working set per token is proportionally smaller.
# Expected: flat or attenuated cliff (similar to M4 CPU Llama profile),
# with higher absolute TPS than Llama 3.2 3B on CPU.
#
# Method: for each context point C, runs:
#   1. pp-only test  (-p PP_TOKENS)           → measures prefill TPS
#   2. pg combined   (-pg PP_TOKENS,TG_TOKENS) → total time, derives gen_tps
#   Both measured at filled context (PP_TOKENS = CTX - TG_TOKENS).
#
# Usage:
#   bash scripts/bench/m4_cpu_qwen_cliff.sh              # all 7 variants
#   bash scripts/bench/m4_cpu_qwen_cliff.sh Q6_K Q3_K_M  # subset
#   bash scripts/bench/m4_cpu_qwen_cliff.sh --resume      # skip completed
#
# Prerequisites:
#   - llama-bench in PATH (brew install llama.cpp)
#   - GGUF models at local-models/qwen2_5_1_5b_gguf/
#     (download: huggingface.co/bartowski/Qwen2.5-1.5B-Instruct-GGUF)
#
# Output:  results/m4_cpu_qwen_cliff_{ts}/cliff_{VARIANT}.jsonl
# Runtime: ~2-4 h  (7 variants × 13 ctx × 5 trials; Qwen faster than Llama on CPU)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
MODELS_DIR="local-models/qwen2_5_1_5b_gguf"
MODEL_PREFIX="Qwen2.5-1.5B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

# 13-point sweep: same grid as M4 CPU Llama for direct comparison.
# Stored as TOTAL context lengths; prompt tokens = CTX - TG_TOKENS.
CTX_SIZES=(256 320 384 448 512 640 768 896 1024 1280 1536 1792 2048)

TG_TOKENS=64          # generation tokens per trial
NUM_TRIALS=5          # repetitions per context point
NGL=0                 # CPU ONLY — no Metal GPU offloading
THREADS=4             # 4 performance cores

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/m4_cpu_qwen_cliff_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

# ── Logging ──────────────────────────────────────────────────
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
log "M4 Mac  —  Qwen 2.5 1.5B KV-Cache Cliff Sweep  (CPU only, ngl=0)"
log "Host     : $(hostname)"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS}  |  TG tokens: ${TG_TOKENS}  |  ngl: ${NGL} (CPU)"
log "Threads  : ${THREADS}"
log "Method   : filled-context (pp + pg combined → derive gen_tps)"
log "Results  : ${RESULTS_DIR}"
log ""
log "Note: Qwen 2.5 1.5B has fewer KV heads than Llama 3.2 3B."
log "      KV working set per token is smaller, so cliff threshold is higher."
hr

if ! command -v llama-bench &>/dev/null; then
    log "❌ FATAL: llama-bench not found."
    log "   Install: brew install llama.cpp"
    log "   Or build from source: cmake -B build && cmake --build build --config Release"
    exit 1
fi
LLAMA_VER=$(llama-bench --version 2>&1 | head -1 || llama-bench 2>&1 | grep "build:" | head -1 || echo "unknown")
log "✅ llama-bench: $(which llama-bench)  |  ${LLAMA_VER}"

MISSING=0
for V in "${VARIANTS[@]}"; do
    [ -f "${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf" ] || {
        log "  ❌ Missing: ${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf"
        MISSING=$((MISSING+1))
    }
done
[ "$MISSING" -gt 0 ] && { log "❌ FATAL: $MISSING model(s) missing."; exit 1; }
log "✅ All ${#VARIANTS[@]} model(s) present"
log ""

# ── Python helper: parse llama-bench JSONL → derived gen_tps ─
PARSER="/tmp/m4cpuqwen_parse_$$.py"
cat > "$PARSER" << 'PYEOF'
#!/usr/bin/env python3
"""
Parse llama-bench JSONL output and derive gen_tps from combined timing.
Usage: python3 parse.py <n_prompt> <n_gen> <variant> <ctx> <model_prefix> <ngl> <threads>
"""
import json, sys, statistics, datetime

n_prompt     = int(sys.argv[1])
n_gen        = int(sys.argv[2])
variant      = sys.argv[3]
ctx          = int(sys.argv[4])
model_prefix = sys.argv[5]
ngl          = int(sys.argv[6])
threads      = int(sys.argv[7])

rows = []
for line in sys.stdin:
    line = line.strip()
    if line.startswith('{'):
        try:
            rows.append(json.loads(line))
        except Exception:
            pass

pp_row = next((r for r in rows if r.get('n_prompt') == n_prompt and r.get('n_gen') == 0),    None)
pg_row = next((r for r in rows if r.get('n_prompt') == n_prompt and r.get('n_gen') == n_gen), None)

if not pp_row or not pg_row:
    out = {
        "variant": variant, "context": ctx, "n_prompt": n_prompt, "n_gen": n_gen,
        "prefill_tps": 0, "prefill_std": 0,
        "decode_tps": 0, "decode_std": 0, "n_trials": 0,
        "device": "M4Mac", "backend": "CPU",
        "model": f"{model_prefix}-{variant}",
        "ngl": ngl, "threads": threads,
        "methodology": "filled_context",
        "error": "missing_rows",
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    print(json.dumps(out))
    sys.exit(0)

pp_samples = pp_row.get('samples_ts', [pp_row.get('avg_ts', 0)])
pg_samples = pg_row.get('samples_ts', [pg_row.get('avg_ts', 0)])
n = min(len(pp_samples), len(pg_samples))

gen_tps_list, prefill_list = [], list(pp_samples[:n])
for i in range(n):
    pp_ts, combined_ts = pp_samples[i], pg_samples[i]
    if pp_ts <= 0 or combined_ts <= 0:
        continue
    gen_time = (n_prompt + n_gen) / combined_ts - n_prompt / pp_ts
    if gen_time > 0:
        gen_tps_list.append(n_gen / gen_time)

out = {
    "variant":      variant,
    "context":      ctx,
    "n_prompt":     n_prompt,
    "n_gen":        n_gen,
    "prefill_tps":  round(statistics.mean(prefill_list),   4) if prefill_list  else 0,
    "prefill_std":  round(statistics.stdev(prefill_list),  4) if len(prefill_list)  > 1 else 0,
    "decode_tps":   round(statistics.mean(gen_tps_list),   4) if gen_tps_list  else 0,
    "decode_std":   round(statistics.stdev(gen_tps_list),  4) if len(gen_tps_list)  > 1 else 0,
    "n_trials":     len(gen_tps_list),
    "device":       "M4Mac",
    "backend":      "CPU",
    "model":        f"{model_prefix}-{variant}",
    "ngl":          ngl,
    "threads":      threads,
    "methodology":  "filled_context",
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
        log "  ↩  RESUME $VARIANT — ${DONE}/${EXPECTED_LINES} done; re-running all"
    fi

    log ""
    log "━━━ [${V_IDX}/${TOTAL_VARIANTS}] ${VARIANT}  (${MODEL_SIZE}) ━━━"
    > "$OUTPUT_FILE"

    CTX_IDX=0
    for CTX in "${CTX_SIZES[@]}"; do
        CTX_IDX=$(( CTX_IDX + 1 ))
        PP_TOKENS=$(( CTX - TG_TOKENS ))
        ELAPSED=$(( $(date +%s) - START_S ))

        log "  [${CTX_IDX}/${EXPECTED_LINES}] ctx=${CTX}  pp=${PP_TOKENS}+tg=${TG_TOKENS}  elapsed=${ELAPSED}s"

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
            RESULT="{\"variant\":\"${VARIANT}\",\"context\":${CTX},\"decode_tps\":0,\"error\":\"parse_failed\"}"

        printf '%s\n' "$RESULT" >> "$OUTPUT_FILE"

        DECODE=$(printf '%s\n' "$RESULT" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); print(f'{d.get(\"decode_tps\",0):.2f}')" 2>/dev/null || echo "?")
        PREFILL=$(printf '%s\n' "$RESULT" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); print(f'{d.get(\"prefill_tps\",0):.1f}')" 2>/dev/null || echo "?")

        log "      → decode=${DECODE} t/s  prefill=${PREFILL} t/s"
    done

    SAVED=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
    log "  ✅ Saved ${OUTPUT_FILE}  (${SAVED} / ${EXPECTED_LINES} rows)"

    if [ "$V_IDX" -lt "$TOTAL_VARIANTS" ]; then
        log "  ⏱  60-second inter-variant cooldown..."
        sleep 60
    fi
done

rm -f "$PARSER"

# ── Cliff analysis ───────────────────────────────────────────
log ""
hr
log "CLIFF ANALYSIS  —  M4 Mac (CPU, ngl=0)  —  Qwen 2.5 1.5B"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
ctx_points  = [256, 320, 384, 448, 512, 640, 768, 896, 1024, 1280, 1536, 1792, 2048]

print(f"\n  {'Variant':<10}  ", end="")
for c in ctx_points:
    print(f"c={c:<5}", end="")
print()
print("  " + "-" * 90)

for variant in requested:
    paths = glob.glob(f"{results_dir}/cliff_{variant}.jsonl")
    if not paths:
        print(f"  {variant:<10}  [no data]")
        continue
    rows = [json.loads(l) for l in open(paths[0]) if l.strip()]
    ctx_map = {r['context']: r for r in rows if 'context' in r}

    baseline = None
    print(f"  {variant:<10}  ", end="")
    for c in ctx_points:
        r = ctx_map.get(c)
        if r and r.get('decode_tps', 0) > 0:
            d = float(r['decode_tps'])
            if baseline is None:
                baseline = d
                marker = "  "
            else:
                pct = (d - baseline) / baseline * 100
                marker = f"↓{abs(pct):.0f}%" if pct < -10 else "  "
            print(f"{d:5.2f}{marker}", end="")
        else:
            print(f"{'ERR':>8}  ", end="")
    print()

print()
print("  Legend: ↓N% = >10% drop from ctx=256 baseline (cliff indicator)")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
log ""
log "Next steps:"
log "  1. Integrate results: python3 scripts/prepare_dataset.py"
log "  2. Bake dashboard: python3 scripts/bake_dashboard_data.py"
log "  3. Compare with m4_cpu_cliff.sh (Llama) and m4_qwen_cliff.sh (Metal) results"
hr
