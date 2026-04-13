# Canonical Results Manifest
## DSC 291 EAI — GGUF Quantization on Mobile ARM

This file maps every paper figure and table claim to its source result directory.
All other result directories under `results/` are exploratory runs or superseded.

---

## Paper: `report/report.pdf` (20 pages)

### Table 1 — Main Results (TPS, PPL, BoolQ)

| Column | Source |
|--------|--------|
| Decode TPS (±std) at ctx=256 | `results/pixel_llama_tps_20260325_120022/` |
| Prefill TPS, TTFT, E2E | `results/pixel_llama_tps_20260325_120022/` |
| BoolQ accuracy + Wilson CI | `results/quality_scores.json` keys `boolq:*` |
| PPL Q2_K, Q3_K_M (Pixel, full corpus ~285K tok) | `results/perplexity_scores.json` via `pixel_6a_ppl_final/` |
| PPL Q4_K_S–Q8_0 (x86, full corpus ~290K tok) | `results/x86_perplexity_results.json` |

### Table 2 — KV-Cache Cliff (filled-context sweep)

**Methodology note:** All cliff directories use `"methodology":"filled_context"` — prompts
are sized N-64 tokens so the KV cache is actually saturated. Earlier runs using
`-c N` (allocation-only) are in `results/pixel_llama_cliff_20260325_060911/` (superseded).

Per-variant canonical sources (some variants require dedicated reruns; see VERIFIED_METRICS_MASTER_TABLE.md):

| Variant | Source | n | Notes |
|---------|--------|---|-------|
| Q2_K, Q3_K_M, Q4_K_S, Q8_0 | `pixel_llama_cliff_filled_20260329_162354/` | 10 | Canonical n=10 batch |
| Q4_K_M | `pixel_llama_cliff_filled_20260326_132101/` | 3 | ⚠ Inflated baseline in `canonical_n10/`; use this run |
| Q5_K_M | `pixel_llama_cliff_filled_20260410_142752/` | 5 | ✅ Clean isolated rerun — cliff onset ctx=512 confirmed |
| Q6_K | `pixel_llama_cliff_filled_20260330_212946/` | 10 | Clean solo rerun |

**⚠ Do NOT use `pixel_llama_cliff_filled_canonical_n10/` for Q4_K_M** (7.6 tok/s inflated baseline).  
**⚠ Do NOT use n=3 run `20260326_132101` for Q5_K_M** (cold baseline masked ctx=512 cliff).

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
| fig_cliff_crossplat | `figures/fig_cliff_crossplat.png` | ARM + Metal 2-panel (old) |
| fig_cliff_crossplat_sel | `figures/fig_cliff_crossplat_sel.png` | ARM + Metal selected variants 2-panel |
| **fig_cliff_3plat_sel** | **`figures/fig_cliff_3plat_sel.png`** | **ARM + x86 + Metal 3-panel (current paper figure)** |
| fig_ppl_vs_accuracy | `figures/fig_ppl_vs_accuracy.png` | quality_scores.json PPL × accuracy scatter |
| fig_xplat_quality_4bench | `figures/fig_xplat_quality_4bench.png` | cross-platform quality 4-benchmark heatmap |

### Cross-Device (x86 + M4 Metal) — RQ4 / §5.5

| Claim | Source |
|-------|--------|
| x86 TPS (Q2_K 14.05, Q4_K_S 8.93, Q4_K_M 8.55, Q6_K 6.80 tok/s) | `results/x86_tps_results.json` |
| x86 filled-context cliff (Q2_K −51% at ctx=2048, cliff ctx=1200–1300) | `results/x86_llama_cliff_20260408_070924/` ✅ canonical (7 variants, TG=128) |
| x86 quality — all 6 benchmarks × 7 variants (HellaSwag, MMLU, BoolQ, TruthfulQA, ARC-C, ARC-E) | `results/quality_scores.json` keys `x86_hellaswag:*`, `x86_mmlu:*`, `x86_boolq:*`, `x86_truthfulqa:*`, `x86_arc_challenge:*`, `x86_arc_easy:*` |
| x86 PPL (Q2_K 11.73, Q4_K_S 9.74, Q4_K_M 9.75, Q8_0 9.71) | `results/x86_perplexity_results.json` |
| M4 Metal TPS (Q4_K_S 19.9, Q4_K_M 19.2, Q2_K 17.8, Q8_0 6.4 tok/s) | `results/m4_llama_tps_20260326_001546/` |
| M4 Metal cliff (flat to +8.5%; Q2_K +8.5%, Q3_K_M +3.4%, others ≤±0.8%; no degradation) | `results/m4_metal_cliff_20260323_015934/` |
| Pixel Qwen TPS (Q2_K=13.9 fastest, Q6_K=7.25 slowest; non-monotonic ordering replication) | `results/pixel_qwen_tps_20260326_033619/` |
| Pixel Qwen cliff sweep (5 trials, 7 variants × 11 ctx; confirms Q2_K cliff on different model) | `results/pixel_qwen_cliff_filled_20260330_235410/` ✅ canonical |

**Platform metadata:**
- x86: Intel i5-1235U, 12th Gen, Windows 11, 6 threads, llama-cli CPU-only (ngl=0)
- M4: MacBook Air M4, Metal GPU (16-core), llama-bench ngl=99, 10 trials
- Pixel 6a Qwen: ARM CPU, 4 threads, llama-completion, Qwen 2.5 1.5B Instruct GGUF

---

## Exploratory / Superseded Runs

These directories exist but are NOT cited in the paper. Kept for audit trail.

| Directory | Status | Notes |
|-----------|--------|-------|
| `pixel_llama_cliff_20260325_060911/` | ⚠️ Superseded | Allocation-only methodology (not filled) |
| `pixel_cliff_sweep_20260321_081838/` | ⚠️ Superseded | Early sweep, stale methodology |
| `pixel_cliff_sweep_20260324_104839/` | ⚠️ Superseded | Pre-filled-context run |
| `kv_cache_cliff_20260320_021544/` | ⚠️ Superseded | Allocation-only |
| `m4_llama_cliff_20260325_*/` | ⚠️ Superseded | decode_tps=0 (derived metric parsing failure) |
| `m4_metal_cliff_20260321_*/` | ⚠️ Superseded | Early M4 cliff runs, incomplete |
| `m4_metal_cliff_20260323_015934/` | ✅ Cited (§5.4 Metal cliff elimination) | Complete: 7 variants × 13 ctx × 5 trials, all valid |
| `pixel_overnight_20260320_021818/` | 🔵 Exploratory | Overnight sweep, pre-final methodology |
| `pixel_power_20260320_173728/` | ✅ Cited (fig5) | Battery measurement run |
| `pixel_6a_ppl_final/` | ✅ Cited (Table 1 PPL) | Full WikiText-2 PPL for Q2_K, Q3_K_M |

---

*Last updated: 2026-04-13*

---

## All Runs Complete — No Active Runs

All primary experiments finished as of 2026-04-02.

| Completed Run | Final Status |
|---------------|-------------|
| `pixel_qwen_cliff_filled_20260330_235410/` | ✅ 7 variants × 55 rows each; complete |
| `pixel_llama_cliff_filled_canonical_n10/` | ✅ All 7 variants n=10; Q2_K cliff −48% at ctx≈512 |
| `m4_metal_cliff_20260323_015934/` | ✅ All 7 variants × 13 ctx × 5 trials; flat ±2%, no cliff |
| `x86_llama_cliff_20260408_070924/` | ✅ Q2_K −51% at ctx=2048, cliff ctx=1200–1300; 7 variants, TG=128 |

### Superseded / Abandoned (not cited)

| Directory | Reason |
|-----------|--------|
| `pixel_qwen_cliff_filled_20260330_004954/` | Superseded by `20260330_235410/` (orphaned process contamination) |
| `pixel_llama_cliff_filled_20260330_172822/` | Deleted — contaminated by orphaned llama-perplexity process |
| `x86_llama_cliff_20260329_002333/` | Superseded by `20260408_070924/` (TG=64; CV higher; incomplete variant set) |
| `x86_llama_cliff_20260328_183442/` | Superseded — early test run, incomplete |
| `mac_humaneval_*/` | Methodology broken (chat-template incompatibility); archived |
