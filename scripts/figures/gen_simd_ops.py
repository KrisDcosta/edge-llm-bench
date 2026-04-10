#!/usr/bin/env python3
"""
Generate Figure G2: SIMD Dequantization Ops per 256-weight superblock.
Data: static analysis of llama.cpp arm/quants.c + x86/quants.c (commit 1a29907).
Output: figures/simd_ops_comparison.pdf
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

# ── Data (static analysis, llama.cpp commit 1a29907) ──────────────────────────
variants = ['Q2_K', 'Q3_K_M', 'Q4_K_S\n/Q4_K_M', 'Q5_K_M', 'Q6_K', 'Q8_0']
ops      = [10,     18,        12,                  16,        26,     8]
colors   = ['#1a9641', '#f46d43', '#4575b4', '#74add1', '#d73027', '#aaaaaa']

# x-positions (Q4_K_S and Q4_K_M share a bar — same kernel)
x = np.arange(len(variants))

# ── Plot ──────────────────────────────────────────────────────────────────────
plt.rcParams.update({
    'font.size': 10,
    'font.family': 'sans-serif',
    'axes.titlesize': 10,
    'axes.labelsize': 10,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
})

fig, ax = plt.subplots(figsize=(5.5, 3.2))

bars = ax.bar(x, ops, color=colors, edgecolor='black', linewidth=0.6, width=0.6)

# Value labels on bars
for bar, op in zip(bars, ops):
    ax.text(bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.4,
            str(op),
            ha='center', va='bottom', fontsize=9, fontweight='bold')

# Annotation: Q6_K — slowest TPS despite mid-range model size
ax.annotate(
    'slowest TPS\n(26 ops/block)',
    xy=(4, 26), xytext=(3.25, 23.5),
    arrowprops=dict(arrowstyle='->', color='#d73027', lw=1.2),
    fontsize=8, color='#d73027', ha='center'
)

# Annotation: Q8_0 — DRAM-bound
ax.annotate(
    'DRAM-bound\n(not dispatch-bound)',
    xy=(5, 8), xytext=(4.5, 19),
    arrowprops=dict(arrowstyle='->', color='#555555', lw=1.0),
    fontsize=8, color='#555555', ha='center'
)

ax.set_xticks(x)
ax.set_xticklabels(variants)
ax.set_ylabel('NEON ops per 256-weight superblock')
ax.set_xlabel('Quantization variant')
ax.set_ylim(0, 31)
ax.yaxis.grid(True, linestyle='--', alpha=0.4)
ax.set_axisbelow(True)

# Legend patch for data provenance
patch = mpatches.Patch(color='none',
    label='Static analysis: arm/quants.c (commit 1a29907)')
ax.legend(handles=[patch], fontsize=7.5, loc='upper left',
          framealpha=0.7, edgecolor='#cccccc')

plt.tight_layout()

import os
os.makedirs('figures', exist_ok=True)
plt.savefig('figures/simd_ops_comparison.pdf', bbox_inches='tight', dpi=300)
plt.savefig('figures/simd_ops_comparison.png', bbox_inches='tight', dpi=300)
print("Saved: figures/simd_ops_comparison.pdf + .png")
