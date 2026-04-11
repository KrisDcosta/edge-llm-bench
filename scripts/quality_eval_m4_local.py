#!/usr/bin/env python3
"""
quality_eval_m4_local.py — Quality evaluation for GGUF quantization on M4 Mac (local).

Runs factual QA prompts on each quantization variant using llama-cli locally
and scores answers against deterministic ground-truth strings.

Usage:
    # All benchmarks on all variants:
    python3 scripts/quality_eval_m4_local.py --all

    # Specific variants:
    python3 scripts/quality_eval_m4_local.py --dataset data/arc_easy_100.yaml Q2_K Q4_K_M Q6_K Q8_0

    # All available datasets:
    python3 scripts/quality_eval_m4_local.py --list-benchmarks

    # Dry run:
    python3 scripts/quality_eval_m4_local.py --all --dry-run

Output:
    results/quality_metrics_m4.json — per-variant accuracy and detailed results
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
MODELS_DIR = PROJECT_ROOT / "local-models" / "llama3_2_3b_gguf"
DEFAULT_PROMPTS_FILE = PROJECT_ROOT / "prompts" / "quality-eval-v1.yaml"
OUTPUT_FILE = PROJECT_ROOT / "results" / "quality_metrics_m4.json"

ALL_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0", "F16"]

# Model paths (local)
def get_model_path(variant: str) -> Path:
    return MODELS_DIR / f"Llama-3.2-3B-Instruct-{variant}.gguf"

DEFAULT_TAG = "custom_v1"

# Model sizes in GB (approx)
MODEL_SIZES_GB = {
    "Q2_K": 1.3,
    "Q3_K_M": 1.6,
    "Q4_K_S": 1.8,
    "Q4_K_M": 1.9,
    "Q5_K_M": 2.2,
    "Q6_K": 2.5,
    "Q8_0": 3.2,
    "F16": 6.0,
}

# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def format_llama3_instruct(user_message: str) -> str:
    """Wrap a user message in the Llama-3.2-3B-Instruct chat template."""
    return (
        "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_message}"
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts_from_yaml(yaml_path: Path) -> list[dict]:
    """Load prompts from a YAML file."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {yaml_path}")

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    prompts: list[dict] = []

    # Handle different YAML structures
    if isinstance(data, dict) and "prompts" in data:
        # Structure: prompts: [...]
        prompts = data["prompts"]
    elif isinstance(data, list):
        # Structure: [...]
        prompts = data
    else:
        raise ValueError(f"Unexpected YAML structure in {yaml_path}")

    # Ensure each prompt has required fields
    for p in prompts:
        p.setdefault("answer_type", "substring")

    return prompts


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_substring(model_output: str, expected: str) -> bool:
    """Case-insensitive: expected appears anywhere in output."""
    return expected.lower().strip() in model_output.lower()


def score_choice(model_output: str, expected: str) -> bool:
    """Extract a multiple-choice letter (A/B/C/D) from model output."""
    letter = expected.upper().strip()
    if letter not in ("A", "B", "C", "D"):
        return score_substring(model_output, expected)

    out = model_output.strip()

    # Pattern 1: output starts with the letter
    if re.match(rf"^{letter}(?:[.):\s]|$)", out, re.IGNORECASE):
        return True

    # Pattern 2: "Answer: X"
    if re.search(rf"\bAnswer\s*(?:is\s*)?:?\s*{letter}\b", out, re.IGNORECASE):
        return True

    # Pattern 3: "(X)" or "X)"
    if re.search(rf"\b\(?{letter}[.):]?\b", out, re.IGNORECASE):
        return True

    # Pattern 4: "The answer is X"
    if re.search(rf"\bthe\s+(?:correct\s+)?answer\s+is\s+{letter}\b", out, re.IGNORECASE):
        return True

    return False


def score_yesno(model_output: str, expected: str) -> bool:
    """Extract yes/no from model output."""
    target = expected.lower().strip()
    if target not in ("yes", "no"):
        return score_substring(model_output, expected)

    out = model_output.strip().lower()

    # Pattern 1: output starts with target word
    if re.match(rf"^{target}\b", out):
        return True

    # Pattern 2: "answer: yes/no"
    if re.search(rf"\banswer\s*(?:is\s*)?:?\s*{target}\b", out):
        return True

    # Pattern 3: standalone target word in short output
    if len(out) <= 20 and re.search(rf"\b{target}\b", out):
        return True

    # Pattern 4: first word is the target
    first_word = re.split(r"[\s.,!?]", out)[0].strip()
    if first_word == target:
        return True

    return False


def score_answer(model_output: str, expected: str, answer_type: str) -> bool:
    """Dispatch to the correct scoring function."""
    if answer_type == "choice":
        return score_choice(model_output, expected)
    elif answer_type == "yesno":
        return score_yesno(model_output, expected)
    else:
        return score_substring(model_output, expected)


_LOG_KEYWORDS = (
    "llama_", "ggml_", "common_perf", "load time", "eval time",
    "prompt eval", "total time", "main: ", "[New Thread",
    "warning:", "error:",
)


def extract_model_answer(raw_output: str) -> str:
    """Extract the generated text from llama-cli output."""
    # Find "assistant" marker and grab text after it
    match = re.search(r"assistant\s*\n\n", raw_output, re.IGNORECASE)
    if match:
        after_match = raw_output[match.end():]
        # Take first non-empty line/section
        lines = [line.strip() for line in after_match.split('\n') if line.strip()]
        if lines:
            return lines[0][:500]

    # Fallback: filter out log lines and get first substantial text
    filtered = "\n".join(
        line for line in raw_output.splitlines()
        if not any(kw in line for kw in _LOG_KEYWORDS)
    )
    lines = [line.strip() for line in filtered.split('\n') if line.strip()]
    if lines:
        return lines[0][:500]

    return ""


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def run_inference(
    prompt: str,
    model_path: Path,
    n_tokens: int = 32,
    dry_run: bool = False,
) -> str | None:
    """Run one inference locally. Returns model output text or None on failure."""
    formatted_prompt = format_llama3_instruct(prompt)

    cmd = [
        "llama-cli",
        "-m", str(model_path),
        "-c", "2048",
        "-n", str(n_tokens),
        "--temp", "0.0",
        "--seed", "42",
        "-t", "4",
        "--log-disable",  # Reduce verbose logging
    ]

    if dry_run:
        print(f"    [DRY RUN] {' '.join(cmd[:5])}...")
        return "DRY_RUN_OUTPUT"

    try:
        result = subprocess.run(
            cmd,
            input=formatted_prompt,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return extract_model_answer(result.stdout + result.stderr)
    except subprocess.TimeoutExpired:
        return None
    except Exception as e:
        print(f"    ERROR: {e}")
        return None


# ---------------------------------------------------------------------------
# Variant evaluation
# ---------------------------------------------------------------------------

def evaluate_variant(
    variant: str,
    prompts: list[dict],
    tag: str,
    dry_run: bool = False,
) -> dict:
    """Run all eval prompts for one variant."""
    model_path = get_model_path(variant)

    if not model_path.exists():
        return {
            "variant": variant,
            "tag": tag,
            "status": "not_found",
            "accuracy_pct": None,
            "correct": None,
            "total": len(prompts),
        }

    print(f"\n  [{variant}] Evaluating {len(prompts)} prompts (tag={tag})...")
    per_question: list[dict] = []
    correct_count = 0

    for i, p in enumerate(prompts, 1):
        prompt_id = p["id"]
        prompt_text = p["prompt"]
        expected = p["answer"]
        category = p.get("category", "unknown")
        answer_type = p.get("answer_type", "substring")

        n_tokens = 8 if answer_type in ("choice", "yesno") else 32

        print(f"    [{i:3d}/{len(prompts)}] {prompt_id:30s} ({answer_type:10s}) ... ", end="", flush=True)

        try:
            model_output = run_inference(prompt_text, model_path, n_tokens=n_tokens, dry_run=dry_run)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"ERROR: {e}")
            model_output = None

        if model_output is None:
            print("TIMEOUT")
            per_question.append({
                "prompt_id": prompt_id,
                "category": category,
                "answer_type": answer_type,
                "expected": expected,
                "model_output": None,
                "correct": False,
                "status": "timeout",
            })
            continue

        is_correct = score_answer(model_output, expected, answer_type)
        correct_count += int(is_correct)
        status_str = "✓" if is_correct else "✗"
        print(f"{status_str}  (got={model_output[:40]!r})")

        per_question.append({
            "prompt_id": prompt_id,
            "category": category,
            "answer_type": answer_type,
            "expected": expected,
            "model_output": model_output[:200],
            "correct": is_correct,
            "status": "success",
        })

        if not dry_run:
            time.sleep(0.5)

    total = len(prompts)
    accuracy_pct = round(100.0 * correct_count / total, 1) if total > 0 else None

    # Wilson 95% CI
    wilson_ci = None
    if total > 0 and accuracy_pct is not None:
        p_hat = correct_count / total
        z = 1.96
        denom = 1 + z * z / total
        center = (p_hat + z * z / (2 * total)) / denom
        margin = (z * (p_hat * (1 - p_hat) / total + z * z / (4 * total * total)) ** 0.5) / denom
        wilson_ci = round(margin * 100, 1)

    print(f"  [{variant}] Accuracy: {correct_count}/{total} = {accuracy_pct}%"
          f"{f' ± {wilson_ci}%' if wilson_ci else ''} (95% Wilson CI)")

    # Per-category breakdown
    categories: dict[str, dict] = {}
    for q in per_question:
        cat = q["category"]
        if cat not in categories:
            categories[cat] = {"correct": 0, "total": 0}
        categories[cat]["total"] += 1
        if q["correct"]:
            categories[cat]["correct"] += 1

    return {
        "variant": variant,
        "tag": tag,
        "status": "success",
        "model_size_gb": MODEL_SIZES_GB.get(variant, 0.0),
        "accuracy_pct": accuracy_pct,
        "wilson_ci_95_pct": wilson_ci,
        "correct": correct_count,
        "total": total,
        "per_category": {
            cat: {
                "accuracy_pct": round(100.0 * v["correct"] / v["total"], 1),
                **v,
            }
            for cat, v in categories.items()
        },
        "per_question": per_question,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Quality evaluation for GGUF quantization on M4 Mac"
    )
    parser.add_argument(
        "variants", nargs="*", metavar="VARIANT",
        help="Specific variants to evaluate (e.g. Q4_K_M Q8_0). Default: all."
    )
    parser.add_argument(
        "--all", dest="run_all", action="store_true",
        help="Evaluate all variants"
    )
    parser.add_argument(
        "--dataset", default=None, metavar="PATH",
        help="Path to YAML dataset file (e.g. data/arc_easy_100.yaml). Default: prompts/quality-eval-v1.yaml"
    )
    parser.add_argument(
        "--tag", default=None, metavar="TAG",
        help="Tag for this eval run. Default: inferred from filename."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show commands without running inference"
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_FILE),
        help="Output JSON file"
    )
    parser.add_argument(
        "--list-benchmarks", action="store_true",
        help="List all available YAML benchmark files and exit"
    )
    args = parser.parse_args()

    # --list-benchmarks
    if args.list_benchmarks:
        data_dir = PROJECT_ROOT / "data"
        yaml_files = sorted(data_dir.glob("*.yaml"))
        if not yaml_files:
            print("No YAML benchmark files found in data/")
            return 0
        print(f"Available benchmark datasets in {data_dir}:")
        for yf in yaml_files:
            try:
                with open(yf) as f:
                    content = f.read()
                    n = content.count("- id:")
                    print(f"  {yf.name:<35}  {n:>4} questions")
            except Exception:
                print(f"  {yf.name}")
        print(f"\nUsage: python3 scripts/quality_eval_m4_local.py --dataset data/<file>.yaml")
        return 0

    # Determine dataset and tag
    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.is_absolute():
            dataset_path = PROJECT_ROOT / dataset_path
        tag = args.tag or dataset_path.stem.replace("-", "_")
    else:
        dataset_path = DEFAULT_PROMPTS_FILE
        tag = args.tag or DEFAULT_TAG

    # Determine variants
    if args.run_all or not args.variants:
        variants = ALL_VARIANTS
    else:
        variants = args.variants
        for v in variants:
            if v not in MODEL_SIZES_GB:
                print(f"ERROR: Unknown variant {v!r}. Valid: {', '.join(sorted(ALL_VARIANTS))}")
                return 1

    # Load prompts
    try:
        prompts = load_prompts_from_yaml(dataset_path)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1

    if not prompts:
        print(f"ERROR: No prompts loaded from {dataset_path}")
        return 1

    # Show configuration
    answer_types = set(p.get("answer_type", "substring") for p in prompts)
    print(f"\n=== M4 Mac Quality Evaluation ===")
    print(f"  Dataset:      {dataset_path.name} ({len(prompts)} questions)")
    print(f"  Answer types: {', '.join(sorted(answer_types))}")
    print(f"  Tag:          {tag}")
    print(f"  Variants:     {', '.join(variants)}")
    print(f"  Mode:         {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    # Load existing results
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if output_path.exists():
        try:
            existing = json.loads(output_path.read_text())
        except Exception:
            pass

    # Evaluate each variant
    all_results: dict[str, dict] = dict(existing)
    for variant in variants:
        result_key = f"{tag}:{variant}"
        result = evaluate_variant(variant, prompts, tag, dry_run=args.dry_run)
        all_results[result_key] = result

        # Save after each variant
        output_path.write_text(json.dumps(all_results, indent=2))

    # Final summary
    print(f"\n=== Summary (tag={tag}) ===")
    print(f"{'Variant':<10} {'Size (GB)':>10} {'Accuracy':>10} {'±CI':>6} {'Correct':>9} {'Total':>7}  Status")
    print("-" * 80)
    for v in variants:
        r = all_results.get(f"{tag}:{v}", {})
        size_gb = r.get("model_size_gb", 0)
        acc = r.get("accuracy_pct")
        ci = r.get("wilson_ci_95_pct")
        corr = r.get("correct")
        tot = r.get("total", len(prompts))
        status = r.get("status", "?")
        size_str = f"{size_gb:.1f}" if size_gb else "?"
        acc_str = f"{acc}%" if acc is not None else "N/A"
        ci_str = f"±{ci}%" if ci is not None else "    "
        corr_str = str(corr) if corr is not None else "N/A"
        print(f"{v:<10} {size_str:>10} {acc_str:>10} {ci_str:>6} {corr_str:>9} {tot:>7}  {status}")

    print(f"\nResults saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
