# DSC 291 EAI — Demo Preparation & Execution Guide

## 📱 Device Setup (Pre-Demo)

### Install Latest APK
```bash
# Build fresh APK if needed
cd /Users/krisdcosta/291_EAI/android
./gradlew clean assembleDebug

# Install on connected Pixel 6a
adb install -r app/build/outputs/apk/debug/app-debug.apk

# Verify installation
adb shell pm list packages | grep eai
# Output should show: com.eai.edgellmbench
```

### Verify Models Pre-loaded
```bash
# Check that all models exist on device
adb shell ls -lh /data/local/tmp/*.gguf | wc -l
# Should show: 6 files (5 quantized + F16)

# Optional: Pre-load a model to warm up engine
# (App will do this automatically on first use)
adb shell "timeout 30 /data/local/tmp/llama-cli -m /data/local/tmp/Llama-3.2-3B-Instruct-Q4_K_M.gguf -p 'Hello' -n 32" | tail -3
```

### Battery Check
- Device should be at **>75% battery** for consistent performance demo
- Close background apps (Chrome, Photos, Gmail, etc.)
- Set **WiFi ADB** to minimize demo interruptions

---

## 🎤 Demo Script (7-10 minutes)

### 1. **Introduction & Motivation** (1 min)
**Talking points:**
- "This project was built for DSC 291 — Edge AI course"
- "Research question: Can we run a capable LLM locally on Android without cloud?"
- "Target device: Pixel 6a (ARM64 CPU, 6GB LPDDR5, no GPU)"
- "Model: Llama 3.2 3B Instruct — small enough for edge, capable enough for real tasks"

**What to show:**
- Open app to Chat tab (model loading)
- Brief mention of 6 variants (Q2_K through F16)

---

### 2. **Chat Feature Demo** (1.5 min)
**Live interaction:**
```
Prompt: "Explain quantum entanglement in 2 sentences"
Wait for streaming response...
```

**Talking points:**
- "See the streaming output — tokens appear in real-time"
- "Model is running locally, not cloud"
- "Temperature setting (0.7 default) controls creativity"
- "Context window (512 tokens) lets the model understand longer conversations"

**If time allows:**
- Send a follow-up: "What are practical applications?"
- Show context being tracked: "The model remembers previous exchanges"

---

### 3. **Models & Performance Metrics** (1.5 min)
**Navigate to Models tab:**

**Show on screen:**
- Model file sizes (1.3 GB Q2_K → 6.4 GB F16)
- Explain quantization: "Q4_K_M reduces F16 from 6.4GB to 2.0GB (68% smaller)"

**Reference Table 1 results (from report):**
```
| Variant | Size  | Decode TPS | BoolQ % | PPL   |
|---------|-------|------------|---------|-------|
| Q4_K_M  | 2.0GB | 5.32±0.52  | 72%     | 11.36 |
| F16     | 6.4GB | 0.15±0.00  | 68%     | ---   |
```

**Talking points:**
- "Q4_K_M is 35× faster than F16 (5.32 vs 0.15 tok/s) despite only 2% accuracy loss"
- "This is the quantization vs performance tradeoff we're exploring"
- "Perplexity is interesting — similar for Q4/Q6/Q8 but very different BoolQ accuracy"

---

### 4. **Benchmark Feature** (2 min)
**Navigate to Benchmark → Run tab:**

**Show default settings:**
- Context length: 512 tokens
- Output length: 128 tokens
- Warmup runs: 1
- Benchmark trials: 5

**Run a live benchmark:**
```
Click "Run Benchmark" → watch progress in real-time
(Takes ~2-3 minutes for 5 trials with warmup)
```

**During run, explain:**
- "Each trial sends a prompt, measures time-to-first-token and decode throughput"
- "Warmup run is discarded to avoid JIT effects"
- "Real-time stats update as trials complete"

**After completion:**
- "Summary shows: mean TPS ± std, min/max range"
- "Results are automatically saved as JSONL file"

---

### 5. **History Tab** (1 min)
**Navigate to Benchmark → History tab:**

**Show:**
- List of previous benchmark runs (sorted by newest first)
- Each row shows: variant, date, config (ctx/tokens/trials), TPS ± std [min-max]
- Tap a row to expand and see full details

**Talking points:**
- "Benchmark history persists across app restarts"
- "You can compare multiple model configurations side-by-side"
- "This helps identify which variant meets your latency requirements"

---

### 6. **Settings & Customization** (1.5 min)
**Navigate to Settings tab:**

**Inference section:**
- Show context length dropdown: 256, 512, 1024, 2048 tokens
- Show thread count: 1, 2, 4, 8 (maps to Pixel 6a cores)
- Mention: "Changing these values requires clicking 'Apply' to reconfigure the live engine"
- Click "Apply" → show loading spinner and success message

**Appearance section:**
- Show "Follow system theme" toggle (currently ON)
- Turn OFF → reveal "Dark mode" toggle
- Toggle dark mode → show theme change in real-time
- Mention: "Settings persist across app restart"

**Talking points:**
- "Full control over inference parameters"
- "Every setting persists via DataStore — no data loss on restart"

---

### 7. **Key Research Findings** (1 min)
**Reference report findings:**

**Q1: Which quantization variant is best?**
- "Depends on your constraint (latency, size, accuracy)"
- "Q4_K_M is the sweet spot: 2.0GB, 5.3 tok/s, 72% BoolQ accuracy"

**Q2: Does perplexity predict downstream task accuracy?**
- "No! Q4_K_M and Q6_K have nearly identical PPL (11.36 vs 11.22)"
- "But Q4_K_M achieves 72% BoolQ accuracy while Q6_K only reaches 65%"
- "This shows task-specific evaluation is essential"

**Q3: How does it compare to GPU?**
- "We created a GPU baseline script for Colab (included in repo)"
- "F16 on GPU runs ~50-100× faster than F16 on Pixel 6a"
- "But Pixel 6a fits in a pocket — GPU doesn't!"

**Upcoming work (post-demo):**
- "iMatrix calibration to improve quantization quality"
- "Battery measurement to assess real-world power efficiency"

---

## ✅ Testing Checklist (Before Demo)

**Run these on device to ensure everything works:**

### Chat Tab
- [ ] Send message → get response (streaming visible)
- [ ] Verify output is coherent (not gibberish)
- [ ] Try long prompt → verify context handling
- [ ] Load different model → Chat uses new model

### Models Tab
- [ ] All 6 models visible (Q2_K, Q3_K_M, Q4_K_M, Q6_K, Q8_0, F16)
- [ ] File sizes shown (1.3GB, 1.6GB, 2.0GB, 2.7GB, 3.4GB, 6.4GB)
- [ ] Select different model → "Load" button enabled
- [ ] Click Load → model switches (verify in Chat)

### Benchmark Tab (Run)
- [ ] Default settings load correctly
- [ ] Click "Run" → progress shows (phase, current, total)
- [ ] Trial results appear in list as they complete
- [ ] After completion → summary stats visible
- [ ] JSONL file exists: `adb shell ls /data/local/tmp/results/run-*.jsonl`

### Benchmark Tab (History)
- [ ] First run appears in History immediately
- [ ] Run card shows: variant, date, config, TPS ± std, min/max
- [ ] Close app → reopen → history persists
- [ ] Second benchmark run → both appear in history (newest first)

### Settings Tab (Inference)
- [ ] Change context length → setting persists
- [ ] Change thread count → setting persists
- [ ] Close app → reopen → values unchanged
- [ ] Click "Apply" → confirmation message

### Settings Tab (Appearance)
- [ ] "Follow system theme" toggle works
- [ ] Turn OFF → "Dark mode" toggle appears
- [ ] Drag mode toggle → theme changes
- [ ] Close app → reopen → theme setting persists

**If any test FAILS:**
- Note the specific failure
- Check logcat: `adb logcat -s "EAI" | grep -i "error|exception|crash"`
- Document with screenshot
- Do NOT proceed to demo without fixing

---

## 🎥 Demo Day Checklist

**30 minutes before:**
- [ ] Device at >75% battery
- [ ] WiFi connected (for ADB, logs don't upload)
- [ ] All background apps closed
- [ ] Run through "Testing Checklist" above — all green
- [ ] Have report PDF open on presenter's laptop (backup visuals)
- [ ] Charge device while presenting (bring USB-C cable)

**During demo:**
- [ ] Speak clearly about research motivation
- [ ] Point to actual data (Table 1) not just app numbers
- [ ] Let inference run naturally (don't rush Chat responses)
- [ ] If benchmark completes early, explain results while showing History tab
- [ ] Keep script 7-10 minutes (leave time for Q&A)

**Backup plans:**
- If Chat is slow: "The Pixel 6a is CPU-only; note how Q4_K_M enables real-time conversation despite model size"
- If benchmark takes too long: "Show the History tab instead with previous runs, explain the data pipeline"
- If dark mode doesn't toggle: "Settings are comprehensive — datastore integration handles persistence; we can skip the theme demo"
- If model won't load: "Explain that model loading is a one-time cold start; all models pre-cached on this device"

---

## 📊 Demo Data Reference

**Table 1 (from report):**
- Q2_K: 1.3GB, 5.66±0.72 tok/s, 69% BoolQ, PPL 11.71
- Q3_K_M: 1.6GB, 4.91±0.40 tok/s, 66% BoolQ, PPL 10.15
- **Q4_K_M: 2.0GB, 5.32±0.52 tok/s, 72% BoolQ, PPL 11.36** ← Best choice
- Q6_K: 2.7GB, 3.98±0.32 tok/s, 65% BoolQ, PPL 11.22
- Q8_0: 3.4GB, 4.95±0.59 tok/s, 68% BoolQ, PPL TBD (in-device measurement pending)
- F16: 6.4GB, 0.15±0.00 tok/s, 68% BoolQ, PPL ---

**Key statistics to cite:**
- Q4_K_M vs F16 speedup: 5.32 / 0.15 = **35.5×**
- Q4_K_M accuracy vs BoolQ: **72%** (second best after Q2_K at 69%)
- Model size reduction: F16 → Q4_K_M = 6.4GB → 2.0GB (**68% smaller**)
- Benchmark trials: **661+ measurements** across 5 quantization variants × 3 context lengths

---

## 🎯 Success Criteria

**Demo is successful if:**
1. ✅ App launches without crash
2. ✅ All 4 tabs are functional (Chat, Models, Benchmark, Settings)
3. ✅ At least one complete Chat message + response shown
4. ✅ Benchmark runs and produces results
5. ✅ Research question (PPL vs accuracy tradeoff) is clearly explained
6. ✅ Audience understands why Q4_K_M is the practical sweet spot

**Bonus points:**
- ✅ Dark mode toggle works smoothly
- ✅ History tab shows multiple runs
- ✅ Report PDF cited for statistical backing
- ✅ GPU baseline script mentioned as future work

---

**Last updated:** 2026-03-11 08:45 UTC
