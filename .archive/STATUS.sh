#!/bin/bash
# Quick status check for all ongoing tasks

echo "=== DSC 291 EAI — PARALLEL TASKS STATUS ==="
echo "Timestamp: $(date)"
echo ""

# Qwen TPS Benchmark
echo "📊 Qwen 2.5 1.5B TPS Benchmark"
QWEN_RUNNING=$(ps aux | grep -c "qwen_tps_sweep" || echo "0")
if [ "$QWEN_RUNNING" -gt 1 ]; then
    QWEN_LOG="results/qwen_tps_sweep_corrected.log"
    if [ -f "$QWEN_LOG" ]; then
        LINES=$(wc -l < "$QWEN_LOG")
        COMPLETED=$(grep -c "t/s$" "$QWEN_LOG" 2>/dev/null || echo "0")
        PERCENT=$((COMPLETED * 100 / 140))
        LAST_LINE=$(tail -1 "$QWEN_LOG")
        echo "  Status: ✅ Running"
        echo "  Progress: $COMPLETED / 140 benchmarks ($PERCENT% complete)"
        echo "  Latest: $LAST_LINE"
    else
        echo "  Status: ✅ Running (setup phase)"
    fi
else
    echo "  Status: ⏸️  Not running"
fi
echo ""

# Wireless ADB
echo "📡 Wireless ADB Connection"
ADB_STATUS=$(adb devices 2>&1 | grep -E "[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+" | grep device)
if [ -n "$ADB_STATUS" ]; then
    echo "  Status: ✅ Connected"
    echo "  Device: $ADB_STATUS"
else
    echo "  Status: ⚠️  Not connected"
    echo "  Action: Run 'adb pair 100.96.96.89:33873' when ready"
    echo "          Pairing code: 937356"
fi
echo ""

# Power Measurement
echo "🔋 Power Measurement"
POWER_RUNNING=$(ps aux | grep -c "benchmark_runner.*wifi-adb" || echo "0")
if [ "$POWER_RUNNING" -gt 1 ]; then
    echo "  Status: ✅ Running"
    POWER_LOG=$(ls -t results/power_*.jsonl 2>/dev/null | head -1)
    if [ -n "$POWER_LOG" ]; then
        echo "  Log: $POWER_LOG"
    fi
else
    echo "  Status: ⏸️  Awaiting wireless ADB"
    echo "  Requirement: Device must be unplugged from USB"
fi
echo ""

# App Build
echo "📦 App Build"
APK=$(ls -lh android/app/build/outputs/apk/debug/app-debug.apk 2>/dev/null)
if [ -n "$APK" ]; then
    SIZE=$(echo "$APK" | awk '{print $5}')
    DATE=$(echo "$APK" | awk '{print $6, $7, $8}')
    echo "  Status: ✅ Ready"
    echo "  File: app-debug.apk ($SIZE)"
    echo "  Built: $DATE"
else
    echo "  Status: ⚠️  Not built"
fi
echo ""

# Report
echo "📄 NeurIPS Course Report"
REPORT=$(ls -lh report/course_project_report.tex 2>/dev/null)
if [ -n "$REPORT" ]; then
    SIZE=$(echo "$REPORT" | awk '{print $5}')
    LINES=$(wc -l < report/course_project_report.tex)
    echo "  Status: ✅ Generated"
    echo "  File: course_project_report.tex ($LINES lines, $SIZE)"
else
    echo "  Status: ⚠️  Not found"
fi
echo ""

echo "=== SETUP INSTRUCTIONS ==="
echo "1. Complete wireless ADB pairing (see WIRELESS_ADB_SETUP.md)"
echo "2. Deploy app: adb install -r android/app/build/outputs/apk/debug/app-debug.apk"
echo "3. Unplug USB from device"
echo "4. Power measurement will start automatically after wireless ADB connects"
echo "5. Monitor Qwen progress: tail -f results/qwen_tps_sweep_corrected.log"
echo ""
