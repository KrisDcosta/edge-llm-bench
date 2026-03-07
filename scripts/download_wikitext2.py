#!/usr/bin/env python3
"""
download_wikitext2.py — Download WikiText-2 test split and extract a plain-text sample.

Usage:
    python3 scripts/download_wikitext2.py              # saves to data/wikitext2_sample.txt
    python3 scripts/download_wikitext2.py --tokens 2048  # first N raw chars (approx tokens)

Output:
    data/wikitext2_sample.txt — raw UTF-8 text suitable for llama-perplexity -f

The WikiText-2 test split is the standard corpus used in GPTQ, AWQ, and GGML
quantization papers, allowing direct comparison of perplexity numbers.
"""

import argparse
import re
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "wikitext2_sample.txt"

# WikiText-2 raw test split — hosted on HuggingFace datasets as a plain text file
# This is the tokenized-then-detokenized version used in standard PPL benchmarks
WIKITEXT2_URLS = [
    # Primary: HuggingFace raw file
    "https://huggingface.co/datasets/wikitext/resolve/main/wikitext-2-raw-v1/test-00000-of-00001.parquet",
    # Fallback: Stephen Merity's original hosting (txt format)
    "https://raw.githubusercontent.com/pytorch/examples/main/word_language_model/data/wikitext-2/test.txt",
]

# Simpler fallback: pytorch word_language_model test split (smaller but same domain)
FALLBACK_TEXT_URL = "https://raw.githubusercontent.com/pytorch/examples/main/word_language_model/data/wikitext-2/test.txt"


def download_text(url: str, timeout: int = 60) -> str:
    """Download a URL and return as UTF-8 string."""
    print(f"  Downloading: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


def clean_wikitext(raw: str) -> str:
    """Remove WikiText markup (section headers, blank lines) to get clean prose."""
    lines = []
    for line in raw.splitlines():
        stripped = line.strip()
        # Skip section headers (= Title =) and empty lines
        if re.match(r"^=+\s.*\s=+$", stripped):
            continue
        if not stripped:
            continue
        lines.append(stripped)
    return " ".join(lines)


def extract_sample(text: str, approx_chars: int) -> str:
    """Extract approximately `approx_chars` characters from the text."""
    return text[:approx_chars]


def main() -> int:
    parser = argparse.ArgumentParser(description="Download WikiText-2 test split for perplexity evaluation")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output file path")
    parser.add_argument(
        "--chars", type=int, default=12000,
        help="Approximate character count to extract (default: 12000 ≈ 2048 tokens for Llama tokenizer)"
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists():
        print(f"  Sample already exists at {output_path} ({output_path.stat().st_size} bytes)")
        print("  Delete it to re-download.")
        return 0

    # Try to download WikiText-2 test split
    raw_text = None
    for url in [FALLBACK_TEXT_URL]:
        try:
            raw_text = download_text(url)
            print(f"  Downloaded {len(raw_text)} chars")
            break
        except Exception as e:
            print(f"  Failed: {e}")
            continue

    if raw_text is None:
        # Last resort: use a short sample of openly-licensed public domain text
        # (Pride and Prejudice opening — guaranteed UTF-8, clean text for PPL)
        try:
            print("  Falling back to Project Gutenberg (Pride and Prejudice)...")
            raw_text = download_text(
                "https://www.gutenberg.org/files/1342/1342-0.txt"
            )
        except Exception as e:
            print(f"ERROR: All download sources failed: {e}", file=sys.stderr)
            print("  Manually place any plain text file at:", output_path, file=sys.stderr)
            return 1

    # Clean and extract sample
    cleaned = clean_wikitext(raw_text)
    sample = extract_sample(cleaned, args.chars)

    # Write to output
    output_path.write_text(sample, encoding="utf-8")
    print(f"  Saved {len(sample)} chars to {output_path}")
    print(f"  (Approximate Llama tokenization: ~{len(sample) // 5} tokens)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
