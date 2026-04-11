# Quality Evaluation Benchmarks - Setup & Status

## Overview

Quality evaluation benchmarks have been initiated for Llama 3.2 3B GGUF quantization variants on M4 Mac. These benchmarks measure the accuracy degradation across different quantization levels.

## Configuration

### Datasets (6 total, 100 questions each)
- **arc_easy**: Multiple choice science questions (easy)
- **arc_challenge**: Multiple choice science questions (challenging)
- **boolq**: Yes/No factual questions
- **hellaswag**: Common sense inference (multiple choice)
- **mmlu**: Multiple choice knowledge across domains
- **truthfulqa**: Factual accuracy evaluation

### Quantization Variants (4 total)
| Variant | Size | Description |
|---------|------|-------------|
| Q2_K | 1.3 GB | Aggressive compression (2-bit K quants) |
| Q4_K_M | 1.9 GB | Balanced compression (4-bit medium) |
| Q6_K | 2.5 GB | Moderate compression (6-bit) |
| Q8_0 | 3.2 GB | Minimal compression (8-bit) |

### Total Workload
- **Total test questions**: 2,400 (6 datasets × 400 per variant set)
- **Total inferences**: 2,400 (each question evaluated once per variant)
- **Expected runtime**: 8-12 hours on M4 Mac (estimated)

## Files Modified/Created

### Script Fixes
1. **scripts/quality_eval_m4_local.py**
   - Fixed YAML parsing to handle multi-line prompts
   - Changed from regex-based line parsing to proper `yaml.safe_load()`
   - Now correctly handles dataset files in standardYAML format

### Benchmark Management Scripts
1. **start_benchmarks.py** - Main orchestrator that runs all datasets sequentially
2. **analyze_quality_results.py** - Analyzes results and generates summary statistics
3. **generate_final_report.py** - Produces final deployment recommendations report
4. **monitor_benchmarks.py** - Monitors progress and updates status

## Execution Status

### Completed
- Fixed YAML parsing in quality_eval_m4_local.py ✓
- Verified all dataset files exist ✓
- Verified all model files exist ✓
- Performed dry-run test (successful) ✓
- Started background benchmark execution ✓

### In Progress
- Running arc_easy benchmark...
- Collecting 100 inferences per variant for arc_easy

### Pending
- arc_challenge (100 q × 4 variants)
- boolq (100 q × 4 variants)
- hellaswag (100 q × 4 variants)
- mmlu (100 q × 4 variants)
- truthfulqa (100 q × 4 variants)

## Expected Results Output

When benchmarks complete, results will include:

### Per-Dataset Results
```json
{
  "arc_easy:Q2_K": {
    "variant": "Q2_K",
    "accuracy_pct": XX.X,
    "wilson_ci_95_pct": XX.X,
    "correct": XXX,
    "total": 100,
    "model_size_gb": 1.3
  },
  ...
}
```

### Analysis Output Files
1. **results/quality_metrics_m4.json** - Raw results (already created)
2. **results/quality_summary.json** - Structured analysis
3. **results/quality_eval_report.txt** - Human-readable report

## Key Metrics Calculated

For each variant and dataset combination:
- **Accuracy**: % of correct answers
- **Wilson CI (95%)**: Conservative confidence interval
- **Per-question details**: Which questions passed/failed
- **Category breakdown**: Accuracy by question category

## Deployment Recommendations (Framework)

The analysis will provide recommendations in 4 categories:

### 1. Quality Priority
- Recommended: Variant with highest accuracy
- Trade-off: Largest model size
- Use case: Production systems requiring maximum accuracy

### 2. Balanced (Quality vs Size)
- Recommended: Typically Q4_K_M or Q6_K
- Trade-off: Moderate accuracy with reasonable size
- Use case: Standard server deployments

### 3. Compact (Size Priority)
- Recommended: Q2_K
- Trade-off: Lowest accuracy
- Use case: Mobile/edge devices with limited storage

### 4. Efficiency Analysis
- Metric: Accuracy per GB (Accuracy/Model Size)
- Shows which variant offers best value

## Accuracy Degradation Expected

Based on typical quantization impact:

| Variant | Expected Accuracy Retention | Degradation vs Q8_0 |
|---------|------|-------------|
| Q8_0 | ~95-98% (baseline) | 0% |
| Q6_K | ~93-97% | 1-2pp |
| Q4_K_M | ~90-96% | 2-5pp |
| Q2_K | ~85-92% | 5-10pp |

(Actual values will be measured and reported)

## How to Monitor Progress

```bash
python3 /Users/krisdcosta/291_EAI/monitor_benchmarks.py
```

This will show updates every 30 seconds as results are recorded.

## How to Analyze Results

Once benchmarks complete:

```bash
# Generate summary analysis
python3 /Users/krisdcosta/291_EAI/analyze_quality_results.py

# Generate final report
python3 /Users/krisdcosta/291_EAI/generate_final_report.py
```

## Files to Monitor

- `/Users/krisdcosta/291_EAI/results/quality_metrics_m4.json` - Primary results
- Progress indicator: Number of entries in results JSON

## Next Steps

1. Benchmarks will run for ~8-12 hours
2. Once complete, analysis scripts will generate comprehensive reports
3. Reports will include deployment recommendations based on actual measurements
4. Results will be committed to git for tracking

## Technical Details

### Test Methodology
- Fixed random seed (42) for reproducibility
- Temperature 0.0 (deterministic sampling)
- Context window: 2048 tokens
- Generation length: 8 tokens (choice/yesno), 32 tokens (other)
- Single-threaded inference (4 CPU threads per llama-cli)

### Scoring
- **Choice type**: Recognizes A/B/C/D letter responses
- **Yes/No type**: Recognizes yes/no responses
- **Substring type**: Case-insensitive substring matching
- **Wilson CI**: Conservative confidence interval for small sample sizes

### Model
- Base: Llama 3.2 3B Instruct
- Quantized with llama.cpp
- iMatrix optimization applied for K-quants
- All variants use same underlying model weights
