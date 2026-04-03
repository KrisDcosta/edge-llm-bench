#!/usr/bin/env bash
# ============================================================
# pixel_thermal_drift.sh  —  Thermal drift characterization
#                             Pixel 6a · CPU (4 threads) · via ADB
#
# PURPOSE: Characterize how sustained inference degrades throughput
# under thermal load, validating the 120-second cooldown assumption
# used in the main experiment.
#
# PROTOCOL:
#   Phase 0 — BASELINE:   5 trials, Q4_K_M, ctx=256, normal cooldown
#   Phase 1 — NO-COOLDOWN: 50 consecutive trials, Q4_K_M, ctx=256,
#              NO sleep between trials.  Records trial index and
#              wall-clock timestamp per trial.
#   Phase 2 — RECOVERY:  Wait exactly 120 seconds, then 5 trials.
#
# JSONL fields: {trial, phase, timestamp, decode_tps, elapsed_seconds_from_start}
#
# Usage:
#   bash scripts/bench/pixel_thermal_drift.sh
#
# Output:  results/pixel_thermal_{ts}/thermal_drift.jsonl
# Runtime: ~45-60 min  (50 trials + 120s cooldown + 10 framing trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
VARIANT="Q4_K_M"
CTX=256
NO_COOLDOWN_TRIALS=50
FRAMING_TRIALS=5
OUTPUT_TOKENS=64
THREADS=4
COOLDOWN_SECONDS=120
PROMPT="The future of artificial intelligence is"

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_thermal_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

hr
log "Pixel 6a  —  Thermal Drift Characterization  (CPU, ${THREADS} threads)"
log "Model     : ${MODEL_PREFIX}-${VARIANT}.gguf"
log "Context   : ${CTX}  |  Output tokens: ${OUTPUT_TOKENS}"
log "Protocol  :"
log "  Phase 0 (baseline)   : ${FRAMING_TRIALS} trials with standard cooldown"
log "  Phase 1 (no-cooldown): ${NO_COOLDOWN_TRIALS} consecutive trials, no sleep between"
log "  Phase 2 (recovery)   : ${COOLDOWN_SECONDS}s cooldown, then ${FRAMING_TRIALS} trials"
log "Results   : ${RESULTS_DIR}"
hr

# ── Preflight: device ─────────────────────────────────────────
if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "FATAL: No Android device connected. Connect USB and enable debugging."
    exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "Device: ${DEVICE_ID}"

# ── Preflight: binary ─────────────────────────────────────────
if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "FATAL: ${LLAMA_BIN} not found on device."
    exit 1
fi
log "llama-completion found on device"

# ── Preflight: model ──────────────────────────────────────────
MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
if ! adb shell "ls ${MODEL_PATH} 2>/dev/null" | grep -q ".gguf"; then
    log "FATAL: ${MODEL_PREFIX}-${VARIANT}.gguf not found on device."
    exit 1
fi
log "Model ${MODEL_PREFIX}-${VARIANT}.gguf present"
log ""

OUTPUT_FILE="${RESULTS_DIR}/thermal_drift.jsonl"
> "$OUTPUT_FILE"

# Helper: run one trial and append to JSONL
# run_trial PHASE TRIAL_INDEX
run_trial() {
    local phase="$1"
    local trial_idx="$2"

    local wall_ts
    wall_ts=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    local elapsed=$(( $(date +%s) - EXPERIMENT_START_S ))

    RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
        echo '' | ${LLAMA_BIN} \
        -m ${MODEL_PATH} \
        -c ${CTX} \
        -n ${OUTPUT_TOKENS} \
        -t ${THREADS} \
        -p '${PROMPT}' 2>&1" 2>/dev/null || echo "ADB_ERROR")

    RAW_BYTES=${#RAW}

    DECODE=$(printf '%s\n' "$RAW" \
        | grep -E "common_perf_print:.*eval time" \
        | grep -v "prompt" \
        | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
        | awk '{print $1}' | head -1 || echo "0")
    [ -z "$DECODE" ] && DECODE="0"

    if [ "$RAW" = "ADB_ERROR" ]; then
        log "  WARNING: ADB error  phase=${phase} trial=${trial_idx}"
    fi
    if [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ]; then
        log "  WARNING: Small output (${RAW_BYTES}B)  phase=${phase} trial=${trial_idx}"
    fi

    printf '{"trial":%d,"phase":"%s","timestamp":"%s","decode_tps":%s,"elapsed_seconds_from_start":%d,"context":%d,"variant":"%s","raw_bytes":%d,"device":"Pixel6a","backend":"CPU","threads":%d,"n_output_tokens":%d}\n' \
        "$trial_idx" "$phase" "$wall_ts" "$DECODE" "$elapsed" \
        "$CTX" "$VARIANT" "$RAW_BYTES" "$THREADS" "$OUTPUT_TOKENS" >> "$OUTPUT_FILE"

    log "  [phase=${phase} trial=${trial_idx}]  decode=${DECODE} t/s  elapsed=${elapsed}s"
}

# ── PHASE 0: Baseline (5 trials with brief cooldown) ─────────
log "=== PHASE 0: BASELINE (${FRAMING_TRIALS} trials, 30s cooldown between) ==="
EXPERIMENT_START_S=$(date +%s)
TOTAL_EXPECTED=$(( FRAMING_TRIALS + NO_COOLDOWN_TRIALS + FRAMING_TRIALS ))

for TRIAL in $(seq 1 $FRAMING_TRIALS); do
    run_trial "baseline" "$TRIAL"
    if [ "$TRIAL" -lt "$FRAMING_TRIALS" ]; then
        log "  (cooldown 30s before next baseline trial)"
        sleep 30
    fi
done
log "Phase 0 complete."
log ""

# ── PHASE 1: No-cooldown run (50 consecutive trials) ─────────
log "=== PHASE 1: NO-COOLDOWN RUN (${NO_COOLDOWN_TRIALS} consecutive trials) ==="
log "  No sleep between trials.  Recording thermal drift."

for TRIAL in $(seq 1 $NO_COOLDOWN_TRIALS); do
    run_trial "no_cooldown" "$TRIAL"
done
log "Phase 1 complete."

PHASE1_END_S=$(date +%s)
log ""

# ── Wait for cooldown ─────────────────────────────────────────
log "=== COOLDOWN: waiting ${COOLDOWN_SECONDS} seconds ==="
WAITED=0
while [ "$WAITED" -lt "$COOLDOWN_SECONDS" ]; do
    REMAINING=$(( COOLDOWN_SECONDS - WAITED ))
    log "  cooldown: ${WAITED}/${COOLDOWN_SECONDS}s elapsed  (${REMAINING}s remaining)"
    if [ "$REMAINING" -ge 30 ]; then
        sleep 30
        WAITED=$(( WAITED + 30 ))
    else
        sleep "$REMAINING"
        WAITED="$COOLDOWN_SECONDS"
    fi
done
log "Cooldown complete."
log ""

# ── PHASE 2: Recovery (5 trials after cooldown) ──────────────
log "=== PHASE 2: RECOVERY (${FRAMING_TRIALS} trials after ${COOLDOWN_SECONDS}s cooldown) ==="

for TRIAL in $(seq 1 $FRAMING_TRIALS); do
    run_trial "recovery" "$TRIAL"
    if [ "$TRIAL" -lt "$FRAMING_TRIALS" ]; then
        sleep 10
    fi
done
log "Phase 2 complete."
log ""
log "Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"

hr
log "THERMAL DRIFT ANALYSIS  —  Pixel 6a"
hr

python3 - "$OUTPUT_FILE" "$COOLDOWN_SECONDS" << 'PYEOF'
import json, sys, statistics

path            = sys.argv[1]
cooldown_target = int(sys.argv[2])

data = [json.loads(l) for l in open(path) if l.strip()]

baseline   = [d for d in data if d["phase"] == "baseline"]
no_cool    = [d for d in data if d["phase"] == "no_cooldown"]
recovery   = [d for d in data if d["phase"] == "recovery"]

def mean_tps(rows):
    vals = [float(r["decode_tps"]) for r in rows if float(r["decode_tps"]) > 0]
    if not vals:
        return 0.0, 0.0
    mu = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return mu, sd

b_mu, b_sd = mean_tps(baseline)
r_mu, r_sd = mean_tps(recovery)

print(f"\n{'='*72}")
print(f"  THERMAL DRIFT SUMMARY  —  Q4_K_M, ctx=256, no-cooldown run")
print(f"{'='*72}")
print(f"\n  Phase 0 baseline   : {b_mu:.2f} +/- {b_sd:.2f} t/s  (n={len(baseline)})")
print(f"  Phase 2 recovery   : {r_mu:.2f} +/- {r_sd:.2f} t/s  (n={len(recovery)})")
if b_mu > 0:
    pct = (r_mu - b_mu) / b_mu * 100
    print(f"  Recovery vs baseline: {pct:+.1f}%")

print(f"\n  No-cooldown drift over {len(no_cool)} consecutive trials:")
print(f"  {'Trial':>6}  {'decode t/s':>12}  {'elapsed s':>10}  {'vs trial-1':>10}")
print(f"  {'-'*6}  {'-'*12}  {'-'*10}  {'-'*10}")

first_tps = None
prev_tps  = None
for row in no_cool:
    tps = float(row["decode_tps"])
    t   = row["trial"]
    el  = row["elapsed_seconds_from_start"]
    if first_tps is None and tps > 0:
        first_tps = tps
    vs_first = f"{(tps - first_tps) / first_tps * 100:+.1f}%" if first_tps and first_tps > 0 else "  N/A"
    vs_prev  = f"{(tps - prev_tps)  / prev_tps  * 100:+.1f}%" if prev_tps and prev_tps > 0 else "  N/A"
    if t == 1 or t % 5 == 0 or t == len(no_cool):
        print(f"  {t:6d}  {tps:12.2f}  {el:10d}  {vs_prev:>10}  (vs t1: {vs_first})")
    prev_tps = tps if tps > 0 else prev_tps

valid_nc = [float(r["decode_tps"]) for r in no_cool if float(r["decode_tps"]) > 0]
if valid_nc:
    nc_mu, nc_sd = statistics.mean(valid_nc), statistics.stdev(valid_nc) if len(valid_nc) > 1 else 0.0
    nc_min, nc_max = min(valid_nc), max(valid_nc)
    drop = (nc_max - nc_min) / nc_max * 100 if nc_max > 0 else 0
    print(f"\n  No-cooldown summary: mean={nc_mu:.2f}  sd={nc_sd:.2f}  min={nc_min:.2f}  max={nc_max:.2f}")
    print(f"  Peak-to-trough drop: {drop:.1f}%")
    if b_mu > 0:
        min_vs_base = (nc_min - b_mu) / b_mu * 100
        print(f"  Trough vs baseline : {min_vs_base:+.1f}%")

print()
if b_mu > 0 and r_mu > 0:
    recovery_pct = (r_mu - b_mu) / b_mu * 100
    if abs(recovery_pct) < 5.0:
        print(f"  CONCLUSION: {cooldown_target}s cooldown appears SUFFICIENT — recovery within 5% of baseline.")
    else:
        print(f"  CONCLUSION: {cooldown_target}s cooldown may be INSUFFICIENT — recovery is {recovery_pct:+.1f}% vs baseline.")
PYEOF

ELAPSED=$(( $(date +%s) - EXPERIMENT_START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
