# Quantized On-Device LLM Inference Study
## ExecuTorch + Llama 3.2 3B on Android (Pixel 6a)

> Goal: a reproducible, measurement-driven benchmark + minimal Android UI demo that quantifies how quantization and context length affect **prefill** and **generation** performance, memory, and energy proxy.

---

## 1) Objective

Build a reproducible on-device benchmarking system to analyze how quantization levels **16/8/6/4/2-bit** affect inference performance of **Llama 3.2 3B** on **Android (Pixel 6a)** using **ExecuTorch**.

We will measure:

- **TTFT** (time to first token)
- **Prefill TPS**
- **Decode TPS**
- **Generation vs Prefill** (ratio and fractions of total time)
- **End-to-End latency**
- **Peak memory**
- **Battery proxy** (energy estimate)
- **Efficiency vs Quality** tradeoff (lightweight quality proxy)

Deliverables:

- Reproducible benchmark harness (config-driven)
- JSONL logs + schema validation
- Auto-generated plots/tables from raw logs
- Minimal Android chat demo with live metrics + log export
- Clear deployment recommendations for a 6GB Android device

---

## 2) Research Questions

### RQ1 — Quantization impact
How do 16/8/6/4/2-bit affect:
- TTFT, Prefill TPS, Decode TPS
- Peak memory
- Battery proxy

### RQ2 — Scaling with context length
How do metrics change as context increases?
- Does prefill degrade faster than decode?
- Where do memory limits appear?

### RQ3 — Generation vs Prefill split
How does time split (prefill vs generation) change across:
- Quant levels
- Context lengths

### RQ4 — Efficiency vs quality
What is the Pareto frontier between:
- performance (TTFT/TPS), memory, battery proxy
- quality proxy

### RQ5 — Practical deployment limits
- When does OOM happen?
- When does thermal throttling distort performance?
- What is the recommended “default config” for Pixel 6a?

---

## 3) Scope

### Included
- **One framework:** ExecuTorch
- **One primary device:** Pixel 6a (Android)
- **One model:** Llama 3.2 3B
- **Quantization comparison:** 16/8/6/4/2 (2-bit is experimental; failure is a valid result)
- **Context sweep** (at least 3 sizes)
- **Structured logging** (JSONL) + schema validation
- **Android UI demo** (chat + live metrics + export logs)

### Excluded (explicitly not doing)
- Training / fine-tuning
- Multi-framework comparisons (unless future work)
- Custom kernel optimizations
- Cloud comparisons
- External power meter hardware (battery proxy only)

---

## 4) Experimental Design

### Context lengths (target)
- 256
- 1024
- 4096
- 8192 (only if stable; otherwise document limit)

### Output length
- Fixed at **128 output tokens** (for fair decode comparisons)

### Trials
- Warmups: **2**
- Recorded: **5**
- Report p50/p90/p99 + mean/std per config

### Prompt suite (minimal, fixed)
- A small prompt set (e.g., 30–100 prompts) covering:
  - short factual Q/A
  - summarization
  - reasoning-ish
- Prompts are versioned in-repo to keep evaluation reproducible.

---

## 5) Metrics (definitions)

All timestamps are monotonic clock on-device.

**TTFT**  
`ttft_s = t_first_token - t_request_start`

**Prefill time**  
`prefill_s = t_first_token - t_model_forward_start`

**Prefill TPS**  
`prefill_tps = input_tokens / prefill_s`

**Generation (decode) time**  
`gen_s = t_last_token - t_first_token`

**Decode TPS**  
`decode_tps = output_tokens / gen_s`

**End-to-End latency**  
`e2e_s = t_last_token - t_request_start`

**Generation vs Prefill**
- Ratio: `gen_over_prefill = gen_s / prefill_s`
- Fractions:
  - `prefill_frac = prefill_s / e2e_s`
  - `gen_frac = gen_s / e2e_s`

**Peak memory**
- `peak_rss_mb` = peak resident set size during trial (sampling-based; document method)

**Battery proxy**
- `battery_drop_pct = battery_start_pct - battery_end_pct`
- Normalized:
  - `battery_drop_per_1k_tokens = 1000 * battery_drop_pct / total_tokens`

**Quality proxy (lightweight)**
Pick ONE (keep simple):
- (Option A) Small task set with simple exact-match scoring for a subset
- (Option B) LLM-as-judge rubric scored consistently (document limitations)
Result: `quality_score` per config (aggregate mean ± std)

---

## 6) Reproducibility Protocol (non-negotiable)

### Device/environment controls
- Airplane mode ON
- Fixed brightness
- Close background apps
- Consistent thermal protocol: cooldown between runs (document)

### Run metadata (must be logged)
Each trial record includes:
- device model, Android version
- ExecuTorch version / build identifier
- model artifact hash
- quant level, context length, output length
- trial index + warmup flag
- timestamps (request/model/first/last)
- input/output token counts
- peak memory
- battery start/end (%)
- optional: temperature if accessible

### Log format
- Append-only **JSONL**: one JSON object per trial
- Location: `results/<run_id>.jsonl`

### Schema + validation
- Maintain `schemas/run.schema.json`
- Provide `scripts/validate_results.py` that fails loudly on schema mismatch

### Experiment registry
- Maintain `experiments/registry.yaml` listing every config executed for the final report (audit trail)

---

## 7) System Architecture (minimal)

### Components
1. **Inference wrapper** (ExecuTorch model load + token generation)
2. **Instrumentation layer** (timestamps, tokens, memory, battery snapshot)
3. **Runner** (config-driven trials + JSONL logging)
4. **Analysis** (read JSONL → tables/plots)
5. **Android UI** (chat + live metrics + benchmark mode)

### Dataflow
Prompts/config → Runner → JSONL logs → Analysis → plots/report  
UI uses the same inference wrapper and writes logs with the same schema.

---

## 8) Acceptance Tests (definition of “done”)

### Smoke test (must pass)
- `scripts/smoke_test.sh` (or equivalent) runs one prompt and prints TTFT + TPS, writes 1 JSON record.

### Benchmark run (must pass)
- Run at least:
  - 3 quant levels (16/8/4 minimum; ideally include 6; attempt 2)
  - 3 context lengths
  - 5 trials each (after warmup)
- Generates plots with one command.

### UI demo (must pass)
- Chat works offline
- Displays TTFT + Prefill TPS + Decode TPS + Gen/Prefill ratio
- Export logs button works

---

## 9) Risks & Mitigations

- **2-bit unsupported/unstable** → treat as result; log failure explicitly; continue with supported quant; include 6-bit as intermediate.
- **OOM at long context** → identify threshold; include as practical limit finding.
- **Thermal throttling** → cooldown protocol + record conditions; report variability.

---

## 10) Future Extensions (post-course)
- Add iOS replication
- Compare delegates/backends within ExecuTorch
- Add a practical app workload (offline summarizer/assistant) using the same benchmark harness
- Paper-style writeup as a measurement study
