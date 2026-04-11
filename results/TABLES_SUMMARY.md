# M4 Mac Benchmark Tables - Publication Ready

**Data Source:** M4 Mac Metal GPU benchmarks and CPU baseline tests
**Date:** 2026-03-17/18
**Model:** Llama-3.2-3B-Instruct
**Output Tokens:** 128

---

## Table 1: Performance Summary (Context Length 2048)

| Variant | Model Size (GB) | GPU Decode TPS | CPU Decode TPS | GPU/CPU Speedup |
|---------|-----------------|----------------|----------------|-----------------|
| Q2_K    | 3.2             | 30.42          | N/A            | N/A             |
| Q3_K_M  | 3.2             | 26.15          | N/A            | N/A             |
| Q4_K_S  | 3.2             | 27.01          | N/A            | N/A             |
| Q4_K_M  | 3.2             | 30.62          | N/A            | N/A             |
| Q5_K_M  | 3.2             | 20.25          | N/A            | N/A             |
| Q6_K    | 3.2             | 21.43          | N/A            | N/A             |
| Q8_0    | 3.2             | 17.51          | N/A            | N/A             |

**Key Findings:** Q4_K_M and Q2_K show the highest GPU decode throughput (~30.6 and 30.4 TPS respectively) at ctx=2048. Larger precision variants (Q6_K, Q8_0) show decreased performance as expected (21.4 and 17.5 TPS).

---

## Table 2: Context Length Impact (GPU)

| Variant | ctx=256 | ctx=512 | ctx=1024 | ctx=2048 |
|---------|---------|---------|----------|----------|
| Q2_K    | 33.68   | 29.87   | 34.93    | 30.42    |
| Q4_K_M  | 30.79   | 30.17   | 29.62    | 30.62    |
| Q6_K    | 21.77   | 22.32   | 22.56    | 21.43    |
| Q8_0    | 17.83   | 18.41   | 17.63    | 17.51    |

**Key Findings:** Context length has minimal impact on GPU decode TPS for these variants. Performance remains relatively stable across context windows (256→2048), with variations <5% for most variants. Q2_K shows the most variation (±4.5 TPS), while Q6_K and Q8_0 remain extremely stable.

---

## Table 3: Statistical Summary (GPU, Context Length 2048)

| Variant | Mean TPS | StdDev | Min  | Max  | 95% CI        | N Samples |
|---------|----------|--------|------|------|---------------|-----------|
| Q2_K    | 30.42    | 0.959  | 28.6 | 32.2 | [29.93, 30.91]| 15        |
| Q3_K_M  | 26.15    | 1.514  | 21.2 | 27.3 | [25.38, 26.91]| 15        |
| Q4_K_S  | 27.01    | 7.534  | 16.4 | 36.2 | [23.20, 30.83]| 15        |
| Q4_K_M  | 30.62    | 1.159  | 28.8 | 32.3 | [30.03, 31.21]| 15        |
| Q5_K_M  | 20.25    | 0.766  | 18.6 | 21.0 | [19.87, 20.64]| 15        |
| Q6_K    | 21.43    | 0.149  | 21.1 | 21.6 | [21.35, 21.50]| 15        |
| Q8_0    | 17.51    | 0.530  | 16.9 | 18.6 | [17.24, 17.78]| 15        |

**Key Findings:**
- **High Stability:** Q6_K and Q8_0 exhibit excellent reproducibility (StdDev < 0.75), indicating stable inference performance
- **Most Variable:** Q4_K_S shows the highest variability (StdDev = 7.534, 95% CI width = 7.63), suggesting higher variance in execution time
- **Consistent Performance:** Q2_K and Q4_K_M are the most performant variants with StdDev < 1.2, representing excellent choices for production deployment
- **Sample Size:** All results based on n=15 trials, providing robust statistical estimates

---

## Notes on Data Quality

- **CPU Benchmark Data:** CPU baseline values contained placeholder metrics and were excluded from speedup calculations. Future CPU benchmarks should be rerun to provide complete GPU/CPU comparison data.
- **GPU Data:** All GPU benchmarks contain 15 measurement trials per variant and context length combination
- **Precision:** Values shown to 2 decimal places for throughput (TPS), 3 decimal places for standard deviation
- **Statistical Methods:** 95% confidence intervals calculated using t-distribution approximation (SE * 1.96)

---

## Output Formats

Three output files have been generated:
1. **paper_tables_final.json** - Structured JSON with all table data and metadata
2. **paper_tables_final.csv** - CSV format with all three tables concatenated
3. **TABLES_SUMMARY.md** - This markdown document with formatted tables

All files are located in: `/Users/krisdcosta/291_EAI/results/`
