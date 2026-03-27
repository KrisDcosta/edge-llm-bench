# Canonical Results Manifest
## DSC 291 EAI — GGUF Quantization on Mobile ARM

This file maps every paper figure and table claim to its source result directory.
All other result directories under `results/` are exploratory runs or superseded.

---

## Paper: `report/report.pdf` (12 pages)

### Table 1 — Main Results (TPS, PPL, BoolQ)

| Column | Source |
|--------|--------|
| Decode TPS (±std) at ctx=256 | `results/pixel_llama_tps_20260325_120022/` |
| Prefill TPS, TTFT, E2E | `results/pixel_llama_tps_20260325_120022/` |
| BoolQ accuracy + Wilson CI | `results/quality_scores.json` keys `boolq:*` |
| PPL (WikiText-2, full corpus) | `results/pixel_6a_ppl_final/` (Q2_K, Q3_K_M); others = 12KB sample |

### Table 2 — KV-Cache Cliff (filled-context sweep)

| Column | Source |
|--------|--------|
| TPS at ctx=256,512,1024,2048 | `results/pixel_llama_cliff_filled_20260326_132101/` |
| Cliff % and onset | Computed from above; see RQ2 section in paper |

**Methodology note:** Files in this directory use `"methodology":"filled_context"` — prompts
are sized N-64 tokens so the KV cache is actually saturated. Earlier runs using
`-c N` (allocation-only) are in `results/pixel_llama_cliff_20260325_060911/` (superseded).

### Table 3 — Quality Benchmarks (all 6 × 7 variants)

| Benchmark | Source key in `results/quality_scores.json` |
|-----------|---------------------------------------------|
| ARC-Challenge | `arc_challenge:*` |
| ARC-Easy | `arc_easy:*` (re-run 2026-03-27; extracted-letter eval) |
| HellaSwag | `hellaswag:*` |
| MMLU | `mmlu:*` |
| BoolQ | `boolq:*` |
| TruthfulQA | `truthfulqa:*` |

### Figure References

| Figure | File | Source |
|--------|------|--------|
| fig1_prefill_tps_vs_context | `figures/fig1_prefill_tps_vs_context.png` | pixel_llama_tps_20260325_120022 |
| fig2_decode_tps_vs_context | `figures/fig2_decode_tps_vs_context.png` | pixel_llama_tps_20260325_120022 |
| fig3_ttft_vs_context | `figures/fig3_ttft_vs_context.png` | pixel_llama_tps_20260325_120022 |
| fig4_peak_memory_vs_quant | `figures/fig4_peak_memory_vs_quant.png` | pixel_llama_tps_20260325_120022 |
| fig5_battery_per_1k_tokens | `figures/fig5_battery_per_1k_tokens.png` | pixel_power_20260320_173728 |
| fig6_pareto_efficiency_quality | `figures/fig6_pareto_efficiency_quality.png` | quality_scores.json + tps above |
| fig7_prefill_vs_decode_fraction | `figures/fig7_prefill_vs_decode_fraction.png` | pixel_llama_tps_20260325_120022 |
| fig8_latency_distribution | `figures/fig8_latency_distribution.png` | pixel_llama_tps_20260325_120022 |
| fig9_model_size_vs_decode_tps | `figures/fig9_model_size_vs_decode_tps.png` | pixel_llama_tps_20260325_120022 |
| fig_kv_cliff | `figures/fig_kv_cliff.png` | pixel_llama_cliff_filled_20260326_132101 |

### Cross-Device (M4 Metal) — RQ4

| Claim | Source |
|-------|--------|
| M4 Metal TPS (Q4_K_S 19.9, Q4_K_M 19.2, Q2_K 17.8, Q8_0 6.4 tok/s) | `results/m4_llama_tps_20260326_001546/` |

---

## Exploratory / Superseded Runs

These directories exist but are NOT cited in the paper. Kept for audit trail.

| Directory | Status | Notes |
|-----------|--------|-------|
| `pixel_llama_cliff_20260325_060911/` | ⚠️ Superseded | Allocation-only methodology (not filled) |
| `pixel_cliff_sweep_20260321_081838/` | ⚠️ Superseded | Early sweep, stale methodology |
| `pixel_cliff_sweep_20260324_104839/` | ⚠️ Superseded | Pre-filled-context run |
| `kv_cache_cliff_20260320_021544/` | ⚠️ Superseded | Allocation-only |
| `m4_llama_cliff_20260325_*/` | 🔵 Exploratory | M4 cliff sweeps; not yet in paper |
| `m4_metal_cliff_20260321_*/` | 🔵 Exploratory | Early M4 cliff runs |
| `pixel_overnight_20260320_021818/` | 🔵 Exploratory | Overnight sweep, pre-final methodology |
| `pixel_power_20260320_173728/` | ✅ Cited (fig5) | Battery measurement run |
| `pixel_6a_ppl_final/` | ✅ Cited (Table 1 PPL) | Full WikiText-2 PPL for Q2_K, Q3_K_M |

---

*Last updated: 2026-03-27*
