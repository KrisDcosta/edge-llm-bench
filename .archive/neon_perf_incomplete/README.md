# Archived: Incomplete NEON/PMU Perf Counter Runs

All runs in this directory produced 100% ADB_ERROR records — no valid PMU counter
data was collected. Archived for audit trail. The script and diagnostics are preserved
for future re-run once the simpleperf event name issue is resolved.

---

## Status: BLOCKED — simpleperf event name mismatch

**Script:** `scripts/bench/pixel_neon_perf.sh` (Phase 2A)
**Goal:** Measure ARM Cortex-X1 PMU counters per K-quant variant to validate the
Q6_K ~3× L2 miss hypothesis underlying paper §6.

**Root cause of failure:**
The Pixel 6a's simpleperf version does not expose `l2-cache-misses` by name.
Available hardware events via `simpleperf list hw`: `branch-misses`, `bus-cycles`,
`cache-misses`, `cache-references`, `cpu-cycles`, `instructions`,
`stalled-cycles-backend`, `stalled-cycles-frontend`.

L2-specific data requires raw event `r17` (l2d_cache_refill, Cortex-X1 PMU code 0x17).
The script has been updated to use `cache-misses:u` (generic) and raw `r17:u` — but
the fix was not yet validated with a clean run before archiving these failed attempts.

**Script fix status:** Updated in `scripts/bench/pixel_neon_perf.sh` (lines 111-115,
event definitions, and probe logic). Requires device reconnect to validate.

## Archived runs

| Directory | Date | Variants | Records | Issue |
|-----------|------|----------|---------|-------|
| pixel_neon_perf_20260406_032748 | 2026-04-06 03:27 | Q2_K,Q3_K_M,Q4_K_M,Q6_K,Q8_0 | 30 | All ADB_ERROR (--duration 0 + kernel sampling) |
| pixel_neon_perf_20260406_101533 | 2026-04-06 10:15 | Q2_K | 3 | All ADB_ERROR (l2-cache-misses unknown event) |
| pixel_neon_perf_20260406_101600 | 2026-04-06 10:16 | All 7 | 42 | All ADB_ERROR (l2-cache-misses unknown event) |
| pixel_neon_perf_20260406_105848 | 2026-04-06 10:58 | — | 0 | Device not connected (test run) |
| pixel_neon_perf_20260406_110201 | 2026-04-06 11:02 | — | 0 | Device not connected (test run) |

## To re-run when device is available

```bash
# Verify fix first with single variant:
bash scripts/bench/pixel_neon_perf.sh Q2_K --ctx=256
# Check for non-zero cache-misses in output file

# If working, run full sweep:
bash scripts/bench/pixel_neon_perf.sh --all-variants
```

Expected events after fix: `cpu-cycles:u,instructions:u,cache-misses:u,stalled-cycles-backend:u`
