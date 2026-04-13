---
license: cc-by-4.0
language:
  - en
tags:
  - llm-inference
  - quantization
  - edge-ai
  - mobile
  - benchmarking
  - llama
  - qwen
  - gguf
  - arm
  - on-device
pretty_name: Edge LLM Bench — GGUF Quantization on Edge Devices
size_categories:
  - 1K<n<10K
task_categories:
  - text-generation
configs:
  - config_name: pixel_inference
    data_files: pixel_inference.parquet
  - config_name: m4_inference
    data_files: m4_inference.parquet
  - config_name: x86_inference
    data_files: x86_inference.parquet
  - config_name: quality_benchmarks
    data_files: quality_benchmarks.parquet
  - config_name: perplexity
    data_files: perplexity.parquet
---

# Edge LLM Bench — GGUF Quantization Benchmarks on Edge Devices

Controlled inference benchmark dataset for **7 GGUF K-quant quantization variants**
(Q2\_K through Q8\_0) of **Llama 3.2 3B Instruct** and **Qwen 2.5 1.5B Instruct** across three hardware platforms:

| Device | SoC / CPU | RAM | Backend |
|---|---|---|---|
| Google Pixel 6a | Google Tensor G1 (ARM Cortex-X1) | 6 GB LPDDR5 | llama.cpp CPU |
| Apple M4 Mac | Apple M4 (ARM, 10-core) | 16 GB unified | llama.cpp Metal |
| HP Pavilion x86 | Intel Core i5-1235U (12th gen) | 16 GB DDR4 | llama.cpp CPU |

**4,062 total records** across 5 splits. All inference records are non-warmup,
success-status runs collected under controlled thermal conditions. Contaminated
and failed records are archived separately and not included here.

---

## Key Findings (from the accompanying paper)

- **Non-monotonic throughput on ARM:** Q2\_K is ~99% faster than Q6\_K on Pixel 6a
  (ctx=256 cliff\_sweep filled-context, n=10) despite having less than half the bits per weight —
  contradicting GPU-derived assumptions. Q4\_K\_M and Q5\_K\_M cliff-sweep ctx=256 baselines
  are affected by a thermal warmup burst; use standard\_sweep values for those two variants.
- **KV-cache collapse threshold:** Q2\_K suffers a −48% throughput cliff beyond ~512 tokens
  on Pixel 6a (ARM); Q3\_K\_M is cliff-attenuated (≤11%, not fully immune); x86 cliff predicted
  at ctx≈1,280 tokens via L2-cache formula, observed at 1,300–1,400 (within 8%)
- **Non-monotonic quality:** Q4\_K\_S outperforms Q8\_0 on BoolQ (74% vs 68%) despite
  fewer bits — superblock K-quant structure allocates precision more effectively than naive
  int8; Q6\_K is Pareto-dominated (slower AND less accurate than Q4\_K\_M)
- **imatrix calibration hurts low-bitwidth models:** imatrix degrades Q2\_K by −4pp and
  Q3\_K\_M by −7pp on BoolQ; modest improvement for Q6\_K (+4pp). Do not use imatrix for
  variants below Q4\_K\_S
- **Cross-device consistency:** Non-monotonic CPU throughput ordering (Q2\_K fastest,
  Q6\_K slowest) confirmed on both ARM NEON and x86 AVX2; ordering reverses on Metal GPU
  where Q4\_K\_S/Q4\_K\_M are fastest and Q8\_0 is slowest

---

## Splits

### `pixel_inference` — 2,490 rows
Pixel 6a (ARM, CPU backend) inference runs.

| Column | Type | Description |
|---|---|---|
| `device` | string | `"Pixel6a"` |
| `backend` | string | `"CPU"` |
| `model` | string | Model name |
| `variant` | string | GGUF quantization variant (Q2\_K … Q8\_0) |
| `context_len` | int | Prompt context window in tokens |
| `trial` | int | Trial index within the experiment |
| `threads` | int | CPU thread count (null = default 4) |
| `decode_tps` | float | Decode throughput (tokens/second) |
| `prefill_tps` | float | Prefill throughput (tokens/second) |
| `ttft_s` | float | Time to first token (seconds) — populated for standard_sweep only |
| `e2e_s` | float | End-to-end latency (seconds) — populated for standard_sweep only |
| `n_output_tokens` | int | Number of generated tokens |
| `experiment_type` | string | `cliff_sweep` \| `standard_sweep` \| `thread_sweep` \| `kv_cache_quant` |
| `kv_quant` | string | KV cache quantization type (`null` = default, `"q8_0"` = quantized) |
| `ngl` | int | GPU layers (null for CPU runs) |
| `ts` | string | ISO-8601 timestamp |
| `source_file` | string | Originating filename |

**experiment_type values:**
- `cliff_sweep` — context length varied to characterise KV-cache collapse (canonical n=10)
- `standard_sweep` — fixed 4 context windows (256/512/1024/2048), 13 trials, 2 warmup
- `thread_sweep` — Q4\_K\_M at threads=1/2/4/8, ctx=256, 15 trials
- `kv_cache_quant` — KV cache set to q8\_0 to test collapse mitigation

---

### `m4_inference` — 1,021 rows
Apple M4 Mac inference runs. Contains two backend configurations:

- **Metal GPU** (931 rows) — `backend = "Metal"`, `ngl = 99`. Includes Llama 3.2 3B and Qwen 2.5 1.5B.
  Cliff sweep covers ctx=1024–2048 (13 points, n=5 trials). Results: flat profile on Metal
  (all variants within ±9%), confirming no KV-cache cliff on GPU-accelerated inference.
- **CPU** (90 rows) — `backend = "CPU"`, `ngl = 0`, `threads = 4`. Llama 3.2 3B only.
  - **Cliff sweep** (88 rows): ctx=256–2048 (13 points, pre-aggregated n\_trials=5 per ctx).
    Collected 2026-04-09. 3 outlier points excluded (Q5\_K\_M ctx=2048 OOM, Q6\_K ctx=1536
    CV=81%, Q8\_0 ctx=2048 CV=99%). Results: significant context-dependent degradation
    on M4 CPU (Q2\_K −13%, Q3\_K\_M −54%, Q4\_K\_S −53%, Q6\_K −60% from ctx=256→2048).
    Note: ctx=256 cliff baseline may be inflated by CPU boost state at start of each variant's sweep.
  - **TPS sweep** (7 rows, `experiment_type = "standard_sweep"`, `context_len = 0`): pure decode
    reference (n\_prompt=0, n\_gen=128, n=10 trials, 2026-04-06). Thermally settled baseline.
    Throughput ordering: Q4\_K\_S (13.16) > Q8\_0 (12.60) > Q4\_K\_M (12.51) > Q2\_K (12.31)
    > Q3\_K\_M (11.48) > Q5\_K\_M (10.59) > Q6\_K (9.29) tok/s. Non-monotonic: Metal reversal
    (Q4\_K\_S fastest) confirmed on M4 CPU as well; Q6\_K remains slowest.

Same columns as `pixel_inference`.

---

### `x86_inference` — 399 rows
Intel Core i5-1235U (x86, AVX2, CPU backend), Windows 11. Contains three experiment types:

- **`standard_sweep` — Llama 3.2 3B** (7 rows) — one reference run per variant at ctx=256, 6 threads
- **`standard_sweep` — Qwen 2.5 1.5B** (7 rows) — one reference run per variant at ctx=256, 6 threads;
  cross-model validation that non-monotonic CPU throughput ordering (Q2\_K fastest, Q6\_K slowest) holds on x86
- **`cliff_sweep`** (385 rows) — n=5 trials per variant across 11 context lengths (256–2,048)
  using filled-context methodology (Llama 3.2 3B only); collected 2026-04-08 to characterise the x86 KV-cache cliff

The cliff sweep enables x86 KV-cache collapse characterisation. Predicted cliff at ctx≈1,280
tokens (from L2-cache formula); observed at 1,300–1,400 tokens (within 8%).

Same columns as `pixel_inference`. `backend = "CPU"`, `threads = 6`.

> **Note:** x86 cliff sweep and quality evaluation cover Llama 3.2 3B only. Qwen 2.5 1.5B on x86
> is limited to `standard_sweep` (ctx=256 decode reference). No Qwen cliff or quality data for x86.

---

### `quality_benchmarks` — 138 rows
Accuracy scores on 6 NLP benchmarks for 7 quantization variants across Pixel 6a and x86 i5-1235U,
including both standard and imatrix-calibrated variants.

| Column | Type | Description |
|---|---|---|
| `benchmark` | string | `arc_challenge` \| `arc_easy` \| `boolq` \| `hellaswag` \| `mmlu` \| `truthfulqa` |
| `variant` | string | GGUF quantization variant |
| `device` | string | `"Pixel6a"` or `"x86"` |
| `model` | string | Model name |
| `calibration` | string | `"standard"` or `"imatrix"` (importance-weighted) |
| `accuracy_pct` | float | Accuracy percentage (0–100) |
| `correct` | int | Correct answers |
| `total` | int | Total questions evaluated |
| `status` | string | `"success"` for all included rows |

**Device coverage:**
- `Pixel6a`: all 6 benchmarks × 7 variants (standard); imatrix calibration for 5 benchmarks × all 7 variants (ARC-Easy excluded — known parser artifact producing 100% for all variants)
- `x86`: all 6 benchmarks × 7 variants (standard only; no imatrix)

**Benchmark sample sizes:** 100 questions each (random sample from official test sets).
BoolQ imatrix calibration covers all 7 variants. TruthfulQA imatrix data collected for
all 7 variants.

---

### `perplexity` — 14 rows
WikiText-2 perplexity scores for Llama 3.2 3B Instruct. Covers both Pixel 6a and x86 i5-1235U measurements.

| Column | Type | Description |
|---|---|---|
| `variant` | string | GGUF quantization variant |
| `model` | string | Model name |
| `device` | string | `"Pixel6a"` or `"x86"` |
| `perplexity` | float | WikiText-2 perplexity (lower = better) |
| `perplexity_status` | string | `"success"` or `"not_evaluated"` |
| `corpus` | string | `"wikitext2_full"` (~290K tokens) or `"wikitext2_sample"` (~12K tokens) |
| `tokens_approx` | int | Approximate token count used |
| `note` | string | Measurement notes |

> **All 7 variants have full-corpus PPL values.** Q2\_K and Q3\_K\_M measured on Pixel 6a (full corpus, ~285K tokens).
> Q4\_K\_S, Q4\_K\_M, Q5\_K\_M, Q6\_K, Q8\_0 measured on x86 i5-1235U (full corpus, ~290K tokens).
> Pixel 6a also has sample-corpus (~12K tokens) measurements for Q4\_K\_M, Q6\_K, Q8\_0 (retained for reference).

---

## How to Load

```python
from datasets import load_dataset

# Pixel 6a inference runs
pixel = load_dataset("KrisDcosta/edge-llm-bench", "pixel_inference", split="train")

# M4 Mac inference runs
m4 = load_dataset("KrisDcosta/edge-llm-bench", "m4_inference", split="train")

# Quality benchmarks
quality = load_dataset("KrisDcosta/edge-llm-bench", "quality_benchmarks", split="train")

# Perplexity scores
ppl = load_dataset("KrisDcosta/edge-llm-bench", "perplexity", split="train")
```

### Quick analysis examples

```python
import pandas as pd
from datasets import load_dataset

# Load as pandas
df = load_dataset("KrisDcosta/edge-llm-bench", "pixel_inference", split="train").to_pandas()

# Mean decode TPS per variant on Pixel 6a (cliff sweep only)
cliff = df[df["experiment_type"] == "cliff_sweep"]
print(cliff.groupby("variant")["decode_tps"].mean().sort_values(ascending=False))

# KV-cache collapse: TPS at ctx=512 vs ctx=2048
stable = cliff[cliff["context_len"].isin([512, 2048])]
print(stable.groupby(["variant", "context_len"])["decode_tps"].mean().unstack())

# Thread count impact on Q4_K_M
threads = df[df["experiment_type"] == "thread_sweep"]
print(threads.groupby("threads")["decode_tps"].agg(["mean", "std"]))
```

---

## Methodology

**Hardware setup:**
- Pixel 6a benchmarks run via ADB with llama.cpp NDK cross-compiled for arm64-v8a
- Device placed on flat surface, screen off, no active charging during runs
- Each experiment preceded by 2 warmup trials (excluded from dataset)
- 1-minute cooldown between variant changes; 30s between context window changes

**Thermal controls:**
- Benchmarks aborted if device temperature > 42°C (re-run after cooldown)
- Temperature logged per trial where accessible via `/sys/class/thermal/`
- Measurement noise reduced from ±8% to ±2% through thermal discipline

**Prompts:**
- Context windows filled with repeating document content to target token count
- Output capped at 64 tokens (cliff sweep) or 128 tokens (standard sweep)
- 3 fixed prompts rotated across trials (standard sweep)

**M4 Mac:**
- llama.cpp Metal backend, `ngl=99` (all layers on GPU)
- Run via `llama-bench` CLI wrapper with same context/output targets

**x86:**
- llama.cpp CPU, AVX2 enabled, 6 threads, Windows 11
- Reference run: 1 trial per variant at ctx=256 (collected March 2026)
- Cliff sweep: n=5 trials per variant × 11 context sizes (256–2,048), filled-context
  methodology, 140s inter-trial cooldown (collected April 2026)

**Quality evaluation:**
- 100-question samples from official benchmark test sets
- Exact-match scoring with normalised output parsing
- imatrix calibration data generated from 512-token WikiText-2 passages

---

## Known Limitations

1. **Pixel 6a primary focus** — x86 and M4 coverage is less comprehensive than Pixel;
   x86 has n=5 trials for cliff sweep but no thread sweep, no kv_cache_quant experiments
2. **x86 Qwen limited to standard_sweep** — Qwen 2.5 1.5B on x86 provides decode TPS reference
   at ctx=256 only; no cliff sweep, thread sweep, or quality data for Qwen on x86
3. **Perplexity corpus inconsistency** — see note in perplexity split above
4. **No power/energy data** — `/proc` interfaces on Pixel 6a are unreliable without root;
   battery drain proxy metrics were collected but not included in this release
5. **Single model family for quality benchmarks** — quality data (BoolQ, HellaSwag, etc.)
   collected on Pixel 6a only; no cross-device quality comparison
6. **llama.cpp version** — builds used llama.cpp circa February–April 2026;
   results may differ with significantly newer versions

---

## Variants Reference

| Variant | Bits/Weight | File Size | Notes |
|---|---|---|---|
| Q2\_K | 2.6 | ~1.3 GB | Fastest on ARM; lowest quality |
| Q3\_K\_M | 3.3 | ~1.6 GB | Cliff-immune on ARM; stable across all tested contexts |
| Q4\_K\_S | 4.1 | ~1.8 GB | Good compression; imatrix gains significant |
| Q4\_K\_M | 4.5 | ~1.9 GB | Pareto-optimal on ARM (speed × quality) |
| Q5\_K\_M | 5.5 | ~2.2 GB | Best imatrix gains |
| Q6\_K | 6.6 | ~2.5 GB | Slowest on ARM; susceptible to collapse |
| Q8\_0 | 8.0 | ~3.2 GB | Near-FP16 quality; stable at long context |

Model: **meta-llama/Llama-3.2-3B-Instruct** quantized with llama.cpp `llama-quantize`.
imatrix calibration data generated from WikiText-2 using `llama-imatrix`.

---

## Citation

If you use this dataset, please cite the accompanying paper:

```bibtex
@misc{dcosta2026gguf,
  title   = {Non-Monotonic Quantization on Mobile ARM: KV-Cache Collapse and
             Superblock Dynamics in GGUF Inference},
  author  = {Dcosta, Kris},
  year    = {2026},
  note    = {Preprint. Dataset: https://huggingface.co/datasets/KrisDcosta/edge-llm-bench}
}
```

---

## License

Dataset: [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
Benchmark code: [Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0)

Benchmark datasets used for quality evaluation (ARC, BoolQ, HellaSwag, MMLU, TruthfulQA)
are subject to their respective licenses. This dataset contains only model accuracy scores,
not the benchmark questions themselves.
