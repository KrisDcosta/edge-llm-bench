#!/usr/bin/env bash
# ============================================================
# pixel_gsm8k.sh  --  GSM8K grade-school math evaluation
#                      Pixel 6a  *  CPU (4 threads)  *  via ADB
#
# Evaluates all 7 K-quant variants of Llama-3.2-3B-Instruct on
# 50 GSM8K test questions using 5-shot chain-of-thought prompting.
#
# Usage:
#   bash scripts/bench/pixel_gsm8k.sh              # all 7 variants
#   bash scripts/bench/pixel_gsm8k.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/pixel_gsm8k.sh --dry-run     # show commands, no ADB
#   bash scripts/bench/pixel_gsm8k.sh --resume      # skip completed variants
#
# Prerequisites:
#   - Pixel 6a connected via ADB
#   - /data/local/tmp/llama-completion on device
#   - All 7 GGUF model files at /data/local/tmp/ on device
#   - python3 on host (for data download and summary)
#
# Output:
#   results/pixel_gsm8k_TIMESTAMP/results_VARIANT.jsonl
#     -- per question: variant, question_id, question, answer,
#                      predicted, correct, decode_tps
#   Console: per-variant accuracy and overall summary table
#
# Runtime:  ~2-4 h (7 variants x 50 questions each; ~4-6 min/question)
# Full set: 1319 questions x 7 variants ≈ 26 h/variant
# ============================================================

# Bash 3.2 compatible -- no associative arrays, no [[ =~ ]] with captures
set -euo pipefail
cd "$(dirname "$0")/../.."

# ── Configuration ────────────────────────────────────────────
DEVICE_DIR="/data/local/tmp"
LLAMA_BIN="${DEVICE_DIR}/llama-completion"
MODEL_PREFIX="Llama-3.2-3B-Instruct"
ALL_VARIANTS="Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0"
THREADS=4
CTX=512
N_PREDICT=256
# Greedy decoding: temperature 0 (deterministic)
TEMPERATURE=0.0
GSM8K_DATA="data/gsm8k_test.jsonl"

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_gsm8k_${TS}"
LOGFILE="${RESULTS_DIR}.log"
mkdir -p "$RESULTS_DIR" results

# ── Logging ──────────────────────────────────────────────────
log() {
    local m
    m="[$(date +%H:%M:%S)] $*"
    printf '%s\n' "$m"
    printf '%s\n' "$m" >> "$LOGFILE"
}
hr() { log "$(printf '=%.0s' $(seq 72))"; }

# ── Argument parsing ─────────────────────────────────────────
DRY_RUN=0
RESUME=0
VARIANTS=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --resume)  RESUME=1  ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS="${VARIANTS} ${arg}" ;;
        *)
            printf 'Unknown argument: %s\n' "$arg" >&2
            printf 'Valid variants : Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0\n' >&2
            printf 'Valid flags    : --dry-run  --resume\n' >&2
            exit 1
            ;;
    esac
done
# Trim leading space
VARIANTS="${VARIANTS# }"
[ -z "$VARIANTS" ] && VARIANTS="$ALL_VARIANTS"

hr
log "Pixel 6a  --  GSM8K Evaluation  (5-shot CoT, greedy)"
log "Variants : ${VARIANTS}"
log "Questions: 50 per variant  (subset; full=1319)"
log "Context  : ${CTX}  |  Output tokens: ${N_PREDICT}"
log "Results  : ${RESULTS_DIR}"
log "Log      : ${LOGFILE}"
[ "$DRY_RUN" -eq 1 ] && log "  *** DRY RUN -- commands printed but not executed ***"
hr

# ── Preflight: ADB device ─────────────────────────────────────
if [ "$DRY_RUN" -eq 0 ]; then
    if ! adb devices 2>/dev/null | grep -q "device$"; then
        log "FATAL: No Android device connected via ADB."
        exit 1
    fi
    DEVICE_ID=$(adb devices 2>/dev/null | grep "device$" | awk '{print $1}' | head -1)
    log "OK  Device: ${DEVICE_ID}"

    if ! adb shell "ls ${LLAMA_BIN} 2>/dev/null" | grep -q "llama-completion"; then
        log "FATAL: ${LLAMA_BIN} not found on device."
        exit 1
    fi
    log "OK  llama-completion found"

    MISSING=0
    for V in $VARIANTS; do
        if ! adb shell "ls ${DEVICE_DIR}/${MODEL_PREFIX}-${V}.gguf 2>/dev/null" | grep -q ".gguf"; then
            log "  MISSING on device: ${MODEL_PREFIX}-${V}.gguf"
            MISSING=$((MISSING + 1))
        fi
    done
    [ "$MISSING" -gt 0 ] && log "FATAL: ${MISSING} model(s) missing from device." && exit 1
    log "OK  All requested model(s) present on device"
fi

# ── Ensure GSM8K data exists ──────────────────────────────────
if [ ! -f "$GSM8K_DATA" ]; then
    log "GSM8K data not found at ${GSM8K_DATA}; running download helper ..."
    if [ "$DRY_RUN" -eq 1 ]; then
        log "  DRY RUN: python3 scripts/eval/download_gsm8k.py"
    else
        if ! python3 scripts/eval/download_gsm8k.py --n 50 --out "$GSM8K_DATA"; then
            log "FATAL: Could not download or create GSM8K data."
            exit 1
        fi
    fi
fi

if [ "$DRY_RUN" -eq 0 ]; then
    Q_COUNT=$(wc -l < "$GSM8K_DATA" | tr -d ' ')
    log "OK  ${GSM8K_DATA}  (${Q_COUNT} questions)"
fi
log ""

# ── 5-shot CoT prompt prefix ─────────────────────────────────
# Standard GSM8K 5-shot examples (public domain training data).
# Each example uses step-by-step reasoning followed by #### ANSWER.
FEWSHOT="Solve the following math problems step by step. End your answer with #### followed by the final number.

Q: There are 15 trees in the grove. Grove workers will plant trees in the grove today. After they are done, there will be 21 trees. How many trees did the grove workers plant today?
A: There are 15 trees originally. Then there were 21 trees after some more were planted. So there must have been 21 - 15 = 6. #### 6

Q: If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?
A: There are originally 3 cars. 2 more cars arrive. 3 + 2 = 5. #### 5

Q: Leah had 32 chocolates and her sister had 42. If they ate 35, how many pieces do they have left in total?
A: Originally, Leah had 32 chocolates. Her sister had 42. So in total they had 32 + 42 = 74. After eating 35, they had 74 - 35 = 39. #### 39

Q: Jason had 20 lollipops. He gave Denny some lollipops. Now Jason has 12 lollipops. How many lollipops did Jason give to Denny?
A: Jason started with 20 lollipops. Then he gave some to Denny. He had 12 left. So he gave Denny 20 - 12 = 8. #### 8

Q: Shawn has five toys. For Christmas, he got two toys each from his mom and dad. How many toys does he have now?
A: Shawn started with 5 toys. If he got 2 toys each from his mom and dad, then that is 4 more toys. 5 + 4 = 9. #### 9

Q: "

# ── Run evaluation ───────────────────────────────────────────
START_S=$(date +%s)
# Count total variants
N_VARIANTS=0
for V in $VARIANTS; do N_VARIANTS=$((N_VARIANTS + 1)); done
VARIANT_NUM=0

for VARIANT in $VARIANTS; do
    VARIANT_NUM=$((VARIANT_NUM + 1))
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUT_FILE="${RESULTS_DIR}/results_${VARIANT}.jsonl"

    # Resume: check if already complete (50 lines)
    if [ "$RESUME" -eq 1 ] && [ -f "$OUT_FILE" ]; then
        DONE_LINES=$(wc -l < "$OUT_FILE" | tr -d ' ')
        if [ "$DONE_LINES" -ge 50 ]; then
            log "SKIP ${VARIANT} -- already complete (${DONE_LINES} rows)"
            continue
        fi
        log "RESUME ${VARIANT} -- found ${DONE_LINES} existing rows; continuing from Q${DONE_LINES}"
        RESUME_FROM=$DONE_LINES
    else
        RESUME_FROM=0
        > "$OUT_FILE"
    fi

    log ""
    log "=== ${VARIANT}  [${VARIANT_NUM}/${N_VARIANTS}] ==="

    CORRECT=0
    TOTAL=0
    Q_NUM=0

    # Read questions from JSONL using Python to handle JSON parsing reliably
    # We emit tab-separated: question_id\tquestion\tanswer
    # shellcheck disable=SC2016
    QUESTIONS=$(python3 -c "
import json, sys
with open('${GSM8K_DATA}', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        qid = obj.get('question_id', 0)
        q   = obj.get('question', '').replace('\t', ' ').replace('\n', ' ')
        a   = obj.get('answer', '').strip()
        print(f'{qid}\t{q}\t{a}')
" 2>/dev/null)

    while IFS="	" read -r QID QUESTION ANSWER; do
        Q_NUM=$((Q_NUM + 1))

        # Resume: skip already-processed questions
        if [ "$Q_NUM" -le "$RESUME_FROM" ]; then
            CORRECT=$((CORRECT + 1))  # approximate; recount at end if needed
            TOTAL=$((TOTAL + 1))
            continue
        fi

        ELAPSED=$(( $(date +%s) - START_S ))
        if [ "$TOTAL" -gt 0 ]; then
            ETA=$(( ELAPSED * 50 / TOTAL - ELAPSED )) 2>/dev/null || ETA=0
        else
            ETA=0
        fi

        # Build full prompt: 5-shot prefix + question
        PROMPT="${FEWSHOT}${QUESTION}
A:"

        if [ "$DRY_RUN" -eq 1 ]; then
            log "  [${Q_NUM}/50 eta=${ETA}s]  ${VARIANT}  Q${QID}  DRY RUN"
            printf '{"variant":"%s","question_id":%s,"question":"%s","answer":"%s","predicted":"DRY","correct":false,"decode_tps":0}\n' \
                "$VARIANT" "$QID" "$(printf '%s' "$QUESTION" | sed 's/"/\\"/g')" "$ANSWER" >> "$OUT_FILE"
            TOTAL=$((TOTAL + 1))
            continue
        fi

        # Write prompt to a temp file on device to avoid shell escaping issues
        PROMPT_DEVICE="/data/local/tmp/gsm8k_prompt_$$.txt"

        # Push prompt via adb shell stdin pipe
        # We use printf to avoid echo's escape interpretation differences
        printf '%s' "$PROMPT" | adb shell "cat > ${PROMPT_DEVICE}" 2>/dev/null || true

        # Run inference; capture full output including stderr for timing
        RAW=$(adb shell "export LD_LIBRARY_PATH=${DEVICE_DIR} && \
            ${LLAMA_BIN} \
            -m ${MODEL_PATH} \
            -c ${CTX} \
            -n ${N_PREDICT} \
            --temp ${TEMPERATURE} \
            -t ${THREADS} \
            -f ${PROMPT_DEVICE} \
            --no-display-prompt \
            2>&1" 2>/dev/null || echo "ADB_ERROR")

        # Clean up temp prompt
        adb shell "rm -f ${PROMPT_DEVICE}" 2>/dev/null || true

        # Extract decode TPS from llama.cpp perf output
        # Pattern: "common_perf_print:        eval time = ... X.XX tokens per second"
        DECODE_TPS=$(printf '%s\n' "$RAW" \
            | grep -E "common_perf_print:.*eval time" \
            | grep -v "prompt" \
            | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
            | awk '{print $1}' | head -1 || true)
        [ -z "$DECODE_TPS" ] && DECODE_TPS="0"

        # Strip llama.cpp log lines (start with "llama_" or "ggml_" etc.) to isolate generated text
        GENERATED=$(printf '%s\n' "$RAW" \
            | grep -v "^llama" \
            | grep -v "^ggml" \
            | grep -v "^common_perf" \
            | grep -v "^system_info" \
            | grep -v "^sampling" \
            | grep -v "^generate" \
            | grep -v "^Log start" \
            | grep -v "^main:" \
            | grep -v "^build:" \
            | grep -v "^load_" \
            | grep -v "^\[" \
            | tr -d '\r' \
            || true)

        # Extract predicted answer: look for "#### N" pattern first, then last number
        PREDICTED=$(printf '%s\n' "$GENERATED" \
            | grep -oE '####[[:space:]]*[0-9,]+' \
            | tail -1 \
            | grep -oE '[0-9,]+' \
            | tr -d ',' \
            || true)

        if [ -z "$PREDICTED" ]; then
            # Fall back: last standalone number in output
            PREDICTED=$(printf '%s\n' "$GENERATED" \
                | grep -oE '\b[0-9][0-9,]*\b' \
                | tail -1 \
                | tr -d ',' \
                || true)
        fi
        [ -z "$PREDICTED" ] && PREDICTED="NONE"

        # Exact match comparison (both digits only, no commas)
        ANSWER_CLEAN=$(printf '%s' "$ANSWER" | tr -d ',')
        PREDICTED_CLEAN=$(printf '%s' "$PREDICTED" | tr -d ',')

        if [ "$PREDICTED_CLEAN" = "$ANSWER_CLEAN" ] && [ "$PREDICTED_CLEAN" != "NONE" ]; then
            CORRECT_FLAG="true"
            CORRECT=$((CORRECT + 1))
            MARK="PASS"
        else
            CORRECT_FLAG="false"
            MARK="FAIL"
        fi

        TOTAL=$((TOTAL + 1))

        # Escape question and generated text for JSON
        Q_JSON=$(printf '%s' "$QUESTION"  | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$QUESTION")
        G_JSON=$(printf '%s' "$GENERATED" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '"%s"' "$GENERATED")

        printf '{"variant":"%s","question_id":%s,"question":%s,"answer":"%s","predicted":"%s","correct":%s,"decode_tps":%s,"generated":%s}\n' \
            "$VARIANT" "$QID" "$Q_JSON" "$ANSWER_CLEAN" "$PREDICTED_CLEAN" "$CORRECT_FLAG" "$DECODE_TPS" "$G_JSON" \
            >> "$OUT_FILE"

        ACC=$(( CORRECT * 100 / TOTAL ))
        log "  [${Q_NUM}/50 eta=${ETA}s]  ${VARIANT}  Q${QID}  pred=${PREDICTED_CLEAN}  ans=${ANSWER_CLEAN}  ${MARK}  acc=${ACC}%  tps=${DECODE_TPS}"

    done <<QEOF
${QUESTIONS}
QEOF

    FINAL_ACC=0
    [ "$TOTAL" -gt 0 ] && FINAL_ACC=$(( CORRECT * 100 / TOTAL ))
    log ""
    log "  VARIANT ${VARIANT}  DONE  --  Accuracy: ${CORRECT}/${TOTAL}  (${FINAL_ACC}%)"
    log "  Saved: ${OUT_FILE}"
done

# ── Summary table ─────────────────────────────────────────────
log ""
hr
log "GSM8K SUMMARY  --  Pixel 6a  --  Llama-3.2-3B  --  50 questions (5-shot CoT)"
hr

python3 - "$RESULTS_DIR" $VARIANTS << 'PYEOF'
import json
import glob
import sys
from pathlib import Path

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

print(f"\n  {'Variant':<12}  {'Correct':>7}  {'Total':>5}  {'Accuracy':>9}  {'Avg TPS':>8}")
print("  " + "-" * 48)

for v in requested:
    paths = glob.glob(f"{results_dir}/results_{v}.jsonl")
    if not paths:
        continue
    records = [json.loads(l) for l in open(paths[0]) if l.strip()]
    if not records:
        continue
    correct = sum(1 for r in records if r.get("correct"))
    total   = len(records)
    acc     = 100.0 * correct / total if total else 0.0
    tps_vals = [float(r["decode_tps"]) for r in records if float(r.get("decode_tps", 0)) > 0]
    avg_tps  = sum(tps_vals) / len(tps_vals) if tps_vals else 0.0
    print(f"  {v:<12}  {correct:>7}  {total:>5}  {acc:>8.1f}%  {avg_tps:>7.2f}")

print()
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
