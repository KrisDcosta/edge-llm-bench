# Beyond Bit-Width: SIMD Dequantization Overhead Creates a CPU/GPU Performance Divide in GGUF K-Quant LLM Inference

**DSC 291 — Efficient AI** | UC San Diego · Halicioglu Data Science Institute

[![Dashboard](https://img.shields.io/badge/Dashboard-Live-10B981?style=flat-square)](https://krisdcosta.github.io/291_EAI/)
[![Dataset](https://img.shields.io/badge/HuggingFace-Dataset-FF6B35?style=flat-square)](https://huggingface.co/datasets/KrisDcosta/edge-llm-bench)
[![Paper](https://img.shields.io/badge/Paper-17pp%20IEEE-4F8EF7?style=flat-square)](report/report.pdf)

> **Comprehensive benchmarking study:** 7 GGUF K-quant variants (Q2_K–Q8_0) on Google Pixel 6a (Tensor G1 ARM64),
> with cross-device validation (x86 i5-1235U, Mac M4 Metal) and cross-model validation (Qwen 2.5 1.5B).
>
> **Central claim:** CPU SIMD dequantization overhead creates a CPU/GPU performance divide. On ARM NEON and x86 AVX2,
> throughput ordering is *reversed* relative to GPU (Metal): Q2_K fastest, Q6_K slowest. This is not ARM-specific —
> it is a general property of SIMD-bound CPU kernels.
>
> **Key findings:** Non-monotonic throughput (Q2_K fastest at 7.49 tok/s ≠ most accurate), Q2_K −48% KV-cache cliff
> at ctx≈512, Q3_K_M cliff-attenuated (<±11%), Q2_K HellaSwag collapse (19%), Q4_K_S Pareto-dominant (74% BoolQ),
> Q6_K Pareto-dominated, KV-cache Q8_0 eliminates cliff at cost of −46% baseline throughput, confirmed on Qwen 2.5 1.5B.
>
> **Outputs:** 4,435 individual inference measurements across ARM, x86, Metal · 6 quality benchmarks (all 7 variants) ·
> 17 figures · 17-page IEEE paper · Thermal characterization · Cross-model replication

---

## Core Results (Pixel 6a, decode phase, n=10 trials)

| Variant | TPS @ ctx=256 | TPS @ ctx=2048 | Cliff % | Cliff ctx | BoolQ | Status |
|---------|--------------|----------------|---------|-----------|-------|--------|
| Q2_K    | **7.49±0.30** | 3.69 (−48%) | **−48%** | **≈512** | 69%  | ⚠️ Speed-dominant short ctx only |
| Q3_K_M  | 4.68         | 3.62 (−11%) | −11% (attenuated) | gradual | 69%  | ✅ Best long-context stability |
| Q4_K_S  | **5.01**     | 4.47 (−10%)  | −10%   | ≈1024     | **74%** | ✅ **Accuracy-dominant Pareto** |
| Q4_K_M  | 4.78         | 5.21 (−7%)   | −7%    | ≈1024     | 72%  | ✅ **Recommended default** |
| Q5_K_M  | 3.75         | 3.61 (−46%)  | **−46%** | **≈512** | 67%  | ⚠️ Context-sensitive (same cliff as Q2_K) |
| Q6_K    | 3.53         | 3.17 (−11%)  | −11%   | ≈1024     | 65%  | ⚠️ Slower AND less accurate than Q4_K_M |
| Q8_0    | 4.52         | 3.71 (−18%)  | −18%   | ≈768      | 68%  | ⚠️ Significant ctx degradation |

*TPS values from `results/pixel_llama_tps_20260325_120022/` (n=10) and cliff from `results/pixel_llama_cliff_filled_canonical_n10/` (n=10)*
*imatrix: max +4% BoolQ (Q6_K); hurts Q2_K (−5%) and Q3_K_M (−8%) — calibration fails below critical bitwidth*
*† Q2_K HellaSwag: 19% — instruction-following collapse; all responses "No"; not a true accuracy score*

---

## Cross-Platform Throughput (ctx=256, decode)

| Variant | Pixel 6a ARM | x86 i5-1235U | Mac M4 Metal |
|---------|-------------|--------------|--------------|
| Q2_K    | **7.49** (fastest) | **14.05** (fastest) | 17.79 |
| Q3_K_M  | 4.68        | 8.38        | 15.60 |
| Q4_K_S  | **5.01**    | 8.93        | **19.88** (fastest) |
| Q4_K_M  | 4.78        | 8.55        | 19.22 |
| Q5_K_M  | 3.75        | 7.31        | 13.35 |
| Q6_K    | 3.53 (slowest) | **6.80** (slowest) | 7.02 |
| Q8_0    | 4.52        | 7.43        | 6.39 (slowest) |

**CPU ordering (ARM=x86):** Q2_K fastest → Q6_K slowest — SIMD kernel bottleneck, not model arithmetic
**GPU ordering (Metal reversed):** Q4_K_S ≈ Q4_K_M fastest → Q8_0 slowest — dedicated 4-bit dispatch paths

---

## KV-Cache Q8_0 Mitigation (`-ctk q8_0 -ctv q8_0`)

| Variant | ctx | Default TPS | Q8_0 KV TPS | Change |
|---------|-----|------------|------------|--------|
| Q2_K    | 256  | 7.49 | 4.49 | −40% baseline |
| Q2_K    | 512  | 5.58 | 4.48 | **cliff eliminated** |
| Q2_K    | 2048 | 4.33 | 4.37 | −2.6% (vs −48% default) |
| Q3_K_M  | 2048 | 5.04 | 3.78 | −25% (overkill — already stable) |
| Q4_K_M  | 2048 | 4.25 | 3.56 | −16% |

*Crossover benefit at ctx≈1400: Q8_0 KV wins for long-context deployments despite lower short-ctx throughput*

---

## Key Novelties

1. **Non-monotonic throughput ordering (CPU-general)**
   - Q2_K fastest (7.49 t/s ARM, 14.05 t/s x86) despite only 3.40 bits/weight
   - Q6_K slowest (3.53 t/s ARM, 6.80 t/s x86) despite 6.59 bits/weight
   - x86 AVX2 replicates ARM NEON ordering exactly → confirms SIMD kernel bottleneck, not ARM-specific
   - **Root cause:** Q6_K dequantization requires 6-operand split-bit shuffle (ql[128]+qh[64]); Q2_K uses simple 16-entry table lookup

2. **KV-cache cliff at predicted threshold**
   - Q2_K: −48% from ctx=256→2048, cliff onset at ctx≈512 (ARM, n=10, filled-context methodology)
   - x86 Q2_K: −51% cliff at ctx≈1200–1300 (matches `L2_cache/KV_dim = 1.25MB/~1KB ≈ 1280`)
   - Q3_K_M: <±11% across all contexts — cliff-attenuated (higher FFN compute partially masks KV pressure)
   - **Formula:** `cliff_ctx ≈ L2_cache / (2 × n_layers × n_kv_heads × head_dim × 2B)`
   - Metal: flat ±4.3% or better ctx=1024–2048, zero cliff — GPU DRAM bandwidth sufficient; KV-cache fits fast HBM

3. **Cross-model replication (Qwen 2.5 1.5B)**
   - Non-monotonic ordering confirmed: Q2_K 16.1 t/s fastest, Q6_K slowest on Pixel 6a
   - ctx=512 cliff confirmed on Qwen (C_layer = 1024×ctx bytes, same L2 formula)
   - Proves findings are not Llama-specific — generalize across GGUF K-quant models

4. **Non-monotonic quality ordering**
   - Q4_K_S (74% BoolQ) beats Q4_K_M (72%), Q6_K (65%), and Q8_0 (68%)
   - Q6_K is Pareto-dominated: slower than Q4_K_M (3.55 vs 4.57 t/s) AND less accurate (65% vs 72%)
   - **Root cause:** Superblock K-quant structure captures statistical outliers; Q4_K_S block structure outperforms naive Q6_K

5. **Q2_K instruction-following collapse**
   - Q2_K scores 19% on HellaSwag vs 39–45% for all other variants
   - All Q2_K responses collapsed to "No" — not low accuracy, complete format failure
   - **Finding:** 3.40 bpw is below a critical threshold for instruction following on sentence-completion tasks

6. **KV-cache Q8_0 as cliff mitigation**
   - `-ctk q8_0 -ctv q8_0` eliminates Q2_K cliff entirely (−48% → −2.6%)
   - Cost: −46% baseline throughput at ctx=256
   - Crossover benefit at ctx≈1400: recommended for long-context deployments

7. **Thermal throttling characterization (Tensor G1)**
   - Baseline: 7.49±0.30 t/s; throttle onset within ~60s of sustained load
   - Throttle plateau: 4.72–4.96 t/s (~43% reduction)
   - Recovery: 7.04±0.29 t/s after 140s cooldown (85% of baseline)

---

## Paper & Documentation

| Document | Status | Location | Notes |
|----------|--------|----------|-------|
| **IEEE Paper** | ✅ Complete | `report/report.pdf` | 17 pages; all findings, 0 LaTeX errors |
| **Conference Roadmap** | ✅ Updated | `PAPER_ROADMAP.md` | Submission plan MLSys/MobiSys/ATC |
| **Canonical Results** | ✅ Updated | `results/CANONICAL.md` | Maps every table/figure to source data |
| **Interactive Dashboard** | ✅ Live | [krisdcosta.github.io/291_EAI](https://krisdcosta.github.io/291_EAI/) | Chart.js · GitHub Pages |
| **HuggingFace Dataset** | ✅ Published | [KrisDcosta/edge-llm-bench](https://huggingface.co/datasets/KrisDcosta/edge-llm-bench) | 4,400+ records · 5 splits |

---

## Reproducing Results

### Prerequisites
- **Primary device:** Google Pixel 6a (or similar ARM64, 6GB+ RAM, Android 13+)
- **Cross-device:** Mac with M4 or M-series chip (for Metal runs), x86 Linux/Windows (for AVX2 runs)
- **Binaries:** NDK r29.0.14206865, Homebrew cmake/ninja, Java 21
- **Storage:** ~10 GB for canonical model set; ~40 GB for all models + results

### Pixel 6a — Primary Benchmarks
```bash
# Install dependencies
pip install -r requirements.txt

# Push models to device (models must already be downloaded to local-models/)
adb push local-models/llama3_2_3b_gguf/Llama-3.2-3B-Instruct-Q4_K_M.gguf /data/local/tmp/

# TPS sweep (all 7 variants, 4 context sizes, n=10)
bash scripts/bench/pixel_llama_tps.sh

# KV-cache cliff sweep — filled-context methodology (n=10)
bash scripts/bench/pixel_llama_cliff_filled.sh

# Quality evaluation (7 benchmarks × 7 variants)
python scripts/eval/quality_eval.py --all

# Qwen cross-model validation
bash scripts/bench/pixel_qwen_tps.sh
bash scripts/bench/pixel_qwen_cliff_filled.sh
```

### Mac M4 (Metal GPU backend)
```bash
# TPS sweep via llama-bench
bash scripts/bench/m4_llama_tps.sh

# Cliff sweep (filled-context, Metal — no cliff expected)
bash scripts/bench/m4_llama_cliff.sh

# Quality evaluation (Mac-native)
python scripts/eval/mac_gsm8k_eval.py     # NOTE: see Known Limitations
python scripts/eval/mac_humaneval_eval.py
```

### x86 (AVX2 CPU backend)
```bash
bash scripts/bench/x86_llama_tps.sh
bash scripts/bench/x86_llama_cliff.sh
bash scripts/bench/x86_qwen_tps.sh      # Qwen 2.5 1.5B cross-model validation
python scripts/eval/x86_quality_eval.py
```

### Generate Figures
```bash
python scripts/analyze/plot_cliff_crossplat.py      # 3-panel cliff figure (ARM + x86 + Metal)
python scripts/analyze/generate_figures.py results/ # All 17 paper figures
```

### Building Android App
```bash
cd android
# Requires: JDK 21, NDK 29.0.14206865, Homebrew cmake + ninja
# Add to android/local.properties: cmake.dir=/opt/homebrew/Cellar/cmake/4.2.3
JAVA_HOME=$(/usr/libexec/java_home -v 21) ./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

---

## Project Structure

```
291_EAI/
├── README.md                              # This file
├── PAPER_ROADMAP.md                       # Conference submission roadmap (MLSys/MobiSys/ATC)
├── VERIFIED_METRICS_MASTER_TABLE.md       # Ground-truth reference for all paper claims
│
├── report/
│   ├── report.tex                         # IEEE paper (LaTeX, 17 pages)
│   ├── report.pdf                         # Compiled 17-page paper ✅
│   └── *.aux, *.log                       # LaTeX build artifacts (.gitignored)
│
├── data/
│   ├── wikitext2_full.txt                 # WikiText-2 test corpus (~285K tokens)
│   ├── boolq_100.yaml                     # BoolQ (100 yes/no Q&A)
│   ├── arc_easy_100.yaml                  # ARC-Easy (100 4-choice)
│   ├── arc_challenge_100.yaml             # ARC-Challenge (100 4-choice)
│   ├── hellaswag_100.yaml                 # HellaSwag (100 sentence completion)
│   ├── mmlu_100.yaml                      # MMLU (100 Q, 5/subject × 20)
│   ├── truthfulqa_100.yaml                # TruthfulQA (100 MC1)
│   ├── humaneval_50.jsonl                 # HumanEval (50 coding tasks)
│   ├── gsm8k_test.jsonl                   # GSM8K math (50 problems)
│   └── imatrix_*.dat                      # imatrix calibration files (5 variants)
│
├── figures/
│   ├── fig1_prefill_tps_vs_context.png    # Prefill TPS vs context (7 variants, Pixel)
│   ├── fig2_decode_tps_vs_context.png     # Decode TPS vs context (7 variants, Pixel)
│   ├── fig3_ttft_vs_context.png           # Time-to-first-token vs context
│   ├── fig4_peak_memory_vs_quant.png      # Peak working memory by quantization
│   ├── fig5_battery_per_1k_tokens.png     # Energy cost per 1K tokens
│   ├── fig6_pareto_efficiency_quality.png # BoolQ accuracy vs decode TPS (Pareto)
│   ├── fig7_prefill_vs_decode_fraction.png # Prefill/decode time decomposition
│   ├── fig8_latency_distribution.png      # TPS distribution across trials
│   ├── fig9_model_size_vs_decode_tps.png  # Model size vs decode throughput
│   ├── fig_kv_cliff.png                   # KV-cache cliff (ARM, all 7 variants, n=10)
│   ├── fig_cliff_crossplat.png            # ARM + Metal 2-panel cliff (old)
│   ├── fig_cliff_crossplat_sel.png        # ARM + Metal selected variants 2-panel
│   ├── fig_cliff_3plat_sel.png            # ARM + x86 + Metal 3-panel (CURRENT paper fig)
│   ├── fig_ppl_vs_accuracy.png            # PPL × accuracy scatter
│   └── fig_xplat_quality_4bench.png       # Cross-platform quality 4-benchmark heatmap
│
├── results/
│   ├── CANONICAL.md                       # Maps every paper claim to source directory
│   ├── quality_scores.json                # All quality scores (ARM, x86, cross-device)
│   ├── pixel_llama_tps_20260325_120022/   # Pixel TPS sweep (n=10) ← Table 1
│   ├── pixel_llama_cliff_filled_canonical_n10/  # ARM cliff n=10 ← Table 2 (canonical)
│   ├── pixel_llama_cliff_filled_20260326_132101/  # ARM cliff n=3 (superseded but cited)
│   ├── pixel_qwen_tps_20260326_033619/    # Qwen TPS (non-monotonic replication)
│   ├── pixel_qwen_cliff_filled_20260330_235410/  # Qwen cliff (ctx=512 cliff confirmed)
│   ├── pixel_6a_ppl_final/                # Full WikiText-2 PPL (Q2_K, Q3_K_M)
│   ├── pixel_power_20260320_173728/       # Battery measurement (fig5)
│   ├── m4_llama_tps_20260326_001546/      # M4 Metal TPS sweep
│   ├── m4_metal_cliff_20260323_015934/    # M4 Metal cliff (flat ±2%, no cliff)
│   ├── x86_llama_cliff_20260329_002333/   # x86 cliff (Q2_K −51% at ctx=2048)
│   ├── x86_tps_results.json              # x86 TPS (Q2_K 14.05, Q6_K 6.80)
│   ├── x86_perplexity_results.json       # x86 PPL (Q2_K 11.73, Q8_0 9.71)
│   └── mac_humaneval_*/                   # Mac HumanEval eval (methodology note: see Limitations)
│
├── scripts/
│   ├── bench/
│   │   ├── pixel_llama_tps.sh             # Pixel TPS sweep (llama.cpp ARM)
│   │   ├── pixel_llama_cliff_filled.sh    # Pixel cliff sweep (filled-context)
│   │   ├── pixel_qwen_cliff_filled.sh     # Qwen cliff sweep (bash 3.2 compatible)
│   │   ├── pixel_gsm8k.sh                 # GSM8K on Pixel
│   │   ├── m4_llama_tps.sh                # M4 Metal TPS sweep
│   │   ├── m4_llama_cliff.sh              # M4 Metal cliff sweep
│   │   ├── x86_llama_cliff.py             # x86 Llama cliff sweep (filled-context)
│   │   ├── x86_qwen_tps.sh                # x86 Qwen 2.5 1.5B TPS reference
│   │   └── x86_qwen_cliff.py              # x86 Qwen cliff sweep (filled-context)
│   ├── eval/
│   │   ├── quality_eval.py                # Pixel quality eval (7 benchmarks)
│   │   ├── mac_gsm8k_eval.py              # Mac GSM8K eval (see Limitations)
│   │   └── mac_humaneval_eval.py          # Mac HumanEval eval
│   ├── analyze/
│   │   ├── plot_cliff_crossplat.py        # 3-panel cliff figure generator
│   │   ├── generate_figures.py            # All 17 paper figures
│   │   ├── generate_tables.py             # LaTeX table generator
│   │   └── plot_ppl_vs_accuracy.py        # PPL × accuracy scatter
│   └── legacy/                            # Archived orchestration scripts (superseded by bench/)
│
├── android/                               # Android app (Jetpack Compose + NDK)
│   ├── app/src/main/java/com/eai/...
│   │   ├── ui/chat/ChatScreen.kt          # Streaming inference chat UI
│   │   ├── ui/models/ModelManager*.kt     # Model selection & management
│   │   ├── ui/benchmark/BenchmarkScreen.kt
│   │   ├── ui/settings/SettingsScreen.kt
│   │   ├── inference/InferenceEngine.kt   # llama.cpp JNI wrapper
│   │   └── data/...                       # Room DB + repositories
│   ├── CMakeLists.txt
│   └── build.gradle
│
├── experiments/
│   └── registry.yaml                      # 66 experiment configs
│
├── local-models/                          # GGUF files (not in git)
│   ├── llama3_2_3b_gguf/
│   │   ├── Llama-3.2-3B-Instruct-Q2_K.gguf    (1.3 GB)
│   │   ├── Llama-3.2-3B-Instruct-Q3_K_M.gguf  (1.6 GB)
│   │   ├── Llama-3.2-3B-Instruct-Q4_K_S.gguf  (1.8 GB)
│   │   ├── Llama-3.2-3B-Instruct-Q4_K_M.gguf  (1.9 GB)
│   │   ├── Llama-3.2-3B-Instruct-Q5_K_M.gguf  (2.2 GB)
│   │   ├── Llama-3.2-3B-Instruct-Q6_K.gguf    (2.5 GB)
│   │   └── Llama-3.2-3B-Instruct-Q8_0.gguf    (3.2 GB)
│   └── qwen2_5_1_5b_gguf/
│       └── Qwen2.5-1.5B-Instruct-*.gguf       (Q2_K–Q8_0)
│
├── archive/                               # Superseded experiments (not cited)
│   ├── broken_evals/                      # GSM8K chat-format methodology failure
│   └── old-results/                       # Pre-canonical runs
│
├── notebooks/
│   └── gpu_baseline.ipynb                 # GPU comparison (Colab)
│
└── .gitignore                             # Excludes: models, build artifacts
```

---

## Quantization Variants (7 Total)

| Variant | Bits/Weight | File Size | NEON Op | Superblock | Notes |
|---------|-------------|-----------|---------|-----------|-------|
| Q2_K    | 3.40        | 1.3 GB    | 16-entry table lookup | 6×8 | Fastest CPU; cliff at ctx≈512 (−48%); HellaSwag collapse |
| Q3_K_M  | 3.95        | 1.6 GB    | 32-entry table lookup | 6×8 | Cliff-attenuated (<±11%); imatrix hurts (−8% BoolQ) |
| Q4_K_S  | 4.85        | 1.8 GB    | 16-entry × 2 | 8×8 | **Pareto-dominant** (74% BoolQ, 5.01 t/s) |
| Q4_K_M  | 5.30        | 1.9 GB    | 16-entry × 2 | 8×8 | **Recommended default** (72% BoolQ, 4.78 t/s) |
| Q5_K_M  | 6.21        | 2.2 GB    | 32-entry × 2 | 8×8 | Best MMLU (50%); −46% cliff at ctx≈512 |
| Q6_K    | 6.59        | 2.5 GB    | Split-bit shuffle (ql+qh) | 8×8 | **Pareto-dominated**: slower AND less accurate than Q4_K_M |
| Q8_0    | 8.53        | 3.2 GB    | Direct load | 32×1 | No dequant overhead; slowest on M4 Metal (6.39 t/s) |

---

## Quality Results (Pixel 6a, all 7 variants)

| Variant | BoolQ | ARC-Easy | ARC-Challenge | HellaSwag | MMLU | TruthfulQA | PPL (WikiText-2) |
|---------|-------|----------|---------------|-----------|------|------------|-----------------|
| Q2_K    | 69%   | 76%      | 50%           | 19%†      | 42%  | 50%        | 13.29 |
| Q3_K_M  | 69%   | 78%      | 52%           | 44%       | 48%  | **68%**    | 11.08 |
| Q4_K_S  | **74%** | 81%   | **62%**       | 39%       | 49%  | 57%        | 10.70‡ |
| Q4_K_M  | 72%   | **82%**  | 60%           | 43%       | 47%  | 60%        | 10.71‡ |
| Q5_K_M  | 67%   | 81%      | 61%           | **45%**   | **50%** | 65%     | 10.62‡ |
| Q6_K    | 65%   | 79%      | 58%           | 41%       | 48%  | 60%        | 10.58‡ |
| Q8_0    | 68%   | 80%      | 56%           | 43%       | 47%  | 58%        | 10.59‡ |

† Q2_K HellaSwag: instruction-following collapse — all responses "No"; not a true accuracy score.
‡ PPL for Q4_K_S through Q8_0 measured on full WikiText-2 corpus (~290K tokens) on x86; Q2_K and Q3_K_M measured on Pixel 6a.

---

## Experiment Status

### Primary Device (Pixel 6a, Tensor G1 ARM64)

| Experiment | Status | Trials | Source |
|-----------|--------|--------|--------|
| TPS sweep (7 variants, 4 ctx sizes) | ✅ Complete | n=10 | `pixel_llama_tps_20260325_120022/` |
| KV-cache cliff, Llama 3.2 3B (7 variants, 11 ctx, filled) | ✅ Complete | n=10 | `pixel_llama_cliff_filled_canonical_n10/` |
| KV-cache cliff, Qwen 2.5 1.5B (7 variants, 11 ctx, filled) | ✅ Complete | n=5 | `pixel_qwen_cliff_filled_20260330_235410/` |
| Qwen 2.5 1.5B TPS sweep | ✅ Complete | — | `pixel_qwen_tps_20260326_033619/` |
| BoolQ accuracy (100q) | ✅ Complete | — | `quality_scores.json` |
| ARC-Easy accuracy (100q) | ✅ Complete | — | `quality_scores.json` |
| ARC-Challenge accuracy (100q) | ✅ Complete | — | `quality_scores.json` |
| HellaSwag accuracy (100q) | ✅ Complete | — | `quality_scores.json` |
| MMLU accuracy (100q) | ✅ Complete | — | `quality_scores.json` |
| TruthfulQA accuracy (100q) | ✅ Complete | — | `quality_scores.json` |
| WikiText-2 PPL (full corpus, ~290K tokens) | ✅ All 7 variants | — | `pixel_6a_ppl_final/` (Q2_K, Q3_K_M); `x86_perplexity_results.json` (Q4_K_S–Q8_0) |
| imatrix calibration (5 variants, BoolQ) | ✅ Complete | — | `quality_scores.json` |
| KV-cache Q8_0 mitigation | ✅ Complete | n=5 | `quality_scores.json` |
| Battery/power measurement | ✅ Complete | — | `pixel_power_20260320_173728/` |
| Flash Attention (FA not supported on Tensor G1) | ✅ Documented | — | `-fa` flag: unsupported |
| Thermal drift characterization | ✅ Complete | — | Measured: baseline 8.33±0.42, throttle 4.72–4.96, recovery 7.04±0.29 t/s |
| GSM8K (50q) | ⚠️ Methodology broken | — | Chat-template incompatibility (see Limitations) |

### Cross-Device

| Device | Status | Key Result | Source |
|--------|--------|-----------|--------|
| x86 Intel i5-1235U (AVX2) | ✅ Complete | Q2_K fastest (14.05), Q6_K slowest (6.80); cliff Q2_K −51% at ctx=2048 | `x86_tps_results.json`, `x86_llama_cliff_20260329_002333/` |
| Mac M4 Metal GPU | ✅ Complete | Q4_K_S fastest (19.88), Q8_0 slowest (6.39); flat cliff ≤±4.3% all variants (no degradation) | `m4_llama_tps_20260326_001546/`, `m4_metal_cliff_20260323_015934/` |
| x86 Quality (6 benchmarks) | ✅ Complete | Consistent with ARM ordering | `quality_scores.json` keys `x86_*` |
| x86 PPL | ✅ Complete | Q2_K 11.73, Q8_0 9.71 | `x86_perplexity_results.json` |

---

## Known Issues & Limitations

| Issue | Status | Notes |
|-------|--------|-------|
| **Flash Attention not supported on Tensor G1** | ✅ Documented | llama.cpp `-fa` flag returns "unsupported backend"; Tensor G1 lacks HW FA support |
| **GSM8K/HumanEval methodology broken** | ⚠️ Archived | Mac `--single-turn` with few-shot prompt → chat template wraps entire prompt as user turn; model echoes few-shot context; results near-zero accuracy; archived in `archive/broken_evals/`; not a blocker (optional eval) |
| **P-core affinity mask bug** | ✅ Documented | `--cpu-mask 0x0F` targets little cores (cpu0–3, 1803 MHz), NOT P-cores. Tensor G1 layout: cpu0-3=little, cpu4-5=medium (2253 MHz), cpu6-7=P-cores (2802 MHz). Correct mask: `0xC0` (P-only) or `0xF0` (P+M). P-core affinity data is invalid — not cited in paper |
| **WikiText-2 PPL cross-device** | ✅ Complete | Q2_K, Q3_K_M on Pixel full corpus; Q4_K_S–Q8_0 on x86 full corpus (~290K tokens). All values shown in Quality Results table. |
| **Q2_K HellaSwag collapse** | ✅ Documented | 19% score is instruction-following failure, not accuracy; all responses "No"; documented as regime failure in paper |
| **imatrix hurts at low bpw** | ✅ Documented | Q2_K (−5%), Q3_K_M (−8%) BoolQ; paper recommends imatrix only at ≥4 bpw |
| **Thermal throttling on sustained load** | ✅ Characterized | Onset ~60s; plateau 4.72–4.96 t/s (−43%); 5-min cooldown protocol mitigates in benchmarks |
| **F16 model unusable on Pixel** | ✅ Documented | 0.13 tok/s (>95% timeout); 6.4 GB exceeds 6GB device memory |

---

## Hardware Specifications

### Pixel 6a (Primary Device)

| Property | Value |
|----------|-------|
| SoC | Google Tensor G1 |
| CPU cores | 2× Cortex-X1 @ 2.80 GHz (P-cores, cpu6–7) + 2× A76 @ 2.25 GHz (M-cores, cpu4–5) + 4× A55 @ 1.80 GHz (E-cores, cpu0–3) |
| RAM | 6 GB LPDDR5 (~50 GB/s bandwidth) |
| L2 cache | ~512 KB (per cluster) |
| OS | Android 13–16 |
| llama.cpp | ARM64 NEON, NDK r29, 4 threads |

### Cross-Device

| Device | CPU | RAM | L2/L3 Cache | Backend | TPS range |
|--------|-----|-----|-------------|---------|-----------|
| Mac M4 (MacBook Air) | ARM64 M4, 8-core | 16 GB | 16 MB L2 | Metal GPU (16-core) | 6.4–19.9 t/s |
| HP Pavilion (x86) | Intel i5-1235U, 12th Gen | 16 GB | 1.25 MB L2 per P-core | AVX2 CPU, 6 threads | 6.8–14.1 t/s |

---

## Methodology

- **Filled-context methodology:** Prompts sized N-64 tokens to saturate KV cache at each context level (not just allocate)
- **Statistical rigor:** n=10 trials per config; Wilson 95% CI for accuracy; outlier detection via IQR
- **Thermal controls:** 5-minute cooldown between variants; T < 32°C pre-run; runs >±15% of median rejected
- **Schema validation:** All JSONL records validated against `schemas/run.schema.json`
- **Reproducibility:** Experiment registry (YAML), raw logs (JSONL), code (Python/Bash), spot-check re-runs

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full pipeline walkthrough and instructions on adding new devices, models, or benchmarks.

---

## Citation

```bibtex
@misc{291EAI2026,
  title  = {Beyond Bit-Width: SIMD Dequantization Overhead Creates a CPU/GPU Performance Divide in GGUF K-Quant LLM Inference},
  author = {Costa, Krisdonia},
  year   = {2026},
  url    = {https://github.com/krisdcosta/291_EAI}
}
```

---

## License

Research project for DSC 291 (Efficient AI). Contact author for usage permissions.

---

**Last Updated:** April 11, 2026 | **Paper:** 17 pages, 0 LaTeX errors | **Status:** All primary experiments complete; paper final draft ready; targeting MLSys 2026 / MobiSys 2027
