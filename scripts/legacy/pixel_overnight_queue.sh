#!/bin/bash
# ================================================================
# pixel_overnight_queue.sh — Pixel 6a overnight benchmark queue
# Run from Mac: bash scripts/pixel_overnight_queue.sh
#
# Queue (sequential, ~7-10 hours total):
#   1. ARC-Easy RERUN (fixed eval) — all 7 variants          ~3.0 hrs
#   2. BoolQ missing variants (Q3_K_M, Q4_K_S, Q5_K_M)      ~2.5 hrs
#
# Results are pulled back to results/pixel_overnight_YYYYMMDD/
# ================================================================

set -e
LOGFILE="results/pixel_overnight_$(date +%Y%m%d_%H%M%S).log"
RESULT_DIR="results/pixel_overnight_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULT_DIR"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOGFILE"; }

log "===== Pixel 6a Overnight Queue Starting ====="
log "Results → $RESULT_DIR"
log "Log     → $LOGFILE"
log ""

# Verify device connected
if ! adb devices | grep -q "device$"; then
    log "❌ ERROR: No Pixel device found. Is USB plugged in?"
    exit 1
fi
log "✅ Pixel 6a connected"

# ----------------------------------------------------------------
# STEP 1: ARC-Easy RERUN with fixed extraction logic
# ----------------------------------------------------------------
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "STEP 1: ARC-Easy RERUN (fixed eval) — 7 variants × 100 Qs"
log "Expected: ~3 hours"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

STEP1_START=$(date +%s)

python3 scripts/quality_eval.py \
    --dataset data/arc_easy_100.yaml \
    --tag arc_easy_fixed \
    Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0 \
    2>&1 | tee -a "$LOGFILE"

STEP1_END=$(date +%s)
STEP1_MINS=$(( (STEP1_END - STEP1_START) / 60 ))
log "✅ STEP 1 done in ${STEP1_MINS} minutes"

# Pull intermediate results
log "Pulling ARC-Easy results from device..."
python3 -c "
import json, shutil
with open('results/quality_scores.json') as f:
    data = json.load(f)
arc = {k:v for k,v in data.items() if 'arc_easy_fixed' in k}
with open('$RESULT_DIR/arc_easy_fixed_results.json', 'w') as f:
    json.dump(arc, f, indent=2)
print(f'Saved {len(arc)} ARC-Easy results')
for k,v in sorted(arc.items()):
    print(f'  {k}: {v[\"accuracy_pct\"]}% ({v[\"correct\"]}/{v[\"total\"]})')
" | tee -a "$LOGFILE"

# ----------------------------------------------------------------
# STEP 2: BoolQ for missing variants
# ----------------------------------------------------------------
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "STEP 2: BoolQ — missing variants (Q3_K_M, Q4_K_S, Q5_K_M)"
log "Expected: ~2.5 hours"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

STEP2_START=$(date +%s)

python3 scripts/quality_eval.py \
    --dataset data/boolq_100.yaml \
    --tag boolq \
    Q3_K_M Q4_K_S Q5_K_M \
    2>&1 | tee -a "$LOGFILE"

STEP2_END=$(date +%s)
STEP2_MINS=$(( (STEP2_END - STEP2_START) / 60 ))
log "✅ STEP 2 done in ${STEP2_MINS} minutes"

# ----------------------------------------------------------------
# FINAL: Pull all results & generate summary
# ----------------------------------------------------------------
log ""
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
log "FINAL RESULTS SUMMARY"
log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

python3 << 'SUMMARY_EOF'
import json

with open('results/quality_scores.json') as f:
    data = json.load(f)

# BoolQ complete table
print("\n=== BoolQ Accuracy (Pixel 6a, Llama 3.2 3B) ===")
boolq_variants = ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0','F16']
for v in boolq_variants:
    k = f'boolq:{v}'
    if k in data:
        d = data[k]
        print(f"  {v:10}: {d['accuracy_pct']:5.1f}% ({d['correct']}/{d['total']})")

# ARC-Easy fixed table
print("\n=== ARC-Easy Accuracy (FIXED, Pixel 6a, Llama 3.2 3B) ===")
arc_variants = ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']
for v in arc_variants:
    k = f'arc_easy_fixed:{v}'
    if k in data:
        d = data[k]
        print(f"  {v:10}: {d['accuracy_pct']:5.1f}% ({d['correct']}/{d['total']})")
    else:
        print(f"  {v:10}: NOT RUN")
SUMMARY_EOF

log ""
log "===== Pixel 6a Overnight Queue COMPLETE ====="
log "Total runtime: $(( ($(date +%s) - STEP1_START) / 60 )) minutes"
log "Results in: $RESULT_DIR"
log "Full quality data: results/quality_scores.json"
