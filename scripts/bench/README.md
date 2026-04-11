# scripts/bench/ — Benchmark Scripts Reference

This directory contains all benchmark scripts for the project.
Scripts are labeled: **Active** (used in paper), **Exploratory** (experimental), or **Superseded** (replaced by better methodology).

---

## Active Scripts — Used in Paper

| Script | Status | Paper Section | Description |
|--------|--------|---------------|-------------|
| `pixel_llama_tps.sh` | ✅ Active | Table 1 (TPS) | Pixel 6a decode/prefill TPS sweep — 7 variants × 4 contexts × 10 trials |
| `pixel_llama_cliff_filled.sh` | ✅ Active | Table 2 (RQ2) | Filled-context KV-cache cliff sweep — prompts sized N-64 tokens to saturate KV cache |
| `pixel_quality.sh` | ✅ Active | Table 3 (RQ3) | Quality benchmarks via ADB — ARC-Challenge, ARC-Easy, HellaSwag, MMLU, BoolQ, TruthfulQA |
| `m4_llama_tps.sh` | ✅ Active | Table 4 (M4 cross-device) | Mac M4 Metal TPS sweep — same variants, Metal GPU backend |
| `m4_llama_cliff.sh` | 🔵 Exploratory | Not in paper (yet) | M4 filled-context cliff sweep — data collected, analysis pending |

---

## Superseded Scripts — Do Not Use

| Script | Status | Replaced By | Why Superseded |
|--------|--------|-------------|----------------|
| `pixel_llama_cliff.sh` | ⚠️ Superseded | `pixel_llama_cliff_filled.sh` | Used `-c N` (allocation-only); KV cache was NOT actually saturated. Results were systematically wrong for RQ2. |

---

## Exploratory Scripts — Not in Paper

| Script | Status | Notes |
|--------|--------|-------|
| `pixel_qwen_tps.sh` | 🔵 Exploratory | Qwen 0.5B TPS on Pixel — not in paper scope |
| `pixel_wikitext_ppl.sh` | 🔵 Exploratory | Full WikiText-2 PPL sweep — partial data used in Table 1 PPL column |
| `m4_qwen_tps.sh` | 🔵 Exploratory | Qwen on M4 Metal — not in paper scope |
| `m4_qwen_cliff.sh` | 🔵 Exploratory | Qwen cliff sweep on M4 — not in paper scope |
| `pixel_llama_fa_mitigation.sh` | ⛔ Blocked | Flash Attention unsupported on this llama-completion binary build |
| `x86_llama_tps.sh` | 🔵 Exploratory | x86 CPU TPS (HP Pavilion) — not yet run; pending |

---

## Canonical Result Directories

See `results/CANONICAL.md` for the full manifest linking each script run → paper figure/table.

Quick reference:
- **Table 1 TPS**: `results/pixel_llama_tps_20260325_120022/`
- **Table 2 cliff**: `results/pixel_llama_cliff_filled_20260326_132101/`
- **Table 3 quality**: `results/quality_scores.json`
- **Table 4 M4**: `results/m4_llama_tps_20260326_001546/`

---

## Common Usage

```bash
# Full TPS sweep (Pixel 6a, ~45 min)
bash scripts/bench/pixel_llama_tps.sh

# KV-cache cliff sweep — filled-context (Pixel 6a, ~90 min)
bash scripts/bench/pixel_llama_cliff_filled.sh

# Quality benchmarks (Pixel 6a via ADB, ~3 hours total)
bash scripts/bench/pixel_quality.sh boolq
bash scripts/bench/pixel_quality.sh arc_easy
bash scripts/bench/pixel_quality.sh arc_challenge
bash scripts/bench/pixel_quality.sh hellaswag
bash scripts/bench/pixel_quality.sh mmlu
bash scripts/bench/pixel_quality.sh truthfulqa

# M4 Metal TPS sweep (~45 min)
bash scripts/bench/m4_llama_tps.sh
```
