# plan.md — Project Execution Plan (Agent-Oriented)

Guiding principle: **ship the smallest system** that answers the PRD research questions with **reproducible measurements**. No over-engineering.

---

## Phase 0 — Scope freeze (PRD alignment)
- Confirm: device, framework, model, quant levels, context sizes, trial counts, prompt suite size.
- Create/confirm:
  - `schemas/run.schema.json`
  - `experiments/registry.yaml` (audit trail)
  - results directory conventions

Exit: PRD choices are frozen; schema + registry exist.

---

## Phase 1 — Baseline: ExecuTorch runs Llama 3.2 3B on device
- Build ExecuTorch Android example
- Load model and generate text for 1 prompt reliably
- Create a **smoke test** command/script that:
  - runs 1 prompt
  - prints TTFT
  - writes one JSON record

Exit: "hello world" is reliable and produces a JSON record.

---

## Phase 2 — Instrumentation + logging (core)
Implement measurement hooks (minimal, correct):
- timestamps:
  - `t_request_start`
  - `t_model_forward_start`
  - `t_first_token`
  - `t_last_token`
- token counts:
  - `input_tokens`, `output_tokens`
- derived metrics:
  - TTFT, Prefill TPS, Decode TPS, E2E latency
  - Generation vs Prefill (ratio + fractions)
- resource:
  - peak RSS sampling (simple periodic sampler)
  - battery start/end snapshot

Add JSONL logging (one record per trial) + schema validation.

Exit: a single config run produces schema-valid JSONL.

---

## Phase 3 — Quantization artifacts
Prepare model artifacts for:
- 16-bit (baseline)
- 8-bit
- 6-bit
- 4-bit
- 2-bit (attempt)

Rules:
- If 2-bit is unsupported/unstable, **do not silently fallback**.
- Log failure reason and continue with supported levels.
- Ensure artifacts are named consistently and hashed.

Exit: 16/8/6/4 run; 2-bit attempted and documented.

---

## Phase 4 — Config-driven runner
Implement config input (YAML preferred):
- `quant`
- `context_length`
- `output_tokens`
- `warmups`
- `trials`
- `prompt_set_id`

Runner behavior:
- warmup runs are executed but flagged `warmup=true`
- recorded runs are `warmup=false`
- writes JSONL
- appends metadata from device/build

Exit: runner can execute any registry config and produce logs.

---

## Phase 5 — Execute sweep (the dataset)
Run the experiment registry:
- Quant × Context matrix (at least 3 contexts × 3+ quants)
- Fixed output length
- 2 warmups + 5 trials per config

Store:
- `results/<run_id>.jsonl`
- `results/<run_id>.meta.json` (optional summary)

Exit: complete dataset for report figures exists.

---

## Phase 6 — Analysis (one-command figure generation)
Implement analysis script(s) that:
- read JSONL logs
- compute summary stats (mean/std, p50/p90/p99)
- generate plots:
  - Prefill TPS vs context (per quant)
  - Decode TPS vs context (per quant)
  - TTFT vs context (per quant)
  - Peak memory vs context (per quant)
  - Generation vs Prefill (ratio/fractions) vs context (per quant)
  - Latency distributions (p50/p90/p99)

Strict rule: plots must be reproducible from raw logs with one command.

Exit: `python analysis/generate_figures.py results/*.jsonl` generates all figures.

---

## Phase 7 — Android UI demo (minimal)
Build a minimal chat UI that:
- runs the same inference wrapper
- displays live metrics (TTFT, prefill/decode TPS, gen/prefill ratio)
- includes a "Benchmark mode" button that runs a small fixed suite and exports logs

Exit: stable offline demo + exported logs are schema-valid.

---

## Phase 8 — Final validation
- Re-run a subset to confirm repeatability
- Verify schema validation passes
- Confirm figures regenerate cleanly
- Write down findings mapped to each research question

Exit: report-ready results + demo reliability.
