#!/bin/bash
# Power measurement script - Pixel 6a
# Runs sustained inference per variant, measures battery drain
# Usage: bash scripts/pixel_power_measure.sh

set -e
RESULTS_DIR="results/pixel_power_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$RESULTS_DIR"
LOG="$RESULTS_DIR/power_run.log"
JSON="$RESULTS_DIR/power_results.jsonl"

VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
MODELDIR="/data/local/tmp"
PROMPT="The future of artificial intelligence in mobile devices is characterized by increasingly sophisticated language models that can run efficiently on constrained hardware. Explain the key challenges."
DURATION_S=180  # 3 min per variant for good signal

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }

log "========================================"
log "Pixel 6a Power Measurement"
log "Variants: ${VARIANTS[*]}"
log "Duration per variant: ${DURATION_S}s"
log "Results: $RESULTS_DIR"
log "========================================"

# Drain idle current for baseline
log "Measuring idle baseline (30s)..."
adb shell "cat /sys/class/power_supply/battery/current_now" > /tmp/idle_before.txt 2>/dev/null
sleep 5
IDLE_CURRENT=$(adb shell "cat /sys/class/power_supply/battery/current_now" 2>/dev/null | tr -d '\r\n')
log "Idle current: ${IDLE_CURRENT} uA"

for VARIANT in "${VARIANTS[@]}"; do
    MODEL="${MODELDIR}/Llama-3.2-3B-Instruct-${VARIANT}.gguf"
    log ""
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Variant: $VARIANT"

    # Check model exists on device
    MODEL_EXISTS=$(adb shell "ls ${MODEL} 2>/dev/null" | tr -d '\r\n')
    if [ -z "$MODEL_EXISTS" ]; then
        log "⚠ SKIP: ${MODEL} not found on device"
        continue
    fi

    # Read battery before
    BATT_BEFORE=$(adb shell "cat /sys/class/power_supply/battery/capacity" | tr -d '\r\n')
    CURRENT_BEFORE=$(adb shell "cat /sys/class/power_supply/battery/current_now" | tr -d '\r\n')
    CHARGE_BEFORE=$(adb shell "cat /sys/class/power_supply/battery/charge_now 2>/dev/null || echo 0" | tr -d '\r\n')
    TEMP_BEFORE=$(adb shell "cat /sys/class/power_supply/battery/temp 2>/dev/null || echo 0" | tr -d '\r\n')
    TIME_BEFORE=$(date +%s)

    log "  Battery before: ${BATT_BEFORE}% | current: ${CURRENT_BEFORE} uA | charge: ${CHARGE_BEFORE} uAh"

    # Run inference for DURATION_S seconds and count tokens
    TOKEN_COUNT=0
    START_TIME=$(date +%s)
    TEMP_OUT="/tmp/power_inference_${VARIANT}.txt"

    # Run llama-cli in background on device, capture output
    adb shell "timeout ${DURATION_S} /data/local/tmp/llama-cli \
        -m ${MODEL} \
        -c 512 \
        -n 256 \
        --repeat 999 \
        -p '${PROMPT}' \
        -t 4 2>&1" > "$TEMP_OUT" &
    INFER_PID=$!

    # While inference runs, sample power every 15s
    SAMPLES=()
    SAMPLE_COUNT=0
    while kill -0 $INFER_PID 2>/dev/null; do
        sleep 15
        CURR=$(adb shell "cat /sys/class/power_supply/battery/current_now" 2>/dev/null | tr -d '\r\n')
        SAMPLES+=("$CURR")
        SAMPLE_COUNT=$((SAMPLE_COUNT + 1))
        log "  [sample ${SAMPLE_COUNT}] current: ${CURR} uA"
    done
    wait $INFER_PID 2>/dev/null || true

    # Read battery after
    BATT_AFTER=$(adb shell "cat /sys/class/power_supply/battery/capacity" | tr -d '\r\n')
    CURRENT_AFTER=$(adb shell "cat /sys/class/power_supply/battery/current_now" | tr -d '\r\n')
    CHARGE_AFTER=$(adb shell "cat /sys/class/power_supply/battery/charge_now 2>/dev/null || echo 0" | tr -d '\r\n')
    TEMP_AFTER=$(adb shell "cat /sys/class/power_supply/battery/temp 2>/dev/null || echo 0" | tr -d '\r\n')
    TIME_AFTER=$(date +%s)
    ELAPSED=$((TIME_AFTER - TIME_BEFORE))

    # Extract TPS from inference output
    TPS=$(grep -oE "generation: [0-9]+\.[0-9]+ t/s" "$TEMP_OUT" 2>/dev/null | tail -1 | grep -oE "[0-9]+\.[0-9]+" || \
          grep -oE "[0-9]+\.[0-9]+ t/s" "$TEMP_OUT" 2>/dev/null | tail -1 | grep -oE "^[0-9]+\.[0-9]+" || echo "0")

    # Compute avg current during inference
    AVG_CURRENT=0
    if [ ${#SAMPLES[@]} -gt 0 ]; then
        SUM=0
        for S in "${SAMPLES[@]}"; do SUM=$((SUM + S)); done
        AVG_CURRENT=$((SUM / ${#SAMPLES[@]}))
    fi

    # Voltage ~3.7V nominal for Pixel 6a battery
    VOLTAGE_V=3700  # mV
    # Power = V * I (in mW): AVG_CURRENT is in uA → convert to mA → mW
    AVG_POWER_MW=$(( (AVG_CURRENT * VOLTAGE_V) / 1000000 ))
    NET_POWER_MW=$(( ((AVG_CURRENT - IDLE_CURRENT) * VOLTAGE_V) / 1000000 ))

    # Tokens generated ≈ TPS * ELAPSED
    TOKENS_GEN=$(echo "$TPS * $ELAPSED" | bc 2>/dev/null || echo "0")
    # Tokens per joule = tokens / (power_W * time_s) = tokens / energy_J
    ENERGY_J=$(echo "scale=2; $AVG_POWER_MW * $ELAPSED / 1000" | bc 2>/dev/null || echo "1")

    log "  Battery after:  ${BATT_AFTER}% | current: ${CURRENT_AFTER} uA | charge: ${CHARGE_AFTER} uAh"
    log "  Elapsed: ${ELAPSED}s | TPS: ${TPS} | Avg current: ${AVG_CURRENT} uA | Est power: ${AVG_POWER_MW} mW"
    log "  Net inference power (minus idle): ${NET_POWER_MW} mW"

    # Save JSON record
    echo "{
  \"variant\": \"$VARIANT\",
  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",
  \"elapsed_s\": $ELAPSED,
  \"decode_tps\": $TPS,
  \"battery_before_pct\": $BATT_BEFORE,
  \"battery_after_pct\": $BATT_AFTER,
  \"charge_before_uah\": $CHARGE_BEFORE,
  \"charge_after_uah\": $CHARGE_AFTER,
  \"idle_current_ua\": $IDLE_CURRENT,
  \"avg_inference_current_ua\": $AVG_CURRENT,
  \"avg_power_mw\": $AVG_POWER_MW,
  \"net_inference_power_mw\": $NET_POWER_MW,
  \"temp_before_decidegC\": $TEMP_BEFORE,
  \"temp_after_decidegC\": $TEMP_AFTER,
  \"samples_count\": ${#SAMPLES[@]}
}" >> "$JSON"

    rm -f "$TEMP_OUT"
    log "  ✅ Saved to $JSON"
    
    # Brief cool-down between variants
    log "  Cooling down 60s..."
    sleep 60
done

log ""
log "========================================"
log "✅ Power measurement complete!"
log "Results: $JSON"
log "========================================"

# Print summary
echo ""
echo "=== POWER SUMMARY ==="
python3 -c "
import json, sys
results = []
with open('$JSON') as f:
    for line in f:
        line = line.strip()
        if line and line != '{' and line != '}':
            pass
try:
    import json
    data = []
    with open('$JSON') as f:
        content = f.read()
    # Parse concatenated JSON objects
    import re
    objects = re.findall(r'\{[^{}]+\}', content, re.DOTALL)
    for obj in objects:
        try: data.append(json.loads(obj))
        except: pass
    print(f'Variant      TPS    Power(mW)  Net Power  Temp Rise')
    print('-' * 55)
    for r in data:
        tps = r.get('decode_tps', 0)
        pwr = r.get('avg_power_mw', 0)
        net = r.get('net_inference_power_mw', 0)
        tb = r.get('temp_before_decidegC', 0) / 10
        ta = r.get('temp_after_decidegC', 0) / 10
        print(f\"{r['variant']:<12} {tps:<6} {pwr:<10} {net:<10} {ta-tb:+.1f}°C\")
except Exception as e:
    print(f'Parse error: {e}')
" 2>/dev/null || cat "$JSON"
