#!/usr/bin/env python3
"""
gen_cross_platform_rank.py
Bump/rank chart: decode throughput (tok/s) of 7 GGUF quantization variants
across 4 platforms. Key finding: Metal reverses the CPU rank ordering.

Output: figures/cross_platform_rank.{pdf,png}
"""

import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Style
# ---------------------------------------------------------------------------
plt.rcParams.update({
    'font.size': 9,
    'font.family': 'sans-serif',
    'axes.grid': True,
    'grid.alpha': 0.3,
})

# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
platforms = ['ARM\n(Pixel 6a)', 'x86\n(i5-1235U)', 'M4\nCPU', 'M4\nMetal']
x = np.arange(len(platforms))

data = {
    'Q2_K':   [7.49,  14.05, 12.31, 17.79],
    'Q3_K_M': [4.68,   8.38, 11.48, 15.60],
    'Q4_K_S': [5.01,   8.93, 13.16, 19.88],
    'Q4_K_M': [4.78,   8.55, 12.51, 19.22],
    'Q5_K_M': [3.75,   7.31, 10.59, 13.35],
    'Q6_K':   [3.53,   6.80,  9.29,  7.02],
    'Q8_0':   [4.52,   7.43, 12.60,  6.39],
}

COLORS = {
    'Q2_K':   '#d73027',
    'Q3_K_M': '#f46d43',
    'Q4_K_S': '#fdae61',
    'Q4_K_M': '#4575b4',
    'Q5_K_M': '#74add1',
    'Q6_K':   '#313695',
    'Q8_0':   '#1a9641',
}

MARKERS = {
    'Q2_K':   'o',
    'Q3_K_M': 's',
    'Q4_K_S': '^',
    'Q4_K_M': 'D',
    'Q5_K_M': 'v',
    'Q6_K':   'P',
    'Q8_0':   'X',
}

# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(6.5, 3.5))

for variant, values in data.items():
    ax.plot(
        x, values,
        color=COLORS[variant],
        marker=MARKERS[variant],
        linewidth=1.8,
        markersize=7,
        label=variant,
        zorder=3,
    )

# ---------------------------------------------------------------------------
# Axes
# ---------------------------------------------------------------------------
ax.set_xticks(x)
ax.set_xticklabels(platforms, fontsize=9)
ax.set_ylabel('Decode throughput (tok/s)')
ax.set_xlim(-0.5, 3.75)
ax.set_ylim(0, 22)

# ---------------------------------------------------------------------------
# Vertical dashed separator: CPU → GPU transition
# ---------------------------------------------------------------------------
sep_x = 2.5
ax.axvline(x=sep_x, color='#888888', linestyle='--', linewidth=1.2, zorder=2)
# Label at top of the separator line
ax.text(sep_x + 0.03, 21.5, 'CPU → GPU',
        fontsize=7.5, color='#555555', va='top', ha='left', style='italic')

# ---------------------------------------------------------------------------
# Annotation: "Metal reverses CPU ordering" with arrow into crossing region
# ---------------------------------------------------------------------------
ax.annotate(
    'Metal reverses\nCPU ordering',
    xy=(2.75, 12.5),          # arrow tip — near the crossing tangle
    xytext=(2.0, 18.2),       # text box centre
    fontsize=7.5,
    color='#333333',
    ha='center',
    arrowprops=dict(
        arrowstyle='->',
        color='#666666',
        lw=1.0,
        connectionstyle='arc3,rad=-0.2',
    ),
    bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='#cccccc', alpha=0.85),
    zorder=5,
)

# ---------------------------------------------------------------------------
# Point annotations
# ---------------------------------------------------------------------------
# Q4_K_S peak on Metal: 19.9 tok/s
ax.annotate(
    '19.9 tok/s',
    xy=(3, 19.88),
    xytext=(3.08, 18.3),
    fontsize=7,
    color=COLORS['Q4_K_S'],
    ha='left',
    arrowprops=dict(arrowstyle='->', color=COLORS['Q4_K_S'], lw=0.8),
)

# Q2_K on ARM: 7.49 tok/s (fastest CPU)
ax.annotate(
    '7.49 tok/s\n(fastest CPU)',
    xy=(0, 7.49),
    xytext=(-0.38, 10.5),
    fontsize=7,
    color=COLORS['Q2_K'],
    ha='center',
    arrowprops=dict(arrowstyle='->', color=COLORS['Q2_K'], lw=0.8),
)

# Q6_K on Metal: drops dramatically from M4 CPU
ax.annotate(
    '7.02\n(Q6_K)',
    xy=(3, 7.02),
    xytext=(3.08, 8.8),
    fontsize=6.5,
    color=COLORS['Q6_K'],
    ha='left',
    arrowprops=dict(arrowstyle='->', color=COLORS['Q6_K'], lw=0.8),
)

# Q8_0 on Metal: lowest point
ax.annotate(
    '6.39\n(Q8_0)',
    xy=(3, 6.39),
    xytext=(2.52, 4.2),
    fontsize=6.5,
    color=COLORS['Q8_0'],
    ha='center',
    arrowprops=dict(arrowstyle='->', color=COLORS['Q8_0'], lw=0.8),
)

# ---------------------------------------------------------------------------
# Legend
# ---------------------------------------------------------------------------
ax.legend(
    loc='upper left',
    fontsize=7.5,
    ncol=2,
    framealpha=0.85,
    edgecolor='#cccccc',
    columnspacing=0.8,
    handlelength=1.5,
)

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
plt.tight_layout()

out_dir = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'figures')
)
plt.savefig(os.path.join(out_dir, 'cross_platform_rank.pdf'), bbox_inches='tight', dpi=300)
plt.savefig(os.path.join(out_dir, 'cross_platform_rank.png'), bbox_inches='tight', dpi=300)
print(f'Saved: {out_dir}/cross_platform_rank.pdf')
print(f'Saved: {out_dir}/cross_platform_rank.png')
