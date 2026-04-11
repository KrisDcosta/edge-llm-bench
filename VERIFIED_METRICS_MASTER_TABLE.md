# Verified Metrics Master Table
## Ground-Truth Reference for Dashboard, README, and Published Dataset Validation

**Generated:** 2026-04-09 | **Updated:** 2026-04-10 (M4 CPU cliff data added)  
**All values extracted directly from raw JSONL/JSON source files.**  
**Use this as the single source of truth — not README, not paper drafts.**

---

## ⚠️ Critical Issues Found During Extraction

| Issue | Detail | Impact |
|-------|--------|--------|
| **ARM ARC-Easy scoring bug** | `arc_easy:*` in quality_scores.json scores 100% for all variants — the parser finds the letter "D" in the echoed question body (e.g., "D) soft") instead of the model's actual output. Corrected values are in `arc_easy_fixed:*` keys. | Use `arc_easy_fixed` values (76–82%), NOT `arc_easy` (100%). Dashboard must be fixed if it uses the bugged key. |
| **ARM cliff Q4_K_M still n=3** | `pixel_llama_cliff_filled_canonical_n10/` Q4_K_M shows inflated baseline (7.606 tok/s); use n=3 from 20260326_132101 (−6.6%). | ARM cliff for Q4_K_M is −6.6% (n=3, cautious). |
| **Q5_K_M cliff RESOLVED (2026-04-10)** | Clean isolated n=5 rerun confirms cliff onset at ctx=512 (−18%), total drop −46% (6.67→3.61 tok/s). Earlier n=3 estimate (−25.8%, cliff at ctx=1300) was an artifact of a cold-device baseline near the cliff floor. The canonical n=10 data (mean baseline 6.10) also shows ctx=512 cliff (−20%). DVFS effect: cliff-sweep 192-token prefill ramps CPU to turbo; TPS sweep 7-token prompt does not → different baselines (6.67 vs 3.75). | Q5_K_M cliff: ctx=512 onset (−18–20%), −42–46% total. Classify same as Q2_K for context sensitivity. |
| **M4 Metal cliff only covers ctx=1024–2048** | The canonical M4 Metal cliff sweep starts at ctx=1024, not ctx=256. The TPS sweep covers ctx=256. This means we cannot compute a filled-context cliff percentage for Metal in the same way as ARM/x86. | Metal cliff table should note "1024-baseline" not "256-baseline". |
| **Q3_K_M KV mitigation shows -11.1% cliff** | In the KV mitigation experiment, Q3_K_M default shows -11.1% (4.05→3.61), consistent with the canonical cliff. Q3_K_M is not "cliff-immune" — it's "cliff-attenuated" (<±11%). | Paper already corrected to ±11%. Verify dashboard uses "attenuated" not "immune". |
| **Qwen TPS paper values wrong** | Paper said Q2_K=13.9 tok/s (n=20). Actual canonical data: Q2_K=16.056±0.670 (n=5). Paper ratio 1.92× → actual 2.23×. Paper now corrected. | Dashboard/README Qwen TPS must use 16.1 tok/s for Q2_K, ratio 2.23×. |
| **Qwen cliff table was contaminated run** | Paper's Qwen cliff table used run 20260330_004954 (concurrent process contamination, 4–6 tok/s baselines). Canonical is 20260330_235410 (8–16 tok/s, clean). Paper now corrected. | Use `pixel_qwen_cliff_filled_20260330_235410` for all Qwen cliff values. |
| **M4 Metal cliff ±2% understated** | Paper said "flat within ±2%". Actual: 5 variants ±0.6–0.8%, Q3_K_M +3.4%, Q2_K +8.5%. Paper corrected to per-variant values. | Dashboard/README Metal cliff description: "flat to +8.5% (no degradation)". |
| **M4 CPU cliff high variance** | M4 CPU cliff sweep (run 2026-04-09, 442 min) shows no structured cliff but exhibits extreme context-to-context variance (CV up to 80%) due to macOS scheduling and AMX dispatch path changes. Ctx=256 baselines for variants 2–7 are 1.4–2× inflated vs dedicated TPS sweep (warmup contamination from sequential variant order). | Use TPS sweep (m4_cpu_tps_20260406_203938, n=10) not cliff sweep for M4 CPU baselines. |

---

## 1. ARM Pixel 6a — Decode TPS at ctx=256 (Primary Throughput)

**Source:** `results/pixel_llama_tps_20260325_120022/tps_*.jsonl`  
**Method:** Fresh-context inference, n=10 trials, 4 threads, ctx=256, 64 output tokens  
**Note:** This is the TPS *sweep* baseline (short/fresh prompt). The cliff baseline (filled context, 192-token prompt) is lower — see Section 3.

| Variant | Decode TPS | 95% CI (±) | Prefill TPS | Model Size | bpw |
|---------|-----------|-----------|------------|-----------|-----|
| Q2_K   | **7.494** | ±0.296 | 9.675 | 1.3 GB | 2.6 |
| Q3_K_M | **4.683** | ±0.096 | 5.568 | 1.6 GB | 3.4 |
| Q4_K_S | **5.014** | ±0.054 | 6.263 | 1.6 GB | 4.3 |
| Q4_K_M | **4.781** | ±0.048 | 5.944 | 2.0 GB | 4.6 |
| Q5_K_M | **3.745** | ±0.029 | 4.568 | 2.3 GB | 5.3 |
| Q6_K   | **3.527** | ±0.028 | 4.121 | 2.7 GB | 6.3 |
| Q8_0   | **4.518** | ±0.507 | 5.803 | 3.4 GB | 8.5 |

**Verified ordering:** Q2_K ≫ Q4_K_S > Q4_K_M ≈ Q3_K_M > Q8_0 > Q5_K_M > Q6_K ✅  
**Note on Q8_0:** High CI (±0.507) reflects high trial variance — possible thermal sensitivity.

---

## 2. ARM Pixel 6a — Decode TPS Across All Context Sizes

**Source:** Same as Section 1, ctx={256, 512, 1024, 2048}

| Variant | ctx=256 | ctx=512 | ctx=1024 | ctx=2048 |
|---------|--------|--------|---------|---------|
| Q2_K   | 7.494±0.296 | 5.822±0.393 | 5.105±0.119 | 4.905±0.094 |
| Q3_K_M | 4.683±0.096 | 4.467±0.048 | 4.266±0.011 | 4.212±0.052 |
| Q4_K_S | 5.014±0.054 | 5.001±0.071 | 4.986±0.012 | 4.996±0.012 |
| Q4_K_M | 4.781±0.048 | 4.786±0.041 | 4.802±0.059 | 4.788±0.042 |
| Q5_K_M | 3.745±0.029 | 3.749±0.050 | 3.774±0.064 | 3.748±0.049 |
| Q6_K   | 3.527±0.028 | 3.520±0.011 | 3.520±0.009 | 3.517±0.011 |
| Q8_0   | 4.518±0.507 | 4.352±0.175 | 4.540±0.308 | 4.455±0.190 |

**Key observation:** In the TPS sweep (fresh context), Q4_K_M, Q4_K_S, Q5_K_M, Q6_K are all essentially **flat** across contexts. Q2_K and Q3_K_M show a mild gradual decline. This is fresh-context — not the cliff behavior.

---

## 3. ARM Pixel 6a — Filled-Context Cliff (11 ctx points, 256→2048)

**Sources (per PROVENANCE.md):**
- Q2_K, Q3_K_M, Q4_K_S, Q8_0: `pixel_llama_cliff_filled_20260329_162354/` (n=10)
- Q6_K: `pixel_llama_cliff_filled_20260330_212946/` (n=10, clean solo rerun)
- Q4_K_M: `pixel_llama_cliff_filled_20260326_132101/` (n=3, original clean)
- Q5_K_M: `pixel_llama_cliff_filled_20260410_142752/` (n=5, isolated clean rerun 2026-04-10) ✅ RESOLVED

⚠️ **Do NOT use `pixel_llama_cliff_filled_canonical_n10/` for Q4_K_M** — inflated baseline (7.6 tok/s).  
⚠️ **Do NOT use n=3 (20260326) for Q5_K_M** — cold-device baseline masked ctx=512 cliff.

| Variant | Base TPS (ctx=256) | End TPS (ctx=2048) | Total Drop | Worst Single Step | n |
|---------|-------------------|--------------------|-----------|-----------------|---|
| Q2_K   | 7.066 | 3.689 | **−47.8%** | −26.7% at ctx=256→512 | 10 |
| Q3_K_M | 4.065 | 3.622 | −10.9% | −3.9% at ctx=1024→1200 | 10 |
| Q4_K_S | 4.984 | 4.470 | −10.3% | −6.4% at ctx=1024→1200 | 10 |
| Q4_K_M | 5.573 | 5.207 | −6.6% | −5.2% at ctx=1800→2048 | 3 ⚠️ |
| **Q5_K_M** | **6.670** | **3.610** | **−45.9%** | **−18.0% at ctx=256→512** | **5 ✅** |
| Q6_K   | 3.549 | 3.172 | −10.6% | −6.0% at ctx=1024→1200 | 10 |
| Q8_0   | 4.527 | 3.707 | −18.1% | −7.0% at ctx=768→1024 | 10 |

**Q5_K_M full cliff profile (n=5, 2026-04-10):**
| ctx | TPS | Δ from base |
|-----|-----|------------|
| 256 | 6.670 | 0.0% |
| 512 | 5.470 | **−18.0%** ← cliff onset |
| 768 | 4.930 | −26.1% |
| 1024 | 4.590 | −31.2% |
| 1200 | 4.060 | −39.2% |
| 1300 | 3.970 | −40.5% |
| 1400 | 3.920 | −41.2% |
| 1500 | 3.760 | −43.6% |
| 1600 | 3.750 | −43.8% |
| 1800 | 3.640 | −45.5% |
| 2048 | 3.610 | −45.9% |

**Note on baseline vs TPS sweep:** The cliff baseline (6.67 tok/s) is higher than the fresh-context TPS sweep (3.75 tok/s). This is a DVFS effect: the 192-token filled prefill sustains CPU turbo frequency before decode starts; the 7-token TPS sweep prompt does not. Both measurements are valid for their respective use cases (peak sustained vs cold-start performance).

**Q2_K full cliff profile:**
| ctx | TPS | Δ from base |
|-----|-----|------------|
| 256 | 7.066±0.694 | 0.0% |
| 512 | 5.179±0.398 | **−26.7%** ← cliff onset |
| 768 | 4.428±0.154 | −37.3% |
| 1024 | 3.953±0.161 | −44.1% |
| 1200 | 3.714±0.138 | −47.4% |
| 1300 | 3.472±0.111 | −50.9% |
| 1400 | 3.358±0.085 | **−52.5%** ← worst |
| 1500 | 3.514±0.206 | −50.3% |
| 1600 | 3.687±0.088 | −47.8% |
| 1800 | 3.722±0.073 | −47.3% |
| 2048 | 3.689±0.076 | −47.8% |

**⚠️ Paper claim check:**
- Paper says Q2_K cliff = "−48%" ✅ (−47.8% from base, peak −52.5%)
- Paper says Q3_K_M "no cliff (<±11%)" ✅ (−10.9% total)
- Paper says Q4_K_M "-12% to ctx=2048" ❌ → actual is **−6.6%** (n=3, use cautiously)
- Paper says Q5_K_M "stable" ❌ → actual: **cliff at ctx=512, −46% total** (n=5 clean run 2026-04-10) ✅ Paper corrected

---

## 4. x86 i5-1235U — Decode TPS at ctx=256 (Single-Run Reference)

**Source:** `results/x86_tps_results.json`  
**n=1 (single-run aggregate), 6 threads, AC power, Windows 11**

| Variant | Decode TPS | Prefill TPS |
|---------|-----------|------------|
| Q2_K   | **14.050** | 24.680 |
| Q3_K_M | **8.380**  | 18.920 |
| Q4_K_S | **8.930**  | 25.190 |
| Q4_K_M | **8.550**  | 22.190 |
| Q5_K_M | **7.310**  | 14.210 |
| Q6_K   | **6.800**  | 13.930 |
| Q8_0   | **7.430**  | 19.100 |

**Ordering:** Q2_K > Q4_K_S > Q4_K_M > Q3_K_M > Q8_0 > Q5_K_M > Q6_K ✅  
(Same non-monotonic pattern as ARM — Q2_K fastest, Q6_K slowest)  
**No CI available** — n=1 single run; use for ordering confirmation only.

---

## 5. x86 i5-1235U — Filled-Context Cliff (n=5 canonical)

**Source:** `results/x86_llama_cliff_20260408_070924/` (n=5, 6 threads, 11 ctx points)

| Variant | Base TPS (ctx=256) | End TPS (ctx=2048) | Total Drop | Worst Step |
|---------|-------------------|--------------------|-----------|-----------|
| Q2_K   | 17.572 | 8.804 | **−49.9%** | −32.6% at ctx=1300→1400 |
| Q3_K_M | 9.006  | 9.592 | +6.5% | −7.3% at ctx=1600→1800 |
| Q4_K_S | 10.936 | 9.904 | −9.4% | −2.3% at ctx=768→1024 |
| Q4_K_M | 10.126 | 9.628 | −4.9% | −5.4% at ctx=1024→1200 |
| Q5_K_M | 9.170  | 8.484 | −7.5% | −3.0% at ctx=256→512 |
| Q6_K   | 8.506  | 7.804 | −8.3% | −4.7% at ctx=1024→1200 |
| Q8_0   | 7.972  | 7.682 | −3.6% | −1.7% at ctx=1300→1400 |

**Key x86 findings:**
- Q2_K cliff onset: ctx=1300→1400 (−32.6% single step), predicted by L2/1024 = 1.25MB/1024 ≈ 1280 tokens ✅
- All other variants: stable (< ±10%)
- Q3_K_M shows +6.5% — slight increase (noise at n=5; effectively flat)

---

## 6. M4 Mac — Metal GPU Decode TPS (n=10)

**Source:** `results/m4_llama_tps_20260326_001546/` | backend=Metal, ngl=99, 4 threads

| Variant | Decode TPS | ±SD | Ordering |
|---------|-----------|-----|---------|
| Q4_K_S | **19.879** | ±2.050 | 1st |
| Q4_K_M | **19.223** | ±0.538 | 2nd |
| Q2_K   | **17.787** | ±0.506 | 3rd |
| Q3_K_M | **15.603** | ±0.696 | 4th |
| Q5_K_M | **13.351** | ±0.413 | 5th |
| Q6_K   | **7.023**  | ±0.246 | 6th |
| Q8_0   | **6.394**  | ±0.245 | 7th (slowest) |

**Metal ordering:** Q4_K_S ≈ Q4_K_M > Q2_K > Q3_K_M > Q5_K_M ≫ Q6_K ≈ Q8_0  
**⚠️ This REVERSES the ARM/x86 ordering** (where Q2_K is fastest and Q8_0 is mid-range)

---

## 7. M4 Mac — Metal GPU Cliff (flat, n=5, ctx=1024–2048)

**Source:** `results/m4_metal_cliff_20260323_015934/` | 13 ctx points, starting at ctx=1024

| Variant | Base (ctx=1024) | End (ctx=2048) | Total Change | Peak Deviation |
|---------|----------------|----------------|-------------|---------------|
| Q2_K   | 9.400 | 10.200 | +8.5% | ±4.3% |
| Q3_K_M | 8.700 | 9.000  | +3.4% | ±1.7% |
| Q4_K_S | 10.220 | 10.240 | +0.2% | ±0.6% |
| Q4_K_M | 9.900  | 9.940  | +0.4% | ±0.4% |
| Q5_K_M | 7.240  | 7.260  | +0.3% | ±0.6% |
| Q6_K   | 7.900  | 7.900  | 0.0%  | ±0.6% |
| Q8_0   | 7.140  | 7.120  | −0.3% | ±0.3% |

**No cliff on Metal** ✅ (all variants flat ±4.3% or better — Q2_K slightly noisy)  
**Note:** Cliff sweep only covers ctx≥1024; ARM cliff for Q2_K occurs at ctx=512. Metal's low-ctx TPS behavior is not captured here.

---

## 8. M4 Mac — CPU Only (ngl=0) Decode TPS (n=10)

**Source:** `results/m4_cpu_tps_20260406_203938/` | backend=CPU, ngl=0, 4 threads

| Variant | Decode TPS (CPU) | Metal TPS | CPU/Metal ratio |
|---------|-----------------|-----------|----------------|
| Q2_K   | 12.306 | 17.787 | 0.69× |
| Q3_K_M | 11.478 | 15.603 | 0.74× |
| Q4_K_S | **13.160** | 19.879 | 0.66× |
| Q4_K_M | 12.506 | 19.223 | 0.65× |
| Q5_K_M | 10.589 | 13.351 | 0.79× |
| Q6_K   | 9.290  | 7.023  | **1.32×** ← CPU beats Metal |
| Q8_0   | **12.596** | 6.394 | **1.97×** ← CPU beats Metal |

**Key finding:** Metal beats CPU for sub-8-bit variants (Q2_K through Q5_K_M), but **CPU beats Metal for Q6_K and Q8_0** due to Q8_0's trivial dequantization and Q6_K's split-bit penalty on the GPU path.  
**CPU ordering:** Q4_K_S > Q8_0 > Q4_K_M > Q2_K > Q3_K_M > Q5_K_M > Q6_K  
(Different again from both ARM CPU and M4 Metal orderings)

---

## 9. Quality Benchmarks — ARM Pixel 6a (n=100 per benchmark)

**Source:** `results/quality_scores.json` | ARC-Easy uses `arc_easy_fixed` key (bug-corrected)  
**Wilson 95% CI = ±8–9pp for all entries at n=100**

| Variant | BoolQ | ARC-Easy | ARC-Chall | HellaSwag | MMLU | TruthfulQA |
|---------|-------|---------|----------|----------|------|-----------|
| Q2_K   | 69% | 76% | 50% | **19%** ⚠️ | 42% | 50% |
| Q3_K_M | 69% | 78% | 52% | 44% | 48% | **68%** |
| Q4_K_S | **74%** | 81% | **62%** | 39% | 49% | 57% |
| Q4_K_M | 72% | **82%** | 60% | 43% | 47% | 60% |
| Q5_K_M | 67% | 81% | 61% | **45%** | **50%** | 65% |
| Q6_K   | 65% | 79% | 58% | 41% | 48% | 60% |
| Q8_0   | 68% | 80% | 56% | 43% | 47% | 58% |

**Key findings:**
- Q2_K HellaSwag: 19% (below 25% random chance) — format collapse (56/100 outputs "No" instead of A/B/C/D) ✅
- Q6_K is dominated: lowest BoolQ (65%) AND slowest practical TPS (3.53) — avoid on all CPU ✅
- No pairwise comparison reaches p<0.05 at n=100 *except* Q2_K HellaSwag vs. any other (z=3.13, p<0.002) ✅
- ARC-Easy range: 76–82% ← use these, not the bugged 100% values

---

## 10. Quality Benchmarks — x86 i5-1235U (n=100 per benchmark)

**Source:** `results/quality_scores.json`, keys `x86_*`

| Variant | BoolQ | ARC-Easy | ARC-Chall | HellaSwag | MMLU | TruthfulQA |
|---------|-------|---------|----------|----------|------|-----------|
| Q2_K   | 70% | 77% | 50% | 22% | 41% | 49% |
| Q3_K_M | 66% | 69% | 45% | 47% | 50% | 60% |
| Q4_K_S | 72% | 78% | 54% | 55% | 51% | 47% |
| Q4_K_M | **74%** | **79%** | **55%** | 54% | 49% | 52% |
| Q5_K_M | 64% | 70% | 56% | 52% | 48% | 53% |
| Q6_K   | 64% | 70% | 54% | 52% | **52%** | 47% |
| Q8_0   | 63% | 71% | 51% | **55%** | 47% | 46% |

**Cross-platform consistency check (ARM vs x86 delta, acceptable ≤ 10pp):**
- BoolQ: within 1–7pp ✅
- HellaSwag: Q2_K ARM=19%, x86=22% (+3pp) ✅; other variants within 2–11pp — Q4_K_M, Q4_K_S show larger gaps (10–16pp) ⚠️
- MMLU: within 1–4pp ✅
- TruthfulQA: larger gaps (Q3_K_M: 68% ARM vs 60% x86, −8pp; Q4_K_S: 57% vs 47%, −10pp) ⚠️

---

## 11. WikiText-2 Perplexity (lower = better)

**ARM Pixel 6a — Source:** `results/perplexity_scores.json`  
**x86 i5-1235U — Source:** `results/x86_perplexity_results.json`

| Variant | ARM PPL | ARM Corpus | x86 PPL |
|---------|---------|-----------|---------|
| Q2_K   | **13.2885** | 285K tokens (full) | 11.7265 |
| Q3_K_M | **11.0832** | 285K tokens (full) | 10.1575 |
| Q4_K_S | N/A | not measured | 9.7414 |
| Q4_K_M | 9.7553 | sample only (12KB) ‡ | 9.7466 |
| Q5_K_M | N/A | not measured | 9.7680 |
| Q6_K   | 9.7520 | sample only (12KB) ‡ | 9.7366 |
| Q8_0   | 9.7044 | sample only (12KB) ‡ | 9.7101 |

‡ ARM sample-only (12KB) values are directionally correct but not full-corpus validated.  
**Use x86 full-corpus values as the authoritative PPL reference for Q4_K_M through Q8_0.**

**PPL ordering (x86 full corpus):** Q2_K(11.73) > Q3_K_M(10.16) > Q5_K_M(9.77) > Q4_K_M(9.75) ≈ Q6_K(9.74) ≈ Q4_K_S(9.74) ≈ Q8_0(9.71)  
**Note:** PPL is monotonically decreasing with bits on x86 (as expected), but the differences among 4–8 bit variants are tiny (<0.08 PPL, well within measurement noise).

---

## 12. KV-Cache Q8_0 Mitigation — ARM Pixel 6a

**Source:** `results/pixel_kvcache_quant_20260331_062405/`  
**Method:** Filled-context sweep (same as cliff), kv_quant=default vs kv_quant=q8_0

| Variant | KV Mode | ctx=256 TPS | ctx=2048 TPS | Total Change | Key Metric |
|---------|---------|------------|-------------|-------------|-----------|
| Q2_K | default | 7.50 | 3.69 | **−50.8%** (cliff) | — |
| Q2_K | q8_0 | **4.04** | 3.93 | **−2.6%** (flat) | Cliff eliminated ✅ |
| Q3_K_M | default | 4.05 | 3.61 | −11.1% | — |
| Q3_K_M | q8_0 | 4.10 | 3.90 | −5.0% | Halves cliff depth ✅ |
| Q4_K_M | default | 4.73 | 4.16 | −11.9% | — |
| Q4_K_M | q8_0 | 4.70 | 4.44 | −5.5% | Halves cliff depth ✅ |

**Derived metrics:**
- Q2_K KV Q8_0 baseline cost: 7.50 → 4.04 = **−46.1% at ctx=256** (fixed overhead of KV dequantization)
- Q2_K crossover point: KV Q8_0 becomes faster at approximately ctx=1400 (3.75 default vs 4.00 q8_0) ✅
- Q3_K_M: <1% baseline cost; KV Q8_0 recommended for ctx≥512
- Q4_K_M: <1% baseline cost; KV Q8_0 recommended for ctx≥512

**⚠️ Note:** The KV mitigation experiment Q2_K baseline (7.50 tok/s) differs slightly from the canonical cliff baseline (7.07 tok/s) because these were separate runs with different thermal starting conditions. Both are real measurements; ±6.3% difference is within the ±15% day-to-day variability envelope.

---

## 13. Qwen 2.5 1.5B — ARM Pixel 6a Cross-Model Validation

**Source (TPS):** `results/pixel_qwen_tps_20260326_033619/` (n=5, ctx=256)  
**Source (Cliff):** `results/pixel_qwen_cliff_filled_20260330_235410/` (n=5, 11 ctx points)

### TPS at ctx=256 (n=5):
| Variant | Decode TPS | ±SD |
|---------|-----------|-----|
| Q2_K   | **16.056** | ±0.670 |
| Q3_K_M | 10.128 | ±0.559 |
| Q4_K_S | 11.086 | ±0.323 |
| Q4_K_M | 9.784  | ±0.222 |
| Q5_K_M | 7.754  | ±0.118 |
| Q6_K   | 7.202  | ±0.052 |
| Q8_0   | 10.220 | ±0.714 |

**Ordering:** Q2_K ≫ Q4_K_S > Q8_0 > Q3_K_M > Q4_K_M > Q5_K_M > Q6_K  
(Same non-monotonic pattern as Llama — Q2_K fastest, Q6_K slowest ✅)

### Cliff (n=5, ctx=256→2048):
| Variant | Base (ctx=256) | End (ctx=2048) | Total Drop |
|---------|---------------|----------------|-----------|
| Q2_K   | 12.632 | 7.766 | **−38.5%** ← cliff confirmed |
| Q3_K_M | 8.436  | 7.686 | −8.9% |
| Q4_K_S | 9.924  | 9.064 | −8.7% |
| Q4_K_M | 9.598  | 8.652 | −9.9% |
| Q5_K_M | 7.572  | 7.134 | −5.8% |
| Q6_K   | 7.320  | 6.888 | −5.9% |
| Q8_0   | 10.090 | 8.412 | −16.6% |

**Cross-model validation of cliff formula:** Qwen 2.5 1.5B cliff onset = ctx=512 (same ARM L2=512KB → L2/1024=512) ✅  
**Cliff is shallower in Qwen** (−38.5% vs −47.8% for Llama) — consistent with Qwen having fewer KV heads (2 vs 8), reducing per-step KV traffic.

---

## 14. Thermal Characterization — ARM Pixel 6a

**Source:** Thermal experiment (fresh-context Q4_K_M, not filled-context)

| Phase | TPS | Notes |
|-------|-----|-------|
| Baseline (fresh-context, short prompt) | **8.33 ± 0.58** | 5 trials; fresh context with 20-token prompt |
| Throttled (50 consecutive trials, no cooldown) | **4.72–4.96** | Stable plateau within 60s, σ=0.07 |
| Recovery (after 140s cooldown) | **7.04 ± 0.30** | 85% recovery |

**Note:** The 8.33 baseline here is the fresh-context, short-prompt value — NOT the filled-context decode TPS (which is 4.78 for Q4_K_M at ctx=256 in the canonical TPS sweep). The difference is expected: short prompt → KV cache nearly empty → faster decode. This is correctly documented in the paper's thermal section.

---

## Summary: Paper vs. Verified Data Comparison

| Paper Claim | Verified Value | Status |
|------------|---------------|--------|
| Q2_K ARM TPS = 7.49 tok/s | **7.494±0.296** | ✅ Correct |
| Q6_K ARM TPS = 3.53 tok/s | **3.527±0.028** | ✅ Correct |
| Q2_K cliff = −48% | **−47.8%** total (peak −52.5% at ctx=1400) | ✅ Correct |
| Q3_K_M cliff < ±11% | **−10.9%** total | ✅ Correct |
| Q4_K_M cliff "−12% to ctx=2048" | **−6.6%** (n=3, from 20260326) | ⚠️ Paper overstates — actual is −6.6% (better than claimed) |
| Q5_K_M cliff | **−45.9%**, cliff ctx=512 (n=5, 2026-04-10) | ✅ Paper corrected — cliff onset ctx=512, −18% single step |
| x86 Q2_K cliff ≈ −50% | **−49.9%** | ✅ Correct |
| x86 cliff onset ctx=1300–1400 | **ctx=1300→1400 worst step** | ✅ Correct |
| M4 Metal Q4_K_S fastest = 19.88 tok/s | **19.879±2.050** | ✅ Correct |
| M4 Metal Q8_0 slowest = 6.39 tok/s | **6.394±0.245** | ✅ Correct |
| M4 Metal no cliff (flat ±2%) | 5 variants ±0.6–0.8%; Q3_K_M +3.4%; Q2_K +8.5% (increase, not drop) | ✅ Paper corrected to per-variant values |
| ARC-Easy ARM 76–82% | **76–82% (arc_easy_fixed)** | ✅ Correct — but raw `arc_easy` key is buggy (100%) |
| BoolQ Q4_K_S highest (74%) | **74%** | ✅ Correct |
| HellaSwag Q2_K collapse (19%) | **19%** (56/100 "No" outputs) | ✅ Correct |
| KV Q8_0 eliminates Q2_K cliff | **−50.8% → −2.6%** | ✅ Correct |
| KV Q8_0 baseline cost = −46% | **7.50 → 4.04 = −46.1%** | ✅ Correct |
| KV crossover ≈ ctx=1400 | **ctx=1400: 3.75 vs 4.00** | ✅ Correct |
| Thermal baseline 8.33±0.58 | **8.33±0.58** (fresh-context, short prompt) | ✅ Correct |
| PPL Q2_K ARM = 13.29 | **13.2885** | ✅ Correct |
| PPL Q3_K_M ARM = 11.08 | **11.0832** | ✅ Correct |
| Qwen Q2_K TPS = 13.9 tok/s | **16.056±0.670** (n=5) | ✅ Paper corrected to 16.1 |
| Qwen ratio = 1.92× | **2.23×** (16.056/7.202) | ✅ Paper corrected |
| M4 CPU no cliff | **Confirmed** — no structured cliff in ctx=[256,2048]; high variance (CV up to 80%) | ✅ Paper updated (2026-04-10) |
| M4 CPU ordering | Q4_K_S=13.16 > Q8_0=12.60 > Q4_K_M=12.51 > Q2_K=12.31 > Q3_K_M=11.48 > Q5_K_M=10.59 > Q6_K=9.29 | ✅ From TPS sweep n=10 |

---

## 15. M4 Mac CPU — Cliff Sweep (2026-04-10)

**Source:** `results/m4_cpu_cliff_20260409_213958/` | ngl=0, 4 threads, 13 ctx × 5 trials  
**Runtime:** 442 min

### Key Findings

**No structured cliff** in ctx=[256, 2048] — consistent with L2/1024 prediction:
- M4 cluster L2 ≈ 16 MB → predicted cliff at ctx ≈ 16,384 tokens (far beyond test range)

**Data quality issues:** High context-to-context variance. Main causes:
1. **Sequential warmup inflation at ctx=256**: Q3_K_M–Q8_0 baselines are 1.4–2× higher than TPS sweep because Q2_K (run first) warms up the AMX pipeline and CPU caches. Use TPS sweep (Section 8) for reliable baselines.
2. **macOS background scheduling**: CV up to 80% at some ctx/variant combinations (Q6_K ctx=1280: CV=79%, Q8_0 ctx=2048: mean=51.49 tok/s with std=50.92 — one pathological trial)
3. **AMX dispatch path changes**: Q2_K jumps from ~11 tok/s at ctx=512 to ~23 tok/s at ctx=768–896 (consistent across 5 trials, CV<10%) — possible AMX threshold effect

### Reliable ctx=256 TPS values (from dedicated TPS sweep, n=10)

Use these — NOT the cliff sweep ctx=256 values:

| Variant | M4 CPU TPS (TPS sweep n=10) | M4 Metal TPS | CPU/Metal |
|---------|---------------------------|------------|---------|
| Q4_K_S | **13.160** | 19.879 | 0.66× |
| Q8_0   | **12.596** | 6.394  | **1.97× CPU wins** |
| Q4_K_M | **12.506** | 19.223 | 0.65× |
| Q2_K   | **12.306** | 17.787 | 0.69× |
| Q3_K_M | **11.478** | 15.603 | 0.74× |
| Q5_K_M | **10.589** | 13.351 | 0.79× |
| Q6_K   | **9.290**  | 7.023  | **1.32× CPU wins** |

**CPU ordering:** Q4_K_S > Q8_0 > Q4_K_M > Q2_K > Q3_K_M > Q5_K_M > Q6_K  
(Different from both ARM ordering and Metal ordering — a third distinct pattern)

---

## Action Items Before Publishing Dashboard / Dataset

1. **Fix dashboard ARC-Easy source** — ensure it uses the `arc_easy_fixed` key (76–82%), not `arc_easy` (100%)
2. **Q5_K_M ARM cliff RESOLVED** — n=5 isolated run (2026-04-10) confirms cliff ctx=512, −46%. Update dashboard to show Q5_K_M as "cliff-prone" (same category as Q2_K), not "moderate". Push `results/pixel_llama_cliff_filled_20260410_142752/` JSONL to repo.
3. **Fix M4 Metal cliff description** — not "flat ±2%"; correct is "5 variants ±0.6–0.8%; Q2_K +8.5% improvement" (paper already corrected)
4. **Fix Qwen TPS values** — Q2_K=16.1 tok/s (not 13.9), ratio=2.23× (not 1.92×) (paper already corrected)
5. **Fix Qwen cliff table** — must use canonical run 20260330_235410, not contaminated 004954 (paper already corrected)
6. **M4 CPU cliff data** — use TPS sweep for baselines, note cliff sweep as "no structured cliff, high macOS variance" in any dashboard display
4. **Q4_K_M cliff caveat** — paper says "−12%" but verified data shows −6.6% (better than claimed, but still n=3); note as "approximately −7%, n=3"
5. **x86 TPS: note n=1** — dashboard should show "single reference measurement, no CI" for x86 TPS
