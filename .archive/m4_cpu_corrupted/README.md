# Archived: Corrupted M4 Mac CPU Benchmark Data

Both directories contain invalid data with two distinct problems.
Neither directory is referenced in any analysis.

---

## Root Cause

**Problem 1 — Wrong value parsed as decode_tps:**
All records have `"decode_tps": 19069.67`. This is NOT a throughput measurement.
It is the `recommendedMaxWorkingSetSize = 19069.67 MB` GPU memory spec line from
`ggml_metal_device_init` log output, incorrectly parsed as tokens/second by the
collection script.

The raw_output confirms: the script scraped the memory spec line instead of the
actual llama.cpp timing output (`eval time = X.XX tokens per second`).

**Problem 2 — Multi-line JSON stored as JSONL:**
Each record is a pretty-printed multi-line JSON object stored in a `.jsonl` file.
JSONL requires one JSON object per line. The files are not valid JSONL.

**Conclusion:** The M4 CPU data is entirely invalid. No records contain real
throughput measurements.

---

## Directories

- `m4_mac_cpu_20260317_022155/` — single Q2_K ctx=256 file only (partial run)
- `m4_mac_cpu_20260317_214131/` — full 7-variant × 4-context run (all corrupted)

## gpu_vs_cpu_comparison.json

`results/gpu_vs_cpu_comparison.json` also references these CPU values and should
not be used for CPU comparisons. The GPU data in that file is valid.

## M4 Metal GPU data (not affected)

`results/m4_mac_metal_20260317_035638/` is clean and unaffected. All GPU metrics
from the Metal run are valid for analysis.

## Re-run plan

To collect valid M4 CPU data, re-run benchmarks on the Mac with a corrected
parsing script that extracts `eval time = X.XX tokens per second` from llama.cpp
output, not GPU device initialization lines.
