<<<<<<< HEAD
#!/usr/bin/env python3
"""
bake_dashboard_data.py
----------------------
Reads cleaned Parquet files from dataset/ and writes pre-aggregated JSON
files to dashboard/data/ for the static GitHub Pages dashboard.

Output files
────────────
  tps_by_variant.json    → Chart 1: throughput bar (device × variant)
  cliff_curves.json      → Chart 2: KV-cache collapse lines (context vs TPS)
  quality_scores.json    → Chart 3: accuracy per benchmark × variant
  cross_device.json      → Chart 4: heatmap (variant × device × context)
  thread_sweep.json      → Bonus: thread count impact
  kv_quant.json          → Bonus: KV-cache quant mitigation comparison
  perplexity.json        → Perplexity scores with corpus annotation
  raw_table.json         → Dataset Explorer: all inference rows (paginated in JS)

Usage
─────
  source .venv/bin/activate
  python3 scripts/bake_dashboard_data.py
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT  = Path(__file__).resolve().parent.parent
DATASET  = PROJECT / "dataset"
OUT      = PROJECT / "dashboard" / "data"

MODEL_LLAMA = "Llama-3.2-3B-Instruct"
MODEL_QWEN  = "Qwen2.5-1.5B-Instruct"

# Canonical display order
VARIANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
DEVICE_ORDER  = ["Pixel6a", "M4Mac", "M4Mac_CPU", "x86"]

BENCHMARK_DISPLAY = {
    "arc_easy":        "ARC-Easy",
    "arc_easy_fixed":  "ARC-Easy",
    "arc_challenge":   "ARC-Challenge",
    "boolq":           "BoolQ",
    "hellaswag":       "HellaSwag",
    "mmlu":            "MMLU",
    "truthfulqa":      "TruthfulQA",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

class _SafeEncoder(json.JSONEncoder):
    """Converts NaN/Inf to null and numpy scalars to Python types."""
    def default(self, o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if math.isnan(float(o)) else float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)

    def iterencode(self, o, _one_shot=False):
        # Intercept floats at encode time
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            yield "null"
            return
        yield from super().iterencode(o, _one_shot)


def write(name: str, data) -> None:
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, cls=_SafeEncoder))
    rows = len(data) if isinstance(data, list) else "dict"
    print(f"  ✓ {name}  ({rows})")


def safe_float(v):
    """Convert numpy scalars / NaN to Python float or None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def agg(series: pd.Series) -> dict:
    """Return mean/std/min/max/n for a numeric series."""
    s = series.dropna()
    if s.empty:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": safe_float(s.mean()),
        "std":  safe_float(s.std()),
        "min":  safe_float(s.min()),
        "max":  safe_float(s.max()),
        "n":    int(len(s)),
    }


def ordered_variants(variants) -> list[str]:
    seen = set(variants)
    return [v for v in VARIANT_ORDER if v in seen]


# ── Load data ─────────────────────────────────────────────────────────────────

pixel = pd.read_parquet(DATASET / "pixel_inference.parquet")
m4    = pd.read_parquet(DATASET / "m4_inference.parquet")
x86   = pd.read_parquet(DATASET / "x86_inference.parquet")
qual  = pd.read_parquet(DATASET / "quality_benchmarks.parquet")
ppl   = pd.read_parquet(DATASET / "perplexity.parquet")

# Convenience subsets
pixel_llama = pixel[pixel["model"] == MODEL_LLAMA]
pixel_qwen  = pixel[pixel["model"] == MODEL_QWEN]
m4_llama    = m4[m4["model"] == MODEL_LLAMA]
m4_qwen     = m4[m4["model"] == MODEL_QWEN]

pixel_cliff = pixel_llama[pixel_llama["experiment_type"] == "cliff_sweep"]

# M4 CPU cliff (ngl=0, 4 threads, 2026-04-09 run)
# 88 rows (91 - 3 excluded: Q5_K_M ctx=2048 OOM, Q6_K ctx=1536 CV=81%, Q8_0 ctx=2048 CV=99%)
m4_cpu_cliff = m4_llama[
    (m4_llama["experiment_type"] == "cliff_sweep") &
    (m4_llama["backend"] == "CPU") &
    (m4_llama["ngl"] == 0)
]

# M4 CPU TPS sweep (ngl=0, 4 threads, 2026-04-06 run) — used for bar chart baselines
# 7 rows: pure decode (n_prompt=0, n_gen=128), n_trials=10 pre-aggregated, context_len=0
# These are thermally settled reference measurements; cliff_sweep ctx=256 is inflated by
# CPU boost state (Q4_K_S: 25.19 cliff vs 13.16 TPS sweep).
m4_cpu_tps_sweep = m4_llama[
    (m4_llama["experiment_type"] == "standard_sweep") &
    (m4_llama["backend"] == "CPU") &
    (m4_llama["ngl"] == 0) &
    (m4_llama["context_len"] == 0)
]

# M4 canonical cliff: filter to the single clean benchmark run from 2026-03-23.
# The parquet contains multiple Q2_K runs (n=28 per ctx) and NaN-trial warmup rows that
# corrupt per-context averages (e.g. Q2_K mean=15.0 instead of correct 9.4 at ctx=1024,
# Q3_K_M NaN row = 176 tok/s at ctx=1800).
# The canonical run (m4_metal_cliff_20260323_015934) starts at 08:55 UTC on 2026-03-23.
# All variants except Q2_K already have n=5 trial-numbered rows from that window;
# Q2_K has additional run batches from earlier dates. Filter: ts in [08:55, 2026-03-24)
# AND trial.notna() isolates exactly 5 canonical rows per variant per context.
M4_CLIFF_TS_MIN = "2026-03-23T08:55"
M4_CLIFF_TS_MAX = "2026-03-24"
m4_cliff    = m4_llama[
    (m4_llama["experiment_type"] == "cliff_sweep") &
    m4_llama["trial"].notna() &
    (m4_llama["ts"] >= M4_CLIFF_TS_MIN) &
    (m4_llama["ts"] <  M4_CLIFF_TS_MAX)
]

# Pixel6a standard_sweep at ctx=256: used as fallback for Q4_K_M and Q5_K_M whose
# cliff_sweep ctx=256 baselines are inflated by a thermal warmup artifact (device burst
# on first trials → Q4_K_M shows 9.12 tok/s trial-1, stabilising to 6.67 by trial-7;
# cliff_sweep mean=7.61 >> standard_sweep mean=4.85 which is consistent with TPS sweep).
pixel_std256 = pixel_llama[
    (pixel_llama["experiment_type"] == "standard_sweep") &
    (pixel_llama["context_len"] == 256)
]
# Variants whose cliff ctx=256 baseline is known-reliable (no thermal warmup artifact)
_CLIFF_RELIABLE_VARIANTS = {"Q2_K", "Q3_K_M", "Q4_K_S", "Q6_K", "Q8_0"}

OUT.mkdir(parents=True, exist_ok=True)
print(f"Writing JSON to {OUT}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Chart 1 — tps_by_variant.json
# Bar chart: mean decode TPS per variant × device
# Pixel: ctx=256. Five variants (Q2_K, Q3_K_M, Q4_K_S, Q6_K, Q8_0) use cliff_sweep
#         (filled-context, pre-collapse baseline). Q4_K_M and Q5_K_M use standard_sweep
#         because their cliff_sweep ctx=256 baselines are inflated by a thermal warmup
#         burst artifact (first trials ~9 tok/s, stabilising to ~6.7; mean=7.61 >> 4.85).
# M4:    ctx=1024 canonical cliff sweep (n=5 per ctx per variant, 2026-03-23 clean run)
# x86:   ctx=256 cliff sweep mean of n=5 trials (Llama only)
# ══════════════════════════════════════════════════════════════════════════════

def bake_tps_by_variant():
    result = {
        "devices": DEVICE_ORDER,
        "variants": VARIANT_ORDER,
        "data": {},
        "notes": {
            "Pixel6a": {
                "Q4_K_M": "standard_sweep ctx=256 (cliff_sweep baseline inflated by thermal warmup burst)",
                "Q5_K_M": "standard_sweep ctx=256 (cliff_sweep baseline inflated by thermal warmup burst)",
            },
            "M4Mac": {
                "_all": "Metal GPU, filled-context cliff_sweep at ctx=1024 (canonical run 2026-03-23, n=5)",
            },
            "M4Mac_CPU": {
                "_all": "CPU (ngl=0, 4 threads), TPS sweep (n_prompt=0, n_gen=128, n=10, 2026-04-06). Thermally settled reference. Cliff sweep ctx=256 excluded — inflated by CPU boost state.",
            },
            "x86": {
                "_all": "cliff_sweep ctx=256, mean of n=5 trials",
            },
        },
    }

    for model_label, model_name in [("Llama", MODEL_LLAMA), ("Qwen", MODEL_QWEN)]:
        model_data = {}

        # Pixel @ ctx=256 — per-variant source selection
        # Q2_K, Q3_K_M, Q4_K_S, Q6_K, Q8_0: cliff_sweep ctx=256 (filled context, n=10)
        # Q4_K_M, Q5_K_M: standard_sweep ctx=256 (thermally settled, n≥12)
        p_cliff = pixel[
            (pixel["model"] == model_name) &
            (pixel["experiment_type"] == "cliff_sweep") &
            (pixel["context_len"] == 256)
        ]
        p_std = pixel[
            (pixel["model"] == model_name) &
            (pixel["experiment_type"] == "standard_sweep") &
            (pixel["context_len"] == 256)
        ]
        pixel_tps = {}
        for v in VARIANT_ORDER:
            if v in _CLIFF_RELIABLE_VARIANTS:
                grp = p_cliff[p_cliff["variant"] == v]["decode_tps"]
            else:
                grp = p_std[p_std["variant"] == v]["decode_tps"]
            if not grp.empty:
                pixel_tps[v] = agg(grp)
        model_data["Pixel6a"] = pixel_tps

        # M4 @ ctx=1024 canonical cliff sweep (cleaned, n=5 per variant)
        # Note: M4 Qwen cliff data in parquet has no trial-numbered rows — falls back
        # to NaN-trial contaminated rows if Qwen is requested; return empty for Qwen.
        m4_tps = {}
        if model_name == MODEL_LLAMA:
            m = m4_cliff[m4_cliff["context_len"] == 1024]
            for v, grp in m.groupby("variant"):
                m4_tps[v] = agg(grp["decode_tps"])
        # Qwen M4 cliff data is all NaN-trial contaminated rows — return empty
        model_data["M4Mac"] = m4_tps

        # M4Mac CPU — TPS sweep (ngl=0, 4 threads, n=10, 2026-04-06) — Llama only
        # Uses standard_sweep rows (context_len=0, pure decode) as thermally settled baseline.
        # cliff_sweep ctx=256 excluded: inflated by CPU boost state (Q4_K_S: 25.19 vs 13.16).
        m4_cpu_tps = {}
        if model_name == MODEL_LLAMA:
            for v, grp in m4_cpu_tps_sweep.groupby("variant"):
                m4_cpu_tps[v] = agg(grp["decode_tps"])
        model_data["M4Mac_CPU"] = m4_cpu_tps

        # x86 @ ctx=256 cliff sweep — use mean of n=5 trials (Llama only; no Qwen on x86)
        x86_tps = {}
        if model_name in x86["model"].values:
            x_cliff256 = x86[
                (x86["model"] == model_name) &
                (x86["experiment_type"] == "cliff_sweep") &
                (x86["context_len"] == 256)
            ]
            for v, grp in x_cliff256.groupby("variant"):
                x86_tps[v] = agg(grp["decode_tps"])
        model_data["x86"] = x86_tps

        result["data"][model_label] = model_data

    write("tps_by_variant.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Chart 2 — cliff_curves.json
# Line chart: decode TPS vs context length per variant
# Pixel (Llama + Qwen), M4 (Llama + Qwen)
# Includes collapse threshold annotation
# ══════════════════════════════════════════════════════════════════════════════

def bake_cliff_curves():
    result = {
        "collapse_threshold": {"start": 1400, "end": 1500,
                               "label": "KV-cache collapse zone"},
        "curves": {},
    }

    x86_cliff_df = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "cliff_sweep")
    ]

    sources = {
        "Pixel6a_Llama": pixel_cliff,
        "Pixel6a_Qwen":  pixel[
            (pixel["model"] == MODEL_QWEN) &
            (pixel["experiment_type"] == "cliff_sweep")
        ],
        "M4Mac_Llama":     m4_cliff,       # Metal GPU canonical run (ts-filtered, n=5/ctx)
        "M4Mac_CPU_Llama": m4_cpu_cliff,  # CPU (ngl=0, 4 threads, 2026-04-09, n_trials=5 pre-aggregated)
        # M4Mac Qwen cliff rows all have trial=NaN (contaminated llama-bench rows) — exclude
        # "M4Mac_Qwen": excluded,
        "x86_Llama":     x86_cliff_df,
    }

    for label, df in sources.items():
        if df.empty:
            continue
        series = {}
        for variant in ordered_variants(df["variant"].unique()):
            v_df = df[df["variant"] == variant]
            points = []
            for ctx in sorted(v_df["context_len"].dropna().unique()):
                g = v_df[v_df["context_len"] == ctx]["decode_tps"]
                stats = agg(g)
                if stats["mean"] is not None:
                    points.append({"context": int(ctx), **stats})
            series[variant] = points
        result["curves"][label] = series

    write("cliff_curves.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Chart 3 — quality_scores.json
# Grouped bar: accuracy per benchmark × variant
# Separates Pixel and x86; standard vs imatrix calibration
# ══════════════════════════════════════════════════════════════════════════════

def bake_quality_scores():
    # Normalise x86_ prefixed benchmark names and assign device
    q = qual.copy()
    q["device_resolved"] = q["benchmark"].apply(
        lambda b: "x86" if b.startswith("x86_") else "Pixel6a"
    )
    q["benchmark_clean"] = q["benchmark"].str.replace("x86_", "", regex=False)

    # Prefer arc_easy_fixed over arc_easy where both exist
    arc_easy_fixed_variants = set(
        q[q["benchmark_clean"] == "arc_easy_fixed"]["variant"].unique()
    )
    # Only suppress old arc_easy for Pixel6a (where arc_easy_fixed was collected).
    # x86 has no arc_easy_fixed — keep its arc_easy rows.
    # Also suppress F16 from old arc_easy (flawed ~100% run; F16 not in arc_easy_fixed).
    q = q[~(
        (q["benchmark_clean"] == "arc_easy") &
        (q["device_resolved"] == "Pixel6a") &
        (q["variant"].isin(arc_easy_fixed_variants | {"F16"}))
    )]
    q["benchmark_clean"] = q["benchmark_clean"].replace(
        "arc_easy_fixed", "arc_easy"
    )

    # Drop custom_qa (too few questions, not a standard benchmark)
    q = q[q["benchmark_clean"] != "custom_qa"]

    benchmarks = [b for b in BENCHMARK_DISPLAY.keys()
                  if b in q["benchmark_clean"].unique()]

    result = {
        "benchmarks": benchmarks,
        "benchmark_labels": {b: BENCHMARK_DISPLAY[b] for b in benchmarks},
        "variants": VARIANT_ORDER,
        "devices": ["Pixel6a", "x86"],
        "data": {},
    }

    for device in ["Pixel6a", "x86"]:
        device_data = {"standard": {}, "imatrix": {}}
        dq = q[q["device_resolved"] == device]

        for calib in ["standard", "imatrix"]:
            cq = dq[dq["calibration"] == calib]
            for bm in benchmarks:
                bq = cq[cq["benchmark_clean"] == bm]
                bm_data = {}
                for _, row in bq.iterrows():
                    v = row["variant"]
                    bm_data[v] = {
                        "accuracy":  safe_float(row["accuracy_pct"]),
                        "correct":   int(row["correct"]) if pd.notna(row["correct"]) else None,
                        "total":     int(row["total"])   if pd.notna(row["total"])   else None,
                    }
                device_data[calib][bm] = bm_data

        result["data"][device] = device_data

    write("quality_scores.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Chart 4 — cross_device.json
# Heatmap: variant × device, value = mean decode TPS
# Sliceable by context_len (JS updates heatmap on slider drag)
# ══════════════════════════════════════════════════════════════════════════════

def bake_cross_device():
    x86_cliff_llama = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "cliff_sweep")
    ]
    x86_ref_llama = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "standard_sweep")
    ]

    # All context lengths: Pixel + M4 cliff, plus x86 cliff contexts
    all_contexts = sorted(set(
        list(pixel_cliff["context_len"].unique()) +
        list(m4_cliff["context_len"].unique()) +
        list(x86_cliff_llama["context_len"].dropna().unique())
    ))

    result = {
        "variants": VARIANT_ORDER,
        "devices":  DEVICE_ORDER,
        "context_lens": [int(c) for c in all_contexts],
        "models": ["Llama", "Qwen"],
        # x86 flat reference (ctx=256 single-run) for legacy fallback
        "x86_tps": {"Llama": {}, "Qwen": {}},
        "data": {},
    }

    # x86 flat reference — use ctx=256 n=5 cliff means where available,
    # else fall back to the single-run standard_sweep values
    x86_ref_ctx256 = x86_cliff_llama[x86_cliff_llama["context_len"] == 256]
    for v in VARIANT_ORDER:
        g = x86_ref_ctx256[x86_ref_ctx256["variant"] == v]["decode_tps"]
        if not g.empty:
            result["x86_tps"]["Llama"][v] = safe_float(g.mean())
        else:
            row = x86_ref_llama[x86_ref_llama["variant"] == v]
            if not row.empty:
                result["x86_tps"]["Llama"][v] = safe_float(row.iloc[0]["decode_tps"])

    for model_label, pixel_src, m4_src in [
        ("Llama", pixel_cliff, m4_cliff),
        ("Qwen",
         pixel[(pixel["model"] == MODEL_QWEN) & (pixel["experiment_type"] == "cliff_sweep")],
         # M4 Qwen cliff rows all have trial=NaN (contaminated llama-bench output rows);
         # exclude entirely — renders as null/— in heatmap, which is correct.
         m4.iloc[0:0]),  # empty with same columns
    ]:
        x86_src = x86_cliff_llama if model_label == "Llama" else pd.DataFrame()

        ctx_data = {}
        for ctx in all_contexts:
            ctx_key = str(int(ctx))
            cell = {"Pixel6a": {}, "M4Mac": {}, "x86": None}

            x86_at_ctx = {}
            for v in VARIANT_ORDER:
                # Pixel
                g = pixel_src[
                    (pixel_src["variant"] == v) &
                    (pixel_src["context_len"] == ctx)
                ]["decode_tps"]
                cell["Pixel6a"][v] = agg(g) if not g.empty else None

                # M4
                g = m4_src[
                    (m4_src["variant"] == v) &
                    (m4_src["context_len"] == ctx)
                ]["decode_tps"]
                cell["M4Mac"][v] = agg(g) if not g.empty else None

                # x86 cliff — only where we have real measurements
                if not x86_src.empty:
                    g = x86_src[
                        (x86_src["variant"] == v) &
                        (x86_src["context_len"] == ctx)
                    ]["decode_tps"]
                    if not g.empty:
                        x86_at_ctx[v] = agg(g)

            cell["x86"] = x86_at_ctx if x86_at_ctx else None
            ctx_data[ctx_key] = cell
        result["data"][model_label] = ctx_data

    write("cross_device.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Bonus — thread_sweep.json
# Q4_K_M on Pixel 6a: decode TPS vs thread count (1/2/4/8)
# ══════════════════════════════════════════════════════════════════════════════

def bake_thread_sweep():
    ts = pixel[
        (pixel["experiment_type"] == "thread_sweep") &
        (pixel["model"] == MODEL_LLAMA)
    ]
    result = {"variant": "Q4_K_M", "context_len": 256, "series": []}

    for threads in sorted(ts["threads"].dropna().unique()):
        g = ts[ts["threads"] == threads]["decode_tps"]
        result["series"].append({"threads": int(threads), **agg(g)})

    write("thread_sweep.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Bonus — kv_quant.json
# KV-cache quantization mitigation: default vs q8_0 kv_quant
# Overlay on top of cliff curves for Q3_K_M / Q6_K
# ══════════════════════════════════════════════════════════════════════════════

def bake_kv_quant():
    kv = pixel[
        (pixel["experiment_type"] == "kv_cache_quant") &
        (pixel["model"] == MODEL_LLAMA)
    ]
    result = {"series": {}}

    for variant in ordered_variants(kv["variant"].unique()):
        v_df = kv[kv["variant"] == variant]
        points = []
        for ctx in sorted(v_df["context_len"].dropna().unique()):
            g = v_df[v_df["context_len"] == ctx]["decode_tps"]
            stats = agg(g)
            if stats["mean"] is not None:
                kv_type = v_df[v_df["context_len"] == ctx]["kv_quant"].iloc[0]
                points.append({
                    "context": int(ctx),
                    "kv_quant": str(kv_type) if kv_type else "default",
                    **stats,
                })
        result["series"][variant] = points

    write("kv_quant.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Perplexity — perplexity.json
# WikiText-2 PPL per variant with corpus annotation
# ══════════════════════════════════════════════════════════════════════════════

def bake_perplexity():
    result = {"variants": VARIANT_ORDER, "data": []}

    for v in VARIANT_ORDER:
        row = ppl[ppl["variant"] == v]
        if row.empty:
            result["data"].append({
                "variant": v, "perplexity": None,
                "status": "not_evaluated", "corpus": None,
                "tokens_approx": None, "note": None,
            })
            continue
        r = row.iloc[0]
        result["data"].append({
            "variant":      v,
            "perplexity":   safe_float(r["perplexity"]),
            "status":       str(r["perplexity_status"]),
            "corpus":       str(r["corpus"]) if pd.notna(r["corpus"]) else None,
            "tokens_approx": int(r["tokens_approx"]) if pd.notna(r["tokens_approx"]) else None,
            "note":         str(r["note"]) if pd.notna(r.get("note")) else None,
        })

    # Warn about corpus mismatch
    result["corpus_warning"] = (
        "Q2_K and Q3_K_M evaluated on full WikiText-2 (~285K tokens). "
        "Q4_K_M, Q6_K, Q8_0 evaluated on a 12K-token sample. "
        "Do not compare across groups without accounting for corpus size."
    )

    write("perplexity.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Dataset Explorer — raw_table.json
# All inference records for the filterable table (paginated in JS)
# ══════════════════════════════════════════════════════════════════════════════

def bake_raw_table():
    cols = ["device", "backend", "model", "variant",
            "context_len", "trial", "threads",
            "decode_tps", "prefill_tps", "experiment_type",
            "kv_quant", "ts"]

    frames = []
    for df in [pixel, m4, x86]:
        subset = df[[c for c in cols if c in df.columns]].copy()
        frames.append(subset)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["decode_tps", "variant"])
    combined["decode_tps"]  = combined["decode_tps"].apply(safe_float)
    combined["prefill_tps"] = combined["prefill_tps"].apply(safe_float)
    combined["context_len"] = combined["context_len"].apply(
        lambda x: int(x) if pd.notna(x) else None
    )
    combined["threads"] = combined["threads"].apply(
        lambda x: int(x) if pd.notna(x) else None
    )

    # Replace NaN strings
    combined = combined.where(pd.notna(combined), other=None)

    # Convert any remaining NaN floats to None (pandas NaN bypasses _SafeEncoder
    # for nested dict values because C-level JSON encoding skips the Python hook)
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    records = [{k: _clean(v) for k, v in row.items()}
               for row in combined.to_dict(orient="records")]

    # Metadata for JS filters
    result = {
        "meta": {
            "total":        len(records),
            "devices":      DEVICE_ORDER,
            "variants":     VARIANT_ORDER,
            "models":       [MODEL_LLAMA, MODEL_QWEN],
            "experiment_types": [
                "cliff_sweep", "standard_sweep",
                "thread_sweep", "kv_cache_quant",
            ],
        },
        "rows": records,
    }

    write("raw_table.json", result)


# ── Run all ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bake_tps_by_variant()
    bake_cliff_curves()
    bake_quality_scores()
    bake_cross_device()
    bake_thread_sweep()
    bake_kv_quant()
    bake_perplexity()
    bake_raw_table()

    print(f"\nAll files written to {OUT}")
    total_kb = sum(f.stat().st_size for f in OUT.glob("*.json")) / 1024
    print(f"Total size: {total_kb:.1f} KB")
=======
#!/usr/bin/env python3
"""
bake_dashboard_data.py
----------------------
Reads cleaned Parquet files from dataset/ and writes pre-aggregated JSON
files to dashboard/data/ for the static GitHub Pages dashboard.

Output files
────────────
  tps_by_variant.json    → Chart 1: throughput bar (device × variant)
  cliff_curves.json      → Chart 2: KV-cache collapse lines (context vs TPS)
  quality_scores.json    → Chart 3: accuracy per benchmark × variant
  cross_device.json      → Chart 4: heatmap (variant × device × context)
  thread_sweep.json      → Bonus: thread count impact
  kv_quant.json          → Bonus: KV-cache quant mitigation comparison
  perplexity.json        → Perplexity scores with corpus annotation
  raw_table.json         → Dataset Explorer: all inference rows (paginated in JS)

Usage
─────
  source .venv/bin/activate
  python3 scripts/bake_dashboard_data.py
"""

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT  = Path(__file__).resolve().parent.parent
DATASET  = PROJECT / "dataset"
OUT      = PROJECT / "dashboard" / "data"

MODEL_LLAMA = "Llama-3.2-3B-Instruct"
MODEL_QWEN  = "Qwen2.5-1.5B-Instruct"

# Canonical display order
VARIANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
DEVICE_ORDER  = ["Pixel6a", "M4Mac", "M4Mac_CPU", "x86"]

BENCHMARK_DISPLAY = {
    "arc_easy":        "ARC-Easy",
    "arc_easy_fixed":  "ARC-Easy",
    "arc_challenge":   "ARC-Challenge",
    "boolq":           "BoolQ",
    "hellaswag":       "HellaSwag",
    "mmlu":            "MMLU",
    "truthfulqa":      "TruthfulQA",
}

# ── Helpers ────────────────────────────────────────────────────────────────────

class _SafeEncoder(json.JSONEncoder):
    """Converts NaN/Inf to null and numpy scalars to Python types."""
    def default(self, o):
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            return None
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return None if math.isnan(float(o)) else float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)

    def iterencode(self, o, _one_shot=False):
        # Intercept floats at encode time
        if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
            yield "null"
            return
        yield from super().iterencode(o, _one_shot)


def write(name: str, data) -> None:
    path = OUT / name
    path.write_text(json.dumps(data, indent=2, cls=_SafeEncoder))
    rows = len(data) if isinstance(data, list) else "dict"
    print(f"  ✓ {name}  ({rows})")


def safe_float(v):
    """Convert numpy scalars / NaN to Python float or None."""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) or math.isinf(f) else round(f, 4)
    except (TypeError, ValueError):
        return None


def agg(series: pd.Series) -> dict:
    """Return mean/std/min/max/n for a numeric series."""
    s = series.dropna()
    if s.empty:
        return {"mean": None, "std": None, "min": None, "max": None, "n": 0}
    return {
        "mean": safe_float(s.mean()),
        "std":  safe_float(s.std()),
        "min":  safe_float(s.min()),
        "max":  safe_float(s.max()),
        "n":    int(len(s)),
    }


def ordered_variants(variants) -> list[str]:
    seen = set(variants)
    return [v for v in VARIANT_ORDER if v in seen]


# ── Load data ─────────────────────────────────────────────────────────────────

pixel = pd.read_parquet(DATASET / "pixel_inference.parquet")
m4    = pd.read_parquet(DATASET / "m4_inference.parquet")
x86   = pd.read_parquet(DATASET / "x86_inference.parquet")
qual  = pd.read_parquet(DATASET / "quality_benchmarks.parquet")
ppl   = pd.read_parquet(DATASET / "perplexity.parquet")

# Convenience subsets
pixel_llama = pixel[pixel["model"] == MODEL_LLAMA]
pixel_qwen  = pixel[pixel["model"] == MODEL_QWEN]
m4_llama    = m4[m4["model"] == MODEL_LLAMA]
m4_qwen     = m4[m4["model"] == MODEL_QWEN]

pixel_cliff = pixel_llama[pixel_llama["experiment_type"] == "cliff_sweep"]

# M4 CPU cliff (ngl=0, 4 threads, 2026-04-09 run)
# 88 rows (91 - 3 excluded: Q5_K_M ctx=2048 OOM, Q6_K ctx=1536 CV=81%, Q8_0 ctx=2048 CV=99%)
m4_cpu_cliff = m4_llama[
    (m4_llama["experiment_type"] == "cliff_sweep") &
    (m4_llama["backend"] == "CPU") &
    (m4_llama["ngl"] == 0)
]

# M4 canonical cliff: filter to the single clean benchmark run from 2026-03-23.
# The parquet contains multiple Q2_K runs (n=28 per ctx) and NaN-trial warmup rows that
# corrupt per-context averages (e.g. Q2_K mean=15.0 instead of correct 9.4 at ctx=1024,
# Q3_K_M NaN row = 176 tok/s at ctx=1800).
# The canonical run (m4_metal_cliff_20260323_015934) starts at 08:55 UTC on 2026-03-23.
# All variants except Q2_K already have n=5 trial-numbered rows from that window;
# Q2_K has additional run batches from earlier dates. Filter: ts in [08:55, 2026-03-24)
# AND trial.notna() isolates exactly 5 canonical rows per variant per context.
M4_CLIFF_TS_MIN = "2026-03-23T08:55"
M4_CLIFF_TS_MAX = "2026-03-24"
m4_cliff    = m4_llama[
    (m4_llama["experiment_type"] == "cliff_sweep") &
    m4_llama["trial"].notna() &
    (m4_llama["ts"] >= M4_CLIFF_TS_MIN) &
    (m4_llama["ts"] <  M4_CLIFF_TS_MAX)
]

# Pixel6a standard_sweep at ctx=256: used as fallback for Q4_K_M and Q5_K_M whose
# cliff_sweep ctx=256 baselines are inflated by a thermal warmup artifact (device burst
# on first trials → Q4_K_M shows 9.12 tok/s trial-1, stabilising to 6.67 by trial-7;
# cliff_sweep mean=7.61 >> standard_sweep mean=4.85 which is consistent with TPS sweep).
pixel_std256 = pixel_llama[
    (pixel_llama["experiment_type"] == "standard_sweep") &
    (pixel_llama["context_len"] == 256)
]
# Variants whose cliff ctx=256 baseline is known-reliable (no thermal warmup artifact)
_CLIFF_RELIABLE_VARIANTS = {"Q2_K", "Q3_K_M", "Q4_K_S", "Q6_K", "Q8_0"}

OUT.mkdir(parents=True, exist_ok=True)
print(f"Writing JSON to {OUT}\n")


# ══════════════════════════════════════════════════════════════════════════════
# Chart 1 — tps_by_variant.json
# Bar chart: mean decode TPS per variant × device
# Pixel: ctx=256. Five variants (Q2_K, Q3_K_M, Q4_K_S, Q6_K, Q8_0) use cliff_sweep
#         (filled-context, pre-collapse baseline). Q4_K_M and Q5_K_M use standard_sweep
#         because their cliff_sweep ctx=256 baselines are inflated by a thermal warmup
#         burst artifact (first trials ~9 tok/s, stabilising to ~6.7; mean=7.61 >> 4.85).
# M4:    ctx=1024 canonical cliff sweep (n=5 per ctx per variant, 2026-03-23 clean run)
# x86:   ctx=256 cliff sweep mean of n=5 trials (Llama only)
# ══════════════════════════════════════════════════════════════════════════════

def bake_tps_by_variant():
    result = {
        "devices": DEVICE_ORDER,
        "variants": VARIANT_ORDER,
        "data": {},
        "notes": {
            "Pixel6a": {
                "Q4_K_M": "standard_sweep ctx=256 (cliff_sweep baseline inflated by thermal warmup burst)",
                "Q5_K_M": "standard_sweep ctx=256 (cliff_sweep baseline inflated by thermal warmup burst)",
            },
            "M4Mac": {
                "_all": "Metal GPU, filled-context cliff_sweep at ctx=1024 (canonical run 2026-03-23, n=5)",
            },
            "M4Mac_CPU": {
                "_all": "CPU (ngl=0, 4 threads), filled-context cliff_sweep at ctx=256 (2026-04-09, n_trials=5 pre-aggregated). Q3_K_M/Q4_K_S/Q4_K_M ctx=256 baseline may be inflated by CPU boost state.",
            },
            "x86": {
                "_all": "cliff_sweep ctx=256, mean of n=5 trials",
            },
        },
    }

    for model_label, model_name in [("Llama", MODEL_LLAMA), ("Qwen", MODEL_QWEN)]:
        model_data = {}

        # Pixel @ ctx=256 — per-variant source selection
        # Q2_K, Q3_K_M, Q4_K_S, Q6_K, Q8_0: cliff_sweep ctx=256 (filled context, n=10)
        # Q4_K_M, Q5_K_M: standard_sweep ctx=256 (thermally settled, n≥12)
        p_cliff = pixel[
            (pixel["model"] == model_name) &
            (pixel["experiment_type"] == "cliff_sweep") &
            (pixel["context_len"] == 256)
        ]
        p_std = pixel[
            (pixel["model"] == model_name) &
            (pixel["experiment_type"] == "standard_sweep") &
            (pixel["context_len"] == 256)
        ]
        pixel_tps = {}
        for v in VARIANT_ORDER:
            if v in _CLIFF_RELIABLE_VARIANTS:
                grp = p_cliff[p_cliff["variant"] == v]["decode_tps"]
            else:
                grp = p_std[p_std["variant"] == v]["decode_tps"]
            if not grp.empty:
                pixel_tps[v] = agg(grp)
        model_data["Pixel6a"] = pixel_tps

        # M4 @ ctx=1024 canonical cliff sweep (cleaned, n=5 per variant)
        # Note: M4 Qwen cliff data in parquet has no trial-numbered rows — falls back
        # to NaN-trial contaminated rows if Qwen is requested; return empty for Qwen.
        m4_tps = {}
        if model_name == MODEL_LLAMA:
            m = m4_cliff[m4_cliff["context_len"] == 1024]
            for v, grp in m.groupby("variant"):
                m4_tps[v] = agg(grp["decode_tps"])
        # Qwen M4 cliff data is all NaN-trial contaminated rows — return empty
        model_data["M4Mac"] = m4_tps

        # M4Mac CPU @ ctx=256 (ngl=0, 4 threads) — Llama only
        m4_cpu_tps = {}
        if model_name == MODEL_LLAMA:
            m_cpu = m4_cpu_cliff[m4_cpu_cliff["context_len"] == 256]
            for v, grp in m_cpu.groupby("variant"):
                m4_cpu_tps[v] = agg(grp["decode_tps"])
        model_data["M4Mac_CPU"] = m4_cpu_tps

        # x86 @ ctx=256 cliff sweep — use mean of n=5 trials (Llama only; no Qwen on x86)
        x86_tps = {}
        if model_name in x86["model"].values:
            x_cliff256 = x86[
                (x86["model"] == model_name) &
                (x86["experiment_type"] == "cliff_sweep") &
                (x86["context_len"] == 256)
            ]
            for v, grp in x_cliff256.groupby("variant"):
                x86_tps[v] = agg(grp["decode_tps"])
        model_data["x86"] = x86_tps

        result["data"][model_label] = model_data

    write("tps_by_variant.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Chart 2 — cliff_curves.json
# Line chart: decode TPS vs context length per variant
# Pixel (Llama + Qwen), M4 (Llama + Qwen)
# Includes collapse threshold annotation
# ══════════════════════════════════════════════════════════════════════════════

def bake_cliff_curves():
    result = {
        "collapse_threshold": {"start": 1400, "end": 1500,
                               "label": "KV-cache collapse zone"},
        "curves": {},
    }

    x86_cliff_df = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "cliff_sweep")
    ]

    sources = {
        "Pixel6a_Llama": pixel_cliff,
        "Pixel6a_Qwen":  pixel[
            (pixel["model"] == MODEL_QWEN) &
            (pixel["experiment_type"] == "cliff_sweep")
        ],
        "M4Mac_Llama":     m4_cliff,       # Metal GPU canonical run (ts-filtered, n=5/ctx)
        "M4Mac_CPU_Llama": m4_cpu_cliff,  # CPU (ngl=0, 4 threads, 2026-04-09, n_trials=5 pre-aggregated)
        # M4Mac Qwen cliff rows all have trial=NaN (contaminated llama-bench rows) — exclude
        # "M4Mac_Qwen": excluded,
        "x86_Llama":     x86_cliff_df,
    }

    for label, df in sources.items():
        if df.empty:
            continue
        series = {}
        for variant in ordered_variants(df["variant"].unique()):
            v_df = df[df["variant"] == variant]
            points = []
            for ctx in sorted(v_df["context_len"].dropna().unique()):
                g = v_df[v_df["context_len"] == ctx]["decode_tps"]
                stats = agg(g)
                if stats["mean"] is not None:
                    points.append({"context": int(ctx), **stats})
            series[variant] = points
        result["curves"][label] = series

    write("cliff_curves.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Chart 3 — quality_scores.json
# Grouped bar: accuracy per benchmark × variant
# Separates Pixel and x86; standard vs imatrix calibration
# ══════════════════════════════════════════════════════════════════════════════

def bake_quality_scores():
    # Normalise x86_ prefixed benchmark names and assign device
    q = qual.copy()
    q["device_resolved"] = q["benchmark"].apply(
        lambda b: "x86" if b.startswith("x86_") else "Pixel6a"
    )
    q["benchmark_clean"] = q["benchmark"].str.replace("x86_", "", regex=False)

    # Prefer arc_easy_fixed over arc_easy where both exist
    arc_easy_fixed_variants = set(
        q[q["benchmark_clean"] == "arc_easy_fixed"]["variant"].unique()
    )
    # Only suppress old arc_easy for Pixel6a (where arc_easy_fixed was collected).
    # x86 has no arc_easy_fixed — keep its arc_easy rows.
    # Also suppress F16 from old arc_easy (flawed ~100% run; F16 not in arc_easy_fixed).
    q = q[~(
        (q["benchmark_clean"] == "arc_easy") &
        (q["device_resolved"] == "Pixel6a") &
        (q["variant"].isin(arc_easy_fixed_variants | {"F16"}))
    )]
    q["benchmark_clean"] = q["benchmark_clean"].replace(
        "arc_easy_fixed", "arc_easy"
    )

    # Drop custom_qa (too few questions, not a standard benchmark)
    q = q[q["benchmark_clean"] != "custom_qa"]

    benchmarks = [b for b in BENCHMARK_DISPLAY.keys()
                  if b in q["benchmark_clean"].unique()]

    result = {
        "benchmarks": benchmarks,
        "benchmark_labels": {b: BENCHMARK_DISPLAY[b] for b in benchmarks},
        "variants": VARIANT_ORDER,
        "devices": ["Pixel6a", "x86"],
        "data": {},
    }

    for device in ["Pixel6a", "x86"]:
        device_data = {"standard": {}, "imatrix": {}}
        dq = q[q["device_resolved"] == device]

        for calib in ["standard", "imatrix"]:
            cq = dq[dq["calibration"] == calib]
            for bm in benchmarks:
                bq = cq[cq["benchmark_clean"] == bm]
                bm_data = {}
                for _, row in bq.iterrows():
                    v = row["variant"]
                    bm_data[v] = {
                        "accuracy":  safe_float(row["accuracy_pct"]),
                        "correct":   int(row["correct"]) if pd.notna(row["correct"]) else None,
                        "total":     int(row["total"])   if pd.notna(row["total"])   else None,
                    }
                device_data[calib][bm] = bm_data

        result["data"][device] = device_data

    write("quality_scores.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Chart 4 — cross_device.json
# Heatmap: variant × device, value = mean decode TPS
# Sliceable by context_len (JS updates heatmap on slider drag)
# ══════════════════════════════════════════════════════════════════════════════

def bake_cross_device():
    x86_cliff_llama = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "cliff_sweep")
    ]
    x86_ref_llama = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "standard_sweep")
    ]

    # All context lengths: Pixel + M4 cliff, plus x86 cliff contexts
    all_contexts = sorted(set(
        list(pixel_cliff["context_len"].unique()) +
        list(m4_cliff["context_len"].unique()) +
        list(x86_cliff_llama["context_len"].dropna().unique())
    ))

    result = {
        "variants": VARIANT_ORDER,
        "devices":  DEVICE_ORDER,
        "context_lens": [int(c) for c in all_contexts],
        "models": ["Llama", "Qwen"],
        # x86 flat reference (ctx=256 single-run) for legacy fallback
        "x86_tps": {"Llama": {}, "Qwen": {}},
        "data": {},
    }

    # x86 flat reference — use ctx=256 n=5 cliff means where available,
    # else fall back to the single-run standard_sweep values
    x86_ref_ctx256 = x86_cliff_llama[x86_cliff_llama["context_len"] == 256]
    for v in VARIANT_ORDER:
        g = x86_ref_ctx256[x86_ref_ctx256["variant"] == v]["decode_tps"]
        if not g.empty:
            result["x86_tps"]["Llama"][v] = safe_float(g.mean())
        else:
            row = x86_ref_llama[x86_ref_llama["variant"] == v]
            if not row.empty:
                result["x86_tps"]["Llama"][v] = safe_float(row.iloc[0]["decode_tps"])

    for model_label, pixel_src, m4_src in [
        ("Llama", pixel_cliff, m4_cliff),
        ("Qwen",
         pixel[(pixel["model"] == MODEL_QWEN) & (pixel["experiment_type"] == "cliff_sweep")],
         # M4 Qwen cliff rows all have trial=NaN (contaminated llama-bench output rows);
         # exclude entirely — renders as null/— in heatmap, which is correct.
         m4.iloc[0:0]),  # empty with same columns
    ]:
        x86_src = x86_cliff_llama if model_label == "Llama" else pd.DataFrame()

        ctx_data = {}
        for ctx in all_contexts:
            ctx_key = str(int(ctx))
            cell = {"Pixel6a": {}, "M4Mac": {}, "x86": None}

            x86_at_ctx = {}
            for v in VARIANT_ORDER:
                # Pixel
                g = pixel_src[
                    (pixel_src["variant"] == v) &
                    (pixel_src["context_len"] == ctx)
                ]["decode_tps"]
                cell["Pixel6a"][v] = agg(g) if not g.empty else None

                # M4
                g = m4_src[
                    (m4_src["variant"] == v) &
                    (m4_src["context_len"] == ctx)
                ]["decode_tps"]
                cell["M4Mac"][v] = agg(g) if not g.empty else None

                # x86 cliff — only where we have real measurements
                if not x86_src.empty:
                    g = x86_src[
                        (x86_src["variant"] == v) &
                        (x86_src["context_len"] == ctx)
                    ]["decode_tps"]
                    if not g.empty:
                        x86_at_ctx[v] = agg(g)

            cell["x86"] = x86_at_ctx if x86_at_ctx else None
            ctx_data[ctx_key] = cell
        result["data"][model_label] = ctx_data

    write("cross_device.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Bonus — thread_sweep.json
# Q4_K_M on Pixel 6a: decode TPS vs thread count (1/2/4/8)
# ══════════════════════════════════════════════════════════════════════════════

def bake_thread_sweep():
    ts = pixel[
        (pixel["experiment_type"] == "thread_sweep") &
        (pixel["model"] == MODEL_LLAMA)
    ]
    result = {"variant": "Q4_K_M", "context_len": 256, "series": []}

    for threads in sorted(ts["threads"].dropna().unique()):
        g = ts[ts["threads"] == threads]["decode_tps"]
        result["series"].append({"threads": int(threads), **agg(g)})

    write("thread_sweep.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Bonus — kv_quant.json
# KV-cache quantization mitigation: default vs q8_0 kv_quant
# Overlay on top of cliff curves for Q3_K_M / Q6_K
# ══════════════════════════════════════════════════════════════════════════════

def bake_kv_quant():
    kv = pixel[
        (pixel["experiment_type"] == "kv_cache_quant") &
        (pixel["model"] == MODEL_LLAMA)
    ]
    result = {"series": {}}

    for variant in ordered_variants(kv["variant"].unique()):
        v_df = kv[kv["variant"] == variant]
        points = []
        for ctx in sorted(v_df["context_len"].dropna().unique()):
            g = v_df[v_df["context_len"] == ctx]["decode_tps"]
            stats = agg(g)
            if stats["mean"] is not None:
                kv_type = v_df[v_df["context_len"] == ctx]["kv_quant"].iloc[0]
                points.append({
                    "context": int(ctx),
                    "kv_quant": str(kv_type) if kv_type else "default",
                    **stats,
                })
        result["series"][variant] = points

    write("kv_quant.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Perplexity — perplexity.json
# WikiText-2 PPL per variant with corpus annotation
# ══════════════════════════════════════════════════════════════════════════════

def bake_perplexity():
    result = {"variants": VARIANT_ORDER, "data": []}

    for v in VARIANT_ORDER:
        row = ppl[ppl["variant"] == v]
        if row.empty:
            result["data"].append({
                "variant": v, "perplexity": None,
                "status": "not_evaluated", "corpus": None,
                "tokens_approx": None, "note": None,
            })
            continue
        r = row.iloc[0]
        result["data"].append({
            "variant":      v,
            "perplexity":   safe_float(r["perplexity"]),
            "status":       str(r["perplexity_status"]),
            "corpus":       str(r["corpus"]) if pd.notna(r["corpus"]) else None,
            "tokens_approx": int(r["tokens_approx"]) if pd.notna(r["tokens_approx"]) else None,
            "note":         str(r["note"]) if pd.notna(r.get("note")) else None,
        })

    # Warn about corpus mismatch
    result["corpus_warning"] = (
        "Q2_K and Q3_K_M evaluated on full WikiText-2 (~285K tokens). "
        "Q4_K_M, Q6_K, Q8_0 evaluated on a 12K-token sample. "
        "Do not compare across groups without accounting for corpus size."
    )

    write("perplexity.json", result)


# ══════════════════════════════════════════════════════════════════════════════
# Dataset Explorer — raw_table.json
# All inference records for the filterable table (paginated in JS)
# ══════════════════════════════════════════════════════════════════════════════

def bake_raw_table():
    cols = ["device", "backend", "model", "variant",
            "context_len", "trial", "threads",
            "decode_tps", "prefill_tps", "experiment_type",
            "kv_quant", "ts"]

    frames = []
    for df in [pixel, m4, x86]:
        subset = df[[c for c in cols if c in df.columns]].copy()
        frames.append(subset)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["decode_tps", "variant"])
    combined["decode_tps"]  = combined["decode_tps"].apply(safe_float)
    combined["prefill_tps"] = combined["prefill_tps"].apply(safe_float)
    combined["context_len"] = combined["context_len"].apply(
        lambda x: int(x) if pd.notna(x) else None
    )
    combined["threads"] = combined["threads"].apply(
        lambda x: int(x) if pd.notna(x) else None
    )

    # Replace NaN strings
    combined = combined.where(pd.notna(combined), other=None)

    # Convert any remaining NaN floats to None (pandas NaN bypasses _SafeEncoder
    # for nested dict values because C-level JSON encoding skips the Python hook)
    def _clean(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    records = [{k: _clean(v) for k, v in row.items()}
               for row in combined.to_dict(orient="records")]

    # Metadata for JS filters
    result = {
        "meta": {
            "total":        len(records),
            "devices":      DEVICE_ORDER,
            "variants":     VARIANT_ORDER,
            "models":       [MODEL_LLAMA, MODEL_QWEN],
            "experiment_types": [
                "cliff_sweep", "standard_sweep",
                "thread_sweep", "kv_cache_quant",
            ],
        },
        "rows": records,
    }

    write("raw_table.json", result)


# ── Run all ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    bake_tps_by_variant()
    bake_cliff_curves()
    bake_quality_scores()
    bake_cross_device()
    bake_thread_sweep()
    bake_kv_quant()
    bake_perplexity()
    bake_raw_table()

    print(f"\nAll files written to {OUT}")
    total_kb = sum(f.stat().st_size for f in OUT.glob("*.json")) / 1024
    print(f"Total size: {total_kb:.1f} KB")
>>>>>>> 6e8752a (Updated Qwen 2.5 Benchmark on x86 Intel i5 device)
