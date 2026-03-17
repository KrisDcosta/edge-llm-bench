#!/usr/bin/env python3
"""
generate_figures.py — One-command figure generation from raw JSONL benchmark logs.

Usage:
    python analysis/generate_figures.py results/                  # all .jsonl in dir
    python analysis/generate_figures.py results/run-20260301.jsonl # single file

Output:
    figures/fig1_prefill_tps_vs_context.png
    figures/fig2_decode_tps_vs_context.png
    figures/fig3_ttft_vs_context.png
    figures/fig4_peak_memory_vs_quant.png
    figures/fig5_battery_per_1k_tokens.png
    figures/fig6_pareto_efficiency_quality.png  (if quality data present)
    figures/fig7_prefill_vs_decode_fraction.png
    figures/fig8_latency_distribution.png
    figures/fig9_model_size_vs_decode_tps.png
    figures/summary_table.csv
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median, stdev

import matplotlib
matplotlib.use("Agg")  # non-interactive backend for headless generation
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent.parent
FIGURES_DIR = PROJECT_ROOT / "figures"

# Quant display order (low → high quality)
QUANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0", "F16"]
QUANT_BITS = {"Q2_K": 2, "Q3_K_M": 3, "Q4_K_M": 4, "Q6_K": 6, "Q8_0": 8, "F16": 16}
MODEL_SIZE_GB = {"Q2_K": 1.3, "Q3_K_M": 1.6, "Q4_K_M": 2.0, "Q6_K": 2.7, "Q8_0": 3.4, "F16": 6.4}

# Color palette: one color per quant variant (colorblind-friendly)
QUANT_COLORS = {
    "Q2_K":   "#e41a1c",
    "Q3_K_M": "#ff7f00",
    "Q4_K_M": "#377eb8",
    "Q6_K":   "#4daf4a",
    "Q8_0":   "#984ea3",
    "F16":    "#a65628",
}

STYLE = {
    "font.family": "sans-serif",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "figure.dpi": 150,
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl_files(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        with open(p) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"WARNING: {p}:{lineno}: JSON parse error: {e}")
    return records


def filter_success(records: list[dict]) -> list[dict]:
    return [r for r in records if r.get("status") == "success" and not r["trial"]["is_warmup"]]


def group_by(records: list[dict], keys: list[str]) -> dict:
    """Group records by tuple of field values."""
    groups = defaultdict(list)
    for r in records:
        key = tuple(r["build"]["gguf_variant"] if k == "gguf_variant"
                    else r["trial"][k] if k in r["trial"]
                    else r["metrics"].get(k)
                    for k in keys)
        groups[key].append(r)
    return dict(groups)


def extract_metric(records: list[dict], metric: str) -> list[float]:
    """Extract a metric from a list of records, filtering nulls."""
    vals = []
    for r in records:
        v = r["metrics"].get(metric) if metric in r.get("metrics", {}) else None
        if v is not None:
            vals.append(float(v))
    return vals


def extract_resource(records: list[dict], field: str) -> list[float]:
    vals = []
    for r in records:
        v = r.get("resources", {}).get(field)
        if v is not None:
            vals.append(float(v))
    return vals


def percentile(data: list[float], p: float) -> float:
    if not data:
        return float("nan")
    sorted_d = sorted(data)
    idx = (len(sorted_d) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_d) - 1)
    return sorted_d[lo] + (sorted_d[hi] - sorted_d[lo]) * (idx - lo)


def stats(data: list[float]) -> dict:
    if not data:
        return {"mean": None, "std": None, "p50": None, "p90": None, "p99": None, "n": 0}
    return {
        "mean": mean(data),
        "std": stdev(data) if len(data) > 1 else 0.0,
        "p50": percentile(data, 50),
        "p90": percentile(data, 90),
        "p99": percentile(data, 99),
        "n": len(data),
    }


# ---------------------------------------------------------------------------
# Figure helpers
# ---------------------------------------------------------------------------

def savefig(fig, name: str):
    FIGURES_DIR.mkdir(exist_ok=True)
    path = FIGURES_DIR / name
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"  Saved: {path}")


def apply_style():
    plt.rcParams.update(STYLE)


def annotate_oom(ax, text="OOM / not run"):
    ax.text(0.98, 0.02, text, transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="gray", style="italic")


# ---------------------------------------------------------------------------
# Figure 1: Prefill TPS vs Context Length
# ---------------------------------------------------------------------------

def fig1_prefill_tps_vs_context(records: list[dict]):
    apply_style()
    fig, ax = plt.subplots(figsize=(7, 4.5))

    grouped = group_by(records, ["gguf_variant", "context_length"])
    contexts_all = sorted(set(r["trial"]["context_length"] for r in records))

    for variant in QUANT_ORDER:
        xs, ys, errs = [], [], []
        for ctx in contexts_all:
            key = (variant, ctx)
            recs = grouped.get(key, [])
            vals = extract_metric(recs, "prefill_tps")
            if vals:
                s = stats(vals)
                xs.append(ctx)
                ys.append(s["mean"])
                errs.append(s["std"])
        if xs:
            color = QUANT_COLORS[variant]
            bits = QUANT_BITS.get(variant, "?")
            ax.errorbar(xs, ys, yerr=errs, marker="o", label=f"{variant} ({bits}-bit)",
                        color=color, capsize=4, linewidth=1.8)

    ax.set_xlabel("Context Length (tokens)")
    ax.set_ylabel("Prefill Throughput (tokens/sec)")
    ax.set_title("Prefill TPS vs Context Length\n(Llama 3.2 3B, Pixel 6a)")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.xaxis.set_major_locator(mticker.FixedLocator(contexts_all))
    fig.tight_layout()
    savefig(fig, "fig1_prefill_tps_vs_context.png")


# ---------------------------------------------------------------------------
# Figure 2: Decode TPS vs Context Length
# ---------------------------------------------------------------------------

def fig2_decode_tps_vs_context(records: list[dict]):
    apply_style()
    fig, ax = plt.subplots(figsize=(7, 4.5))

    grouped = group_by(records, ["gguf_variant", "context_length"])
    contexts_all = sorted(set(r["trial"]["context_length"] for r in records))

    for variant in QUANT_ORDER:
        xs, ys, errs = [], [], []
        for ctx in contexts_all:
            recs = grouped.get((variant, ctx), [])
            vals = extract_metric(recs, "decode_tps")
            if vals:
                s = stats(vals)
                xs.append(ctx)
                ys.append(s["mean"])
                errs.append(s["std"])
        if xs:
            color = QUANT_COLORS[variant]
            bits = QUANT_BITS.get(variant, "?")
            ax.errorbar(xs, ys, yerr=errs, marker="s", label=f"{variant} ({bits}-bit)",
                        color=color, capsize=4, linewidth=1.8)

    ax.set_xlabel("Context Length (tokens)")
    ax.set_ylabel("Decode Throughput (tokens/sec)")
    ax.set_title("Decode TPS vs Context Length\n(Llama 3.2 3B, Pixel 6a)")
    ax.legend(loc="upper right", fontsize=8)
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.xaxis.set_major_locator(mticker.FixedLocator(contexts_all))
    fig.tight_layout()
    savefig(fig, "fig2_decode_tps_vs_context.png")


# ---------------------------------------------------------------------------
# Figure 3: TTFT vs Context Length
# ---------------------------------------------------------------------------

def fig3_ttft_vs_context(records: list[dict]):
    apply_style()
    fig, ax = plt.subplots(figsize=(7, 4.5))

    grouped = group_by(records, ["gguf_variant", "context_length"])
    contexts_all = sorted(set(r["trial"]["context_length"] for r in records))

    for variant in QUANT_ORDER:
        xs, ys, errs = [], [], []
        for ctx in contexts_all:
            recs = grouped.get((variant, ctx), [])
            vals = extract_metric(recs, "ttft_s")
            if vals:
                s = stats(vals)
                xs.append(ctx)
                ys.append(s["mean"])
                errs.append(s["std"])
        if xs:
            ax.errorbar(xs, ys, yerr=errs, marker="^", label=f"{variant}",
                        color=QUANT_COLORS[variant], capsize=4, linewidth=1.8)

    ax.set_xlabel("Context Length (tokens)")
    ax.set_ylabel("Time to First Token (seconds)")
    ax.set_title("TTFT vs Context Length\n(Llama 3.2 3B, Pixel 6a)")
    ax.legend(fontsize=8)
    ax.set_xscale("log", base=2)
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.xaxis.set_major_locator(mticker.FixedLocator(contexts_all))
    fig.tight_layout()
    savefig(fig, "fig3_ttft_vs_context.png")


# ---------------------------------------------------------------------------
# Figure 4: Peak Memory vs Quant Level
# ---------------------------------------------------------------------------

def fig4_peak_memory_vs_quant(records: list[dict]):
    apply_style()
    # Only include records that have peak_rss_mb
    recs_with_mem = [r for r in records if r.get("resources", {}).get("peak_rss_mb") is not None]
    if not recs_with_mem:
        print("  NOTE: No peak_rss_mb data — skipping fig4 (run benchmark_runner.py for real data)")
        # Create placeholder figure
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No peak memory data collected yet.\nRun benchmark to populate.",
                ha="center", va="center", transform=ax.transAxes, fontsize=12, color="gray")
        ax.set_title("Peak RSS Memory vs Quantization Level")
        ax.axis("off")
        savefig(fig, "fig4_peak_memory_vs_quant.png")
        return

    grouped = group_by(recs_with_mem, ["gguf_variant", "context_length"])
    contexts_all = sorted(set(r["trial"]["context_length"] for r in recs_with_mem))
    variants = [v for v in QUANT_ORDER if any((v, c) in grouped for c in contexts_all)]

    x = np.arange(len(variants))
    width = 0.8 / len(contexts_all)

    fig, ax = plt.subplots(figsize=(8, 5))
    for i, ctx in enumerate(contexts_all):
        ys = []
        for v in variants:
            recs = grouped.get((v, ctx), [])
            vals = extract_resource(recs, "peak_rss_mb")
            ys.append(mean(vals) if vals else 0)
        offset = (i - len(contexts_all) / 2 + 0.5) * width
        ax.bar(x + offset, ys, width * 0.9, label=f"ctx={ctx}", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(variants, rotation=15)
    ax.set_xlabel("Quantization Variant")
    ax.set_ylabel("Peak RSS Memory (MB)")
    ax.set_title("Peak Memory Usage vs Quantization Level\n(Llama 3.2 3B, Pixel 6a)")
    ax.axhline(y=6144, color="red", linestyle="--", alpha=0.6, label="Device RAM (6GB)")
    ax.legend(fontsize=8)
    fig.tight_layout()
    savefig(fig, "fig4_peak_memory_vs_quant.png")


# ---------------------------------------------------------------------------
# Figure 5: Battery Drain per 1K Tokens
# ---------------------------------------------------------------------------

def fig5_battery_per_1k_tokens(records: list[dict]):
    """
    Battery energy proxy figure.

    Measurement context: experiments were run over USB ADB (WiFi) with the device
    plugged in during the full sweep (~35,000 output tokens across all variants).
    Android's dumpsys battery reports integer %, so per-trial (≈30s) resolution is
    too coarse to attribute < 1% drops per variant reliably.

    We show three pieces of honest information:
      1. Session-level drain estimate: 78% → 2%  ≈ 76% over ~35k tokens
         → ≈ 2.2 % battery per 1K tokens (global proxy, not broken out by variant)
      2. A bar chart of decode throughput normalised by model size (GB) as a
         model-size-adjusted efficiency proxy — a well-defined quantity from our data.
      3. A text annotation explaining the battery measurement limitation.
    """
    apply_style()

    # ── efficiency proxy: decode TPS / model size (GB) ─────────────────────
    grouped = group_by(records, ["gguf_variant"])
    variants = [v for v in QUANT_ORDER if (v,) in grouped]

    proxy_vals = []
    for v in variants:
        tps_list = extract_metric(grouped[(v,)], "decode_tps")
        size_gb   = MODEL_SIZE_GB.get(v, 1.0)
        if tps_list:
            proxy_vals.append(mean(tps_list) / size_gb)
        else:
            proxy_vals.append(0.0)

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5),
                             gridspec_kw={"width_ratios": [3, 2]})

    # Left panel: TPS / GB bar chart
    ax = axes[0]
    colors = [QUANT_COLORS.get(v, "#888888") for v in variants]
    xs = list(range(len(variants)))
    bars = ax.bar(xs, proxy_vals, color=colors, alpha=0.85, edgecolor="white", width=0.65)
    ax.set_xticks(xs)
    ax.set_xticklabels(variants, rotation=15, fontsize=9)
    ax.set_xlabel("Quantization Variant")
    ax.set_ylabel("Decode Throughput / Model Size\n(tokens/s per GB)", fontsize=9)
    ax.set_title("Size-Adjusted Throughput Efficiency\n(proxy for compute-per-byte)", fontsize=10)
    for bar, val in zip(bars, proxy_vals):
        if val > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=8)

    # Right panel: battery methodology note
    ax2 = axes[1]
    ax2.axis("off")
    note = (
        "Battery Measurement — Limitation Note\n"
        "─────────────────────────────────────\n\n"
        "Session drain observed:\n"
        "  78% → 2%  ≈  76% total\n"
        "  over ~35,000 output tokens\n"
        "  ≈  2.2 % / 1K tokens  (global proxy)\n\n"
        "Per-trial isolation not feasible:\n"
        "  • Android reports battery as integer %\n"
        "  • Each trial lasts ≈ 20–35 s — too\n"
        "    short to consume a full 1% reliably\n"
        "  • USB charging offsets real-time draw\n\n"
        "A dedicated battery sweep (WiFi ADB,\n"
        "device unplugged) is planned to provide\n"
        "per-variant energy figures."
    )
    ax2.text(0.05, 0.95, note, transform=ax2.transAxes,
             va="top", ha="left", fontsize=8.5,
             fontfamily="monospace",
             bbox=dict(boxstyle="round,pad=0.6", facecolor="#f5f5f5",
                       edgecolor="#cccccc", alpha=0.9))

    fig.suptitle("Energy Efficiency: Size-Adjusted Throughput & Battery Note\n"
                 "(Llama 3.2 3B Instruct, Pixel 6a Tensor G1)", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    savefig(fig, "fig5_battery_per_1k_tokens.png")


# ---------------------------------------------------------------------------
# Figure 6: Efficiency–Accuracy Pareto Frontier
# ---------------------------------------------------------------------------

def fig6_pareto_frontier(records: list[dict]):
    """Scatter of decode TPS vs quality score per variant, with Pareto annotation."""
    apply_style()
    # Quality proxy: placeholder until perplexity data is collected
    # Once available, read from results or a separate quality_scores.json

    quality_scores_file = PROJECT_ROOT / "results" / "quality_scores.json"
    has_quality = quality_scores_file.exists()

    grouped = group_by(records, ["gguf_variant"])
    variants = [v for v in QUANT_ORDER if (v,) in grouped]

    # Decode TPS per variant (mean across all contexts)
    tps_by_variant = {}
    for v in variants:
        vals = extract_metric(grouped[(v,)], "decode_tps")
        if vals:
            tps_by_variant[v] = mean(vals)

    quality_by_variant = {}
    if has_quality:
        with open(quality_scores_file) as f:
            quality_by_variant = json.load(f)

    if not tps_by_variant:
        fig, ax = plt.subplots(figsize=(6, 3))
        ax.text(0.5, 0.5, "No decode TPS data yet.\nRun benchmark to populate.",
                ha="center", va="center", transform=ax.transAxes, fontsize=12, color="gray")
        ax.axis("off")
        savefig(fig, "fig6_pareto_efficiency_quality.png")
        return

    fig, ax = plt.subplots(figsize=(7, 5))

    # Collect valid (non-confounded) quality data points for Pareto line
    valid_points = []  # (tps, q) for Pareto computation

    for v, tps in tps_by_variant.items():
        # Prefer BoolQ scores (standard 100-question benchmark) over legacy custom QA
        raw_q = quality_by_variant.get(f"boolq:{v}", quality_by_variant.get(v, None))
        # quality_scores.json values may be nested dicts {accuracy_pct, per_question, ...}
        # or plain scalars — normalise to a float or None
        q = None
        is_confounded = False
        if isinstance(raw_q, dict):
            # Check if evaluation was confounded by ADB timeouts
            per_question = raw_q.get("per_question", [])
            timeout_count = sum(1 for pq in per_question if pq.get("status") == "timeout")
            total_count = len(per_question)
            # Mark as confounded if majority of questions timed out (ADB dropout)
            if total_count > 0 and timeout_count / total_count > 0.3:
                is_confounded = True
            else:
                acc = raw_q.get("accuracy_pct")
                if acc is not None:
                    q = float(acc)
        elif raw_q is not None:
            try:
                q = float(raw_q)
            except (TypeError, ValueError):
                q = None

        color = QUANT_COLORS.get(v, "#888")
        bits = QUANT_BITS.get(v, "?")
        size_gb = MODEL_SIZE_GB.get(v, 0)

        if q is not None:
            ax.scatter(tps, q, s=size_gb * 80, color=color, zorder=5,
                       label=f"{v} ({bits}-bit, {size_gb:.1f} GB)")
            ax.annotate(v, (tps, q), xytext=(6, 4), textcoords="offset points",
                        fontsize=9, fontweight="bold")
            valid_points.append((tps, q, v))
        else:
            # No valid quality data — show TPS-only dashed line
            label_suffix = " (ADB timeout)" if is_confounded else " (quality N/A)"
            ax.axvline(tps, color=color, linestyle="--", alpha=0.45, linewidth=1.0,
                       label=f"{v} {label_suffix}")

    # ── Iso-efficiency lines (TPS × accuracy/100 = constant) ─────────────
    # These hyperbolas show "equal utility" contours; points on the same curve
    # are equivalently useful under a linear TPS × accuracy objective.
    if valid_points:
        all_tps    = [p[0] for p in valid_points]
        tps_min    = max(0.5, min(all_tps) * 0.7)
        tps_max    = max(all_tps) * 1.15
        tps_range  = np.linspace(tps_min, tps_max, 300)

        # Choose iso-lines at the 25th, 50th and 75th percentile of TPS×acc products
        products = sorted([p[0] * p[1] for p in valid_points])
        def pick_levels(prods):
            n = len(prods)
            if n == 0:
                return []
            candidates = set()
            for frac in [0.25, 0.5, 0.75, 1.0]:
                candidates.add(prods[min(int(frac * (n - 1)), n - 1)])
            # round to nearest 5 for readability
            return sorted({round(c / 5) * 5 for c in candidates if c > 0})

        iso_levels = pick_levels(products)
        # Also always include the maximum product for reference
        if products:
            iso_levels = sorted(set(iso_levels + [round(products[-1] / 5) * 5]))

        iso_plotted = False
        for iso_val in iso_levels:
            # quality = iso_val / tps  (in %)
            iso_q = iso_val / tps_range
            # only plot where quality is in the visible range [70, 105]
            mask = (iso_q >= 72) & (iso_q <= 103)
            if mask.sum() > 2:
                alpha = 0.18 if iso_val != iso_levels[-1] else 0.28
                lw    = 0.8  if iso_val != iso_levels[-1] else 1.1
                label = "Iso-efficiency" if not iso_plotted else None
                ax.plot(tps_range[mask], iso_q[mask], color="#888888",
                        linestyle=":", linewidth=lw, alpha=alpha,
                        zorder=1, label=label)
                # Label the curve at the right edge
                last_i = np.where(mask)[0][-1]
                ax.text(tps_range[last_i] * 1.005, iso_q[last_i],
                        f"E={iso_val}", fontsize=7, color="#aaaaaa",
                        va="center", ha="left")
                iso_plotted = True

    # ── Pareto frontier line through non-dominated points ──────────────────
    if len(valid_points) >= 2:
        valid_points_sorted = sorted(valid_points, key=lambda x: x[0])
        pareto = []
        max_q_so_far = -1
        for pt in reversed(valid_points_sorted):  # high TPS → low TPS
            if pt[1] > max_q_so_far:
                pareto.append(pt)
                max_q_so_far = pt[1]
        pareto.sort(key=lambda x: x[0])
        if len(pareto) >= 2:
            px = [p[0] for p in pareto]
            py = [p[1] for p in pareto]
            ax.plot(px, py, "k--", linewidth=1.5, alpha=0.65,
                    label="Pareto frontier", zorder=4)
        # Shade dominated region (grey fill below-left of Pareto frontier)
        if len(pareto) >= 2:
            fill_x = [tps_min if 'tps_min' in dir() else px[0]] + px + [px[-1], px[0]]
            fill_y = [py[0], *py, 70, 70]
            ax.fill(fill_x, fill_y, color="#dddddd", alpha=0.18, zorder=0,
                    label="Dominated region")

    ax.set_xlabel("Decode Throughput (tokens/sec)", fontsize=11)
    ax.set_ylabel("Factual Accuracy (%, 15-question suite)", fontsize=11)
    ax.set_title("Efficiency–Accuracy Trade-off\n(Llama 3.2 3B Instruct, Pixel 6a Tensor G1)", fontsize=11)
    ax.set_ylim(70, 105)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.0f%%"))
    if quality_by_variant:
        ax.legend(fontsize=8, loc="lower right")
    else:
        ax.text(0.5, 0.5, "(Quality scores pending — add results/quality_scores.json)",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=9, color="gray", alpha=0.7)
    fig.tight_layout()
    savefig(fig, "fig6_pareto_efficiency_quality.png")


# ---------------------------------------------------------------------------
# Figure 7: Prefill vs Decode Time Fraction (stacked bar)
# ---------------------------------------------------------------------------

def fig7_prefill_vs_decode_fraction(records: list[dict]):
    apply_style()
    grouped = group_by(records, ["gguf_variant", "context_length"])
    contexts_all = sorted(set(r["trial"]["context_length"] for r in records))

    # Use one representative context for the stacked bar
    ctx = contexts_all[len(contexts_all) // 2]
    variants = [v for v in QUANT_ORDER if (v, ctx) in grouped]

    prefill_fracs = []
    gen_fracs = []
    for v in variants:
        recs = grouped.get((v, ctx), [])
        pf = extract_metric(recs, "prefill_frac")
        gf = extract_metric(recs, "gen_frac")
        prefill_fracs.append(mean(pf) if pf else 0)
        gen_fracs.append(mean(gf) if gf else 0)

    x = np.arange(len(variants))
    fig, ax = plt.subplots(figsize=(7, 4.5))
    p1 = ax.bar(x, prefill_fracs, label="Prefill fraction", color="#2196F3", alpha=0.85)
    p2 = ax.bar(x, gen_fracs, bottom=prefill_fracs, label="Generation fraction", color="#FF9800", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(variants, rotation=15)
    ax.set_ylim(0, 1.1)
    ax.set_xlabel("Quantization Variant")
    ax.set_ylabel("Fraction of Total Time")
    ax.set_title(f"Prefill vs Generation Time Split\n(Llama 3.2 3B, ctx={ctx}, Pixel 6a)")
    ax.legend(fontsize=9)
    fig.tight_layout()
    savefig(fig, "fig7_prefill_vs_decode_fraction.png")


# ---------------------------------------------------------------------------
# Figure 8: Latency Distribution (box plot)
# ---------------------------------------------------------------------------

def fig8_latency_distribution(records: list[dict]):
    apply_style()
    grouped = group_by(records, ["gguf_variant"])
    variants = [v for v in QUANT_ORDER if (v,) in grouped]

    data = []
    labels = []
    colors = []
    for v in variants:
        vals = extract_metric(grouped[(v,)], "e2e_s")
        if vals:
            data.append(vals)
            bits = QUANT_BITS.get(v, "?")
            labels.append(f"{v}\n({bits}-bit)")
            colors.append(QUANT_COLORS.get(v, "#888"))

    if not data:
        return

    fig, ax = plt.subplots(figsize=(8, 5))
    bp = ax.boxplot(data, tick_labels=labels, patch_artist=True, notch=False,
                    medianprops=dict(color="black", linewidth=2))
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.set_xlabel("Quantization Variant")
    ax.set_ylabel("End-to-End Latency (seconds)")
    ax.set_title("E2E Latency Distribution by Quantization\n(Llama 3.2 3B, Pixel 6a, 128 output tokens)")
    fig.tight_layout()
    savefig(fig, "fig8_latency_distribution.png")


# ---------------------------------------------------------------------------
# Figure 9: Model Size vs Decode TPS
# ---------------------------------------------------------------------------

def fig9_model_size_vs_tps(records: list[dict]):
    apply_style()
    grouped = group_by(records, ["gguf_variant"])
    variants = [v for v in QUANT_ORDER if (v,) in grouped]

    xs, ys, labels, colors = [], [], [], []
    for v in variants:
        vals = extract_metric(grouped[(v,)], "decode_tps")
        size = MODEL_SIZE_GB.get(v)
        if vals and size:
            xs.append(size)
            ys.append(mean(vals))
            labels.append(v)
            colors.append(QUANT_COLORS.get(v, "#888"))

    if not xs:
        return

    fig, ax = plt.subplots(figsize=(7, 4.5))
    scatter = ax.scatter(xs, ys, c=colors, s=200, zorder=5, edgecolors="white", linewidths=1.5)

    for x, y, label in zip(xs, ys, labels):
        ax.annotate(label, (x, y), xytext=(8, 4), textcoords="offset points", fontsize=9)

    # Fit and plot a curve to show diminishing returns
    if len(xs) >= 3:
        z = np.polyfit(xs, ys, 2)
        p = np.poly1d(z)
        x_smooth = np.linspace(min(xs) * 0.9, max(xs) * 1.1, 100)
        ax.plot(x_smooth, p(x_smooth), "k--", alpha=0.3, linewidth=1.2, label="trend")

    ax.set_xlabel("Model File Size (GB)")
    ax.set_ylabel("Decode Throughput (tokens/sec)")
    ax.set_title("Model Size vs Decode Throughput\n(Llama 3.2 3B, Pixel 6a)")
    ax.invert_xaxis()  # smaller = better compression on left
    ax.set_xlabel("Model File Size (GB) ← smaller (more compressed)")
    fig.tight_layout()
    savefig(fig, "fig9_model_size_vs_decode_tps.png")


# ---------------------------------------------------------------------------
# Summary table (CSV)
# ---------------------------------------------------------------------------

def generate_summary_table(records: list[dict]):
    import csv

    grouped = group_by(records, ["gguf_variant", "context_length"])
    contexts_all = sorted(set(r["trial"]["context_length"] for r in records))
    variants = [v for v in QUANT_ORDER if any((v, c) in grouped for c in contexts_all)]

    rows = []
    for v in variants:
        bits = QUANT_BITS.get(v, "?")
        size = MODEL_SIZE_GB.get(v, "?")
        for ctx in contexts_all:
            recs = grouped.get((v, ctx), [])
            if not recs:
                continue

            decode_vals = extract_metric(recs, "decode_tps")
            prefill_vals = extract_metric(recs, "prefill_tps")
            ttft_vals = extract_metric(recs, "ttft_s")
            e2e_vals = extract_metric(recs, "e2e_s")
            mem_vals = extract_resource(recs, "peak_rss_mb")

            def fmt(x):
                return f"{x:.2f}" if x is not None else "N/A"

            decode_s = stats(decode_vals)
            rows.append({
                "variant": v,
                "quant_bits": bits,
                "model_size_gb": size,
                "context_length": ctx,
                "decode_tps_mean": fmt(decode_s["mean"]),
                "decode_tps_p50": fmt(decode_s["p50"]),
                "decode_tps_p90": fmt(decode_s["p90"]),
                "decode_tps_std": fmt(decode_s["std"]),
                "prefill_tps_mean": fmt(stats(prefill_vals)["mean"]),
                "ttft_mean_s": fmt(stats(ttft_vals)["mean"]),
                "e2e_mean_s": fmt(stats(e2e_vals)["mean"]),
                "peak_rss_mb_mean": fmt(stats(mem_vals)["mean"]) if mem_vals else "N/A",
                "n_trials": decode_s["n"],
            })

    FIGURES_DIR.mkdir(exist_ok=True)
    out_path = FIGURES_DIR / "summary_table.csv"
    if rows:
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"  Saved: {out_path}  ({len(rows)} rows)")
    else:
        print("  NOTE: No data for summary table yet.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(f"Usage: python {sys.argv[0]} <results_dir_or_jsonl_file...>")
        sys.exit(1)

    # Collect input paths
    jsonl_paths = []
    for arg in sys.argv[1:]:
        p = Path(arg)
        if p.is_dir():
            jsonl_paths.extend(sorted(p.glob("*.jsonl")))
        elif p.suffix == ".jsonl" and p.exists():
            jsonl_paths.append(p)
        else:
            print(f"WARNING: Skipping '{arg}' (not a .jsonl file or directory)")

    if not jsonl_paths:
        print("ERROR: No .jsonl files found.")
        sys.exit(1)

    print(f"Loading {len(jsonl_paths)} JSONL file(s)...")
    all_records = load_jsonl_files(jsonl_paths)
    print(f"  Total records: {len(all_records)}")

    success_records = filter_success(all_records)
    failed_records = [r for r in all_records if r.get("status") != "success"]
    print(f"  Success (non-warmup): {len(success_records)}")
    print(f"  Failed/OOM: {len(failed_records)}")

    if failed_records:
        failure_summary = defaultdict(int)
        for r in failed_records:
            code = r.get("failure", {}).get("code", "unknown") if r.get("failure") else r.get("status", "unknown")
            variant = r.get("build", {}).get("gguf_variant", "unknown")
            failure_summary[f"{variant}:{code}"] += 1
        print("  Failures:")
        for k, v in sorted(failure_summary.items()):
            print(f"    {k}: {v}")

    if not success_records:
        print("\nNo successful records to plot.")
        print("Run benchmarks first: python scripts/benchmark_runner.py --smoke")
        # Still generate placeholder figures
        for fn in [fig4_peak_memory_vs_quant, fig5_battery_per_1k_tokens, fig6_pareto_frontier]:
            try:
                fn([])
            except Exception:
                pass
        sys.exit(0)

    print(f"\nGenerating figures in {FIGURES_DIR}/")
    plt.rcParams.update(STYLE)

    fns = [
        ("fig1", fig1_prefill_tps_vs_context),
        ("fig2", fig2_decode_tps_vs_context),
        ("fig3", fig3_ttft_vs_context),
        ("fig4", fig4_peak_memory_vs_quant),
        ("fig5", fig5_battery_per_1k_tokens),
        ("fig6", fig6_pareto_frontier),
        ("fig7", fig7_prefill_vs_decode_fraction),
        ("fig8", fig8_latency_distribution),
        ("fig9", fig9_model_size_vs_tps),
    ]

    for label, fn in fns:
        try:
            fn(success_records)
        except Exception as e:
            print(f"  WARNING: {label} failed: {e}")

    generate_summary_table(success_records)

    print(f"\nDone. Open figures/ to review.")


if __name__ == "__main__":
    main()
