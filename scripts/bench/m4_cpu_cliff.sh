#!/usr/bin/env bash
# ============================================================
# m4_cpu_cliff.sh  —  Llama 3.2 3B KV-cache cliff sweep
#                      M4 Mac · CPU only (ngl=0) · uses llama-bench
#
# PURPOSE: Collect filled-context cliff data for M4 CPU (no Metal GPU)
# to compare directly with:
#   - ARM Pixel 6a cliff  (results/pixel_llama_cliff_filled_canonical_n10/)
#   - M4 Metal cliff      (results/m4_metal_cliff_20260323_015934/)
#
# This establishes the CPU/GPU divide claim: M4 Metal shows no cliff
# (flat ±2%), M4 CPU should also show no cliff because the Apple M4
# has a large per-cluster L2 (~16 MB), so ctx_cliff = 16MB/1024 ≈ 16,384
# tokens — well beyond our test range.
#
# Method: for each context point C, runs:
#   1. pp-only test  (-p PP_TOKENS)           → measures prefill TPS
#   2. pg combined   (-pg PP_TOKENS,TG_TOKENS) → total time, derives gen_tps
#
# Usage:
#   bash scripts/bench/m4_cpu_cliff.sh              # all 7 variants
#   bash scripts/bench/m4_cpu_cliff.sh Q6_K Q3_K_M  # subset
#   bash scripts/bench/m4_cpu_cliff.sh --resume      # skip completed
#
# Output:  results/m4_cpu_cliff_{ts}/cliff_{VARIANT}.jsonl
# Runtime: ~4-6 h  (7 variants × 13 ctx × 5 trials, CPU is slower than Metal)
#
# After running: compare decode_tps profile across ctx values.
# Expected result: flat (no cliff) — M4 L2 >> working set at ctx=2048.
# If cliff appears: compute ctx_cliff × 1024 = effective L2 per thread.
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
MODELS_DIR="local-models/llama3_2_3b_gguf"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

# 13-point sweep: broad coverage from 256 (ARM cliff start) through 2048.
# ARM cliff occurs at ctx=512 (L2=512KB → 512KB/1024=512).
# M4 L2 >> 2MB, so no cliff predicted in this range.
# Stored as TOTAL context lengths; prompt tokens = CTX - TG_TOKENS.
CTX_SIZES=(256 320 384 448 512 640 768 896 1024 1280 1536 1792 2048)

TG_TOKENS=64          # generation tokens per trial (matches ARM cliff methodology)
NUM_TRIALS=5          # 5 repetitions per context point (matches Metal cliff depth)
NGL=0                 # CPU ONLY — no Metal GPU offloading
THREADS=4             # 4 performance cores (matches ARM Pixel 6a for cross-platform)

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/m4_cpu_cliff_${TS}"
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
log "M4 Mac  —  Llama 3.2 3B KV-Cache Cliff Sweep  (CPU only, ngl=0)"
log "Host     : $(hostname)"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS}  |  TG tokens: ${TG_TOKENS}  |  ngl: ${NGL} (CPU)"
log "Threads  : ${THREADS}"
log "Method   : filled-context (pp + pg combined → derive gen_tps)"
log "Results  : ${RESULTS_DIR}"
log ""
log "Theory: M4 L2 per cluster ≈ 16 MB → ctx_cliff = 16MB/1024 ≈ 16,384 tokens"
log "        → no cliff expected in ctx=[256..2048] range"
hr

if ! command -v llama-bench &>/dev/null; then
    log "❌ FATAL: llama-bench not found.  Install: brew install llama.cpp"
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
PARSER="/tmp/m4cpucliff_parse_$$.py"
cat > "$PARSER" << 'PYEOF'
#!/usr/bin/env python3
"""
Parse llama-bench JSONL output and derive gen_tps from combined timing.

Usage: python3 parse.py <n_prompt> <n_gen> <variant> <ctx> <device> <ngl> <threads>
Reads llama-bench JSONL from stdin; prints one JSONL result line to stdout.
"""
import json, sys, statistics, datetime

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
        except Exception:
            pass

# Find pp-only row and combined pg row
pp_row = next((r for r in rows if r.get('n_prompt') == n_prompt and r.get('n_gen') == 0),   None)
pg_row = next((r for r in rows if r.get('n_prompt') == n_prompt and r.get('n_gen') == n_gen), None)

if not pp_row or not pg_row:
    out = {
        "variant": variant, "context": ctx, "n_prompt": n_prompt, "n_gen": n_gen,
        "prefill_tps": 0, "prefill_std": 0,
        "decode_tps": 0, "decode_std": 0,
        "n_trials": 0, "device": device, "backend": "CPU",
        "model": f"Llama-3.2-3B-Instruct-{variant}",
        "ngl": ngl, "threads": threads,
        "methodology": "filled_context",
        "error": "missing_rows",
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    }
    print(json.dumps(out))
    sys.exit(0)

# Per-trial derived gen_tps using timing decomposition
pp_samples = pp_row.get('samples_ts', [pp_row.get('avg_ts', 0)])
pg_samples = pg_row.get('samples_ts', [pg_row.get('avg_ts', 0)])

n = min(len(pp_samples), len(pg_samples))
gen_tps_list = []
prefill_list = list(pp_samples[:n])

for i in range(n):
    pp_ts       = pp_samples[i]
    combined_ts = pg_samples[i]
    if pp_ts <= 0 or combined_ts <= 0:
        continue
    total_time = (n_prompt + n_gen) / combined_ts
    pp_time    = n_prompt / pp_ts
    gen_time   = total_time - pp_time
    if gen_time <= 0:
        continue
    gen_tps_list.append(n_gen / gen_time)

prefill_mean = statistics.mean(prefill_list) if prefill_list else 0
prefill_std  = statistics.stdev(prefill_list) if len(prefill_list) > 1 else 0
decode_mean  = statistics.mean(gen_tps_list) if gen_tps_list else 0
decode_std   = statistics.stdev(gen_tps_list) if len(gen_tps_list) > 1 else 0

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
    "backend":      "CPU",
    "model":        f"Llama-3.2-3B-Instruct-{variant}",
    "ngl":          ngl,
    "threads":      threads,
    "methodology":  "filled_context",
    "ts":           datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
}
print(json.dumps(out))
PYEOF

# ── Main sweep ───────────────────────────────────────────────
EXPECTED_LINES=${#CTX_SIZES[@]}   # 13 lines per variant
START_S=$(date +%s)
TOTAL_VARIANTS=${#VARIANTS[@]}
V_IDX=0

# Detect device name for output schema
DEVICE_NAME="M4Mac"
if system_profiler SPHardwareDataType 2>/dev/null | grep -q "M4 Pro\|M4 Max"; then
    DEVICE_NAME="M4ProMax"
elif system_profiler SPHardwareDataType 2>/dev/null | grep -q "M4"; then
    DEVICE_NAME="M4Mac"
fi
log "Device tag: ${DEVICE_NAME}"
log ""

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

        # Run llama-bench (CPU, ngl=0):
        #   -p PP_TOKENS        → pp-only row  (measures prefill TPS)
        #   -pg PP,TG           → combined row (measures total time, KV filled)
        #   -ngl 0              → force CPU inference, no Metal GPU
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
                "$DEVICE_NAME" "$NGL" "$THREADS" 2>/dev/null) || \
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

    # Brief cooldown between variants — M4 CPU runs warm
    if [ "$V_IDX" -lt "$TOTAL_VARIANTS" ]; then
        log "  ⏱  60-second inter-variant cooldown..."
        sleep 60
    fi
done

rm -f "$PARSER"

# ── Cliff analysis ───────────────────────────────────────────
log ""
hr
log "CLIFF ANALYSIS  —  M4 Mac (CPU, ngl=0)  —  Llama 3.2 3B"
log "Expected: flat (no cliff) for all variants — M4 L2 >> working set"
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
print(f"  Theory: M4 L2 ≈ 16 MB → ctx_cliff = 16384 tokens (beyond test range)")
PYEOF

# ── Comparison vs Metal cliff (if available) ─────────────────
log ""
hr
log "Comparison instructions:"
log "  Metal cliff: results/m4_metal_cliff_20260323_015934/"
log "  CPU   cliff: ${RESULTS_DIR}/"
log ""
log "  To compare Q2_K:"
log "    python3 - << 'EOF'"
log "    import json, glob"
log "    for backend, d in [('Metal','m4_metal_cliff_20260323_015934'), ('CPU','${RESULTS_DIR}')]:"
log "        rows = [json.loads(l) for f in glob.glob(f'results/{d}/cliff_Q2_K.jsonl')"
log "                for l in open(f) if l.strip()]"
log "        ctx_map = {r['context']: r['decode_tps'] for r in rows}"
log "        print(backend, [(c, ctx_map.get(c,0)) for c in [256,512,1024,2048]])"
log "    EOF"
hr

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
log ""
log "Next steps:"
log "  1. Review cliff analysis table above — confirm flat profile"
log "  2. Compare with Metal cliff: both should be flat (no cliff), just different TPS"
log "  3. If cliff appears at some ctx: report ctx_cliff × 1024 as effective L2"
log "  4. Add data to paper §8 Cross-Device Validation as 'M4 CPU' column"
hr
