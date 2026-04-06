# Archived: Contaminated Experiment Runs

These files contain runs that were marked `status: "contaminated"` due to
concurrent process interference during data collection. They are archived
here rather than deleted to preserve the audit trail.

They are **NOT referenced** in any analysis, paper sections, or summary tables.

---

## run-20260307T042308.jsonl

- **Variant:** Q8_0
- **Records:** 17
- **Run date:** 2026-03-07
- **Contamination type:** `concurrent_process_memory_contention`
- **Root cause:** `llama-perplexity` running concurrently on device during benchmark.
  Memory contention caused degraded decode throughput (0.24–2.34 t/s vs expected ~2.0–2.5 t/s).
  Some trials show decode_tps = 0.24 t/s (10× slower than clean runs).
- **Evidence:** All 17 records carry `"status": "contaminated"` and
  `"failure.code": "contaminated"` with `"failure.message": "concurrent_process_memory_contention"`.
- **Action:** Archived 2026-04-06. Not included in any analysis.
- **Clean replacement:** Q8_0 results from the canonical cliff sweep
  (`results/pixel_llama_cliff_filled_canonical_n10/cliff_filled_Q8_0.jsonl`)
  are unaffected and used in all analysis.
