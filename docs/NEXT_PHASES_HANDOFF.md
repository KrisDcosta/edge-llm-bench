# Next Phases Handoff

Date: 2026-04-17

This document is for the next agent taking over after phase 1.

## Current Baseline

Phase 1 is complete. The project now has:
- one canonical public rebuild command: `python3 scripts/build_public_release.py`
- one generated release manifest: `artifacts/public_release_manifest.json`
- one generated public truth table: `artifacts/public_truth_table.md`
- CI that validates the public release before deploy

Before making any changes in later phases, always start by reading:
- `artifacts/public_release_manifest.json`
- `artifacts/public_truth_table.md`
- `results/CANONICAL.md`
- `docs/PUBLIC_RELEASE_AUDIT.md`

## Phase 1 Outcomes That Must Be Preserved

Do not regress these:
- public parquet excludes contaminated Pixel Qwen cliff data
- public parquet includes validated M4 Qwen TPS/cliff data from `results/m4_qwen_tps_20260415_130955/` and `results/m4_qwen_cliff_20260416_021323/`
- public parquet includes the clean M4 CPU TPS rerun from `results/m4_cpu_tps_20260415_231524/`
- x86 Qwen cliff reruns remain excluded because the pushed result files contain missing/zero-throughput rows at larger contexts
- Pixel cliff rows come from per-variant canonical sources, not the older mixed batch
- canonical Pixel TPS comes from `results/pixel_llama_tps_20260325_120022/`
- public docs do not reference ignored private files such as `VERIFIED_METRICS_MASTER_TABLE.md`
- dashboard text stays synchronized with the validated artifact counts

Any change that touches `results/`, `dataset/`, `dashboard/`, `README.md`, or `CONTRIBUTING.md`
should end with:

```bash
python3 scripts/build_public_release.py
```

## Recommended Execution Order

### Phase 2 — Structured Evaluation Layer

Goal: turn the benchmark from score reporting into a behavioral evaluation framework.

Recommended deliverables:
- define task classes:
  - MCQ knowledge
  - reasoning
  - long-context sensitivity
  - instruction following
  - output-format reliability
- create a structured failure taxonomy:
  - answer collapse
  - formatting failure
  - refusal drift
  - verbosity drift
  - inconsistency across retries
- generate per-variant evaluation reports that can be linked from the dashboard
- keep the new outputs derived from canonical public data and route them through the same release build

Suggested implementation shape:
- add a new evaluation artifact under `artifacts/`
- keep benchmark scoring in `results/quality_scores.json`, but add a derived report layer rather than overloading the raw score file
- expose summaries in the dashboard only after they have a stable schema and validator checks

### Phase 3 — Quantization Recommendation Engine v1

Goal: convert the benchmark into a decision system.

Inputs:
- device
- backend
- context length
- task class
- latency preference
- quality preference

Outputs:
- recommended quant
- expected TPS band
- cliff risk
- quality caveat
- fallback alternatives

Implementation guidance:
- start rule-based, not learned
- use the public truth table and canonical parquet splits as the only policy source
- expose the recommender in the dashboard as an additional view, not a separate product
- add validator checks for policy outputs so recommendations remain traceable to measured data

### Phase 4 — Adaptive Quantization Recommendation Engine

Goal: move from static recommendation to runtime-aware policy switching.

Recommended policy factors:
- prompt/context length
- task class
- thermal state
- latency-critical vs quality-critical mode

Recommended first policy rules:
- short context, latency-critical: Q2_K fast path
- long context or collapse-prone contexts: prefer Q4_K_M or Q3_K_M
- instruction-sensitive tasks: avoid Q2_K
- sustained/thermal pressure: degrade to safer throughput choice only if quality constraints allow

Expected output:
- a policy engine that can explain why it switched variants
- scenario cards showing when the adaptive policy outperforms any static single-quant choice

### Phase 5 — Publication Strengthening

Goal: raise the work from strong public project to stronger publication candidate.

Recommended additions:
- one Snapdragon flagship device
- one Apple A-series phone/tablet device
- `simpleperf` / `perf` counter evidence
- cache-miss and backend-stall evidence for the dequantization explanation
- validation of whether the recommendation policy transfers across devices

Strong publication framing:
- measurement-driven adaptive quantization policy for edge inference
- cross-device validation of CPU/GPU quantization-ordering divergence
- mechanistic explanation tied to cache pressure and dequantization cost

## Explicitly Avoid

Do not spend time on:
- a generic chat app layer
- RAG features unrelated to quantization policy
- broad MLOps work that does not strengthen reproducibility or recommendation quality

## Resume / Positioning Notes

When future phases land, keep the narrative consistent:
- phase 1: artifact-quality benchmark and public release
- phase 2: structured behavioral evaluation
- phase 3: recommendation engine
- phase 4: adaptive policy engine
- phase 5: publication-strengthening cross-device systems study

This sequencing keeps the project coherent instead of turning it into a pile of unrelated LLM features.
