#!/usr/bin/env python3
"""
download_wikitext2.py — Download WikiText-2 test split for perplexity evaluation.

Usage:
    python3 scripts/download_wikitext2.py              # full test set → data/wikitext2_full.txt
    python3 scripts/download_wikitext2.py --sample     # 12K char sample (legacy) → data/wikitext2_sample.txt
    python3 scripts/download_wikitext2.py --output /path/to/file.txt

Output (default — full corpus):
    data/wikitext2_full.txt — full WikiText-2 test split (~1.1MB, ~285K tokens)
    This is the standard corpus used in GPTQ, AWQ, GGML and llama.cpp PPL benchmarks.
    Fine-grained comparisons between quantization levels are only valid with the
    full corpus; the 12K sample produces noise-dominated results.

Output (--sample mode, legacy):
    data/wikitext2_sample.txt — 12K char slice (~3K tokens); kept for backward compat.
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FULL_OUTPUT   = PROJECT_ROOT / "data" / "wikitext2_full.txt"
DEFAULT_SAMPLE_OUTPUT = PROJECT_ROOT / "data" / "wikitext2_sample.txt"

# WikiText-2 raw test split — pytorch examples repo (plain .txt, no parquet parsing needed)
WIKITEXT2_URL = (
    "https://raw.githubusercontent.com/pytorch/examples/main"
    "/word_language_model/data/wikitext-2/test.txt"
)

GUTENBERG_FALLBACK_URL = "https://www.gutenberg.org/files/1342/1342-0.txt"


def download_text(url: str, timeout: int = 120) -> str:
    """Download a URL and return as UTF-8 string."""
    print(f"  Downloading: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def clean_wikitext(raw: str) -> str:
    """Remove WikiText markup (section headers) to get clean prose paragraphs.

    Preserves blank lines between paragraphs so llama-perplexity can segment
    the text at natural boundaries (matches standard PPL eval methodology).
    """
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        # Skip section headers (= Title =, == Sub ==, etc.)
        if re.match(r"^=+\s.*\s=+$", stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download WikiText-2 test split for perplexity evaluation"
    )
    parser.add_argument(
        "--output", default=None,
        help="Output file path (default: data/wikitext2_full.txt or data/wikitext2_sample.txt)"
    )
    parser.add_argument(
        "--sample", action="store_true",
        help="Legacy mode: extract only 12,000 chars (~3K tokens) instead of full corpus"
    )
    parser.add_argument(
        "--chars", type=int, default=12000,
        help="Character count to extract in --sample mode (default: 12000)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if output file already exists"
    )
    args = parser.parse_args()

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    elif args.sample:
        output_path = DEFAULT_SAMPLE_OUTPUT
    else:
        output_path = DEFAULT_FULL_OUTPUT

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not args.force:
        size = output_path.stat().st_size
        print(f"  File already exists: {output_path} ({size:,} bytes, ~{size//5:,} tokens)")
        print("  Use --force to re-download.")
        return 0

    # Download
    raw_text = None
    try:
        raw_text = download_text(WIKITEXT2_URL)
        print(f"  Downloaded {len(raw_text):,} chars from WikiText-2 source")
    except Exception as e:
        print(f"  WikiText-2 source failed: {e}")

    if raw_text is None:
        try:
            print("  Falling back to Project Gutenberg (Pride and Prejudice)...")
            raw_text = download_text(GUTENBERG_FALLBACK_URL)
            print(f"  Downloaded {len(raw_text):,} chars from Gutenberg fallback")
        except Exception as e:
            print(f"ERROR: All download sources failed: {e}", file=sys.stderr)
            print("  Manually place any plain text file at:", output_path, file=sys.stderr)
            return 1

    # Clean markup
    cleaned = clean_wikitext(raw_text)

    # Apply sample limit only in --sample mode
    if args.sample:
        output_text = cleaned[:args.chars]
        print(f"  [SAMPLE MODE] Using first {len(output_text):,} chars (~{len(output_text)//5:,} tokens)")
    else:
        output_text = cleaned
        print(f"  [FULL CORPUS] Using all {len(output_text):,} chars (~{len(output_text)//5:,} tokens)")
        print(f"  NOTE: Full WikiText-2 test set enables statistically valid PPL comparisons.")

    # Write output
    output_path.write_text(output_text, encoding="utf-8")
    size = output_path.stat().st_size
    print(f"  Saved to: {output_path} ({size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
