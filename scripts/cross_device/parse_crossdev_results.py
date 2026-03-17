#!/usr/bin/env python3
"""
parse_crossdev_results.py — Summarise cross-device benchmark JSONL files.

Reads one or more JSONL files produced by mac_m4_bench.sh or x86_bench.sh
and computes per-variant per-context mean±std for the four key metrics:
    decode_tps, prefill_tps, ttft_s, e2e_s

Outputs:
  1. A summary CSV to stdout (or --output-csv PATH)
  2. A formatted table printed to stdout
  3. Optionally an additional CSV per device tag (--split-devices)

The CSV column layout is compatible with analysis/generate_figures.py's
summary_table.csv format so cross-device data can be loaded by the same
figure-generation pipeline.

Usage:
    python3 scripts/cross_device/parse_crossdev_results.py results/crossdev_mac_m4_*.jsonl
    python3 scripts/cross_device/parse_crossdev_results.py results/crossdev_x86_*.jsonl
    python3 scripts/cross_device/parse_crossdev_results.py results/crossdev_*.jsonl --split-devices
    python3 scripts/cross_device/parse_crossdev_results.py results/crossdev_mac_m4_20260313.jsonl \
        --output-csv results/mac_m4_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev


# ---------------------------------------------------------------------------
# Constants (mirror generate_figures.py for compatibility)
# ---------------------------------------------------------------------------

QUANT_ORDER = ["Q2_K", "Q3_K_S", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q5_K_S", "Q6_K", "Q8_0", "F16"]
QUANT_BITS  = {"Q2_K": 2, "Q3_K_S": 3, "Q3_K_M": 3,
               "Q4_K_S": 4, "Q4_K_M": 4,
               "Q5_K_S": 5, "Q5_K_M": 5,
               "Q6_K": 6, "Q8_0": 8, "F16": 16}
MODEL_SIZE_GB = {"Q2_K": 1.3, "Q3_K_M": 1.6, "Q4_K_S": 1.8, "Q4_K_M": 2.0,
                 "Q5_K_M": 2.2, "Q6_K": 2.7, "Q8_0": 3.2, "F16": 6.4}

# Output columns — must match generate_figures.py's summary_table.csv columns
# so that cross-device CSVs can be loaded by the same figure pipeline.
CSV_COLUMNS = [
    "device_tag",          # extra column: identifies source device/platform
    "variant",
    "quant_bits",
    "model_size_gb",
    "context_length",
    "decode_tps_mean",
    "decode_tps_std",
    "decode_tps_p50",
    "decode_tps_p90",
    "prefill_tps_mean",
    "prefill_tps_std",
    "ttft_mean_s",
    "ttft_std_s",
    "e2e_mean_s",
    "e2e_std_s",
    "peak_rss_mb_mean",
    "n_trials",
]

METRICS_TO_COMPUTE = [
    "decode_tps",
    "prefill_tps",
    "ttft_s",
    "e2e_s",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_jsonl(paths: list[Path]) -> list[dict]:
    records = []
    for p in paths:
        with open(p) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    print(f"WARNING: {p}:{lineno}: JSON parse error: {exc}", file=sys.stderr)
    return records


def filter_measurement(records: list[dict]) -> list[dict]:
    """Keep only successful, non-warmup records."""
    return [
        r for r in records
        if r.get("status") == "success"
        and not r.get("trial", {}).get("is_warmup", False)
    ]


def device_tag(record: dict) -> str:
    """Extract a short device identifier from a record."""
    dev = record.get("device", {})
    platform = dev.get("platform", "")
    backend  = dev.get("backend", "")
    model    = dev.get("model", "")
    if platform == "macos":
        return f"mac_m4_metal"
    elif platform == "linux":
        return f"x86_avx2"
    elif platform == "android":
        return f"android_{model}".replace(" ", "_").lower()
    return f"{platform}_{backend}".strip("_") or "unknown"


# ---------------------------------------------------------------------------
# Statistics helpers
# ---------------------------------------------------------------------------

def _percentile(data: list[float], p: float) -> float:
    if not data:
        return float("nan")
    s = sorted(data)
    idx = (len(s) - 1) * p / 100
    lo, hi = int(idx), min(int(idx) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (idx - lo)


def compute_stats(values: list[float]) -> dict:
    if not values:
        return {"mean": None, "std": None, "p50": None, "p90": None, "n": 0}
    n = len(values)
    return {
        "mean": mean(values),
        "std":  stdev(values) if n > 1 else 0.0,
        "p50":  _percentile(values, 50),
        "p90":  _percentile(values, 90),
        "n":    n,
    }


def fmt(x: float | None, decimals: int = 3) -> str:
    if x is None or x != x:  # None or NaN
        return "N/A"
    return f"{x:.{decimals}f}"


# ---------------------------------------------------------------------------
# Grouping and aggregation
# ---------------------------------------------------------------------------

def aggregate(
    records: list[dict],
) -> list[dict]:
    """
    Group by (device_tag, gguf_variant, context_length) and compute stats.
    Returns a list of row dicts matching CSV_COLUMNS.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        tag     = device_tag(r)
        variant = r.get("build", {}).get("gguf_variant", "unknown")
        ctx     = r.get("trial", {}).get("context_length", 0)
        groups[(tag, variant, ctx)].append(r)

    rows = []
    # Sort: device_tag, then variant by QUANT_ORDER, then ctx ascending
    def sort_key(k):
        tag, variant, ctx = k
        vi = QUANT_ORDER.index(variant) if variant in QUANT_ORDER else 99
        return (tag, vi, ctx)

    for key in sorted(groups.keys(), key=sort_key):
        tag, variant, ctx = key
        recs = groups[key]

        def vals(metric: str) -> list[float]:
            out = []
            for r in recs:
                v = r.get("metrics", {}).get(metric)
                if v is not None:
                    out.append(float(v))
            return out

        def rss_vals() -> list[float]:
            out = []
            for r in recs:
                v = r.get("resources", {}).get("peak_rss_mb")
                if v is not None:
                    out.append(float(v))
            return out

        ds = compute_stats(vals("decode_tps"))
        ps = compute_stats(vals("prefill_tps"))
        ts = compute_stats(vals("ttft_s"))
        es = compute_stats(vals("e2e_s"))
        rs = compute_stats(rss_vals())

        rows.append({
            "device_tag":       tag,
            "variant":          variant,
            "quant_bits":       QUANT_BITS.get(variant, "?"),
            "model_size_gb":    MODEL_SIZE_GB.get(variant, "?"),
            "context_length":   ctx,
            "decode_tps_mean":  fmt(ds["mean"]),
            "decode_tps_std":   fmt(ds["std"]),
            "decode_tps_p50":   fmt(ds["p50"]),
            "decode_tps_p90":   fmt(ds["p90"]),
            "prefill_tps_mean": fmt(ps["mean"]),
            "prefill_tps_std":  fmt(ps["std"]),
            "ttft_mean_s":      fmt(ts["mean"]),
            "ttft_std_s":       fmt(ts["std"]),
            "e2e_mean_s":       fmt(es["mean"]),
            "e2e_std_s":        fmt(es["std"]),
            "peak_rss_mb_mean": fmt(rs["mean"]) if rs["n"] > 0 else "N/A",
            "n_trials":         ds["n"],
        })

    return rows


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def write_csv(rows: list[dict], path: Path | None) -> None:
    if not rows:
        print("WARNING: No rows to write.", file=sys.stderr)
        return
    if path is None:
        import io
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
        print(buf.getvalue(), end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
            w.writeheader()
            w.writerows(rows)
        print(f"CSV written: {path}  ({len(rows)} rows)")


def print_table(rows: list[dict]) -> None:
    if not rows:
        print("No results to display.")
        return

    # Group by device_tag for section headers
    by_device: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_device[r["device_tag"]].append(r)

    for device, device_rows in sorted(by_device.items()):
        print()
        print(f"Device: {device}")
        print("-" * 100)
        header = (
            f"{'Variant':<12} {'Ctx':>6}  "
            f"{'Decode TPS':>12} {'±':>6}  "
            f"{'Prefill TPS':>12} {'±':>6}  "
            f"{'TTFT (s)':>10} {'±':>6}  "
            f"{'E2E (s)':>9} {'±':>6}  "
            f"{'N':>4}"
        )
        print(header)
        print("-" * 100)

        for r in device_rows:
            line = (
                f"{r['variant']:<12} {r['context_length']:>6}  "
                f"{r['decode_tps_mean']:>12} {r['decode_tps_std']:>6}  "
                f"{r['prefill_tps_mean']:>12} {r['prefill_tps_std']:>6}  "
                f"{r['ttft_mean_s']:>10} {r['ttft_std_s']:>6}  "
                f"{r['e2e_mean_s']:>9} {r['e2e_std_s']:>6}  "
                f"{r['n_trials']:>4}"
            )
            print(line)

        print()


def print_failure_summary(all_records: list[dict]) -> None:
    failed = [r for r in all_records if r.get("status") != "success"]
    if not failed:
        return
    print(f"\nFailed records: {len(failed)}", file=sys.stderr)
    summary: dict[str, int] = defaultdict(int)
    for r in failed:
        code    = (r.get("failure") or {}).get("code", r.get("status", "unknown"))
        variant = r.get("build", {}).get("gguf_variant", "unknown")
        summary[f"{variant}:{code}"] += 1
    for k, v in sorted(summary.items()):
        print(f"  {k}: {v}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "jsonl_files",
        nargs="*",
        metavar="FILE",
        help="One or more .jsonl files from mac_m4_bench.sh or x86_bench.sh",
    )
    p.add_argument(
        "--output-csv",
        metavar="PATH",
        default=None,
        help="Write summary CSV to this path (default: print to stdout)",
    )
    p.add_argument(
        "--split-devices",
        action="store_true",
        help="Write a separate CSV per device_tag alongside --output-csv base name",
    )
    p.add_argument(
        "--no-table",
        action="store_true",
        help="Suppress the formatted table output (useful when piping CSV)",
    )
    p.add_argument(
        "--include-warmups",
        action="store_true",
        help="Include warmup trials in the analysis (default: excluded)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Collect input files
    input_paths: list[Path] = []
    for arg in args.jsonl_files:
        p = Path(arg)
        if p.is_dir():
            input_paths.extend(sorted(p.glob("crossdev_*.jsonl")))
        elif p.suffix == ".jsonl" and p.exists():
            input_paths.append(p)
        else:
            print(f"WARNING: Skipping '{arg}' (not a .jsonl file or directory)", file=sys.stderr)

    if not input_paths:
        parser.print_help()
        return 0

    # Load records
    print(f"Loading {len(input_paths)} file(s)...", file=sys.stderr)
    all_records = load_jsonl(input_paths)
    print(f"  Total records: {len(all_records)}", file=sys.stderr)

    if args.include_warmups:
        measurement_records = [r for r in all_records if r.get("status") == "success"]
    else:
        measurement_records = filter_measurement(all_records)

    warmup_count = sum(1 for r in all_records if r.get("trial", {}).get("is_warmup", False))
    print(f"  Measurement records: {len(measurement_records)}  "
          f"(warmups excluded: {warmup_count})", file=sys.stderr)

    print_failure_summary(all_records)

    if not measurement_records:
        print("ERROR: No successful measurement records found.", file=sys.stderr)
        return 1

    # Aggregate
    rows = aggregate(measurement_records)

    # Output
    out_path = Path(args.output_csv) if args.output_csv else None

    if not args.no_table:
        print_table(rows)

    write_csv(rows, out_path)

    # Split by device if requested
    if args.split_devices and out_path is not None:
        by_device: dict[str, list[dict]] = defaultdict(list)
        for r in rows:
            by_device[r["device_tag"]].append(r)
        for tag, device_rows in by_device.items():
            tag_path = out_path.parent / f"{out_path.stem}_{tag}{out_path.suffix}"
            write_csv(device_rows, tag_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
