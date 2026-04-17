#!/usr/bin/env python3
"""
download_arc_boolq.py — Download ARC-Easy and BoolQ benchmark datasets.

Downloads the first 100 questions from each dataset and converts them to the
quality-eval YAML format used by quality_eval.py.

Usage:
    python3 scripts/download_arc_boolq.py              # both datasets
    python3 scripts/download_arc_boolq.py --arc-only   # only ARC-Easy
    python3 scripts/download_arc_boolq.py --boolq-only # only BoolQ
    python3 scripts/download_arc_boolq.py --count 50   # 50 questions each

Output:
    data/arc_easy_100.yaml  — 100 ARC-Easy questions (4-choice: A/B/C/D)
    data/boolq_100.yaml     — 100 BoolQ questions (yes/no)

Dataset sources (no authentication required):
    ARC-Easy: HuggingFace datasets hub (AI2 ARC, ARC-Easy test split)
    BoolQ:    HuggingFace datasets hub (SuperGLUE BoolQ, validation split)

Both YAML files use the same format as prompts/quality-eval-v1.yaml:
    prompts:
      - id: arc_001
        prompt: "..."
        answer: "A"          # letter for ARC-Easy
        answer_type: choice  # signals quality_eval.py to use choice scoring
        category: arc_easy

      - id: boolq_001
        prompt: "..."
        answer: "yes"        # or "no"
        answer_type: yesno   # signals quality_eval.py to use yesno scoring
        category: boolq
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
NUMERIC_TO_LETTER = {"1": "A", "2": "B", "3": "C", "4": "D"}

# ---------------------------------------------------------------------------
# HuggingFace dataset URLs (parquet files, no auth needed for public datasets)
# ---------------------------------------------------------------------------

# ARC-Easy test split (AI2 ARC)
ARC_EASY_URL = (
    "https://huggingface.co/datasets/allenai/ai2_arc/resolve/main"
    "/ARC-Easy/test-00000-of-00001.parquet"
)
# BoolQ validation split (SuperGLUE)
BOOLQ_URL = (
    "https://huggingface.co/datasets/google/boolq/resolve/main"
    "/data/validation-00000-of-00001.parquet"
)

# Fallback: JSON Lines versions (easier to parse without pyarrow)
ARC_EASY_JSON_URL = (
    "https://huggingface.co/datasets/allenai/ai2_arc/resolve/main"
    "/ARC-Easy/test-00000-of-00001.parquet"
)

# Alternative: use the datasets library's JSON export endpoint
# These are pre-converted JSONL files from the datasets viewer API
ARC_VIEWER_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=allenai%2Fai2_arc&config=ARC-Easy&split=test&offset=0&length=100"
)
BOOLQ_VIEWER_URL = (
    "https://datasets-server.huggingface.co/rows"
    "?dataset=google%2Fboolq&config=boolq&split=validation&offset=0&length=100"
)


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def fetch_json(url: str, timeout: int = 60) -> dict:
    """Fetch a URL and parse as JSON."""
    print(f"  Fetching: {url[:80]}...")
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# ARC-Easy
# ---------------------------------------------------------------------------

def download_arc_easy(count: int = 100) -> list[dict]:
    """Download ARC-Easy test questions via HuggingFace datasets viewer API."""
    print(f"\n[ARC-Easy] Downloading {count} questions from test split...")

    url = (
        f"https://datasets-server.huggingface.co/rows"
        f"?dataset=allenai%2Fai2_arc&config=ARC-Easy&split=test"
        f"&offset=0&length={count}"
    )
    data = fetch_json(url)
    rows = data.get("rows", [])
    print(f"  Got {len(rows)} rows")

    prompts = []
    for i, row_obj in enumerate(rows[:count], 1):
        row = row_obj.get("row", row_obj)  # viewer API wraps in {"row": {...}}

        question = row["question"]
        choices_obj = row["choices"]

        # choices is {"text": [...], "label": [...]}; ARC sometimes uses
        # numeric labels, so normalize everything to A/B/C/D.
        raw_labels = choices_obj["label"]
        labels = [NUMERIC_TO_LETTER.get(str(lbl), str(lbl)) for lbl in raw_labels]
        texts = choices_obj["text"]
        correct_label = NUMERIC_TO_LETTER.get(str(row["answerKey"]), str(row["answerKey"]))

        # Build prompt
        choice_lines = "  ".join(f"{lbl}) {txt}" for lbl, txt in zip(labels, texts))
        prompt = (
            f"Question: {question}\n"
            f"Choices: {choice_lines}\n"
            f"Answer with only the letter (A, B, C, or D):"
        )

        prompts.append({
            "id": f"arc_{i:03d}",
            "prompt": prompt,
            "answer": correct_label,
            "answer_type": "choice",
            "category": "arc_easy",
        })

    print(f"  Parsed {len(prompts)} ARC-Easy questions (correct labels: "
          f"{', '.join(set(p['answer'] for p in prompts[:5]))}...)")
    return prompts


# ---------------------------------------------------------------------------
# BoolQ
# ---------------------------------------------------------------------------

def download_boolq(count: int = 100) -> list[dict]:
    """Download BoolQ validation questions.

    Tries HuggingFace datasets library first (most reliable), then falls back
    to the viewer API.
    """
    print(f"\n[BoolQ] Downloading {count} questions from validation split...")

    rows = []

    # Attempt 1: HuggingFace datasets library (preferred)
    try:
        from datasets import load_dataset
        print("  Using HuggingFace datasets library...")
        ds = load_dataset("super_glue", "boolq", split="validation", streaming=True)
        for i, item in enumerate(ds):
            if i >= count:
                break
            rows.append(item)
        print(f"  Loaded {len(rows)} rows via datasets library")
    except Exception as e:
        print(f"  datasets library failed ({e}), trying viewer API...")
        rows = []

    # Attempt 2: HuggingFace viewer API (fallback)
    if not rows:
        url = (
            f"https://datasets-server.huggingface.co/rows"
            f"?dataset=super_glue&config=boolq&split=validation"
            f"&offset=0&length={count}"
        )
        try:
            data = fetch_json(url)
            raw_rows = data.get("rows", [])
            rows = [r.get("row", r) for r in raw_rows]
            print(f"  Loaded {len(rows)} rows via viewer API")
        except Exception as e:
            raise RuntimeError(f"Both BoolQ download methods failed. Last error: {e}")

    prompts = []
    for i, row in enumerate(rows[:count], 1):
        passage  = row["passage"]
        question = row["question"]
        # datasets lib: label=0→False→"no", label=1→True→"yes"
        # viewer API: answer=True/False
        raw_answer = row.get("label", row.get("answer", None))
        if raw_answer is None:
            continue
        answer = "yes" if raw_answer in (True, 1) else "no"

        # Truncate very long passages to stay well under 512-token context limit
        # BoolQ passages average 120 words; truncate at 600 chars (~150 tokens) for safety
        if len(passage) > 600:
            passage = passage[:597] + "..."

        prompt = (
            f"Passage: {passage}\n"
            f"Question: {question}\n"
            f"Answer with only yes or no:"
        )

        prompts.append({
            "id": f"boolq_{i:03d}",
            "prompt": prompt,
            "answer": answer,
            "answer_type": "yesno",
            "category": "boolq",
        })

    yes_count = sum(1 for p in prompts if p["answer"] == "yes")
    print(f"  Parsed {len(prompts)} BoolQ questions "
          f"(yes={yes_count}, no={len(prompts)-yes_count})")
    return prompts


# ---------------------------------------------------------------------------
# YAML writer (no PyYAML dependency)
# ---------------------------------------------------------------------------

def write_yaml(prompts: list[dict], output_path: Path, description: str) -> None:
    """Write prompts list to YAML format compatible with quality_eval.py."""
    lines = [
        f"# {description}",
        f"# Generated by scripts/download_arc_boolq.py",
        f"# {len(prompts)} questions",
        f"# answer_type: choice (A/B/C/D) or yesno (yes/no)",
        f"# Scored by quality_eval.py using choice/yesno answer type handlers",
        "",
        "prompts:",
    ]

    for p in prompts:
        # Escape prompt for YAML (use block scalar to avoid quote escaping issues)
        prompt_escaped = p["prompt"].replace("\\", "\\\\")
        # Replace internal double quotes to avoid YAML parse issues
        prompt_escaped = prompt_escaped.replace('"', '\\"')

        lines.append(f'  - id: {p["id"]}')
        lines.append(f'    prompt: "{prompt_escaped}"')
        lines.append(f'    answer: "{p["answer"]}"')
        lines.append(f'    answer_type: {p["answer_type"]}')
        lines.append(f'    category: {p["category"]}')
        lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Saved: {output_path} ({output_path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download ARC-Easy and BoolQ benchmark datasets for quality_eval.py"
    )
    parser.add_argument(
        "--count", type=int, default=100,
        help="Number of questions to download per dataset (default: 100)"
    )
    parser.add_argument("--arc-only",   action="store_true", help="Only download ARC-Easy")
    parser.add_argument("--boolq-only", action="store_true", help="Only download BoolQ")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download even if output files already exist"
    )
    args = parser.parse_args()

    do_arc   = not args.boolq_only
    do_boolq = not args.arc_only

    arc_output   = DATA_DIR / f"arc_easy_{args.count}.yaml"
    boolq_output = DATA_DIR / f"boolq_{args.count}.yaml"

    # Check existing files
    if do_arc and arc_output.exists() and not args.force:
        print(f"  ARC-Easy already exists: {arc_output} (use --force to re-download)")
        do_arc = False
    if do_boolq and boolq_output.exists() and not args.force:
        print(f"  BoolQ already exists: {boolq_output} (use --force to re-download)")
        do_boolq = False

    if not do_arc and not do_boolq:
        print("  Both datasets already downloaded. Run with --force to refresh.")
        return 0

    success = True

    if do_arc:
        try:
            arc_prompts = download_arc_easy(count=args.count)
            write_yaml(
                arc_prompts, arc_output,
                f"ARC-Easy test split — {args.count} questions, 4-choice (A/B/C/D)"
            )
        except Exception as e:
            print(f"\nERROR downloading ARC-Easy: {e}", file=sys.stderr)
            import traceback; traceback.print_exc()
            success = False

    if do_boolq:
        try:
            boolq_prompts = download_boolq(count=args.count)
            write_yaml(
                boolq_prompts, boolq_output,
                f"BoolQ validation split — {args.count} questions, yes/no"
            )
        except Exception as e:
            print(f"\nERROR downloading BoolQ: {e}", file=sys.stderr)
            import traceback; traceback.print_exc()
            success = False

    if success:
        print(f"\n=== Done ===")
        if arc_output.exists():
            print(f"  ARC-Easy: {arc_output}")
        if boolq_output.exists():
            print(f"  BoolQ:    {boolq_output}")
        print(f"\nNext: python3 scripts/quality_eval.py --dataset data/arc_easy_100.yaml --tag arc_easy")
        print(f"      python3 scripts/quality_eval.py --dataset data/boolq_100.yaml --tag boolq")

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
