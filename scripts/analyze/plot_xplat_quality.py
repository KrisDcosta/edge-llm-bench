#!/usr/bin/env python3
"""
plot_xplat_quality.py — Cross-platform quality comparison figure
ARM (Pixel 6a) vs x86 (Intel i5-1235U), all 7 K-quant variants.

Generates two figures:
  figures/fig_xplat_hellaswag.png  — HellaSwag side-by-side bar chart
  figures/fig_xplat_mmlu.png       — MMLU side-by-side bar chart
  figures/fig_xplat_quality_4bench.png — 2×2 grid: HellaSwag, MMLU, BoolQ, TruthfulQA

Usage:
  python3 scripts/analyze/plot_xplat_quality.py
"""

import json, math, os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Load data ────────────────────────────────────────────────
with open("results/quality_scores.json") as f:
    data = json.load(f)

VARIANTS   = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
V_LABELS   = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
BENCHMARKS = {
    "hellaswag":   ("HellaSwag",  "ARM key:hellaswag:{v}",   "x86 key:x86_hellaswag:{v}"),
    "mmlu":        ("MMLU",       "ARM key:mmlu:{v}",        "x86 key:x86_mmlu:{v}"),
    "boolq":       ("BoolQ",      "ARM key:boolq:{v}",       "x86 key:x86_boolq:{v}"),
    "truthfulqa":  ("TruthfulQA", "ARM key:truthfulqa:{v}",  "x86 key:x86_truthfulqa:{v}"),
}

def get_acc(key):
    d = data.get(key)
    if d is None:
        return None, None
    acc = d.get("accuracy_pct")
    n   = d.get("total", 100)
    if acc is None:
        return None, None
    acc = acc / 100.0
    z   = 1.96
    lo  = (acc + z**2/(2*n) - z*math.sqrt(acc*(1-acc)/n + z**2/(4*n**2))) / (1 + z**2/n)
    hi  = (acc + z**2/(2*n) + z*math.sqrt(acc*(1-acc)/n + z**2/(4*n**2))) / (1 + z**2/n)
    return acc * 100, (hi - lo) * 100 / 2   # return pct, half-CI

def get_bench_data(bench):
    arm_acc, arm_ci, x86_acc, x86_ci = [], [], [], []
    for v in VARIANTS:
        a_key  = f"{bench}:{v}"
        # arc_easy uses arc_easy_fixed key on ARM
        if bench == "arc_easy":
            a_key = f"arc_easy_fixed:{v}"
        x_key  = f"x86_{bench}:{v}"
        a, ac  = get_acc(a_key)
        x, xc  = get_acc(x_key)
        arm_acc.append(a or 0); arm_ci.append(ac or 0)
        x86_acc.append(x or 0); x86_ci.append(xc or 0)
    return arm_acc, arm_ci, x86_acc, x86_ci

# ── Color palette ─────────────────────────────────────────────
ARM_COLOR = "#2563EB"   # blue
X86_COLOR = "#DC2626"   # red
RANDOM_4CH = 25.0       # 4-choice random baseline (HellaSwag)
RANDOM_MMLU = 25.0      # 4-choice MMLU

os.makedirs("figures", exist_ok=True)

# ── Helper: grouped bar chart ─────────────────────────────────
def plot_bench_bars(ax, bench, title, random_line=None, highlight_q2k=True):
    arm_acc, arm_ci, x86_acc, x86_ci = get_bench_data(bench)

    x     = np.arange(len(VARIANTS))
    width = 0.35

    bars_arm = ax.bar(x - width/2, arm_acc, width,
                      label="ARM (Pixel 6a)",
                      color=ARM_COLOR, alpha=0.85,
                      yerr=arm_ci, capsize=3, error_kw=dict(elinewidth=1, ecolor='#1e3a6e'))
    bars_x86 = ax.bar(x + width/2, x86_acc, width,
                      label="x86 (i5-1235U)",
                      color=X86_COLOR, alpha=0.85,
                      yerr=x86_ci, capsize=3, error_kw=dict(elinewidth=1, ecolor='#7f1d1d'))

    # Random baseline
    if random_line is not None:
        ax.axhline(random_line, color='gray', linestyle='--', linewidth=1.2,
                   label=f"Random ({int(random_line)}%)")

    # Annotate Q2_K collapse if highlight_q2k
    if highlight_q2k and arm_acc[0] > 0 and arm_acc[0] < 28:
        ax.annotate("↓ collapse\n(near random)", xy=(x[0] - width/2, arm_acc[0]+0.5),
                    xytext=(x[0]+0.6, arm_acc[0]+12),
                    fontsize=7, color=ARM_COLOR, ha='center',
                    arrowprops=dict(arrowstyle='->', color=ARM_COLOR, lw=1))

    ax.set_xticks(x)
    ax.set_xticklabels(V_LABELS, fontsize=9, rotation=15, ha='right')
    ax.set_ylabel("Accuracy (%)", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight='bold', pad=6)
    ax.set_ylim(0, 100)
    ax.yaxis.set_major_locator(plt.MultipleLocator(20))
    ax.yaxis.set_minor_locator(plt.MultipleLocator(10))
    ax.grid(axis='y', alpha=0.3, linestyle=':', linewidth=0.8)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Value labels on bars
    for bar in bars_arm:
        h = bar.get_height()
        if h > 3:
            ax.text(bar.get_x() + bar.get_width()/2, h + 1.5,
                    f"{h:.0f}", ha='center', va='bottom', fontsize=6.5, color=ARM_COLOR)
    for bar in bars_x86:
        h = bar.get_height()
        if h > 3:
            ax.text(bar.get_x() + bar.get_width()/2, h + 1.5,
                    f"{h:.0f}", ha='center', va='bottom', fontsize=6.5, color=X86_COLOR)

    return ax

# ── Figure 1: HellaSwag standalone ──────────────────────────
fig, ax = plt.subplots(figsize=(8, 4.5))
plot_bench_bars(ax, "hellaswag", "HellaSwag Accuracy: ARM vs x86",
                random_line=25.0, highlight_q2k=True)
ax.legend(fontsize=9, loc='upper right', framealpha=0.9)
fig.tight_layout()
out = "figures/fig_xplat_hellaswag.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Figure 2: MMLU standalone ────────────────────────────────
fig, ax = plt.subplots(figsize=(8, 4.5))
plot_bench_bars(ax, "mmlu", "MMLU Accuracy: ARM vs x86",
                random_line=25.0, highlight_q2k=False)
ax.legend(fontsize=9, loc='upper right', framealpha=0.9)
fig.tight_layout()
out = "figures/fig_xplat_mmlu.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Figure 3: 2×2 grid (all 4 key benchmarks) ───────────────
fig, axes = plt.subplots(2, 2, figsize=(13, 9))
configs = [
    ("hellaswag",  "HellaSwag",    25.0,  True),
    ("mmlu",       "MMLU",         25.0,  False),
    ("boolq",      "BoolQ",        None,  False),
    ("truthfulqa", "TruthfulQA",   None,  False),
]

for ax, (bench, title, rline, hi_q2k) in zip(axes.flat, configs):
    plot_bench_bars(ax, bench, title, random_line=rline, highlight_q2k=hi_q2k)

# Shared legend in the BoolQ/TruthfulQA region
arm_patch  = mpatches.Patch(color=ARM_COLOR, alpha=0.85, label="ARM (Pixel 6a)")
x86_patch  = mpatches.Patch(color=X86_COLOR, alpha=0.85, label="x86 (Intel i5-1235U)")
rand_line  = plt.Line2D([0], [0], color='gray', linestyle='--', linewidth=1.2, label="4-choice random (25%)")
fig.legend(handles=[arm_patch, x86_patch, rand_line],
           loc='lower center', ncol=3, fontsize=10,
           bbox_to_anchor=(0.5, -0.02), framealpha=0.95)

fig.suptitle("Cross-Platform Quality: ARM (Pixel 6a) vs x86 (Intel i5-1235U)\n"
             "Llama 3.2 3B Instruct · n=100 per cell · 95% Wilson CI shown as error bars",
             fontsize=12, fontweight='bold', y=1.01)

fig.tight_layout(rect=[0, 0.04, 1, 1])
out = "figures/fig_xplat_quality_4bench.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

print("\nAll cross-platform quality figures saved to figures/")
