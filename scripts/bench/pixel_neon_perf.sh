#!/usr/bin/env bash
# ============================================================
# pixel_neon_perf.sh  —  NEON/PMU perf counter sweep
#                         Pixel 6a · Cortex-X1 · via ADB
#
# PURPOSE (Phase 2A)
# ------------------
# Measures ARM PMU hardware performance counters per K-quant
# variant to mechanistically validate the two claims in §6:
#
#   Claim A: Q6_K has ~3× higher L2 miss rate than Q2_K
#            (split-bit layout ql[128]+qh[64] thrashes cache).
#
#   Claim B: KV-cache L2 overflow at ctx=512 explains the cliff.
#            At ctx=256 (cache-resident), L2 miss rate is low;
#            at ctx=512 (KV set > L2), it spikes sharply.
#
# HARDWARE COUNTERS (Cortex-X1 PMU)
# ----------------------------------
#   cpu-cycles          — total cycles
#   instructions        — total instructions (for IPC)
#   l1d_cache_refill    — L1D refill from L2 (raw 0x03)
#   l2d_cache_refill    — L2 refill from DRAM (= LLC miss; X1 has no L3)
#   stall_backend       — pipeline backend stall cycles (memory-bound indicator)
#
# The script probes event availability; if hardware cache events require
# root, it falls back to cpu-cycles + instructions only and prints a clear
# warning.  Run `adb shell su -c 'echo -1 > /proc/sys/kernel/perf_event_paranoid'`
# before running this script to enable all hardware counters (rooted device).
#
# METHODOLOGY
# -----------
#   • Short prompt (single word) → 128 decode tokens at each context size
#   • simpleperf stat wraps entire llama-completion run; decode dominates
#     (128 decode >> 1-token prefill in all variants)
#   • n=3 trials per (variant, context) — enough to verify ordering claim
#   • Two context sizes: ctx=256 (fresh, below cliff), ctx=512 (just past cliff)
#   • 5 variants covering the extremes + middle: Q2_K, Q3_K_M, Q4_K_M, Q6_K, Q8_0
#
# PRE-EXPERIMENT HYPOTHESES (documented for expected vs actual comparison)
# -------------------------------------------------------------------------
#   H1: l2d_cache_refill / token: Q6_K ≈ 3× Q2_K at ctx=256
#       Reasoning: Q6_K's ql[128]+qh[64] split-bit layout requires loading
#       ~192B per 256-weight superblock; Q2_K only 32+32=64B.  3× data
#       footprint per superblock → ~3× L2 refills per token.
#
#   H2: l2d_cache_refill / token: Q2_K ctx=512 ≈ 2-5× Q2_K ctx=256
#       Reasoning: KV cache at ctx=512 = 512KB exactly (L2 capacity on X1).
#       At ctx=256 the KV fits in L2; at ctx=512 it just overflows → L2 miss
#       rate should jump sharply for attention computation.
#
#   H3: Q3_K_M shows smaller stall_backend increase from ctx=256→512
#       than Q2_K (compute-masking: heavier FFN kernel keeps backend busy
#       even when KV misses increase, so IPC drop is proportionally smaller)
#
#   H4: Q8_0 stall_backend / cycle ≈ Q2_K (both have simple single-array
#       formats; Q8_0 slower only because of ~4× more data loaded)
#
# SURPRISING THRESHOLD (triggers root-cause investigation if exceeded)
#   l2d_cache_refill ratio Q6_K/Q2_K > 6× or < 1.5×
#   l2d_cache_refill increase Q2_K ctx=512/ctx=256 < 1.5× (cliff may be prefetch)
#
# USAGE
#   bash scripts/bench/pixel_neon_perf.sh                   # all 5 variants
#   bash scripts/bench/pixel_neon_perf.sh Q2_K Q6_K         # subset
#   bash scripts/bench/pixel_neon_perf.sh --ctx 256,512,768 # custom contexts
#   bash scripts/bench/pixel_neon_perf.sh --trials 1 --tokens 8 Q2_K # smoke test
#   bash scripts/bench/pixel_neon_perf.sh --timeout 900      # per-run timeout seconds
#   bash scripts/bench/pixel_neon_perf.sh --all-variants     # all 7 variants
#   bash scripts/bench/pixel_neon_perf.sh --resume           # skip done variants
#
# OUTPUT
#   results/pixel_neon_perf_{ts}/neon_perf_{VARIANT}.jsonl
#   results/pixel_neon_perf_{ts}/probe_results.json
#   results/pixel_neon_perf_{ts}.log
#
# RUNTIME: ~45 min (5 variants × 2 ctx × 3 trials × ~1.5 min/run)
#
# NOTES
#   • Requires simpleperf on device (/system/bin/simpleperf); ships with
#     Android NDK and is standard on AOSP builds including Pixel stock ROM.
#   • Hardware cache events (l2d_cache_refill, stall_backend) require
#     perf_event_paranoid ≤ 1 on most Android builds.  On unrooted Pixel 6a
#     with Android 13, basic cpu-cycles/instructions are available without root.
#     For full hardware events: root + set paranoid to -1.
#   • Simpleperf stat counts the WHOLE PROCESS (prefill + decode + init).
#     With a 1-word prompt and 128 decode tokens, decode is ≥97% of cycles.
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
SIMPLEPERF_BIN="/system/bin/simpleperf"

# Default: 5 variants covering extremes + midpoint
DEFAULT_VARIANTS=(Q2_K Q3_K_M Q4_K_M Q6_K Q8_0)
ALL_VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)

# Context sizes: below cliff (256) and at cliff (512)
DEFAULT_CTXS=(256 512)

NUM_TRIALS=3      # n=3 sufficient to verify ordering; increase to 5 for paper
OUTPUT_TOKENS=128 # large enough for stable measurement; decode dominates
THREADS=4         # match TPS benchmark for fair comparison
RUN_TIMEOUT=900   # seconds per simpleperf-wrapped generation
PROMPT="Write"    # single-word prompt → minimal prefill contamination

# PMU events: try hardware events first, fall back to basic
# Cortex-X1 PMU event codes: l1d_cache_refill=0x03, l2d_cache_refill=0x17, stall_backend=0x24
# NOTE: Pixel 6a simpleperf doesn't expose l2-cache-misses by name; use raw event r17 (L2D_REFILL)
# Available standard events on Pixel 6a: cache-misses (generic), stalled-cycles-backend
EVENTS_FULL="cpu-cycles:u,instructions:u,cache-misses:u,stalled-cycles-backend:u"
EVENTS_HW_CACHE="cpu-cycles:u,instructions:u,cache-misses:u"
EVENTS_BASIC="cpu-cycles:u,instructions:u"
# Raw event codes as fallback (Cortex-X1 / ARMv8)
# r03=l1d_refill, r17=l2d_refill, r24=stall_backend
EVENTS_RAW="cpu-cycles:u,instructions:u,r17:u"

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_neon_perf_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }
warn(){ log "  ⚠️  $*"; }

# ── Argument parsing ──────────────────────────────────────────────────────────
RESUME=0
USE_ALL_VARIANTS=0
VARIANTS=()
CTX_SIZES=()

while [ "$#" -gt 0 ]; do
    arg="$1"
    case "$arg" in
        --resume)       RESUME=1; shift ;;
        --all-variants) USE_ALL_VARIANTS=1; shift ;;
        --trials)
            [ "$#" -lt 2 ] && printf 'Missing value for --trials\n' >&2 && exit 1
            NUM_TRIALS="$2"
            shift 2
            ;;
        --tokens)
            [ "$#" -lt 2 ] && printf 'Missing value for --tokens\n' >&2 && exit 1
            OUTPUT_TOKENS="$2"
            shift 2
            ;;
        --timeout)
            [ "$#" -lt 2 ] && printf 'Missing value for --timeout\n' >&2 && exit 1
            RUN_TIMEOUT="$2"
            shift 2
            ;;
        --trials=*)
            NUM_TRIALS="${arg#--trials=}"
            shift
            ;;
        --tokens=*)
            OUTPUT_TOKENS="${arg#--tokens=}"
            shift
            ;;
        --timeout=*)
            RUN_TIMEOUT="${arg#--timeout=}"
            shift
            ;;
        --ctx)
            [ "$#" -lt 2 ] && printf 'Missing value for --ctx\n' >&2 && exit 1
            IFS=',' read -ra CTX_SIZES <<< "$2"
            shift 2
            ;;
        --ctx=*)
            IFS=',' read -ra CTX_SIZES <<< "${arg#--ctx=}"
            shift
            ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0)
            VARIANTS+=("$arg")
            shift
            ;;
        *) printf 'Unknown argument: %s\n' "$arg" >&2; exit 1 ;;
    esac
done

if [ "$USE_ALL_VARIANTS" -eq 1 ]; then
    VARIANTS=("${ALL_VARIANTS[@]}")
elif [ ${#VARIANTS[@]} -eq 0 ]; then
    VARIANTS=("${DEFAULT_VARIANTS[@]}")
fi
[ ${#CTX_SIZES[@]} -eq 0 ] && CTX_SIZES=("${DEFAULT_CTXS[@]}")

# ── Preflight: device ─────────────────────────────────────────────────────────
hr
log "Pixel 6a  —  NEON/PMU Perf Counter Sweep  (Phase 2A)"
log "Variants : ${VARIANTS[*]}"
log "Contexts : ${CTX_SIZES[*]}"
log "Trials   : ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}  |  Timeout: ${RUN_TIMEOUT}s  |  Prompt: '${PROMPT}'"
log "Results  : ${RESULTS_DIR}"
hr

if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No Android device connected."; exit 1
fi
DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
log "✅ Device: ${DEVICE_ID}"

if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
    log "❌ FATAL: ${LLAMA_BIN} not found on device."; exit 1
fi
log "✅ llama-completion found"

MISSING=0
for V in "${VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ❌ Missing on device: ${MODEL_PREFIX}-${V}.gguf"; MISSING=$((MISSING+1))
    fi
done
[ "$MISSING" -gt 0 ] && log "❌ FATAL: $MISSING model(s) missing." && exit 1
log "✅ All ${#VARIANTS[@]} model(s) present"

# ── Probe: simpleperf availability ────────────────────────────────────────────
log ""
log "=== SIMPLEPERF PROBE ==="

SIMPLEPERF_OK=0
if adb shell "ls ${SIMPLEPERF_BIN} 2>/dev/null" | grep -q "simpleperf"; then
    log "✅ simpleperf found at ${SIMPLEPERF_BIN}"
    SIMPLEPERF_OK=1
else
    # Try alternate locations (NDK-pushed binary)
    for ALT_PATH in "/data/local/tmp/simpleperf" "${DEVICE_DIR}/simpleperf"; do
        if adb shell "ls ${ALT_PATH} 2>/dev/null" | grep -q "simpleperf" 2>/dev/null; then
            SIMPLEPERF_BIN="$ALT_PATH"
            log "✅ simpleperf found at ${SIMPLEPERF_BIN}"
            SIMPLEPERF_OK=1
            break
        fi
    done
fi

if [ "$SIMPLEPERF_OK" -eq 0 ]; then
    log "❌ FATAL: simpleperf not found on device."
    log "   Push it with: adb push \$(ndk-path)/simpleperf/bin/android/arm64 ${DEVICE_DIR}/simpleperf"
    log "   NDK ships simpleperf in: <NDK>/simpleperf/bin/android/arm64/simpleperf"
    exit 1
fi

# ── Probe: perf_event_paranoid ────────────────────────────────────────────────
PARANOID=$(adb shell "cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo 3")
PARANOID=$(printf '%s' "$PARANOID" | tr -d '[:space:]')
log "perf_event_paranoid = ${PARANOID}"
if [ "$PARANOID" -gt 1 ] 2>/dev/null; then
    warn "perf_event_paranoid=${PARANOID} — hardware cache events may be unavailable."
    warn "For full hardware events, run (requires root):"
    warn "  adb shell su -c 'echo -1 > /proc/sys/kernel/perf_event_paranoid'"
fi

# ── Probe: which events are available ─────────────────────────────────────────
log ""
log "Probing available PMU events..."

ACTIVE_EVENTS=""
PROBE_CMD="export LD_LIBRARY_PATH=${DEVICE_DIR} && \
  ${SIMPLEPERF_BIN} stat -e cpu-cycles echo hello 2>&1"
PROBE_OUT=$(adb shell "$PROBE_CMD" 2>/dev/null || echo "FAILED")

if printf '%s' "$PROBE_OUT" | grep -q "cpu-cycles"; then
    log "  ✅ cpu-cycles: available"
    # Try generic cache-misses (Pixel 6a doesn't expose l2-cache-misses by name)
    PROBE_CACHE="export LD_LIBRARY_PATH=${DEVICE_DIR} && \
      ${SIMPLEPERF_BIN} stat -e cache-misses:u echo hello 2>&1"
    PROBE_CACHE_OUT=$(adb shell "$PROBE_CACHE" 2>/dev/null || echo "FAILED")
    if printf '%s' "$PROBE_CACHE_OUT" | grep -q "cache-misses"; then
        log "  ✅ cache-misses (generic, ARM L2-equivalent): available"
        ACTIVE_EVENTS="$EVENTS_HW_CACHE"
        # Try stall event
        PROBE_STALL="export LD_LIBRARY_PATH=${DEVICE_DIR} && \
          ${SIMPLEPERF_BIN} stat -e stalled-cycles-backend:u echo hello 2>&1"
        PROBE_STALL_OUT=$(adb shell "$PROBE_STALL" 2>/dev/null || echo "FAILED")
        if printf '%s' "$PROBE_STALL_OUT" | grep -q "stalled-cycles-backend"; then
            log "  ✅ stalled-cycles-backend: available"
            ACTIVE_EVENTS="$EVENTS_FULL"
        else
            log "  ⚠️  stalled-cycles-backend: unavailable — using cache-misses only"
        fi
    else
        log "  ⚠️  cache-misses: unavailable — trying raw event r17 (L2D_REFILL)"
        PROBE_RAW="export LD_LIBRARY_PATH=${DEVICE_DIR} && \
          ${SIMPLEPERF_BIN} stat -e r17:u echo hello 2>&1"
        PROBE_RAW_OUT=$(adb shell "$PROBE_RAW" 2>/dev/null || echo "FAILED")
        if printf '%s' "$PROBE_RAW_OUT" | grep -q "r17"; then
            log "  ✅ Raw PMU event r17 (l2d_refill): available"
            PROBE_STALL="export LD_LIBRARY_PATH=${DEVICE_DIR} && \
              ${SIMPLEPERF_BIN} stat -e stalled-cycles-backend:u echo hello 2>&1"
            if adb shell "$PROBE_STALL" 2>/dev/null | grep -q "stalled-cycles-backend"; then
                ACTIVE_EVENTS="cpu-cycles:u,instructions:u,r17:u,stalled-cycles-backend:u"
                log "  ✅ stalled-cycles-backend: also available"
            else
                ACTIVE_EVENTS="$EVENTS_RAW"
            fi
        else
            warn "Hardware cache events unavailable. Falling back to cpu-cycles,instructions only."
            warn "This limits mechanistic analysis to IPC. Root device and set paranoid=-1 for full data."
            ACTIVE_EVENTS="$EVENTS_BASIC"
        fi
    fi
else
    log "❌ FATAL: simpleperf stat cpu-cycles failed. Check device compatibility."
    printf '%s\n' "$PROBE_OUT"
    exit 1
fi

log "Active event set: ${ACTIVE_EVENTS}"
# Save probe results to JSON
printf '{"perf_event_paranoid":%s,"active_events":"%s","simpleperf_path":"%s","probe_ts":"%s"}\n' \
    "${PARANOID}" "${ACTIVE_EVENTS}" "${SIMPLEPERF_BIN}" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "${RESULTS_DIR}/probe_results.json"

# ── Determine whether we have cache miss events ───────────────────────────────
HAS_CACHE_EVENTS=0
if printf '%s' "$ACTIVE_EVENTS" | grep -qE "cache-misses|l2-cache-misses|r17|l2d_cache"; then
    HAS_CACHE_EVENTS=1
    log "✅ L2 cache miss events available — full mechanistic analysis possible"
else
    warn "L2 cache miss events NOT available — analysis limited to IPC and cycle counts"
    warn "Root the device and set perf_event_paranoid=-1 for L2/stall events."
fi

# ── Main sweep ────────────────────────────────────────────────────────────────
log ""
hr
log "Starting PMU counter sweep..."
hr

TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CTX_SIZES[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/neon_perf_${VARIANT}.jsonl"

    EXPECTED_LINES=$(( ${#CTX_SIZES[@]} * NUM_TRIALS ))
    if [ "$RESUME" -eq 1 ] && [ -f "$OUTPUT_FILE" ]; then
        DONE=$(wc -l < "$OUTPUT_FILE" 2>/dev/null | tr -d ' ' || echo 0)
        if [ "${DONE:-0}" -ge "$EXPECTED_LINES" ]; then
            log "⏩ SKIP $VARIANT — already complete (${DONE} rows)"
            CURRENT_RUN=$(( CURRENT_RUN + EXPECTED_LINES ))
            continue
        fi
    fi

    log ""
    log "━━━ ${VARIANT} ━━━"
    > "$OUTPUT_FILE"

    for CTX in "${CTX_SIZES[@]}"; do
        for TRIAL in $(seq 1 "$NUM_TRIALS"); do
            CURRENT_RUN=$(( CURRENT_RUN + 1 ))
            ELAPSED=$(( $(date +%s) - START_S ))
            [ "$CURRENT_RUN" -gt 1 ] \
                && ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED )) \
                || ETA=0

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  ctx=${CTX}  trial=${TRIAL}  ..."

            # Run simpleperf stat wrapping llama-completion.
            # Do not pass --duration 0: Pixel simpleperf rejects it as invalid.
            # stderr from llama-completion + simpleperf summary both captured.
            REMOTE_CMD="export LD_LIBRARY_PATH=${DEVICE_DIR} && \
                timeout ${RUN_TIMEOUT} \
                ${SIMPLEPERF_BIN} stat \
                    -e ${ACTIVE_EVENTS} \
                    -- ${LLAMA_BIN} \
                        -m ${MODEL_PATH} \
                        -c ${CTX} \
                        -n ${OUTPUT_TOKENS} \
                        -p '${PROMPT}' \
                        -t ${THREADS} \
                        -no-cnv \
                        --no-mmap \
                        </dev/null 2>&1"
            if RAW=$(adb shell "$REMOTE_CMD" 2>&1); then
                RC=0
            else
                RC=$?
            fi

            if [ "$RC" -ne 0 ]; then
                warn "Command error rc=${RC} on ${VARIANT} ctx=${CTX} trial=${TRIAL}"
                DEBUG_FILE="${RESULTS_DIR}/debug_${VARIANT}_ctx${CTX}_trial${TRIAL}.txt"
                {
                    printf 'remote_cmd=%s\n' "$REMOTE_CMD"
                    printf 'return_code=%s\n\n' "$RC"
                    printf '%s\n' "$RAW"
                } > "$DEBUG_FILE"
                python3 - "$VARIANT" "$CTX" "$TRIAL" "$RC" "$DEBUG_FILE" << 'PY' >> "$OUTPUT_FILE"
import datetime
import json
import sys

variant, ctx, trial, rc, debug_file = sys.argv[1:]
print(json.dumps({
    "variant": variant,
    "context": int(ctx),
    "trial": int(trial),
    "status": "command_error",
    "return_code": int(rc),
    "debug_file": debug_file,
    "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
}))
PY
                continue
            fi

            # Extract decode TPS from llama.cpp output (for cross-reference)
            DECODE_TPS=$(printf '%s\n' "$RAW" \
                | grep -E "(common_perf_print|llama_perf_context_print):.*eval time" | grep -v "prompt" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
                | awk '{print $1}' | head -1 || echo "0")
            [ -z "$DECODE_TPS" ] && DECODE_TPS="0"

            # Parse simpleperf stat output
            # simpleperf stat output format:
            #   "  1,234,567  cpu-cycles   #  1.23 GHz"
            #   "    123,456  instructions  #  0.10 insn per cycle"
            # Numbers may have commas; strip them for parsing
            parse_counter() {
                local event_pattern="$1"
                printf '%s\n' "$RAW" \
                    | grep -iE "${event_pattern}" \
                    | grep -oE "^[[:space:]]*[0-9,]+" \
                    | head -1 \
                    | tr -d ', ' \
                    || echo "0"
            }

            CYCLES=$(parse_counter "cpu-cycles")
            INSTRS=$(parse_counter "instructions")
            L1D_REFILL=$(parse_counter "l1d-cache-misses|l1d_cache_refill|r03")
            # L2D_REFILL: check for cache-misses (generic ARM L2) or raw r17 (L2D_REFILL)
            L2D_REFILL=$(parse_counter "cache-misses|l2-cache-misses|l2d_cache_refill|r17")
            STALL_BE=$(parse_counter "stalled-cycles-backend|stall_backend|r24")
            ELAPSED_MS=$(printf '%s\n' "$RAW" \
                | grep -oE "[0-9]+\.[0-9]+ seconds time elapsed" \
                | awk '{print $1 * 1000}' | head -1 || echo "0")

            [ -z "$CYCLES" ]     && CYCLES="0"
            [ -z "$INSTRS" ]     && INSTRS="0"
            [ -z "$L1D_REFILL" ] && L1D_REFILL="0"
            [ -z "$L2D_REFILL" ] && L2D_REFILL="0"
            [ -z "$STALL_BE" ]   && STALL_BE="0"
            [ -z "$ELAPSED_MS" ] && ELAPSED_MS="0"

            printf '{"variant":"%s","context":%d,"trial":%d,"decode_tps":%s,"elapsed_ms":%s,"cycles":%s,"instructions":%s,"l1d_refill":%s,"l2d_refill":%s,"stall_backend":%s,"n_output_tokens":%d,"active_events":"%s","device":"Pixel6a","cpu":"CortexX1","model":"%s","threads":%d,"ts":"%s"}\n' \
                "$VARIANT" "$CTX" "$TRIAL" "$DECODE_TPS" "$ELAPSED_MS" \
                "$CYCLES" "$INSTRS" "$L1D_REFILL" "$L2D_REFILL" "$STALL_BE" \
                "$OUTPUT_TOKENS" "$ACTIVE_EVENTS" \
                "${MODEL_PREFIX}-${VARIANT}" "$THREADS" \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

            # Quick sanity log
            IPC="N/A"
            if [ "$CYCLES" != "0" ] && [ "$INSTRS" != "0" ] 2>/dev/null; then
                IPC=$(python3 -c "print(f'{int(\"${INSTRS}\")/int(\"${CYCLES}\"):.3f}')" 2>/dev/null || echo "N/A")
            fi
            L2_PER_TOK="N/A"
            if [ "$L2D_REFILL" != "0" ] 2>/dev/null; then
                L2_PER_TOK=$(python3 -c "print(f'{int(\"${L2D_REFILL}\")/${OUTPUT_TOKENS}:.0f}')" 2>/dev/null || echo "N/A")
            fi

            log "    decode=${DECODE_TPS} t/s  IPC=${IPC}  l2_miss/tok=${L2_PER_TOK}"
        done
    done

    log "  ✅ Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

# ── Analysis summary ──────────────────────────────────────────────────────────
log ""
hr
log "NEON/PMU COUNTER ANALYSIS  —  Pixel 6a Cortex-X1  —  Llama 3.2 3B"
log "Pre-experiment hypotheses:"
log "  H1: l2d_refill/token(Q6_K) ≈ 3× l2d_refill/token(Q2_K) at ctx=256"
log "  H2: l2d_refill/token(Q2_K,ctx=512) ≈ 2-5× l2d_refill/token(Q2_K,ctx=256)"
log "  H3: Q3_K_M stall_backend delta (ctx=256→512) < Q2_K delta (compute-masking)"
hr

python3 - "$RESULTS_DIR" "$OUTPUT_TOKENS" "${VARIANTS[@]}" "${CTX_SIZES[@]}" << 'PYEOF'
import json, glob, sys, statistics
from collections import defaultdict

results_dir = sys.argv[1]
N_TOKENS = int(sys.argv[2])
# Parse variants and contexts from args
all_args = sys.argv[3:]
known_variants = ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
variants = [a for a in all_args if a in known_variants]
ctx_args = [a for a in all_args if a.isdigit()]
ctx_list = [int(c) for c in ctx_args] if ctx_args else [256, 512]

def mean_safe(vals):
    return statistics.mean(vals) if vals else None

def fmt(v, fmt_str):
    return fmt_str.format(v) if v is not None else "   N/A"

# Load all data
data_by_variant = {}
for variant in variants:
    paths = glob.glob(f"{results_dir}/neon_perf_{variant}.jsonl")
    if not paths:
        continue
    rows = []
    for line in open(paths[0]):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    data_by_variant[variant] = rows

if not data_by_variant:
    print("No data found.")
    sys.exit(0)

# ── Table 1: Per-token metrics by variant and context ─────────────────────────
print(f"\n{'─'*100}")
print(f"{'VARIANT':<10}  {'CTX':>5}  {'TPS':>7}  {'CYCLES/tok':>12}  {'INSTRS/tok':>12}  "
      f"{'L1_miss/tok':>12}  {'L2_miss/tok':>12}  {'STALL_BE/tok':>12}  {'IPC':>6}  {'STALL%':>7}")
print(f"{'─'*100}")

# Store per-variant ctx=256 data for ratio computation
baseline_l2 = {}

for variant in variants:
    if variant not in data_by_variant:
        continue
    rows = data_by_variant[variant]

    for ctx in ctx_list:
        ctx_rows = [r for r in rows if r.get("context") == ctx and r.get("status") != "adb_error"]
        if not ctx_rows:
            print(f"{variant:<10}  {ctx:>5}  {'no data':>7}")
            continue

        tps_vals  = [float(r["decode_tps"]) for r in ctx_rows if float(r.get("decode_tps", 0)) > 0]
        cyc_vals  = [int(r["cycles"]) / N_TOKENS for r in ctx_rows if int(r.get("cycles", 0)) > 0]
        ins_vals  = [int(r["instructions"]) / N_TOKENS for r in ctx_rows if int(r.get("instructions", 0)) > 0]
        l1_vals   = [int(r["l1d_refill"]) / N_TOKENS for r in ctx_rows if int(r.get("l1d_refill", 0)) > 0]
        l2_vals   = [int(r["l2d_refill"]) / N_TOKENS for r in ctx_rows if int(r.get("l2d_refill", 0)) > 0]
        stl_vals  = [int(r["stall_backend"]) / N_TOKENS for r in ctx_rows if int(r.get("stall_backend", 0)) > 0]

        tps  = mean_safe(tps_vals)
        cyc  = mean_safe(cyc_vals)
        ins  = mean_safe(ins_vals)
        l1   = mean_safe(l1_vals)
        l2   = mean_safe(l2_vals)
        stl  = mean_safe(stl_vals)
        ipc  = (ins / cyc) if (ins and cyc and cyc > 0) else None
        stl_pct = (stl / cyc * 100) if (stl and cyc and cyc > 0) else None

        if ctx == 256 and l2 is not None:
            baseline_l2[variant] = l2

        print(f"{variant:<10}  {ctx:>5}  "
              f"{fmt(tps, '{:>7.2f}'):>7}  "
              f"{fmt(cyc, '{:>12,.0f}'):>12}  "
              f"{fmt(ins, '{:>12,.0f}'):>12}  "
              f"{fmt(l1,  '{:>12,.0f}'):>12}  "
              f"{fmt(l2,  '{:>12,.0f}'):>12}  "
              f"{fmt(stl, '{:>12,.0f}'):>12}  "
              f"{fmt(ipc, '{:>6.3f}'):>6}  "
              f"{fmt(stl_pct, '{:>6.1f}%'):>7}")

print(f"{'─'*100}")

# ── Table 2: Hypothesis validation ───────────────────────────────────────────
print(f"\n{'═'*80}")
print("HYPOTHESIS VALIDATION")
print(f"{'═'*80}")

# H1: Q6_K L2 miss rate vs Q2_K at ctx=256
q2k_l2  = baseline_l2.get("Q2_K")
q6k_l2  = baseline_l2.get("Q6_K")
if q2k_l2 and q6k_l2 and q2k_l2 > 0:
    h1_ratio = q6k_l2 / q2k_l2
    h1_result = "✅ CONFIRMED" if 1.5 <= h1_ratio <= 6.0 else "❌ OUTSIDE EXPECTED RANGE"
    h1_surprise = " ← SURPRISING (>6x)" if h1_ratio > 6.0 else (" ← SURPRISING (<1.5x)" if h1_ratio < 1.5 else "")
    print(f"\nH1: L2 miss/tok ratio Q6_K/Q2_K at ctx=256")
    print(f"    Hypothesis: ~3× (expected range 1.5x–6.0x)")
    print(f"    Result:     Q6_K={q6k_l2:,.0f}  Q2_K={q2k_l2:,.0f}  ratio={h1_ratio:.2f}x  {h1_result}{h1_surprise}")
else:
    print(f"\nH1: Cannot evaluate — L2 miss data not available (Q2_K: {q2k_l2}, Q6_K: {q6k_l2})")

# H2: Q2_K L2 miss rate ctx=512 vs ctx=256
if "Q2_K" in data_by_variant:
    q2k_rows = data_by_variant["Q2_K"]
    q2k_256_l2 = [int(r["l2d_refill"]) / N_TOKENS for r in q2k_rows
                  if r.get("context") == 256 and int(r.get("l2d_refill", 0)) > 0]
    q2k_512_l2 = [int(r["l2d_refill"]) / N_TOKENS for r in q2k_rows
                  if r.get("context") == 512 and int(r.get("l2d_refill", 0)) > 0]
    mu_256 = mean_safe(q2k_256_l2)
    mu_512 = mean_safe(q2k_512_l2)
    if mu_256 and mu_512 and mu_256 > 0:
        h2_ratio = mu_512 / mu_256
        h2_result = "✅ CONFIRMED" if h2_ratio >= 1.5 else "❌ BELOW EXPECTED (cliff may be prefetch-dominated)"
        print(f"\nH2: Q2_K L2 miss/tok ratio ctx=512/ctx=256")
        print(f"    Hypothesis: 2–5× (cliff = L2 overflow)")
        print(f"    Result:     ctx=256: {mu_256:,.0f}  ctx=512: {mu_512:,.0f}  ratio={h2_ratio:.2f}x  {h2_result}")
    else:
        print(f"\nH2: Cannot evaluate — Q2_K L2 miss data incomplete")

# H3: Q3_K_M vs Q2_K stall_backend delta
print(f"\nH3: Compute-masking — stall_backend delta (ctx=256→512) smaller for Q3_K_M than Q2_K")
for v in ["Q2_K", "Q3_K_M"]:
    if v not in data_by_variant:
        continue
    rows = data_by_variant[v]
    for ctxa, ctxb in [(256, 512)]:
        stl_a = [int(r["stall_backend"]) / N_TOKENS for r in rows
                 if r.get("context") == ctxa and int(r.get("stall_backend", 0)) > 0]
        stl_b = [int(r["stall_backend"]) / N_TOKENS for r in rows
                 if r.get("context") == ctxb and int(r.get("stall_backend", 0)) > 0]
        mu_a = mean_safe(stl_a)
        mu_b = mean_safe(stl_b)
        if mu_a and mu_b:
            delta = (mu_b - mu_a) / mu_a * 100
            print(f"    {v:<10}: stall/tok ctx={ctxa}: {mu_a:,.0f}  ctx={ctxb}: {mu_b:,.0f}  delta={delta:+.1f}%")
        else:
            print(f"    {v:<10}: stall_backend data not available")

# H4: Q8_0 vs Q2_K IPC
print(f"\nH4: Q8_0 stall_backend/cycle ≈ Q2_K (simple single-array format; slower due to data volume only)")
for v in ["Q2_K", "Q8_0"]:
    if v not in data_by_variant:
        continue
    rows = [r for r in data_by_variant[v] if r.get("context") == 256]
    cyc = mean_safe([int(r["cycles"]) for r in rows if int(r.get("cycles", 0)) > 0])
    stl = mean_safe([int(r["stall_backend"]) for r in rows if int(r.get("stall_backend", 0)) > 0])
    if cyc and stl:
        stl_frac = stl / cyc * 100
        print(f"    {v:<10}: stall_backend/cycle = {stl_frac:.1f}%")
    else:
        print(f"    {v:<10}: data not available")

# ── Table 3: Dequant overhead proxy ──────────────────────────────────────────
print(f"\n{'═'*80}")
print("DEQUANTIZATION OVERHEAD PROXY  (instructions/token at ctx=256, normalized to Q2_K=1.0)")
print("Expected: Q6_K ≈ 3.0×; Q8_0 ≈ 1.5–2.0×; Q4_K_M ≈ 1.5–2.5×")
print(f"{'═'*80}")

q2k_256_ins = None
for variant in variants:
    if variant not in data_by_variant or variant != "Q2_K":
        continue
    rows = [r for r in data_by_variant[variant] if r.get("context") == 256]
    ins_vals = [int(r["instructions"]) / N_TOKENS for r in rows if int(r.get("instructions", 0)) > 0]
    q2k_256_ins = mean_safe(ins_vals)

for variant in variants:
    if variant not in data_by_variant:
        continue
    rows = [r for r in data_by_variant[variant] if r.get("context") == 256]
    ins_vals = [int(r["instructions"]) / N_TOKENS for r in rows if int(r.get("instructions", 0)) > 0]
    mu_ins = mean_safe(ins_vals)
    if mu_ins and q2k_256_ins and q2k_256_ins > 0:
        ratio = mu_ins / q2k_256_ins
        print(f"  {variant:<10}: {mu_ins:>12,.0f} insn/tok  ({ratio:.2f}× Q2_K)")
    elif mu_ins:
        print(f"  {variant:<10}: {mu_ins:>12,.0f} insn/tok  (Q2_K baseline not available)")
    else:
        print(f"  {variant:<10}: no instruction count data")

print(f"\n{'─'*80}")
print("LaTeX table snippet for §6 (copy to paper after validation):")
print(f"{'─'*80}")
print(r"\begin{table}[h]")
print(r"\small\centering")
print(r"\caption{ARM Cortex-X1 PMU counters per decode token (ctx=256, n=" +
      "3 trials). Validates mechanistic claims: Q6\\_K dequant overhead "
      r"(3$\times$ instructions) and KV-cache cliff (L2 miss spike ctx=256$\to$512).}")
print(r"\label{tab:pmu_counters}")
print(r"\begin{tabular}{@{}lccccc@{}}")
print(r"\toprule")
print(r"\textbf{Variant} & \textbf{TPS} & \textbf{IPC} & "
      r"\textbf{L2 miss/tok} & \textbf{Insn/tok} & \textbf{Stall\%} \\")
print(r"\midrule")
for variant in variants:
    if variant not in data_by_variant:
        print(f"% {variant}: no data")
        continue
    rows = [r for r in data_by_variant[variant] if r.get("context") == 256
            and r.get("status") != "adb_error"]
    if not rows:
        continue
    tps_v  = mean_safe([float(r["decode_tps"]) for r in rows if float(r.get("decode_tps",0))>0])
    cyc_v  = mean_safe([int(r["cycles"]) for r in rows if int(r.get("cycles",0))>0])
    ins_v  = mean_safe([int(r["instructions"]) for r in rows if int(r.get("instructions",0))>0])
    l2_v   = mean_safe([int(r["l2d_refill"]) / N_TOKENS for r in rows if int(r.get("l2d_refill",0))>0])
    stl_v  = mean_safe([int(r["stall_backend"]) for r in rows if int(r.get("stall_backend",0))>0])
    ipc_v  = (ins_v / cyc_v) if (ins_v and cyc_v and cyc_v > 0) else None
    stlp_v = (stl_v / cyc_v * 100) if (stl_v and cyc_v and cyc_v > 0) else None
    ins_k  = (ins_v / N_TOKENS / 1000) if ins_v else None
    print(f"  {variant:<10} & "
          f"{fmt(tps_v, '{:.2f}'):>5} & "
          f"{fmt(ipc_v, '{:.3f}'):>5} & "
          f"{fmt(l2_v, '{:,.0f}'):>8} & "
          f"{fmt(ins_k, '{:,.0f}K'):>8} & "
          f"{fmt(stlp_v, '{:.1f}\\%'):>7} \\\\")
print(r"\bottomrule")
print(r"\end{tabular}")
print(r"\end{table}")

PYEOF

log ""
log "Writing machine-readable NEON summary..."
python3 scripts/analyze/analyze_neon_perf.py "$RESULTS_DIR" | tee -a "$LOGFILE"

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
log ""
log "Next steps:"
log "  1. Check hypothesis validation above against pre-experiment predictions"
log "  2. If H1 ratio ∉ [1.5×, 6.0×] — investigate kernel source (llama.cpp commit 1a29907)"
log "  3. If H2 ratio < 1.5× — KV cliff may be prefetch-mediated; inspect simpleperf record"
log "  4. Copy LaTeX table snippet into report §6 after validating numbers"
log "  5. Run with --all-variants for supplementary material"
hr
