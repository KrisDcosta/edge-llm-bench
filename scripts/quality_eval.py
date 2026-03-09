#!/usr/bin/env python3
"""
quality_eval.py — Exact-match accuracy evaluation for GGUF quantization levels.

Runs factual QA prompts on each quantization variant and scores answers
against deterministic ground-truth strings. Reports per-variant accuracy.

Usage:
    # Original custom 15-question eval (backward compatible):
    python3 scripts/quality_eval.py --all
    python3 scripts/quality_eval.py Q4_K_M
    python3 scripts/quality_eval.py Q2_K Q4_K_M

    # Standard benchmark datasets (ARC-Easy, BoolQ):
    python3 scripts/quality_eval.py --dataset data/arc_easy_100.yaml --tag arc_easy
    python3 scripts/quality_eval.py --dataset data/boolq_100.yaml --tag boolq
    python3 scripts/quality_eval.py --dataset data/arc_easy_100.yaml --tag arc_easy Q4_K_M Q8_0

    # imatrix variants:
    python3 scripts/quality_eval.py --dataset data/arc_easy_100.yaml --tag arc_easy --imatrix

    # Dry run (show commands without running):
    python3 scripts/quality_eval.py --all --dry-run

Output:
    results/quality_scores.json — per-variant accuracy, per-question results.
    Results are keyed by "{tag}:{variant}" (e.g. "arc_easy:Q4_K_M").
    The default custom eval uses tag "custom_v1".

Answer types (specified per-question in YAML via answer_type field):
    substring (default) — expected string must appear anywhere in output (case-insensitive)
    choice   — single letter A/B/C/D; also accepts "A)", "(A)", "Answer: A"
    yesno    — "yes" or "no"; also accepts "Yes.", "No.", "Yes,", "No,"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR   = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_PROMPTS_FILE = PROJECT_ROOT / "prompts" / "quality-eval-v1.yaml"
OUTPUT_FILE  = PROJECT_ROOT / "results" / "quality_scores.json"
DEVICE_DIR        = "/data/local/tmp"
LLAMA_CLI         = f"{DEVICE_DIR}/llama-completion"
PROMPT_DEVICE_PATH = f"{DEVICE_DIR}/eval_prompt.txt"   # temp file for per-question prompts

GGUF_DEVICE_PATHS = {
    "Q2_K":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q2_K.gguf",
    "Q3_K_M": f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q3_K_M.gguf",
    "Q4_K_M": f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    "Q6_K":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q6_K.gguf",
    "Q8_0":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q8_0.gguf",
    "F16":    f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-F16.gguf",
}

# imatrix variants (produced by requantize_imatrix.sh)
GGUF_IMATRIX_DEVICE_PATHS = {
    "Q2_K":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q2_K-imatrix.gguf",
    "Q3_K_M": f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q3_K_M-imatrix.gguf",
    "Q4_K_M": f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q4_K_M-imatrix.gguf",
    "Q6_K":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q6_K-imatrix.gguf",
    "Q8_0":   f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q8_0-imatrix.gguf",
}

ALL_VARIANTS         = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0", "F16"]
ALL_IMATRIX_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_M", "Q6_K", "Q8_0"]

DEFAULT_TAG = "custom_v1"

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


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------

def format_llama3_instruct(user_message: str) -> str:
    """Wrap a user message in the Llama-3.2-3B-Instruct chat template.

    The model was fine-tuned with this exact format; without it raw
    completion mode won't follow yes/no or letter-only instructions.
    """
    return (
        "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_message}"
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def push_prompt_to_device(text: str) -> None:
    """Write *text* to PROMPT_DEVICE_PATH on the connected device.

    Using adb push avoids all shell-quoting issues (dollar signs, backticks,
    angle brackets, newlines) that arise when passing long BoolQ passages
    through adb shell -p "...".
    """
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(text)
        host_path = fh.name

    result = subprocess.run(
        [ADB_BIN, "push", host_path, PROMPT_DEVICE_PATH],
        capture_output=True, text=True, timeout=20,
    )
    Path(host_path).unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(f"adb push failed: {result.stderr.strip()}")


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

def load_prompts_from_yaml(yaml_path: Path) -> list[dict]:
    """Load prompts from a YAML file. Returns list of {id, prompt, answer, category, answer_type}."""
    if not yaml_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {yaml_path}")

    try:
        import yaml
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
        prompts = data.get("prompts", [])
        # Ensure answer_type defaults to "substring" if not specified
        for p in prompts:
            p.setdefault("answer_type", "substring")
        return prompts
    except ImportError:
        pass

    # Manual YAML parser (no PyYAML dependency)
    prompts: list[dict] = []
    current: dict = {}

    with open(yaml_path) as f:
        for line in f:
            if m := re.match(r"\s*-\s+id:\s*(.+)", line):
                if current.get("id"):
                    current.setdefault("answer_type", "substring")
                    prompts.append(current)
                current = {"id": m.group(1).strip()}
            elif m := re.match(r'\s+prompt:\s*"(.*)"', line):
                # Unescape \" in prompt text
                current["prompt"] = m.group(1).replace('\\"', '"')
            elif m := re.match(r'\s+answer:\s*"(.*)"', line):
                current["answer"] = m.group(1)
            elif m := re.match(r"\s+answer_type:\s*(\S+)", line):
                current["answer_type"] = m.group(1).strip()
            elif m := re.match(r"\s+category:\s*(.+)", line):
                current["category"] = m.group(1).strip()

    if current.get("id"):
        current.setdefault("answer_type", "substring")
        prompts.append(current)

    return prompts


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score_substring(model_output: str, expected: str) -> bool:
    """Case-insensitive: expected appears anywhere in output."""
    return expected.lower().strip() in model_output.lower()


def score_choice(model_output: str, expected: str) -> bool:
    """
    Extract a multiple-choice letter (A/B/C/D) from model output.

    Accepts:
      - Bare letter: "A", "B", "C", "D"
      - With punctuation: "A.", "A)", "A:"
      - Prefixed: "(A)", "Answer: A", "Answer: A.", "The answer is A"
      - First token heuristic: if output starts with a valid letter, use it
    """
    letter = expected.upper().strip()
    if letter not in ("A", "B", "C", "D"):
        # Fall back to substring for unexpected answer formats
        return score_substring(model_output, expected)

    out = model_output.strip()

    # Pattern 1: output starts with the letter as a standalone token
    # (not part of a longer word like "Answer:")
    # Matches: "A", "A.", "A)", "A:", "A " but NOT "Answer..."
    if re.match(rf"^{letter}(?:[.):\s]|$)", out, re.IGNORECASE):
        return True

    # Pattern 2: "Answer: X" or "Answer is X"
    if re.search(rf"\bAnswer\s*(?:is\s*)?:?\s*{letter}\b", out, re.IGNORECASE):
        return True

    # Pattern 3: "(X)" or "X)" or "X." at word boundary
    if re.search(rf"\b\(?{letter}[.):]?\b", out, re.IGNORECASE):
        return True

    # Pattern 4: "The answer is X" or "The correct answer is X"
    if re.search(rf"\bthe\s+(?:correct\s+)?answer\s+is\s+{letter}\b", out, re.IGNORECASE):
        return True

    return False


def score_yesno(model_output: str, expected: str) -> bool:
    """
    Extract yes/no from model output.

    Accepts:
      - Bare: "yes", "no"
      - With punctuation: "yes.", "no,", "yes!"
      - Prefixed: "Answer: yes", "The answer is no"
      - Capitalized: "Yes", "No"
    """
    target = expected.lower().strip()
    if target not in ("yes", "no"):
        return score_substring(model_output, expected)

    out = model_output.strip().lower()

    # Pattern 1: output starts with target word
    if re.match(rf"^{target}\b", out):
        return True

    # Pattern 2: "answer: yes/no" or "answer is yes/no"
    if re.search(rf"\banswer\s*(?:is\s*)?:?\s*{target}\b", out):
        return True

    # Pattern 3: standalone target word in short output (<= 20 chars)
    if len(out) <= 20 and re.search(rf"\b{target}\b", out):
        return True

    # Pattern 4: first word is the target (after stripping punctuation)
    first_word = re.split(r"[\s.,!?]", out)[0].strip()
    if first_word == target:
        return True

    return False


def score_answer(model_output: str, expected: str, answer_type: str) -> bool:
    """Dispatch to the correct scoring function based on answer_type."""
    if answer_type == "choice":
        return score_choice(model_output, expected)
    elif answer_type == "yesno":
        return score_yesno(model_output, expected)
    else:
        # Default: substring match (works for custom eval Q&A)
        return score_substring(model_output, expected)


_LOG_KEYWORDS = (
    "llama_", "ggml_", "common_perf", "load time", "eval time",
    "prompt eval", "total time", "main: ", "[New Thread",
    "warning:", "error:",
)

_ASSISTANT_MARKER = "<|start_header_id|>assistant<|end_header_id|>"


def extract_model_answer(raw_output: str) -> str:
    """Extract the generated text from llama-completion output.

    When using the Llama-3.2 instruct template (-f prompt_file), the binary
    echoes the full prompt back before the generated tokens.  We locate the
    last assistant header marker and take only the text after it, stripping
    debug log lines throughout.
    """
    # Instruct-format path: slice everything after the last assistant header
    if _ASSISTANT_MARKER in raw_output:
        idx = raw_output.rfind(_ASSISTANT_MARKER)
        response = raw_output[idx + len(_ASSISTANT_MARKER):]
        # Drop the two leading newlines that follow the header token
        response = response.lstrip("\n")
        # Remove EOS/EOT tokens that may appear in the text stream
        response = response.replace("<|eot_id|>", "").replace("<|end_of_text|>", "")
        lines = [
            l for l in response.splitlines()
            if not any(kw in l for kw in _LOG_KEYWORDS)
        ]
        return " ".join(lines).strip()

    # Fallback: original behaviour for raw-completion / custom-eval prompts
    lines = []
    for line in raw_output.splitlines():
        if any(kw in line for kw in _LOG_KEYWORDS):
            continue
        lines.append(line)
    return " ".join(lines).strip()


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

class DeviceDisconnectedError(RuntimeError):
    """Raised when adb loses contact with the device mid-evaluation."""


def run_inference(
    prompt: str,
    model_path: str,
    n_tokens: int = 32,
    dry_run: bool = False,
) -> str | None:
    """Run one inference on device. Returns model output text or None on failure.

    Applies the Llama-3.2-3B-Instruct chat template and pushes the formatted
    prompt to a temp file on device (avoids all shell-quoting problems with
    long BoolQ/ARC passages containing $, `, <, >, etc.).

    Context window is 2048 tokens to accommodate the longest BoolQ passages
    without silent truncation.
    """
    formatted_prompt = format_llama3_instruct(prompt)

    cmd = (
        f"LD_LIBRARY_PATH={DEVICE_DIR} {LLAMA_CLI} "
        f"-m {model_path} "
        f"-c 2048 "
        f"-n {n_tokens} "
        f"--temp 0.0 "
        f"--seed 42 "
        f"-t 4 "
        f"-no-cnv "
        f"-f {PROMPT_DEVICE_PATH}"
    )

    if dry_run:
        print(f"    [DRY RUN] push prompt + adb shell {cmd[:70]}...")
        return "DRY_RUN_OUTPUT"

    try:
        push_prompt_to_device(formatted_prompt)
    except RuntimeError as e:
        raise DeviceDisconnectedError(f"adb push failed: {e}") from e

    try:
        raw = adb_shell(cmd, timeout=180)
        # Detect USB disconnection mid-run
        if "no devices/emulators found" in raw or "error: device" in raw:
            raise DeviceDisconnectedError("ADB device disconnected")
        return extract_model_answer(raw)
    except DeviceDisconnectedError:
        raise
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
    model_paths: dict[str, str],
    tag: str,
    dry_run: bool = False,
) -> dict:
    """Run all eval prompts for one variant. Returns result dict."""
    model_path = model_paths.get(variant)
    if not model_path:
        return {
            "variant": variant, "tag": tag,
            "status": "unsupported",
            "accuracy_pct": None, "correct": None, "total": len(prompts),
        }

    # Verify model exists on device
    if not dry_run:
        check = adb_shell(f"ls {model_path} 2>/dev/null", timeout=10)
        if ".gguf" not in check:
            print(f"  [{variant}] SKIP — model not on device at {model_path}")
            return {
                "variant": variant, "tag": tag,
                "status": "skipped_not_on_device",
                "accuracy_pct": None, "correct": None, "total": len(prompts),
            }

    print(f"\n  [{variant}] Evaluating {len(prompts)} prompts (tag={tag})...")
    per_question: list[dict] = []
    correct_count = 0

    for i, p in enumerate(prompts, 1):
        prompt_id   = p["id"]
        prompt_text = p["prompt"]
        expected    = p["answer"]
        category    = p.get("category", "unknown")
        answer_type = p.get("answer_type", "substring")

        # Tokens needed: choice/yesno need only 4-8 tokens; substring needs 32
        n_tokens = 8 if answer_type in ("choice", "yesno") else 32

        print(f"    [{i:3d}/{len(prompts)}] {prompt_id} ({answer_type}) ... ", end="", flush=True)
        try:
            model_output = run_inference(prompt_text, model_path, n_tokens=n_tokens, dry_run=dry_run)
        except DeviceDisconnectedError:
            print("DEVICE DISCONNECTED — aborting variant")
            # Return partial results so the caller can save what we have
            total_so_far = len(per_question)
            accuracy_partial = round(100.0 * correct_count / total_so_far, 1) if total_so_far > 0 else None
            return {
                "variant": variant, "tag": tag,
                "status": "aborted_disconnected",
                "accuracy_pct": accuracy_partial,
                "correct": correct_count,
                "total": total_so_far,
                "per_question": per_question,
            }

        if model_output is None:
            print("TIMEOUT")
            per_question.append({
                "prompt_id": prompt_id, "category": category,
                "answer_type": answer_type,
                "expected": expected, "model_output": None,
                "correct": False, "status": "timeout",
            })
            continue

        is_correct = score_answer(model_output, expected, answer_type)
        correct_count += int(is_correct)
        status_str = "✓" if is_correct else "✗"
        print(f"{status_str}  (expected={expected!r}, got={model_output[:50]!r})")

        per_question.append({
            "prompt_id": prompt_id, "category": category,
            "answer_type": answer_type,
            "expected": expected, "model_output": model_output[:200],
            "correct": is_correct, "status": "success",
        })

        if not dry_run:
            time.sleep(1)  # Brief pause between inferences

    total = len(prompts)
    accuracy_pct = round(100.0 * correct_count / total, 1) if total > 0 else None

    # Wilson 95% CI
    wilson_ci = None
    if total > 0 and accuracy_pct is not None:
        p_hat = correct_count / total
        z = 1.96  # 95%
        denom = 1 + z * z / total
        center = (p_hat + z * z / (2 * total)) / denom
        margin = (z * (p_hat * (1 - p_hat) / total + z * z / (4 * total * total)) ** 0.5) / denom
        wilson_ci = round(margin * 100, 1)

    print(f"  [{variant}] {tag} Accuracy: {correct_count}/{total} = {accuracy_pct}%"
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
        description="Exact-match quality evaluation for GGUF quantization levels"
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
        help="Path to YAML dataset file (e.g. data/arc_easy_100.yaml). "
             "Default: prompts/quality-eval-v1.yaml"
    )
    parser.add_argument(
        "--tag", default=None, metavar="TAG",
        help="Tag for this eval run (used as key prefix in output JSON). "
             "Default: 'custom_v1' for default dataset, or inferred from filename."
    )
    parser.add_argument(
        "--imatrix", action="store_true",
        help="Evaluate imatrix-calibrated variants instead of originals"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show commands without running inference"
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_FILE),
        help="Output JSON file"
    )
    args = parser.parse_args()

    # Determine dataset file and tag
    if args.dataset:
        dataset_path = Path(args.dataset)
        if not dataset_path.is_absolute():
            dataset_path = PROJECT_ROOT / dataset_path
        # Infer tag from filename if not provided
        tag = args.tag or dataset_path.stem.replace("-", "_")
    else:
        dataset_path = DEFAULT_PROMPTS_FILE
        tag = args.tag or DEFAULT_TAG

    # Select model paths
    if args.imatrix:
        model_paths = GGUF_IMATRIX_DEVICE_PATHS
        valid_variants = ALL_IMATRIX_VARIANTS
        # Append _imatrix to tag to keep results separate
        if not tag.endswith("_imatrix"):
            tag = tag + "_imatrix"
    else:
        model_paths = GGUF_DEVICE_PATHS
        valid_variants = ALL_VARIANTS

    # Determine variants
    if args.run_all or not args.variants:
        variants = valid_variants
    else:
        variants = args.variants
        for v in variants:
            if v not in model_paths:
                print(f"ERROR: Unknown variant {v!r}. Valid: {', '.join(valid_variants)}")
                return 1

    # Check device
    if not args.dry_run:
        if not check_device():
            print("ERROR: No Android device connected.")
            print("  Connect device via USB and ensure USB debugging is enabled.")
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

    # Show eval configuration
    answer_types = set(p.get("answer_type", "substring") for p in prompts)
    print(f"\n=== Quality Evaluation ===")
    print(f"  Dataset:      {dataset_path.name} ({len(prompts)} questions)")
    print(f"  Answer types: {', '.join(sorted(answer_types))}")
    print(f"  Tag:          {tag}")
    print(f"  Variants:     {', '.join(variants)}")
    print(f"  imatrix:      {'yes' if args.imatrix else 'no'}")
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
        result = evaluate_variant(
            variant, prompts, model_paths, tag,
            dry_run=args.dry_run,
        )
        all_results[result_key] = result

        # Save after each variant (crash-safe)
        output_path.write_text(json.dumps(all_results, indent=2))

    # Final summary
    print(f"\n=== Summary (tag={tag}) ===")
    print(f"{'Variant':<10} {'Accuracy':>10} {'±CI':>6} {'Correct':>9} {'Total':>7}  Status")
    print("-" * 60)
    for v in variants:
        r = all_results.get(f"{tag}:{v}", {})
        acc   = r.get("accuracy_pct")
        ci    = r.get("wilson_ci_95_pct")
        corr  = r.get("correct")
        tot   = r.get("total", len(prompts))
        status = r.get("status", "?")
        acc_str  = f"{acc}%"  if acc  is not None else "N/A"
        ci_str   = f"±{ci}%" if ci   is not None else "    "
        corr_str = str(corr)  if corr is not None else "N/A"
        print(f"{v:<10} {acc_str:>10} {ci_str:>6} {corr_str:>9} {tot:>7}  {status}")

    print(f"\nResults saved to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
