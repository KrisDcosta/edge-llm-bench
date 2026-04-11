#!/usr/bin/env python3
"""
plot_ppl_vs_accuracy.py — PPL vs Task Accuracy scatter figure
Shows the disconnect between WikiText-2 perplexity (monotonic with bpw)
and downstream task accuracy (non-monotonic).

Generates:
  figures/fig_ppl_vs_accuracy.png   — scatter: PPL on x-axis, BoolQ/MMLU/HellaSwag on y
  figures/fig_ppl_ordering.png      — PPL bar chart with BoolQ overlay

Usage:
  python3 scripts/analyze/plot_ppl_vs_accuracy.py
"""

import json, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

os.makedirs("figures", exist_ok=True)

# ── Data (from Pixel 6a full-corpus PPL + quality_scores.json) ──
with open("results/quality_scores.json") as f:
    qdata = json.load(f)

def get_pct(key):
    d = qdata.get(key)
    if d:
        return d.get("accuracy_pct", 0)
    return 0

VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
BPW      = [2.63,   3.44,     4.50,     5.09,      5.57,      6.56,   8.50]

# ARM full-corpus WikiText-2 PPL (pixel_6a_ppl_final/, 568 chunks)
PPL = {
    "Q2_K":   13.2885,
    "Q3_K_M": 11.0832,
    "Q4_K_S": 10.7005,
    "Q4_K_M": 10.7128,
    "Q5_K_M": 10.6243,
    "Q6_K":   10.5841,
    "Q8_0":   10.5894,
}

BOOLQ     = [get_pct(f"boolq:{v}")     for v in VARIANTS]
MMLU      = [get_pct(f"mmlu:{v}")      for v in VARIANTS]
HELLASWAG = [get_pct(f"hellaswag:{v}") for v in VARIANTS]
TRUTHFULQA= [get_pct(f"truthfulqa:{v}") for v in VARIANTS]
PPL_LIST  = [PPL[v] for v in VARIANTS]

# Variant colors (consistent with paper)
COLORS = {
    "Q2_K":   "#ef4444",
    "Q3_K_M": "#f97316",
    "Q4_K_S": "#eab308",
    "Q4_K_M": "#22c55e",
    "Q5_K_M": "#06b6d4",
    "Q6_K":   "#8b5cf6",
    "Q8_0":   "#ec4899",
}
color_list = [COLORS[v] for v in VARIANTS]

# ── Figure 1: PPL vs Task Accuracy Scatter ────────────────────
fig, axes = plt.subplots(1, 3, figsize=(14, 5))

bench_data = [
    (BOOLQ,      "BoolQ (%)",     "BoolQ"),
    (MMLU,       "MMLU (%)",      "MMLU"),
    (HELLASWAG,  "HellaSwag (%)","HellaSwag"),
]

for ax, (accs, ylabel, bench_name) in zip(axes, bench_data):
    for i, v in enumerate(VARIANTS):
        ax.scatter(PPL_LIST[i], accs[i], s=120, color=color_list[i],
                   zorder=5, edgecolors='white', linewidths=0.8)
        # Label each point
        offset_x = 0.04
        offset_y = 1.2
        if v == "Q2_K":
            offset_x = 0.12
            offset_y = -3.0
        ax.annotate(v, (PPL_LIST[i] + offset_x, accs[i] + offset_y),
                    fontsize=7.5, color=color_list[i], fontweight='bold')

    # Fit a linear trendline
    if len(PPL_LIST) > 2:
        z = np.polyfit(PPL_LIST, accs, 1)
        p = np.poly1d(z)
        xline = np.linspace(min(PPL_LIST)-0.2, max(PPL_LIST)+0.2, 100)
        ax.plot(xline, p(xline), '--', color='gray', linewidth=1.2, alpha=0.6,
                label=f"Linear fit (R²={np.corrcoef(PPL_LIST, accs)[0,1]**2:.2f})")

    ax.set_xlabel("WikiText-2 PPL (Pixel 6a, full corpus ↓ better)", fontsize=9)
    ax.set_ylabel(ylabel, fontsize=9)
    ax.set_title(f"PPL vs {bench_name}", fontsize=11, fontweight='bold')
    ax.grid(alpha=0.3, linestyle=':', linewidth=0.8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Annotate the paradox region
    if bench_name == "BoolQ":
        ax.annotate("Q6_K: lowest PPL,\nworst BoolQ",
                    xy=(PPL_LIST[VARIANTS.index("Q6_K")], BOOLQ[VARIANTS.index("Q6_K")]-1),
                    xytext=(11.5, 58),
                    fontsize=7.5, color=COLORS["Q6_K"],
                    arrowprops=dict(arrowstyle='->', color=COLORS["Q6_K"], lw=1))

    ax.legend(fontsize=8, loc='lower right')

fig.suptitle("WikiText-2 Perplexity Does Not Predict Task Accuracy\n"
             "Llama 3.2 3B Instruct · ARM (Pixel 6a) · n=100 per benchmark",
             fontsize=12, fontweight='bold', y=1.02)
fig.tight_layout()
out = "figures/fig_ppl_vs_accuracy.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Figure 2: PPL bar chart + BoolQ/MMLU overlay ─────────────
fig, ax1 = plt.subplots(figsize=(9, 5))

x      = np.arange(len(VARIANTS))
width  = 0.55

bars = ax1.bar(x, PPL_LIST, width, color=color_list, alpha=0.75, zorder=2,
               label="PPL (left axis)")
ax1.set_ylabel("WikiText-2 Perplexity ↓", fontsize=10, color='#374151')
ax1.set_ylim(0, 15.5)
ax1.set_xticks(x)
ax1.set_xticklabels(VARIANTS, fontsize=9, rotation=15, ha='right')
ax1.grid(axis='y', alpha=0.25, linestyle=':', zorder=0)
ax1.spines['top'].set_visible(False)

# Bar value labels
for bar, ppl in zip(bars, PPL_LIST):
    ax1.text(bar.get_x() + bar.get_width()/2, ppl + 0.15,
             f"{ppl:.2f}", ha='center', va='bottom', fontsize=7.5, color='#374151')

# Overlay: BoolQ and MMLU on right axis
ax2 = ax1.twinx()
ax2.plot(x, BOOLQ,      'D-', color='#2563EB', linewidth=2, markersize=7,
         label="BoolQ % (right)", zorder=6)
ax2.plot(x, MMLU,       's--', color='#16a34a', linewidth=2, markersize=7,
         label="MMLU % (right)", zorder=6)
ax2.plot(x, TRUTHFULQA, '^:', color='#9333ea', linewidth=1.5, markersize=6,
         label="TruthfulQA % (right)", zorder=6)
ax2.set_ylabel("Task Accuracy (%) →", fontsize=10, color='#1e40af')
ax2.set_ylim(0, 100)
ax2.spines['top'].set_visible(False)

# Highlight Q2_K gap: low PPL improvement → massive quality gap
ax1.axvspan(-0.5, 0.5, alpha=0.08, color='red', zorder=0)
ax1.text(0, 14.5, "Q2_K:\nhigh PPL\n& high TPS", ha='center', fontsize=7.5,
         color='#dc2626', style='italic')

# Combined legend
lines1, labels1 = ax1.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax1.legend(lines1 + lines2, labels1 + labels2,
           loc='upper right', fontsize=8.5, framealpha=0.92)

fig.suptitle("PPL is Monotonic with bpw; Task Accuracy is Not\n"
             "WikiText-2 PPL (bars) vs downstream task accuracy (lines)",
             fontsize=11, fontweight='bold')
fig.tight_layout()
out = "figures/fig_ppl_ordering.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Print summary table ───────────────────────────────────────
print("\nPPL vs Task Accuracy Summary:")
print(f"{'Variant':<10} {'bpw':>5} {'PPL':>7} {'BoolQ':>7} {'MMLU':>7} {'HellaS':>8} {'TruthQA':>9}")
print("-"*55)
for i, v in enumerate(VARIANTS):
    print(f"{v:<10} {BPW[i]:>5.2f} {PPL_LIST[i]:>7.4f} "
          f"{BOOLQ[i]:>7.1f} {MMLU[i]:>7.1f} {HELLASWAG[i]:>8.1f} {TRUTHFULQA[i]:>9.1f}")

print("\nKey observation:")
print(f"  PPL range Q5_K_M→Q8_0: {PPL[' Q5_K_M'] if ' Q5_K_M' in PPL else PPL['Q5_K_M']:.4f}–{PPL['Q8_0']:.4f} (Δ={abs(PPL['Q5_K_M']-PPL['Q8_0']):.4f} nats)")
print(f"  BoolQ range Q5_K_M→Q8_0: {BOOLQ[VARIANTS.index('Q5_K_M')]:.0f}–{BOOLQ[VARIANTS.index('Q8_0')]:.0f}%")
