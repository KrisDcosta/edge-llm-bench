#!/usr/bin/env python3
"""Validate a clean x86 Qwen cliff result directory before promotion."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
CONTEXTS = [256, 512, 768, 1024, 1200, 1300, 1400, 1500, 1600, 1800, 2048]


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path)
    parser.add_argument("--max-cv", type=float, default=0.20)
    parser.add_argument("--expected-trials", type=int, default=5)
    args = parser.parse_args()

    failures: list[str] = []
    if not args.results_dir.exists():
        print(f"missing results dir: {args.results_dir}", file=sys.stderr)
        return 2

    total_rows = 0
    for variant in VARIANTS:
        path = args.results_dir / f"cliff_{variant}.jsonl"
        if not path.exists():
            failures.append(f"{variant}: missing file {path.name}")
            continue

        try:
            rows = load_jsonl(path)
        except Exception as exc:
            failures.append(f"{variant}: failed to parse {path.name}: {exc}")
            continue

        total_rows += len(rows)
        by_ctx = {int(row.get("context", -1)): row for row in rows}

        extra = sorted(set(by_ctx) - set(CONTEXTS))
        if extra:
            failures.append(f"{variant}: unexpected contexts {extra}")

        for ctx in CONTEXTS:
            row = by_ctx.get(ctx)
            if row is None:
                failures.append(f"{variant} ctx={ctx}: missing row")
                continue

            err = row.get("error")
            decode = float(row.get("decode_tps", 0) or 0)
            n_trials = int(row.get("n_trials", 0) or 0)
            std = float(row.get("decode_std", 0) or 0)
            cv = std / decode if decode > 0 else float("inf")

            if err:
                failures.append(f"{variant} ctx={ctx}: error={err}")
            if decode <= 0:
                failures.append(f"{variant} ctx={ctx}: decode_tps={decode}")
            if n_trials != args.expected_trials:
                failures.append(f"{variant} ctx={ctx}: n_trials={n_trials}, expected={args.expected_trials}")
            if cv > args.max_cv:
                failures.append(f"{variant} ctx={ctx}: decode CV={cv:.1%} > {args.max_cv:.0%}")

    expected_total = len(VARIANTS) * len(CONTEXTS)
    if total_rows != expected_total:
        failures.append(f"total rows={total_rows}, expected={expected_total}")

    if failures:
        print("x86 Qwen cliff validation: FAILED")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("x86 Qwen cliff validation: PASS")
    print(f"  rows: {total_rows}/{expected_total}")
    print(f"  variants: {', '.join(VARIANTS)}")
    print(f"  contexts: {CONTEXTS[0]}..{CONTEXTS[-1]} ({len(CONTEXTS)} points)")
    print(f"  max allowed CV: {args.max_cv:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
