#!/usr/bin/env python3
"""
quality_eval.py — Exact-match accuracy evaluation for GGUF quantization levels.

Runs 15 factual QA prompts on each quantization variant and scores answers
against deterministic ground-truth strings. Reports per-variant accuracy.

Usage:
    python3 scripts/quality_eval.py --all           # all downloaded variants
    python3 scripts/quality_eval.py Q4_K_M          # one variant
    python3 scripts/quality_eval.py Q2_K Q4_K_M     # specific variants
    python3 scripts/quality_eval.py --all --dry-run  # show commands, don't run

Output:
    results/quality_scores.json — per-variant accuracy and per-question results
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

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PROMPTS_FILE = PROJECT_ROOT / "prompts" / "quality-eval-v1.yaml"
OUTPUT_FILE = PROJECT_ROOT / "results" / "quality_scores.json"
DEVICE_DIR = "/data/local/tmp"
LLAMA_CLI = f"{DEVICE_DIR}/llama-completion"

GGUF_DEVICE_PATHS = {
    "Q2_K":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q2_K.gguf",
    "Q3_K_M": f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q3_K_M.gguf",
    "Q4_K_M": f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    "Q6_K":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q6_K.gguf",
    "Q8_0":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q8_0.gguf",
    "F16":    f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-F16.gguf",
}

ALL_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0", "F16"]

# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------

def _find_adb() -> str:
    import shutil
    if env := os.environ.get("ADB"):
        return env
    if shutil.which("adb"):
        return "adb"
    candidates = [
        Path.home() / "Library/Android/sdk/platform-tools/adb",
        Path("/usr/local/lib/android/sdk/platform-tools/adb"),
    ]
    if android_home := os.environ.get("ANDROID_HOME"):
        candidates.insert(0, Path(android_home) / "platform-tools/adb")
    for c in candidates:
        if c.exists():
            return str(c)
    raise RuntimeError("adb not found. Add Android SDK platform-tools to PATH or set ADB=/path/to/adb")


ADB_BIN = _find_adb()


def adb_shell(cmd: str, timeout: int = 120) -> str:
    """Run a shell command on device, return stdout+stderr as string."""
    result = subprocess.run(
        [ADB_BIN, "shell", cmd],
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout + result.stderr


def check_device() -> bool:
    """Return True if a device is connected."""
    result = subprocess.run([ADB_BIN, "devices"], capture_output=True, text=True, timeout=10)
    return "\tdevice" in result.stdout


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_quality_prompts() -> list[dict]:
    """Load quality eval prompts from YAML. Returns list of {id, prompt, answer, category}."""
    if not PROMPTS_FILE.exists():
        raise FileNotFoundError(f"Quality eval prompts not found: {PROMPTS_FILE}")

    try:
        import yaml
        with open(PROMPTS_FILE) as f:
            data = yaml.safe_load(f)
        return data.get("prompts", [])
    except ImportError:
        # Manual YAML parser for the simple structure we have
        prompts = []
        current: dict = {}
        with open(PROMPTS_FILE) as f:
            for line in f:
                if re.match(r"\s*-\s+id:\s*(.+)", line):
                    if current.get("id"):
                        prompts.append(current)
                    current = {"id": re.match(r"\s*-\s+id:\s*(.+)", line).group(1).strip()}
                elif m := re.match(r"\s+prompt:\s*\"(.+)\"", line):
                    current["prompt"] = m.group(1)
                elif m := re.match(r"\s+answer:\s*\"(.+)\"", line):
                    current["answer"] = m.group(1)
                elif m := re.match(r"\s+category:\s*(.+)", line):
                    current["category"] = m.group(1).strip()
        if current.get("id"):
            prompts.append(current)
        return prompts


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_exact_contains(model_output: str, expected_answer: str) -> bool:
    """Case-insensitive check: expected_answer appears in model_output."""
    return expected_answer.lower().strip() in model_output.lower()


def extract_model_answer(raw_output: str) -> str:
    """Extract the generated text from llama-completion output, stripping the prompt echo."""
    # llama-completion may echo the prompt; try to isolate the response
    # Look for text after the last occurrence of "Answer" or "> " or just take all output
    # after stripping llama timing lines
    lines = []
    for line in raw_output.splitlines():
        # Skip timing/log lines
        if any(kw in line for kw in ["llama_", "ggml_", "common_perf", "load time", "eval time",
                                       "prompt eval", "total time", "main: ", "[New Thread",
                                       "warning:", "error:"]):
            continue
        lines.append(line)
    return " ".join(lines).strip()


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

def run_inference(prompt: str, model_path: str, dry_run: bool = False) -> str | None:
    """Run one inference on device. Returns model output text or None on failure."""
    cmd = (
        f"LD_LIBRARY_PATH={DEVICE_DIR} {LLAMA_CLI} "
        f"-m {model_path} "
        f"-c 256 "
        f"-n 32 "
        f"--temp 0.0 "
        f"--seed 42 "
        f"-t 4 "
        f"-no-cnv "
        f"-p \"{prompt}\""
    )

    if dry_run:
        print(f"    [DRY RUN] adb shell {cmd[:80]}...")
        return "DRY_RUN_OUTPUT"

    try:
        raw = adb_shell(cmd, timeout=120)
        return extract_model_answer(raw)
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
    dry_run: bool = False,
) -> dict:
    """Run all quality eval prompts for one variant. Returns result dict."""
    model_path = GGUF_DEVICE_PATHS.get(variant)
    if not model_path:
        return {"variant": variant, "status": "unsupported", "accuracy_pct": None, "correct": None, "total": len(prompts)}

    # Verify model on device
    if not dry_run:
        check = adb_shell(f"ls {model_path} 2>/dev/null", timeout=10)
        if ".gguf" not in check:
            print(f"  [{variant}] SKIP — model not on device at {model_path}")
            return {"variant": variant, "status": "skipped_not_on_device", "accuracy_pct": None, "correct": None, "total": len(prompts)}

    print(f"\n  [{variant}] Evaluating {len(prompts)} prompts...")
    per_question: list[dict] = []
    correct_count = 0

    for i, p in enumerate(prompts, 1):
        prompt_id = p["id"]
        prompt_text = p["prompt"]
        expected = p["answer"]
        category = p.get("category", "unknown")

        print(f"    [{i:2d}/{len(prompts)}] {prompt_id} ... ", end="", flush=True)
        model_output = run_inference(prompt_text, model_path, dry_run=dry_run)

        if model_output is None:
            print("TIMEOUT")
            per_question.append({
                "prompt_id": prompt_id, "category": category,
                "expected": expected, "model_output": None,
                "correct": False, "status": "timeout",
            })
            continue

        is_correct = score_exact_contains(model_output, expected)
        correct_count += int(is_correct)
        status_str = "✓" if is_correct else "✗"
        print(f"{status_str}  (expected={expected!r}, got={model_output[:40]!r})")

        per_question.append({
            "prompt_id": prompt_id, "category": category,
            "expected": expected, "model_output": model_output[:200],
            "correct": is_correct, "status": "success",
        })

        # Small delay between inferences to avoid thermal buildup
        if not dry_run:
            time.sleep(2)

    total = len(prompts)
    accuracy_pct = round(100.0 * correct_count / total, 1) if total > 0 else None

    print(f"  [{variant}] Accuracy: {correct_count}/{total} = {accuracy_pct}%")

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
        "status": "success",
        "accuracy_pct": accuracy_pct,
        "correct": correct_count,
        "total": total,
        "per_category": {
            cat: {"accuracy_pct": round(100.0 * v["correct"] / v["total"], 1), **v}
            for cat, v in categories.items()
        },
        "per_question": per_question,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Exact-match quality evaluation for GGUF quant levels")
    parser.add_argument(
        "variants", nargs="*", metavar="VARIANT",
        help="Specific variants to evaluate (e.g. Q4_K_M Q8_0). Default: all."
    )
    parser.add_argument("--all", dest="run_all", action="store_true", help="Evaluate all variants")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without running inference")
    parser.add_argument("--output", default=str(OUTPUT_FILE), help="Output JSON file")
    args = parser.parse_args()

    # Determine variants
    if args.run_all or not args.variants:
        variants = ALL_VARIANTS
    else:
        variants = args.variants
        for v in variants:
            if v not in GGUF_DEVICE_PATHS:
                print(f"ERROR: Unknown variant {v!r}. Valid: {', '.join(ALL_VARIANTS)}")
                return 1

    # Check device
    if not args.dry_run:
        if not check_device():
            print("ERROR: No Android device connected.")
            return 1

    # Load prompts
    try:
        prompts = load_quality_prompts()
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1

    if not prompts:
        print("ERROR: No prompts loaded from quality-eval-v1.yaml")
        return 1

    print(f"\n=== Quality Evaluation ===")
    print(f"  Prompts: {len(prompts)}")
    print(f"  Variants: {', '.join(variants)}")
    print(f"  Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
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
        result = evaluate_variant(variant, prompts, dry_run=args.dry_run)
        all_results[variant] = result

        # Save after each variant (in case we crash partway)
        output_path.write_text(json.dumps(all_results, indent=2))

    # Final summary
    print(f"\n=== Summary ===")
    print(f"{'Variant':<10} {'Accuracy':>10} {'Correct':>10} {'Total':>8} {'Status'}")
    print("-" * 55)
    for v in variants:
        r = all_results.get(v, {})
        acc = r.get("accuracy_pct")
        corr = r.get("correct")
        tot = r.get("total", len(prompts))
        status = r.get("status", "?")
        acc_str = f"{acc}%" if acc is not None else "N/A"
        corr_str = str(corr) if corr is not None else "N/A"
        print(f"{v:<10} {acc_str:>10} {corr_str:>10} {tot:>8}  {status}")

    print(f"\nResults saved to: {output_path}")
    print(f"\nNext: python3 analysis/generate_figures.py <results_file>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
