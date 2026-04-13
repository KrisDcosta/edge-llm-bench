#!/usr/bin/env python3
"""
Generate publication-quality figures for MLSys 2026 paper.
IEEE two-column format, 300 DPI, consistent color scheme.

Figures generated:
  fig_decode_tps   — Pixel 6a decode throughput vs context length (all 7 variants)
  fig_kv_cliff     — KV-cache cliff: decode TPS vs context (Pixel + M4, key variants)
  fig_ppl_curve    — Perplexity vs bits-per-weight (PPL-bpw trade-off)
  fig_pareto       — Pareto frontier: decode TPS vs ARC-Easy accuracy
  fig_quality      — Quality metrics heatmap across benchmarks and variants
"""

import json
import os
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ─────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────
BASE = str(Path(__file__).resolve().parent.parent.parent)
PIXEL_TPS_DIR  = f"{BASE}/results/pixel_llama_tps_20260325_120022"
PIXEL_CLIFF_DIR = f"{BASE}/results/pixel_llama_cliff_20260325_060911"
M4_TPS_DIR     = f"{BASE}/results/m4_llama_tps_20260326_001546"
M4_CLIFF_NEW = {
    "Q3_K_M": f"{BASE}/results/m4_llama_cliff_20260325_160146/cliff_Q3_K_M.jsonl",
    "Q4_K_S": f"{BASE}/results/m4_llama_cliff_20260325_172455/cliff_Q4_K_S.jsonl",
    "Q5_K_M": f"{BASE}/results/m4_llama_cliff_20260325_180433/cliff_Q5_K_M.jsonl",
}
M4_CLIFF_OLD = f"{BASE}/results/kv_cache_cliff_20260320_021544"
QUALITY_JSON = f"{BASE}/results/quality_scores.json"
OUT_DIR = f"{BASE}/report/figures"
os.makedirs(OUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# Style constants — IEEE two-column
# ─────────────────────────────────────────────
VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
VARIANT_LABELS = {
    "Q2_K":   "Q2_K",
    "Q3_K_M": "Q3_K_M",
    "Q4_K_S": "Q4_K_S",
    "Q4_K_M": "Q4_K_M (*)",
    "Q5_K_M": "Q5_K_M",
    "Q6_K":   "Q6_K",
    "Q8_0":   "Q8_0",
}

# Colorblind-safe palette (7 colors)
COLORS = {
    "Q2_K":   "#d62728",
    "Q3_K_M": "#ff7f0e",
    "Q4_K_S": "#bcbd22",
    "Q4_K_M": "#2ca02c",
    "Q5_K_M": "#17becf",
    "Q6_K":   "#1f77b4",
    "Q8_0":   "#9467bd",
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

# IEEE single-column width = 3.5 in, double = 7.16 in
FIG_W_SINGLE = 3.5
FIG_W_DOUBLE = 7.16
FIG_H = 2.6   # height for single-column plots

plt.rcParams.update({
    "font.family":    "serif",
    "font.size":      8,
    "axes.titlesize": 9,
    "axes.labelsize": 8,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "legend.fontsize": 6.5,
    "lines.linewidth": 1.2,
    "lines.markersize": 4,
    "axes.grid":      True,
    "grid.alpha":     0.35,
    "grid.linestyle": "--",
    "figure.dpi":     300,
})

# ─────────────────────────────────────────────
# Data loading helpers
# ─────────────────────────────────────────────

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def load_pixel_tps():
    """Returns {variant: {ctx: (mean, std)}}"""
    data = {}
    for variant in VARIANTS:
        path = os.path.join(PIXEL_TPS_DIR, f"tps_{variant}.jsonl")
        if not os.path.exists(path):
            continue
        records = [r for r in load_jsonl(path) if r.get("decode_tps", 0) > 0]
        by_ctx = {}
        for r in records:
            by_ctx.setdefault(r["context"], []).append(r["decode_tps"])
        data[variant] = {
            ctx: (np.mean(v), np.std(v, ddof=1) if len(v) > 1 else 0)
            for ctx, v in by_ctx.items()
        }
    return data

def load_pixel_cliff():
    """Returns {variant: {ctx: (mean, std)}}"""
    data = {}
    for variant in VARIANTS:
        path = os.path.join(PIXEL_CLIFF_DIR, f"cliff_{variant}.jsonl")
        if not os.path.exists(path):
            continue
        records = [r for r in load_jsonl(path) if r.get("decode_tps", 0) > 0]
        by_ctx = {}
        for r in records:
            by_ctx.setdefault(r["context"], []).append(r["decode_tps"])
        data[variant] = {
            ctx: (np.mean(v), np.std(v, ddof=1) if len(v) > 1 else 0)
            for ctx, v in by_ctx.items()
        }
    return data

def load_m4_cliff():
    """Returns {variant: {ctx: (mean, std)}} mixing old+new runs."""
    data = {}
    # Old Mar-20 data (per-trial format)
    for fname in os.listdir(M4_CLIFF_OLD):
        if not fname.endswith(".jsonl"):
            continue
        variant = fname.replace("cliff_", "").replace(".jsonl", "")
        records = [r for r in load_jsonl(os.path.join(M4_CLIFF_OLD, fname))
                   if r.get("decode_tps", 0) > 0]
        by_ctx = {}
        for r in records:
            by_ctx.setdefault(r["context"], []).append(r["decode_tps"])
        data[variant] = {
            ctx: (np.mean(v), np.std(v, ddof=1) if len(v) > 1 else 0)
            for ctx, v in by_ctx.items()
        }
    # New runs (pre-aggregated: decode_tps is already mean, decode_std is std)
    for variant, path in M4_CLIFF_NEW.items():
        if not os.path.exists(path):
            continue
        records = [r for r in load_jsonl(path) if r.get("decode_tps", 0) > 0]
        data[variant] = {
            r["context"]: (r["decode_tps"], r.get("decode_std", 0))
            for r in records
        }
    return data

def load_m4_tps():
    """Returns {variant: {"pp": {n_prompt: (mean,std)}, "tg": (mean,std)}}"""
    data = {}
    for variant in VARIANTS:
        path = os.path.join(M4_TPS_DIR, f"tps_{variant}.jsonl")
        if not os.path.exists(path):
            continue
        records = load_jsonl(path)
        pp = {}
        tg = None
        for r in records:
            if r.get("test_type") == "pp":
                pp[r["n_prompt"]] = (r["tps_mean"], r["tps_std"])
            elif r.get("test_type") == "tg":
                tg = (r["tps_mean"], r["tps_std"])
        data[variant] = {"pp": pp, "tg": tg}
    return data

def load_quality():
    with open(QUALITY_JSON) as f:
        return json.load(f)

# ─────────────────────────────────────────────
# Hard-coded reference data
# ─────────────────────────────────────────────

# PPL from COMPLETE_RESULTS_SUMMARY.json (Pixel 6a, WikiText-2 full)
PPL_DATA = {
    "Q2_K":   13.29,
    "Q3_K_M": 11.08,
    "Q4_K_S": 10.70,
    "Q4_K_M": 10.71,
    "Q5_K_M": 10.62,
    "Q6_K":   10.58,
    "Q8_0":   10.59,
}
PPL_STD = {   # from ±0.08 / ±0.10 in summary
    "Q2_K":   0.10,
    "Q3_K_M": 0.08,
    "Q4_K_S": 0.08,
    "Q4_K_M": 0.08,
    "Q5_K_M": 0.08,
    "Q6_K":   0.08,
    "Q8_0":   0.08,
}

# Bits-per-weight (file_bytes * 8 / 3.21e9 params)
BPW = {
    "Q2_K":   3.40,
    "Q3_K_M": 4.20,
    "Q4_K_S": 4.81,
    "Q4_K_M": 5.03,
    "Q5_K_M": 5.79,
    "Q6_K":   6.59,
    "Q8_0":   8.53,
}

# Model sizes in GB
SIZE_GB = {
    "Q2_K":   1.36,
    "Q3_K_M": 1.69,
    "Q4_K_S": 1.93,
    "Q4_K_M": 2.02,
    "Q5_K_M": 2.32,
    "Q6_K":   2.64,
    "Q8_0":   3.42,
}

# ═══════════════════════════════════════════════════════════
# Figure 1 — Pixel 6a Decode TPS vs Context Length
# ═══════════════════════════════════════════════════════════

def fig_decode_tps():
    data = load_pixel_tps()
    fig, ax = plt.subplots(figsize=(FIG_W_DOUBLE, FIG_H))

    for variant in VARIANTS:
        if variant not in data:
            continue
        ctxs = sorted(data[variant].keys())
        means = [data[variant][c][0] for c in ctxs]
        stds  = [data[variant][c][1] for c in ctxs]
        ax.errorbar(
            ctxs, means, yerr=stds,
            label=VARIANT_LABELS[variant],
            color=COLORS[variant],
            marker=MARKERS[variant],
            capsize=2, capthick=0.8,
        )

    ax.set_xlabel("Context Length (tokens)")
    ax.set_ylabel("Decode Throughput (t/s)")
    ax.set_title("Pixel 6a: Decode Throughput vs. Context Length")
    ax.set_xscale("log", base=2)
    ax.set_xticks([256, 512, 1024, 2048])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.legend(loc="lower left", ncol=2, framealpha=0.85)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    save_fig(fig, "fig_decode_tps")


# ═══════════════════════════════════════════════════════════
# Figure 2 — KV-Cache Cliff  (Pixel + M4)
# ═══════════════════════════════════════════════════════════

def fig_kv_cliff():
    pixel_cliff = load_pixel_cliff()
    m4_cliff    = load_m4_cliff()

    # Select variants with visible cliff or interesting pattern
    # Pixel: Q2_K has a clear cliff ~1350-1600; Q3_K_M gradual decline
    # M4:    Q6_K has sharp cliff at 1500→1550; Q4_K_M flat (no cliff)
    pixel_variants = ["Q2_K", "Q4_K_M", "Q6_K"]
    m4_variants    = ["Q4_K_M", "Q6_K"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(FIG_W_DOUBLE, FIG_H), sharey=False)

    # ── Pixel panel ──
    for variant in pixel_variants:
        if variant not in pixel_cliff:
            continue
        ctxs  = sorted(pixel_cliff[variant].keys())
        means = [pixel_cliff[variant][c][0] for c in ctxs]
        stds  = [pixel_cliff[variant][c][1] for c in ctxs]
        ax1.errorbar(ctxs, means, yerr=stds,
                     label=VARIANT_LABELS[variant],
                     color=COLORS[variant], marker=MARKERS[variant],
                     capsize=2, capthick=0.8)

    ax1.set_xlabel("Context Length (tokens)")
    ax1.set_ylabel("Decode Throughput (t/s)")
    ax1.set_title("(a) Pixel 6a — KV-Cache Cliff")
    ax1.set_xlim(1000, 2100)
    ax1.set_xticks([1024, 1200, 1400, 1600, 1800, 2048])
    ax1.tick_params(axis='x', rotation=30)
    ax1.legend(fontsize=6)

    # ── M4 panel ──
    for variant in m4_variants:
        if variant not in m4_cliff:
            continue
        ctxs  = sorted(m4_cliff[variant].keys())
        means = [m4_cliff[variant][c][0] for c in ctxs]
        stds  = [m4_cliff[variant][c][1] for c in ctxs]
        ax2.errorbar(ctxs, means, yerr=stds,
                     label=VARIANT_LABELS[variant],
                     color=COLORS[variant], marker=MARKERS[variant],
                     capsize=2, capthick=0.8)

    ax2.set_xlabel("Context Length (tokens)")
    ax2.set_ylabel("Decode Throughput (t/s)")
    ax2.set_title("(b) M4 Mac (Metal) — KV-Cache Cliff")
    ax2.set_xlim(1000, 2100)
    ax2.set_xticks([1024, 1200, 1400, 1600, 1800, 2048])
    ax2.tick_params(axis='x', rotation=30)
    ax2.legend(fontsize=6)

    fig.tight_layout()
    save_fig(fig, "fig_kv_cliff")


# ═══════════════════════════════════════════════════════════
# Figure 3 — PPL vs Bits-per-Weight
# ═══════════════════════════════════════════════════════════

def fig_ppl_curve():
    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, FIG_H))

    bpws  = [BPW[v]     for v in VARIANTS]
    ppls  = [PPL_DATA[v] for v in VARIANTS]
    stds  = [PPL_STD[v]  for v in VARIANTS]
    colors = [COLORS[v]  for v in VARIANTS]
    markers= [MARKERS[v] for v in VARIANTS]

    for i, variant in enumerate(VARIANTS):
        ax.errorbar(bpws[i], ppls[i], yerr=stds[i],
                    color=colors[i], marker=markers[i],
                    capsize=2, capthick=0.8,
                    label=VARIANT_LABELS[variant])

    # Annotate Q4_K_M as recommended
    idx = VARIANTS.index("Q4_K_M")
    ax.annotate("Recommended", xy=(bpws[idx], ppls[idx]),
                xytext=(bpws[idx] + 0.4, ppls[idx] + 0.3),
                fontsize=6, arrowprops=dict(arrowstyle="->", lw=0.8),
                color=COLORS["Q4_K_M"])

    ax.set_xlabel("Bits per Weight (bpw)")
    ax.set_ylabel("Perplexity (WikiText-2, ↓ better)")
    ax.set_title("Perplexity vs. Quantization Level")
    ax.legend(fontsize=5.5, loc="upper right")
    ax.invert_xaxis()   # higher bpw = more bits, lower perplexity (left = Q8, right = Q2)

    ax.set_xlim(9.0, 3.0)

    fig.tight_layout()
    save_fig(fig, "fig_ppl_curve")


# ═══════════════════════════════════════════════════════════
# Figure 4 — Pareto: Decode TPS vs Quality (arc_easy_fixed)
# ═══════════════════════════════════════════════════════════

def fig_pareto():
    pixel_tps = load_pixel_tps()
    quality   = load_quality()

    ctx = 1024  # representative context

    tps_vals  = {}
    acc_vals  = {}
    size_vals = {}

    for variant in VARIANTS:
        key = f"arc_easy_fixed:{variant}"
        if variant not in pixel_tps or key not in quality:
            continue
        if ctx not in pixel_tps[variant]:
            continue
        tps_vals[variant]  = pixel_tps[variant][ctx][0]
        acc_vals[variant]  = quality[key]["accuracy_pct"]
        size_vals[variant] = SIZE_GB[variant]

    fig, ax = plt.subplots(figsize=(FIG_W_SINGLE, FIG_H + 0.2))

    # Scatter: bubble size = model file size
    max_size = max(size_vals.values())
    for variant in tps_vals:
        sz = size_vals[variant]
        bubble = (sz / max_size) * 250  # scale bubble area
        ax.scatter(acc_vals[variant], tps_vals[variant],
                   s=bubble, color=COLORS[variant],
                   marker=MARKERS[variant], zorder=5,
                   edgecolors="white", linewidths=0.5,
                   label=f"{VARIANT_LABELS[variant]} ({sz:.1f} GB)")

    # Draw Pareto frontier
    pts = sorted(zip(acc_vals.values(), tps_vals.values()))
    pareto = []
    best_tps = -1
    for acc, tps in sorted(pts, reverse=True):
        if tps > best_tps:
            best_tps = tps
            pareto.append((acc, tps))
    if pareto:
        px, py = zip(*sorted(pareto))
        ax.step(px, py, where="post", color="gray", lw=1.0,
                linestyle="--", alpha=0.6, label="Pareto frontier")

    ax.set_xlabel("ARC-Easy Accuracy (%)")
    ax.set_ylabel("Decode Throughput at ctx=1024 (t/s)")
    ax.set_title("Quality–Speed Pareto Frontier\n(Pixel 6a, bubble size ∝ model size)")
    ax.legend(fontsize=5.5, loc="lower right")

    fig.tight_layout()
    save_fig(fig, "fig_pareto")


# ═══════════════════════════════════════════════════════════
# Figure 5 — Quality Metrics Heatmap
# ═══════════════════════════════════════════════════════════

def fig_quality():
    quality = load_quality()

    # Benchmarks and variants with full coverage
    # hellaswag added once all 7 variants completed; mmlu pending Q5/Q6/Q8
    benchmarks = ["arc_easy_fixed", "arc_challenge", "boolq", "hellaswag"]
    bench_labels = ["ARC-Easy", "ARC-Challenge", "BoolQ", "HellaSwag"]
    variants_full = [v for v in VARIANTS
                     if all(f"{b}:{v}" in quality for b in benchmarks)]

    matrix = np.zeros((len(benchmarks), len(variants_full)))
    for i, bench in enumerate(benchmarks):
        for j, variant in enumerate(variants_full):
            key = f"{bench}:{variant}"
            matrix[i, j] = quality[key]["accuracy_pct"]

    fig, ax = plt.subplots(figsize=(FIG_W_DOUBLE, 2.8))

    im = ax.imshow(matrix, aspect="auto", cmap="RdYlGn",
                   vmin=15, vmax=90)

    ax.set_xticks(range(len(variants_full)))
    ax.set_xticklabels([VARIANT_LABELS[v] for v in variants_full],
                       fontsize=7, rotation=20, ha="right")
    ax.set_yticks(range(len(benchmarks)))
    ax.set_yticklabels(bench_labels, fontsize=7)

    # Annotate cells
    for i in range(len(benchmarks)):
        for j in range(len(variants_full)):
            val = matrix[i, j]
            text_color = "black" if 50 < val < 80 else "white"
            ax.text(j, i, f"{val:.0f}%", ha="center", va="center",
                    fontsize=7, color=text_color, fontweight="bold")

    # Highlight Q4_K_M column
    if "Q4_K_M" in variants_full:
        jstar = variants_full.index("Q4_K_M")
        ax.add_patch(mpatches.Rectangle(
            (jstar - 0.5, -0.5), 1, len(benchmarks),
            fill=False, edgecolor="gold", lw=2, zorder=10
        ))

    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    cb.set_label("Accuracy (%)", fontsize=7)
    ax.set_title("Quality Benchmark Accuracy by Quantization Variant")

    fig.tight_layout()
    save_fig(fig, "fig_quality")


# ═══════════════════════════════════════════════════════════
# Figure 6 — Cross-Device Decode TPS: Pixel vs M4 (grouped bar)
# ═══════════════════════════════════════════════════════════

def fig_tps_bar():
    """Grouped bar: Pixel 6a (ctx=1024) vs M4 Mac Metal (TG, empty ctx) decode TPS."""
    pixel_tps = load_pixel_tps()
    m4_tps    = load_m4_tps()
    ctx = 1024

    variants_ok = [v for v in VARIANTS
                   if v in pixel_tps and ctx in pixel_tps[v]
                   and v in m4_tps and m4_tps[v]["tg"] is not None]

    n = len(variants_ok)
    x = np.arange(n)
    w = 0.35  # bar width

    pixel_means = [pixel_tps[v][ctx][0] for v in variants_ok]
    pixel_stds  = [pixel_tps[v][ctx][1] for v in variants_ok]
    m4_means    = [m4_tps[v]["tg"][0]   for v in variants_ok]
    m4_stds     = [m4_tps[v]["tg"][1]   for v in variants_ok]

    fig, ax = plt.subplots(figsize=(FIG_W_DOUBLE, FIG_H))

    bars_pixel = ax.bar(x - w/2, pixel_means, w,
                        color=[COLORS[v] for v in variants_ok],
                        edgecolor="white", linewidth=0.5,
                        label="Pixel 6a (CPU, ctx=1024)", alpha=0.9)
    ax.errorbar(x - w/2, pixel_means, yerr=pixel_stds,
                fmt="none", color="black", capsize=2, capthick=0.7, lw=0.7)

    bars_m4 = ax.bar(x + w/2, m4_means, w,
                     color=[COLORS[v] for v in variants_ok],
                     edgecolor="white", linewidth=0.5,
                     label="M4 Mac (Metal, empty ctx)", alpha=0.55,
                     hatch="//")
    ax.errorbar(x + w/2, m4_means, yerr=m4_stds,
                fmt="none", color="black", capsize=2, capthick=0.7, lw=0.7)

    # Highlight Q4_K_M bars
    if "Q4_K_M" in variants_ok:
        idx = variants_ok.index("Q4_K_M")
        bars_pixel[idx].set_edgecolor("gold")
        bars_pixel[idx].set_linewidth(2)
        bars_m4[idx].set_edgecolor("gold")
        bars_m4[idx].set_linewidth(2)

    # Annotate speedup ratio above each M4 bar
    for i, v in enumerate(variants_ok):
        ratio = m4_means[i] / pixel_means[i] if pixel_means[i] > 0 else 0
        ax.text(x[i] + w/2, m4_means[i] + m4_stds[i] + 0.3,
                f"{ratio:.1f}x", ha="center", va="bottom",
                fontsize=5.5, color="dimgray")

    ax.set_xticks(x)
    ax.set_xticklabels([VARIANT_LABELS[v] for v in variants_ok],
                       rotation=20, ha="right", fontsize=7)
    ax.set_ylabel("Decode Throughput (t/s)")
    ax.set_title("Cross-Device Decode TPS: Pixel 6a vs. M4 Mac  (Llama 3.2 3B)")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=6.5, loc="upper right")

    fig.tight_layout()
    save_fig(fig, "fig_tps_bar")


# ═══════════════════════════════════════════════════════════
# Figure 7 — M4 Mac: Prefill TPS across context lengths
# ═══════════════════════════════════════════════════════════

def fig_m4_prefill():
    """M4 Metal prefill (PP) TPS vs context size, all variants."""
    m4_tps = load_m4_tps()
    pp_sizes = [128, 256, 512, 1024]

    fig, ax = plt.subplots(figsize=(FIG_W_DOUBLE, FIG_H))

    for variant in VARIANTS:
        if variant not in m4_tps:
            continue
        pp = m4_tps[variant]["pp"]
        ctxs  = [p for p in pp_sizes if p in pp]
        means = [pp[p][0] for p in ctxs]
        stds  = [pp[p][1] for p in ctxs]
        ax.errorbar(
            ctxs, means, yerr=stds,
            label=VARIANT_LABELS[variant],
            color=COLORS[variant],
            marker=MARKERS[variant],
            capsize=2, capthick=0.8,
        )

    ax.set_xlabel("Prompt Length (tokens)")
    ax.set_ylabel("Prefill Throughput (t/s)")
    ax.set_title("M4 Mac (Metal): Prefill TPS vs. Prompt Length  (Llama 3.2 3B)")
    ax.set_xscale("log", base=2)
    ax.set_xticks(pp_sizes)
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.legend(loc="lower right", ncol=2, framealpha=0.85)
    ax.set_ylim(bottom=0)

    fig.tight_layout()
    save_fig(fig, "fig_m4_prefill")


# ─────────────────────────────────────────────
# Save helper — both PDF and PNG
# ─────────────────────────────────────────────

def save_fig(fig, name):
    for ext in ("pdf", "png"):
        path = os.path.join(OUT_DIR, f"{name}.{ext}")
        fig.savefig(path, dpi=300, bbox_inches="tight")
        print(f"  Saved: {path}")
    plt.close(fig)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

if __name__ == "__main__":
    import matplotlib.ticker  # needed for ScalarFormatter

    print("Generating figures...")
    print()

    print("[1/7] fig_decode_tps — Pixel decode TPS vs context")
    fig_decode_tps()

    print("[2/7] fig_kv_cliff — KV-cache cliff (Pixel + M4)")
    fig_kv_cliff()

    print("[3/7] fig_ppl_curve — Perplexity vs bpw")
    fig_ppl_curve()

    print("[4/7] fig_pareto — Quality-speed Pareto")
    fig_pareto()

    print("[5/7] fig_quality — Quality heatmap")
    fig_quality()

    print("[6/7] fig_tps_bar — Cross-device decode TPS comparison (Pixel vs M4)")
    fig_tps_bar()

    print("[7/7] fig_m4_prefill — M4 Metal prefill TPS vs prompt length")
    fig_m4_prefill()

    print()
    print("All figures saved to:", OUT_DIR)
    print("Files:", sorted(os.listdir(OUT_DIR)))
