#!/usr/bin/env python3
"""
cliff_analysis.py  —  KV-cache cliff analysis from JSONL benchmark output

Loads cliff sweep JSONL files produced by m4_llama_cliff.sh,
m4_qwen_cliff.sh, pixel_llama_cliff.sh and prints a per-variant
throughput table with cliff detection.

Usage:
    python3 scripts/analyze/cliff_analysis.py results/m4_llama_cliff_*/
    python3 scripts/analyze/cliff_analysis.py results/pixel_llama_cliff_*/ --device Pixel6a
    python3 scripts/analyze/cliff_analysis.py results/m4_llama_cliff_*/ results/pixel_llama_cliff_*/

Options:
    --device LABEL   Override device label in output  (default: from JSON)
    --min-n  N       Minimum valid trials per context point (default: 1)
    --csv            Also write CSV to results/cliff_summary.csv
    --json           Also write JSON to results/cliff_summary.json
"""

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path


VARIANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
CLIFF_THRESHOLD = 0.10   # >10% drop triggers cliff annotation


def load_results(results_dirs: list[str], min_n: int = 1):
    """
    Load all cliff_*.jsonl from one or more results directories.
    Returns: {device_label: {variant: {context: [decode_tps, ...]}}}
    """
    all_data: dict[str, dict[str, dict[int, list[float]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )

    for results_dir in results_dirs:
        p = Path(results_dir)
        jsonl_files = sorted(p.glob("cliff_*.jsonl"))
        if not jsonl_files:
            print(f"  ⚠️  No cliff_*.jsonl found in {results_dir}", file=sys.stderr)
            continue

        for fpath in jsonl_files:
            for line in fpath.open():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue

                tps = float(d.get("decode_tps", 0))
                if tps <= 0:
                    continue

                device  = d.get("device", "unknown")
                variant = d.get("variant", fpath.stem.replace("cliff_", ""))
                ctx     = int(d.get("context", 0))

                all_data[device][variant][ctx].append(tps)

    return all_data


def find_cliff(ctx_tps: dict[int, list[float]], threshold: float = CLIFF_THRESHOLD):
    """Return (cliff_ctx, drop_pct) or (None, 0) if no cliff detected."""
    contexts = sorted(ctx_tps)
    prev_avg = None
    for ctx in contexts:
        vals = ctx_tps[ctx]
        if not vals:
            continue
        avg = sum(vals) / len(vals)
        if prev_avg and (prev_avg - avg) / prev_avg > threshold:
            return ctx, (prev_avg - avg) / prev_avg * 100
        prev_avg = avg
    return None, 0


def print_table(device: str, variant_data: dict[str, dict[int, list[float]]], min_n: int):
    """Pretty-print the cliff table for one device."""
    # Collect all context sizes present
    all_ctxs: set[int] = set()
    for vd in variant_data.values():
        all_ctxs.update(vd)
    ctxs = sorted(all_ctxs)

    print(f"\n{'='*72}")
    print(f"  Device: {device}")
    print(f"{'='*72}")
    print(f"  {'Variant':<10}  " + "  ".join(f"ctx={c:5d}" for c in ctxs))
    print(f"  {'-'*10}  " + "  ".join("-" * 10 for _ in ctxs))

    for variant in VARIANT_ORDER:
        ctx_tps = variant_data.get(variant, {})
        if not ctx_tps:
            continue

        cliff_ctx, drop_pct = find_cliff(ctx_tps)
        row = f"  {variant:<10}  "
        prev_avg = None
        for ctx in ctxs:
            vals = [v for v in ctx_tps.get(ctx, []) if v > 0]
            if len(vals) < min_n:
                row += f"{'N/A':>10}  "
                continue
            avg = sum(vals) / len(vals)
            if prev_avg and (prev_avg - avg) / prev_avg > CLIFF_THRESHOLD:
                row += f"{avg:8.2f}↓  "   # cliff marker
            else:
                row += f"{avg:8.2f}   "
            prev_avg = avg
        print(row)

        if cliff_ctx:
            print(f"  {'':10}  ↑ CLIFF at ctx={cliff_ctx}: -{drop_pct:.0f}% drop")

    print()


def build_summary(all_data: dict) -> list[dict]:
    """Build flat list of dicts for CSV/JSON export."""
    rows = []
    for device, variant_data in sorted(all_data.items()):
        for variant in VARIANT_ORDER:
            ctx_tps = variant_data.get(variant, {})
            if not ctx_tps:
                continue
            cliff_ctx, drop_pct = find_cliff(ctx_tps)
            for ctx in sorted(ctx_tps):
                vals = [v for v in ctx_tps[ctx] if v > 0]
                if not vals:
                    continue
                import statistics
                rows.append({
                    "device":       device,
                    "variant":      variant,
                    "context":      ctx,
                    "n_trials":     len(vals),
                    "decode_mean":  round(sum(vals) / len(vals), 4),
                    "decode_std":   round(statistics.stdev(vals), 4) if len(vals) > 1 else 0,
                    "decode_min":   round(min(vals), 4),
                    "decode_max":   round(max(vals), 4),
                    "cliff_ctx":    cliff_ctx,
                    "cliff_drop_pct": round(drop_pct, 1),
                })
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dirs", nargs="+", help="results/m4_llama_cliff_*/ directories")
    ap.add_argument("--device",  help="Override device label in output")
    ap.add_argument("--min-n",   type=int, default=1, metavar="N",
                    help="Minimum valid trials required per context point (default: 1)")
    ap.add_argument("--csv",  action="store_true", help="Write results/cliff_summary.csv")
    ap.add_argument("--json", action="store_true", help="Write results/cliff_summary.json")
    args = ap.parse_args()

    all_data = load_results(args.results_dirs, args.min_n)

    if not all_data:
        print("No valid data found.", file=sys.stderr)
        sys.exit(1)

    for device, variant_data in sorted(all_data.items()):
        label = args.device or device
        print_table(label, variant_data, args.min_n)

    summary = build_summary(all_data)

    if args.csv:
        out = Path("results/cliff_summary.csv")
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=summary[0].keys())
            w.writeheader()
            w.writerows(summary)
        print(f"  CSV written: {out}")

    if args.json:
        out = Path("results/cliff_summary.json")
        out.write_text(json.dumps(summary, indent=2))
        print(f"  JSON written: {out}")


if __name__ == "__main__":
    main()
