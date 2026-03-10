# BoolQ Re-run Monitoring & Automated Pareto Update

## Quick Start: Monitor BoolQ Progress Every 15 Minutes

Run this command in a terminal:

```bash
cd /Users/krisdcosta/291_EAI && bash scripts/boolq_pipeline.sh
```

This script will:
1. ✓ Display progress every 15 minutes
2. ✓ Show accuracy for each variant as it completes
3. ✓ Automatically update the Pareto plot when all variants finish
4. ✓ Display next steps for report update

---

## What Each Script Does

### `scripts/boolq_pipeline.sh` (RECOMMENDED)
The all-in-one monitoring + automation script.

**Features:**
- Monitors BoolQ progress every 15 minutes
- Shows real-time accuracy for each variant
- Auto-triggers Pareto plot update on completion
- Displays formatted progress UI
- Gives you the next steps for report update

**Run:**
```bash
bash scripts/boolq_pipeline.sh
```

**Output:** Clear progress display with variant accuracy %, completion status, and next check time.

---

### `scripts/monitor_boolq.sh`
Manual monitoring script (if you prefer basic output).

**Features:**
- Simpler progress display
- Shows accuracy per variant
- Auto-triggers Pareto update

**Run:**
```bash
bash scripts/monitor_boolq.sh
```

---

### `scripts/update_pareto_with_boolq.py`
Standalone Pareto plot update (can run manually anytime).

**Features:**
- Reads BoolQ results from quality_scores.json
- Extracts decode TPS from benchmark results
- Regenerates fig6 with new accuracy data
- Identifies Pareto frontier variants

**Run manually:**
```bash
python3 scripts/update_pareto_with_boolq.py
```

---

## Timeline Expectations

| Variant | Est. Time | Cumulative |
|---------|-----------|-----------|
| Q2_K    | ~45 min   | 0:45      |
| Q3_K_M  | ~45 min   | 1:30      |
| Q4_K_M  | ~45 min   | 2:15      |
| Q6_K    | ~20 min   | 2:35      |
| Q8_0    | ~20 min   | 2:55      |
| F16     | ~30 min+  | 3:25+     |

**Total: ~3.5 hours** (may vary by device thermal state)

---

## What Happens When It Completes

Once BoolQ finishes, the pipeline will:

1. ✓ Automatically update `figures/fig6_pareto_efficiency_quality_UPDATED.png`
2. ✓ Print the Pareto frontier variants (which are optimal)
3. ✓ Display next steps:

```
Next Steps:

1. Review the updated Pareto plot:
   open figures/fig6_pareto_efficiency_quality_UPDATED.png

2. Update the report (report/report.tex):
   • Section RQ4: Replace custom QA accuracy with BoolQ results
   • Update Table 1 with new accuracy %
   • Update Figure 6 caption with BoolQ reference

3. Recompile the PDF:
   cd report && pdflatex report.tex && cd ..

4. Verify the updated PDF:
   open report/report.pdf
```

---

## Monitoring Without Interactive Display

If you want to monitor in the background without a terminal (e.g., if you close your laptop):

```bash
# Run in background and log to file
nohup bash scripts/boolq_pipeline.sh > boolq_monitor.log 2>&1 &

# Check progress anytime:
tail -50 boolq_monitor.log
```

---

## File Locations

- **Results:** `results/quality_scores.json`
- **Updated plot:** `figures/fig6_pareto_efficiency_quality_UPDATED.png`
- **Report source:** `report/report.tex`
- **Compiled PDF:** `report/report.pdf`

---

## Troubleshooting

**If the script errors out:**

1. Check device is still connected:
   ```bash
   adb devices
   ```

2. Manually check BoolQ results:
   ```bash
   python3 -c "import json; f=open('results/quality_scores.json'); data=json.load(f); [print(r['variant'], r.get('accuracy_pct')) for r in data if r['tag']=='boolq']"
   ```

3. Manually update Pareto plot:
   ```bash
   python3 scripts/update_pareto_with_boolq.py
   ```

---

## Notes

- The monitoring script polls the results JSON file every 15 minutes
- No need to keep a terminal open if using `nohup` (but you'll need to check the log)
- The Pareto plot update runs automatically once all 6 variants complete
- The report update is still manual (you choose what text to change)
