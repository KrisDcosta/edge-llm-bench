# Demo Recording Plan — DSC 291 Edge AI on Mobile

## Overview
**Two videos:**
1. **Video 1** (2 min): Chat speed/accuracy comparison — same prompt across 5 quantization variants
2. **Video 2** (3 min): Settings, Benchmark, and History features

---

## Video 1: Quantization Variants Speed Comparison

### Prompt Selection
Use a **consistent, substantive prompt** that demonstrates reasoning/understanding (not just trivia):

**Selected Prompt:**
```
"Explain in 2-3 sentences: Why would reducing the bit-width of neural 
network weights affect both inference speed and accuracy? What's the 
tradeoff?"
```

Expected output: ~60-100 tokens (good length to show speed difference while staying < 2 min for fastest variant)

### Recording Sequence (5 Recordings)

Each recording follows the same procedure:

#### Step-by-Step for Each Recording:

1. **Device Prep** (before each recording)
   ```bash
   adb shell "sync && echo 3 > /proc/sys/vm/drop_caches"
   adb shell "pkill -f llama"
   adb shell "am start -n com.eai.edgellmbench/.MainActivity"
   sleep 3
   ```

2. **In-App: Select Model**
   - Tap "Models" tab
   - Tap the desired variant (Q2_K, Q4_K_M, Q6_K, Q8_0, or F16)
   - Wait for "Model loaded" confirmation (~3-5 seconds)
   - Tap "Chat" tab

3. **Record**: (Start recording with screen capture/ADB screencap)
   - Copy/paste the prompt into the Chat input box
   - Hit "Send"
   - **Let it run until response completes**
   - Record the total time from send to final token
   - Take screenshot of final response

4. **Note the metrics:**
   - Time to first token (TTFT) — how long until first word appears
   - Time to complete response (Total latency)
   - Response quality (grammatical correctness, relevance)

### Recording Details

| Variant | Expected TTFT | Expected Total Time | Quality |
|---------|---------------|--------------------|---------|
| **Q2_K** | ~3.8s | ~12-14s | Good (69% BoolQ) |
| **Q4_K_M** | ~4.0s | ~13-15s | Best (72% BoolQ) |
| **Q6_K** | ~5.7s | ~16-19s | Lower (65% BoolQ) |
| **Q8_0** | ~3.95s | ~13-15s | Good (68% BoolQ) |
| **F16** | ~14.5s | ~120-180s | Best (68% BoolQ) - VERY SLOW |

**Note on F16:** Unquantized model will be VERY slow (~2-3 minutes for output). You may need to reduce the output expected tokens or just record the first 30 seconds to keep video watchable.

### Video 1 Editing Instructions

**Combine into single comparison video:**

```
Timeline:
0:00 - Introduction (overlay text): "Same prompt, different quantization"
0:05 - Q2_K recording (sped up to 1.5x) — "Q2_K: Fast (5.66 tok/s)"
0:25 - Q4_K_M recording (1x speed) — "Q4_K_M: Balanced (5.32 tok/s)"
0:45 - Q6_K recording (1.2x speed) — "Q6_K: Slow (3.98 tok/s)"
1:05 - Q8_0 recording (1x speed) — "Q8_0: Fast (4.95 tok/s)"
1:25 - F16 recording (2.0x speed or skip) — "F16: Unquantized (0.15 tok/s)"
1:50 - Summary slide with accuracy/speed table
2:00 - End
```

**Video Specs:**
- Resolution: 1080p (from device screen capture)
- Codec: H.264 or similar
- Frame rate: 30fps
- Audio: Optional (can use voiceover explaining results)
- Subtitles: Show prompt at top, show metrics as each variant completes

---

## Video 2: Settings, Benchmark, History Features (3 min)

### Script

1. **Intro** (0:00-0:10)
   - Show app main screen
   - "App has 4 tabs: Chat, Models, Benchmark, Settings"

2. **Settings Tab** (0:10-0:40)
   - Tap Settings
   - Show available settings:
     - Context Length (toggle between 256 and 1024)
     - Warmup Runs (default: 1)
     - Benchmark Runs (default: 3)
     - Output Tokens (default: 128)
   - Change context length, demonstrate toggle persists
   - Show explanation: "Settings are persisted across app restarts"

3. **Benchmark Tab - Run Section** (0:40-1:30)
   - Return to Benchmark tab
   - Show "Run" tab is active
   - Click "Run Benchmark" button
   - Show progress bar updating (0/3 → 1/3 → 2/3 → 3/3)
   - Wait for completion
   - Show Benchmark Summary Card:
     - Decode TPS: mean ± std
     - TTFT: mean ± std
   - Show Trial Results table with individual results

4. **History Tab** (1:30-2:20)
   - Tap "History" tab (should show "History (1)" if one run completed)
   - Show the benchmark run card:
     - Model variant, context length, timestamp
     - Stats: mean TPS, TTFT
   - Explain: "History persists for the session, JSONL export available for long-term storage"

5. **Dark Mode Toggle** (2:20-2:50)
   - Return to Settings
   - Show dark mode toggle
   - Toggle between light/dark
   - Show both themes
   - Text: "Supports both light and dark mode"

6. **Summary** (2:50-3:00)
   - Show all 4 tabs
   - Mention: "Open-source, available on GitHub"
   - Final screen: Report PDF with results

### Video 2 Recording Tips

- **One continuous recording** (or stitch 2-3 short clips)
- **Go slow**: Let UI transitions finish before next action
- **Show success**: Make sure everything works (no errors)
- **Narration**: Add voice-over explaining each feature as you demonstrate

---

## Device Preparation Checklist

Before EACH recording session:
```bash
# Free up memory
adb shell "sync && echo 3 > /proc/sys/vm/drop_caches"

# Kill any lingering processes
adb shell "pkill -f llama"

# Verify free memory
adb shell "free -h"  # Should show ~1GB free

# Clear app cache (optional)
adb shell "am clear-debug-app com.eai.edgellmbench"
```

---

## Recording Tools Options

### Option A: Android built-in screen recording
```bash
# Start recording
adb shell screenrecord --output-format=h264 /sdcard/recording.mp4

# Stop after desired duration
# Pull to computer
adb pull /sdcard/recording.mp4 ~/Desktop/
```

### Option B: scrcpy (wireless mirroring + record)
```bash
# Install: `brew install scrcpy` (macOS)
scrcpy --record /tmp/recording.mp4
```

### Option C: ADB screencap + ffmpeg for video
```bash
# Capture frames
adb exec-out screenrecord --output-format=h264 | ffmpeg -i - output.mp4
```

---

## Post-Production

### Video 1 Editing
- Use iMovie, Adobe Premiere, or DaVinci Resolve
- Overlay text: variant name, TPS, TTFT
- Speed up Q2_K/Q6_K slightly to keep video punchy
- Sync audio: explain each variant as it plays
- Benchmark comparison table at end

### Video 2 Editing
- Simple cuts between sections
- Add text labels for each feature
- Include voiceover or captions
- Background music (optional, keep audio of app UI for authenticity)

---

## Timing Summary

| Video | Content | Duration | Recording Time |
|-------|---------|----------|-----------------|
| **V1** | 5 quantization variants | 2 min | ~20 min (5 variant recordings) |
| **V2** | Settings, Benchmark, History | 3 min | ~5 min (1 continuous recording) |
| **Total** | — | 5 min | ~25 min recording + 15 min editing |

---

## Success Criteria

- [ ] All 5 variant recordings complete without crashes
- [ ] Same prompt displayed/confirmed in all videos
- [ ] Metrics (TTFT, total time) clearly visible
- [ ] Settings persist across actions
- [ ] Benchmark completes and shows results
- [ ] History tab displays prior run
- [ ] Dark mode toggle works
- [ ] No errors or ANRs
- [ ] Final video is smooth and watchable
- [ ] Narrative clearly explains speed/accuracy tradeoffs

---

## Next Steps

1. **Confirm prompt** — Which prompt to use? (provided above or choose your own?)
2. **Device prep** — Run memory cleanup commands
3. **Start Recording V1** — Record all 5 variants
4. **Record V2** — One Settings/Benchmark/History walkthrough
5. **Edit** — Combine into two final videos
6. **Upload** — Post to YouTube or deliver as MP4

**Estimated total time: 1 hour recording + editing**

