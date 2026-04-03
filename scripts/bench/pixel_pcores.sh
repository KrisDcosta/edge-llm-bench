#!/usr/bin/env bash
# ============================================================
# pixel_pcores.sh  —  P-core CPU affinity test
#                      Pixel 6a · via ADB
#
# Runs Llama 3.2 3B Instruct Q2_K and Q3_K_M at ctx=256,
# n=10 trials, output_tokens=64.  Compares:
#   - P-core only  (--cpu-mask 0x0F, pins to performance cores)
#   - Baseline     (no mask, 4 threads, standard scheduler)
#
# JSONL fields: {variant, trial, cpu_mask, decode_tps, prefill_tps}
#
# Usage:
#   bash scripts/bench/pixel_pcores.sh
#
# Output:  results/pixel_pcores_{ts}/pcores_{VARIANT}.jsonl
# Runtime: ~30 min  (2 variants × 2 masks × 10 trials)
# ============================================================

set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ─────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
VARIANTS=(Q2_K Q3_K_M)
CTX=256
NUM_TRIALS=10
OUTPUT_TOKENS=64
THREADS=4
PROMPT="The future of artificial intelligence is"

# CPU masks for Tensor G1 (verified via cpuinfo_max_freq 2026-03-31):
#   CPU0-3: Cortex-A55 @ 1.803 GHz (little)  — 0x0F WRONG, do not use
#   CPU4-5: Cortex-A76 @ 2.253 GHz (medium perf)
#   CPU6-7: Cortex-X1  @ 2.802 GHz (big perf)
#   0xF0 = binary 11110000 = cores 4-7 (A76 + X1, all perf cores, 4 threads)
#   0xC0 = binary 11000000 = cores 6-7 (X1 big only, 2 threads)
# "none" sentinel means no --cpu-mask flag (OS-managed baseline)
CPU_MASKS=(none 0xF0 0xC0)

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_pcores_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

log() { local m="[$(date +%H:%M:%S)] $*"; printf '%s\n' "$m"; printf '%s\n' "$m" >> "$LOGFILE"; }
hr()  { log "$(printf '=%.0s' $(seq 72))"; }

hr
log "Pixel 6a  —  P-core CPU Affinity Test  (CPU, ${THREADS} threads)"
log "Variants  : ${VARIANTS[*]}"
log "Context   : ${CTX}  |  Trials: ${NUM_TRIALS}  |  Output tokens: ${OUTPUT_TOKENS}"
log "CPU masks : none (baseline), 0xF0 (A76+X1 perf cores), 0xC0 (X1 big only)"
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

# ── Preflight: models ─────────────────────────────────────────
MISSING=0
for V in "${VARIANTS[@]}"; do
    if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  Missing on device: ${MODEL_PREFIX}-${V}.gguf"
        MISSING=$((MISSING + 1))
    fi
done
[ "$MISSING" -gt 0 ] && log "FATAL: $MISSING model(s) missing from device." && exit 1
log "All ${#VARIANTS[@]} model(s) present on device"
log ""

# ── Main sweep ────────────────────────────────────────────────
TOTAL_RUNS=$(( ${#VARIANTS[@]} * ${#CPU_MASKS[@]} * NUM_TRIALS ))
CURRENT_RUN=0
START_S=$(date +%s)

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUTPUT_FILE="${RESULTS_DIR}/pcores_${VARIANT}.jsonl"
    > "$OUTPUT_FILE"

    log ""
    log "=== ${VARIANT} ==="

    for CPU_MASK in "${CPU_MASKS[@]}"; do
        # Build the mask flag string (or empty string for baseline)
        if [ "$CPU_MASK" = "none" ]; then
            MASK_FLAG=""
            MASK_LABEL="none"
        else
            MASK_FLAG="--cpu-mask ${CPU_MASK}"
            MASK_LABEL="${CPU_MASK}"
        fi

        log "  --- cpu_mask=${MASK_LABEL} ---"

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            CURRENT_RUN=$(( CURRENT_RUN + 1 ))
            ELAPSED=$(( $(date +%s) - START_S ))
            if [ "$CURRENT_RUN" -gt 1 ]; then
                ETA=$(( ELAPSED * TOTAL_RUNS / CURRENT_RUN - ELAPSED ))
            else
                ETA=0
            fi

            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
                echo '' | ${LLAMA_BIN} \
                -m ${MODEL_PATH} \
                -c ${CTX} \
                -n ${OUTPUT_TOKENS} \
                -t ${THREADS} \
                ${MASK_FLAG} \
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

            if [ "$RAW" = "ADB_ERROR" ]; then
                log "  WARNING: ADB error  variant=${VARIANT} mask=${MASK_LABEL} trial=${TRIAL}"
            fi
            if [ "$RAW_BYTES" -lt 500 ] && [ "$RAW" != "ADB_ERROR" ]; then
                log "  WARNING: Small output (${RAW_BYTES}B)  mask=${MASK_LABEL} trial=${TRIAL} — binary may have failed"
            fi

            printf '{"variant":"%s","context":%d,"trial":%d,"cpu_mask":"%s","decode_tps":%s,"prefill_tps":%s,"raw_bytes":%d,"device":"Pixel6a","backend":"CPU","threads":%d,"n_output_tokens":%d,"ts":"%s"}\n' \
                "$VARIANT" "$CTX" "$TRIAL" "$MASK_LABEL" \
                "$DECODE" "$PREFILL" "$RAW_BYTES" \
                "$THREADS" "$OUTPUT_TOKENS" \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$OUTPUT_FILE"

            log "  [${CURRENT_RUN}/${TOTAL_RUNS} eta=${ETA}s]  ${VARIANT}  ctx=${CTX}  mask=${MASK_LABEL}  trial=${TRIAL}  decode=${DECODE} t/s  prefill=${PREFILL} t/s"
        done
    done

    log "  Saved ${OUTPUT_FILE}  ($(wc -l < "$OUTPUT_FILE" | tr -d ' ') rows)"
done

log ""
hr
log "P-CORE AFFINITY SUMMARY  —  Pixel 6a"
hr

python3 - "$RESULTS_DIR" "${VARIANTS[@]}" << 'PYEOF'
import json, glob, sys, statistics
from collections import defaultdict

results_dir = sys.argv[1]
requested   = sys.argv[2:]

for variant in requested:
    paths = glob.glob(f"{results_dir}/pcores_{variant}.jsonl")
    if not paths:
        continue
    data = [json.loads(l) for l in open(paths[0]) if l.strip()]
    by_mask = defaultdict(list)
    for d in data:
        if float(d.get("decode_tps", 0)) > 0:
            by_mask[d["cpu_mask"]].append(float(d["decode_tps"]))

    print(f"\n{'='*60}")
    print(f"  {variant}")
    print(f"{'='*60}")
    masks = sorted(by_mask.keys())
    baseline_mu = None
    for mask in masks:
        vals = by_mask[mask]
        if not vals:
            print(f"  mask={mask:<6}:  no valid data")
            continue
        mu = statistics.mean(vals)
        sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
        label = "baseline" if mask == "none" else "P-cores only"
        note = ""
        if baseline_mu is not None and baseline_mu > 0:
            pct = (mu - baseline_mu) / baseline_mu * 100
            note = f"  ({pct:+.1f}% vs baseline)"
        else:
            baseline_mu = mu
        print(f"  mask={mask:<6} ({label}):  decode={mu:.2f}+/-{sd:.2f} t/s  (n={len(vals)}){note}")
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
