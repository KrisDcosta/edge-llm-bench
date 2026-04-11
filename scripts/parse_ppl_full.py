#!/usr/bin/env python3
"""
Parse full-corpus WikiText-2 perplexity results from device output files.

Usage:
    python3 scripts/parse_ppl_full.py results/
    
    This script:
    1. Reads ppl_full_*.txt files from the results directory (pulled from device)
    2. Extracts the "Final estimate" perplexity value from each
    3. Updates results/perplexity_scores.json with full-corpus values
    4. Preserves existing partial-corpus entries
"""

import re
import json
import sys
from pathlib import Path

def extract_ppl_from_file(filepath):
    """Extract perplexity value from device output file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Look for "Final estimate ... : X.XXXX"
        match = re.search(r'Final estimate.*?:\s*([\d.]+)', content, re.IGNORECASE | re.DOTALL)
        if match:
            ppl_value = float(match.group(1))
            return ppl_value
        else:
            print(f"Warning: Could not find 'Final estimate' in {filepath}")
            return None
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return None

def main():
    results_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("results")
    
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
        ppl_value = extract_ppl_from_file(ppl_file)
        
        if ppl_value is not None:
            results[variant] = ppl_value
            print(f"✓ {variant}: {ppl_value:.4f}")
        else:
            print(f"✗ {variant}: FAILED TO PARSE")
    
    if not results:
        print("No results were successfully parsed.")
        sys.exit(1)
    
    # Load existing perplexity scores
    scores_file = results_dir / "perplexity_scores.json"
    if scores_file.exists():
        with open(scores_file, 'r') as f:
            existing_scores = json.load(f)
    else:
        existing_scores = {}
    
    # Update with new full-corpus values
    for variant, ppl_value in results.items():
        if variant not in existing_scores:
            existing_scores[variant] = {}
        
        existing_scores[variant]["perplexity"] = ppl_value
        existing_scores[variant]["perplexity_status"] = "success"
        existing_scores[variant]["corpus"] = "wikitext2_full"
        existing_scores[variant]["corpus_bytes"] = 1268800  # ~285K tokens ≈ 1.2 MB
    
    # Write updated scores
    with open(scores_file, 'w') as f:
        json.dump(existing_scores, f, indent=2)
    
    print(f"\n✓ Updated {scores_file}")
    print(f"  Total variants with full-corpus PPL: {len(results)}")
    
    # Summary
    print("\n=== Final PPL Summary ===")
    for variant in sorted(existing_scores.keys()):
        if "perplexity" in existing_scores[variant]:
            ppl = existing_scores[variant]["perplexity"]
            corpus = existing_scores[variant].get("corpus", "?")
            print(f"  {variant:12} {ppl:7.4f} (corpus: {corpus})")

if __name__ == "__main__":
    main()
