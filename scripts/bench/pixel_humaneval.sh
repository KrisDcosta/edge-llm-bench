#!/usr/bin/env bash
# ============================================================
# pixel_humaneval.sh  --  HumanEval code generation evaluation
#                          Pixel 6a  *  CPU (4 threads)  *  via ADB
#
# Evaluates all 7 K-quant variants of Llama-3.2-3B-Instruct on
# the first 50 HumanEval problems (problems 0-49).
#
# Device limitation: Python cannot run on the Pixel 6a.
# Strategy:
#   1. Push each prompt to device, run llama-completion, capture output.
#   2. Strip llama.cpp log lines; save raw generated text on Mac.
#   3. Write per-question JSONL records locally.
#   4. After all variants, offer to run eval_humaneval.py locally for
#      syntax + execution scoring.
#
# Usage:
#   bash scripts/bench/pixel_humaneval.sh              # all 7 variants
#   bash scripts/bench/pixel_humaneval.sh Q4_K_M Q8_0  # subset
#   bash scripts/bench/pixel_humaneval.sh --dry-run     # show commands, no ADB
#   bash scripts/bench/pixel_humaneval.sh --resume      # skip completed variants
#   bash scripts/bench/pixel_humaneval.sh --eval        # run local eval after capture
#
# Prerequisites:
#   - Pixel 6a connected via ADB
#   - /data/local/tmp/llama-completion on device
#   - All 7 GGUF model files at /data/local/tmp/ on device
#   - python3 on host (for data download and evaluation)
#
# Output:
#   results/pixel_humaneval_TIMESTAMP/results_VARIANT.jsonl
#     -- per problem: variant, problem_id, task_id, prompt,
#                     generated_code, syntax_ok, test_passed, decode_tps
#
# Runtime:  ~1-3 h (7 variants x 50 problems; ~1-3 min/problem)
# ============================================================

# Bash 3.2 compatible
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
# Slightly above 0 for code generation -- avoid degenerate greedy loops
# Use 0 for fully deterministic; 0.1 is common for code evals
TEMPERATURE=0.1
HE_DATA="data/humaneval_50.jsonl"
N_PROBLEMS=50

TS=$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/pixel_humaneval_${TS}"
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
RUN_EVAL=0
VARIANTS=""
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --resume)  RESUME=1  ;;
        --eval)    RUN_EVAL=1 ;;
        Q2_K|Q3_K_M|Q4_K_S|Q4_K_M|Q5_K_M|Q6_K|Q8_0) VARIANTS="${VARIANTS} ${arg}" ;;
        *)
            printf 'Unknown argument: %s\n' "$arg" >&2
            printf 'Valid variants : Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0\n' >&2
            printf 'Valid flags    : --dry-run  --resume  --eval\n' >&2
            exit 1
            ;;
    esac
done
VARIANTS="${VARIANTS# }"
[ -z "$VARIANTS" ] && VARIANTS="$ALL_VARIANTS"

hr
log "Pixel 6a  --  HumanEval Code Generation  (problems 0-49)"
log "Variants : ${VARIANTS}"
log "Problems : ${N_PROBLEMS}  (first 50 of 164)"
log "Context  : ${CTX}  |  Output tokens: ${N_PREDICT}  |  Temp: ${TEMPERATURE}"
log "Results  : ${RESULTS_DIR}"
log "Log      : ${LOGFILE}"
[ "$DRY_RUN"  -eq 1 ] && log "  *** DRY RUN -- commands printed but not executed ***"
[ "$RUN_EVAL" -eq 1 ] && log "  Local eval (syntax + exec) will run after capture"
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

# ── Ensure HumanEval data exists ──────────────────────────────
if [ ! -f "$HE_DATA" ]; then
    log "HumanEval data not found at ${HE_DATA}; running download helper ..."
    if [ "$DRY_RUN" -eq 1 ]; then
        log "  DRY RUN: python3 scripts/eval/download_humaneval.py --n 50 --out ${HE_DATA}"
    else
        if ! python3 scripts/eval/download_humaneval.py --n 50 --out "$HE_DATA"; then
            log "FATAL: Could not download or create HumanEval data."
            exit 1
        fi
    fi
fi

if [ "$DRY_RUN" -eq 0 ]; then
    P_COUNT=$(wc -l < "$HE_DATA" | tr -d ' ')
    log "OK  ${HE_DATA}  (${P_COUNT} problems)"
fi
log ""

# ── Extract problems into tab-separated lines ─────────────────
# Fields: problem_id  TAB  task_id  TAB  entry_point  TAB  prompt
# We use Python to parse JSON and emit safe single-line tab-separated records.
PROBLEMS=$(python3 -c "
import json, sys
with open('${HE_DATA}', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if i >= ${N_PROBLEMS}:
            break
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        pid    = obj.get('problem_id', i)
        tid    = obj.get('task_id', f'HumanEval/{i}')
        ep     = obj.get('entry_point', '')
        prompt = obj.get('prompt', '').replace('\t', '    ')
        # Newlines replaced with sentinel; restored per-problem below
        prompt_enc = prompt.replace('\n', '<<NL>>')
        print(f'{pid}\t{tid}\t{ep}\t{prompt_enc}')
" 2>/dev/null)

# ── Run evaluation ───────────────────────────────────────────
START_S=$(date +%s)
N_VARIANTS=0
for V in $VARIANTS; do N_VARIANTS=$((N_VARIANTS + 1)); done
VARIANT_NUM=0

for VARIANT in $VARIANTS; do
    VARIANT_NUM=$((VARIANT_NUM + 1))
    MODEL_PATH="${DEVICE_DIR}/${MODEL_PREFIX}-${VARIANT}.gguf"
    OUT_FILE="${RESULTS_DIR}/results_${VARIANT}.jsonl"

    # Resume: skip if already complete
    if [ "$RESUME" -eq 1 ] && [ -f "$OUT_FILE" ]; then
        DONE_LINES=$(wc -l < "$OUT_FILE" | tr -d ' ')
        if [ "$DONE_LINES" -ge "$N_PROBLEMS" ]; then
            log "SKIP ${VARIANT} -- already complete (${DONE_LINES} rows)"
            continue
        fi
        log "RESUME ${VARIANT} -- found ${DONE_LINES} existing rows"
        RESUME_FROM=$DONE_LINES
    else
        RESUME_FROM=0
        > "$OUT_FILE"
    fi

    log ""
    log "=== ${VARIANT}  [${VARIANT_NUM}/${N_VARIANTS}] ==="

    P_NUM=0

    while IFS="	" read -r PID TASK_ID ENTRY_POINT PROMPT_ENC; do
        P_NUM=$((P_NUM + 1))

        # Resume: skip already-processed problems
        if [ "$P_NUM" -le "$RESUME_FROM" ]; then
            continue
        fi

        # Restore newlines
        PROMPT=$(printf '%s' "$PROMPT_ENC" | sed 's/<<NL>>/\
/g')

        ELAPSED=$(( $(date +%s) - START_S ))
        if [ "$P_NUM" -gt 1 ]; then
            ETA=$(( ELAPSED * N_PROBLEMS / (P_NUM - 1) - ELAPSED )) 2>/dev/null || ETA=0
        else
            ETA=0
        fi

        # Build completion prompt: instruction + function stub
        FULL_PROMPT="Complete the following Python function:

${PROMPT}"

        if [ "$DRY_RUN" -eq 1 ]; then
            log "  [${P_NUM}/${N_PROBLEMS} eta=${ETA}s]  ${VARIANT}  ${TASK_ID}  DRY RUN"
            printf '{"variant":"%s","problem_id":%s,"task_id":"%s","entry_point":"%s","prompt":"DRY","generated_code":"pass","syntax_ok":false,"test_passed":false,"decode_tps":0}\n' \
                "$VARIANT" "$PID" "$TASK_ID" "$ENTRY_POINT" >> "$OUT_FILE"
            continue
        fi

        # Write prompt to temp file on device
        PROMPT_DEVICE="${DEVICE_DIR}/he_prompt_$$.txt"
        printf '%s' "$FULL_PROMPT" | adb shell "cat > ${PROMPT_DEVICE}" 2>/dev/null || true

        # Run inference
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

        adb shell "rm -f ${PROMPT_DEVICE}" 2>/dev/null || true

        # Extract decode TPS
        DECODE_TPS=$(printf '%s\n' "$RAW" \
            | grep -E "common_perf_print:.*eval time" \
            | grep -v "prompt" \
            | grep -oE "[0-9]+\.[0-9]+ tokens per second" \
            | awk '{print $1}' | head -1 || true)
        [ -z "$DECODE_TPS" ] && DECODE_TPS="0"

        # Strip llama.cpp diagnostic lines to isolate generated code
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

        # Combine prompt + generated to give the full function context to evaluator
        # The prompt already contains the function signature; generated is the body.
        FULL_CODE="${PROMPT}${GENERATED}"

        # Quick local syntax check (Python available on Mac)
        SYNTAX_OK="false"
        SYNTAX_ERR=""
        if python3 -c "
import ast, sys
try:
    ast.parse(sys.stdin.read())
    print('ok')
except SyntaxError as e:
    print(f'err:{e}')
" <<< "$FULL_CODE" 2>/dev/null | grep -q "^ok"; then
            SYNTAX_OK="true"
        fi

        # JSON-encode the generated code and prompt safely via Python
        GEN_JSON=$(printf '%s' "$GENERATED"  | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '""')
        PRO_JSON=$(printf '%s' "$FULL_PROMPT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null || printf '""')

        printf '{"variant":"%s","problem_id":%s,"task_id":"%s","entry_point":"%s","prompt":%s,"generated_code":%s,"syntax_ok":%s,"test_passed":false,"decode_tps":%s}\n' \
            "$VARIANT" "$PID" "$TASK_ID" "$ENTRY_POINT" "$PRO_JSON" "$GEN_JSON" "$SYNTAX_OK" "$DECODE_TPS" \
            >> "$OUT_FILE"

        log "  [${P_NUM}/${N_PROBLEMS} eta=${ETA}s]  ${VARIANT}  ${TASK_ID}  syntax=${SYNTAX_OK}  tps=${DECODE_TPS}"

    done <<PEOF
${PROBLEMS}
PEOF

    log "  VARIANT ${VARIANT}  DONE  --  Saved: ${OUT_FILE}"
done

# ── Optional local evaluation ─────────────────────────────────
if [ "$RUN_EVAL" -eq 1 ] && [ "$DRY_RUN" -eq 0 ]; then
    log ""
    log "Running local syntax + execution evaluation ..."
    if python3 scripts/eval/eval_humaneval.py "$RESULTS_DIR"; then
        log "OK  Evaluation complete"
    else
        log "WARNING: eval_humaneval.py exited non-zero -- check output above"
    fi
fi

# ── Summary table ─────────────────────────────────────────────
log ""
hr
log "HUMANEVAL CAPTURE SUMMARY  --  Pixel 6a  --  Llama-3.2-3B  --  50 problems"
hr

python3 - "$RESULTS_DIR" $VARIANTS << 'PYEOF'
import json
import glob
import sys
from pathlib import Path

results_dir = sys.argv[1]
requested   = sys.argv[2:] or ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

print(f"\n  {'Variant':<12}  {'Problems':>8}  {'Syntax OK':>9}  {'Test Pass':>10}  {'Avg TPS':>8}")
print("  " + "-" * 55)

for v in requested:
    paths = glob.glob(f"{results_dir}/results_{v}.jsonl")
    if not paths:
        continue
    records = [json.loads(l) for l in open(paths[0]) if l.strip()]
    if not records:
        continue
    n        = len(records)
    syn_ok   = sum(1 for r in records if r.get("syntax_ok"))
    tst_pass = sum(1 for r in records if r.get("test_passed"))
    tps_vals = [float(r["decode_tps"]) for r in records if float(r.get("decode_tps", 0)) > 0]
    avg_tps  = sum(tps_vals) / len(tps_vals) if tps_vals else 0.0
    print(f"  {v:<12}  {n:>8}  {syn_ok:>9}  {tst_pass:>10}  {avg_tps:>7.2f}")

print()
print("  NOTE: test_passed=false until eval_humaneval.py is run locally.")
print(f"  Run: python3 scripts/eval/eval_humaneval.py {results_dir}")
print()
PYEOF

ELAPSED=$(( $(date +%s) - START_S ))
log ""
hr
log "DONE  |  runtime: $(( ELAPSED/60 ))m $(( ELAPSED%60 ))s  |  results: ${RESULTS_DIR}"
hr
log "To score results locally:"
log "  python3 scripts/eval/eval_humaneval.py ${RESULTS_DIR}"
hr
