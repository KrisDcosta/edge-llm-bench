# DSC 291 EAI — Current Status & Next Steps

**Current Date:** 2026-03-16 | **Phase:** 2A (WikiText-2 PPL) | **Device Status:** Running (~30 hrs remaining)

---

## Phase 2A: WikiText-2 Full Corpus PPL (In Progress)

**Status:** Device is running perplexity measurements on full 285K-token corpus

**Completion Status:**
- ✅ Q2_K, Q3_K_M: Complete
- ⏳ Q4_K_S, Q5_K_M: Running (~8 hrs per variant)
- ⏳ Q4_K_M, Q6_K, Q8_0: Queued (~8–16 hrs per variant)
- **Total remaining: ~30 hours**

**What to do when device finishes:**
```bash
# 1. Pull results from device
adb pull /data/local/tmp/ppl_full_*.txt results/

# 2. Parse and update results/perplexity_scores.json
python3 scripts/parse_ppl_full.py

# 3. Update report figures and tables with final PPL values
cd report && pdflatex report.tex && pdflatex report.tex
```

---

## Phase 2B: New Quality Benchmarks (Queued)

**Status:** Ready to run after WikiText-2 completes

**Benchmarks ready:**
- ✅ ARC-Challenge: 100 questions (data/arc_challenge_100.yaml)
- ✅ HellaSwag: 100 questions (data/hellaswag_100.yaml)
- ✅ MMLU: 100 questions (data/mmlu_100.yaml)
- ✅ TruthfulQA: 100 questions (data/truthfulqa_100.yaml)

**Commands to run sequentially (after WikiText-2 completes):**
```bash
# Push models to device first (if not already present)
for VARIANT in Q2_K Q3_K_M Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0; do
    adb push local-models/llama3_2_3b_gguf/Llama-3.2-3B-Instruct-${VARIANT}.gguf /data/local/tmp/
done

# Run quality evals sequentially (each ~1.5–2 hrs per benchmark × 7 variants)
# Total estimated: ~8–12 hours on device

python3 scripts/quality_eval.py --dataset data/arc_challenge_100.yaml --tag arc_challenge --all
python3 scripts/quality_eval.py --dataset data/hellaswag_100.yaml --tag hellaswag --all
python3 scripts/quality_eval.py --dataset data/mmlu_100.yaml --tag mmlu --all
python3 scripts/quality_eval.py --dataset data/truthfulqa_100.yaml --tag truthfulqa --all

# Results will be appended to results/quality_scores.json with keys like:
# "arc_challenge:Q2_K", "hellaswag:Q3_K_M", "mmlu:Q4_K_M", etc.
```

**Expected accuracy ranges (3B models):**
| Benchmark | Expected Range |
|-----------|-----------------|
| ARC-Challenge | 45–60% |
| HellaSwag | 65–75% |
| MMLU | 45–60% |
| TruthfulQA | 35–55% |

---

## Paper Status

**Sections completed:**
- ✅ Introduction (RQ1–RQ5, comprehensive motivation, problem statement, roadmap)
- ✅ Related Work (existing)
- ✅ Methodology (existing)
- ⏳ Results: Throughput & KV-Collapse (PAPER_PLAN.md section 5–6 outline ready)
- ⏳ Results: Quality Evals (waiting for Phase 2B to complete)
- ⏳ Discussion & Validation (waiting for all data)

**Next steps for paper:**
1. Integrate INTRODUCTION.md into report.tex (✅ Done)
2. Update Results section with updated PPL and new quality benchmark data
3. Add new benchmark tables (ARC-Challenge, HellaSwag, MMLU, TruthfulQA)
4. Generate final comparison figures (all 7 variants across 7 benchmarks)
5. Compile final PDF with all sections integrated

---

## Infrastructure Checklist

**Data files:** ✅ All complete
- ✅ Arc-Challenge, HellaSwag, MMLU, TruthfulQA YAML files
- ✅ WikiText-2 full corpus (1.2 MB, ~285K tokens)
- ✅ All 7 GGUF variants on host
- ✅ All 5 imatrix variants on host (for later Phase 3)

**Scripts:** ✅ All ready
- ✅ quality_eval.py (supports all 7 benchmarks + imatrix flag)
- ✅ benchmark_runner.py (supports all 7 variants, fixed -fa flag)
- ✅ run_perplexity_full.sh (supports all 7 variants)
- ✅ analysis/generate_figures.py (generates publication-quality plots)

**Android app:** ✅ Production ready
- ✅ Chat tab with inference
- ✅ Models tab with variant selection
- ✅ Benchmark tab (real-time trial results)
- ✅ Settings tab (persist across app restart)
- ✅ History tab + Dark/Light mode toggle (already implemented per user feedback)

---

## Critical Commands Reference

### When device completes WikiText-2:
```bash
# Collect results
adb pull /data/local/tmp/ppl_full_*.txt results/

# Validate
python3 scripts/parse_ppl_full.py results/

# Check output
cat results/perplexity_scores.json
```

### When ready to run Phase 2B (new quality benchmarks):
```bash
# Run all 4 benchmarks sequentially
for BENCHMARK in arc_challenge hellaswag mmlu truthfulqa; do
    echo "Starting $BENCHMARK..."
    python3 scripts/quality_eval.py \
        --dataset data/${BENCHMARK}_100.yaml \
        --tag $BENCHMARK \
        --all
    sleep 60  # Cool-down between benchmarks
done
```

### Update paper with new results:
```bash
cd report
pdflatex report.tex
pdflatex report.tex  # Run twice for cross-refs
cd ..
```

---

## Known Issues & Limitations

| ID | Issue | Status |
|----|-------|--------|
| BUG-001 | Q8_0 F16 model fails to load in app | Tracked (unlikely to fix) |
| BUG-002 | Peak RSS instrumentation unreliable | Deferred (Phase 3) |
| PPL-SAMPLE | Q4_K_M, Q6_K, Q8_0 originally on 12KB sample | ✅ Fixed (full corpus running) |

---

## Estimated Total Timeline

| Phase | Duration | Status |
|-------|----------|--------|
| Phase 2A (WikiText-2) | ~30 hours | ⏳ In progress |
| Phase 2B (New quality evals) | ~8–12 hours | Queued (after 2A) |
| Paper integration + final polish | ~3 hours | Ready to start |
| **Total remaining** | **~41–45 hours** | **36+ on device, ~5 on host** |

---

Generated: 2026-03-16 | Next update: When WikiText-2 completes or new results arrive
