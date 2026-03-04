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

## Next steps
1) Implement smoke test producing one JSON record
2) Add schema + validator
3) Add config runner + experiment registry
4) Add analysis plots
5) Add minimal Android UI demo
