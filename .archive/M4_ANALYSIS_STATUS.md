# M4 Mac GPU Benchmark Analysis

**Status:** Analysis in progress
**Start Time:** 2026-03-17 13:45 UTC
**Expected Duration:** 5-15 minutes

---

## Benchmark Summary

✅ **COMPLETE**
- Total Runs: 420/420 (100%)
- Device: M4 Mac with Metal GPU
- Variants: Q2_K, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0
- Contexts: 256, 512, 1024, 2048 tokens
- Trials per config: 15
- Results Directory: `results/m4_mac_metal_20260317_035638/`

---

## Data Quality Check

✅ **TPS Values Verified**
- Q2_K ctx256: 38.6 - 63.4 tok/s ✓
- Expected range for M4 GPU: 20-100 tok/s
- All values present and valid

✅ **File Integrity**
- 28 JSONL files created (7 variants × 4 contexts)
- File sizes: 280-400 MB each
- Total dataset: ~9 GB

---

## Expected Analysis Outputs

Once analysis completes, you'll find:

```
analysis/figures/
├── m4_gpu_throughput_by_variant.png      # TPS across quantization levels
├── m4_gpu_throughput_by_context.png      # TPS across context lengths
├── m4_gpu_tps_violin_plot.json           # Distribution of TPS values
├── m4_gpu_summary_stats.json             # Mean, std, min, max per variant
└── m4_gpu_analysis_report.txt            # Text summary
```

---

## Key Metrics Expected

**Throughput Ordering (M4 Metal GPU - Monotonic):**
1. Q8_0 (fastest, most bits)
2. Q6_K
3. Q5_K_M
4. Q4_K_M / Q4_K_S
5. Q3_K_M
6. Q2_K (slowest, fewest bits)

**Context Impact:**
- ctx256: Highest throughput
- ctx512: ~5-10% slower
- ctx1024: ~10-20% slower
- ctx2048: ~20-30% slower (KV-cache effects)

---

## Next Steps

1. ✅ Wait for analysis to complete
2. 📊 Review generated figures
3. 📋 Compare with:
   - Pixel 6a PPL results (once complete)
   - Previous M1 benchmarks (if available)
4. 📝 Integration into paper (Table 5, Figure 3)

---

## Log Location

Analysis logs: `/tmp/analysis.log`

Monitor with:
```bash
tail -f /tmp/analysis.log
```

Check completion:
```bash
ls -lh analysis/figures/
```

