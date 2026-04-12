# Direction 4: Adaptive Quantization Recommendation Engine

## Project Context

**Repository:** github.com/KrisDcosta/291_EAI  
**Parent project:** EdgeLLMBench — a controlled benchmarking study of GGUF K-quant variants
(Q2_K through Q8_0) of Llama 3.2 3B Instruct and Qwen 2.5 1.5B Instruct across three
hardware platforms (Pixel 6a ARM64, x86 i5-1235U, Mac M4 Metal).

The benchmarking phase is complete (~4,400 measurements). Direction 4 builds an ML
pipeline on top of that dataset to answer the question:
> *Given a user's device, context budget, and use case — which GGUF variant should they use?*

---

## The Core Insight (From the Benchmark Data)

The benchmark uncovered three non-obvious findings that make this recommendation problem
genuinely hard (and interesting):

1. **Non-monotonic throughput ordering on CPU.** Q2_K is the fastest CPU variant despite
   being the lowest bit-width (8.33 t/s on Pixel 6a; 14.05 t/s on x86). Q6_K is the
   *slowest* CPU variant despite being higher bit-width (3.55 t/s ARM; 6.80 t/s x86).
   This is completely counter-intuitive and is caused by SIMD dequantization kernel
   complexity (Q6_K requires a 6-operand split-bit shuffle; Q2_K uses a 16-entry table
   lookup). GPU (Metal) ordering is reversed: Q4_K_S fastest, Q8_0 slowest.

2. **KV-cache cliff at a predictable context threshold.** Q2_K has a −48% TPS cliff onset
   at ctx≈512 on ARM and ctx≈1,200–1,300 on x86. The cliff threshold is predictable from
   hardware specs: `cliff_ctx ≈ L2_cache / (2 × n_layers × n_kv_heads × head_dim × 2B)`.
   Q3_K_M is cliff-immune (<±5%). This means a model recommender must account for the
   user's intended context length, not just their device specs.

3. **Non-monotonic quality ordering.** Q4_K_S (74% BoolQ) outperforms Q4_K_M (72%) and
   Q6_K (65%), despite Q6_K having more bits. Q6_K is Pareto-dominated: slower AND less
   accurate than Q4_K_M. imatrix calibration helps at ≥4 bpw but hurts Q2_K/Q3_K_M.

---

## Dataset Available

The dataset is published at: https://huggingface.co/datasets/KrisDcosta/edge-llm-bench

**Splits:**
- `pixel_inference` — 2,875 rows: Pixel 6a (ARM64) TPS measurements across 7 variants ×
  4–11 context lengths × 3–10 trials. Includes experiment types: `standard_sweep`,
  `cliff_sweep`, `kv_cache_quant`, `thread_sweep`, `imatrix_sweep`.
- `m4_inference` — 1,021 rows: Mac M4 Metal GPU (931) + CPU (90). TPS across contexts.
- `x86_inference` — 399 rows: Intel i5-1235U. Llama cliff sweep (385) + Qwen/Llama
  standard reference (14).
- `quality_benchmarks` — 105 rows: accuracy scores (BoolQ, ARC-Easy, ARC-Challenge,
  HellaSwag, MMLU, TruthfulQA) × 7 variants × (standard + imatrix).
- `perplexity` — 7 rows: WikiText-2 full corpus (~290K tokens) PPL per variant.

**Key features available per inference record:**
`variant`, `context_len`, `decode_tps`, `prefill_tps`, `backend` (CPU/Metal),
`threads`, `experiment_type`, `model` (Llama/Qwen)

---

## What to Build

### Phase 1 — ML Model (2–3 weeks)

**Input features (device + use-case context):**
- `backend`: CPU_ARM / CPU_x86 / GPU_Metal
- `l2_cache_kb`: L2 cache per core (key predictor of cliff threshold)
- `ram_gb`: available RAM
- `cpu_cores`: physical cores
- `context_budget`: max context length the user needs
- `priority`: `speed` / `accuracy` / `balanced`
- `use_case`: `chat` (short ctx) / `rag` (medium ctx) / `summarization` (long ctx)

**Target outputs (multi-task):**
1. **Recommended variant** (7-class classification: Q2_K … Q8_0)
2. **Predicted decode TPS** at the user's context length (regression)
3. **KV-cache cliff risk flag** (binary: will throughput drop >20% at target context?)
4. **Predicted accuracy** on BoolQ proxy (regression, device-independent)

**Model architecture:**
- Gradient-boosted trees (XGBoost or LightGBM) as primary — small dataset, tabular features,
  interpretable. The cliff threshold formula gives a strong engineered feature.
- Consider a small neural net as comparison baseline.
- Feature engineering: `cliff_risk = (context_budget > cliff_ctx_estimate)` where
  `cliff_ctx_estimate = l2_cache_kb * 1024 / (2 * n_layers * n_kv_heads * head_dim * 2)`.

**Evaluation:**
- Leave-one-device-out cross-validation (train on Pixel + x86, test on M4 and vice versa).
- This tests generalization to unseen hardware — the actual deployment scenario.
- Metric: recommendation accuracy (does the recommended variant match the Pareto-optimal
  choice for the test device?) and TPS prediction MAE.

### Phase 2 — Serving

**Python API (FastAPI):**
```python
POST /recommend
{
  "device_backend": "CPU_ARM",
  "l2_cache_kb": 512,
  "ram_gb": 6,
  "context_budget": 1024,
  "priority": "balanced"
}
# Returns: { "variant": "Q4_K_M", "predicted_tps": 4.3, "cliff_risk": false,
#            "reasoning": "Q4_K_S preferred for accuracy but cliff risk at ctx>512..." }
```

**ONNX export for Android:**
- Export the trained model to ONNX using `sklearn-onnx` or `xgboost.to_onnx()`.
- Load in the Android app (already exists in `/android`) via ONNX Runtime for Android.
- The app's `BenchmarkScreen.kt` can surface the recommendation before running inference.

**Optional: Distill to rule-based fallback** for devices where ONNX Runtime is unavailable.

### Phase 3 — Monitoring (stretch)
- Log actual TPS from the Android app against predicted TPS.
- Track prediction drift as new hardware configurations are encountered.
- Auto-retrain trigger when prediction error exceeds threshold.

---

## Agent Prompt

Use this prompt when handing this task to a coding agent:

---

```
You are building Direction 4 of the EdgeLLMBench project: an Adaptive Quantization
Recommendation Engine. The benchmarking phase is complete — your job is to build an
ML pipeline on top of the existing dataset.

REPO: github.com/KrisDcosta/291_EAI
DATASET: https://huggingface.co/datasets/KrisDcosta/edge-llm-bench

CONTEXT — READ THIS FIRST:
The dataset measures inference throughput of 7 GGUF quantization variants (Q2_K through
Q8_0) across 3 devices (Pixel 6a ARM, x86 i5-1235U, Mac M4 Metal). The key findings are:
1. CPU throughput is NON-MONOTONIC: Q2_K is fastest on CPU (not lowest quality). Q6_K is
   slowest on CPU (despite more bits). GPU (Metal) ordering is REVERSED.
2. Q2_K has a KV-cache cliff: -48% TPS drop at ctx≈512 on ARM. This is predictable from
   L2 cache: cliff_ctx ≈ L2_cache / (2 * n_layers * n_kv_heads * head_dim * 2).
3. Q4_K_S is Pareto-dominant for accuracy (74% BoolQ). Q6_K is Pareto-dominated.

YOUR TASK:
1. Load the dataset from HuggingFace using the `datasets` library.
2. Feature-engineer the training set:
   - Per device: L2 cache KB, RAM GB, CPU cores, backend type (CPU_ARM/CPU_x86/GPU)
   - Per record: variant (ordinal encoded), context_len, experiment_type
   - Engineered: cliff_ctx_estimate (from formula above), cliff_risk (bool)
3. Train an XGBoost model to predict decode_tps given device features + variant + context.
4. Train a second XGBoost classifier to recommend the Pareto-optimal variant given:
   device features + context_budget + priority (speed/accuracy/balanced).
5. Evaluate with leave-one-device-out CV. Report: TPS prediction MAE, recommendation
   accuracy vs the empirical Pareto-optimal choice.
6. Export models to ONNX using sklearn-onnx or xgboost's built-in ONNX export.
7. Write a FastAPI endpoint that takes {backend, l2_cache_kb, ram_gb, context_budget,
   priority} and returns {variant, predicted_tps, cliff_risk, reasoning}.
8. Write unit tests for the feature engineering and recommendation logic.

OUTPUT FILES:
- scripts/ml/train_recommendation_engine.py  (training pipeline)
- scripts/ml/feature_engineering.py          (feature extraction from raw dataset)
- scripts/ml/evaluate.py                     (cross-device evaluation)
- models/recommendation_engine.onnx          (exported model)
- api/recommend.py                           (FastAPI endpoint)

KEY CONSTRAINT: The model must generalize to unseen devices — use leave-one-device-out
CV, not random split. A recommendation that only works on devices already in the training
set has limited deployment value.
```

---

## Files to Reference

Before starting, read these files in the repo:

| File | Why |
|------|-----|
| `dataset/README.md` | Schema for all 5 dataset splits |
| `results/CANONICAL.md` | Maps paper claims to source data directories |
| `VERIFIED_METRICS_MASTER_TABLE.md` | Ground-truth TPS/accuracy values to validate against |
| `scripts/prepare_dataset.py` | How raw JSONL results are transformed into parquets |
| `scripts/bake_dashboard_data.py` | Shows current feature extraction logic |
| `android/app/src/main/java/com/eai/edgellmbench/` | Android app structure for ONNX integration |

---

## Success Criteria

- Leave-one-device-out TPS prediction MAE < 1.5 t/s
- Recommendation accuracy > 70% (matches empirical Pareto-optimal variant)
- ONNX model < 5 MB (loadable on Android)
- FastAPI endpoint with <50ms p99 latency
- The cliff risk flag correctly identifies Q2_K at ctx>512 for ARM, Q2_K at ctx>1200 for x86

---

## Resume Impact

This completes the MLE pipeline story:
> *"Built ML recommendation engine on 4,400+ controlled inference measurements;
> trained gradient-boosted model to predict optimal GGUF quantization variant from
> device specs with leave-one-device-out CV; deployed as ONNX in Android app."*
