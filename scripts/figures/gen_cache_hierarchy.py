"""
gen_cache_hierarchy.py
Generate a two-panel cache hierarchy diagram illustrating the KV-cache cliff
phenomenon on ARM (Pixel 6a) vs x86 (i5-1235U).

Output:
  figures/cache_hierarchy_diagram.pdf
  figures/cache_hierarchy_diagram.png
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch

# ── Style ────────────────────────────────────────────────────────────────────
plt.rcParams.update({"font.size": 9, "font.family": "sans-serif"})

COLORS = {
    "L1":   "#4575b4",  # blue
    "L2":   "#d73027",  # red  — the cliff level
    "L3":   "#74add1",  # light blue
    "DRAM": "#aaaaaa",  # gray
}

FIG_W, FIG_H = 6.5, 3.2   # inches — two-column spanning


# ── Helper ───────────────────────────────────────────────────────────────────
def draw_cache_stack(ax, levels, arrow_target_idx, arrow_label,
                     cliff_text, panel_title):
    """
    Draw a vertical stack of cache boxes (bottom = DRAM, top = L1).

    Parameters
    ----------
    ax              : matplotlib Axes
    levels          : list of (label, color) from top (L1) to bottom (DRAM)
    arrow_target_idx: index into levels that the arrow points to
    arrow_label     : multiline string for the arrow annotation
    cliff_text      : string shown below the stack in red
    panel_title     : axes title
    """
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.4, len(levels) + 0.6)
    ax.axis("off")
    ax.set_title(panel_title, fontsize=10, fontweight="bold", pad=6)

    # Box geometry — boxes grow wider toward DRAM
    n = len(levels)
    min_w = 3.6   # L1 width
    max_w = 7.0   # DRAM width
    box_h = 0.62
    cx = 5.0       # horizontal centre

    box_coords = []   # (x_left, y_bottom, width) for each level
    for i, (label, color) in enumerate(levels):
        # i=0 → top (L1), i=n-1 → bottom (DRAM)
        w = min_w + (max_w - min_w) * i / max(n - 1, 1)
        x = cx - w / 2
        # y: stack from top; level 0 is highest row
        y_row = n - 1 - i          # row index from bottom
        y = y_row * (box_h + 0.18)
        box_coords.append((x, y, w))

        patch = FancyBboxPatch(
            (x, y), w, box_h,
            boxstyle="round,pad=0.04",
            linewidth=1.2,
            edgecolor="white",
            facecolor=color,
            zorder=3,
        )
        ax.add_patch(patch)

        # Label inside box
        ax.text(cx, y + box_h / 2, label,
                ha="center", va="center",
                fontsize=8.5, color="white", fontweight="bold", zorder=4)

    # Arrow: from right edge of the target box, curving to annotation text
    tgt_i = arrow_target_idx
    tx, ty, tw = box_coords[tgt_i]
    arrow_x = tx + tw + 0.15           # start x (right side of target box)
    arrow_y = ty + box_h / 2           # start y (mid-height)

    # Text placed to the right of the stack
    txt_x = cx + max_w / 2 + 2.3
    txt_y = arrow_y

    ax.annotate(
        arrow_label,
        xy=(arrow_x, arrow_y),
        xytext=(txt_x, txt_y),
        fontsize=6.8,
        color="#222222",
        ha="left", va="center",
        arrowprops=dict(
            arrowstyle="-|>",
            color="#555555",
            lw=1.1,
            connectionstyle="arc3,rad=0.0",
        ),
        zorder=5,
    )

    # Cliff threshold text below the stack
    ax.text(cx, -1.1, cliff_text,
            ha="center", va="center",
            fontsize=7.8, color="#cc0000",
            fontstyle="italic",
            wrap=True)


# ── Figure layout ────────────────────────────────────────────────────────────
fig, axes = plt.subplots(1, 2, figsize=(FIG_W, FIG_H))

# ── Left panel: ARM Cortex-X1 (Pixel 6a) ─────────────────────────────────────
arm_levels = [
    ("L1  48 KB",          COLORS["L1"]),
    ("L2  512 KB",         COLORS["L2"]),
    ("DRAM  6 GB LPDDR5",  COLORS["DRAM"]),
]

arm_arrow_label = (
    "KV working set\n"
    "ctx=512:  512×4096 = 2 MB total\n"
    "÷4 threads = 512 KB ≈ L2"
)

arm_cliff = "cliff threshold:  ctx = 512 KB / 1024 = 512 tokens"

draw_cache_stack(
    axes[0],
    arm_levels,
    arrow_target_idx=1,      # L2
    arrow_label=arm_arrow_label,
    cliff_text=arm_cliff,
    panel_title="ARM Cortex-X1 (Pixel 6a)",
)

# ── Right panel: Intel i5-1235U (x86) ────────────────────────────────────────
x86_levels = [
    ("L1  48 KB",          COLORS["L1"]),
    ("L2  1.25 MB",        COLORS["L2"]),
    ("L3  12 MB",          COLORS["L3"]),
    ("DRAM  16 GB DDR4",   COLORS["DRAM"]),
]

x86_arrow_label = (
    "KV working set\n"
    "ctx=1280:  1280×4096 = 5 MB total\n"
    "÷4 threads = 1.25 MB ≈ L2"
)

x86_cliff = "cliff threshold:  ctx = 1.25 MB / 1024 = 1280 tokens"

draw_cache_stack(
    axes[1],
    x86_levels,
    arrow_target_idx=1,      # L2
    arrow_label=x86_arrow_label,
    cliff_text=x86_cliff,
    panel_title="Intel i5-1235U (x86)",
)

# ── Legend ───────────────────────────────────────────────────────────────────
legend_handles = [
    mpatches.Patch(color=COLORS["L1"],   label="L1 cache"),
    mpatches.Patch(color=COLORS["L2"],   label="L2 cache (cliff level)"),
    mpatches.Patch(color=COLORS["L3"],   label="L3 cache"),
    mpatches.Patch(color=COLORS["DRAM"], label="DRAM"),
]
fig.legend(
    handles=legend_handles,
    loc="lower center",
    ncol=4,
    fontsize=7.5,
    frameon=False,
    bbox_to_anchor=(0.5, -0.01),
)

# ── Save ─────────────────────────────────────────────────────────────────────
plt.tight_layout(rect=[0, 0.06, 1, 1])   # leave room for legend

out_dir = os.path.join(os.path.dirname(__file__), "..", "..", "figures")
out_dir = os.path.normpath(out_dir)
os.makedirs(out_dir, exist_ok=True)

pdf_path = os.path.join(out_dir, "cache_hierarchy_diagram.pdf")
png_path = os.path.join(out_dir, "cache_hierarchy_diagram.png")

plt.savefig(pdf_path, bbox_inches="tight", dpi=300)
plt.savefig(png_path, bbox_inches="tight", dpi=300)

print(f"Saved: {pdf_path}")
print(f"Saved: {png_path}")
