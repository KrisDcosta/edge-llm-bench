# Phase 1.1 Runbook

Date: 2026-04-21

Phase 1 is the public release baseline. Phase 1.1 is an extension pass for
evidence that missed the public-release cutoff. Do not mix incomplete Phase 1.1
results into the dashboard, Hugging Face dataset, or report claims.

## Current Status

Phase 1.1 tooling is ready for the remaining runs:

- Pixel NEON/simpleperf runner supports `--filled-context` and records
  `prompt_mode`, `prompt_eval_tokens`, prefill TPS, decode TPS, PMU counters,
  and backend stall counters.
- NEON analyzer reports `PMU cache-miss proxy/tok`, not definitive L2 misses,
  unless the active event set explicitly uses raw `r17`.
- x86 Qwen cliff runner retries incomplete `llama-bench` output, supports
  `--resume`, writes debug payloads, and exits nonzero if invalid cells remain.
- Public Phase 1 build remains unchanged: x86 Qwen cliff and NEON PMU data are
  excluded until the validation gates below pass.

## What Remains

| Work item | Status | Blocking reason |
|---|---|---|
| Pixel NEON PMU, all 7 variants | Complete | `results/pixel_neon_perf_20260422_025741/` passed strict validation: 42/42 success rows, filled-context prompts, no warnings. |
| x86 Qwen cliff | Pending | Previous pushed runs had missing/zero-throughput cells; hardened runner must produce a clean all-variant directory. |
| WikiText full-corpus audit | Complete | Public PPL split has Pixel6a=7 and x86=7 rows, all `wikitext2_full`, no missing PPL values. |
| Report/dashboard integration | Partial | Report/canonical docs can cite NEON PMU as supplementary; dashboard/public parquet remain unchanged until x86 Qwen is clean. |
| Hugging Face re-upload | Not needed yet | NEON PMU is supplementary raw results; public parquet counts remain unchanged. |

## Execution Order

### 0. Start From A Clean Baseline

```bash
git pull
python3 scripts/build_public_release.py
```

Expected state:

- build exits `0`
- `artifacts/public_release_manifest.json` still reports `3,437` total records
- x86 Qwen cliff remains excluded
- no Phase 1.1 PMU rows appear in public parquet

### 1. Run Canonical Pixel NEON PMU

Preferred command, one clean 7-variant directory:

```bash
bash scripts/bench/pixel_neon_perf.sh --filled-context --all-variants --trials 3 --tokens 128 --ctx 256,512 --timeout 1200
```

Fallback if the 5-variant run is retained and only missing variants are needed:

```bash
bash scripts/bench/pixel_neon_perf.sh --filled-context --trials 3 --tokens 128 --ctx 256,512 --timeout 1200 Q4_K_S Q5_K_M
```

Prefer the single 7-variant directory for publication cleanliness.

Validation command:

```bash
python3 scripts/analyze/analyze_neon_perf.py --strict results/pixel_neon_perf_<timestamp>
```

Acceptance criteria:

- 42 rows for the 7-variant run: `7 variants x 2 ctx x 3 trials`
- all rows have `status=success`
- all rows have `prompt_mode=filled_context`
- ctx=256 `prompt_eval_tokens` is near `113`
- ctx=512 `prompt_eval_tokens` is near `369`
- `active_events` includes `cache-misses` or raw `r17`
- no analyzer validation warnings
- decode CV should be under 20% for every cell

Interpretation rules:

- Safe claim: quantization format changes PMU cache-miss pressure and backend
  stall behavior.
- Unsafe claim unless new data supports it: ctx=512 cliff is proven to be an
  L2-cache-refill spike.
- Use the phrase `PMU cache-miss proxy/tok` unless raw `r17` is the active event.

### 2. Run x86 Qwen Cliff On The Other Device

On the x86 machine:

```powershell
git pull
py -3 scripts/bench/x86_qwen_cliff.py --threads 6 --retries 4 --timeout 1200
```

If the run is interrupted or some cells fail:

```powershell
py -3 scripts/bench/x86_qwen_cliff.py --threads 6 --retries 4 --timeout 1200 --output-dir results/<same_x86_qwen_dir> --resume
```

The runner must finish with exit code `0`. If it prints `FAILED CELLS REMAIN`,
do not promote that directory.

Validation criteria:

- 77 rows total: `7 variants x 11 ctx`
- every row has no `error`
- every row has `decode_tps > 0`
- every row has `n_trials == 5`
- decode CV should generally be under 20%; investigate cells above that
- no `_debug` failures should be required for final publication

Validation command:

```powershell
py -3 scripts/analyze/validate_x86_qwen_cliff.py results/<x86_qwen_dir>
```

After a clean run:

```powershell
git add results/x86_qwen_cliff_<host>_<timestamp>
git commit -m "results: add clean x86 qwen cliff run"
git push
```

Then on the Mac:

```bash
git pull
python3 scripts/build_public_release.py
```

If `prepare_dataset.py` already ingests the new clean directory, the public row
counts will change. If not, update ingestion deliberately and add a validator so
old invalid x86 Qwen directories cannot leak back in.

### 3. Verify WikiText Full-Corpus PPL

Run the public build first:

```bash
python3 scripts/build_public_release.py
```

Then spot-check the public perplexity split:

```bash
python3 - <<'PY'
import pandas as pd
df = pd.read_parquet("dataset/perplexity.parquet")
print(df.groupby(["device", "corpus"]).size())
print(df[df["corpus"] != "wikitext2_full"])
print(df[df["perplexity"].isna()])
PY
```

Acceptance criteria:

- no `wikitext2_sample` rows in the public split
- no missing PPL values
- Pixel 6a has all 7 variants on `wikitext2_full`
- x86 rows, if present, are clearly marked supplementary and full-corpus

Only rerun PPL if this check fails:

```bash
python3 scripts/download_wikitext2.py
bash scripts/bench/pixel_wikitext_ppl.sh
python3 scripts/parse_ppl_full.py results/pixel_wikitext_ppl_<timestamp>
python3 scripts/build_public_release.py
```

### 4. Promote Phase 1.1 Results

Only after steps 1-3 pass:

1. Update `results/CANONICAL.md` with the exact run directories.
2. Update `docs/PUBLIC_RELEASE_AUDIT.md` if public dataset/dashboard counts change.
3. Update `README.md` only with claims backed by promoted data.
4. Update the report using constrained mechanistic language.
5. Run:

```bash
python3 scripts/build_public_release.py
git diff --check
```

6. If parquet outputs changed, re-upload Hugging Face dataset using the command
   in `CONTRIBUTING.md`.
7. Push and verify GitHub Actions plus dashboard deploy.

## Report Wording To Use

Safe wording:

> Filled-context ARM PMU counters show that quantization format materially
> changes cache pressure. In the validated all-7-variant pass, Q6_K showed
> 1.92x and Q8_0 showed 3.21x the PMU cache-miss proxy per measured token
> relative to Q2_K at ctx=256. However, the Q2_K ctx=512 throughput cliff was
> not accompanied by a proportional cache-miss proxy increase (1.07x), so the
> cliff is not explained by a simple cache-refill spike alone.

Do not write:

- `Q6_K has 3x instruction overhead`
- `KV cliff confirmed by L2 counters`
- `cache-misses:u is exactly L2D refill`
- `Phase 1.1 is complete` before clean x86 Qwen cliff passes

## Final Phase 1.1 Checklist

- [x] Pixel NEON PMU all 7 variants complete and validated
- [ ] x86 Qwen cliff all 7 variants complete and validated
- [x] WikiText full-corpus audit passes
- [x] canonical manifest updated with promoted NEON run directory
- [x] report updated with constrained PMU wording
- [x] dashboard/public parquet unchanged; no Phase 1.1 PMU blanks introduced
- [x] `python3 scripts/build_public_release.py` passes
- [ ] GitHub Actions pass after push
- [ ] Hugging Face dataset re-uploaded if parquet outputs changed
