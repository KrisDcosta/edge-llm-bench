# Data Gaps — Required Re-runs Before Publication
Last updated: 2026-04-06 (GAP-1, GAP-2, GAP-thread-sweep, GAP-7 COMPLETE ✅; GAP-5/6 scripts ready)

All entries represent experiments that must be completed and validated
before any downstream analysis, figures, or paper sections that depend
on them are considered final. Data is the foundation — nothing proceeds
on incomplete data.

---

## CRITICAL — Blocks paper submission

### GAP-1: Q4_K_M cliff sweep n=10 (isolated)
- **What:** Filled-context KV-cache cliff sweep, 11 context sizes, n=10 trials
- **Why missing:** 20260329 n=10 run excluded — thermal recovery artifact.
  ctx=1800-2048 showed 35% speedup vs ctx=256 (physically impossible).
  Overnight CPU frequency scaling recovery after prior throttling session.
- **Current state:** n=3 from 20260326 in canonical dataset (correct behavior, low power)
- **Script:** `scripts/bench/pixel_cliff_rerun_n10_isolated.sh`
- **Command:** `bash scripts/bench/pixel_cliff_rerun_n10_isolated.sh Q4_K_M`
- **Est. runtime:** ~3.7 h (11 ctx × 10 trials × ~2 min/run)
- **Device:** Pixel 6a via ADB, fully isolated (no background processes)
- **Integration:** After completion:
  1. Verify n=10 per ctx, all decode_tps > 0, monotone decay from ctx=256
  2. Copy cliff_filled_Q4_K_M.jsonl into pixel_llama_cliff_filled_canonical_n10/
  3. Update PROVENANCE.md in canonical dir

### GAP-2: Q5_K_M cliff sweep n=10 (isolated)
- **What:** Same methodology as GAP-1, Q5_K_M variant
- **Why missing:** 20260329 n=10 run excluded — concurrent Qwen process contamination.
  llama-perplexity + pixel_qwen_cliff_filled ran concurrently from ~12:49 AM.
  ctx=1500+ crashed to 1.6 t/s (expected ~3.0 t/s from n=3 run).
- **Current state:** n=3 from 20260326
- **Script:** `scripts/bench/pixel_cliff_rerun_n10_isolated.sh`
- **Command:** `bash scripts/bench/pixel_cliff_rerun_n10_isolated.sh Q5_K_M`
- **Est. runtime:** ~3.7 h
- **Device:** Pixel 6a, isolated
- **Integration:** Same as GAP-1

---

## HIGH PRIORITY — Required for §6 Mechanistic Analysis

### GAP-3 (renamed to GAP-thread-sweep): Q4_K_M thread scaling (1, 2, 4, 8 threads)
- **What:** Thread scaling benchmark at ctx=256, filled-context methodology.
  Characterizes P-core vs LITTLE-core behavior on Pixel 6a (2x Cortex-X1 + 2x Cortex-A76 + 4x A55).
- **Script:** `scripts/bench/pixel_threads_q4km.sh`
- **Command:** Already executed on device
- **Results:**
  - threads=1:  3.38 ± 0.22 t/s (baseline, single P-core)
  - threads=2:  3.78 ± 0.50 t/s (1.12x speedup, both P-cores saturated)
  - threads=4:  4.81 ± 0.26 t/s (1.42x speedup, P-cores + 2 E-cores)
  - threads=8:  3.83 ± 0.54 t/s (1.13x speedup, E-core saturation/contention)
- **Data files:** `results/pixel_threads_q4km_20260406_100148/threads_{1,2,4,8}.jsonl` (15 records each)
- **Registry updated:** q4km-threads-1/2/8 changed from blocked→complete; q4km-threads-4 linked to new data
- **Analysis:** Validates big.LITTLE heterogeneous core behavior; threads=8 regression indicates E-core queue saturation
- **Blocks:** None; strengthens Phase 2 mechanistic analysis

### GAP-4: NEON/PMU hardware performance counters
- **What:** ARM Cortex-X1 PMU counters (L2 miss rate, IPC, stall cycles) per variant.
  Directly validates the Q6_K ~3x L2 miss hypothesis underlying §6.
- **Script:** `scripts/bench/pixel_neon_perf.sh` (updated with correct event names)
- **Status:** 🗃️  ARCHIVED — all 5 run attempts produced 100% ADB_ERROR.
  Archived to `.archive/neon_perf_incomplete/` with full README.
- **Root cause diagnosed:** Pixel 6a simpleperf has no `l2-cache-misses` event by name.
  Requires generic `cache-misses:u` or raw event `r17:u` (L2D_REFILL, Cortex-X1 code 0x17).
  Script updated with correct event names — requires device reconnect to validate.
- **Script fix location:** `scripts/bench/pixel_neon_perf.sh` lines 111-115 (events) + probe logic
- **To re-run:** `bash scripts/bench/pixel_neon_perf.sh Q2_K --ctx=256` to verify fix, then `--all-variants`
- **Est. runtime:** ~45 min once script fix confirmed working
- **Device:** Pixel 6a. Root enabled (perf_event_paranoid=-1).
- **Blocks:** Paper §6 (Mechanistic Analysis), PMU counter LaTeX table

---

## MEDIUM PRIORITY — Strengthens paper

### GAP-5: x86 cliff sweep with filled-context methodology (n=5)
- ✅ **COMPLETE** — 2026-04-08 (results: `results/x86_llama_cliff_20260408_070924/`)
- **Key findings (n=5, 7 variants × 11 ctx):**
  - Q2_K: 17.6 → 8.8 t/s, **−50%** cliff onset ctx=1300–1400 (predicted 1280 by L2 formula, within 8%)
  - Q4_K_S: **no cliff** (−9% to ctx=2048) — prior n=3 thermal artifact showed spurious −14%
  - All other variants: flat within ±8%; Q3_K_M varies ±7% with no monotone trend
  - Cliff is Q2_K-exclusive on x86; Q4_K_M/Q5_K_M/Q6_K/Q8_0 all context-stable
- **Integrated:** Tab:x86_cliff updated (n=3→n=5, added ctx=1400 column); all cliff threshold text corrected to 1300–1400 throughout paper; Q4_K_S cliff claim retracted; abstract −51%→−50%

### GAP-6: imatrix calibration quality delta
- ✅ **COMPLETE** — 2026-04-08. BoolQ + TruthfulQA imatrix eval done for Q2_K and Q3_K_M.
- **Data keys:** `boolq_imatrix:{Q2_K,Q3_K_M}`, `truthfulqa_imatrix:{Q2_K,Q3_K_M}` in `results/quality_scores.json`
- **Findings (n=100 per run; Wilson CI ≈ ±9.6pp):**
  - BoolQ Q2_K: 69% → 65% (−4pp; within CI, but consistent with prior −5pp run)
  - BoolQ Q3_K_M: 69% → 62% (−7pp; within CI, but consistent with prior −8pp run)
  - TruthfulQA Q2_K: 50% → 51% (+1pp; no effect)
  - TruthfulQA Q3_K_M: 68% → 68% (0pp; no effect)
  - Q4_K_S through Q8_0 (BoolQ only): all ±4pp or less
  - **Statistical note:** BoolQ decrements do NOT individually reach significance at n=100. Two independent runs show consistent direction (−4/−5pp and −7/−8pp). Real effect likely in −4 to −8pp range.
- **Paper integration:** Updated Future Work §9 with two-run data, nuanced significance framing, TruthfulQA non-result, and Q4_K_S as best imatrix target.
- **Script:** `scripts/bench/pixel_imatrix_quality.sh` (functional since 2026-04-07)

### GAP-7: M4 Mac CPU baseline TPS (all 7 variants, corrected)
- **What:** Baseline decode TPS sweep for M4 Mac CPU backend (ngl=0). 4 context lengths, 10 trials.
- ✅ **COMPLETE** — 2026-04-06 (77m 13s, results: `results/m4_cpu_tps_20260406_203938`)
- **Key findings:**
  - All values clean (no 19069.67); n=10 per configuration; backend=CPU confirmed
  - Q4_K_S fastest on M4 CPU (13.16 t/s), Q6_K slowest (9.29 t/s) — non-monotonic, matches CPU pattern
  - Q8_0 on Metal (6.39) is **0.51× SLOWER than M4 CPU** (12.60) — Metal hurts Q8_0
  - Q6_K on Metal (7.02) is **0.76× SLOWER than M4 CPU** (9.29)
  - M4 CPU is 1.4–2.6× faster than Pixel 6a ARM (same 4-thread config)
- **Integrated:** `gpu_vs_cpu_comparison.json` updated; cross-platform table in §8 extended to 4 columns

---

## Validation protocol after each re-run

1. `grep -c '"decode_tps"' <output>.jsonl` — must equal 110 (11 ctx x 10 trials)
2. `python3 -c "import json; bad=[l for l in open('<f>') if json.loads(l)['decode_tps']<=0]; print(len(bad),'bad rows')"` — must be 0
3. Check ctx=256 is highest TPS (no thermal inversion at long context)
4. Compare mean±SD to existing n=3 values — must agree within 10%
5. Update canonical PROVENANCE.md
6. Update this file status column
7. Update report/report.tex cliff column if new mean differs >5% from current

---

## Status

| Gap         | Priority | Status                        | Est. completion     | Completion |
|-------------|----------|-------------------------------|---------------------|------------|
| GAP-1       | CRITICAL | ✅ COMPLETE n=10              | Device session      | 2026-04-05 00:27 |
| GAP-2       | CRITICAL | ✅ COMPLETE n=10              | Device session      | 2026-04-06 03:08 |
| GAP-thread  | HIGH     | ✅ COMPLETE (threads sweep)   | Device session      | 2026-04-06 10:29 |
| GAP-4       | HIGH     | 🗃️  ARCHIVED (re-run later)   | Future device sess  | Script fixed, needs validation |
| GAP-5       | MEDIUM   | ✅ COMPLETE n=5               | 2026-04-08          | results/x86_llama_cliff_20260408_070924 |
| GAP-6       | MEDIUM   | ✅ COMPLETE (BoolQ + TruthfulQA) | 2026-04-08        | results/quality_scores.json (boolq_imatrix:*, truthfulqa_imatrix:*) |
| GAP-7       | MEDIUM   | ✅ COMPLETE                   | 2026-04-06 21:56    | results/m4_cpu_tps_20260406_203938 |
