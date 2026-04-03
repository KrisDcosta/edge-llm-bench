#!/bin/bash
# ================================================================
# pixel_master_overnight.sh — Full overnight queue for Pixel 6a
#
# Jobs (sequential, ~13–15 hours total):
#
#   JOB 1 — Fine-grained cliff sweep        ~2.5 hrs
#            5 Llama variants × 13 ctx pts × 3 trials
#
#   JOB 2 — Q4_K_S + Q5_K_M TPS sweep      ~40 min
#            2 missing variants × 4 ctx × 10 trials
#
#   JOB 3 — Full WikiText-2 PPL             ~6.5 hrs
#            5 variants needing full-corpus rerun
#
#   JOB 4 — Qwen 2.5 1.5B TPS on Pixel     ~45 min
#            7 variants × 4 ctx × 5 trials
#            (pushes models if needed — ensure ~10 GB free on device)
#
#   JOB 5 — Remaining quality benchmarks    ~3 hrs
#            ARC-Challenge, HellaSwag, MMLU × 7 variants × 100q
#            (TruthfulQA skipped — MC1 format trivially 100%)
#
# Usage:
#   bash scripts/pixel_master_overnight.sh
#   bash scripts/pixel_master_overnight.sh --skip-ppl    # skip slow PPL
#   bash scripts/pixel_master_overnight.sh --skip-qwen   # skip Qwen push
#
# All results saved to timestamped dirs in results/.
# All output teed to results/overnight_{timestamp}.log.
# ================================================================

set -euo pipefail
cd "$(dirname "$0")/.."   # always run from project root

SKIP_PPL=0
SKIP_QWEN=0
for arg in "$@"; do
    case "$arg" in
        --skip-ppl)  SKIP_PPL=1  ;;
        --skip-qwen) SKIP_QWEN=1 ;;
    esac
done

TS=$(date +%Y%m%d_%H%M%S)
LOGFILE="results/overnight_${TS}.log"
mkdir -p results

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }
hr()  { log "================================================================"; }
elapsed() { echo $(( ($(date +%s) - MASTER_START) / 60 )) ; }

MASTER_START=$(date +%s)

hr
log "PIXEL 6a MASTER OVERNIGHT QUEUE"
log "Start : $(date)"
log "Log   : $LOGFILE"
log "skip-ppl  = $SKIP_PPL"
log "skip-qwen = $SKIP_QWEN"
hr

# ----------------------------------------------------------------
# PREFLIGHT: device + binaries
# ----------------------------------------------------------------
log ""
log "PREFLIGHT CHECKS"

if ! adb devices 2>/dev/null | grep -q "device$"; then
    log "❌ FATAL: No Android device found. Is USB connected?"
    exit 1
fi
log "  ✅ Device connected"

DEVICE_DIR="/data/local/tmp"
if ! adb shell "ls ${DEVICE_DIR}/llama-completion 2>/dev/null" | grep -q "llama-completion"; then
    log "❌ FATAL: llama-completion not found on device at ${DEVICE_DIR}/llama-completion"
    exit 1
fi
log "  ✅ llama-completion present on device"

if ! adb shell "ls ${DEVICE_DIR}/llama-perplexity 2>/dev/null" | grep -q "llama-perplexity"; then
    log "  ⚠️  llama-perplexity not found on device — JOB 3 (PPL) will fail"
    [ "$SKIP_PPL" = "0" ] && SKIP_PPL=1 && log "  ⚠️  Auto-skipping PPL (llama-perplexity missing)"
fi

# Check Llama models
MISSING_MODELS=0
for V in Q2_K Q3_K_M Q4_K_M Q6_K Q8_0; do
    if ! adb shell "ls ${DEVICE_DIR}/Llama-3.2-3B-Instruct-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ⚠️  Missing on device: Llama ${V}"
        MISSING_MODELS=$((MISSING_MODELS + 1))
    fi
done

# Also check Q4_K_S and Q5_K_M for JOB 2
for V in Q4_K_S Q5_K_M; do
    if ! adb shell "ls ${DEVICE_DIR}/Llama-3.2-3B-Instruct-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
        log "  ⚠️  Missing on device: Llama ${V} (needed for JOB 2 — TPS sweep)"
    fi
done

log "  Preflight complete. Missing base models: $MISSING_MODELS"
log ""

# ================================================================
# JOB 1: Fine-grained KV-cache cliff sweep
# ================================================================
hr
log "JOB 1 / 5 — Fine-grained cliff sweep (Llama 3.2 3B)"
log "7 variants × 13 context points × 3 trials"
log "Expected: ~3.5 hours"
hr

J1_START=$(date +%s)
bash scripts/pixel_cliff_sweep.sh Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0 2>&1 | tee -a "$LOGFILE" || {
    log "⚠️  JOB 1 exited non-zero — results may be partial"
}
J1_MINS=$(( ($(date +%s) - J1_START) / 60 ))
log "✅ JOB 1 done in ${J1_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# JOB 2: Q4_K_S + Q5_K_M TPS sweep (completing the 7-variant table)
# ================================================================
hr
log "JOB 2 / 5 — Q4_K_S + Q5_K_M TPS sweep"
log "2 variants × 4 contexts × 10 trials"
log "Expected: ~40 min"
hr

J2_START=$(date +%s)
J2_DIR="results/pixel_tps_addl_${TS}"
mkdir -p "$J2_DIR"

for VARIANT in Q4_K_S Q5_K_M; do
    MODEL="${DEVICE_DIR}/Llama-3.2-3B-Instruct-${VARIANT}.gguf"
    if ! adb shell "ls ${MODEL} 2>/dev/null" | grep -q ".gguf"; then
        log "  ⚠️  SKIP $VARIANT — not on device"
        continue
    fi
    log "  Benchmarking $VARIANT..."
    for CTX in 256 512 1024 2048; do
        OUT="${J2_DIR}/${VARIANT}_ctx${CTX}.jsonl"
        > "$OUT"
        for TRIAL in $(seq 1 10); do
            RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && echo '' | ${DEVICE_DIR}/llama-completion \
                -m ${MODEL} -c ${CTX} -n 64 \
                -p 'The future of artificial intelligence is' -t 4 2>&1" 2>/dev/null || echo "")

            DECODE=$(echo "$RAW" | grep -E "llama_perf_context_print:.*eval time" | grep -v "prompt" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" | awk '{print $1}' | head -1)
            [ -z "$DECODE" ] && DECODE="0"

            PREFILL=$(echo "$RAW" | grep -E "prompt eval time" \
                | grep -oE "[0-9]+\.[0-9]+ tokens per second" | awk '{print $1}' | head -1)
            [ -z "$PREFILL" ] && PREFILL="0"

            echo "{\"variant\":\"${VARIANT}\",\"context_length\":${CTX},\"trial\":${TRIAL},\"decode_tps\":${DECODE},\"prefill_tps\":${PREFILL},\"device\":\"Pixel6a\",\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" >> "$OUT"
            log "  $VARIANT ctx=${CTX} t=${TRIAL}: ${DECODE} t/s"
        done
    done
done

# Quick summary for JOB 2
python3 - "$J2_DIR" << 'PYEOF' 2>/dev/null | tee -a "$LOGFILE" || true
import json, glob, sys
from collections import defaultdict
data = defaultdict(lambda: defaultdict(list))
for f in glob.glob(f"{sys.argv[1]}/*.jsonl"):
    for line in open(f):
        try:
            r = json.loads(line)
            if float(r.get("decode_tps", 0)) > 0:
                data[r["variant"]][r["context_length"]].append(float(r["decode_tps"]))
        except: pass
for v in ["Q4_K_S","Q5_K_M"]:
    if v not in data: continue
    row = f"{v}: " + " | ".join(f"ctx={c}: {sum(data[v].get(c,[0]))/max(len(data[v].get(c,[1])),1):.2f} t/s" for c in [256,512,1024,2048])
    print(row)
PYEOF

J2_MINS=$(( ($(date +%s) - J2_START) / 60 ))
log "✅ JOB 2 done in ${J2_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# JOB 3: Full WikiText-2 PPL (5 variants on full corpus)
# ================================================================
hr
log "JOB 3 / 5 — Full WikiText-2 Perplexity"
log "5 variants needing full-corpus rerun: Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"
log "Expected: ~6.5 hours"
hr

J3_START=$(date +%s)
if [ "$SKIP_PPL" = "1" ]; then
    log "  ⚠️  Skipping PPL (--skip-ppl or llama-perplexity missing)"
else
    bash scripts/run_perplexity_full.sh Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0 2>&1 | tee -a "$LOGFILE" || {
        log "⚠️  JOB 3 exited non-zero — check PPL results manually"
    }
fi
J3_MINS=$(( ($(date +%s) - J3_START) / 60 ))
log "✅ JOB 3 done in ${J3_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# JOB 4: Qwen 2.5 1.5B TPS on Pixel
# ================================================================
hr
log "JOB 4 / 5 — Qwen 2.5 1.5B TPS sweep on Pixel"
log "7 variants × 4 contexts × 5 trials"
log "Note: will push models if not already on device (~10 GB push if needed)"
log "Expected: ~45 min (plus push time if models not on device)"
hr

J4_START=$(date +%s)
if [ "$SKIP_QWEN" = "1" ]; then
    log "  ⚠️  Skipping Qwen sweep (--skip-qwen)"
else
    bash scripts/pixel_qwen_tps.sh 2>&1 | tee -a "$LOGFILE" || {
        log "⚠️  JOB 4 exited non-zero — Qwen models may not be on device"
    }
fi
J4_MINS=$(( ($(date +%s) - J4_START) / 60 ))
log "✅ JOB 4 done in ${J4_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# JOB 5: Remaining quality benchmarks
# ================================================================
hr
log "JOB 5 / 5 — Remaining quality benchmarks"
log "ARC-Challenge, HellaSwag, MMLU × all 7 Llama variants × 100 questions each"
log "Note: TruthfulQA skipped (MC1 format causes trivially perfect baseline scores)"
log "Expected: ~3 hours"
hr

J5_START=$(date +%s)
ALL7="Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"

for DATASET_TAG in "data/arc_challenge_100.yaml:arc_challenge" \
                   "data/hellaswag_100.yaml:hellaswag" \
                   "data/mmlu_100.yaml:mmlu"; do
    DATASET_FILE="${DATASET_TAG%%:*}"
    DATASET_TAG_NAME="${DATASET_TAG##*:}"

    log ""
    log "  Running $DATASET_TAG_NAME on all 7 variants..."
    python3 scripts/quality_eval.py \
        --dataset "$DATASET_FILE" \
        --tag "$DATASET_TAG_NAME" \
        $ALL7 2>&1 | tee -a "$LOGFILE" || {
        log "  ⚠️  $DATASET_TAG_NAME exited non-zero — partial results may be saved"
    }
    log "  ✅ $DATASET_TAG_NAME done"
done

# Print quality summary
log ""
log "Quality results summary:"
python3 - << 'PYEOF' 2>/dev/null | tee -a "$LOGFILE" || true
import json
data = json.load(open("results/quality_scores.json"))
tags = ["arc_challenge", "hellaswag", "mmlu"]
variants = ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]
header = f"{'Variant':<10}" + "".join(f"{t:>15}" for t in tags)
print(header)
print("-" * (10 + 15*len(tags)))
for v in variants:
    row = f"{v:<10}"
    for t in tags:
        k = f"{t}:{v}"
        if k in data:
            acc = data[k].get("accuracy_pct", 0)
            row += f"{acc:14.1f}%"
        else:
            row += f"{'N/A':>15}"
    print(row)
PYEOF

J5_MINS=$(( ($(date +%s) - J5_START) / 60 ))
log "✅ JOB 5 done in ${J5_MINS} min  |  Total elapsed: $(elapsed) min"

# ================================================================
# FINAL SUMMARY
# ================================================================
TOTAL_MINS=$(elapsed)
hr
log "OVERNIGHT RUN COMPLETE"
log "Total runtime   : ${TOTAL_MINS} min ($(( TOTAL_MINS / 60 ))h $(( TOTAL_MINS % 60 ))m)"
log ""
log "JOB 1 Cliff sweep : ${J1_MINS} min  → results/pixel_cliff_sweep_*/"
log "JOB 2 TPS addl    : ${J2_MINS} min  → results/pixel_tps_addl_${TS}/"
log "JOB 3 PPL full    : ${J3_MINS} min  → (adb shell, pull with parse_perplexity_results.sh)"
log "JOB 4 Qwen TPS    : ${J4_MINS} min  → results/pixel_qwen_tps_*/"
log "JOB 5 Benchmarks  : ${J5_MINS} min  → results/quality_scores.json"
log ""
log "Full log: $LOGFILE"
hr
