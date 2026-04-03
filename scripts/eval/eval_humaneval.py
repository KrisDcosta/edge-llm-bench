#!/usr/bin/env python3
"""
eval_humaneval.py  --  Evaluate saved HumanEval generated-code results.

Reads a results/pixel_humaneval_*/results_*.jsonl directory produced by
pixel_humaneval.sh and runs:
  1. Syntax check  (py_compile)
  2. Execution test  (calls the generated function with the HumanEval test harness)

Updates the JSONL records in-place with fields:
  syntax_ok     : bool
  test_passed   : bool
  error_msg     : str | null

Also prints a per-variant accuracy table.

Usage:
    python3 scripts/eval/eval_humaneval.py results/pixel_humaneval_20260330_120000/
    python3 scripts/eval/eval_humaneval.py results/pixel_humaneval_20260330_120000/ --variant Q4_K_M
    python3 scripts/eval/eval_humaneval.py results/pixel_humaneval_20260330_120000/ --no-exec
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT  = Path(__file__).parent.parent.parent
HE_DATA_FILE  = PROJECT_ROOT / "data" / "humaneval_50.jsonl"
ALL_VARIANTS  = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_he_problems(path: Path) -> dict[str, dict]:
    """Return dict keyed by task_id."""
    problems: dict[str, dict] = {}
    if not path.exists():
        return problems
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                p = json.loads(line)
                problems[p["task_id"]] = p
    return problems


def extract_function_body(raw: str, entry_point: str) -> str:
    """
    Try to pull out a clean Python function from model output.
    Handles cases where the model echoes the prompt, adds markdown fences, etc.
    """
    # Strip markdown code fences
    raw = re.sub(r"```python\s*", "", raw)
    raw = re.sub(r"```\s*", "", raw)

    # If the model output contains the function definition, grab from there
    fn_pattern = re.compile(rf"^\s*def {re.escape(entry_point)}\s*\(", re.MULTILINE)
    m = fn_pattern.search(raw)
    if m:
        return raw[m.start():]

    return raw


def check_syntax(code: str) -> tuple[bool, str]:
    """Return (ok, error_message)."""
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as exc:
        return False, f"SyntaxError: {exc}"


def run_execution_test(
    prompt: str,
    generated_body: str,
    test_code: str,
    entry_point: str,
    timeout: int = 10,
) -> tuple[bool, str]:
    """
    Write a temp file with:  prompt + generated_body + test_code + check(entry_point)
    Run it in a subprocess with a timeout.
    Returns (passed, error_message).
    """
    full_code = textwrap.dedent(f"""
{prompt}
{generated_body}

{test_code}

check({entry_point})
""")
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w",
                                     delete=False, encoding="utf-8") as f:
        f.write(full_code)
        tmp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, ""
        else:
            err = (result.stderr or result.stdout or "").strip()
            return False, err[:400]
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"
    except Exception as exc:
        return False, str(exc)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run syntax + execution evaluation on pixel_humaneval results."
    )
    parser.add_argument("results_dir", help="Path to results/pixel_humaneval_TIMESTAMP/ dir")
    parser.add_argument("--variant", action="append", dest="variants",
                        help="Evaluate only this variant (repeatable). Default: all.")
    parser.add_argument("--no-exec", action="store_true",
                        help="Skip execution test; only check syntax.")
    parser.add_argument("--problems", default=str(HE_DATA_FILE),
                        help=f"HumanEval problems JSONL (default: {HE_DATA_FILE})")
    parser.add_argument("--timeout", type=int, default=10,
                        help="Per-problem execution timeout in seconds (default: 10)")
    args = parser.parse_args()

    results_dir = Path(args.results_dir)
    if not results_dir.exists():
        print(f"ERROR: results dir not found: {results_dir}", file=sys.stderr)
        sys.exit(1)

    variants = args.variants or ALL_VARIANTS
    problems = load_he_problems(Path(args.problems))
    if not problems:
        print(f"WARNING: could not load HumanEval problems from {args.problems}. "
              "Execution tests will be skipped.", file=sys.stderr)
        args.no_exec = True

    summary: dict[str, dict] = defaultdict(lambda: {"syntax_ok": 0, "test_passed": 0, "total": 0})

    # Find all JSONL result files in the directory
    all_jsonl = sorted(results_dir.glob("results_*.jsonl"))
    if not all_jsonl:
        print(f"No results_*.jsonl files found in {results_dir}", file=sys.stderr)
        sys.exit(1)

    for jsonl_path in all_jsonl:
        variant_match = re.search(r"results_(.+)\.jsonl$", jsonl_path.name)
        if not variant_match:
            continue
        variant = variant_match.group(1)
        if variant not in variants:
            continue

        print(f"\n--- Evaluating {variant} from {jsonl_path.name} ---")

        records = []
        with jsonl_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))

        updated = []
        for rec in records:
            task_id    = rec.get("task_id", f"HumanEval/{rec.get('problem_id', '?')}")
            gen_code   = rec.get("generated_code", "")
            problem_id = rec.get("problem_id", 0)

            # Get problem metadata
            prob = problems.get(task_id) or problems.get(f"HumanEval/{problem_id}")
            entry_point = (prob or {}).get("entry_point", "")

            # 1. Syntax check
            clean_code = extract_function_body(gen_code, entry_point) if entry_point else gen_code
            syn_ok, syn_err = check_syntax(clean_code)

            # 2. Execution test
            test_passed = False
            exec_err    = ""
            if not args.no_exec and syn_ok and prob:
                test_passed, exec_err = run_execution_test(
                    prob["prompt"],
                    clean_code,
                    prob["test"],
                    entry_point,
                    timeout=args.timeout,
                )

            rec["syntax_ok"]    = syn_ok
            rec["test_passed"]  = test_passed
            rec["error_msg"]    = (syn_err or exec_err) or None

            updated.append(rec)
            summary[variant]["total"]       += 1
            summary[variant]["syntax_ok"]   += int(syn_ok)
            summary[variant]["test_passed"] += int(test_passed)

            status = "PASS" if test_passed else ("SYN_ERR" if not syn_ok else "FAIL")
            print(f"  [{status}] {task_id:<24}  syntax={syn_ok}  exec={test_passed}"
                  + (f"  err={exec_err[:60]}" if exec_err else ""))

        # Write back updated records
        with jsonl_path.open("w", encoding="utf-8") as f:
            for rec in updated:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        print(f"  -> Updated {jsonl_path}")

    # Print summary table
    print("\n" + "=" * 70)
    print("HUMANEVAL SUMMARY")
    print("=" * 70)
    hdr = f"{'Variant':<12}  {'Total':>5}  {'Syntax OK':>9}  {'Test Pass':>9}  {'Syntax%':>8}  {'Test%':>7}"
    print(hdr)
    print("-" * 70)
    for v in variants:
        s = summary.get(v)
        if not s or s["total"] == 0:
            continue
        n     = s["total"]
        syn_p = 100.0 * s["syntax_ok"]   / n
        tst_p = 100.0 * s["test_passed"] / n
        print(f"{v:<12}  {n:>5}  {s['syntax_ok']:>9}  {s['test_passed']:>9}  {syn_p:>7.1f}%  {tst_p:>6.1f}%")

    print("=" * 70)
    print(f"\nResults updated in: {results_dir}")


if __name__ == "__main__":
    main()
