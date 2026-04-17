# Public Release Audit

Date: 2026-04-17

This audit was completed against the canonical public build path:

```bash
python3 scripts/build_public_release.py
```

That command now rebuilds the parquet dataset from `results/`, re-bakes the dashboard JSON,
writes `artifacts/public_release_manifest.json`, writes `artifacts/public_truth_table.md`,
and fails if the public repo drifts from the validated artifact contract.

## Release Verdict

The repo is ready to be public in its current v1 state.

The public-facing dataset and dashboard now expose only validated, reproducible work:
- contaminated Pixel Qwen cliff data is excluded
- M4 Qwen TPS/cliff data is promoted from the validated 2026-04-15/16 reruns
- x86 Qwen cliff reruns are excluded because they contain missing/zero-throughput large-context rows
- Pixel cliff metrics are built from the same per-variant canonical sources cited in `results/CANONICAL.md`
- Pixel TPS metrics are built from the canonical `pixel_llama_tps_20260325_120022/` batch
- quality benchmark names are normalized to the 6-task public schema
- exploratory bare-key `custom_qa` rows are excluded from the public split

## Verified Build Outputs

From the validated release manifest:

| Split | Rows |
|---|---:|
| `pixel_inference.parquet` | 1,819 |
| `m4_inference.parquet` | 1,035 |
| `x86_inference.parquet` | 399 |
| `quality_benchmarks.parquet` | 128 |
| `perplexity.parquet` | 14 |
| **Total published records** | **3,395** |

Additional release-contract checks:

| Check | Result |
|---|---|
| Published inference rows | 3,253 |
| Dashboard `raw_table.json` rows | 3,253 |
| Quality device split | Pixel6a=86, x86=42 |
| Pixel Qwen rows | 522 |
| Pixel Qwen split | cliff\_sweep=385, standard\_sweep=137 |
| M4 Qwen rows | 98 |
| M4 Qwen split | cliff\_sweep=91, standard\_sweep=7 |
| Dashboard collapse thresholds | Pixel6a=512, Pixel Qwen=512, x86=1300–1400, M4 Llama/Qwen=none |

## Files Added For Phase 1

- `scripts/build_public_release.py`
- `artifacts/public_release_manifest.json`
- `artifacts/public_truth_table.md`
- `.github/workflows/validate-public-release.yml`
- `docs/PUBLIC_RELEASE_AUDIT.md`
- `docs/NEXT_PHASES_HANDOFF.md`

## What Phase 1 Now Guarantees

- One canonical public rebuild command
- One generated public manifest with split counts and dashboard contract
- One generated public truth table for headline metrics
- CI validation for schema drift, contaminated run leakage, stale dashboard copy, and doc/source drift
- Public docs reference only public artifacts, not ignored private working notes

## Remaining Caveats

- The Hugging Face dataset card was re-uploaded and verified against the new counts (`3,395` total records).
- The dashboard is generated and validated locally; GitHub Pages will reflect this after the updated build is pushed.
- M4 quality remains excluded. The server-based runner avoided crashes, but the current run mostly predicted `A`, so it is not quality evidence.

## Recommended Release Checklist

1. Push the current branch to GitHub.
2. Confirm the `Validate Public Release` workflow passes.
3. Confirm the `Deploy Dashboard to GitHub Pages` workflow passes.
4. Spot-check the live dashboard and the Hugging Face dataset card against `artifacts/public_release_manifest.json`.

The refreshed Hugging Face dataset has already been uploaded and verified against the
same split counts in this audit.
