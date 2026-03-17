# Cross-Device Benchmark Setup

This directory contains scripts for running equivalent GGUF benchmarks on three
platforms beyond the primary Google Pixel 6a Android device:

| Platform | Script | Backend | Expected decode TPS |
|---|---|---|---|
| Mac M4 (MacBook Pro / Mac Mini) | `mac_m4_bench.sh` | Metal GPU | 50–80 tok/s |
| x86_64 Linux (HP Pavilion etc.) | `x86_bench.sh` | CPU / AVX2 | 3–8 tok/s |
| iPhone 14 Pro | Manual via LLM Farm | ANE / GPU | 15–35 tok/s |

The Pixel 6a baseline runs at approximately 4–6 tok/s (decode) with Q4_K_M.
The large Mac M4 advantage is expected and reflects the hardware ceiling difference.

---

## Benchmark parameters (all platforms)

- **Model**: Llama 3.2 3B Instruct (7 GGUF variants)
- **Context sizes**: 256, 1024, 2048 tokens (512 skipped to save time)
- **Output length**: 128 tokens per run
- **Trials per cell**: 10 (+ 2 warmups, excluded from analysis)
- **Prompt**: `qa_short_001` from `prompts/prompt-suite-v1.yaml`

---

## 1. Mac M4 Setup

### Install llama.cpp

**Option A — Homebrew (recommended):**
```bash
brew install llama.cpp
# Verify:
llama-cli --version
```

**Option B — Build from source with Metal:**
```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
cmake -B build -DLLAMA_METAL=ON
cmake --build build --config Release -j8
export PATH=$PATH:$(pwd)/build/bin
llama-cli --version
```

### Download models

From the project root:
```bash
bash scripts/download_models.sh
# Models land in: local-models/llama3_2_3b_gguf/
```

### Run the benchmark

```bash
bash scripts/cross_device/mac_m4_bench.sh \
    --model-dir local-models/llama3_2_3b_gguf/ \
    --output-dir results/
```

Optional flags:
```bash
# Run only two variants:
--variants Q4_K_M,Q8_0

# Override context sizes:
--ctx-sizes 256,2048
```

Output: `results/crossdev_mac_m4_YYYYMMDD_HHMMSS.jsonl`

### What to expect

- Load time: 1–3 seconds per model (models cached in memory after first load)
- Q4_K_M decode: ~60 tok/s at ctx=256, ~55 tok/s at ctx=2048
- Full run (all 7 variants × 3 contexts × 12 runs): ~45 minutes

---

## 2. HP Pavilion / x86_64 Linux Setup

### Build llama.cpp with AVX2

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp

# Option A — Makefile:
make GGML_AVX2=1 -j$(nproc)
export PATH=$PATH:$(pwd)

# Option B — cmake:
cmake -B build -DGGML_AVX2=ON
cmake --build build --config Release -j$(nproc)
export PATH=$PATH:$(pwd)/build/bin

llama-cli --version
```

Verify AVX2 is present on the target machine:
```bash
grep -m1 avx2 /proc/cpuinfo && echo "AVX2 OK" || echo "WARNING: no AVX2"
```

### Copy models

Transfer the GGUF files to the Linux machine. From your Mac:
```bash
rsync -avz local-models/llama3_2_3b_gguf/ user@hp-pavilion:/home/user/llama_models/
```

### Run the benchmark

```bash
bash scripts/cross_device/x86_bench.sh \
    --model-dir /home/user/llama_models/ \
    --output-dir results/
```

Output: `results/crossdev_x86_YYYYMMDD_HHMMSS.jsonl`

### What to expect

- CPU inference is much slower than Metal; expect 3–8 tok/s for Q4_K_M
- Q2_K and Q3_K_M will be fastest; Q8_0 may be 2–3× slower than Q4_K_M
- Full run: 3–6 hours; consider `--variants Q4_K_M,Q8_0` for a quick pass first
- Watch CPU temperature: sustained inference at 100% can cause throttling

---

## 3. iPhone 14 Pro Setup (Manual)

iPhone benchmarking uses the **LLM Farm** app since llama.cpp does not have
a scriptable iOS CLI. Results are recorded manually as single data points.

### Install LLM Farm

1. Open the App Store on iPhone 14 Pro
2. Search for "LLM Farm" (developer: guinmoon)
3. Install the free app

### Transfer model files

1. On your Mac, open Finder
2. Connect iPhone via USB and trust the connection
3. In Finder sidebar select your iPhone → Files → LLM Farm → `models/`
4. Drag the following GGUF files into that folder:
   - `Llama-3.2-3B-Instruct-Q2_K.gguf`
   - `Llama-3.2-3B-Instruct-Q4_K_M.gguf`
   - `Llama-3.2-3B-Instruct-Q8_0.gguf`

Alternatively use the Files app on iPhone:
- On iPhone, go to Files → On My iPhone → LLM Farm → models
- Use AirDrop to receive the GGUF files from Mac

### Run the built-in benchmark

1. Open LLM Farm
2. Tap the model file to load it
3. In the model settings screen look for "Benchmark" or "Speed test" button
4. Run the benchmark (it will generate tokens and display tok/s)
5. Record the displayed **tokens/second** value

Repeat for Q2_K, Q4_K_M, and Q8_0 at each context length you want to compare.
LLM Farm does not currently support 10-trial averaging, so record 3 readings
and note the mean manually.

### Enter results for comparison

Create a file `results/crossdev_ios_manual.csv` with this format:

```csv
device_tag,variant,context_length,decode_tps_mean,n_trials
iphone14pro_ane,Q2_K,256,<value>,3
iphone14pro_ane,Q4_K_M,256,<value>,3
iphone14pro_ane,Q8_0,256,<value>,3
```

These can be imported manually into `analysis/generate_figures.py` figures
for a qualitative comparison. Full JSONL output is not available from LLM Farm.

---

## 4. Standardising Results

After running `mac_m4_bench.sh` and/or `x86_bench.sh`:

```bash
# Analyse a single platform:
python3 scripts/cross_device/parse_crossdev_results.py results/crossdev_mac_m4_*.jsonl

# Analyse multiple platforms together:
python3 scripts/cross_device/parse_crossdev_results.py \
    results/crossdev_mac_m4_*.jsonl \
    results/crossdev_x86_*.jsonl

# Write summary CSV (compatible with generate_figures.py):
python3 scripts/cross_device/parse_crossdev_results.py \
    results/crossdev_mac_m4_*.jsonl \
    --output-csv results/crossdev_summary.csv

# Split into one CSV per device:
python3 scripts/cross_device/parse_crossdev_results.py \
    results/crossdev_*.jsonl \
    --output-csv results/crossdev_all.csv \
    --split-devices
```

The output CSV columns match `figures/summary_table.csv` from the Android
baseline run, with an extra `device_tag` column (`mac_m4_metal`, `x86_avx2`,
or `android_<model>`).

---

## 5. Expected Results

Approximate decode throughput (tok/s) for Q4_K_M at ctx=256:

| Device | Backend | Approx. decode TPS |
|---|---|---|
| Apple M4 (MacBook Pro) | Metal | 55–80 |
| iPhone 14 Pro | Apple Neural Engine | 15–30 |
| Google Pixel 6a | CPU (llama.cpp) | 4–6 |
| HP Pavilion (Core i7) | CPU / AVX2 | 3–7 |

**The Mac M4 advantage (10–15× faster than Pixel 6a) is expected and correct.**
It demonstrates the hardware ceiling for this model size — a dedicated NPU +
unified memory architecture running at ~3.7 GHz with 10-core GPU outperforms
a mobile SoC running pure-CPU inference.

The Pixel 6a baseline is the primary experimental target (examining
quantization trade-offs on a representative mid-range Android device).
Cross-device numbers provide context for the absolute scale of the trade-offs.

---

## Troubleshooting

**`llama-cli: command not found`**
Add the llama.cpp build directory to `PATH` or install via `brew install llama.cpp`.

**`WARNING: No GGUF file found for variant ...`**
Check that filenames contain the variant string (e.g. `Q4_K_M`). The search is
case-insensitive and looks for `*Q4_K_M*.gguf` anywhere in `--model-dir`.

**Mac: inference using CPU instead of Metal**
Confirm with `llama-cli --version` that the binary was built with Metal support.
Homebrew builds on Apple Silicon include Metal by default. Check for the string
"Metal" in the model loading output.

**x86: very slow inference**
Verify AVX2: `grep -m1 avx2 /proc/cpuinfo`. If absent, the binary may be using
scalar fallback. Rebuild with `GGML_AVX2=1`.

**Parse errors in output JSONL**
Run with a single trial to inspect raw output:
```bash
llama-cli --model <file.gguf> --ctx-size 256 --n-predict 128 --threads 8 --prompt "Hello"
```
The script expects the standard `llama_perf_context_print:` timing lines.
