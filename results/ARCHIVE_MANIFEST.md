# Results Archive Manifest

This file records result artifacts that were removed from the top-level `results/`
namespace so they cannot be mistaken for canonical evidence. The archive directories
are local audit trail only; canonical public sources are listed in `results/CANONICAL.md`.

## 2026-04-15 Cleanup

| Archived group | Reason | Replacement / current status |
|---|---|---|
| `results/archive/m4_qwen_superseded_20260415/` | Old M4 Qwen TPS/cliff runs were incomplete, high-variance, empty, or generated with the unstable 32-token cliff window. | M4 Qwen TPS is now `results/m4_qwen_tps_20260415_130955/`; M4 Qwen cliff is now `results/m4_qwen_cliff_20260416_021323/`. |
| `results/archive/m4_quality_failed_20260415/quality_metrics_m4.json` | M4 quality attempt timed out question-by-question and contains invalid 0% results / dry-run artifacts. | No M4 quality evidence is canonical. Redesign the runner before rerunning. |
| `results/archive/stale_summaries_20260415/` | Old summary JSON files referenced stale M4 quality and early project scope. | Use `artifacts/public_release_manifest.json`, `artifacts/public_truth_table.md`, and `results/CANONICAL.md`. |

## 2026-04-16 Cleanup

| Archived group | Reason | Replacement / current status |
|---|---|---|
| `results/archive/m4_qwen_superseded_20260416/` | M4 Qwen cliff attempts from 2026-04-15 and targeted `Q4_K_M` from 2026-04-16 were diagnostic/intermediate. The 2026-04-15 full run had an impossible `Q4_K_M ctx=1800` spike; the targeted rerun was valid but not same-session comparable. | M4 Qwen cliff is now `results/m4_qwen_cliff_20260416_021323/`. |
| `results/archive/m4_quality_failed_20260416/quality_metrics_m4_server.json` | Server-based M4 quality runner avoided crashes, but the run mostly predicted `A` for multiple-choice tasks. This is not publishable quality evidence. | No M4 quality evidence is canonical. Redesign prompts/scoring before rerunning. |
| `results/archive/m4_cpu_tps_superseded_20260416/` | Earlier M4 CPU TPS rerun was superseded before promotion. | M4 CPU TPS is now `results/m4_cpu_tps_20260415_231524/`. |

## 2026-04-17 Public-Release Cleanup

| Removed top-level artifact | Reason | Replacement / current status |
|---|---|---|
| `results/m4_cpu_tps_20260406_203938/` | Clean but superseded M4 CPU TPS run; retaining it beside the newer run made the canonical source ambiguous. | M4 CPU TPS is now `results/m4_cpu_tps_20260415_231524/`. |
| `results/m4_cpu_tps_20260415_125713/` | Intermediate rerun not promoted to canonical. | M4 CPU TPS is now `results/m4_cpu_tps_20260415_231524/`. |
| `results/m4_mac_metal_20260317_022155/`, `results/m4_mac_metal_20260317_035031/` | Early parser-contaminated raw files stored GPU memory size as throughput. | Excluded from all public builds; the current parser aborts if this contamination appears. |
| `results/gpu_vs_cpu_comparison.json`, `results/GPU_CPU_COMPARISON_README.md`, `results/COMPARISON_ANALYSIS.md` | Derived from old CPU/GPU comparison work and stale after the April 15 CPU rerun. | Use `dataset/m4_inference.parquet`, dashboard JSON, and `artifacts/public_release_manifest.json`. |
| `results/x86_qwen_cliff_DESKTOP-D70B_20260412_145905/` | Invalid x86 Qwen cliff attempt; not complete enough for publication. | No x86 Qwen cliff is canonical in Phase 1. Rerun with the corrected script before integration. |
| `results/m4_quality_server_logs/` | Logs from a failed M4 quality attempt that mostly predicted one answer class. | No M4 quality evidence is canonical. Redesign prompts/scoring before rerunning. |
