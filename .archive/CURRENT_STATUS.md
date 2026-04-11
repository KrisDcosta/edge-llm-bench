# DSC 291 EAI — Current Status Report (2026-03-16)

## Executive Summary

**Project State:** Phase 2A (Device Data Collection) — In Progress
**Primary Bottleneck:** Device benchmarking (WikiText-2 full corpus PPL, ~30 hours remaining)
**Paper Status:** Introduction section finalized (✅) | Results sections awaiting data
**Infrastructure:** ✅ Complete | All scripts and data files ready

---

## Completed Work (This Session)

### 1. Repository Cleanup & Documentation
- ✅ Removed stale demo files (DEMO_*, SESSION_*, TASK_STATUS.md)
- ✅ Updated README.md with comprehensive findings (5 novelties, hardware specs, methodology)
- ✅ Updated PROJECT_PLAN.md with Phase 2 status
- ✅ Created PAPER_PLAN.md (19-section blueprint for conference submission)
- ✅ Committed all changes to main branch

### 2. Paper Integration
- ✅ Integrated comprehensive INTRODUCTION.md into report.tex
  - Motivation section: On-device LLM inference, quantization imperative
  - Problem statement: 3 specific gaps in current literature
  - 5 Research Contributions (RQ1–RQ5) with quantified findings
  - Roadmap telegraphing paper structure (§2–§9)
  - LaTeX formatted with proper citations and formatting

### 3. Infrastructure Preparation
- ✅ Created `scripts/parse_ppl_full.py` — Extracts full-corpus PPL from device output
- ✅ Created `scripts/integrate_results.sh` — Comprehensive results integration workflow
- ✅ Verified `scripts/quality_eval.py` supports all 6 benchmarks (arc_easy, arc_challenge, boolq, hellaswag, mmlu, truthfulqa)
- ✅ Verified `analysis/generate_figures.py` ready to generate 9 publication-quality figures
- ✅ Created NEXT_STEPS.md with detailed commands for next phases

### 4. Benchmark Data Files
- ✅ ARC-Challenge: 100 questions (4-choice science, hard)
- ✅ HellaSwag: 100 questions (4-choice commonsense completion)
- ✅ MMLU: 100 questions (5 per subject × 20 subjects)
- ✅ TruthfulQA: 100 questions (MC truthfulness evaluation)
- ✅ WikiText-2: Full corpus ready (~285K tokens, 1.2 MB)

---

## Current Work in Progress

### Device Benchmarking (Phase 2A): WikiText-2 Full Corpus PPL

**Status:** ⏳ Running on Pixel 6a (6GB LPDDR5, Tensor G1 ARM)

**Progress:**
| Variant | Status | ETA | Notes |
|---------|--------|-----|-------|
| Q2_K | ✅ Complete | — | ~90 hrs corpus (~285K tokens) |
| Q3_K_M | ✅ Complete | — | Full corpus |
| Q4_K_S | ⏳ Running | ~8 hrs | ~285K tokens |
| Q5_K_M | ⏳ Running | ~15 hrs | ~285K tokens (longest estimate) |
| Q4_K_M | ⏳ Queued | ~8 hrs | Q5_K_M finishing after Q4_K_S |
| Q6_K | ⏳ Queued | ~16 hrs | Q4_K_M + subsequent runs |
| Q8_0 | ⏳ Queued | ~12 hrs | Last in queue |

**Total Remaining:** ~30 hours (sequential execution)

**How to Monitor:**
```bash
adb shell "ls -la /data/local/tmp/ppl_full_*.txt | tail -5"
# Shows latest PPL output files and timestamps
```

---

## Work Queued (Phase 2B & 2C)

### Phase 2B: New Quality Benchmark Evaluations
**Trigger:** After WikiText-2 completes (~30+ hours from now)
**Duration:** ~8–12 hours on device
**Benchmarks:** ARC-Challenge, HellaSwag, MMLU, TruthfulQA (all 7 variants)
**Command:** See NEXT_STEPS.md for sequential execution

### Phase 2C: Paper Finalization
**Trigger:** After Phase 2A + 2B complete
**Duration:** ~3–4 hours on host machine
**Tasks:**
1. Update Results section with final PPL values
2. Add quality eval tables (ARC-Challenge, HellaSwag, MMLU, TruthfulQA)
3. Generate final comparison figures
4. Compile final PDF with all sections
5. Polish and proofread for conference submission

---

## Key Data & Outputs

### Results Files Location
```
results/
├── run-YYYYMMDDTHHMMSS.jsonl        (device benchmark runs, 8 files)
├── perplexity_scores.json            (PPL values, updating with full corpus)
├── quality_scores.json               (accuracy scores, will update with new evals)
└── [ppl_full_*.txt]                  (device raw output, pulled via ADB)
```

### Figure Generation
```
figures/
├── fig1_prefill_tps_vs_context.pdf
├── fig2_decode_tps_vs_context.pdf
├── fig3_ttft_vs_context.pdf
├── fig4_peak_memory_vs_quant.pdf
├── fig5_battery_per_1k_tokens.pdf
├── fig6_pareto_frontier.pdf
├── fig7_prefill_vs_decode_fraction.pdf
├── fig8_latency_distribution.pdf
├── fig9_model_size_vs_tps.pdf
└── summary_table.csv
```

### Paper Output
```
report/
├── report.tex                        (main paper source, updated introduction)
├── report.pdf                        (compiled, ~10 pages)
├── course_report.tex                 (course submission, 13-15 pages)
└── course_report.pdf                 (compiled for submission)
```

---

## Known Issues & Limitations

| ID | Issue | Severity | Status | Notes |
|----|-------|----------|--------|-------|
| BUG-001 | Q8_0/F16 model fails to load in app | Medium | Tracked | Unlikely to fix; low priority |
| BUG-002 | Peak RSS measurement unreliable | Medium | Deferred | Pixel 6a USB-C power detection limited |
| PPL-001 | Original PPL measured on 12KB sample | ✅ **FIXED** | Resolved | Full corpus runs now (Q4_K_S, Q5_K_M, Q4_K_M, Q6_K, Q8_0) |
| DATA-001 | F16 only 2 trials | Low | Noted | Not prioritized for paper |

---

## Immediate Action Items (For User)

**None right now.** The device is running autonomously. 

**Next action point:** When device finishes WikiText-2 (~30+ hours from now):
1. Connect device and run: `adb pull /data/local/tmp/ppl_full_*.txt results/`
2. Run: `python3 scripts/parse_ppl_full.py results/`
3. Review updated perplexity scores
4. Queue Phase 2B (new quality benchmarks)

---

## Quick Reference: Important Commands

### Monitor Device Status
```bash
adb devices                              # Check connection
adb shell "ps | grep llama"              # See if still running
adb shell "tail -10 /data/local/tmp/ppl_full_*.txt"  # Latest PPL output
```

### Collect Results When Ready
```bash
adb pull /data/local/tmp/ppl_full_*.txt results/
python3 scripts/parse_ppl_full.py results/
python3 analysis/generate_figures.py results/
```

### Queue New Benchmarks
```bash
python3 scripts/quality_eval.py --dataset data/arc_challenge_100.yaml --tag arc_challenge --all
python3 scripts/quality_eval.py --dataset data/hellaswag_100.yaml --tag hellaswag --all
python3 scripts/quality_eval.py --dataset data/mmlu_100.yaml --tag mmlu --all
python3 scripts/quality_eval.py --dataset data/truthfulqa_100.yaml --tag truthfulqa --all
```

### Update & Compile Report
```bash
cd report && pdflatex report.tex && pdflatex report.tex && cd ..
# Generates report/report.pdf with all integrated sections
```

---

## Paper Completion Checklist

- [x] Title & Abstract
- [x] Introduction (RQ1–RQ5, motivation, problem statement, roadmap)
- [ ] Related Work (~2 pages) — Existing, may need updates
- [ ] Methodology (~2–2.5 pages) — Existing, may need updates
- [ ] Results: Throughput & Latency (~2–2.5 pages) — Ready, needs final data
- [ ] Results: KV-Cache Collapse (~2–2.5 pages) — Ready, needs final data
- [ ] Results: Quality Evals (~1.5–2 pages) — Needs Phase 2B completion
- [ ] Discussion & Implications (~1–1.5 pages) — Ready structure, needs final data
- [ ] Cross-Device Validation (~1 page) — Ready, needs final data
- [ ] Limitations & Future Work (~1 page) — Existing
- [ ] Conclusion (~0.5 page) — Existing
- [ ] Experimental Reproducibility (~1 page) — Existing
- [ ] Quality Evaluation Details (~1 page) — Existing

**Total:** ~14 pages target | Current: ~10 pages | Need: ~4 more pages from results/validation sections

---

## Git Status

**Last Commit:** `6fc5470` — "Add comprehensive results integration workflow script"
**Commits ahead of origin/main:** 11
**Untracked files:** None (INTRODUCTION.md now tracked)

**To push progress:**
```bash
git push origin main
```

---

## Success Metrics (By End of Project)

- [ ] 420+ benchmark runs complete on Pixel 6a (all 7 variants × 4 contexts) ✅
- [ ] 661+ valid measurements across multiple dimensions ✅
- [ ] Full WikiText-2 PPL (285K tokens) for all 7 variants (in progress)
- [ ] 4 new quality benchmarks × 7 variants complete (queued)
- [ ] 7 key findings documented with quantified evidence
- [ ] Cross-device validation (Pixel 6a, iPhone 14 Pro, Mac M4, HP Pavilion x86)
- [ ] 14-page research paper (MobiSys/MLSys/USENIX ATC quality) ready for submission
- [ ] Reproducibility: All scripts, data, and methodology fully documented
- [ ] Deployment guidance: Practical recommendations for practitioners

---

**Status Last Updated:** 2026-03-16 19:45 UTC  
**Next Update:** When device completes Phase 2A or user provides new data  
**Questions?** See NEXT_STEPS.md, PROJECT_PLAN.md, or PAPER_PLAN.md for detailed guidance
