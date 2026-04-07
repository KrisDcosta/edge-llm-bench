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
(Q2\_K through Q8\_0) of **Llama 3.2 3B Instruct** across three hardware platforms:

| Device | SoC / CPU | RAM | Backend |
|---|---|---|---|
| Google Pixel 6a | Google Tensor G1 (ARM Cortex-X1) | 6 GB LPDDR5 | llama.cpp CPU |
| Apple M4 Mac | Apple M4 (ARM, 10-core) | 16 GB unified | llama.cpp Metal |
| HP Pavilion x86 | Intel Core i5-1235U (12th gen) | 16 GB DDR4 | llama.cpp CPU |

**3,923 total records** across 5 splits. All inference records are non-warmup,
success-status runs collected under controlled thermal conditions. Contaminated
and failed records are archived separately and not included here.

---

## Key Findings (from the accompanying paper)

- **Non-monotonic throughput on ARM:** Q2\_K is 112% faster than Q6\_K on Pixel 6a
  despite having less than half the bits per weight — contradicting GPU-derived assumptions
- **KV-cache collapse threshold:** Q3\_K\_M and Q6\_K suffer a ≥40% throughput cliff beyond
  ~1400–1500 context tokens on Pixel 6a; Q2\_K, Q4\_K\_M, Q8\_0 remain stable
- **Non-monotonic quality:** Q4\_K\_M outperforms Q6\_K on BoolQ (72% vs 65%) despite
  fewer bits — superblock structure matters more than raw bit count
- **imatrix calibration:** Importance-weighted quantization recovers 4–6% accuracy at
  4–5 bits with minimal throughput cost
- **Cross-device consistency:** ARM throughput ordering replicates on M4 (±5%); reverses
  on M4 Metal GPU where Q8\_0 is fastest

---

## Splits

### `pixel_inference` — 2,875 rows
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

### `m4_inference` — 931 rows
Apple M4 Mac (Metal GPU backend) inference runs.

Same columns as `pixel_inference`. `backend = "Metal"`, `ngl = 99` (all layers on GPU).
Includes Llama 3.2 3B and Qwen 2.5 1.5B for cross-model validation.

> **Note:** M4 CPU (non-Metal) data was collected but found to be corrupted during
> post-processing and is excluded from this dataset.

---

### `x86_inference` — 7 rows
Intel Core i5-1235U (x86, AVX2, CPU backend), Windows 11. One aggregate data point
per variant (single timed run, not repeated trials). Useful as a rough cross-architecture
reference point only.

---

### `quality_benchmarks` — 103 rows
Accuracy scores on 6 NLP benchmarks for 7 quantization variants on Pixel 6a.

| Column | Type | Description |
|---|---|---|
| `benchmark` | string | `arc_challenge` \| `arc_easy` \| `boolq` \| `hellaswag` \| `mmlu` \| `truthfulqa` \| `custom_qa` |
| `variant` | string | GGUF quantization variant |
| `device` | string | `"Pixel6a"` |
| `model` | string | Model name |
| `calibration` | string | `"standard"` or `"imatrix"` (importance-weighted) |
| `accuracy_pct` | float | Accuracy percentage (0–100) |
| `correct` | int | Correct answers |
| `total` | int | Total questions evaluated |
| `status` | string | `"success"` for all included rows |

**Benchmark sample sizes:** 100 questions each (random sample from official test sets).
BoolQ imatrix calibration covers all 7 variants.

---

### `perplexity` — 7 rows
WikiText-2 perplexity scores for Llama 3.2 3B Instruct on Pixel 6a.

| Column | Type | Description |
|---|---|---|
| `variant` | string | GGUF quantization variant |
| `model` | string | Model name |
| `device` | string | `"Pixel6a"` |
| `perplexity` | float | WikiText-2 perplexity (lower = better); null if not evaluated |
| `perplexity_status` | string | `"success"` or `"not_evaluated"` |
| `corpus` | string | `"wikitext2_full"` (~285K tokens) or `"wikitext2_sample"` (~12K tokens) |
| `tokens_approx` | int | Approximate token count used |
| `note` | string | Reason if not\_evaluated |

> **Important:** Q2\_K and Q3\_K\_M were evaluated on the full WikiText-2 corpus;
> Q4\_K\_M, Q6\_K, Q8\_0 on a 12K-token sample. Do not directly compare perplexity
> values across these two groups without accounting for corpus size effects.
> Q4\_K\_S and Q5\_K\_M were added after the initial sweep and are marked `not_evaluated`.

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
- Single timed run per variant (not repeated trials)

**Quality evaluation:**
- 100-question samples from official benchmark test sets
- Exact-match scoring with normalised output parsing
- imatrix calibration data generated from 512-token WikiText-2 passages

---

## Known Limitations

1. **Pixel 6a only for primary data** — cross-device coverage for M4 and x86 is less
   comprehensive than Pixel; x86 is a single data point per variant
2. **x86 no repeated trials** — cannot report variance for x86 results
3. **Perplexity corpus inconsistency** — see note in perplexity split above
4. **No power/energy data** — `/proc` interfaces on Pixel 6a are unreliable without root;
   battery drain proxy metrics were collected but not included in this release
5. **Single model family** — primary data uses Llama 3.2 3B Instruct; Qwen 2.5 1.5B
   cross-model data is included for M4 and Pixel cliff sweeps only
6. **llama.cpp version** — builds used llama.cpp circa February–April 2026;
   results may differ with significantly newer versions

---

## Variants Reference

| Variant | Bits/Weight | File Size | Notes |
|---|---|---|---|
| Q2\_K | 2.6 | ~1.3 GB | Fastest on ARM; lowest quality |
| Q3\_K\_M | 3.3 | ~1.6 GB | Susceptible to KV-cache collapse |
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
