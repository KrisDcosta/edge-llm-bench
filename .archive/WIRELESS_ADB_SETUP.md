# Wireless ADB Setup Instructions

## Current Status (as of 2026-03-20 19:55 UTC)

- ✅ Qwen 2.5 TPS benchmark: **Running** (started at 19:52 UTC)
  - Location: `results/qwen_tps_20260320_195255/`
  - Progress: Q2_K started
  - Completion ETA: ~6-8 hours (7 variants × 4 contexts × 5 trials)
  - Monitor: `tail -f results/qwen_tps_sweep_corrected.log`

- ⚠️ Wireless ADB pairing: **Awaiting user input**
  - Device: Pixel 6a
  - Device IP:Port: **100.96.96.89:33873**
  - Pairing Code: **937356**
  - Status: Previous pairing attempt was non-interactive; needs to be redone with proper input

- 📦 App Build: **Ready** (`android/app/build/outputs/apk/debug/app-debug.apk`)
  - Includes: Q4_K_S/Q5_K_M variants, corrected device name, removed "Coming Soon"
  - Waiting for: Wireless ADB connection

- 📊 Power Measurement: **Pending** wireless ADB connection
  - Will run after wireless ADB is confirmed stable
  - Device MUST be unplugged from USB

---

## Step-by-Step Wireless ADB Pairing (do this now)

### 1. Open Terminal and run pairing command
```bash
adb pair 100.96.96.89:33873
```

### 2. When prompted, enter the pairing code
```
Enter pairing code: [paste: 937356]
```

### 3. Expected output (success)
```
Successfully paired to 100.96.96.89:33873 [unique identifier]
```

### 4. Connect via wireless TCP/IP
```bash
adb connect 100.96.96.89:5555
```

### 5. Verify connection
```bash
adb devices
```
Expected output:
```
List of devices attached
100.96.96.89:5555    device
```

---

## After Wireless ADB is Connected

### Deploy Updated App
```bash
cd /Users/krisdcosta/291_EAI
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

### Start Power Measurement (UNPLUG USB FIRST!)
```bash
# Unplug USB cable from device, then:
python3 scripts/benchmark_runner.py \
    --wifi-adb \
    --output-length 256 \
    --trials 10 \
    --variants Q2_K Q3_K_M Q4_K_M Q6_K Q8_0
```

---

## Troubleshooting

### If pairing fails with "protocol fault"
- Verify IP:Port is correct: `100.96.96.89:33873` (NOT the local network IP)
- Make sure phone is on same WiFi network
- Toggle WiFi debugging on phone: Settings → Developer Options → Wireless debugging (off/on)
- Try pairing again

### If device shows "unauthorized"
```bash
# Device may still be waiting for USB approval
adb devices
# Look for: 100.96.96.89:5555    unauthorized
# On phone: tap "Allow" in USB Debugging prompt (if shown)
# Or restart adb: adb kill-server && adb devices
```

### If connection drops
- Phone may have gone to sleep or switched networks
- Reconnect: `adb connect 100.96.96.89:5555`
- Or restart WiFi debugging: Phone Settings → Developer Options → Wireless debugging (toggle off/on)

---

## Files Affected by Recent Updates

### App Model Repository (added 2 variants)
`android/app/src/main/java/.../data/repository/ModelRepository.kt`
- Added: Q4_K_S (1.8GB, "Best efficiency — Pareto optimal")
- Added: Q5_K_M (2.3GB, "High quality, moderate size")

### App Settings (corrected device name, removed placeholder section)
`android/app/src/main/java/.../ui/settings/SettingsScreen.kt`
- Device: "Pixel 6a · Google Tensor (Whitechapel) · 6 GB LPDDR5"
- Version: "1.1"
- Removed: "Coming Soon" section (RAG, Voice, etc.)

### Report Generated
`report/course_project_report.tex` (12 pages, NeurIPS format)
- Contains all M4/Pixel benchmarks, analysis, and academic structure
- Ready for review/submission

---

## Next Steps (Once Wireless ADB Connected)

1. ✅ Pair via wireless ADB (THIS STEP - do now)
2. ✅ Connect via TCP/IP
3. Deploy updated app with `adb install`
4. Unplug USB from device
5. Start power measurement (256-token output)
6. Monitor Qwen benchmark progress
7. Review final report and submit

