# New Chat Context

Date: 2026-04-23

This document is the starting context for future Codex/agent chats after the
repository rename from `291_EAI` to `edge-llm-bench`.

## Repository State

- Local checkout: `/Users/krisdcosta/edge-llm-bench`
- GitHub repo: `https://github.com/KrisDcosta/edge-llm-bench`
- Dashboard: `https://krisdcosta.github.io/edge-llm-bench/`
- Hugging Face dataset: `https://huggingface.co/datasets/KrisDcosta/edge-llm-bench`
- Default branch: `main`
- Remote branches: only `origin/main`
- GitHub repo description: `Edge LLM benchmark for GGUF quantization across Pixel ARM, x86 AVX2, and Mac M4 Metal`

The old repo name/path `291_EAI` should not be reintroduced in public docs or
links. The old GitHub repo slug redirects, but all maintained references should
use `edge-llm-bench`.

## Public Release Baseline

The current public release is valid and shareable as an independent project.
It is no longer framed as a course project.

Canonical validation command:

```bash
python3 scripts/build_public_release.py
```

Expected public artifact counts:

| Split | Rows |
|---|---:|
| `pixel_inference.parquet` | 1,819 |
| `m4_inference.parquet` | 1,035 |
| `x86_inference.parquet` | 399 |
| `quality_benchmarks.parquet` | 170 |
| `perplexity.parquet` | 14 |
| **Total** | **3,437** |

This command rebuilds parquet splits, dashboard JSON, the public release
manifest, and the public truth table. It should pass before any release-facing
commit.

## Key Public Artifacts

- `README.md`: public project overview, artifacts, results, reproduction steps
- `dataset/README.md`: Hugging Face dataset card source
- `dashboard/index.html`: live dashboard shell and metadata
- `artifacts/public_release_manifest.json`: generated release contract
- `artifacts/public_truth_table.md`: generated public metric summary
- `results/CANONICAL.md`: source-of-truth mapping from claims to raw runs
- `docs/PUBLIC_RELEASE_AUDIT.md`: public release audit and guarantees
- `docs/PHASE_1_1_RUNBOOK.md`: v1.1 extension runbook
- `docs/NEXT_PHASES_HANDOFF.md`: forward-looking plan
- `CITATION.cff`: GitHub citation metadata

## Current Scientific Positioning

Project framing:

> Independent edge LLM benchmarking project studying GGUF K-quant behavior
> across Pixel ARM, x86 AVX2, and Mac M4 Metal, with a reproducible dataset,
> live dashboard, Android app, CI-validated artifact pipeline, and
> publication-oriented findings.

Core findings:

- CPU throughput ordering is non-monotonic: low-bit Q2_K can be fastest on ARM
  and x86, while Q6_K can be slower despite higher bit width.
- Mac M4 Metal follows a different ordering, supporting a CPU/GPU
  quantization-performance divide.
- Q2_K has strong short-context speed but a filled-context cliff around
  Pixel ctx≈512.
- Q4_K_S/Q4_K_M are stronger practical defaults than Q6_K in the validated
  speed-quality tradeoff.
- Q2_K can fail structured completion behavior, especially HellaSwag-style
  tasks; treat this as format/task collapse, not ordinary low accuracy.
- Pixel simpleperf/PMU evidence is supplementary and should be described as
  `PMU cache-miss proxy/tok`, not definitive L2D refill.

## Known Exclusions / Limitations

- x86 Qwen cliff is intentionally set aside. Previous runs had missing or
  zero-throughput large-context cells. Do not promote or cite x86 Qwen cliff
  until a clean 77-cell run passes validation.
- Existing quality evaluations are MCQ-heavy. BoolQ, ARC, HellaSwag, MMLU, and
  TruthfulQA are useful, but the next evaluation layer should include non-MCQ
  and structured-generation tasks.
- GSM8K and HumanEval attempts are archived/invalid because the prior
  chat-template/scoring methodology was broken.
- Apple A-series and Snapdragon are not yet measured. They are strong future
  publication-strengthening targets.

## Remaining v1.1 Item

Keep x86 Qwen cliff aside unless the x86 machine is available and quiet enough.
If it is attempted later, use:

```powershell
git pull
py -3 scripts/bench/x86_qwen_cliff.py --threads 6 --retries 4 --timeout 1200
py -3 scripts/analyze/validate_x86_qwen_cliff.py results/<x86_qwen_result_dir>
```

Acceptance criteria:

- 77 rows total: 7 variants x 11 contexts
- no errors
- `decode_tps > 0`
- `n_trials == 5`
- no missing variant/context cells
- acceptable CV; investigate cells above ~20%

If it fails, leave it excluded.

## Recommended Next Phase

Do not start with generic app features. The strongest next work is:

1. **Structured Evaluation Layer**
   - Add task taxonomy: MCQ knowledge, reasoning, long-context retrieval,
     instruction following, structured output, free-form generation, consistency.
   - Add failure taxonomy: label collapse, invalid option, JSON/schema failure,
     refusal drift, verbosity drift, inconsistency, format collapse.
   - Generate derived per-variant behavioral reports from existing and new eval
     outputs.
   - Add dashboard section only after the schema and validator are stable.

2. **Quantization Recommender v1**
   - Rule-based, using only validated public data.
   - Inputs: device/backend, model, context length, task class, speed-vs-quality
     priority, stability requirement.
   - Outputs: recommended variant, expected TPS band, cliff risk, quality caveat,
     avoid warnings, evidence links.

3. **Adaptive Quantization Policy**
   - Extend recommender into runtime policy simulation.
   - Example policy: Q2_K for short latency-critical tasks, avoid Q2_K for
     structured-output tasks and long context, prefer Q4_K_M/Q4_K_S for balanced
     reliability, use device-specific rules for Metal vs CPU.

4. **Hardware Expansion**
   - Snapdragon Android device: highest priority for mobile ARM generalization.
   - Apple A-series: feasible with iPhone 14 Pro or iPad A16 via Xcode/iOS
     harness. Be careful to label runtime/backend differences if not using the
     same llama.cpp path.

5. **Paper Refresh**
   - Reframe around measurement-driven quantization policy for edge LLMs.
   - Include structured failure modes, recommender logic, PMU appendix, and
     future hardware validation plan.

## Apple A-Series Notes

Available user hardware:

- iPhone 14 Pro
- iPad A16
- Xcode available

Preferred methodology:

- Use an iOS harness with the closest possible runtime to the existing
  methodology.
- Prefer `llama.cpp` if feasible to keep model format and prompts aligned.
- If using Core ML, MLC, or another runtime, clearly label results as
  backend/runtime comparison rather than pure hardware comparison.

## Communication / Quality Bar For Future Agents

- Do not reintroduce stale, contaminated, or excluded data.
- Do not fill dashboard blanks with assumptions.
- Do not promote x86 Qwen cliff without validator pass.
- Do not claim PMU counters prove L2 refill causality.
- Always run `python3 scripts/build_public_release.py` before release-facing
  commits.
- Keep public docs aligned with current artifact counts and canonical sources.

## Quick Start For New Chat

Use this sequence at the start of a new agent session:

```bash
cd /Users/krisdcosta/edge-llm-bench
git status --short --branch
git pull
python3 scripts/build_public_release.py
```

Then read, in order:

1. `docs/NEW_CHAT_CONTEXT.md`
2. `artifacts/public_release_manifest.json`
3. `artifacts/public_truth_table.md`
4. `results/CANONICAL.md`
5. `docs/NEXT_PHASES_HANDOFF.md`
6. `docs/PHASE_1_1_RUNBOOK.md`

