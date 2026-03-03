# agent.md — Codex Agent Instructions (Strict, Simple, Reproducible)

You are a coding agent helping build a **reproducible on-device LLM benchmark**.
Optimize for: **correctness, simplicity, reproducibility, and clear documentation**.

---

## Non-negotiable rules
- Keep solutions **simple**. Avoid abstractions unless they remove real repetition.
- Do not introduce new frameworks/tools unless strictly necessary.
- Prefer a few clear scripts over complex orchestration.
- Every change should move the repo toward: **(1) working runner, (2) trustworthy logs, (3) reproducible plots, (4) stable demo**.

---

## Bias-to-action (Codex harness style)
- Implement working code, not just plans.
- Avoid long preambles. Provide minimal context, then act.
- If details are missing, make reasonable assumptions and proceed.
- Persist until the subtask is complete (code + verification), unless blocked.

---

## Search-first / reuse-first
Before adding helpers:
- search the repo for existing patterns
- reuse existing utilities for config/logging when possible
- do not duplicate functionality

---

## No silent failures
- Never silently skip measurements.
- Never silently fallback when a config fails (e.g., 2-bit quant).
- If something fails:
  - surface the error clearly
  - log it as a result when appropriate
  - continue with supported configs if possible

---

## Minimal architecture constraints
Allowed components only:
1. inference wrapper
2. instrumentation layer
3. config-driven runner producing JSONL
4. analysis scripts generating plots from logs
5. minimal Android UI that uses the same wrapper and exports logs

Do NOT add:
- databases
- services
- background daemons
- distributed runners
- complex build systems beyond what ExecuTorch/Android requires

---

## Logging and schema requirements
- Output format: **JSONL**, one object per trial.
- All results must validate against `schemas/run.schema.json`.
- Each record must include:
  - timestamps, token counts, derived metrics
  - device/build identifiers
  - quant, context, output length, trial index, warmup flag
  - peak memory and battery proxy (when available)

Add/modify schema fields only if required; keep backward compatibility.

---

## Measurement discipline
- Instrumentation must be lightweight and consistent across configs.
- Timing must use a monotonic clock.
- Do not mix UI logic with measurement logic.
- Prefer measuring in the runner/wrapper, then surface metrics to UI.

---

## “Definition of done” for any subtask
A subtask is done only when:
- code compiles/runs
- outputs are produced (logs/plots/UI)
- a short verification step is included (command to run)
- docs are updated briefly (README or relevant .md)

---

## Documentation style
- Explain *what* and *why* in short bullets.
- Avoid verbose theory. Focus on reproducible steps and exact definitions.
- Keep docs aligned with PRD (do not drift scope).
