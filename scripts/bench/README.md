# scripts/bench/ — Benchmark Scripts Reference

This directory contains all benchmark scripts for the project.
Scripts are labeled: **Active** (used in paper), **Exploratory** (experimental), or **Superseded** (replaced by better methodology).

---

## Active Scripts — Used in Paper

| Script | Status | Paper Section | Description |
|--------|--------|---------------|-------------|
| `pixel_llama_tps.sh` | ✅ Active | Table 1 (TPS) | Pixel 6a decode/prefill TPS sweep — 7 variants × 4 contexts × 10 trials |
| `pixel_llama_cliff_filled.sh` | ✅ Active | Table 2 (RQ2) | Filled-context KV-cache cliff sweep — prompts sized N-64 tokens to saturate KV cache |
| `pixel_quality.sh` | ✅ Active | Table 3 (RQ3) | Quality benchmarks via ADB — ARC-Challenge, ARC-Easy, HellaSwag, MMLU, BoolQ, TruthfulQA |
| `m4_llama_tps.sh` | ✅ Active | Table 4 (M4 cross-device) | Mac M4 Metal TPS sweep — same variants, Metal GPU backend |
| `m4_llama_cliff.sh` | 🔵 Exploratory | Not in paper (yet) | M4 filled-context cliff sweep — data collected, analysis pending |

---

## Superseded Scripts — Do Not Use

| Script | Status | Replaced By | Why Superseded |
|--------|--------|-------------|----------------|
| `pixel_llama_cliff.sh` | ⚠️ Superseded | `pixel_llama_cliff_filled.sh` | Used `-c N` (allocation-only); KV cache was NOT actually saturated. Results were systematically wrong for RQ2. |

---

## Exploratory Scripts — Not in Paper

| Script | Status | Notes |
|--------|--------|-------|
| `pixel_qwen_tps.sh` | 🔵 Exploratory | Qwen 2.5 1.5B TPS on Pixel — dataset supplement |
| `pixel_wikitext_ppl.sh` | 🔵 Exploratory | Full WikiText-2 PPL via ADB — Pixel PPL column (Q2_K/Q3_K_M collected; Q4–Q8 pending) |
| `m4_qwen_tps.sh` | ✅ Validated extension | Qwen 2.5 1.5B TPS on M4 Metal — canonical run: `results/m4_qwen_tps_20260415_130955/` |
| `m4_qwen_cliff.sh` | ✅ Validated extension | Qwen cliff sweep on M4 Metal — canonical run: `results/m4_qwen_cliff_20260416_021323/` |
| `m4_cpu_cliff.sh` | 🔵 Exploratory | Llama 3.2 3B cliff on M4 CPU (ngl=0) — collected 2026-04 |
| `m4_cpu_tps.sh` | 🔵 Exploratory | Llama 3.2 3B TPS on M4 CPU — collected 2026-04 |
| `m4_cpu_qwen_cliff.sh` | 🔵 Exploratory | Qwen 2.5 1.5B cliff on M4 CPU — **pending data collection** |
| `x86_llama_tps.sh` | 🔵 Exploratory | x86 CPU decode TPS reference — 7 variants at ctx=256 |
| `x86_qwen_cliff.py` | 🔵 Exploratory | Qwen 2.5 1.5B cliff on x86 — **pending rerun** (v2: TG=128) |
| `x86_qwen_tps.sh` | 🔵 Exploratory | Qwen 2.5 1.5B TPS on x86 — ctx=256 reference |
| `pixel_imatrix_quality.sh` | 🔵 Exploratory | imatrix calibrated quality benchmarks — all 7 variants × 5 benchmarks |
| `pixel_llama_fa_mitigation.sh` | ⛔ Blocked | Flash Attention unsupported on this llama-completion binary build |

---

## Pending Data Collection

Scripts ready to run — data not yet collected:

| # | Script | Platform | Expected Runtime | Purpose |
|---|--------|----------|-----------------|---------|
| 1 | `x86_qwen_cliff.py` | Windows x86 (i5-1235U) | ~4–6 h | Qwen KV-cache cliff sweep, 11 ctx × 5 trials × 7 variants (TG=128 rerun) |
| 2 | `pixel_wikitext_ppl.sh Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0` | Pixel 6a via ADB | ~5–7 h | Pixel full-corpus PPL for Q4–Q8 (Q2_K/Q3_K_M already collected) |
| 3 | M4 Qwen ingestion promotion | M4 Mac | TBD | TPS and cliff data are validated; parquet/dashboard integration still pending |
| 4 | `m4_cpu_tps.sh` | M4 Mac | ~90–120 min | M4 CPU TPS rerun under idle conditions |
| 5 | M4 quality runner redesign | M4 Mac | TBD | Existing runner is invalid because it reloads one model per question |

See **Running Instructions** section below for step-by-step commands.

---

## Canonical Result Directories

See `results/CANONICAL.md` for the full manifest linking each script run → paper figure/table.

Quick reference:
- **Table 1 TPS**: `results/pixel_llama_tps_20260325_120022/`
- **Table 2 cliff**: `results/pixel_llama_cliff_filled_20260326_132101/`
- **Table 3 quality**: `results/quality_scores.json`
- **Table 4 M4**: `results/m4_llama_tps_20260326_001546/`
- **M4 Qwen TPS extension**: `results/m4_qwen_tps_20260415_130955/`
- **M4 Qwen cliff extension**: `results/m4_qwen_cliff_20260416_021323/`

---

## Common Usage

```bash
# Full TPS sweep (Pixel 6a, ~45 min)
bash scripts/bench/pixel_llama_tps.sh

# KV-cache cliff sweep — filled-context (Pixel 6a, ~90 min)
bash scripts/bench/pixel_llama_cliff_filled.sh

# Quality benchmarks (Pixel 6a via ADB, ~3 hours total)
bash scripts/bench/pixel_quality.sh boolq
bash scripts/bench/pixel_quality.sh arc_easy
bash scripts/bench/pixel_quality.sh arc_challenge
bash scripts/bench/pixel_quality.sh hellaswag
bash scripts/bench/pixel_quality.sh mmlu
bash scripts/bench/pixel_quality.sh truthfulqa

# M4 Metal TPS sweep (~45 min)
bash scripts/bench/m4_llama_tps.sh
```

---

## Running Instructions — Pending Data Collection

### 1. x86 Qwen Cliff Re-run (Windows x86)

**Why:** Previous run used `TG_TOKENS=32` — too short for Windows scheduler noise (CV 50–80%).
v2 uses `TG_TOKENS=128` (~6.4s decode window → CV <15%).

**Platform:** HP Pavilion x86 (or any Windows i5+ machine with llama.cpp built)

**Prerequisites:**
```
# 1. Build llama.cpp (if not already done):
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && cmake -B build -DGGML_AVX2=ON && cmake --build build --config Release
# Binary at: build\bin\Release\llama-bench.exe

# 2. Download Qwen models (run once, ~13 GB total):
pip install huggingface_hub
python -c "
from huggingface_hub import hf_hub_download; import os
os.makedirs('local-models/qwen2_5_1_5b_gguf', exist_ok=True)
for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:
    hf_hub_download('bartowski/Qwen2.5-1.5B-Instruct-GGUF',
        f'Qwen2.5-1.5B-Instruct-{v}.gguf',
        local_dir='local-models/qwen2_5_1_5b_gguf')
"

# 3. Set binary path (or add to PATH):
set LLAMA_BENCH_PATH=C:\path\to\llama.cpp\build\bin\Release\llama-bench.exe
```

**Run:**
```
# Close all background apps (Defender real-time scan, browser, Slack)
# Plug into power — no battery mode
py -3 scripts/bench/x86_qwen_cliff.py

# Subset if needed:
py -3 scripts/bench/x86_qwen_cliff.py Q2_K Q3_K_M
# Resume interrupted run:
py -3 scripts/bench/x86_qwen_cliff.py --resume
```

**Output:** `results/x86_qwen_cliff_<HOSTNAME>_<ts>/cliff_<VARIANT>.jsonl`

**After collecting:**
```bash
python3 scripts/prepare_dataset.py
python3 scripts/bake_dashboard_data.py
```

---

### 2. Pixel 6a Full-Corpus PPL for Q4–Q8

**Why:** Q2_K and Q3_K_M already have Pixel full-corpus PPL (~285K tokens).
Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0 currently use x86 values (~290K tokens).
Collecting Pixel values enables cross-device PPL consistency check and removes
the corpus-device mismatch note from the dashboard.

**Platform:** Pixel 6a via ADB (Mac host)

**Prerequisites:**
```bash
# 1. Confirm device connected:
adb devices   # should show "device" status

# 2. Ensure llama-perplexity binary on device:
adb shell ls /data/local/tmp/llama-perplexity
# If missing, build with Android NDK (arm64-v8a) and push:
# adb push llama-perplexity /data/local/tmp/
# adb shell chmod +x /data/local/tmp/llama-perplexity

# 3. Download WikiText-2 full corpus (run once):
python3 scripts/download_wikitext2.py
# Produces: data/wikitext2_full.txt (~1.5 MB)

# 4. Check models on device (each ~1.3–3.2 GB):
for V in Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0; do
  adb shell ls /data/local/tmp/Llama-3.2-3B-Instruct-${V}.gguf 2>/dev/null \
    && echo "  ✅ ${V}" || echo "  ❌ MISSING: ${V}"
done
# Push missing models:
# adb push local-models/llama3_2_3b_gguf/Llama-3.2-3B-Instruct-Q4_K_M.gguf /data/local/tmp/
```

**Run:**
```bash
# Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0 only (Q2_K and Q3_K_M already collected)
bash scripts/bench/pixel_wikitext_ppl.sh Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0

# Each variant takes ~60–90 min; total ~5–7 h
# Thermal note: keep device screen off, not charging, on flat surface
# Resume if interrupted:
bash scripts/bench/pixel_wikitext_ppl.sh --resume Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0
```

**Output:** `results/pixel_wikitext_ppl_<ts>/ppl_<VARIANT>.json`

**After collecting:** copy JSON files into `results/` and run:
```bash
python3 scripts/prepare_dataset.py
python3 scripts/bake_dashboard_data.py
```
The pipeline auto-selects full-corpus Pixel values over x86 values when both exist.

---

### 3. Qwen M4 GPU TPS Sweep

**Why:** Establishes Qwen 2.5 1.5B Metal baseline TPS across context lengths.
Complements existing Llama M4 Metal TPS data for cross-model comparison on GPU.

**Platform:** M4 Mac (Metal GPU)

**Prerequisites:**
```bash
# 1. Confirm llama-bench is available:
which llama-bench   # should return a path
llama-bench --version

# 2. Confirm Qwen GGUF models exist:
ls local-models/qwen2_5_1_5b_gguf/
# Expected: Qwen2.5-1.5B-Instruct-{Q2_K,Q3_K_M,Q4_K_S,Q4_K_M,Q5_K_M,Q6_K,Q8_0}.gguf
# Download if missing (run from repo root):
pip install huggingface_hub
python -c "
from huggingface_hub import hf_hub_download; import os
os.makedirs('local-models/qwen2_5_1_5b_gguf', exist_ok=True)
for v in ['Q2_K','Q3_K_M','Q4_K_S','Q4_K_M','Q5_K_M','Q6_K','Q8_0']:
    hf_hub_download('bartowski/Qwen2.5-1.5B-Instruct-GGUF',
        f'Qwen2.5-1.5B-Instruct-{v}.gguf',
        local_dir='local-models/qwen2_5_1_5b_gguf')
"
```

**Run:**
```bash
# All 7 variants, 4 context sizes, 10 trials each (~30–40 min)
bash scripts/bench/m4_qwen_tps.sh

# Subset:
bash scripts/bench/m4_qwen_tps.sh Q4_K_M Q8_0
# Resume:
bash scripts/bench/m4_qwen_tps.sh --resume
```

**Output:** `results/m4_qwen_tps_<ts>/tps_<VARIANT>.jsonl`

**After collecting:**
```bash
python3 scripts/prepare_dataset.py
python3 scripts/bake_dashboard_data.py
```

---

### 4. M4 CPU Qwen Cliff Sweep

**Why:** Characterises KV-cache cliff behaviour for Qwen 2.5 1.5B on M4 CPU
(no Metal GPU). Complements Llama M4 CPU cliff data and Qwen M4 Metal cliff data.
Expected outcome: flat or mildly degraded profile (M4 L2 >> working set for Qwen 1.5B).

**Platform:** M4 Mac (CPU only, ngl=0)

**Prerequisites:**
```bash
# Same as #3 above — llama-bench and Qwen GGUF models required
which llama-bench
ls local-models/qwen2_5_1_5b_gguf/
```

**Run:**
```bash
# All 7 variants, 13 context sizes (256–2048), 5 trials each (~2–4 h)
bash scripts/bench/m4_cpu_qwen_cliff.sh

# Subset:
bash scripts/bench/m4_cpu_qwen_cliff.sh Q2_K Q4_K_M Q8_0
# Resume:
bash scripts/bench/m4_cpu_qwen_cliff.sh --resume
```

**Output:** `results/m4_cpu_qwen_cliff_<ts>/cliff_<VARIANT>.jsonl`

**After collecting:**
```bash
python3 scripts/prepare_dataset.py
python3 scripts/bake_dashboard_data.py
```

**Thermal note:** M4 runs warm under sustained CPU load. The script includes a
60-second inter-variant cooldown. For reliable results, keep the Mac plugged in
and avoid running other CPU-intensive tasks concurrently.
