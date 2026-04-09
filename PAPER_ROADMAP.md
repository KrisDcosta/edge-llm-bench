# Paper Roadmap: GGUF K-Quant Benchmarking on CPU Inference
## Targeting: MLSys 2026 / MobiSys 2027 / USENIX ATC 2027

**Last Updated:** 2026-04-09
**Status:** All data gaps closed. Phases 1–4 complete. Entering Phase 5: figures + final submission prep.

---

## 1. Central Thesis (Updated)

> **"CPU SIMD dequantization overhead creates a CPU/GPU performance divide in GGUF K-quantized inference. On all CPU backends (ARM NEON, x86 AVX2), quantization variants exhibit triple non-monotonic behavior — throughput, KV-cache context sensitivity, and quality all defy bit-width ordering — driven by a shared SIMD kernel bottleneck. GPU backends with dedicated 4-bit dispatch paths (Metal) reverse this ordering entirely. Within the CPU regime, a filled-context cliff in Q2_K (−40% ARM, −51% x86) and the unexpected stability of Q3_K_M (<±5% across all contexts) are explained by superblock structure and its interaction with CPU cache hierarchy."**

**Why this is publishable:**
1. Novel empirical phenomenon documented across 3 hardware platforms and ~2,500 measurements
2. Mechanistic explanation tied to CPU microarchitecture (SIMD tables, L2/L3 cache)
3. Cross-model validation confirmed on Qwen 2.5 1.5B (same non-monotonic ordering, same cliff threshold)
4. Directly actionable: practitioners currently choose variants by bpw; this work shows why that is wrong
5. The CPU/GPU divide is a clean, testable claim with practical implications for iOS/macOS vs Android deployment
6. KV-cache Q8_0 mitigation provides quantified tradeoff: eliminates cliff at −46% short-ctx throughput cost

---

## 2. Current Data Inventory

### What Exists and Is Verified ✅

| Dataset | Platform | Variants | n | Notes |
|---------|----------|----------|---|-------|
| Decode/Prefill TPS sweep | Pixel 6a ARM | All 7, ctx {256,512,1024,2048} | 10 trials | Table 1 ✅ |
| Filled-context cliff | Pixel 6a ARM | All 7, 11 ctx pts (256→2048) | **10 trials** | Table 2 ✅ (n=10 canonical) |
| Filled-context cliff | x86 i5-1235U | All 7, 11 ctx pts | **5 trials** | §5.5 ✅ (n=5 complete 2026-04-08) |
| TPS sweep | Mac M4 Metal | All 7, ctx {256,512,1024,2048} | 10 trials | Table 4 ✅ |
| **Qwen 2.5 1.5B TPS** | Pixel 6a ARM | All 7, ctx {256,512,1024,2048} | — | Cross-model replication ✅ |
| **Qwen 2.5 1.5B cliff** | Pixel 6a ARM | All 7, 11 ctx pts (256→2048) | 5 trials | ctx=512 cliff confirmed ✅ |
| **M4 Metal cliff sweep** | Mac M4 Metal | All 7, 13 ctx pts | 5 trials | Flat ±2%, no cliff ✅ |
| BoolQ (100q) | Pixel 6a ARM | All 7 | — | Verified ✅ |
| ARC-Easy (100q) | Pixel 6a ARM | All 7 | — | 76–82% verified ✅ |
| ARC-Challenge (100q) | Pixel 6a ARM | All 7 | — | Verified ✅ |
| HellaSwag (100q) | Pixel 6a ARM | All 7 | — | Q2_K collapse documented ✅ |
| MMLU (100q) | Pixel 6a ARM | All 7 | — | Tight 42–50% cluster ✅ |
| TruthfulQA (100q) | Pixel 6a ARM | All 7 | — | Q3_K_M leads at 68% ✅ |
| All 6 benchmarks | x86 i5-1235U | All 7 | — | Consistent with ARM ✅ |
| WikiText-2 PPL (full corpus) | Pixel 6a ARM | Q2_K, Q3_K_M | — | 13.29, 11.08 ✅ |
| WikiText-2 PPL (full corpus) | x86 i5-1235U | All 7 | — | 9.71–11.73 range ✅ |
| WikiText-2 PPL (12KB only) | Pixel 6a ARM | Q4_K_M, Q5_K_M, Q6_K, Q8_0 | — | ‡ in Table 1 (x86 full corpus available) |
| WikiText-2 PPL | Pixel 6a ARM | Q4_K_S | — | Missing Pixel only; x86 available |
| **KV-cache Q8_0 mitigation** | Pixel 6a ARM | Q2_K, Q3_K_M, Q4_K_M | n=5 | Cliff elimination confirmed ✅ |
| **Thermal characterization** | Pixel 6a ARM | Q2_K | sustained | 8.33→4.72–4.96, 85% recovery ✅ |

### Remaining Gaps ⚠️ (for full conference version)

| Gap | Priority | Status | Notes |
|-----|----------|--------|-------|
| Full Pixel PPL for Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0 | Medium | ⚠️ Partial | x86 values available as fallback — acceptable for conference |
| Root cause section with NEON perf counter data | High | 🗃️ Archived | simpleperf events require device reconnect; framed as future work in §9 |
| Cliff threshold prediction formula (quantitative) | High | ✅ Done | ARM 512 tok, x86 1280 tok, Qwen 512 tok — validated in paper |
| imatrix BoolQ + TruthfulQA | Low | ✅ Done | Two independent BoolQ runs: Q2_K −4/−5pp, Q3_K_M −7/−8pp; TruthfulQA ±1pp |

---

## 3. What Makes This Conference-Ready (Checklist)

### Novelty ✅/❌
- [x] Novel empirical phenomenon (triple non-monotonicity) — not in literature
- [x] CPU/GPU divide established across 3 platforms
- [x] Mechanistic explanation with quantitative support (SIMD kernel ops, L2 cache model, cliff formula)
- [x] Cliff threshold prediction formula — validated ARM (512 tokens), x86 (1280 tokens), Qwen (512 tokens)
- [x] Cross-model generalization — Qwen 2.5 1.5B confirms both non-monotonic ordering and cliff threshold
- [x] KV-cache Q8_0 mitigation — quantified tradeoff with crossover analysis

### Rigor ✅/❌
- [x] ~2,500 measurements across ARM, x86, Metal
- [x] Wilson 95% CI for all quality metrics
- [x] Three-platform cross-device validation (ARM + x86 + Metal)
- [x] Two model families (Llama 3.2 3B + Qwen 2.5 1.5B)
- [x] Filled-context methodology (correct KV cache saturation)
- [x] n=10 for primary cliff trials (ARM)
- [x] n=5 for Qwen cliff and Metal cliff
- [ ] Full-corpus Pixel PPL for all 7 variants (x86 available; Pixel Q4_K_M/Q5_K_M/Q6_K/Q8_0 = 12KB sample)
- [ ] NEON perf counter data (future work — simpleperf available)

### Writing ✅/❌
- [x] Core findings written clearly (17 pages)
- [x] Mechanistic analysis section written (§4: SIMD kernel overhead, cache model)
- [x] KV-cache quantization subsection written (§5.3)
- [x] Thermal characterization updated with measured values
- [x] Cross-model replication section (Qwen cliff confirmed)
- [x] Deployment recommendations updated with Q8_0 KV guidance
- [x] Conference-quality related work (51 citations, 5 subsections, explicit comparison table ✅ 2026-04-08)
- [x] Strong abstract (146 words, 3 numbered findings, Llama + Qwen validation ✅ 2026-04-09)
- [ ] Publication-quality figure pass (current matplotlib plots functional but not camera-ready)

---

## 4. Prioritized Action Plan

### Phase 1 — Critical Data — ✅ COMPLETE

| Task | Status | Key Result |
|------|--------|-----------|
| Full Pixel PPL | ⚠️ Partial | Q2_K (13.29), Q3_K_M (11.08) done; others on x86 |
| Cliff n=3 → n=10 | ✅ Done | All 7 variants n=10; Q2_K cliff: −48%, onset ctx≈512 |
| Qwen TPS sweep | ✅ Done | Q2_K 13.9 t/s fastest, Q6_K 7.25 t/s slowest |
| Qwen cliff sweep | ✅ Done | ctx=512 cliff confirmed; 7 variants × 5 trials |
| M4 Metal cliff sweep | ✅ Done | Flat ±2% all variants (no cliff); 7 variants × 13 ctx × 5 trials |
| x86 quality (all 6 benchmarks) | ✅ Done | Consistent with ARM ordering |
| KV-cache Q8_0 mitigation | ✅ Done | Q2_K cliff eliminated (−48%→−2.6%); −46% baseline cost |
| Thermal characterization | ✅ Done | Throttle onset ~60s; 85% recovery after 140s |

### Phase 2 — Root Cause Analysis — IN PROGRESS (April 2026)

**4.6 — llama.cpp kernel analysis** ✅ (paper §4 written)
- Q6_K dequantization: split-bit layout (ql[128]+qh[64]), 6-operand shuffle per superblock
- Q2_K dequantization: 16-entry table lookup, fits L1 cache entirely
- Root cause confirmed in paper: SIMD kernel op count, not arithmetic intensity

**4.7 — KV-cache size model** ✅ (formula derived and validated)
For Llama 3.2 3B: `C_layer(ctx) = 2048 × ctx bytes`
ARM cliff: `512KB / 1024 ≈ 512 tokens` ← observed ✅
x86 cliff: `1.25MB / 1024 ≈ 1280 tokens` ← observed 1200–1300 ✅
Qwen cliff: `C_layer = 1024×ctx` (2 KV heads), same 512-token threshold ✅

**4.8 — NEON perf counter validation** ⬜ Future work
`simpleperf` available on Pixel 6a; events: `L1-dcache-load-misses`, `LLC-load-misses`, `stalled-cycles-backend`
Would directly measure cache miss rate per variant; highest-impact future experiment

### Phase 3 — Supplementary Experiments — ✅ COMPLETE (2026-04-08)
- ✅ x86 cliff n=5 complete; Q4_K_S cliff retracted (was thermal artifact); threshold 1300–1400 confirmed
- ✅ imatrix BoolQ + TruthfulQA: two independent BoolQ runs; consistent −4 to −8pp for sub-4bpw
- ✅ M4 CPU baseline TPS: all 7 variants; Q8_0 Metal 0.51× CPU; GPU/CPU divide confirmed
- ✅ Thread scaling sweep: n=15 at 1/2/4/8 threads; big.LITTLE behavior documented
- ✅ All paper values updated (ARM TPS, cliff thresholds, cross-platform table expanded to 4 platforms)

### Phase 4 — Paper Rewrite — ✅ COMPLETE (2026-04-09)

| Task | Status | Notes |
|------|--------|-------|
| Abstract | ✅ | 146 words, 3 findings, Llama+Qwen validation |
| Introduction | ✅ | Tight conference prose, wrong heuristic → Finding 1/2/3 |
| Related work | ✅ | 51 citations, 5 subsections, comparison table |
| Methodology §3 | ✅ | Filled-context methodology described accurately |
| Section structure | ✅ | RQ framing removed; §4–9 topic-driven |
| Conclusion | ✅ | Mirrors intro structure; 3 findings + practical guidance |
| Thermal section | ✅ | std corrected (±0.58), fresh-context vs filled-context clarified |
| Statistical appendix | ✅ | n=10 filled-context protocol, invocation template updated |

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
| x86 cliff (n=5 canonical) | `results/x86_llama_cliff_20260408_070924/` |
| x86 quality | `results/quality_scores.json` keys `x86_*` |
| x86 PPL | `results/x86_perplexity_results.json` |
| M4 Metal TPS | `results/m4_llama_tps_20260326_001546/` |
| Full Pixel PPL | `results/pixel_6a_ppl_final/` (Q2_K, Q3_K_M done; others pending) |
| Qwen Pixel TPS | `results/pixel_qwen_tps_20260326_033619/` |
| Qwen Pixel cliff | `results/pixel_qwen_cliff_filled_20260330_235410/` |
| M4 cliff (filled-context) | `results/m4_metal_cliff_20260323_015934/` |
| KV-cache Q8_0 mitigation | `results/quality_scores.json` keys `kvcache_q8_0:*` |
| Thermal characterization | See §Limitations; baseline 8.33±0.58 (fresh-ctx), throttle 4.72–4.96, recovery 7.04±0.30 t/s |
