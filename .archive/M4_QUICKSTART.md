# M4 Mac Benchmark - Quick Start

## TL;DR - Run This Now

```bash
cd ~/path/to/291_EAI
bash scripts/benchmark_m4_mac.sh
```

**That's it!** The script will:
- ✅ Autodetect all 7 models in `local-models/llama3_2_3b_gguf/`
- ✅ Run benchmark on M4 Metal GPU (4 contexts × 7 variants × 15 trials)
- ✅ Save results to timestamped directory
- ✅ Show progress in real-time

**Estimated time:** 3-4 hours (fully autonomous, you can leave running)

---

## What the Script Does

1. **Checks setup:**
   - Verifies models exist in local-models/llama3_2_3b_gguf/
   - Verifies llama-cli is installed

2. **Runs benchmarks:**
   - 7 variants: Q2_K, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0
   - 4 context lengths: 256, 512, 1024, 2048 tokens
   - 15 trials per config
   - Total: 420 inference runs

3. **Collects results:**
   - Saves TPS (tokens per second) for each run
   - Generates timestamped results directory
   - Creates JSONL files (one per variant+context combo)

4. **Shows progress:**
   - Real-time trial counter
   - Overall progress percentage
   - Results summary when complete

---

## Prerequisites

### Verify llama-cli is installed:
```bash
llama-cli --version
```

If NOT installed:
```bash
brew install llama.cpp
```

### Verify models exist:
```bash
ls -lh ~/path/to/291_EAI/local-models/llama3_2_3b_gguf/
# Should show: Q2_K.gguf, Q3_K_M.gguf, Q4_K_S.gguf, Q4_K_M.gguf, Q5_K_M.gguf, Q6_K.gguf, Q8_0.gguf
```

If models missing, download from HuggingFace:
```bash
cd local-models/llama3_2_3b_gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q2_K.gguf
wget https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q3_K_M.gguf
# ... etc for other variants
```

---

## Run It Now

```bash
cd ~/path/to/291_EAI
bash scripts/benchmark_m4_mac.sh
```

**Output will look like:**
```
===================================================================
M4 Mac Metal Benchmark
Start Time: 2026-03-17T06:45:32
Models: local-models/llama3_2_3b_gguf
Results: results/m4_mac_metal_20260317_064532
Variants: Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0
Contexts: 256 512 1024 2048
Trials per config: 15
===================================================================

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 Benchmarking: Q2_K
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Context: 256 tokens | Trials: 15
    Trial 1/15 (0%) ✓ 12.45 tok/s
    Trial 2/15 (1%) ✓ 12.38 tok/s
    ...
```

---

## While It's Running

The script runs autonomously. You can:

1. **Monitor in another terminal:**
   ```bash
   # Watch progress
   watch -n 30 'ls -lh ~/path/to/291_EAI/results/m4_mac_metal_*/*.jsonl'

   # Or tail recent results
   tail -f ~/path/to/291_EAI/results/m4_mac_metal_*/m4_*.jsonl | jq '.decode_tps'
   ```

2. **Check system resources:**
   ```bash
   # Open Activity Monitor
   open -a "Activity Monitor"
   # Watch: GPU usage (should be ~80-95%), CPU usage, Memory
   ```

3. **Or just leave it running** - will complete in 3-4 hours

---

## When It Completes

```bash
# Check results saved
ls results/m4_mac_metal_*/

# View sample results
head -3 results/m4_mac_metal_*/m4_Q2_K_ctx256.jsonl

# Example output:
# {"variant": "Q2_K", "context_length": 256, "trial": 1, "timestamp": "...",
#  "device": "M4 Mac", "backend": "Metal", "decode_tps": 12.45, ...}
```

---

## Next Steps After Benchmark Completes

```bash
# 1. Copy to results directory (already there)
# (Already saved with timestamped directory)

# 2. Generate comparison figures
python3 analysis/generate_figures.py results/m4_mac_metal_*/

# 3. Analyze M4 vs Pixel 6a throughput
# Compare: GPU (M4) vs ARM NEON (Pixel 6a)
# Expected: M4 Q8_0 ~12 tok/s (3x faster), monotonic ordering (vs non-monotonic on ARM)
```

---

## Expected Results

### GPU (M4 Metal) - Monotonic Ordering
```
Q8_0:    12.1 tok/s  ← Fastest on GPU
Q6_K:    11.8 tok/s
Q5_K_M:  11.5 tok/s
Q4_K_M:  11.2 tok/s
Q4_K_S:  10.9 tok/s
Q3_K_M:  10.6 tok/s
Q2_K:    10.2 tok/s  ← Slowest on GPU (opposite of ARM!)
```

### ARM NEON (Pixel 6a) - Non-Monotonic Ordering
```
Q2_K:    5.66 tok/s  ← Fastest on ARM
Q4_K_M:  5.32 tok/s
Q8_0:    4.95 tok/s
Q3_K_M:  4.12 tok/s
Q6_K:    3.98 tok/s  ← Slowest on ARM
```

**Key finding:** GPU prefers full precision; ARM prefers lightweight quantization.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `llama-cli: command not found` | `brew install llama.cpp` |
| `Models not found` | Verify path: `ls local-models/llama3_2_3b_gguf/` |
| Benchmark very slow (< 1 tok/s) | Check Activity Monitor: GPU might not be detected. Verify Metal GPU: `llama-cli --version \| grep -i metal` |
| Out of memory | Script uses 4 threads. Reduce to 2: Edit script line `llama-cli ... -t 4` → `-t 2` |
| Results directory not created | Verify write permissions: `touch results/test.txt` |

---

## That's It!

**Run:** `bash scripts/benchmark_m4_mac.sh`

**Time:** 3-4 hours autonomous

**Output:** M4 GPU throughput validation for cross-device comparison

Go grab coffee ☕ and check back in 4 hours! 🚀
