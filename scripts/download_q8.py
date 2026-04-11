#!/usr/bin/env python3
"""
download_q8.py — Download Llama-3.2-3B-Instruct Q8_0.gguf to C:/temp/llama3_2_3b_gguf/

Usage:
    py -3 scripts/download_q8.py
"""
import urllib.request
import sys
from pathlib import Path

DEST = Path("C:/temp/llama3_2_3b_gguf/Q8_0.gguf")
URL  = "https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q8_0.gguf"

def progress(block_num, block_size, total):
    downloaded = block_num * block_size
    if total > 0:
        pct = min(downloaded / total * 100, 100)
        mb  = downloaded / 1_048_576
        total_mb = total / 1_048_576
        print(f"\r  {pct:5.1f}%  {mb:.0f} / {total_mb:.0f} MB", end="", flush=True)

if DEST.exists():
    print(f"Already exists: {DEST} ({DEST.stat().st_size / 1_048_576:.0f} MB)")
    sys.exit(0)

DEST.parent.mkdir(parents=True, exist_ok=True)
tmp = DEST.with_suffix(".gguf.tmp")

print(f"Downloading Q8_0 (~3.3 GB)...")
print(f"  URL : {URL}")
print(f"  Dest: {DEST}")

try:
    urllib.request.urlretrieve(URL, tmp, reporthook=progress)
    print()
    tmp.rename(DEST)
    print(f"Done: {DEST} ({DEST.stat().st_size / 1_048_576:.0f} MB)")
except Exception as e:
    print(f"\nFAILED: {e}")
    tmp.unlink(missing_ok=True)
    sys.exit(1)
