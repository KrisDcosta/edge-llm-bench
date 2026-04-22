#!/usr/bin/env bash
# ============================================================
# m4_cpu_tps.sh  —  Llama 3.2 3B baseline TPS sweep
#                    M4 Mac · CPU only (ngl=0) · uses llama-bench
#
# This is the CORRECTED re-run script replacing the corrupt
# m4_mac_cpu_20260317_* data (removed from the public tree).
#
# Root cause of previous corruption:
#   - Old script parsed 'recommendedMaxWorkingSetSize = 19069.67 MB'
#     (GPU init log line) as decode_tps — NOT a throughput value.
#   - Old script wrote pretty-printed multi-line JSON (not valid JSONL).
#
# Fix: Use llama-bench with -ngl 0 (CPU-only inference, no Metal GPU).
#   llama-bench outputs clean JSON rows; no log-line scraping needed.
#
# Usage:
#   bash scripts/bench/m4_cpu_tps.sh              # all 7 variants
#   bash scripts/bench/m4_cpu_tps.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/m4_cpu_tps.sh --resume      # skip completed
#
# Output:  results/m4_cpu_tps_{ts}/tps_{VARIANT}.jsonl
# Runtime: ~90-120 min  (7 variants × 4 ctx × 10 trials, CPU is slow)
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
NGL=0          # CPU only — no Metal GPU offloading
THREADS=4      # Match Pixel 6a (4 P-cores) for cross-platform comparison

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/m4_cpu_tps_${TS}"
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
log "M4 Mac  —  Llama 3.2 3B Baseline TPS Sweep  (CPU only, ngl=0, llama-bench)"
log "Host     : $(hostname)"
log "Variants : ${VARIANTS[*]}"
log "NGL      : ${NGL} (CPU-only — Metal GPU disabled)"
log "Threads  : ${THREADS}"
log "PP sizes : ${PP_TOKENS[*]}  |  TG: ${TG_TOKENS}  |  Trials: ${NUM_TRIALS}"
log "Results  : ${RESULTS_DIR}"
hr

if ! command -v llama-bench &>/dev/null; then
    log "❌ FATAL: llama-bench not found. Install llama.cpp first."
    exit 1
fi

# Verify all models present
MISSING=0
for V in "${VARIANTS[@]}"; do
    [ -f "${MODELS_DIR}/${MODEL_PREFIX}-${V}.gguf" ] || { log "  ❌ Missing: ${V}"; MISSING=$((MISSING+1)); }
done
[ "$MISSING" -gt 0 ] && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present"
log ""

# ── Python parser: converts llama-bench JSONL output → project JSONL schema ──
# Key difference from old script: llama-bench outputs proper JSON rows.
# We do NOT parse raw log text. No risk of scraping GPU init log lines.
PARSE_SCRIPT=$(mktemp /tmp/m4cpu_parse.XXXXXX.py)
SUMMARY_SCRIPT=$(mktemp /tmp/m4cpu_summary.XXXXXX.py)
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
    # llama-bench outputs samples_ts (list of per-trial TPS) or avg_ts (scalar)
    samples = d.get('samples_ts', [])
    if not samples:
        avg = d.get('avg_ts', 0)
        if avg > 0:
            samples = [avg]
    if not samples:
        continue

    mean_ts = statistics.mean(samples)
    std_ts  = statistics.stdev(samples) if len(samples) > 1 else 0.0

    # Sanity check: reject obviously corrupt values
    # 19069.67 is recommendedMaxWorkingSetSize in MB — if this appears, abort.
    if mean_ts > 10000:
        print(f"FATAL: Suspiciously high TPS={mean_ts:.2f} for {variant} n_prompt={np} n_gen={ng}. "
              f"Possible log-line contamination. Aborting row.", file=sys.stderr)
        continue

    out = {
        "variant":    variant,
        "n_prompt":   np,
        "n_gen":      ng,
        "test_type":  "pp" if ng == 0 else "tg",
        "tps_mean":   round(mean_ts, 4),
        "tps_std":    round(std_ts, 4),
        "n_trials":   len(samples),
        "device":     "M4Mac",
        "backend":    "CPU",          # CPU-only (ngl=0)
        "model":      f"{model_prefix}-{variant}",
        "ngl":        ngl,
        "threads":    threads,
        "ts":         datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    # Single-line JSON — valid JSONL format
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
        line = line.strip()
        if not line:
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
    if v not in pp_map and v not in tg_dict:
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

    PP_ARG=$(IFS=,; echo "${PP_TOKENS[*]}")

    # Run llama-bench with -ngl 0 (CPU only — no Metal GPU)
    BENCH_JSON=$(llama-bench \
        -m   "$MODEL_PATH" \
        -p   "$PP_ARG" \
        -n   "$TG_TOKENS" \
        -r   "$NUM_TRIALS" \
        -ngl "$NGL" \
        -t   "$THREADS" \
        -o   jsonl 2>/dev/null) || true

    # Parse each row and save as single-line JSONL
    printf '%s\n' "$BENCH_JSON" | python3 "$PARSE_SCRIPT" "$VARIANT" "$MODEL_PREFIX" "$NGL" "$THREADS" \
        >> "$OUTPUT_FILE"

    SAVED=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
    if [ "$SAVED" -lt "$EXPECTED_LINES" ]; then
        log "  ⚠️  WARNING: expected ${EXPECTED_LINES} rows, got ${SAVED} — check output"
    else
        log "  ✅ Saved ${OUTPUT_FILE}  (${SAVED} rows)"
    fi

    # Verify no corrupt values leaked through
    CORRUPT=$(grep -c '"tps_mean": 190[0-9][0-9]' "$OUTPUT_FILE" 2>/dev/null || echo 0)
    if [ "$CORRUPT" -gt 0 ]; then
        log "  ❌ ABORT: Found $CORRUPT corrupt TPS values (GPU memory spec leak). Check parser."
        exit 1
    fi

    # Brief cooldown between variants (CPU runs hot)
    [ "$V_IDX" -lt "${#VARIANTS[@]}" ] && sleep 30
done

log ""
hr
log "TPS SUMMARY  —  M4 Mac (CPU only, ngl=0)  —  Llama 3.2 3B"
hr

python3 "$SUMMARY_SCRIPT" "$RESULTS_DIR" "${VARIANTS[@]}"

log ""
log "VALIDATION CHECKS:"
log "  1. Check all tg128 TPS values are reasonable (expected ~3-15 tok/s for CPU)"
log "  2. Verify no value equals 19069.67 (GPU memory spec contamination)"
log "  3. Compare ordering to ARM Pixel 6a: Q2_K fastest, Q6_K slowest expected"
log "  4. Update DATA_GAPS.md and registry.yaml after validation"

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
