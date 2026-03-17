# Parallel Cross-Device Benchmarking Setup Guide

**Goal:** Run throughput & quality benchmarks on M4, iPhone 14 Pro, and HP Pavilion **in parallel** with Pixel 6a WikiText-2 runs.

**Timeline:** Start immediately; all can run autonomously while Pixel 6a finishes Phase 2A.

---

## Quick Start

### **On M4 Mac (You have this now)** ⏰ ~3-4 hours total

#### **Step 1: Download llama.cpp with Metal backend**
```bash
# Clone llama.cpp (if not already done)
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
make clean && make -j$(nproc) GGML_METAL=1

# Or use Homebrew (faster)
brew install llama.cpp
```

#### **Step 2: Download models**
```bash
# Copy from your host machine (or download fresh)
# All 7 GGUF variants needed for M4
cp -v ~/path/to/291_EAI/local-models/llama3_2_3b_gguf/*.gguf ~/llama-models/

# Or download if needed:
cd ~/llama-models
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q2_K.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q3_K_M.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_S.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q5_K_M.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q6_K.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q8_0.gguf
```

#### **Step 3: Run M4 throughput benchmark**
```bash
# Create script: scripts/benchmark_m4_metal.sh
cat > benchmark_m4_metal.sh << 'EOF'
#!/bin/bash

MODELS_DIR=~/llama-models
RESULTS_DIR=results/m4_metal_$(date +%Y%m%d_%H%M%S)
mkdir -p $RESULTS_DIR

CTX_SIZES=(256 512 1024 2048)
VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
NUM_TRIALS=15
PROMPT="The future of artificial intelligence is"
OUTPUT_TOKENS=128

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_FILE="$MODELS_DIR/Llama-3.2-3B-Instruct-${VARIANT}.gguf"

    if [ ! -f "$MODEL_FILE" ]; then
        echo "ERROR: $MODEL_FILE not found"
        continue
    fi

    echo "=== Benchmarking Q${VARIANT} on M4 Metal ==="

    for CTX in "${CTX_SIZES[@]}"; do
        echo "  Context: $CTX tokens"

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            # Use Metal GPU (default on M4)
            llama-cli \
                -m "$MODEL_FILE" \
                -c $CTX \
                -n $OUTPUT_TOKENS \
                -p "$PROMPT" \
                -t 4 \
                --log-format json \
                2>&1 | jq --arg variant $VARIANT --arg ctx $CTX --arg trial $TRIAL \
                '.build.description as $build |
                 {variant: $variant, ctx: $ctx, trial: $trial,
                  build: {description: $build},
                  metrics: {decode_tps: .timings.tokens_per_second_tokens}}' \
                >> "$RESULTS_DIR/m4_metal_${VARIANT}_ctx${CTX}.jsonl"
        done
    done
done

echo "Results saved to: $RESULTS_DIR"
ls -lah "$RESULTS_DIR"
EOF

chmod +x benchmark_m4_metal.sh
./benchmark_m4_metal.sh
```

#### **Step 4: Collect M4 results**
```bash
# When done, copy results back to host
scp -r results/m4_metal_* <host>:~/291_EAI/results/cross_device/
```

---

### **On iPhone 14 Pro** ⏰ ~2-3 hours total

**Option A: Using LLM Farm (Easiest)**

#### **Step 1: Install LLM Farm**
- Download from App Store: "LLM Farm"
- Open app

#### **Step 2: Add models**
```
1. In app: Settings → Model Management → Add Model
2. Select from HuggingFace: bartowski/Llama-3.2-3B-Instruct-GGUF
3. Download all 7 variants (Q2_K, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0)
   Each will take 2-5 minutes depending on WiFi
```

#### **Step 3: Run benchmark in LLM Farm**
```
1. For each variant:
   - Select model in app
   - Go to "Benchmark" tab
   - Set context length: 256, 512, 1024, 2048 (separate runs)
   - Set output tokens: 128
   - Run 15 trials
   - Note the TPS values displayed
   - Screenshot or copy results

2. Manual recording needed (app exports via email/Files):
   - Tap "Export Results"
   - Save to iCloud or email to yourself
```

**Option B: Using llama.cpp CLI (More Automated)**

#### **Step 1: SSH to iPhone (requires jailbreak - skip if not jailbroken)**
If you have SSH access via jailbreak:
```bash
# From Mac: SSH into iPhone
ssh root@<iphone-ip-address>

# Run llama.cpp:
cd /var/mobile/llama.cpp
./llama-cli -m Llama-3.2-3B-Instruct-Q4_K_M.gguf \
    -c 1024 -n 128 -t 4 \
    --log-format json \
    -p "The future of AI is"
```

**Recommendation:** Use **LLM Farm app** (easier, no jailbreak needed). Manual recording is fine for cross-device validation purposes.

---

### **On HP Pavilion x86** ⏰ ~2-3 hours total

#### **Step 1: Install llama.cpp with AVX2**
```bash
# On Windows (PowerShell) or Linux (bash):
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp

# Linux:
make -j$(nproc) GGML_AVX2=1

# Windows (MSVC):
cmake -B build -DGGML_AVX2=ON
cmake --build build --config Release -j
```

#### **Step 2: Copy models**
```bash
# Copy from 291_EAI to HP Pavilion
mkdir -p ~/llama-models
cp /path/to/291_EAI/local-models/llama3_2_3b_gguf/*.gguf ~/llama-models/
```

#### **Step 3: Run x86 benchmark script**
```bash
cat > benchmark_x86_avx2.sh << 'EOF'
#!/bin/bash

MODELS_DIR=~/llama-models
RESULTS_DIR=results/x86_avx2_$(date +%Y%m%d_%H%M%S)
mkdir -p $RESULTS_DIR

CTX_SIZES=(256 512 1024 2048)
VARIANTS=(Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0)
NUM_TRIALS=15
PROMPT="The future of artificial intelligence is"
OUTPUT_TOKENS=128

for VARIANT in "${VARIANTS[@]}"; do
    MODEL_FILE="$MODELS_DIR/Llama-3.2-3B-Instruct-${VARIANT}.gguf"

    [ ! -f "$MODEL_FILE" ] && echo "ERROR: $MODEL_FILE not found" && continue

    echo "=== Benchmarking $VARIANT on x86 AVX2 ==="

    for CTX in "${CTX_SIZES[@]}"; do
        echo "  Context: $CTX tokens"

        for TRIAL in $(seq 1 $NUM_TRIALS); do
            llama-cli \
                -m "$MODEL_FILE" \
                -c $CTX \
                -n $OUTPUT_TOKENS \
                -p "$PROMPT" \
                -t 8 \
                --log-format json \
                2>&1 | tee -a "$RESULTS_DIR/x86_${VARIANT}_ctx${CTX}.jsonl"
        done
    done
done

echo "Results saved to: $RESULTS_DIR"
tar -czf "x86_avx2_results_$(date +%Y%m%d_%H%M%S).tar.gz" "$RESULTS_DIR"
echo "Archive created: x86_avx2_results_*.tar.gz"
EOF

chmod +x benchmark_x86_avx2.sh
./benchmark_x86_avx2.sh
```

#### **Step 4: Send results back**
```bash
# Option 1: Upload to cloud
rclone copy x86_avx2_results_*.tar.gz gdrive:/Benchmarks/

# Option 2: SCP to host Mac
scp x86_avx2_results_*.tar.gz <user>@<host>:~/291_EAI/results/cross_device/

# Option 3: Manual via USB
# Copy tar.gz to USB drive and physically transfer
```

---

## Summary Table: Parallel Execution Plan

| Device | Backend | Time | Status | Trigger |
|--------|---------|------|--------|---------|
| **Pixel 6a** | NEON ARM | ~40 hrs | ⏳ Running (Phase 2A) | Auto (now) |
| **M4 Mac** | Metal GPU | ~3-4 hrs | ⏰ Ready to start | Start immediately |
| **iPhone 14 Pro** | A16 Metal | ~2-3 hrs | ⏰ Ready to start | Start immediately (manual) |
| **HP Pavilion** | AVX2 x86 | ~2-3 hrs | ⏰ Ready to start | Start immediately |

**Total Parallel Time:** 40 hours (sequential not needed!)
**Work Required:** ~5 hours setup + ~10 hours monitoring

---

## Commands to Start ALL in Parallel NOW

### **On M4 Mac (Terminal 1):**
```bash
cd ~/llama.cpp
./benchmark_m4_metal.sh 2>&1 | tee ~/m4_benchmark.log
```

### **On HP Pavilion (Terminal or SSH):**
```bash
cd ~/llama.cpp
bash benchmark_x86_avx2.sh 2>&1 | tee ~/x86_benchmark.log
```

### **On iPhone 14 Pro:**
```
Open LLM Farm app → Benchmark tab → Start manual runs
(Or if SSH access: ssh root@<ip> and run llama-cli)
```

### **On Pixel 6a (Running autonomously):**
```bash
# Already running WikiText-2
# Check status:
adb shell "ps | grep llama"
adb shell "tail -5 /data/local/tmp/ppl_full_*.txt"
```

---

## Expected Speedup

**Sequential (current plan):** 40 hrs (Pixel) + 8 hrs (quality evals) + 3-4 hrs (cross-device) = ~51 hours total

**Parallel (new plan):** 40 hrs (Pixel) + 4 hrs (M4/iPhone/x86) + 8 hrs (quality evals) = ~52 hours total BUT all device work runs concurrently

**Actual wall-clock time:** ~50 hours instead of ~51 hours (minor gain due to overlap)

**But more importantly:** You'll have cross-device data by tomorrow instead of waiting until after Phase 2A + 2B complete!

---

## Monitoring Dashboard

Create a simple status file to track all devices:

```bash
cat > PARALLEL_STATUS.txt << 'EOF'
=== PARALLEL BENCHMARK STATUS ===
Last Updated: $(date)

Pixel 6a (Tensor G1, ARM NEON):
  Phase: WikiText-2 Full Corpus PPL
  Progress: Q4_K_S running (~8hrs remaining)
  ETA Completion: ~2026-03-17 18:00 UTC
  Status: ⏳ In Progress

M4 Mac (Apple Metal GPU):
  Phase: Throughput sweep (4 contexts × 7 variants × 15 trials)
  Progress: Starting now
  ETA Completion: ~2026-03-17 14:00 UTC
  Status: 🟢 Queued

iPhone 14 Pro (A16, Metal):
  Phase: Throughput sweep (manual in LLM Farm)
  Progress: Ready for start
  ETA Completion: ~2026-03-17 13:00 UTC
  Status: 🟡 Manual (ready)

HP Pavilion (x86 AVX2):
  Phase: Throughput sweep (4 contexts × 7 variants × 15 trials)
  Progress: Queued
  ETA Completion: ~2026-03-17 14:00 UTC
  Status: 🟢 Queued

Quality Benchmarks (4 new benchmarks × 7 variants):
  Phase: ARC-Challenge, HellaSwag, MMLU, TruthfulQA
  Trigger: After Pixel 6a Phase 2A completes
  ETA Start: ~2026-03-17 18:00 UTC
  ETA Completion: ~2026-03-18 02:00 UTC
  Status: ⏳ Queued (awaiting Phase 2A)
EOF
```

Update this file as benchmarks progress.

---

## When Results Arrive

### **M4 Mac Results:**
```bash
# Copy back to host
scp -r ~/llama.cpp/results/m4_metal_* <host>:~/291_EAI/results/cross_device/m4/

# Analysis
python3 analysis/analyze_cross_device.py results/cross_device/m4/
```

### **iPhone 14 Pro Results:**
```bash
# Manual: Screenshot or copy from LLM Farm export
# Manually create JSON:
cat > results/cross_device/iphone14pro/iphone_results.json << 'EOF'
{
  "device": "iPhone 14 Pro (A16)",
  "backend": "Metal",
  "results": {
    "Q2_K_ctx256": 4.89,
    "Q2_K_ctx512": 4.82,
    ...
  }
}
EOF
```

### **HP Pavilion Results:**
```bash
# Copy archive to host
scp x86_avx2_results_*.tar.gz <host>:~/291_EAI/results/cross_device/x86/
tar -xzf x86_avx2_results_*.tar.gz
```

---

## Integration into Report

Once all parallel results arrive:

```bash
# Master consolidation script
python3 scripts/consolidate_cross_device_results.py \
    results/cross_device/m4/ \
    results/cross_device/iphone14pro/ \
    results/cross_device/x86/ \
    --output results/cross_device_summary.json

# Generate comparison figures
python3 analysis/generate_cross_device_figures.py \
    results/cross_device_summary.json \
    --output figures/cross_device_comparison.pdf
```

---

## Start Time Recommendation

**START ALL THREE (M4, iPhone, HP) IMMEDIATELY** ✅

- M4 Mac: `./benchmark_m4_metal.sh`
- HP Pavilion: `bash benchmark_x86_avx2.sh`
- iPhone 14 Pro: Open LLM Farm app
- Pixel 6a: Already running (monitor via `adb shell`)

**Do NOT wait** for Pixel 6a to finish. All cross-device runs are independent.

By the time Pixel 6a Phase 2A completes (~40 hours), you'll already have:
- ✅ M4 Metal GPU results
- ✅ iPhone 14 Pro A16 results
- ✅ HP Pavilion x86 AVX2 results
- ⏳ Pixel 6a WikiText-2 PPL (completing)

Then immediately:
- Run Phase 2B (new quality benchmarks on Pixel 6a only, ~8-12 hrs)
- Integrate all cross-device data into paper
- **Final submission-ready paper in <48 hours total**

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| M4 Metal not detected | Check `llama-cli --version \| grep metal` |
| iPhone LLM Farm won't download | Ensure WiFi, not cellular; try restarting app |
| HP Pavilion AVX2 compilation fails | Use pre-built binary: `https://github.com/ggerganov/llama.cpp/releases` |
| Results file too large | Results are <1MB per device; should fit on any system |

---

**Ready to start parallel benchmarking? Run the commands above on each device NOW!** 🚀
