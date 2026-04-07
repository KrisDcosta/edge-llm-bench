# Data Gaps — Required Re-runs Before Publication
Last updated: 2026-04-06 (GAP-1, GAP-2, GAP-thread-sweep COMPLETE ✅; GAP-7 script ready)

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
- **What:** Validate KV-cache cliff formula on x86 (predicted cliff_ctx ~1280 tokens,
  1.25 MB L2 / 1024 = 1220 within 2.4%)
- **Current state:** x86 results exist but methodology (fresh vs filled) unconfirmed
- **Script:** `scripts/bench/x86_llama_cliff.py`
- **Device:** x86 laptop (Intel i5-1235U) — not Pixel
- **Blocks:** Cross-platform cliff table in §8

### GAP-6: imatrix calibration quality delta (n >= 3 per benchmark)
- **What:** BoolQ/TruthfulQA delta with vs without imatrix for Q2_K and Q3_K_M.
  Currently: Q2_K -5%, Q3_K_M -8% — from single eval pass (n=1, not publishable).
- **Blocks:** §7 imatrix subsection

### GAP-7: M4 Mac CPU baseline TPS (all 7 variants, corrected)
- **What:** Baseline decode TPS sweep for M4 Mac CPU backend (ngl=0). 4 context lengths, 10 trials.
  Fills the "CPU TPS" column in gpu_vs_cpu_comparison.json (currently corrupted/invalid).
  Enables M4 GPU vs CPU comparison for §8 cross-platform analysis.
- **Why missing:** All previous data corrupted — script parsed `recommendedMaxWorkingSetSize = 19069.67 MB`
  (ggml_metal_device_init GPU init log) as decode_tps. Additionally files were pretty-printed
  multi-line JSON, not valid JSONL. Archived to `.archive/m4_cpu_corrupted/`.
- **Script:** `scripts/bench/m4_cpu_tps.sh` (NEW — corrected, uses llama-bench -ngl 0)
- **Command:** `bash scripts/bench/m4_cpu_tps.sh`
- **Est. runtime:** ~90-120 min (7 variants × 4 ctx × 10 trials, CPU without Metal)
- **Device:** M4 Mac — reconnect and run when available
- **Integration after completion:**
  1. Verify all tg128 values in range 3-25 tok/s; no value equals 19069.67
  2. Verify ordering: Q2_K fastest, Q6_K slowest (matches ARM/x86 non-monotonic pattern)
  3. Update `results/gpu_vs_cpu_comparison.json` CPU columns with real values
  4. Add M4 CPU column to cross-platform table in `report/report.tex` §8
  5. Update registry `m4-cpu-tps-all-variants` → complete

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
| GAP-5       | MEDIUM   | Not started                   | Next laptop session | — |
| GAP-6       | MEDIUM   | Not started                   | Next laptop session | — |
| GAP-7       | MEDIUM   | ⏳ Script ready, needs Mac session | Next Mac session | Script: m4_cpu_tps.sh |
