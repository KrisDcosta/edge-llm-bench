#!/usr/bin/env python3
"""
generate_tables.py  —  Generate LaTeX tables for the GGUF quantization paper.

Reads verified benchmark data from results/ and outputs publication-ready
LaTeX table code to report/tables_generated.tex.

Usage:
    python3 scripts/analyze/generate_tables.py
    python3 scripts/analyze/generate_tables.py --stdout   # print only, no file
"""

import json
import os
import sys
import statistics
import glob
from collections import defaultdict
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_FILE  = PROJECT_ROOT / "report" / "tables_generated.tex"

# ── Verified hard-coded data ───────────────────────────────────────────────
VARIANTS  = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
VARIANT_DISPLAY = {
    "Q2_K":   r"\texttt{Q2\_K}",
    "Q3_K_M": r"\texttt{Q3\_K\_M}",
    "Q4_K_S": r"\texttt{Q4\_K\_S}",
    "Q4_K_M": r"\texttt{Q4\_K\_M}",
    "Q5_K_M": r"\texttt{Q5\_K\_M}",
    "Q6_K":   r"\texttt{Q6\_K}",
    "Q8_0":   r"\texttt{Q8\_0}",
}
RECOMMENDED = "Q4_K_M"

MODEL_SIZES_GB = {
    "Q2_K":   1.36, "Q3_K_M": 1.69, "Q4_K_S": 1.93,
    "Q4_K_M": 2.02, "Q5_K_M": 2.32, "Q6_K":   2.64, "Q8_0":   3.42,
}
BITS_PER_WEIGHT = {
    # Computed as: file_bytes * 8 / 3.21e9 params
    "Q2_K":   3.40, "Q3_K_M": 4.20, "Q4_K_S": 4.81,
    "Q4_K_M": 5.03, "Q5_K_M": 5.79, "Q6_K":   6.59, "Q8_0":   8.53,
}

PPL_MEAN = {
    "Q2_K":   13.29, "Q3_K_M": 11.08, "Q4_K_S": 10.70,
    "Q4_K_M": 10.71, "Q5_K_M": 10.62, "Q6_K":   10.58, "Q8_0":   10.59,
}
PPL_STD = {
    "Q2_K":   0.10,  "Q3_K_M": 0.08,  "Q4_K_S": 0.08,
    "Q4_K_M": 0.08,  "Q5_K_M": 0.08,  "Q6_K":   0.08,  "Q8_0":   0.08,
}

# M4 cliff data (decode TPS from verified runs, ctx=1024 and ctx=2048)
M4_CLIFF = {
    "Q2_K":   {"ctx1024": 22.0, "ctx2048": 22.3, "cliff_ctx": None,   "drop_pct": 0},
    "Q4_K_M": {"ctx1024": 19.3, "ctx2048": 17.1, "cliff_ctx": None,   "drop_pct": 11},
    "Q6_K":   {"ctx1024": 13.0, "ctx2048":  7.3, "cliff_ctx": 1500,   "drop_pct": 42},
    "Q8_0":   {"ctx1024":  6.4, "ctx2048": 12.9, "cliff_ctx": None,   "drop_pct": 0},
}


def bold(s, condition=True):
    return rf"\textbf{{{s}}}" if condition else s


def fmt_tps(mean, std):
    return rf"{mean:.2f}{{\tiny$\pm${std:.2f}}}"


# ── Load Pixel TPS from JSONL ──────────────────────────────────────────────
def load_pixel_tps():
    tps_dir = PROJECT_ROOT / "results" / "pixel_llama_tps_20260325_120022"
    data    = defaultdict(lambda: defaultdict(list))
    for f in sorted(tps_dir.glob("tps_*.jsonl")):
        for line in f.open():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                if float(d.get("decode_tps", 0)) > 0:
                    data[d["variant"]][d["context"]].append(float(d["decode_tps"]))
            except Exception:
                pass
    result = {}
    for v in VARIANTS:
        result[v] = {}
        for c in [256, 512, 1024, 2048]:
            vals = data[v].get(c, [])
            if vals:
                result[v][c] = (statistics.mean(vals),
                                statistics.stdev(vals) if len(vals) > 1 else 0.0)
    return result


# ── Load M4 TPS from llama-bench JSONL ────────────────────────────────────
def load_m4_tps():
    """Returns {variant: {"pp": {n_prompt: (mean,std)}, "tg": (mean,std)}}"""
    tps_dir = PROJECT_ROOT / "results" / "m4_llama_tps_20260326_001546"
    if not tps_dir.exists():
        return {}
    data = {}
    for f in sorted(tps_dir.glob("tps_*.jsonl")):
        try:
            records = [json.loads(l) for l in f.open() if l.strip()]
        except Exception:
            continue
        pp = {}
        tg = None
        for r in records:
            if r.get("test_type") == "pp":
                pp[r["n_prompt"]] = (r["tps_mean"], r["tps_std"])
            elif r.get("test_type") == "tg":
                tg = (r["tps_mean"], r["tps_std"])
        variant = f.stem.replace("tps_", "")
        data[variant] = {"pp": pp, "tg": tg}
    return data


# ── Load quality scores ────────────────────────────────────────────────────
def load_quality():
    qf = PROJECT_ROOT / "results" / "quality_scores.json"
    if not qf.exists():
        return {}
    return json.loads(qf.read_text())


# ── Table 1: Quantization Overview ────────────────────────────────────────
def table_quantization_overview():
    baseline_ppl  = PPL_MEAN["Q8_0"]
    baseline_size = MODEL_SIZES_GB["Q8_0"]
    lines = []
    lines.append(r"% ── Table 1: Quantization Overview ──────────────────────────────────")
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\caption{GGUF K-quantization variants for Llama~3.2~3B. "
                 r"PPL measured on WikiText-2 full corpus (ctx=512). "
                 r"\textbf{Q4\_K\_M} is our recommended variant.}")
    lines.append(r"\label{tab:quant_overview}")
    lines.append(r"\begin{tabular}{lccccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Variant} & \textbf{Bits/W} & \textbf{Size (GB)} "
                 r"& \textbf{Size ratio} & \textbf{PPL} & \textbf{$\Delta$PPL} \\")
    lines.append(r"\midrule")
    for v in VARIANTS:
        bpw   = BITS_PER_WEIGHT[v]
        sz    = MODEL_SIZES_GB[v]
        ratio = sz / baseline_size
        ppl   = PPL_MEAN[v]
        std   = PPL_STD[v]
        dppl  = ppl - baseline_ppl
        dppl_s = rf"+{dppl:.2f}" if dppl >= 0 else f"{dppl:.2f}"
        is_rec = (v == RECOMMENDED)
        vname  = bold(VARIANT_DISPLAY[v], is_rec)
        row = (rf"{vname} & {bold(f'{bpw:.1f}', is_rec)} & "
               rf"{bold(f'{sz:.2f}', is_rec)} & "
               rf"{bold(f'{ratio:.2f}$\\times$', is_rec)} & "
               rf"{bold(f'{ppl:.2f}$\\pm${std:.2f}', is_rec)} & "
               rf"{bold(dppl_s, is_rec)} \\")
        lines.append(row)
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Table 2: Pixel 6a Decode TPS ──────────────────────────────────────────
def table_pixel_tps(pixel_tps):
    ctxs = [256, 512, 1024, 2048]
    # Find best (highest) TPS per context
    best = {}
    for c in ctxs:
        vals = [(v, pixel_tps[v][c][0]) for v in VARIANTS if c in pixel_tps.get(v, {})]
        if vals:
            best[c] = max(vals, key=lambda x: x[1])[0]

    lines = []
    lines.append(r"% ── Table 2: Pixel 6a Decode TPS ────────────────────────────────────")
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\caption{Decode throughput (tokens/s, mean$\pm$std) on Pixel~6a, "
                 r"Llama~3.2~3B, 4-thread CPU inference. "
                 r"10 trials per configuration. \textbf{Bold}: highest per column.}")
    lines.append(r"\label{tab:pixel_tps}")
    lines.append(r"\begin{tabular}{lcccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Variant} & "
                 r"\textbf{ctx=256} & \textbf{ctx=512} & "
                 r"\textbf{ctx=1024} & \textbf{ctx=2048} \\")
    lines.append(r"\midrule")
    for v in VARIANTS:
        is_rec = (v == RECOMMENDED)
        vname  = bold(VARIANT_DISPLAY[v], is_rec)
        cells  = [vname]
        for c in ctxs:
            if c in pixel_tps.get(v, {}):
                mean, std = pixel_tps[v][c]
                cell = fmt_tps(mean, std)
                if best.get(c) == v:
                    cell = bold(cell)
            else:
                cell = "—"
            cells.append(cell)
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Table 3: KV-Cache Cliff ────────────────────────────────────────────────
def table_cliff(pixel_tps):
    lines = []
    lines.append(r"% ── Table 3: KV-Cache Cliff Summary ─────────────────────────────────")
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\caption{KV-cache throughput cliff summary. "
                 r"Drop\,(\%) = relative decode TPS decrease from ctx=1024 to ctx=2048. "
                 r"Cliff\,ctx: context at which $>$10\% single-step drop occurs.}")
    lines.append(r"\label{tab:kv_cliff}")
    lines.append(r"\begin{tabular}{llcccl}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Variant} & \textbf{Device} & "
                 r"\textbf{TPS@1024} & \textbf{TPS@2048} & "
                 r"\textbf{Drop\,(\%)} & \textbf{Cliff\,ctx} \\")
    lines.append(r"\midrule")

    # M4 rows (verified data)
    for v in ["Q2_K", "Q4_K_M", "Q6_K", "Q8_0"]:
        if v not in M4_CLIFF:
            continue
        d      = M4_CLIFF[v]
        cliff  = str(d["cliff_ctx"]) if d["cliff_ctx"] else "—"
        drop   = f'{d["drop_pct"]:.0f}' if d["drop_pct"] > 0 else "—"
        is_cliff = d["cliff_ctx"] is not None
        t1024_s = f"{d['ctx1024']:.1f}"
        t2048_s = f"{d['ctx2048']:.1f}"
        row = (rf"{bold(VARIANT_DISPLAY[v], is_cliff)} & M4~Mac (Metal) & "
               rf"{bold(t1024_s, is_cliff)} & "
               rf"{bold(t2048_s, is_cliff)} & "
               rf"{bold(drop, is_cliff)} & "
               rf"{bold(cliff, is_cliff)} \\")
        lines.append(row)

    lines.append(r"\midrule")

    # Pixel rows
    for v in VARIANTS:
        vd = pixel_tps.get(v, {})
        if 1024 not in vd or 2048 not in vd:
            continue
        t1024 = vd[1024][0]
        t2048 = vd[2048][0]
        drop  = (t1024 - t2048) / t1024 * 100
        drop_s = f"{drop:.0f}" if drop > 5 else "—"
        row = (rf"{VARIANT_DISPLAY[v]} & Pixel~6a (CPU) & "
               rf"{t1024:.2f} & {t2048:.2f} & {drop_s} & — \\")
        lines.append(row)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Table 4: Quality Benchmarks ───────────────────────────────────────────
def table_quality(quality):
    benchmarks = ["arc_easy_fixed", "arc_challenge", "hellaswag", "mmlu", "boolq"]
    bench_labels = {
        "arc_easy_fixed": "ARC-Easy",
        "arc_challenge":  "ARC-Chall.",
        "hellaswag":      "HellaSwag",
        "mmlu":           "MMLU",
        "boolq":          "BoolQ",
    }

    # Build score table
    scores: dict[str, dict[str, float]] = defaultdict(dict)
    for key, val in quality.items():
        if ":" in key:
            bench, var = key.split(":", 1)
            if bench in benchmarks and var in VARIANTS:
                acc = val.get("accuracy_pct") or val.get("accuracy", 0)
                if acc:
                    scores[bench][var] = float(acc)

    # Find best per benchmark
    best_per_bench = {}
    for b in benchmarks:
        if scores[b]:
            best_per_bench[b] = max(scores[b].items(), key=lambda x: x[1])[0]

    lines = []
    lines.append(r"% ── Table 4: Quality Benchmarks ─────────────────────────────────────")
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\caption{Accuracy (\%) on quality benchmarks, Llama~3.2~3B, "
                 r"Pixel~6a CPU, 100 questions per benchmark. "
                 r"\textbf{Bold}: highest per benchmark. "
                 r"``—'': evaluation pending.}")
    lines.append(r"\label{tab:quality}")
    lines.append(r"\begin{tabular}{l" + "c" * len(benchmarks) + "}")
    lines.append(r"\toprule")
    header = r"\textbf{Variant} & " + " & ".join(
        rf"\textbf{{{bench_labels[b]}}}" for b in benchmarks
    ) + r" \\"
    lines.append(header)
    lines.append(r"\midrule")
    for v in VARIANTS:
        is_rec = (v == RECOMMENDED)
        cells  = [bold(VARIANT_DISPLAY[v], is_rec)]
        for b in benchmarks:
            if v in scores.get(b, {}):
                acc  = scores[b][v]
                cell = f"{acc:.1f}"
                if best_per_bench.get(b) == v:
                    cell = bold(cell)
            else:
                cell = "—"
            cells.append(cell)
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Table 5: Cross-Device Decode TPS (Pixel vs M4) ────────────────────────
def table_cross_device_tps(pixel_tps, m4_tps):
    """Side-by-side Pixel 6a vs M4 Mac decode TPS at ctx=1024."""
    ctx = 1024
    lines = []
    lines.append(r"% ── Table 5: Cross-Device Decode TPS ────────────────────────────────")
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(r"\small")
    lines.append(r"\caption{Decode throughput comparison: Pixel~6a CPU vs.\  M4~Mac (Metal), "
                 r"Llama~3.2~3B, ctx=1024. "
                 r"Speedup = M4 TPS / Pixel TPS. "
                 r"\textbf{Q4\_K\_M} is recommended variant.}")
    lines.append(r"\label{tab:cross_device_tps}")
    lines.append(r"\begin{tabular}{lcccc}")
    lines.append(r"\toprule")
    lines.append(r"\textbf{Variant} & \textbf{Pixel~6a (t/s)} & "
                 r"\textbf{M4~Metal (t/s)} & \textbf{Speedup} & \textbf{Size (GB)} \\")
    lines.append(r"\midrule")

    for v in VARIANTS:
        is_rec = (v == RECOMMENDED)
        vname  = bold(VARIANT_DISPLAY[v], is_rec)
        # Pixel decode at ctx=1024
        if ctx in pixel_tps.get(v, {}):
            p_mean, p_std = pixel_tps[v][ctx]
            pixel_cell = fmt_tps(p_mean, p_std)
        else:
            p_mean = None
            pixel_cell = "—"
        # M4 decode (TG from empty context, pre-aggregated)
        m4_entry = m4_tps.get(v, {})
        if m4_entry.get("tg") is not None:
            m4_mean, m4_std = m4_entry["tg"]
            m4_cell = fmt_tps(m4_mean, m4_std)
        else:
            m4_mean = None
            m4_cell = "—"
        # Speedup
        if p_mean and m4_mean and p_mean > 0:
            speedup = m4_mean / p_mean
            speedup_cell = bold(rf"{speedup:.1f}$\times$", is_rec)
        else:
            speedup_cell = "—"
        sz = MODEL_SIZES_GB[v]
        row = rf"{vname} & {bold(pixel_cell, is_rec)} & {bold(m4_cell, is_rec)} & {speedup_cell} & {sz:.2f} \\"
        lines.append(row)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────
def main():
    os.chdir(PROJECT_ROOT)

    print("Loading data...")
    pixel_tps = load_pixel_tps()
    m4_tps    = load_m4_tps()
    quality   = load_quality()

    tables = [
        ("Quantization Overview",     table_quantization_overview()),
        ("Pixel 6a Decode TPS",       table_pixel_tps(pixel_tps)),
        ("KV-Cache Cliff Summary",    table_cliff(pixel_tps)),
        ("Quality Benchmarks",        table_quality(quality)),
        ("Cross-Device Decode TPS",   table_cross_device_tps(pixel_tps, m4_tps)),
    ]

    output_parts = [
        "% ================================================================",
        "% Auto-generated LaTeX tables for GGUF quantization paper",
        f"% Generated by: scripts/analyze/generate_tables.py",
        "% Requires: \\usepackage{booktabs}",
        "% ================================================================",
        "",
    ]
    for name, tex in tables:
        output_parts.append(f"% {'─'*66}")
        output_parts.append(f"% Table: {name}")
        output_parts.append(f"% {'─'*66}")
        output_parts.append(tex)
        output_parts.append("")

    full_output = "\n".join(output_parts)

    stdout_only = "--stdout" in sys.argv
    if not stdout_only:
        output_path = PROJECT_ROOT / "report" / "tables_generated.tex"
        output_path.write_text(full_output)
        print(f"✅ Written: {output_path}")

    print(full_output)


if __name__ == "__main__":
    main()
