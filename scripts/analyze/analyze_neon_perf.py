#!/usr/bin/env python3
"""
Analyze Pixel 6a simpleperf/NEON counter output.

Usage:
  python3 scripts/analyze/analyze_neon_perf.py results/pixel_neon_perf_YYYYMMDD_HHMMSS

Outputs:
  neon_perf_summary.json
  neon_perf_summary.md
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

VARIANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
TOKENS_PER_RUN = 128


def mean(values: list[float]) -> float | None:
    return statistics.mean(values) if values else None


def stdev(values: list[float]) -> float | None:
    return statistics.stdev(values) if len(values) > 1 else None


def safe_float(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def rounded(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if value is not None else None


def load_rows(results_dir: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(results_dir.glob("neon_perf_*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            row["_source_file"] = path.name
            rows.append(row)
    return rows


def aggregate(rows: list[dict]) -> dict:
    variants = [v for v in VARIANT_ORDER if any(r.get("variant") == v for r in rows)]
    contexts = sorted({safe_int(r.get("context")) for r in rows if safe_int(r.get("context")) > 0})

    cells: dict[str, dict[str, dict]] = {}
    validation: list[str] = []

    for variant in variants:
        cells[variant] = {}
        for ctx in contexts:
            cr = [
                r for r in rows
                if r.get("variant") == variant
                and safe_int(r.get("context")) == ctx
                and r.get("status") != "adb_error"
            ]
            good_decode = [safe_float(r.get("decode_tps")) for r in cr if safe_float(r.get("decode_tps")) > 0]
            cycles = [safe_int(r.get("cycles")) / TOKENS_PER_RUN for r in cr if safe_int(r.get("cycles")) > 0]
            instrs = [safe_int(r.get("instructions")) / TOKENS_PER_RUN for r in cr if safe_int(r.get("instructions")) > 0]
            l1 = [safe_int(r.get("l1d_refill")) / TOKENS_PER_RUN for r in cr if safe_int(r.get("l1d_refill")) > 0]
            l2 = [safe_int(r.get("l2d_refill")) / TOKENS_PER_RUN for r in cr if safe_int(r.get("l2d_refill")) > 0]
            stall = [safe_int(r.get("stall_backend")) / TOKENS_PER_RUN for r in cr if safe_int(r.get("stall_backend")) > 0]

            cycles_mean = mean(cycles)
            instrs_mean = mean(instrs)
            stall_mean = mean(stall)
            ipc = (instrs_mean / cycles_mean) if instrs_mean and cycles_mean else None
            stall_pct = (stall_mean / cycles_mean * 100.0) if stall_mean and cycles_mean else None
            tps_mean = mean(good_decode)
            tps_std = stdev(good_decode)
            tps_cv = (tps_std / tps_mean) if tps_mean and tps_std else None

            cell = {
                "n_rows": len(cr),
                "n_decode_success": len(good_decode),
                "decode_tps_mean": rounded(tps_mean),
                "decode_tps_std": rounded(tps_std),
                "decode_tps_cv": rounded(tps_cv),
                "cycles_per_token": rounded(cycles_mean),
                "instructions_per_token": rounded(instrs_mean),
                "l1d_refill_per_token": rounded(mean(l1)),
                "l2d_refill_per_token": rounded(mean(l2)),
                "stall_backend_per_token": rounded(stall_mean),
                "ipc": rounded(ipc),
                "stall_backend_pct": rounded(stall_pct),
            }
            cells[variant][str(ctx)] = cell

            if len(good_decode) < 3:
                validation.append(f"{variant} ctx={ctx}: fewer than 3 decode-success trials")
            if tps_cv is not None and tps_cv > 0.20:
                validation.append(f"{variant} ctx={ctx}: decode CV {tps_cv:.1%} > 20%")

    hypotheses = compute_hypotheses(cells)
    return {
        "variants": variants,
        "contexts": contexts,
        "tokens_per_run": TOKENS_PER_RUN,
        "cells": cells,
        "hypotheses": hypotheses,
        "validation_warnings": validation,
    }


def cell_metric(cells: dict, variant: str, ctx: int, metric: str) -> float | None:
    return cells.get(variant, {}).get(str(ctx), {}).get(metric)


def ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den in (None, 0):
        return None
    return num / den


def compute_hypotheses(cells: dict) -> dict:
    q2_l2_256 = cell_metric(cells, "Q2_K", 256, "l2d_refill_per_token")
    q6_l2_256 = cell_metric(cells, "Q6_K", 256, "l2d_refill_per_token")
    q2_l2_512 = cell_metric(cells, "Q2_K", 512, "l2d_refill_per_token")

    q2_instr_256 = cell_metric(cells, "Q2_K", 256, "instructions_per_token")
    q6_instr_256 = cell_metric(cells, "Q6_K", 256, "instructions_per_token")
    q8_instr_256 = cell_metric(cells, "Q8_0", 256, "instructions_per_token")

    return {
        "h1_q6_vs_q2_l2_refill_ctx256": rounded(ratio(q6_l2_256, q2_l2_256)),
        "h2_q2_l2_refill_ctx512_vs_256": rounded(ratio(q2_l2_512, q2_l2_256)),
        "q6_vs_q2_instructions_ctx256": rounded(ratio(q6_instr_256, q2_instr_256)),
        "q8_vs_q2_instructions_ctx256": rounded(ratio(q8_instr_256, q2_instr_256)),
    }


def fmt(value, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{digits}f}"


def write_markdown(summary: dict, out_path: Path) -> None:
    lines = [
        "# NEON / Simpleperf Summary",
        "",
        f"Variants: {', '.join(summary['variants'])}",
        f"Contexts: {', '.join(str(c) for c in summary['contexts'])}",
        "",
        "## Per-Token Counter Table",
        "",
        "| Variant | Ctx | n | TPS | CV | IPC | Instr/tok | L2 refill/tok | Backend stall % |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]

    for variant in summary["variants"]:
        for ctx in summary["contexts"]:
            cell = summary["cells"][variant][str(ctx)]
            lines.append(
                f"| {variant} | {ctx} | {cell['n_decode_success']} | "
                f"{fmt(cell['decode_tps_mean'])} | {fmt((cell['decode_tps_cv'] or 0) * 100, 1)}% | "
                f"{fmt(cell['ipc'], 3)} | {fmt(cell['instructions_per_token'], 0)} | "
                f"{fmt(cell['l2d_refill_per_token'], 0)} | {fmt(cell['stall_backend_pct'], 1)}% |"
            )

    lines.extend([
        "",
        "## Hypothesis Checks",
        "",
        "| Check | Ratio | Expected |",
        "|---|---:|---|",
        f"| Q6_K / Q2_K L2 refill per token at ctx=256 | {fmt(summary['hypotheses']['h1_q6_vs_q2_l2_refill_ctx256'])}x | 1.5x to 6.0x, directionally near 3x |",
        f"| Q2_K L2 refill ctx=512 / ctx=256 | {fmt(summary['hypotheses']['h2_q2_l2_refill_ctx512_vs_256'])}x | >=1.5x if L2 overflow drives cliff |",
        f"| Q6_K / Q2_K instructions per token at ctx=256 | {fmt(summary['hypotheses']['q6_vs_q2_instructions_ctx256'])}x | >1.0x, directionally high |",
        f"| Q8_0 / Q2_K instructions per token at ctx=256 | {fmt(summary['hypotheses']['q8_vs_q2_instructions_ctx256'])}x | >1.0x, data-volume dominated |",
        "",
        "## Validation Warnings",
        "",
    ])

    if summary["validation_warnings"]:
        lines.extend(f"- {warning}" for warning in summary["validation_warnings"])
    else:
        lines.append("- None")

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze Pixel NEON/simpleperf counter results")
    parser.add_argument("results_dir", type=Path)
    args = parser.parse_args()

    if not args.results_dir.exists():
        print(f"missing results dir: {args.results_dir}", file=sys.stderr)
        return 2

    rows = load_rows(args.results_dir)
    if not rows:
        print(f"no neon_perf_*.jsonl rows found in {args.results_dir}", file=sys.stderr)
        return 2

    summary = aggregate(rows)
    json_path = args.results_dir / "neon_perf_summary.json"
    md_path = args.results_dir / "neon_perf_summary.md"
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(summary, md_path)

    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    if summary["validation_warnings"]:
        print("validation warnings:")
        for warning in summary["validation_warnings"]:
            print(f"  - {warning}")
    else:
        print("validation warnings: none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
