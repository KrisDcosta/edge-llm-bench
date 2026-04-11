#!/usr/bin/env python3
"""
gen_deployment_flowchart.py
Generate Figure: Deployment decision flowchart for GGUF quantization variant selection.
Output: figures/deployment_flowchart.pdf + .png

Style spec:
  - Decision diamonds: border #4575b4, fill #deebf7
  - Terminal (recommendation) boxes: border #1a9641, fill #e5f5e0
  - AVOID box: border #d73027, fill #fee0d2
  - Font: sans-serif, 8 pt decisions, 7 pt annotations
  - Figure: ~4 in wide x 7 in tall (single-column)
"""
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Polygon

plt.rcParams.update({'font.size': 8, 'font.family': 'sans-serif'})

# ── Colours ───────────────────────────────────────────────────────────────────
C_DEC_E = '#4575b4'
C_DEC_F = '#deebf7'
C_REC_E = '#1a9641'
C_REC_F = '#e5f5e0'
C_AVD_E = '#d73027'
C_AVD_F = '#fee0d2'
C_STA_E = '#555555'
C_STA_F = '#f0f0f0'
C_ARR   = '#333333'

# ── Canvas ────────────────────────────────────────────────────────────────────
fig, ax = plt.subplots(figsize=(4.0, 7.2))
ax.set_xlim(0, 10)
ax.set_ylim(0, 18)
ax.axis('off')

CX   = 4.8    # centre-x for main (left) column
RX   = 8.6    # centre-x for right terminal boxes

# ── Drawing helpers ───────────────────────────────────────────────────────────

def draw_rect(cx, cy, w, h, label, fc, ec, fs=8, bold=False, note=None):
    """Rounded rectangle centred at (cx, cy)."""
    patch = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle='round,pad=0.12',
        facecolor=fc, edgecolor=ec, linewidth=1.2, zorder=3,
    )
    ax.add_patch(patch)
    label_y = cy + (0.15 if note else 0)
    ax.text(cx, label_y, label, ha='center', va='center',
            fontsize=fs, fontweight='bold' if bold else 'normal',
            multialignment='center', zorder=4)
    if note:
        ax.text(cx, cy - 0.22, note, ha='center', va='center',
                fontsize=6.5, style='italic', color='#444444', zorder=4)


def draw_diamond(cx, cy, w, h, label, fs=8):
    """Diamond for decisions."""
    hw, hh = w / 2, h / 2
    xs = [cx,      cx + hw, cx,       cx - hw, cx]
    ys = [cy + hh, cy,      cy - hh,  cy,      cy + hh]
    poly = Polygon(list(zip(xs, ys)), closed=True,
                   facecolor=C_DEC_F, edgecolor=C_DEC_E,
                   linewidth=1.2, zorder=3)
    ax.add_patch(poly)
    ax.text(cx, cy, label, ha='center', va='center',
            fontsize=fs, multialignment='center', zorder=4)


def vert_arrow(x, y1, y2, label='', label_dx=-0.35):
    """Vertical arrow from (x,y1) to (x,y2) with optional YES/NO label."""
    ax.annotate('', xy=(x, y2), xytext=(x, y1),
                arrowprops=dict(arrowstyle='->', color=C_ARR, lw=1.0), zorder=2)
    if label:
        my = (y1 + y2) / 2
        ax.text(x + label_dx, my, label, fontsize=6.8,
                color='#222222', ha='center', va='center',
                bbox=dict(boxstyle='round,pad=0.04', fc='white', ec='none', alpha=0.85))


def horiz_arrow(x1, y, x2, label='', label_dy=0.22):
    """Horizontal arrow from (x1,y) to (x2,y) with label above mid-point."""
    ax.annotate('', xy=(x2, y), xytext=(x1, y),
                arrowprops=dict(arrowstyle='->', color=C_ARR, lw=1.0), zorder=2)
    if label:
        mx = (x1 + x2) / 2
        ax.text(mx, y + label_dy, label, fontsize=6.8,
                color='#222222', ha='center', va='bottom',
                bbox=dict(boxstyle='round,pad=0.04', fc='white', ec='none', alpha=0.85))


# ── Node geometry ─────────────────────────────────────────────────────────────
# Heights: diamonds hh=0.45 (total height=0.9), rects vary
DH = 0.45   # diamond half-height
DW = 2.6    # diamond half-width

# Y positions (top=17, bottom=1)
Y_START = 17.0
Y_D1    = 15.6
Y_D2    = 13.5
Y_AVOID = 13.5   # AVOID box same row as D2 (right branch)
Y_T2    = 12.2   # Q4_K_S box (below AVOID on right)
Y_D3    = 11.2
Y_D4    =  9.1
Y_D5    =  7.0
Y_DEF   =  5.1

# Right-branch terminal box sizes
RW, RH = 2.6, 0.9

# ── START ─────────────────────────────────────────────────────────────────────
draw_rect(CX, Y_START, 5.4, 0.7,
          'START: Select GGUF variant',
          fc=C_STA_F, ec=C_STA_E, fs=8, bold=True)

# START → D1
vert_arrow(CX, Y_START - 0.35, Y_D1 + DH)

# ── D1: ctx > 512 AND speed-critical? ────────────────────────────────────────
draw_diamond(CX, Y_D1, DW * 2, DH * 2,
             'ctx > 512\nAND speed-critical?')

# YES → Q2_K + KV Q8_0
horiz_arrow(CX + DW, Y_D1, RX - RW / 2, label='YES')
draw_rect(RX, Y_D1, RW, RH,
          'Q2_K + KV Q8_0',
          fc=C_REC_F, ec=C_REC_E, fs=7.5,
          note='4.04 tok/s, cliff-free above ctx≈1400')

# NO → D2
vert_arrow(CX, Y_D1 - DH, Y_D2 + DH, label='NO')

# ── D2: MCQ / classification / tool-call? ────────────────────────────────────
draw_diamond(CX, Y_D2, DW * 2, DH * 2,
             'MCQ / classification\n/ tool-call?')

# YES → AVOID Q2_K
horiz_arrow(CX + DW, Y_D2, RX - RW / 2, label='YES')
draw_rect(RX, Y_AVOID, RW, 0.75,
          'AVOID Q2_K\n(format collapse)',
          fc=C_AVD_F, ec=C_AVD_E, fs=7)

# → below AVOID: Q4_K_S
vert_arrow(RX, Y_AVOID - 0.375, Y_T2 + 0.45, label='use', label_dx=0.38)
draw_rect(RX, Y_T2, RW, RH,
          'Q4_K_S',
          fc=C_REC_F, ec=C_REC_E, fs=7.5,
          note='5.01 tok/s, 74% BoolQ')

# NO → D3
vert_arrow(CX, Y_D2 - DH, Y_D3 + DH, label='NO')

# ── D3: RAM ≤ 2 GB? ───────────────────────────────────────────────────────────
draw_diamond(CX, Y_D3, DW * 2, DH * 2,
             'RAM ≤ 2 GB?')

# YES → Q3_K_M
horiz_arrow(CX + DW, Y_D3, RX - RW / 2, label='YES')
draw_rect(RX, Y_D3, RW, RH,
          'Q3_K_M',
          fc=C_REC_F, ec=C_REC_E, fs=7.5,
          note='1.6 GB, 4.68 tok/s, −11% ctx-stable')

# NO → D4
vert_arrow(CX, Y_D3 - DH, Y_D4 + DH, label='NO')

# ── D4: Metal GPU backend (M4)? ───────────────────────────────────────────────
draw_diamond(CX, Y_D4, DW * 2, DH * 2,
             'Metal GPU\nbackend (M4)?')

# YES → Q4_K_S Metal
horiz_arrow(CX + DW, Y_D4, RX - RW / 2, label='YES')
draw_rect(RX, Y_D4, RW, RH,
          'Q4_K_S Metal',
          fc=C_REC_F, ec=C_REC_E, fs=7.5,
          note='19.9 tok/s — ordering reversed')

# NO → D5
vert_arrow(CX, Y_D4 - DH, Y_D5 + DH, label='NO')

# ── D5: ctx ≥ 512 (extended context)? ────────────────────────────────────────
draw_diamond(CX, Y_D5, DW * 2, DH * 2,
             'ctx ≥ 512\n(extended context)?')

# YES → Q4_K_M + KV Q8_0
horiz_arrow(CX + DW, Y_D5, RX - RW / 2, label='YES')
draw_rect(RX, Y_D5, RW, RH,
          'Q4_K_M + KV Q8_0',
          fc=C_REC_F, ec=C_REC_E, fs=7.5,
          note='4.70 tok/s, −5.5% to ctx=2048')

# NO → DEFAULT
vert_arrow(CX, Y_D5 - DH, Y_DEF + 0.48, label='NO')

# ── DEFAULT terminal ──────────────────────────────────────────────────────────
draw_rect(CX, Y_DEF, 5.4, 0.95,
          'Q4_K_M  —  default',
          fc=C_REC_F, ec=C_REC_E, fs=8, bold=True,
          note='4.78 tok/s · 72% BoolQ · best all-round')

# ── Legend ────────────────────────────────────────────────────────────────────
legend_items = [
    (C_DEC_F, C_DEC_E, 'Decision'),
    (C_REC_F, C_REC_E, 'Recommendation'),
    (C_AVD_F, C_AVD_E, 'Caution / Avoid'),
]
lx, ly = 0.4, 3.8
for fc, ec, lbl in legend_items:
    patch = FancyBboxPatch((lx, ly - 0.22), 0.55, 0.44,
                           boxstyle='round,pad=0.04',
                           facecolor=fc, edgecolor=ec, linewidth=1.0, zorder=3)
    ax.add_patch(patch)
    ax.text(lx + 0.72, ly, lbl, fontsize=6.8, va='center')
    lx += 3.1

# ── Save ──────────────────────────────────────────────────────────────────────
plt.tight_layout()

out_dir = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'figures')
)
os.makedirs(out_dir, exist_ok=True)

pdf_path = os.path.join(out_dir, 'deployment_flowchart.pdf')
png_path = os.path.join(out_dir, 'deployment_flowchart.png')
plt.savefig(pdf_path, bbox_inches='tight', dpi=300)
plt.savefig(png_path, bbox_inches='tight', dpi=300)
print(f'Saved: {pdf_path}')
print(f'Saved: {png_path}')
plt.close()
