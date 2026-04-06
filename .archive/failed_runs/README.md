# Archived: Failed Experiment Runs

These runs failed during data collection due to tooling bugs and are **not referenced**
in any analysis. Archived here for audit trail only.

---

## Flash Attention (-fa) Parse Failures — 2026-03-14

**Root cause:** llama.cpp changed its CLI flag syntax from `-fa` (boolean) to `-fa on`
(value-required) between builds. The benchmark runner passed `-fa` without a value,
causing `returncode=1` with `error while handling argument "-fa": error`.

**Files:**
- `run-20260314T114204.jsonl` — 235 rows: 188 success + **47 PARSE_FAILURE** (Q4_K_S)
- `run-20260314T143302.jsonl` — 235 rows: 188 success + **47 PARSE_FAILURE** (Q5_K_M)
- `run-20260314T172119.jsonl` — 7 rows: **7 PARSE_FAILURE** (Q4_K_S, retry attempt)

**Fix applied:** `benchmark_runner.py` updated to pass `-fa on` syntax.
**Clean replacement:** Q4_K_S and Q5_K_M data collected in subsequent clean runs.

---

## Process Exit / Parse Failures — 2026-03-07 and 2026-03-20

These runs had individual trial failures (returncode=143 signal/OOM, returncode=255
parse error) mixed in with valid successes. The valid records were superseded by later
clean canonical runs.

**Files:**
- `run-20260307T042757.jsonl` — 1 row: Q2_K failed (returncode=143, likely OOM/signal)
- `run-20260320T201608.jsonl` — 32 rows: 18 success + 14 failed (Q2_K, returncode=255)
- `run-20260320T220431.jsonl` — 32 rows: 5 success + 27 failed (Q4_K_M, returncode=255)

**Clean replacement:** Canonical n=10 cliff sweep data for all variants.
