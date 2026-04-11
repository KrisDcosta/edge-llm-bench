#!/usr/bin/env python3
"""
download_humaneval.py  --  Save first 50 HumanEval problems to data/humaneval_50.jsonl.

Each line: {"task_id": str, "problem_id": int, "prompt": str,
             "entry_point": str, "test": str, "canonical_solution": str}

Usage:
    python3 scripts/eval/download_humaneval.py
    python3 scripts/eval/download_humaneval.py --out data/humaneval_50.jsonl
    python3 scripts/eval/download_humaneval.py --hardcoded   # use bundled subset
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
DEFAULT_OUT  = PROJECT_ROOT / "data" / "humaneval_50.jsonl"

# ---------------------------------------------------------------------------
# Hardcoded fallback: first 10 HumanEval problems (problems 0-9).
# We keep only 10 inline to avoid bloat; the download path gets all 50.
# If HF download fails we write these 10 and warn the user.
# ---------------------------------------------------------------------------
HARDCODED_10 = [
    {
        "task_id": "HumanEval/0",
        "problem_id": 0,
        "entry_point": "has_close_elements",
        "prompt": (
            "from typing import List\n\n\n"
            "def has_close_elements(numbers: List[float], threshold: float) -> bool:\n"
            '    """ Check if in given list of numbers, are any two numbers closer to each other than\n'
            "    given threshold.\n"
            "    >>> has_close_elements([1.0, 2.0, 3.0], 0.5)\n"
            "    False\n"
            "    >>> has_close_elements([1.0, 2.8, 3.0, 4.0, 5.0, 2.0], 0.3)\n"
            "    True\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    sorted_numbers = sorted(numbers)\n"
            "    for idx, elem in enumerate(sorted_numbers[:-1]):\n"
            "        diff = sorted_numbers[idx + 1] - elem\n"
            "        if diff < threshold:\n"
            "            return True\n\n"
            "    return False\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.3) == True\n"
            "    assert candidate([1.0, 2.0, 3.9, 4.0, 5.0, 2.2], 0.05) == False\n"
            "    assert candidate([1.0, 2.0, 5.9, 4.0, 5.0], 0.95) == True\n"
            "    assert candidate([1.0, 2.0, 5.9, 4.0, 5.0], 0.8) == False\n"
            "    assert candidate([1.0, 2.0, 3.0, 4.0, 5.0, 2.0], 0.1) == True\n"
            "    assert candidate([1.1, 2.2, 3.1, 4.1, 5.1], 1.0) == True\n"
            "    assert candidate([1.1, 2.2, 3.1, 4.1, 5.1], 0.5) == False\n"
        ),
    },
    {
        "task_id": "HumanEval/1",
        "problem_id": 1,
        "entry_point": "separate_paren_groups",
        "prompt": (
            "from typing import List\n\n\n"
            "def separate_paren_groups(paren_string: str) -> List[str]:\n"
            '    """ Input to this function is a string containing multiple groups of nested parentheses.\n'
            "    Your goal is to separate those group into separate strings and return the list of those.\n"
            "    Separate groups are balanced (each open brace is properly closed) and not nested within each other.\n"
            "    Ignore any spaces in the input string.\n"
            "    >>> separate_paren_groups('( ) (( )) (( )( ))')\n"
            "    ['()', '(())', '(()())']\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    result = []\n"
            "    current_string = []\n"
            "    current_depth = 0\n\n"
            "    for c in paren_string:\n"
            "        if c == '(':\n"
            "            current_depth += 1\n"
            "            current_string.append(c)\n"
            "        elif c == ')':\n"
            "            current_depth -= 1\n"
            "            current_string.append(c)\n"
            "            if current_depth == 0:\n"
            "                result.append(''.join(current_string))\n"
            "                current_string = []\n\n"
            "    return result\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate('(()()) ((())) () ((())(()))') == ['(()())', '((()))', '()', '((())(()))']\n"
            "    assert candidate('() (()) ((())) (((())))') == ['()', '(())', '((()))', '(((())))']\n"
            "    assert candidate('(()(())((())))') == ['(()(())((())))']\n"
            "    assert candidate('( ) (( )) (( )( ))') == ['()', '(())', '(()())']\n"
        ),
    },
    {
        "task_id": "HumanEval/2",
        "problem_id": 2,
        "entry_point": "truncate_number",
        "prompt": (
            "\n\ndef truncate_number(number: float) -> float:\n"
            '    """ Given a positive floating point number, it can be decomposed into\n'
            "    and integer part (largest integer smaller than given number) and decimals\n"
            "    (leftover part always smaller than 1).\n\n"
            "    Return the decimal part of the number.\n"
            "    >>> truncate_number(3.5)\n"
            "    0.5\n"
            '    """\n'
        ),
        "canonical_solution": "    return number % 1.0\n",
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate(3.5) == 0.5\n"
            "    assert abs(candidate(1.33) - 0.33) < 1e-6\n"
            "    assert abs(candidate(123.456) - 0.456) < 1e-6\n"
        ),
    },
    {
        "task_id": "HumanEval/3",
        "problem_id": 3,
        "entry_point": "below_zero",
        "prompt": (
            "from typing import List\n\n\n"
            "def below_zero(operations: List[int]) -> bool:\n"
            '    """ You\'re given a list of deposit and withdrawal operations on a bank account that starts with\n'
            "    zero balance. Your task is to detect if at any point the balance of account fallls below zero, and\n"
            "    at that point function should return True. Otherwise it should return False.\n"
            "    >>> below_zero([1, 2, 3])\n"
            "    False\n"
            "    >>> below_zero([1, 2, -4, 5])\n"
            "    True\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    balance = 0\n\n"
            "    for op in operations:\n"
            "        balance += op\n"
            "        if balance < 0:\n"
            "            return True\n\n"
            "    return False\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate([]) == False\n"
            "    assert candidate([1, 2, -3, 1, 2, -3]) == False\n"
            "    assert candidate([1, 2, -4, 5, 6]) == True\n"
            "    assert candidate([1, -1, 2, -2, 5, -5, 4, -4]) == False\n"
            "    assert candidate([1, -1, 2, -2, 5, -5, 4, -5]) == True\n"
            "    assert candidate([1, -2, 2, -2, 5, -5, 4, -4]) == True\n"
        ),
    },
    {
        "task_id": "HumanEval/4",
        "problem_id": 4,
        "entry_point": "mean_absolute_deviation",
        "prompt": (
            "from typing import List\n\n\n"
            "def mean_absolute_deviation(numbers: List[float]) -> float:\n"
            '    """ For a given list of input numbers, calculate Mean Absolute Deviation\n'
            "    around the mean of this dataset.\n"
            "    Mean Absolute Deviation is the average absolute difference between each\n"
            "    element and a centerpoint (mean in this case):\n"
            "    MAD = average | x - x_mean |\n"
            "    >>> mean_absolute_deviation([1.0, 2.0, 3.0, 4.0])\n"
            "    1.0\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    mean = sum(numbers) / len(numbers)\n"
            "    return sum(abs(x - mean) for x in numbers) / len(numbers)\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert abs(candidate([1.0, 2.0, 3.0]) - 2.0/3.0) < 1e-6\n"
            "    assert abs(candidate([1.0, 2.0, 3.0, 4.0]) - 1.0) < 1e-6\n"
            "    assert abs(candidate([1.0, 2.0, 3.0, 4.0, 5.0]) - 6.0/5.0) < 1e-6\n"
        ),
    },
    {
        "task_id": "HumanEval/5",
        "problem_id": 5,
        "entry_point": "intersperse",
        "prompt": (
            "from typing import List\n\n\n"
            "def intersperse(numbers: List[int], delimeter: int) -> List[int]:\n"
            '    """ Insert a number \'delimeter\' between every two consecutive elements of input list `numbers\'\n'
            "    >>> intersperse([], 4)\n"
            "    []\n"
            "    >>> intersperse([1, 2, 3], 4)\n"
            "    [1, 4, 2, 4, 3]\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    if not numbers:\n"
            "        return []\n\n"
            "    result = []\n\n"
            "    for n in numbers[:-1]:\n"
            "        result.append(n)\n"
            "        result.append(delimeter)\n"
            "    result.append(numbers[-1])\n\n"
            "    return result\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate([], 7) == []\n"
            "    assert candidate([5, 6, 3, 2], 8) == [5, 8, 6, 8, 3, 8, 2]\n"
            "    assert candidate([2, 2, 2], 2) == [2, 2, 2, 2, 2]\n"
        ),
    },
    {
        "task_id": "HumanEval/6",
        "problem_id": 6,
        "entry_point": "parse_nested_parens",
        "prompt": (
            "from typing import List\n\n\n"
            "def parse_nested_parens(paren_string: str) -> List[int]:\n"
            '    """ Input to this function is a string represented multiple groups for nested parentheses\n'
            "    separated by spaces. For each of the group, output the deepest level of nesting of\n"
            "    parentheses. E.g. (()()) has maximum two levels of nesting while ((())) has three.\n\n"
            "    >>> parse_nested_parens('(()()) ((())) () ((())(())())')\n"
            "    [2, 3, 1, 3]\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    def parse_paren_group(s):\n"
            "        depth = 0\n"
            "        max_depth = 0\n"
            "        for c in s:\n"
            "            if c == '(':\n"
            "                depth += 1\n"
            "                max_depth = max(depth, max_depth)\n"
            "            elif c == ')':\n"
            "                depth -= 1\n\n"
            "        return max_depth\n\n"
            "    return [parse_paren_group(x) for x in paren_string.split(' ') if x]\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate('(()()) ((())) () ((())(()))') == [2, 3, 1, 3]\n"
            "    assert candidate('() (()) ((())) (((())))') == [1, 2, 3, 4]\n"
            "    assert candidate('(()(())((())))') == [4]\n"
        ),
    },
    {
        "task_id": "HumanEval/7",
        "problem_id": 7,
        "entry_point": "filter_by_substring",
        "prompt": (
            "from typing import List\n\n\n"
            "def filter_by_substring(strings: List[str], substring: str) -> List[str]:\n"
            '    """ Filter an input list of strings only for ones that contain given substring\n'
            "    >>> filter_by_substring([], 'a')\n"
            "    []\n"
            "    >>> filter_by_substring(['abc', 'bacd', 'cde', 'array'], 'a')\n"
            "    ['abc', 'bacd', 'array']\n"
            '    """\n'
        ),
        "canonical_solution": "    return [x for x in strings if substring in x]\n",
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate([], 'john') == []\n"
            "    assert candidate(['xxx', 'asd', 'xxy', 'john doe', 'xxxAAA', 'xxx'], 'xxx') == ['xxx', 'xxxAAA', 'xxx']\n"
            "    assert candidate(['xxx', 'asd', 'xxy', 'john doe', 'xxxAAA', 'xxx'], 'john') == ['john doe']\n"
            "    assert candidate(['xxx', 'asd', 'xxy', 'john doe', 'xxxAAA', 'xxx'], 'asd') == ['asd']\n"
        ),
    },
    {
        "task_id": "HumanEval/8",
        "problem_id": 8,
        "entry_point": "sum_product",
        "prompt": (
            "from typing import List, Tuple\n\n\n"
            "def sum_product(numbers: List[int]) -> Tuple[int, int]:\n"
            '    """ For a given list of integers, return a tuple consisting of a sum and a product of all the integers in a list.\n'
            "    Empty sum should be equal to 0 and empty product should be equal to 1.\n"
            "    >>> sum_product([])\n"
            "    (0, 1)\n"
            "    >>> sum_product([1, 2, 3, 4])\n"
            "    (10, 24)\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    sum_value = 0\n"
            "    prod_value = 1\n\n"
            "    for n in numbers:\n"
            "        sum_value += n\n"
            "        prod_value *= n\n"
            "    return sum_value, prod_value\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate([]) == (0, 1)\n"
            "    assert candidate([1, 1, 1]) == (3, 1)\n"
            "    assert candidate([100, 0]) == (100, 0)\n"
            "    assert candidate([3, 5, 7]) == (15, 105)\n"
            "    assert candidate([10]) == (10, 10)\n"
        ),
    },
    {
        "task_id": "HumanEval/9",
        "problem_id": 9,
        "entry_point": "rolling_max",
        "prompt": (
            "from typing import List\n\n\n"
            "def rolling_max(numbers: List[int]) -> List[int]:\n"
            '    """ From a given list of integers, generate a list of rolling maximum element found until given moment\n'
            "    in the sequence.\n"
            "    >>> rolling_max([1, 2, 3, 2, 3, 4, 2])\n"
            "    [1, 2, 3, 3, 3, 4, 4]\n"
            '    """\n'
        ),
        "canonical_solution": (
            "    running_max = None\n"
            "    result = []\n\n"
            "    for n in numbers:\n"
            "        if running_max is None:\n"
            "            running_max = n\n"
            "        else:\n"
            "            running_max = max(running_max, n)\n\n"
            "        result.append(running_max)\n\n"
            "    return result\n"
        ),
        "test": (
            "METADATA = {\n    'author': 'jt',\n    'dataset': 'test'\n}\n\n\n"
            "def check(candidate):\n"
            "    assert candidate([]) == []\n"
            "    assert candidate([1, 2, 3, 4]) == [1, 2, 3, 4]\n"
            "    assert candidate([4, 3, 2, 1]) == [4, 4, 4, 4]\n"
            "    assert candidate([3, 2, 3, 100, 3]) == [3, 3, 3, 100, 100]\n"
        ),
    },
]


def download_from_hf(n: int = 50) -> list[dict] | None:
    """Try to download first n HumanEval problems from HuggingFace."""
    try:
        from datasets import load_dataset  # type: ignore
    except ImportError:
        print("[download_humaneval] 'datasets' package not installed; using hardcoded fallback.")
        return None

    try:
        print("[download_humaneval] Downloading HumanEval from HuggingFace …")
        ds = load_dataset("openai_humaneval", split="test")
        items = []
        for i, ex in enumerate(ds):
            if i >= n:
                break
            items.append({
                "task_id": ex["task_id"],
                "problem_id": i,
                "entry_point": ex["entry_point"],
                "prompt": ex["prompt"],
                "canonical_solution": ex["canonical_solution"],
                "test": ex["test"],
            })
        print(f"[download_humaneval] Downloaded {len(items)} problems.")
        return items
    except Exception as exc:
        print(f"[download_humaneval] HuggingFace download failed: {exc}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Download first 50 HumanEval problems.")
    parser.add_argument("--hardcoded", action="store_true",
                        help="Use bundled 10-problem fallback only (no HF download).")
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"Output JSONL path (default: {DEFAULT_OUT})")
    parser.add_argument("--n", type=int, default=50,
                        help="Number of problems to save (default: 50)")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if args.hardcoded:
        items = HARDCODED_10[: args.n]
        source = "hardcoded (10 problems)"
    else:
        items = download_from_hf(args.n)
        if items is None:
            print("[download_humaneval] WARNING: falling back to 10 hardcoded problems. "
                  "Install 'datasets' (pip install datasets) for the full 50.")
            items = HARDCODED_10
            source = "hardcoded fallback (10 problems)"
        else:
            source = "HuggingFace openai_humaneval test split"

    with out_path.open("w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[download_humaneval] Wrote {len(items)} problems to {out_path}  (source: {source})")


if __name__ == "__main__":
    main()
