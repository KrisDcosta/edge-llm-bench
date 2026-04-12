# Contributing to EdgeLLMBench

EdgeLLMBench is a controlled benchmarking study of GGUF quantization on edge hardware. Contributions that extend coverage (new devices, models, benchmarks) or improve reproducibility are welcome.

---

## How the Pipeline Works

Raw benchmark output flows through three stages:

```
JSONL results  →  prepare_dataset.py  →  Parquet files  →  bake_dashboard_data.py  →  8 JSON files  →  GitHub Pages dashboard
(results/*/)      (dataset/*.parquet)                      (dashboard/data/*.json)
```

**Critical rule:** Never edit `dashboard/data/*.json` directly — they are overwritten on the next bake. The parquet files in `dataset/` are the source of truth. Always update there, then re-run bake.

### Stage 1 — Run benchmark, save JSONL

Each benchmark run produces one or more JSONL files under `results/<run_id>/`. The schema is defined in `schemas/run.schema.json`. Key fields:

```jsonl
{"model": "Llama-3.2-3B-Instruct-Q4_K_M", "backend": "CPU", "context_len": 512,
 "decode_tps": 4.78, "prefill_tps": 5.94, "threads": 4, "trial": 1,
 "experiment_type": "standard_sweep", "timestamp": "2026-03-25T12:00:00Z"}
```

Validate new JSONL before committing:
```bash
python scripts/validate_results.py results/<run_id>/*.jsonl
```

### Stage 2 — Ingest into parquet

```bash
python scripts/prepare_dataset.py
```

This reads all JSONL under `results/` and rebuilds the four parquet files in `dataset/`:
- `pixel_inference.parquet`
- `m4_inference.parquet`
- `x86_inference.parquet`
- `quality_benchmarks.parquet`
- `perplexity.parquet`

### Stage 3 — Bake dashboard JSON

```bash
python scripts/bake_dashboard_data.py
```

Reads parquets, computes per-context aggregate statistics, writes `dashboard/data/*.json`.

### Stage 4 — Preview dashboard locally

```bash
cd dashboard && python -m http.server 8080
# Open http://localhost:8080
```

---

## Adding a New Device

1. Run benchmarks using one of the existing bench scripts as a template (`scripts/bench/`).
2. Save results to `results/<device>_llama_tps_<timestamp>/` using the standard JSONL schema.
3. Run `prepare_dataset.py` to ingest. The new device will appear as a new `backend` value.
4. Update `bake_dashboard_data.py` if the new device needs a dedicated dashboard section.
5. Add device specs to the Cross-Platform table in README.md.

## Adding a New Model

1. Download the GGUF file to `local-models/`.
2. Run the appropriate bench script with the new model name.
3. The model assignment in `prepare_dataset.py` is determined by the `model` field in JSONL. Ensure it matches the pattern `Llama-*` or `Qwen*` (or add a new branch).
4. Add the model to the dataset README at `dataset/README.md` and re-upload to HuggingFace.

## Adding a New Quality Benchmark

1. Create a 100-question YAML file in `data/` following the format of `boolq_100.yaml`.
2. Add the benchmark to `scripts/eval/quality_eval.py`.
3. Run the eval; scores are written to `results/quality_scores.json`.
4. Run `prepare_dataset.py` to incorporate into `quality_benchmarks.parquet`.

---

## Canonical Data Policy

- **Do not delete** any JSONL file under `results/` that is cited in `results/CANONICAL.md`.
- Superseded runs go to `archive/old-results/` with a note in CANONICAL.md explaining why.
- When adding new canonical runs, update CANONICAL.md and VERIFIED_METRICS_MASTER_TABLE.md.

## HuggingFace Dataset

The dataset is published at [KrisDcosta/edge-llm-bench](https://huggingface.co/datasets/KrisDcosta/edge-llm-bench). After adding new data:

```bash
python scripts/prepare_dataset.py          # rebuild parquets
# Then push to HuggingFace via the HF Hub CLI or web UI
huggingface-cli upload KrisDcosta/edge-llm-bench dataset/ --repo-type dataset
```

---

## Code Style

- Python: standard library + pandas/numpy/matplotlib; no style enforcer currently.
- Bash: `#!/usr/bin/env bash`; quote variables; avoid bashisms for portability.
- JSONL: one record per line; validate with `scripts/validate_results.py`.

## Submitting Changes

1. Fork the repo and create a branch: `git checkout -b feature/my-device`.
2. Add results + update parquets + bake dashboard.
3. Verify the dashboard renders correctly locally.
4. Open a PR with a brief description of the new hardware/model and key findings.
