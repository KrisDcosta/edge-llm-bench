#!/usr/bin/env python3
"""
plot_cliff_crossplat.py — Cross-platform KV-cache cliff figure

Compares KV-cache cliff behavior across three platforms:
  ARM (Pixel 6a)  — clear cliff when KV cache overflows L2 (~768 tokens)
  x86 (i5-1235U)  — delayed cliff at L2 limit (~1200-1300 tokens)
  M4 Metal        — completely flat (GPU unified memory, no L2 bottleneck)

Generates:
  figures/fig_cliff_crossplat.png      — 3-panel, all 7 variants
  figures/fig_cliff_crossplat_sel.png  — selected variants for paper
  figures/fig_cliff_3plat_sel.png      — 3-platform selected variants (paper main figure)

Usage:
  python3 scripts/analyze/plot_cliff_crossplat.py
"""

import json, os
from collections import defaultdict
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

os.makedirs("figures", exist_ok=True)

# ── Data directories ──────────────────────────────────────────
PIXEL_DIR = "results/pixel_llama_cliff_filled_canonical_n10"
X86_DIR   = "results/x86_llama_cliff_20260329_002333"
M4_DIR    = "results/m4_metal_cliff_20260323_015934"

VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
COLORS = {
    "Q2_K":   "#ef4444",
    "Q3_K_M": "#f97316",
    "Q4_K_S": "#eab308",
    "Q4_K_M": "#22c55e",
    "Q5_K_M": "#06b6d4",
    "Q6_K":   "#8b5cf6",
    "Q8_0":   "#ec4899",
}
MARKERS = {
    "Q2_K":   "o",
    "Q3_K_M": "s",
    "Q4_K_S": "^",
    "Q4_K_M": "D",
    "Q5_K_M": "v",
    "Q6_K":   "P",
    "Q8_0":   "X",
}
LINE_STYLES = {
    "Q2_K":   "-",
    "Q3_K_M": "--",
    "Q4_K_S": "-.",
    "Q4_K_M": ":",
    "Q5_K_M": (0, (5, 1)),
    "Q6_K":   (0, (3, 1, 1, 1)),
    "Q8_0":   (0, (1, 1)),
}

def load_cliff(results_dir, file_prefix="cliff_filled_"):
    """Load JSONL cliff files; fall back to 'cliff_' prefix if filled not found."""
    data = {}
    for v in VARIANTS:
        path = os.path.join(results_dir, f"{file_prefix}{v}.jsonl")
        if not os.path.exists(path):
            # Try without 'filled' prefix (M4 naming)
            path = os.path.join(results_dir, f"cliff_{v}.jsonl")
        if not os.path.exists(path):
            continue
        ctx_tps = defaultdict(list)
        for line in open(path):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            tps = float(r.get("decode_tps", 0))
            if tps > 0:
                ctx_tps[r["context"]].append(tps)
        if ctx_tps:
            data[v] = ctx_tps
    return data

pixel_data = load_cliff(PIXEL_DIR, file_prefix="cliff_filled_")
x86_data   = load_cliff(X86_DIR,   file_prefix="cliff_filled_")
m4_data    = load_cliff(M4_DIR,    file_prefix="cliff_")

def get_curve(ctx_tps):
    ctxs  = sorted(ctx_tps)
    means = [np.mean(ctx_tps[c]) for c in ctxs]
    stds  = [np.std(ctx_tps[c]) / np.sqrt(len(ctx_tps[c])) for c in ctxs]  # SEM
    return ctxs, means, stds

# ── Figure 1: All 7 variants, side-by-side ──────────────────
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5.5))

for v in VARIANTS:
    if v in pixel_data:
        ctxs, means, sems = get_curve(pixel_data[v])
        ax1.plot(ctxs, means, color=COLORS[v], linestyle=LINE_STYLES[v],
                 marker=MARKERS[v], markersize=5, linewidth=1.5,
                 label=v, zorder=5)
        ax1.fill_between(ctxs,
                         [m - s for m, s in zip(means, sems)],
                         [m + s for m, s in zip(means, sems)],
                         color=COLORS[v], alpha=0.12)

# Annotate Pixel cliff region
ax1.axvspan(768, 1100, alpha=0.07, color='red', label='_nolegend_')
ax1.text(920, ax1.get_ylim()[1] * 0.97 if ax1.get_ylim()[1] > 0 else 5.5,
         "L2\ncliff\nzone", ha='center', fontsize=7.5, color='#dc2626',
         style='italic', va='top')

ax1.set_xlabel("Context Length (tokens)", fontsize=10)
ax1.set_ylabel("Decode Throughput (t/s)", fontsize=10)
ax1.set_title("(a) ARM Pixel 6a — KV-Cache Cliff\n(filled context, 3 trials)", fontsize=11, fontweight='bold')
ax1.legend(fontsize=8, loc='upper right', ncol=2, framealpha=0.9)
ax1.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

for v in VARIANTS:
    if v in m4_data:
        ctxs, means, sems = get_curve(m4_data[v])
        ax2.plot(ctxs, means, color=COLORS[v], linestyle=LINE_STYLES[v],
                 marker=MARKERS[v], markersize=5, linewidth=1.5,
                 label=v, zorder=5)
        ax2.fill_between(ctxs,
                         [m - s for m, s in zip(means, sems)],
                         [m + s for m, s in zip(means, sems)],
                         color=COLORS[v], alpha=0.12)

ax2.set_xlabel("Context Length (tokens)", fontsize=10)
ax2.set_ylabel("Decode Throughput (t/s)", fontsize=10)
ax2.set_title("(b) M4 Mac (Metal GPU) — No Cliff\n(filled context, 5 trials)", fontsize=11, fontweight='bold')
ax2.legend(fontsize=8, loc='center right', ncol=2, framealpha=0.9)
ax2.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)

# Add "flat" annotation for Metal
ax2.annotate("All variants\nflat ±2%",
             xy=(1600, 9.0), fontsize=9, color='#374151',
             ha='center', style='italic',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#f9fafb', alpha=0.85))

fig.suptitle("KV-Cache Cliff: ARM CPU vs Metal GPU\n"
             "Llama 3.2 3B Instruct · filled context (prompt ≈ ctx − 64 tokens)",
             fontsize=12, fontweight='bold', y=1.01)

fig.tight_layout()
out = "figures/fig_cliff_crossplat.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Figure 2: Selected variants for paper (cleaner) ──────────
SEL = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K"]

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

for v in SEL:
    if v in pixel_data:
        ctxs, means, sems = get_curve(pixel_data[v])
        ax1.errorbar(ctxs, means, yerr=sems, color=COLORS[v], linestyle=LINE_STYLES[v],
                     marker=MARKERS[v], markersize=6, linewidth=2,
                     label=v, capsize=3, capthick=1, zorder=5)

ax1.axvspan(768, 1100, alpha=0.08, color='red')
ax1.text(935, 0.5, "L2 cliff zone", ha='center', fontsize=8,
         color='#dc2626', style='italic', transform=ax1.get_xaxis_transform())

ax1.set_xlabel("Context Length (tokens)", fontsize=10)
ax1.set_ylabel("Decode Throughput (t/s)", fontsize=10)
ax1.set_title("(a) ARM Pixel 6a — KV-Cache Cliff", fontsize=11, fontweight='bold')
ax1.legend(fontsize=9, loc='upper right', framealpha=0.9)
ax1.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax1.spines['top'].set_visible(False)
ax1.spines['right'].set_visible(False)

for v in SEL:
    if v in m4_data:
        ctxs, means, sems = get_curve(m4_data[v])
        ax2.errorbar(ctxs, means, yerr=sems, color=COLORS[v], linestyle=LINE_STYLES[v],
                     marker=MARKERS[v], markersize=6, linewidth=2,
                     label=v, capsize=3, capthick=1, zorder=5)

ax2.set_xlabel("Context Length (tokens)", fontsize=10)
ax2.set_ylabel("Decode Throughput (t/s)", fontsize=10)
ax2.set_title("(b) M4 Metal — No KV-Cache Cliff", fontsize=11, fontweight='bold')
ax2.legend(fontsize=9, loc='center right', framealpha=0.9)
ax2.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax2.spines['top'].set_visible(False)
ax2.spines['right'].set_visible(False)

# Metal y-axis: zoom in to show flatness clearly
if m4_data:
    all_m4 = [v for sl in [list(m4_data[v].values()) for v in SEL if v in m4_data] for vl in sl for v in vl]
    if all_m4:
        ymin, ymax = min(all_m4) * 0.85, max(all_m4) * 1.15
        ax2.set_ylim(ymin, ymax)
        ax2.annotate("±2% variation\n(no cliff)", xy=(1600, (ymin+ymax)/2),
                     fontsize=9, color='#374151', ha='center',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor='#f9fafb', alpha=0.9))

fig.suptitle("Metal GPU Eliminates the KV-Cache L2 Cliff Seen on ARM/x86 CPU\n"
             "Llama 3.2 3B Instruct · Pixel 6a (ARM, 4 threads) vs M4 Mac (Metal)",
             fontsize=11, fontweight='bold', y=1.01)

fig.tight_layout()
out = "figures/fig_cliff_crossplat_sel.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Figure 3: Three-platform selected variants (paper main figure) ──
SEL3 = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K"]

fig, axes = plt.subplots(1, 3, figsize=(17, 5))
ax1, ax2, ax3 = axes

# Panel (a) ARM Pixel 6a
for v in SEL3:
    if v in pixel_data:
        ctxs, means, sems = get_curve(pixel_data[v])
        ax1.errorbar(ctxs, means, yerr=sems, color=COLORS[v], linestyle=LINE_STYLES[v],
                     marker=MARKERS[v], markersize=5, linewidth=2,
                     label=v, capsize=3, capthick=1)

ax1.axvspan(600, 900, alpha=0.10, color='red')
ax1.text(750, ax1.get_ylim()[1] if ax1.get_ylim()[1] > 0 else 5, "L2\ncliff",
         ha='center', fontsize=8, color='#dc2626', style='italic',
         transform=ax1.transData, va='top',
         bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none'))
ax1.set_xlabel("Context Length (tokens)", fontsize=10)
ax1.set_ylabel("Decode TPS (tokens/s)", fontsize=10)
ax1.set_title("(a) ARM — Pixel 6a (Cortex-X1)\n512 KB L2 · cliff ≈ 768 tok", fontsize=10, fontweight='bold')
ax1.legend(fontsize=8.5, loc='upper right', framealpha=0.9)
ax1.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax1.spines['top'].set_visible(False); ax1.spines['right'].set_visible(False)

# Panel (b) x86 Intel i5-1235U
for v in SEL3:
    if v in x86_data:
        ctxs, means, sems = get_curve(x86_data[v])
        ax2.errorbar(ctxs, means, yerr=sems, color=COLORS[v], linestyle=LINE_STYLES[v],
                     marker=MARKERS[v], markersize=5, linewidth=2,
                     label=v, capsize=3, capthick=1)

ax2.axvspan(1100, 1400, alpha=0.10, color='orange')
ax2.text(1250, ax2.get_ylim()[1] if ax2.get_ylim()[1] > 0 else 12, "L2\ncliff",
         ha='center', fontsize=8, color='#d97706', style='italic',
         transform=ax2.transData, va='top',
         bbox=dict(boxstyle='round,pad=0.2', facecolor='white', alpha=0.7, edgecolor='none'))
ax2.set_xlabel("Context Length (tokens)", fontsize=10)
ax2.set_ylabel("Decode TPS (tokens/s)", fontsize=10)
ax2.set_title("(b) x86 — Intel i5-1235U (AVX2)\n1.25 MB L2 · cliff ≈ 1200–1300 tok", fontsize=10, fontweight='bold')
ax2.legend(fontsize=8.5, loc='upper right', framealpha=0.9)
ax2.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax2.spines['top'].set_visible(False); ax2.spines['right'].set_visible(False)

# Panel (c) M4 Metal
for v in SEL3:
    if v in m4_data:
        ctxs, means, sems = get_curve(m4_data[v])
        ax3.errorbar(ctxs, means, yerr=sems, color=COLORS[v], linestyle=LINE_STYLES[v],
                     marker=MARKERS[v], markersize=5, linewidth=2,
                     label=v, capsize=3, capthick=1)

ax3.set_xlabel("Context Length (tokens)", fontsize=10)
ax3.set_ylabel("Decode TPS (tokens/s)", fontsize=10)
ax3.set_title("(c) Metal GPU — Apple M4\nUnified memory · no cliff", fontsize=10, fontweight='bold')
ax3.legend(fontsize=8.5, loc='center right', framealpha=0.9)
ax3.grid(alpha=0.3, linestyle=':', linewidth=0.8)
ax3.spines['top'].set_visible(False); ax3.spines['right'].set_visible(False)
# Zoom y to show flatness
all_m4_vals = [x for v in SEL3 if v in m4_data for vals in m4_data[v].values() for x in vals]
if all_m4_vals:
    ylo, yhi = min(all_m4_vals)*0.88, max(all_m4_vals)*1.12
    ax3.set_ylim(ylo, yhi)
ax3.annotate("All lines flat ±2%", xy=(1600, (ax3.get_ylim()[0]+ax3.get_ylim()[1])/2),
             fontsize=9, color='#374151', ha='center', style='italic',
             bbox=dict(boxstyle='round,pad=0.3', facecolor='#f9fafb', alpha=0.9))

fig.suptitle("KV-Cache Cliff: CPU L2 Overflow vs GPU Unified Memory · Llama 3.2 3B Instruct",
             fontsize=12, fontweight='bold', y=1.02)
fig.tight_layout()
out = "figures/fig_cliff_3plat_sel.png"
fig.savefig(out, dpi=150, bbox_inches='tight')
plt.close(fig)
print(f"✅ Saved {out}")

# ── Print x86 cliff summary ───────────────────────────────────
print("\nx86 filled-context cliff summary:")
print(f"{'Variant':<10} {'256':>7} {'768':>7} {'1024':>7} {'1300':>7} {'2048':>7} {'drop%':>7}")
print("-"*58)
for v in VARIANTS:
    if v not in x86_data:
        print(f"{v:<10}  (no data)"); continue
    d = x86_data[v]
    def m(c): return np.mean(d[c]) if c in d else float('nan')
    base = m(256); final = m(2048)
    drop = (base - final)/base*100 if base > 0 else 0
    def fmt(x): return f"{x:.1f}" if not np.isnan(x) else "  —"
    print(f"{v:<10} {fmt(m(256)):>7} {fmt(m(768)):>7} {fmt(m(1024)):>7} {fmt(m(1300)):>7} {fmt(m(2048)):>7} {drop:>6.0f}%")

# ── Print summary table ───────────────────────────────────────
print("\nPixel 6a filled-context cliff summary:")
print(f"{'Variant':<10} {'ctx=256':>8} {'ctx=768':>8} {'ctx=1024':>9} {'ctx=2048':>9} {'drop%':>7}")
print("-"*55)
for v in VARIANTS:
    if v not in pixel_data:
        print(f"{v:<10}  (no data)")
        continue
    d = pixel_data[v]
    c256  = np.mean(d.get(256,  [0])) or None
    c768  = np.mean(d.get(768,  [0])) or None
    c1024 = np.mean(d.get(1024, [0])) or None
    c2048 = np.mean(d.get(2048, [0])) or None
    baseline = c256 or c768 or c1024 or 0
    final    = c2048 or 0
    drop = (baseline - final) / baseline * 100 if baseline > 0 else 0
    def fmt(x): return f"{x:.2f}" if x else "  —  "
    print(f"{v:<10} {fmt(c256):>8} {fmt(c768):>8} {fmt(c1024):>9} {fmt(c2048):>9} {drop:>6.0f}%")

print("\nM4 Metal summary (flat — no cliff):")
print(f"{'Variant':<10} {'ctx=1024':>9} {'ctx=1500':>9} {'ctx=2048':>9} {'variation%':>11}")
print("-"*50)
for v in VARIANTS:
    if v not in m4_data:
        print(f"{v:<10}  (no data)")
        continue
    d = m4_data[v]
    c1024 = np.mean(d.get(1024, [0])) or None
    c1500 = np.mean(d.get(1500, [0])) or None
    c2048 = np.mean(d.get(2048, [0])) or None
    all_vals = [x for xs in d.values() for x in xs]
    variation = (max(all_vals) - min(all_vals)) / np.mean(all_vals) * 100 if all_vals else 0
    def fmt(x): return f"{x:.2f}" if x else "  —  "
    print(f"{v:<10} {fmt(c1024):>9} {fmt(c1500):>9} {fmt(c2048):>9} {variation:>10.1f}%")
