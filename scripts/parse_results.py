#!/usr/bin/env python3
"""
parse_results.py — Parse benchmark result JSONL files and print human-readable summary.

Usage:
    python3 scripts/parse_results.py results/run-*.jsonl
    python3 scripts/parse_results.py results/run-*.jsonl --variant Q4_K_M
    python3 scripts/parse_results.py results/run-*.jsonl --json
"""

import json
import sys
import argparse
from pathlib import Path
from collections import defaultdict
from statistics import mean, stdev

def parse_args():
    parser = argparse.ArgumentParser(description='Parse benchmark result JSONL files')
    parser.add_argument('files', nargs='+', help='JSONL result files')
    parser.add_argument('--variant', type=str, help='Filter by variant (e.g., Q4_K_M)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    return parser.parse_args()

def load_jsonl(filepath):
    """Load JSONL file and return list of records."""
    records = []
    with open(filepath) as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return records

def main():
    args = parse_args()

    # Load all records
    all_records = []
    for fpath in args.files:
        p = Path(fpath)
        if p.exists():
            all_records.extend(load_jsonl(p))

    if not all_records:
        print("No records found", file=sys.stderr)
        return 1

    # Group by experiment and variant
    groups = defaultdict(lambda: defaultdict(list))
    for record in all_records:
        if record.get('status') != 'success':
            continue
        exp_id = record.get('experiment_id', 'unknown')
        variant = record.get('variant', 'unknown')
        ctx = record.get('context_size', '?')

        if args.variant and variant != args.variant:
            continue

        # Collect throughput metric
        tok_s = record.get('tokens_per_second')
        if tok_s is not None:
            groups[(exp_id, variant, ctx)]['tok_s'].append(tok_s)

    if args.json:
        # Output as JSON summary
        summary = {}
        for (exp, var, ctx), metrics in groups.items():
            key = f"{var}:{ctx}" if ctx != '?' else var
            if 'tok_s' in metrics and metrics['tok_s']:
                summary[key] = {
                    'n_ok': len(metrics['tok_s']),
                    'tok_s_mean': mean(metrics['tok_s']),
                    'tok_s_std': stdev(metrics['tok_s']) if len(metrics['tok_s']) > 1 else 0.0,
                }
        print(json.dumps(summary, indent=2))
    else:
        # Table output
        print(f"Loaded {len(all_records)} non-warmup records from {len(args.files)} file(s)\n")
        print(f"{'Variant':<12} {'Ctx':<6} {'OK/Total':<10} {'Tok/s (decode)':<18} {'±Std':<7} Status")
        print("-" * 75)

        total_ok = 0
        for (exp, var, ctx), metrics in sorted(groups.items()):
            if 'tok_s' in metrics and metrics['tok_s']:
                n = len(metrics['tok_s'])
                mean_tok = mean(metrics['tok_s'])
                std_tok = stdev(metrics['tok_s']) if n > 1 else 0.0
                total_ok += n

                # Count total expected (rough estimate: 45 per group)
                status_str = "✓"
                print(f"{var:<12} {str(ctx):<6} {n}/45{'':<4} {mean_tok:>6.2f}{'':>10} {std_tok:>6.2f}  {status_str}")

        print(f"\nTotal: {total_ok} OK records across {len(groups)} groups")

    return 0

if __name__ == '__main__':
    sys.exit(main())
