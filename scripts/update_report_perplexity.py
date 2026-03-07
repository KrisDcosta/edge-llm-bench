#!/usr/bin/env python3
"""
update_report_perplexity.py — Inject WikiText-2 perplexity scores into report.tex.

Reads results/perplexity_scores.json and updates:
  1. Table 1: adds PPL column
  2. RQ4 section: add perplexity paragraph
  3. Regenerates figures with full data

Usage:
  python3 scripts/update_report_perplexity.py
"""
import json, re, subprocess, sys
from pathlib import Path

PROJECT = Path(__file__).parent.parent
PPL_FILE = PROJECT / "results" / "perplexity_scores.json"
REPORT   = PROJECT / "report" / "report.tex"

if not PPL_FILE.exists():
    print("ERROR: perplexity_scores.json not found")
    sys.exit(1)

ppl_data = json.loads(PPL_FILE.read_text())

# Verify we have the key variants
VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0"]
missing = [v for v in VARIANTS if ppl_data.get(v, {}).get("perplexity") is None]
if missing:
    print(f"WARNING: missing PPL for: {missing}")
    print("Proceeding with available data...")

print("\n=== Perplexity values ===")
for v in VARIANTS:
    ppl = ppl_data.get(v, {}).get("perplexity")
    status = ppl_data.get(v, {}).get("perplexity_status", "unknown")
    print(f"  {v}: PPL={ppl} [{status}]")

def ppl_str(variant):
    ppl = ppl_data.get(variant, {}).get("perplexity")
    return f"{ppl:.1f}" if ppl is not None else "---"

# ── Table 1 update ──────────────────────────────────────────────────────────
# Add PPL column to the existing 9-column table
tex = REPORT.read_text()

# Update column header
old_header = (r"\textbf{Variant} & \textbf{Size (GB)} & \textbf{Decode TPS} & \textbf{TPS Std} &\n"
              r"\textbf{Prefill TPS} & \textbf{TTFT (s)} & \textbf{E2E (s)} & \textbf{Acc. (\%)} & \textbf{95\% CI} \\")
new_header = (r"\textbf{Variant} & \textbf{Size (GB)} & \textbf{Decode TPS} & \textbf{TPS Std} &" + "\n" +
              r"\textbf{Prefill TPS} & \textbf{TTFT (s)} & \textbf{E2E (s)} & \textbf{Acc. (\%)} & \textbf{95\% CI} & \textbf{PPL$\downarrow$} \\")
tex = tex.replace(old_header, new_header, 1)

# Fallback regex approach for the header
if "\\textbf{PPL" not in tex:
    tex = tex.replace(
        r"\textbf{Acc. (\%)} & \textbf{95\% CI} \\",
        r"\textbf{Acc. (\%)} & \textbf{95\% CI} & \textbf{PPL$\downarrow$} \\",
        1
    )

# Update data rows — insert PPL before \\
ROW_UPDATES = {
    "Q2\\_K":    f"& {ppl_str('Q2_K')} \\\\",
    "Q3\\_K\\_M": f"& {ppl_str('Q3_K_M')} \\\\",
    "Q4\\_K\\_M": f"& {ppl_str('Q4_K_M')} \\\\",
    "Q6\\_K":    f"& {ppl_str('Q6_K')} \\\\",
    "Q8\\_0":    f"& {ppl_str('Q8_0')} \\\\",
}

# Match each data row and add PPL
for variant_tex, ppl_suffix in ROW_UPDATES.items():
    # Pattern: the row ends with [80-100] or [62-96] etc. followed by \\
    pattern = rf"({re.escape(variant_tex)}.*?\[[\d\-]+\]) \\\\"
    replacement = rf"\1 {ppl_suffix}"
    new_tex, count = re.subn(pattern, replacement, tex, count=1, flags=re.DOTALL)
    if count:
        tex = new_tex
        print(f"  Updated row for {variant_tex}")
    else:
        print(f"  WARNING: could not update row for {variant_tex}")

# Update tabular column spec from 9 to 10 columns
tex = tex.replace("{lrrrrrrrl}", "{lrrrrrrrrl}", 1)

# Update footnote
tex = tex.replace(
    r"\multicolumn{9}{l}{\small Accuracy: exact-match over 15 factual questions; 95\% CI via Wilson score interval ($n{=}15$).}\\",
    r"\multicolumn{10}{l}{\small Accuracy: exact-match over 15 factual questions; 95\% CI via Wilson score interval ($n{=}15$).}\\" + "\n" +
    r"        \multicolumn{10}{l}{\small PPL: WikiText-2 perplexity (lower = better) measured via \texttt{llama-perplexity} on device.}\\",
    1
)
tex = tex.replace(
    r"\multicolumn{9}{l}{\small F16: 1 trial only (2/3 timed out at 600\,s). Q8\_0 achieves best TTFT at 3.95\,s.}\\",
    r"\multicolumn{10}{l}{\small F16: 1 trial only (2/3 timed out at 600\,s). Q8\_0 achieves best TTFT at 3.95\,s.}\\",
    1
)

REPORT.write_text(tex)
print("\nTable 1 updated with PPL column.")

# ── Rebuild PDF ──────────────────────────────────────────────────────────────
print("\nRecompiling PDF...")
result = subprocess.run(
    ["pdflatex", "-interaction=nonstopmode", "report.tex"],
    cwd=PROJECT / "report", capture_output=True, text=True
)
if result.returncode == 0:
    subprocess.run(["pdflatex", "-interaction=nonstopmode", "report.tex"],
                   cwd=PROJECT / "report", capture_output=True, text=True)
    print("PDF compiled successfully.")
else:
    print("WARNING: pdflatex returned non-zero")
    print(result.stdout[-2000:])
