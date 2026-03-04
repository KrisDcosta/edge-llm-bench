# Quantized On-Device LLM Inference Study (ExecuTorch + Android)

This repo benchmarks Llama 3.2 3B on Android (Pixel 6a) using ExecuTorch across quantization levels (16/8/6/4/2-bit attempt).

## Docs
- PRD: `PRD.md`
- Execution plan: `plan.md`
- Agent instructions: `agent.md`

## Repo conventions
- Benchmark outputs are JSONL in `results/` (not committed).
- Schema contracts live in `schemas/`.
- All plots must be reproducible from raw logs.

## Directory layout
- `android/`: Android app and on-device execution code
- `analysis/`: scripts and notebooks for benchmark analysis
- `experiments/`: experiment registry and run planning files
- `prompts/`: fixed prompt sets used for reproducible runs
- `schemas/`: JSON schema definitions for logged results
- `scripts/`: validation, smoke-test, and runner utilities
- `results/`: generated benchmark outputs (ignored by Git)

## Example result record
Successful trial records set `failure` to `null`. Failed, blocked, or unsupported trials keep the same shape and populate `failure`, while any unavailable measurements remain `null`.

```json
{
  "record_version": "1.0",
  "run_id": "pixel6a-q8-ctx1024-20260303-01",
  "status": "success",
  "device": {
    "manufacturer": "Google",
    "model": "Pixel 6a",
    "android_version": "14",
    "build_fingerprint": "google/bluejay/bluejay:14/AP1A.240505.004/1234567:user/release-keys"
  },
  "build": {
    "executorch_version": "0.5.0",
    "app_build_id": "android-debug-20260303"
  },
  "model": {
    "name": "Llama 3.2 3B",
    "artifact_hash": "sha256:0123456789abcdef",
    "quant_bits": 8
  },
  "trial": {
    "prompt_id": "qa_short_001",
    "context_length": 1024,
    "output_length": 128,
    "trial_index": 0,
    "is_warmup": false
  },
  "timing_s": {
    "t_request_start": 100.0,
    "t_model_forward_start": 100.05,
    "t_first_token": 100.85,
    "t_last_token": 104.05
  },
  "tokens": {
    "input_tokens": 243,
    "output_tokens": 128
  },
  "metrics": {
    "ttft_s": 0.85,
    "prefill_s": 0.8,
    "prefill_tps": 303.75,
    "gen_s": 3.2,
    "decode_tps": 40.0,
    "e2e_s": 4.05,
    "gen_over_prefill": 4.0,
    "prefill_frac": 0.1975,
    "gen_frac": 0.7901
  },
  "resources": {
    "peak_rss_mb": 2140.5,
    "battery_start_pct": 76.0,
    "battery_end_pct": 75.8,
    "battery_drop_pct": 0.2,
    "battery_drop_per_1k_tokens": 0.5391,
    "temperature_c": 36.5
  },
  "failure": null
}
```

## Next steps
1) Implement smoke test producing one JSON record
2) Add schema validator
3) Add config runner + experiment registry
4) Add analysis plots
5) Add minimal Android UI demo
