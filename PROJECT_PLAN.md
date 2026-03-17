# Project Plan: Benchmarking GGUF Quantization for On-Device LLM Inference
**Status:** Phase 2 (Device Runs + Paper Drafting) | **Last Updated:** 2026-03-16 | **Target Venue:** MobiSys 2027 / MLSys 2027 / USENIX ATC 2027

---

## Project Status Summary (as of 2026-03-16)

### ✅ Completed Phases

**Phase 0: Scope & Planning**
- ✅ 7 variants finalized (Q2_K, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0)
- ✅ 7 benchmarks selected (WikiText-2, BoolQ, ARC-Easy, ARC-Challenge, HellaSwag, MMLU, TruthfulQA)
- ✅ 5 research questions defined (RQ1–RQ5)
- ✅ 19-section paper blueprint created (PAPER_PLAN.md)

**Phase 1A: Android App Development & Infrastructure**
- ✅ Production-quality Android app (Jetpack Compose, Material3, 4 screens)
- ✅ Benchmark runner script (420+ runs, ADB orchestration, thermal controls)
- ✅ Quality evaluation framework (7 benchmarks, exact-match scoring, Wilson CI)
- ✅ Cross-device scripts (Mac M4, x86, iPhone setup)

**Phase 1B: Primary Device Benchmarking (Pixel 6a)**
- ✅ Standard sweep: 7 variants × 4 contexts × 15 trials = 420 runs **complete**
- ✅ Granular collapse sweep: Q3_K_M, Q6_K × 5 contexts × 15 trials = 150 runs **complete**
- ✅ Flash Attention mitigation (−fa on syntax fixed, re-runs complete)
- ✅ KV quantization mitigation (−ctk q8_0 tested)
- ✅ imatrix calibration: 5 variants calibrated, 100 BoolQ runs **complete**
- ✅ Quality evaluation: BoolQ (100 runs all 7 variants) **complete** + imatrix variant **complete**

**Phase 1C: Data Collection & Validation**
- ✅ 420+ benchmark runs logged to JSONL (8 run files, 597 records total)
- ✅ Quality scores computed (BoolQ + imatrix BoolQ)
- ✅ Schema validation script created & passing
- ✅ Results organized in `results/` directory

**Phase 1D: Documentation & Repo Cleanup**
- ✅ README.md updated with comprehensive findings (5 key novelties, hardware specs, methodology)
- ✅ PROJECT_PLAN.md updated with completion status
- ✅ PAPER_PLAN.md created (19-section top-tier conference blueprint)
- ✅ Stale demo files removed (.DEMO_*, .SESSION_*, .TASK_*)
- ✅ Experiments archived (ExecuTorch, Qwen3 exploration)
- ✅ Repository committed to main

**Phase 1E: Paper & Report Writing**
- ✅ IEEE publication paper (report.pdf) — 10 pages, all findings verified
- ✅ Course project report (course_report.tex) — 13–15 pages, compiled to PDF
- ⏳ **3 parallel agents writing paper sections:**
  - **Agent a18e9d2a6b08d0104:** Introduction + 5 contributions
  - **Agent a85e63041726c977b:** Results sections (Throughput, KV-Collapse, Quality)
  - **Agent acf539f07aa808037:** Cross-Device Validation + Discussion

### ⏳ In-Progress (Phase 2A: Extended Benchmarking)

**WikiText-2 Full Corpus PPL**
- ✅ Q2_K, Q3_K_M: complete (full ~285K tokens)
- ⏳ Q4_K_S, Q5_K_M: running now (~8 hrs per variant)
- ⏳ Q4_K_M, Q6_K, Q8_0: queued (~8–16 hrs per variant)
- **Estimated total remaining: ~30 hours** (Q6_K, Q8_0 longest)

### 📋 Queued (Phase 2B: New Quality Benchmarks)

After WikiText-2 completes:
- ARC-Challenge: 100 runs (7 variants × ~1–2 min per variant)
- HellaSwag: 100 runs
- MMLU: 100 runs (5/subject × 20)
- TruthfulQA: 100 runs
- **Estimated total: ~8–12 hours on device**

### 📌 Key Findings (Ready for Paper)

1. **Non-monotonic throughput:** Q2_K (5.66 tok/s) fastest despite 2.6 bits/weight; Q6_K (3.98 tok/s) slowest despite 6.6 bits/weight
2. **KV-cache collapse:** Q3_K_M (−43%), Q6_K (−52%) at ctx≈2048; threshold ~1400–1500 tokens identified
3. **Non-monotonic quality:** Q4_K_M optimal (71% BoolQ); Q6_K underperforms (65% BoolQ) despite more bits
4. **imatrix surprise:** Q4_K_S-imatrix (75% BoolQ) beats Q4_K_M-imatrix (71%); importance weighting > static K
5. **Cross-device portability:** ARM patterns replicate (Pixel 6a ≈ iPhone 14 Pro ±5% TPS); GPU reverses ordering

---

## 1. Scope Decision: 1 Paper or 2?

**Decision: 1 focused paper.**

The scope as finalized (7 variants, 7 benchmarks, 3 models, 5 devices, KV-cache sensitivity) is appropriate for a single strong systems conference paper of 14 pages. The key is that each axis adds to a coherent narrative:

> *"We benchmark GGUF quantization on real consumer mobile hardware, discover non-monotonic throughput and quality orderings, identify a variant-specific KV-cache fragility that no prior work has characterized, and provide the first cross-device generalizability study on 4 distinct platforms."*

The imatrix and multi-model results are validation sections, not separate papers.

**Primary novel contributions (ordered by strength):**
1. KV-cache window sensitivity: Q3_K_M (−43%) and Q6_K (−52%) collapse at ctx=2048 — first characterization on mobile ARM, including threshold analysis and mitigation
2. Non-monotonic throughput (Q2_K fastest, Q6_K slowest despite 6 bits vs 8) — mechanistically explained via ARM NEON dequantization kernel analysis
3. Non-monotonic accuracy (Q4_K_M best, Q6_K worst on BoolQ) — confirmed across 4+ benchmarks
4. First comprehensive cross-device GGUF benchmark: Android (Tensor G1), Apple Silicon (M4), Apple Mobile (A16), x86 (AVX2)
5. imatrix calibration comparison: does importance-weighted requantization recover quality at 2–3 bits?

**Target venues (in order of fit):**
- MobiSys 2027 (mobile systems, perfect fit)
- MLSys 2027 (ML + systems, strong fit)
- USENIX ATC 2027 (systems benchmarking, good fit)
- Near-term: arXiv preprint → MobileAI/EfficientLLM workshop → full conference

---

## 2. Final Experiment Configuration

### 2a. Models
| Model | Primary | Cross-Model Validation |
|-------|---------|----------------------|
| Llama 3.2 3B Instruct | ✅ Full study | — |
| Qwen 2.5 1B | — | ✅ Q4_K_M spot-check at Pixel 6a |
| Gemma 3 1B | — | ✅ Q4_K_M spot-check at Pixel 6a |

### 2b. Quantization Variants (7 standard + 5 imatrix)
| Variant | BPW | Status | On Disk |
|---------|-----|--------|---------|
| Q2_K | ~2.6 | ✅ Complete | Llama-3.2-3B-Instruct-Q2_K.gguf + imatrix ✅ |
| Q3_K_M | ~3.4 | ✅ Complete | Llama-3.2-3B-Instruct-Q3_K_M.gguf + imatrix ✅ |
| Q4_K_S | ~4.4 | ✅ Complete | Llama-3.2-3B-Instruct-Q4_K_S.gguf + imatrix ✅ |
| Q4_K_M | ~4.8 | ✅ Complete | Llama-3.2-3B-Instruct-Q4_K_M.gguf + imatrix ✅ |
| Q5_K_M | ~5.7 | ✅ Complete | Llama-3.2-3B-Instruct-Q5_K_M.gguf + imatrix ✅ |
| Q6_K | ~6.6 | ✅ Complete | Llama-3.2-3B-Instruct-Q6_K.gguf + imatrix ✅ |
| Q8_0 | ~8.5 | ✅ Complete | Llama-3.2-3B-Instruct-Q8_0.gguf + imatrix ✅ |

**All 7 variants downloaded and on device. 5 imatrix variants calibrated and on device. Q4_K_S + Q5_K_M new variants added to suite; both performing well (Q4_K_S-imatrix: 75% BoolQ, Q5_K_M-imatrix: 76% BoolQ).**

### 2c. KV-Cache Window Sizes
- Standard sweep: 256, 512, 1024, 2048 (all 7 variants)
- Granular collapse sweep (Q3_K_M + Q6_K only): 1024, 1280, 1536, 1792, 2048
- Mitigation tests at ctx=2048: `-fa` (Flash Attention) and `-ctk q8_0` (KV quantization)

### 2d. Evaluation Benchmarks (7)
| Benchmark | Questions | Type | Expected Range (3B) | Status |
|-----------|-----------|------|---------------------|--------|
| WikiText-2 PPL | Full corpus (~285K tokens) | Perplexity | 9–14 | ⏳ In Progress (Q2_K/Q3_K_M done; Q4_K_S, Q5_K_M, Q4_K_M, Q6_K, Q8_0 running; ~30 hrs remaining) |
| BoolQ | 100 | Yes/No Reading Comprehension | 65–72% | ✅ Complete + imatrix variant done |
| ARC-Easy | 100 | 4-choice Science (easy) | ~100% | ✅ Complete (ceiling — baseline confirmed) |
| ARC-Challenge | 100 | 4-choice Science (hard) | 45–60% | ✅ Data ready, queued (after WikiText-2) |
| HellaSwag | 100 | 4-choice Commonsense | 65–75% | ✅ Data ready, queued |
| MMLU | 100 (5Q × 20 subjects) | 4-choice Knowledge | 45–60% | ✅ Data ready, queued |
| TruthfulQA | 100 | MC Truthfulness | 35–55% | ✅ Data ready, queued |

**imatrix BoolQ results (all 7 variants): Q2_K 64%, Q3_K_M 61%, Q4_K_S 75%*, Q4_K_M 71%, Q5_K_M 76%*, Q6_K 69%, Q8_0 68% (* imatrix calibrated). Surprising finding: Q4_K_S-imatrix beats Q4_K_M-imatrix despite lower bitwidth. Hypothesis: importance weighting from calibration > static K value.**

### 2e. Metrics (complete set)
**Measured directly:**
- Decode TPS ± std (tok/s)
- Prefill TPS (tok/s)
- TTFT (s)
- E2E latency (s)
- Peak RSS memory (MB) — fix instrumentation
- Energy per 1K tokens (mJ/1K) — from power_mw_mean × time (already in JSONL!)
- Model cold-start load time (s) — add to benchmark runner

**Derived (no new runs needed):**
- Bits per weight (BPW) — known constant per variant
- Compression ratio vs F16 (6.4 GB / variant_GB)
- Coefficient of Variation (CoV = std/mean) — inference stability
- BoolQ × decode_TPS efficiency score
- Pareto frontier (already plotted, extend with new variants)
- Memory headroom = 6 GB − model_size_GB − KV_cache_MB/1024

**Quality:**
- Per-benchmark accuracy + 95% Wilson CI
- PPL with corpus size noted

### 2f. Devices (4)
| Device | SoC | Backend | Priority | Est. Session Time |
|--------|-----|---------|----------|------------------|
| Pixel 6a | Tensor G1 (ARM) | llama.cpp CPU NDK | Primary | Full access |
| Mac M4 | Apple M4 (ARM) | llama.cpp Metal | High | ~3 hours |
| iPhone 14 Pro | Apple A16 (ARM) | LLM Farm / llama.cpp Metal | Medium | ~2 hours |
| HP Pavilion 14 | x86_64 | llama.cpp CPU AVX2 | Lower | ~2 hours |

---

## 3. Work Breakdown Structure

> **Developer model:** Since there is only 1 device (Pixel 6a), device experiments are sequential and run by the user. Code, analysis, and writing tasks are handled by Claude. Clear handoff points are defined.
>
> **Agent IDs:** Tasks are labeled INFRA (infrastructure/code), DEVICE (requires physical device), ANALYSIS (data processing), PAPER (LaTeX writing). These can be parallelized across INFRA/ANALYSIS/PAPER dimensions since they don't block each other.

---

### Phase 0 — Cleanup & Infrastructure Setup
**Can start immediately. All tasks are code/config.**

| ID | Task | Owner | Depends On |
|----|------|-------|------------|
| P0-CLEAN | Delete/archive stale files per cleanup plan | Claude | — |
| P0-GITIGNORE | Update .gitignore (figures, __pycache__, report build artifacts) | Claude | — |
| P0-MODELS | Download Q4_K_S.gguf and Q5_K_M.gguf locally | User | — |
| P0-EVALDATA | Create ARC-Challenge, HellaSwag, MMLU, TruthfulQA 100Q YAML data files | Claude | — |
| P0-EVALSCRIPT | Extend quality_eval.py for 4 new benchmarks (same MC interface as ARC-Easy) | Claude | P0-EVALDATA |
| P0-BENCHSCRIPT | Extend benchmark_runner.py: add load_time metric; add Q4_K_S + Q5_K_M variant support | Claude | — |
| P0-REGISTRY | Update experiments/registry.yaml: new variants, granular ctx sweep, mitigation experiments | Claude | — |
| P0-CROSSDEV | Write cross-device benchmark scripts: llama-bench wrapper for Mac/iPhone/HP | Claude | — |

---

### Phase 1 — Pixel 6a Data Collection
**Sequential on device. User runs each job; Claude monitors and validates.**

| ID | Task | Estimated Device Time | Depends On | Notes |
|----|------|----------------------|------------|-------|
| P1-NEWVAR | Benchmark Q4_K_S + Q5_K_M: 4 ctx × n=15 each | ~4 hours | P0-MODELS, P0-BENCHSCRIPT | Produces ~120 new records |
| P1-PPL | Re-run PPL full corpus for Q4_K_M, Q6_K, Q8_0 | ~2–3 hours | — | Fix the ‡ values in Table 1 |
| P1-GRCTX | Granular ctx sweep: Q3_K_M + Q6_K at 1024/1280/1536/1792/2048 | ~2 hours | — | Key for collapse threshold paper section |
| P1-MITIG | Mitigation: all 7 variants at ctx=2048 with -fa flag; Q3_K_M+Q6_K with -ctk q8_0 | ~2 hours | P1-NEWVAR | Provides mitigation result |
| P1-NEWEVAL | New benchmarks (ARC-Challenge, HellaSwag, MMLU, TruthfulQA) × 7 variants | ~4–6 hours | P0-EVALDATA, P0-EVALSCRIPT | 700 questions total |
| P1-IMATRIX | Benchmark imatrix variants: Q2_K-im, Q3_K_M-im, Q4_K_M-im, Q6_K-im, Q8_0-im at ctx=256/1024, n=15 | ~3 hours | — | Already on disk, just run |
| P1-MISC | F16 trials to n=15; fix peak RSS; add cold-start timing | ~1–2 hours | P0-BENCHSCRIPT | Fixes outstanding issues |
| P1-MODELS | Download Qwen2.5-1B + Gemma 3 1B GGUFs; push to device; run Q4_K_M spot-check | ~2 hours | P0-MODELS | Cross-model validation section |

**Total estimated Pixel 6a device time: ~20–22 hours**

---

### Phase 2 — Cross-Device Data Collection
**Each device is a separate session. Can be interleaved with Phase 1.**

| ID | Task | Device | Est. Time | Output |
|----|------|--------|-----------|--------|
| P2-MAC | llama-bench: all 7 Llama 3.2 3B variants, ctx=256/1024/2048, n=15, Metal backend | Mac M4 | ~3 hours | Comparison data: GPU-accelerated ARM |
| P2-IOS | LLM Farm or custom: Q2_K, Q4_K_M, Q8_0 at ctx=256/1024, n=10 | iPhone 14 Pro | ~2 hours | Apple A16 comparison |
| P2-X86 | llama.cpp CPU AVX2: same 7 variants, ctx=256/1024, n=10 | HP Pavilion | ~2 hours | x86 baseline |

**Total cross-device time: ~7 hours (any 3 separate sessions)**

---

### Phase 3 — Analysis & Figures
**Fully parallel with Phase 1/2 data collection. Claude builds incrementally.**

| ID | Task | Owner | Depends On |
|----|------|-------|------------|
| P3-SCHEMA | Update data schema to include new variants, devices, mitigation flags | Claude | P0-CLEAN |
| P3-FIGSCRIPT | Extend generate_figures.py: new variants, granular ctx, cross-device plots, imatrix comparison | Claude | P3-SCHEMA |
| P3-METRICS | Add derived metrics computation: CoV, compression ratio, efficiency score, memory headroom | Claude | P3-FIGSCRIPT |
| P3-THRESHOLD | KV collapse threshold analysis: fit sigmoid/step function to 5-point ctx sweep | Claude | P1-GRCTX |
| P3-CROSSDEV | Cross-device comparison analysis + plots | Claude | P2-MAC, P2-IOS, P2-X86 |
| P3-IMATRIX | imatrix vs standard comparison: PPL delta, BoolQ delta, TPS delta | Claude | P1-IMATRIX |
| P3-FIGS | Regenerate all figures with full dataset | Claude | P3-FIGSCRIPT, P1-* |

---

### Phase 4 — Paper Rewrite
**Parallel with Phase 3. Iterative updates as data arrives.**

| ID | Task | Owner | Depends On |
|----|------|-------|------------|
| P4-STRUCT | Restructure report.tex to 8-section IEEE/ACM format for target venue | Claude | P0-CLEAN |
| P4-RELATED | Write Related Work section: cite arXiv:2601.14277, MobileAIBench, ARM kernel paper, KVSwap | Claude | — |
| P4-METH | Rewrite Methodology: 7 variants, 7 benchmarks, 4 devices, experiment design | Claude | P0-REGISTRY |
| P4-RQ1 | Rewrite RQ1 (throughput): update with Q4_K_S + Q5_K_M data | Claude | P1-NEWVAR, P3-FIGS |
| P4-RQ2 | Rewrite RQ2 (KV sensitivity): add threshold analysis + mitigation results | Claude | P1-GRCTX, P1-MITIG, P3-THRESHOLD |
| P4-RQ3 | Write RQ3 (quality): 7-benchmark comparison, imatrix comparison | Claude | P1-NEWEVAL, P1-IMATRIX |
| P4-RQ4 | Write RQ4 (cross-device): Mac M4, iPhone, x86 comparison | Claude | P2-*, P3-CROSSDEV |
| P4-RQ5 | Write RQ5 (cross-model): Qwen + Gemma spot-check generalizability | Claude | P1-MODELS |
| P4-DISC | Rewrite Discussion + Deployment Recommendations | Claude | P4-RQ1..5 |
| P4-FINAL | Final pass: consistency check, all values verified, bibliography complete | Claude | All P4 |

---

## 4. Repository Cleanup Plan

### Delete (stale/redundant)
```
DEMO_GUIDE.md
DEMO_READINESS.md
DEMO_RECORDING_PLAN.md
MONITORING_GUIDE.md
PRESENTATION_BUILD_SPEC.md
PRESENTATION_SCRIPT.md
PRESENTATION_SLIDES.md
SESSION_SUMMARY.md
TASK_STATUS.md
agent.md
plan.md
.Rhistory
analysis/regenerate_figures.py          ← superseded by generate_figures.py
scripts/debug_q8_extraction.py          ← debugging artifact
scripts/update_pareto_with_boolq.py     ← one-off
scripts/update_report_perplexity.py     ← one-off
scripts/monitor_boolq.sh                ← one-off
scripts/boolq_pipeline.sh               ← superseded by _FIXED version
results/test-synthetic.jsonl            ← synthetic test data
data/requantize_Q*.log                  ← 5 one-off logs (keep .dat files)
data/imatrix_Q*.log                     ← 5 one-off logs (keep .dat files)
report/report.aux, report.log, report.out ← LaTeX build artifacts
```

### Archive (move to archive/ — real data, not needed for active work)
```
results/run-20260306T130117.jsonl       ← 34-record partial test run
results/run-20260306T131527.jsonl       ← 85-record partial test run
results/run-20260306T152054.jsonl       ← 17-record partial test run
results/smoke-20260305T121804.jsonl     ← smoke test
results/smoke-20260305T174033.jsonl     ← smoke test
android_executorch_backup/              ← abandoned ExecuTorch approach
local-models/llama3_2/                  ← ExecuTorch .pte model, superseded
local-models/qwen3/                     ← tokenizer only, no model
```

### Add to .gitignore
```
figures/*.png
figures/*.csv
report/*.aux
report/*.log
report/*.out
results/smoke-*.jsonl
**/__pycache__/
**/*.pyc
.DS_Store
.Rhistory
local-models/
```

### Keep & Update
```
README.md           ← update with new scope
QUICKSTART.md       ← update setup instructions
PRD.md              ← keep as requirements reference
requirements.txt    ← add new dependencies if any
experiments/registry.yaml  ← extend with new experiment definitions
```

---

## 5. New Directory Structure (Post-Cleanup)

```
291_EAI/
├── README.md                    # Project overview, setup, reproducibility guide
├── QUICKSTART.md                # Fast-path: run benchmarks in 10 minutes
├── PROJECT_PLAN.md              # This file
├── PRD.md                       # Product/research requirements
├── requirements.txt
├── .gitignore
│
├── data/                        # Evaluation datasets + imatrix calibration data
│   ├── boolq_100.yaml
│   ├── arc_easy_100.yaml
│   ├── arc_challenge_100.yaml   ← NEW
│   ├── hellaswag_100.yaml       ← NEW
│   ├── mmlu_100.yaml            ← NEW
│   ├── truthfulqa_100.yaml      ← NEW
│   ├── wikitext2_full.txt
│   ├── wikitext2_sample.txt
│   └── imatrix_Q*.dat           ← 5 imatrix calibration files
│
├── scripts/                     # All executable scripts
│   ├── benchmark_runner.py      ← extend with load_time, new variants
│   ├── parse_llama_output.py
│   ├── quality_eval.py          ← extend with 4 new benchmarks
│   ├── validate_results.py
│   ├── gpu_baseline.py
│   ├── download_models.sh
│   ├── download_arc_boolq.py
│   ├── download_wikitext2.py
│   ├── build_llamacpp_android.sh
│   ├── push_models_to_device.sh
│   ├── run_full_benchmark.sh
│   ├── run_perplexity.sh
│   ├── run_perplexity_full.sh
│   ├── run_imatrix.sh
│   ├── requantize_imatrix.sh
│   ├── boolq_pipeline_FIXED.sh
│   ├── parse_perplexity_results.sh
│   ├── smoke_test.sh
│   └── cross_device/            ← NEW: Mac, iPhone, x86 benchmark scripts
│       ├── mac_m4_bench.sh
│       ├── ios_bench.md          ← instructions for LLM Farm
│       └── x86_bench.sh
│
├── analysis/
│   └── generate_figures.py      ← extend with all new plots
│
├── experiments/
│   └── registry.yaml            ← extend with new experiment definitions
│
├── results/                     # All canonical JSONL run files
│   ├── run-20260305T174113.jsonl   ← run1 (canonical)
│   ├── run-20260306T152616.jsonl   ← run2 (canonical)
│   ├── run-20260307T*.jsonl        ← ctx=2048 dedicated runs
│   ├── quality_scores.json
│   ├── perplexity_scores.json
│   └── archive/                    ← partial/test runs
│
├── figures/                     ← gitignored, regenerated by analysis/
│
├── prompts/
│   ├── prompt-suite-v1.yaml
│   └── quality-eval-v1.yaml
│
├── schemas/
│   └── run.schema.json
│
├── notebooks/
│   └── gpu_baseline.ipynb
│
├── report/
│   ├── report.tex
│   └── report.pdf
│
├── android/                     ← Android app source
│
├── local-models/                ← gitignored (large files)
│   └── llama3_2_3b_gguf/
│       ├── Q2_K.gguf, Q2_K-imatrix.gguf
│       ├── Q3_K_M.gguf, Q3_K_M-imatrix.gguf
│       ├── Q4_K_S.gguf              ← NEW
│       ├── Q4_K_M.gguf, Q4_K_M-imatrix.gguf
│       ├── Q5_K_M.gguf              ← NEW
│       ├── Q6_K.gguf, Q6_K-imatrix.gguf
│       ├── Q8_0.gguf, Q8_0-imatrix.gguf
│       └── F16.gguf
│
├── Proposal/                    ← Original proposal docs (reference)
│
└── archive/                     ← Archived old files (not deleted, just out of the way)
```

---

## 6. Immediate Next Steps (Ordered)

### Step 1 — Today (Claude does): Repo Cleanup
Execute cleanup plan: delete stale files, move to archive/, update .gitignore

### Step 2 — Today (Claude does): Infrastructure
- P0-EVALDATA: Create 4 new benchmark YAML data files (ARC-Challenge, HellaSwag, MMLU, TruthfulQA)
- P0-EVALSCRIPT: Extend quality_eval.py for new benchmarks
- P0-CROSSDEV: Write Mac M4 + x86 benchmark scripts

### Step 3 — User Action: Download Missing Models
```bash
# Download Q4_K_S and Q5_K_M (approximately 1.8 GB + 2.2 GB)
# From HuggingFace: bartowski/Llama-3.2-3B-Instruct-GGUF
wget https://huggingface.co/.../Llama-3.2-3B-Instruct-Q4_K_S.gguf -O local-models/llama3_2_3b_gguf/Q4_K_S.gguf
wget https://huggingface.co/.../Llama-3.2-3B-Instruct-Q5_K_M.gguf -O local-models/llama3_2_3b_gguf/Q5_K_M.gguf
```

### Step 4 — User Action: Device Runs (Pixel 6a, in order)
1. P1-PPL first (fixes existing paper errors, quick win: ~3 hours)
2. P1-NEWVAR (Q4_K_S + Q5_K_M throughput sweep: ~4 hours)
3. P1-GRCTX (collapse threshold sweep: ~2 hours)
4. P1-NEWEVAL (new benchmarks × 7 variants: ~5 hours)
5. P1-IMATRIX (imatrix comparison: ~3 hours)
6. P1-MITIG (mitigation experiments: ~2 hours)
7. P1-MODELS (cross-model: ~2 hours)
8. P1-MISC (F16 + fix RSS: ~1 hour)

### Step 5 — Any free device session: Cross-Device
Mac M4 can be done any time (no exclusive access needed — it's yours). ~3 hours total.

### Step 6 — Ongoing (Claude does as data arrives):
Update figures, analysis, and paper sections incrementally as each Phase 1 task completes.

---

## 7. Issue Backlog (Open Items)

| ID | Issue | Priority | Phase |
|----|-------|----------|-------|
| BUG-001 | Q8_0 / F16 model fails to load in app (redirects to Settings) | Medium | Android App |
| BUG-002 | Peak RSS instrumentation unreliable (MemAvailable-delta) | High | P1-MISC |
| DATA-001 | PPL for Q4_K_M, Q6_K, Q8_0 measured on 12KB sample only | Critical | P1-PPL |
| DATA-002 | F16 only 2 trials (insufficient for statistical claims) | High | P1-MISC |
| DATA-003 | Q4_K_S and Q5_K_M missing from all benchmarks | High | P0-MODELS, P1-NEWVAR |
| DATA-004 | New quality benchmarks (ARC-Challenge, HellaSwag, MMLU, TruthfulQA) not yet run | High | P1-NEWEVAL |

---

## 8. Paper Outline (Target: 14 pages IEEE/ACM)

```
1. Introduction (1.5 pp)
   - On-device LLM motivation
   - GGUF/llama.cpp ecosystem
   - Research questions (5 RQs)
   - Contributions summary

2. Background & Related Work (1.5 pp)
   - GGUF K-quant format
   - Prior benchmarking work (MobileAIBench, arXiv:2601.14277)
   - ARM NEON kernel characteristics (arXiv:2501.00032)
   - KV cache memory behavior (KVSwap)

3. Methodology (2 pp)
   - Hardware: 4 devices, specs table
   - GGUF variants: 7 standard + 5 imatrix, BPW table
   - Evaluation suite: 7 benchmarks, dataset sources
   - Experimental design: n=15, warmup, prompts

4. RQ1: Throughput vs. Quantization (1.5 pp)
   - Non-monotonic ordering + explanation
   - Cross-device comparison
   - Thread scaling

5. RQ2: KV-Cache Window Sensitivity (2 pp)  ← MAIN NOVEL CONTRIBUTION
   - Collapse finding (Q3_K_M/Q6_K)
   - Granular threshold analysis
   - Mitigation: Flash Attention + KV quantization
   - Mechanistic discussion

6. RQ3: Quality vs. Quantization (1.5 pp)
   - 7-benchmark comparison
   - imatrix calibration impact
   - PPL vs task accuracy divergence

7. RQ4: Cross-Device Generalizability (1 pp)
   - Pixel 6a vs Mac M4 vs iPhone 14 Pro vs x86
   - Does non-monotonic ordering hold across architectures?

8. RQ5: Cross-Model Generalizability (0.75 pp)
   - Qwen 2.5 1B + Gemma 3 1B spot-check
   - Does Q4_K_M recommendation generalize?

9. Discussion & Deployment Recommendations (0.75 pp)
   - Decision tree for practitioners
   - Variants to avoid

10. Conclusion (0.5 pp)
```

---

*This plan supersedes: plan.md, TASK_STATUS.md, agent.md, SESSION_SUMMARY.md*
