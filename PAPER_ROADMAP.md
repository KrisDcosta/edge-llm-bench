# Paper Roadmap: GGUF K-Quant Benchmarking on CPU Inference
## Targeting: MLSys 2026 / MobiSys 2027 / USENIX ATC 2027

**Last Updated:** 2026-03-28
**Status:** Course work complete. Active pivot to conference submission.

---

## 1. Central Thesis (Updated)

> **"CPU SIMD dequantization overhead creates a CPU/GPU performance divide in GGUF K-quantized inference. On all CPU backends (ARM NEON, x86 AVX2), quantization variants exhibit triple non-monotonic behavior — throughput, KV-cache context sensitivity, and quality all defy bit-width ordering — driven by a shared SIMD kernel bottleneck. GPU backends with dedicated 4-bit dispatch paths (Metal) reverse this ordering entirely. Within the CPU regime, a filled-context cliff in Q2_K (−40% ARM, −51% x86) and the unexpected stability of Q3_K_M (<±5% across all contexts) are explained by superblock structure and its interaction with CPU cache hierarchy."**

**Why this is publishable:**
1. Novel empirical phenomenon documented across 3 hardware platforms and 700+ trials
2. Mechanistic explanation tied to CPU microarchitecture (SIMD tables, L2/L3 cache)
3. Cross-model validation (Qwen) needed — in progress
4. Directly actionable: practitioners currently choose variants by bpw; this work shows why that is wrong
5. The CPU/GPU divide is a clean, testable claim with practical implications for iOS/macOS vs Android deployment

---

## 2. Current Data Inventory

### What Exists and Is Verified ✅

| Dataset | Platform | Variants | n | Notes |
|---------|----------|----------|---|-------|
| Decode/Prefill TPS sweep | Pixel 6a ARM | All 7, ctx {256,512,1024,2048} | 10 trials | Table 1 |
| Filled-context cliff | Pixel 6a ARM | All 7, 11 ctx pts (256→2048) | 3 trials | Table 2 — n=3 is weak |
| Filled-context cliff | x86 i5-1235U | All 7, 11 ctx pts | 3 trials | §5.5 |
| TPS sweep | Mac M4 Metal | All 7, ctx {256,512,1024,2048} | 10 trials | Table 4 |
| BoolQ (100q) | Pixel 6a ARM | All 7 | — | Verified |
| ARC-Easy (100q) | Pixel 6a ARM | All 7 | — | 76–82% verified |
| ARC-Challenge (100q) | Pixel 6a ARM | All 7 | — | Verified |
| HellaSwag (100q) | Pixel 6a ARM | All 7 | — | Q2_K collapse documented |
| MMLU (100q) | Pixel 6a ARM | All 7 | — | Tight 42–50% cluster |
| TruthfulQA (100q) | Pixel 6a ARM | All 7 | — | Q3_K_M leads at 68% |
| BoolQ, ARC-Easy, ARC-Challenge, TruthfulQA | x86 i5-1235U | All 7 | — | Consistent with ARM |
| WikiText-2 PPL (full corpus) | Pixel 6a ARM | Q2_K, Q3_K_M | — | 13.29, 11.08 |
| WikiText-2 PPL (full corpus) | x86 i5-1235U | All 7 | — | 9.71–11.73 range |
| WikiText-2 PPL (12KB only) | Pixel 6a ARM | Q4_K_M, Q5_K_M, Q6_K, Q8_0 | — | ‡ in Table 1 — needs full corpus |
| WikiText-2 PPL | Pixel 6a ARM | Q4_K_S | — | ❌ Missing entirely |

### Critical Gaps ❌

| Gap | Blocks | Effort |
|-----|--------|--------|
| **Qwen 2.5 1.5B TPS + cliff on Pixel 6a** | Cross-model generalization claim | ~6h device time |
| **Root cause analysis** (superblock math, KV-cache sizing, llama.cpp kernel) | Mechanism section | ~1 day analysis |
| **Cliff threshold prediction formula** | Predictive contribution | Derived from root cause |
| **Full Pixel PPL for Q4_K_M, Q5_K_M, Q6_K, Q8_0, Q4_K_S** | Table 1 ‡ marks | ~8h overnight device |
| **M4 Metal cliff sweep** (does Metal avoid the cliff?) | CPU/GPU divide mechanistic support | ~2h M4 time |
| **n≥10 cliff trials** (currently n=3) | Statistical rigor for reviewers | ~6h device time |
| **x86 HellaSwag + MMLU** | Complete cross-device quality table | HP Pavilion pending |
| **imatrix on 3+ benchmarks** (currently BoolQ only) | RQ5 claim depth | ~4h device time |

---

## 3. What Makes This Conference-Ready (Checklist)

### Novelty ✅/❌
- [x] Novel empirical phenomenon (triple non-monotonicity) — not in literature
- [x] CPU/GPU divide established across 3 platforms
- [ ] Mechanistic explanation with quantitative support (superblock → cache → cliff)
- [ ] Cliff threshold prediction formula (quantitative model, not just observation)
- [ ] Cross-model generalization (Qwen 2.5 1.5B on Pixel)

### Rigor ✅/❌
- [x] >700 trials on primary device
- [x] Wilson 95% CI for all quality metrics
- [x] Three-platform cross-device validation
- [x] Filled-context methodology (correct KV cache saturation)
- [ ] n≥10 for cliff trials (currently n=3)
- [ ] Full-corpus PPL for all 7 Pixel variants
- [ ] Second model family

### Writing ✅/❌
- [x] Core findings written clearly
- [ ] Conference-quality related work (need 35+ citations, comparison table)
- [ ] Methodology section with full hardware specs and reproducibility
- [ ] Mechanistic analysis section (currently absent)
- [ ] Strong abstract targeting conference reviewers (shorter, punchier)
- [ ] Publication-quality figures (full matplotlib pass)

---

## 4. Prioritized Action Plan

### Phase 1 — Critical Data (Week of March 29) — DEVICE TIME NEEDED
Pixel 6a must be connected.

**4.1 — Full Pixel PPL (overnight, highest ROI)**
```bash
bash scripts/run_perplexity_full.sh Q4_K_S Q4_K_M Q5_K_M Q6_K Q8_0
```
~8 hours. Removes all ‡ from Table 1. Non-negotiable for submission.

**4.2 — Cliff n=3 → n=10 re-run**
```bash
bash scripts/bench/pixel_llama_cliff_filled.sh --trials 10
```
~6 hours. n=3 will be flagged by every reviewer.

**4.3 — Qwen 2.5 1.5B TPS sweep on Pixel**
```bash
bash scripts/bench/pixel_llama_tps.sh --model qwen  # (adapt script)
```
~4 hours. Without a second model, claims can't generalize.

**4.4 — Qwen cliff sweep on Pixel**
~3 hours. Does Qwen's smaller KV-cache (GQA, fewer heads) shift the cliff threshold?
This is the key cross-model prediction.

**4.5 — M4 Metal filled-context cliff sweep**
```bash
bash scripts/bench/m4_llama_cliff.sh
```
~2 hours. Does Metal avoid the cliff? Completes the CPU/GPU divide story mechanistically.

### Phase 2 — Root Cause Analysis (Week of April 5) — NO DEVICE NEEDED
This is pure analysis work. Most impactful per hour of work.

**4.6 — llama.cpp kernel inspection**
- Find ggml-quants.c/ggml-cpu.c — document superblock sizes per variant
- Q2_K: 256-element superblocks; Q4_K_M: 32-element; Q8_0: 32-element
- Compute expected L2 cache pressure vs measured cliff threshold

**4.7 — KV-cache size model**
For Llama 3.2 3B at cliff threshold ctx=768 (Q2_K ARM):
```
KV_size = 2 × n_layers × n_kv_heads × head_dim × ctx × sizeof(f16)
        = 2 × 28 × 8 × 64 × 768 × 2 bytes = ~44 MB
```
Compare to Tensor G1 total RAM bandwidth and cache sizes.
Build formula: `cliff_ctx(device, model) ≈ L2_cache / (2 × kv_dim_per_token)`

**4.8 — Cliff threshold prediction formula**
Derive from above. Validate on: Pixel Q3_K_M (no cliff), Q4_K_M (ctx=1024), Qwen.

### Phase 3 — Supplementary Experiments (April 5–11)
- imatrix on ARC-Challenge, HellaSwag, TruthfulQA (need to actually claim "minimal benefit")
- x86 HellaSwag + MMLU (HP Pavilion, once WiFi restored)
- Power measurement clean run (if battery data needed for energy efficiency claim)

### Phase 4 — Paper Rewrite (April 12–25)
Full conference-quality rewrite. The current 12-page course paper is the scaffold;
the conference paper is a new document that reuses verified data but rewrites every section.

Key changes from course paper:
- **Introduction:** Cut motivation, sharpen to 3 concrete unknowns → 3 findings
- **Methodology:** Add full hardware teardown, exact llama.cpp version/commit, build flags
- **New section:** Mechanistic Analysis (superblock structure, cache model, cliff prediction)
- **Results:** Restructure around CPU/GPU divide as unifying theme, not 5 separate RQs
- **Related Work:** 35+ citations, explicit comparison table showing what prior work measured vs. didn't
- **Abstract:** 150 words max, 4 findings, target MLSys reviewer mental model

### Phase 5 — Submission (April 26 – May deadline)
- Final figures (publication-quality matplotlib)
- Bibliography pass (no broken citations, proper formatting)
- Supplementary material / artifact appendix
- Submit to MLSys 2026; arXiv simultaneous

---

## 5. Target Venues and Deadlines

| Venue | Fit | Likely Deadline | Notes |
|-------|-----|-----------------|-------|
| **MLSys 2026** | Best — systems measurement paper | ~May 2026 | Verify exact date |
| **MobiSys 2027** | Strong — mobile systems | ~Jan 2027 | Fallback if MLSys misses |
| **USENIX ATC 2027** | Good — systems + measurement | ~Jan 2027 | Fallback |
| NeurIPS 2026 Efficient ML Workshop | Moderate | ~Aug 2026 | Workshop, not full paper |

---

## 6. Revised Paper Structure

**Title candidate:** "Triple Non-Monotonicity in CPU GGUF Inference: Throughput, Context Sensitivity, and Quality All Defy Bit-Width Ordering"

**Or more concisely:** "The CPU/GPU Quantization Divide: Non-Monotonic GGUF Variant Ordering on ARM and x86"

**Outline (12 pages, 2 columns, IEEE/ACM format):**

1. **Introduction** (1.5p) — Motivation, 3 questions, 3 non-obvious answers, paper structure
2. **Background** (1p) — GGUF K-quants, superblock structure, llama.cpp, mobile CPU memory hierarchy
3. **Methodology** (1p) — Devices (Pixel 6a, i5-1235U, M4), models (Llama + Qwen), filled-context method, reproducibility
4. **Throughput Results: Non-Monotonic Ordering** (1.5p) — RQ1, all 3 platforms, Table 1, ARM-vs-Metal ordering reversal
5. **Context Sensitivity: The KV-Cache Cliff** (1.5p) — RQ2, filled-context methodology, Q2_K cliff, Q3_K_M stability, cross-platform cliff comparison
6. **Root Cause: SIMD Dequantization and Cache Pressure** (1.5p) — NEW — superblock analysis, KV-cache size model, cliff threshold formula, validation
7. **Quality: Non-Monotonic Accuracy Ordering** (1p) — RQ3, 6 benchmarks, Q4_K_S/Q3_K_M findings, PPL vs. accuracy decoupling
8. **Cross-Device Validation** (0.5p) — 3-platform TPS table, CPU/GPU divide summary
9. **Deployment Recommendations** (0.5p) — Decision table by use case
10. **Related Work** (0.75p) — 35+ citations
11. **Conclusion** (0.25p)

**Key figures (8 total):**
- Fig 1: Decode TPS vs context, all 7 variants, 3 platforms — **money figure**
- Fig 2: Filled-context cliff curves (Q2_K vs Q3_K_M vs Q4_K_M — ARM + x86 side by side)
- Fig 3: Root cause — KV-cache size at cliff threshold vs. cache hierarchy (roofline-style)
- Fig 4: Cross-model cliff (Llama vs Qwen — different thresholds, same mechanism)
- Fig 5: Quality heatmap (6 benchmarks × 7 variants)
- Fig 6: 3-platform ordering comparison (Table 4 as stacked bars or rank chart)
- Fig 7: Pareto frontier (accuracy vs TPS, annotated)
- Fig 8: Deployment decision flowchart

---

## 7. What We Are NOT Doing (Scope Boundaries)

- No GPU-side benchmarking (T4/A100 are context only, not primary contribution)
- No model sizes other than Llama 3.2 3B and Qwen 2.5 1.5B
- No quantization formats other than GGUF K-quants (GPTQ, AWQ = related work)
- No hardware modification or kernel patching
- No user study

---

## 8. Canonical Results Index

| Claim | Source |
|-------|--------|
| Pixel TPS (all 7 variants) | `results/pixel_llama_tps_20260325_120022/` |
| Pixel cliff (filled-context) | `results/pixel_llama_cliff_filled_20260326_132101/` |
| Pixel quality (6 benchmarks) | `results/quality_scores.json` keys without prefix |
| x86 TPS | `results/x86_tps_results.json` |
| x86 cliff | `results/x86_llama_cliff_20260329_002333/` |
| x86 quality | `results/quality_scores.json` keys `x86_*` |
| x86 PPL | `results/x86_perplexity_results.json` |
| M4 Metal TPS | `results/m4_llama_tps_20260326_001546/` |
| Full Pixel PPL | `results/pixel_6a_ppl_final/` (Q2_K, Q3_K_M done; others pending) |
| Qwen Pixel TPS | **TO RUN** |
| Qwen Pixel cliff | **TO RUN** |
| M4 cliff (filled-context) | **TO RUN** |
