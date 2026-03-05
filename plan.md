# plan.md — Revised Execution Plan (llama.cpp Pivot)

Guiding principle: **ship the smallest system** that answers the PRD research questions with **reproducible measurements**. No over-engineering.

---

## Context

ExecuTorch was evaluated in T05–T06 and found infeasible for Llama 3.2 3B on Pixel 6a (6GB RAM) due to OOM kills. The project pivots to **llama.cpp** with GGUF models.

Completed infrastructure (T00–T04) is reused. The Android app is rebuilt using llama.cpp.

---

## Phase 0 — Pivot Setup

- Update PRD, plan.md, schema, registry for llama.cpp
- Cross-compile llama.cpp for Android ARM64 using NDK
- Download one GGUF model (Q4_K_M) from HuggingFace
- Push binary + model to Pixel 6a via adb
- Run one prompt: `adb shell /data/local/tmp/llama-cli -m model.gguf -p "What is 2+2?" -n 32`

Exit: one prompt generates text on device.

---

## Phase 1 — Benchmark Runner + JSONL Logging

- Create `scripts/benchmark_runner.py`:
  - reads config from `experiments/registry.yaml`
  - runs warmup + recorded trials via `adb shell`
  - captures llama.cpp stdout (includes `llama_print_timings`)
  - captures peak RSS via `adb shell dumpsys meminfo`
  - captures battery via `adb shell dumpsys battery`
- Create `scripts/parse_llama_output.py`:
  - parses llama.cpp timing output into schema-valid JSONL
  - maps prompt_eval → prefill, eval → decode
- Write `results/<run_id>.jsonl`
- Validate with existing `scripts/validate_results.py`

Exit: `python scripts/benchmark_runner.py --quant Q4_K_M --context 256` produces valid JSONL.

---

## Phase 2 — Model Artifacts

Download from `bartowski/Llama-3.2-3B-Instruct-GGUF`:
- Q2_K (~1.3 GB)
- Q3_K_M (~1.6 GB) — bonus
- Q4_K_M (~2.0 GB)
- Q6_K (~2.7 GB)
- Q8_0 (~3.4 GB) — attempt

For each:
- Compute SHA256 hash
- Push to device, run smoke test
- Document load success vs OOM
- Attempt FP16 → document OOM as result

Exit: at least Q2_K, Q4_K_M, Q6_K verified. Q8_0 attempted.

---

## Phase 3 — Full Experiment Sweep

Matrix:
```
Quant:    [Q2_K, Q3_K_M, Q4_K_M, Q6_K, Q8_0*]
Context:  [256, 512, 1024, 2048*]
Output:   128 tokens (fixed)
Warmups:  2
Trials:   5
```

Protocol: airplane mode, fixed brightness, background apps closed, 2-min cooldown.

Store: `results/<quant>-<context>.jsonl`

Exit: complete dataset. Schema validation passes on all files.

---

## Phase 4 — Analysis & Figures

Create `analysis/generate_figures.py`:
1. Prefill TPS vs Context Length (per quant, with error bars)
2. Decode TPS vs Context Length (per quant, with error bars)
3. TTFT vs Context Length (per quant)
4. Peak Memory vs Quant Level (bar chart)
5. Battery Drain per 1K Tokens vs Quant Level
6. Efficiency-Accuracy Pareto Frontier
7. Prefill vs Decode Time Fraction (stacked bar)
8. Latency Distribution (box/violin, p50/p90/p99)
9. Model Size vs Decode TPS

Exit: `python analysis/generate_figures.py results/` generates all plots.

---

## Phase 5 — Android Chat UI Demo

Base: llama.cpp `examples/llama.android/` (Kotlin/Compose + JNI)

Customize:
- Live metrics overlay (TTFT, Prefill TPS, Decode TPS)
- Quant selector dropdown
- Benchmark mode button (runs prompt suite, exports JSONL)

Fallback (if time-pressed): Kotlin wrapper around `Runtime.exec()` calling `llama-cli`

Exit: offline chat works on Pixel 6a, shows metrics, exports logs.

---

## Phase 6 — Report & Polish

- Re-run subset for repeatability
- Verify schema validation
- Regenerate all figures from raw logs
- Map findings to RQ1–RQ5
- Document ExecuTorch evaluation and pivot rationale
- Record demo video

Exit: report-ready results + stable demo.

---

## Phase Gates

### Gate A — Baseline
Do not start sweep until:
- llama.cpp runs on device reliably
- one prompt completes end-to-end
- one schema-valid JSONL record exists

### Gate B — Sweep
Do not start full matrix until:
- benchmark runner is stable
- schema validation passes
- at least 2 quant levels verified

### Gate C — Report
Do not write conclusions until:
- figures regenerate from raw logs in one command
- repeatability subset rerun
- failures documented explicitly
