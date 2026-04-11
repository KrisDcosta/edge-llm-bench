# M4 Mac GPU vs CPU Benchmark Comparison - README

## Overview

This directory contains comprehensive performance comparison data between GPU (Metal) and CPU backends for running Llama-3.2-3B model on Apple M4 Mac hardware across 7 quantization variants and 4 context lengths.

## Generated Files

### 1. `gpu_vs_cpu_comparison.json` (Primary Output)
**Purpose:** Machine-readable JSON containing all benchmark metrics and analysis

**Structure:**
```json
{
  "metadata": {
    "gpu_directory": "...",
    "cpu_directory": "...",
    "variants": [...],
    "context_lengths": [...],
    "data_quality": {
      "status": "...",
      "issue": "...",
      "gpu_data_status": "..."
    }
  },
  "main_comparison_ctx2048": [...],
  "comparison_by_context": {...},
  "gpu_performance_analysis": {...},
  "insights": {...},
  "raw_data_summary": {...}
}
```

**Key Fields:**
- `main_comparison_ctx2048`: GPU/CPU metrics at 2048 token context (primary use case)
- `comparison_by_context`: Performance across all 4 context lengths
- `gpu_performance_analysis`: Detailed GPU-only analysis
- `data_quality`: Critical information about data validity

### 2. `COMPARISON_ANALYSIS.md` (Human-Readable Report)
**Purpose:** Detailed analysis, insights, and recommendations

**Contents:**
- Executive summary
- Data quality assessment (identifies CPU data corruption)
- GPU performance rankings
- Quantization impact analysis
- Efficiency metrics (TPS/GB)
- Context length scaling behavior
- Production recommendations
- Visualization suggestions

**Key Finding:** GPU data is valid and reliable. CPU data is corrupted (all values are identical 19069.67, extracted from GPU memory spec).

### 3. `visualization_data.json` (Chart-Ready Format)
**Purpose:** Pre-processed data optimized for visualization/plotting

**Sections:**
```
throughput_by_variant_ctx2048:
  - variants: [Q2_K, Q3_K_M, ...]
  - gpu_tps: [30.42, 26.15, ...]
  - efficiency_tps_per_gb: [9.51, 8.17, ...]

throughput_by_context_length:
  - By variant: TPS for each context (256/512/1024/2048)

efficiency_comparison:
  - Ranked by TPS/GB efficiency

summary_statistics:
  - Best/worst performers
  - Average throughput
  - Performance ranges
```

## Key Results Summary

### GPU Performance Rankings (Context: 2048 tokens)

| Rank | Variant | GPU TPS | TPS/GB | Status |
|------|---------|---------|--------|--------|
| 1 | **Q4_K_M** | **30.62** | **9.57** | **RECOMMENDED** |
| 2 | Q2_K | 30.42 | 9.51 | Good |
| 3 | Q4_K_S | 27.01 | 8.44 | Moderate |
| 4 | Q3_K_M | 26.15 | 8.17 | Moderate |
| 5 | Q6_K | 21.43 | 6.70 | Lower |
| 6 | Q5_K_M | 20.25 | 6.33 | Lower |
| 7 | Q8_0 | 17.51 | 5.47 | Avoid |

### Performance vs Context Length

GPU throughput decreases with larger context windows:
- **256 tokens:** 27.15 TPS (avg)
- **512 tokens:** 25.68 TPS (-5.4%)
- **1024 tokens:** 24.13 TPS (-11.1%)
- **2048 tokens:** 24.10 TPS (-11.3%)

→ Suggests KV-cache memory bandwidth becomes limiting factor at larger contexts

### Data Quality Status

| Component | Status | Details |
|-----------|--------|---------|
| GPU Benchmarks | ✓ VALID | All 28 files, multiple trials, realistic metrics |
| CPU Benchmarks | ✗ CORRUPTED | All values identical (19069.67), extracted from GPU memory |
| GPU/CPU Comparison | ⚠ NOT AVAILABLE | Cannot compute speedup due to CPU data quality |

## Usage Guide

### For Quick Summary
1. Read `COMPARISON_ANALYSIS.md` executive summary
2. Check the GPU performance rankings table
3. Review production recommendations

### For Visualization
1. Use `visualization_data.json` as input to plotting tools
2. See "Data Visualization Suggestions" in `COMPARISON_ANALYSIS.md` for chart recommendations
3. Example variants for charts:
   - Bar chart: GPU TPS by variant
   - Line chart: TPS vs context length (7 lines, one per variant)
   - Heatmap: TPS/GB efficiency matrix

### For Further Analysis
1. Load `gpu_vs_cpu_comparison.json` into Python/R
2. Extract `comparison_by_context` for context-length analysis
3. Use `gpu_performance_analysis` for efficiency metrics
4. Reference `insights` section for key findings

### For Data Integration
```json
// Example: Get Q4_K_M performance at all contexts
comparison_by_context["256"][3] -> Q4_K_M ctx=256
comparison_by_context["512"][3] -> Q4_K_M ctx=512
comparison_by_context["1024"][3] -> Q4_K_M ctx=1024
comparison_by_context["2048"][3] -> Q4_K_M ctx=2048
```

## Critical Issues & Recommendations

### CPU Data Problem
**Issue:** All CPU benchmark files have `decode_tps = 19069.67` (GPU memory value)
**Impact:** Cannot compare GPU vs CPU performance
**Action Required:** Re-run CPU benchmarks with proper metric extraction

**Suggestion for fix:**
1. Check benchmark script to ensure CPU metrics are correctly parsed
2. Validate CPU metrics are in reasonable range (expect 1-10 TPS for CPU)
3. Re-collect CPU data before making production decisions

### Production Use Case
**Current Recommendation:** Use GPU (Metal) backend with Q4_K_M quantization
- Best throughput: 30.62 TPS
- Best efficiency: 9.57 TPS/GB
- Optimal compression: 4-bit K-quantization
- Expected performance drop: ~11% for 256→2048 token contexts

## Data Source Information

**GPU Benchmarks:**
- Directory: `/Users/krisdcosta/291_EAI/results/m4_mac_metal_20260317_035638/`
- Files: 28 (7 variants × 4 contexts)
- Timestamp: 2026-03-17 03:56:38 UTC

**CPU Benchmarks:**
- Directory: `/Users/krisdcosta/291_EAI/results/m4_mac_cpu_20260317_214131/`
- Files: 28 (7 variants × 4 contexts)
- Timestamp: 2026-03-18 05:21:31 UTC
- Status: Data quality issues detected

**Hardware:**
- Device: Apple M4 Mac
- GPU: Metal API
- Model: Llama-3.2-3B-Instruct
- Output tokens: 128 per trial

## File Formats

### JSON Structure Details
- `gpu_tps`: Floating point, tokens per second for GPU
- `cpu_tps`: Floating point, tokens per second for CPU (currently invalid)
- `speedup`: Float, GPU TPS / CPU TPS ratio (N/A due to CPU corruption)
- `model_size_gb`: Float, quantized model size in gigabytes
- `variant`: String, quantization format (Q2_K, Q3_K_M, etc.)
- `context_length`: Integer, context window size in tokens

## Next Steps

1. **Immediate:** Review GPU performance recommendations for production use
2. **Short-term:** Re-collect CPU benchmark data for valid GPU/CPU comparison
3. **Medium-term:** Implement data validation in benchmark pipeline
4. **Long-term:** Expand to other devices (GPU variants, other CPUs) for comprehensive comparison

## Questions?

- For GPU-only analysis: See `COMPARISON_ANALYSIS.md`
- For raw metrics: Check `gpu_vs_cpu_comparison.json`
- For visualization: Use `visualization_data.json`
- For data validation: See `metadata.data_quality` fields

---
**Generated:** 2026-03-17
**Last Updated:** 2026-03-17
**Status:** GPU data ready for use; CPU data requires re-collection
