#!/usr/bin/env python3
"""
Parse full-corpus WikiText-2 perplexity results from device output files.

Usage:
    python3 scripts/parse_ppl_full.py results/pixel_6a_ppl_final \
        --scores-file results/perplexity_scores.json --require-all
    
    This script:
    1. Reads ppl_full_*.txt files from the results directory (pulled from device)
    2. Extracts the "Final estimate" perplexity value from each
    3. Updates results/perplexity_scores.json with full-corpus values
    4. Preserves extra metadata such as chunk count and standard error
"""

import argparse
import re
import json
import sys
from pathlib import Path

VARIANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
TOKENS_APPROX = 285000


def extract_ppl_from_file(filepath):
    """Extract final perplexity, standard error, and chunk count."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()

        match = re.search(
            r'Final estimate:\s*PPL\s*=\s*([0-9.]+)\s*\+/-\s*([0-9.]+)',
            content,
            re.IGNORECASE,
        )
        if not match:
            print(f"Warning: Could not find 'Final estimate' in {filepath}")
            return None

        chunks = re.search(r'calculating perplexity over\s+(\d+)\s+chunks', content)
        n_ctx = re.search(r'n_ctx=(\d+)', content)
        return {
            "perplexity": float(match.group(1)),
            "standard_error": float(match.group(2)),
            "n_chunks": int(chunks.group(1)) if chunks else None,
            "n_ctx": int(n_ctx.group(1)) if n_ctx else None,
        }
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Parse full-corpus WikiText-2 PPL outputs")
    parser.add_argument("results_dir", nargs="?", default="results/pixel_6a_ppl_final")
    parser.add_argument("--scores-file", default="results/perplexity_scores.json")
    parser.add_argument("--require-all", action="store_true", help="fail unless all 7 canonical variants are parsed")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    scores_file = Path(args.scores_file)

    # Find all ppl_full_*.txt files
    ppl_files = list(results_dir.glob("ppl_full_*.txt"))
    
    if not ppl_files:
        print(f"No ppl_full_*.txt files found in {results_dir}")
        print("Expected files: ppl_full_Q2_K.txt, ppl_full_Q3_K_M.txt, etc.")
        sys.exit(1)
    
    # Extract variant from filename and perplexity from content
    results = {}
    for ppl_file in sorted(ppl_files):
        # Extract variant from filename: ppl_full_Q4_K_M.txt -> Q4_K_M
        match = re.search(r'ppl_full_(.+)\.txt', ppl_file.name)
        if not match:
            print(f"Warning: Could not parse variant from {ppl_file.name}")
            continue

        variant = match.group(1)
        parsed = extract_ppl_from_file(ppl_file)

        if parsed is not None:
            parsed["source_file"] = str(ppl_file)
            results[variant] = parsed
            print(f"✓ {variant}: {parsed['perplexity']:.4f} +/- {parsed['standard_error']:.5f}")
        else:
            print(f"✗ {variant}: FAILED TO PARSE")
    
    if not results:
        print("No results were successfully parsed.")
        sys.exit(1)
    
    if args.require_all:
        missing = sorted(set(VARIANT_ORDER) - set(results))
        if missing:
            print(f"Missing full-corpus PPL files for: {missing}", file=sys.stderr)
            sys.exit(1)

    if scores_file.exists():
        with open(scores_file, 'r') as f:
            existing_scores = json.load(f)
    else:
        existing_scores = {}

    # Update with new full-corpus values
    for variant, parsed in results.items():
        if variant not in existing_scores:
            existing_scores[variant] = {}

        existing_scores[variant]["perplexity"] = parsed["perplexity"]
        existing_scores[variant]["perplexity_status"] = "success"
        existing_scores[variant]["corpus"] = "wikitext2_full"
        existing_scores[variant]["tokens_approx"] = TOKENS_APPROX
        existing_scores[variant]["n_chunks"] = parsed["n_chunks"]
        existing_scores[variant]["n_ctx"] = parsed["n_ctx"]
        existing_scores[variant]["standard_error"] = parsed["standard_error"]
        existing_scores[variant]["source_file"] = parsed["source_file"]
        existing_scores[variant]["note"] = "Measured on Pixel 6a (full WikiText-2 corpus, 568 chunks)"

    # Write updated scores
    scores_file.parent.mkdir(parents=True, exist_ok=True)
    with open(scores_file, 'w') as f:
        json.dump(existing_scores, f, indent=2)
        f.write("\n")

    print(f"\n✓ Updated {scores_file}")
    print(f"  Total variants with full-corpus PPL: {len(results)}")

    # Summary
    print("\n=== Final PPL Summary ===")
    for variant in VARIANT_ORDER:
        if "perplexity" in existing_scores[variant]:
            ppl = existing_scores[variant]["perplexity"]
            corpus = existing_scores[variant].get("corpus", "?")
            print(f"  {variant:12} {ppl:7.4f} (corpus: {corpus})")

if __name__ == "__main__":
    main()
