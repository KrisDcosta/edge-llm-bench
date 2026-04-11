#!/usr/bin/env bash
# ============================================================
# pixel_cliff_rerun_n10_isolated.sh  —  Isolated n=10 cliff re-run
#                                        Pixel 6a · CPU (4 threads) · via ADB
#
# PURPOSE
# -------
# Replacement for contaminated n=10 cliff runs for Q4_K_M and Q5_K_M.
# This script enforces strict isolation to prevent the two failure modes
# that invalidated the 20260329 runs:
#
#   Failure 1 (Q4_K_M): Thermal recovery artifact
#     Device cooled overnight; ctx=1800-2048 showed 35% speedup vs ctx=256.
#     Fix: Check thermal state before starting; abort if <35°C (too cool =
#     frequency scaling not yet at steady state) or >45°C (throttling).
#     Target: 38-43°C battery temp (normal operating range after 5-10 min use).
#
#   Failure 2 (Q5_K_M): Concurrent process contamination
#     llama-perplexity and pixel_qwen_cliff_filled ran simultaneously;
#     ctx=1500+ crashed to 1.6 t/s.
#     Fix: Kill all llama* and perplexity processes on device before starting.
#     Verify no competing processes remain throughout the run.
#
# ISOLATION PROTOCOL
# ------------------
#   1. Kill all llama*, perplexity*, benchmark* processes on device
#   2. Check battery temperature: wait until 38-43°C (steady-state)
#   3. Lock to performance cores (taskset 0xC0 = Cortex-X1 cores 6-7)
#      to reduce scheduler variance
#   4. Run single variant, n=10, all 11 context sizes
#   5. Verify no competing processes started mid-run (check every ctx sweep)
#   6. Log thermal readings at each context size
#
# USAGE
#   bash scripts/bench/pixel_cliff_rerun_n10_isolated.sh Q4_K_M
#   bash scripts/bench/pixel_cliff_rerun_n10_isolated.sh Q5_K_M
#   bash scripts/bench/pixel_cliff_rerun_n10_isolated.sh Q4_K_M --skip-thermal
#   bash scripts/bench/pixel_cliff_rerun_n10_isolated.sh Q4_K_M --resume
#
# OUTPUT
#   results/pixel_cliff_rerun_{VARIANT}_{ts}/cliff_filled_{VARIANT}.jsonl
#   results/pixel_cliff_rerun_{VARIANT}_{ts}.log
#   JSONL records include provenance="rerun_n10_isolated_2026" field
#
# RUNTIME: ~3.5-4 h per variant (11 ctx × 10 trials × ~2 min/run)
#
# INTEGRATION (after successful run)
#   1. Run validation:
#      python3 scripts/analyze/validate_cliff_rerun.py results/pixel_cliff_rerun_{VARIANT}_{ts}/
#   2. If validation passes, copy to canonical dir:
#      cp results/pixel_cliff_rerun_{VARIANT}_{ts}/cliff_filled_{VARIANT}.jsonl \
#         results/pixel_llama_cliff_filled_canonical_n10/
#   3. Update results/pixel_llama_cliff_filled_canonical_n10/PROVENANCE.md
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"

# Identical to canonical dataset — do not change
CTX_SIZES=(256 512 768 1024 1200 1300 1400 1500 1600 1800 2048)
NUM_TRIALS=10
OUTPUT_TOKENS=64
THREADS=4

# Thermal thresholds (battery temp via /sys/class/power_supply/battery/temp)
# Value is in tenths of a degree: 380 = 38.0°C
THERMAL_MIN=380   # below this = too cold (freq scaling not at steady state)
THERMAL_MAX=450   # above this = throttling risk
THERMAL_WAIT_S=60 # seconds to wait between thermal checks
THERMAL_WARMUP_CMD="for i in \$(seq 1 3); do ${LLAMA_BIN} -m ${DEVICE_DIR}/${MODEL_PREFIX}-Q4_K_M.gguf -c 256 -n 64 -p 'warm' -t 4 2>/dev/null; done"

# Process isolation: kill patterns on device before starting
KILL_PATTERNS=("llama-completion" "llama-perplexity" "llama-cli" "benchmark_runner")

# Seed text for prompt generation (same as pixel_llama_cliff_filled.sh)
SEED_TEXT="The transformer architecture fundamentally changed natural language processing by introducing self-attention mechanisms that allow models to relate different positions of a sequence when computing a representation. Unlike recurrent networks, transformers process sequences in parallel and use positional encodings to maintain order information. Each transformer block consists of a multi-head attention layer followed by a feed-forward network, with layer normalization and residual connections enabling stable training of deep models. The key innovation is the attention mechanism itself: for each token, attention computes a weighted sum of all other token representations, where weights are determined by learned query and key projections. This allows long-range dependencies to be captured in a single layer. Modern large language models scale this architecture to billions of parameters across dozens of layers, using grouped-query attention and other efficiency improvements to reduce memory requirements during inference."

generate_prompt() {
    local target_tokens=$1
    local target_chars=$(( target_tokens * 13 / 10 ))
    local text=""
    while [ ${#text} -lt $target_chars ]; do
        text="${text} ${SEED_TEXT}"
    done
    echo "${text:0:$target_chars}"
}

# ── Parse arguments ────────────────────────────────────────────
VARIANT=""
SKIP_THERMAL=0
RESUME=0

for arg in "$@"; do
    case "$arg" in
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANT="$arg" ;;
        --skip-thermal) SKIP_THERMAL=1 ;;
        --resume)       RESUME=1 ;;
        *) printf 'Unknown argument: %s\n' "$arg" >&2
           printf 'Usage: %s <VARIANT> [--skip-thermal] [--resume]\n' "$0" >&2
           exit 1 ;;
    esac
done

if [ -z "$VARIANT" ]; then
    printf 'ERROR: Specify a variant: Q4_K_M or Q5_K_M\n' >&2
    printf 'Usage: bash %s Q4_K_M\n' "$0" >&2
    exit 1
fi

MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_cliff_rerun_${VARIANT}_${TS}"
LOGFILE="${RESULTS_DIR}.log"
OUTPUT_FILE="${RESULTS_DIR}/cliff_filled_${VARIANT}.jsonl"
mkdir -p "$RESULTS_DIR" results

log()  { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()   { log "$(printf '=%.0s' $(seq 72))"; }
warn() { log "  WARNING: $*"; }
die()  { log "FATAL: $*"; exit 1; }

# ── Banner ─────────────────────────────────────────────────────
hr
log "Pixel 6a  —  ISOLATED n=10 Cliff Re-run  —  ${VARIANT}"
log "Provenance  : rerun_n10_isolated_2026 (replaces contaminated 20260329)"
log "Contexts    : ${CTX_SIZES[*]}"
log "Trials      : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
log "Results     : ${RESULTS_DIR}"
log "Thermal     : $([ $SKIP_THERMAL -eq 1 ] && echo 'SKIPPED (--skip-thermal)' || echo "wait for ${THERMAL_MIN}–${THERMAL_MAX} (tenths °C)")"
hr

# ── Preflight: device ──────────────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    die "No Android device connected. Connect USB and enable USB debugging."
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "Device: ${DEVICE_ID}"

if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    die "${LLAMA_BIN} not found on device."
fi
log "llama-completion: found"

if ! adb shell "ls ${MODEL_PATH} 2>/dev/null" | grep -q ".gguf"; then
    die "Model not found on device: ${MODEL_PATH}"
fi
log "Model: found (${MODEL_PATH})"

# ── Step 1: Kill all competing processes ───────────────────────
log ""
log "=== ISOLATION: Killing background llama processes ==="
KILLED=0
for PATTERN in "${KILL_PATTERNS[@]}"; do
    PIDS=$(adb shell "ps -e 2>/dev/null | grep '${PATTERN}' | grep -v grep | awk '{print \$2}'" 2>/dev/null || echo "")
    if [ -n "$PIDS" ]; then
        for PID in $PIDS; do
            adb shell "kill -9 ${PID} 2>/dev/null" || true
            log "  Killed PID ${PID} (${PATTERN})"
            KILLED=$(( KILLED + 1 ))
        done
    fi
done
if [ "$KILLED" -eq 0 ]; then
    log "  No competing processes found — device is clean"
else
    log "  Killed ${KILLED} process(es). Waiting 5s for cleanup..."
    sleep 5
fi

# Verify clean
REMAINING=$(adb shell "ps -e 2>/dev/null | grep -E 'llama|perplexity' | grep -v grep" 2>/dev/null || echo "")
if [ -n "$REMAINING" ]; then
    warn "Processes still running after kill:"
    printf '%s\n' "$REMAINING" | while read -r line; do warn "  $line"; done
    warn "Proceeding anyway — monitor manually"
fi
log "  Process isolation: complete"

# ── Step 2: Thermal check ──────────────────────────────────────
log ""
log "=== THERMAL CHECK ==="

get_thermal() {
    # Try battery temp first, then CPU thermal zone
    BATT=$(adb shell "cat /sys/class/power_supply/battery/temp 2>/dev/null || echo 0")
    BATT=$(printf '%s' "$BATT" | tr -d '[:space:]')
    if [ "${BATT:-0}" -gt 0 ] 2>/dev/null; then
        echo "$BATT"
    else
        # Fallback: thermal zone 0
        TZ=$(adb shell "cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null || echo 0")
        TZ=$(printf '%s' "$TZ" | tr -d '[:space:]')
        echo "${TZ:-0}"
    fi
}

if [ "$SKIP_THERMAL" -eq 1 ]; then
    log "  Thermal check skipped (--skip-thermal). Proceeding immediately."
else
    TEMP=$(get_thermal)
    log "  Current temp: ${TEMP} (tenths °C = $(echo "scale=1; ${TEMP:-0}/10" | bc)°C)"

    # If too cold, do warmup runs
    if [ "${TEMP:-0}" -lt "$THERMAL_MIN" ] 2>/dev/null; then
        log "  Device too cold (${TEMP} < ${THERMAL_MIN}). Running warmup..."
        log "  Warmup: 3 short inference passes to bring device to steady-state temp..."
        # Run a warmup model that exists (use whatever variant we're benchmarking)
        adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
            for i in 1 2 3; do \
                ${LLAMA_BIN} -m ${MODEL_PATH} -c 256 -n 32 -p 'warm' -t ${THREADS} 2>/dev/null; \
            done" 2>/dev/null || true
        sleep 10
        TEMP=$(get_thermal)
        log "  Post-warmup temp: ${TEMP}"
    fi

    # Wait for temp to settle in range
    WAIT_ITERS=0
    while true; do
        TEMP=$(get_thermal)
        TEMP_C=$(printf '%.1f' "$(echo "scale=1; ${TEMP:-0}/10" | bc 2>/dev/null || echo 0)")
        if [ "${TEMP:-0}" -ge "$THERMAL_MIN" ] && [ "${TEMP:-0}" -le "$THERMAL_MAX" ] 2>/dev/null; then
            log "  Thermal OK: ${TEMP} (${TEMP_C}°C) — in range [${THERMAL_MIN},${THERMAL_MAX}]"
            break
        elif [ "${TEMP:-0}" -gt "$THERMAL_MAX" ] 2>/dev/null; then
            log "  Too hot (${TEMP_C}°C > $(echo "scale=1; ${THERMAL_MAX}/10" | bc)°C). Waiting ${THERMAL_WAIT_S}s to cool..."
            sleep "$THERMAL_WAIT_S"
        else
            log "  Too cold (${TEMP_C}°C < $(echo "scale=1; ${THERMAL_MIN}/10" | bc)°C). Waiting ${THERMAL_WAIT_S}s for warmup..."
            sleep "$THERMAL_WAIT_S"
        fi
        WAIT_ITERS=$(( WAIT_ITERS + 1 ))
        if [ "$WAIT_ITERS" -gt 20 ]; then
            warn "Thermal wait exceeded 20 min. Proceeding anyway (temp=${TEMP})."
            break
        fi
    done
fi

# ── Step 3: Main sweep ─────────────────────────────────────────
log ""
log "=== CLIFF SWEEP: ${VARIANT} (n=${NUM_TRIALS} per context) ==="

EXPECTED_LINES=$(( ${#CTX_SIZES[@]} * NUM_TRIALS ))
TOTAL_RUNS="$EXPECTED_LINES"
CURRENT_RUN=0
START_S=$(date +%s)

if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
    DONE=$(wc -l < "$OUTPUT_FILE" | tr -d ' ')
    log "Resuming: ${DONE}/${EXPECTED_LINES} rows already present"
    CURRENT_RUN="$DONE"
else
    > "$OUTPUT_FILE"
fi

CTX_IDX=0
for CTX in "${CTX_SIZES[@]}"; do
    CTX_IDX=$(( CTX_IDX + 1 ))

    # Check for competing processes every new context size
    COMPETING=$(adb shell "ps -e 2>/dev/null | grep -E 'llama|perplexity' | grep -v grep | grep -v '$$'" 2>/dev/null || echo "")
    if [ -n "$COMPETING" ]; then
        warn "Competing process detected at ctx=${CTX}:"
        printf '%s\n' "$COMPETING" | while read -r line; do warn "  $line"; done
        warn "ISOLATION BREACH — results at ctx=${CTX} may be contaminated."
        warn "Consider aborting and re-running (bash $0 $VARIANT --resume)"
    fi

    # Get thermal reading before each ctx block
    TEMP_NOW=$(get_thermal 2>/dev/null || echo "N/A")
    TEMP_C_NOW=$([ "$TEMP_NOW" != "N/A" ] && echo "scale=1; ${TEMP_NOW}/10" | bc 2>/dev/null || echo "N/A")

    PROMPT_TOKENS=$(( CTX - OUTPUT_TOKENS ))
    PROMPT=$(generate_prompt "$PROMPT_TOKENS")

    log ""
    log "  --- ctx=${CTX} (${CTX_IDX}/${#CTX_SIZES[@]})  prompt_tok≈${PROMPT_TOKENS}  temp=${TEMP_C_NOW}°C ---"

    for TRIAL in $(seq 1 "$NUM_TRIALS"); do
        # Skip already-done rows when resuming
        if [ "$RESUME" -eq 1 ]; then
            DONE_SO_FAR=$(wc -l < "$OUTPUT_FILE" 2>/dev/null | tr -d ' ' || echo 0)
            EXPECTED_FOR_THIS_CTX=$(( (CTX_IDX - 1) * NUM_TRIALS + TRIAL ))
            if [ "${DONE_SO_FAR:-0}" -ge "$EXPECTED_FOR_THIS_CTX" ]; then
                CURRENT_RUN=$(( CURRENT_RUN + 1 ))
                continue
            fi
        fi

        CURRENT_RUN=$(( CURRENT_RUN + 1 ))
        ELAPSED=$(( $(date +%s) - START_S ))
        [ "$CURRENT_RUN" -gt 1 ] \
            && ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED )) \
            || ETA=0

        RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
            echo '' | ${LLAMA_BIN} \
            -m ${MODEL_PATH} \
            -c ${CTX} \
            -n ${OUTPUT_TOKENS} \
            -t ${THREADS} \
            -p '${PROMPT}' 2>&1" 2>/dev/null || echo "ADB_ERROR")

        RAW_BYTES=${#RAW}

        PREFILL=$(printf '%s\n' "$RAW" \
            | grep -E "common_perf_print:.*prompt eval time" \
            | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
            | awk '{print $1}' | head -1 || echo "0")
        DECODE=$(printf '%s\n' "$RAW" \
            | grep -E "common_perf_print:.*eval time" \
            | grep -v "prompt" \
            | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
            | awk '{print $1}' | head -1 || echo "0")
        [ -z "$PREFILL" ] && PREFILL="0"
        [ -z "$DECODE"  ] && DECODE="0"

        TEMP_TRIAL=$(get_thermal 2>/dev/null || echo "0")

        if [ "$RAW" = "ADB_ERROR" ]; then
            warn "ADB error  ctx=${CTX} trial=${TRIAL}"
        fi
        if [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ]; then
            warn "Small output (${RAW_BYTES}B)  ctx=${CTX} trial=${TRIAL} — binary may have crashed"
        fi
        if [ "$(echo "$DECODE > 0" | bc -l 2>/dev/null || echo 0)" -eq 0 ] && [ "$RAW" != "ADB_ERROR" ]; then
            warn "decode_tps=0 at ctx=${CTX} trial=${TRIAL} — parse failure or crash"
        fi

        printf '{"variant":"%s","context":%d,"prompt_tokens_approx":%d,"trial":%d,"decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device_temp_tenths":%s,"device":"Pixel6a","cpu":"CortexX1","backend":"CPU","methodology":"filled_context","provenance":"rerun_n10_isolated_2026","model":"%s","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
            "$VARIANT" "$CTX" "$PROMPT_TOKENS" "$TRIAL" \
            "$DECODE" "$PREFILL" "$RAW_BYTES" "$TEMP_TRIAL" \
            "${MODEL_PREFIX}-${VARIANT}" "$THREADS" "$OUTPUT_TOKENS" \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

        log "    [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ctx=${CTX}  t=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s  temp=${TEMP_TRIAL}"
    done
done

log ""
log "=== SWEEP COMPLETE — running validation ==="
hr

python3 - "$OUTPUT_FILE" "$VARIANT" "${NUM_TRIALS}" << 'PYEOF'
import json, sys, statistics
from collections import defaultdict

output_file = sys.argv[1]
variant     = sys.argv[2]
n_trials    = int(sys.argv[3])
ctx_sizes   = [256, 512, 768, 1024, 1200, 1300, 1400, 1500, 1600, 1800, 2048]

rows = []
try:
    with open(output_file) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"  WARNING: Bad JSON line: {e}")
except FileNotFoundError:
    print(f"ERROR: Output file not found: {output_file}")
    sys.exit(1)

print(f"\n{'='*72}")
print(f"  VALIDATION: {variant}  ({len(rows)} total records)")
print(f"{'='*72}")

ctx_data = defaultdict(list)
for r in rows:
    tps = float(r.get("decode_tps", 0))
    if tps > 0:
        ctx_data[r["context"]].append(tps)

errors = []
warnings = []

# Check 1: correct trial count
for ctx in ctx_sizes:
    n = len(ctx_data.get(ctx, []))
    if n < n_trials:
        errors.append(f"ctx={ctx}: only {n}/{n_trials} valid trials")
    elif n > n_trials:
        warnings.append(f"ctx={ctx}: {n} trials (expected {n_trials})")

# Check 2: monotone decay from baseline (allow up to 5% variance at any step)
if ctx_data.get(256):
    baseline = statistics.mean(ctx_data[256])
    prev_mean = baseline
    for ctx in ctx_sizes[1:]:
        if not ctx_data.get(ctx):
            continue
        mu = statistics.mean(ctx_data[ctx])
        # Flag if any context is MORE than 5% faster than baseline (thermal inversion)
        if mu > baseline * 1.05:
            errors.append(
                f"ctx={ctx}: mean={mu:.2f} t/s is {(mu-baseline)/baseline*100:.1f}% "
                f"FASTER than baseline={baseline:.2f} t/s — THERMAL INVERSION DETECTED"
            )
        prev_mean = mu

# Check 3: provenance field
bad_prov = [r for r in rows if r.get("provenance") != "rerun_n10_isolated_2026"]
if bad_prov:
    warnings.append(f"{len(bad_prov)} records missing provenance field")

# Print results table
print(f"\n  {'CTX':>5}  {'n':>3}  {'mean':>7}  {'sd':>6}  {'min':>6}  {'max':>6}  {'vs ctx=256':>10}")
baseline_mu = None
for ctx in ctx_sizes:
    vals = ctx_data.get(ctx, [])
    if not vals:
        print(f"  {ctx:>5}  {0:>3}  {'NO DATA':>7}")
        continue
    mu  = statistics.mean(vals)
    sd  = statistics.stdev(vals) if len(vals) > 1 else 0.0
    if baseline_mu is None:
        baseline_mu = mu
    pct = (mu - baseline_mu) / baseline_mu * 100 if baseline_mu else 0
    flag = " <-- INVERSION" if mu > baseline_mu * 1.05 else ""
    print(f"  {ctx:>5}  {len(vals):>3}  {mu:>7.2f}  {sd:>6.3f}  {min(vals):>6.2f}  {max(vals):>6.2f}  {pct:>+9.1f}%{flag}")

# Print validation summary
print(f"\n  {'─'*60}")
if errors:
    print(f"  VALIDATION: FAILED ({len(errors)} error(s), {len(warnings)} warning(s))")
    for e in errors:
        print(f"  ERROR:   {e}")
    for w in warnings:
        print(f"  WARNING: {w}")
    print(f"\n  DO NOT integrate into canonical dataset — re-run required.")
    sys.exit(2)
elif warnings:
    print(f"  VALIDATION: PASSED WITH WARNINGS ({len(warnings)} warning(s))")
    for w in warnings:
        print(f"  WARNING: {w}")
else:
    print(f"  VALIDATION: PASSED — all {n_trials} trials per context, no thermal inversion")

# Integration instructions
print(f"\n  NEXT STEPS (if validated):")
print(f"  cp {output_file} \\")
print(f"     results/pixel_llama_cliff_filled_canonical_n10/cliff_filled_{variant}.jsonl")
print(f"  # Then update results/pixel_llama_cliff_filled_canonical_n10/PROVENANCE.md")

PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  variant=${VARIANT}  runtime=$(( ELAPSED/60 ))m $(( ELAPSED%60 ))s"
log "Output: ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
hr
