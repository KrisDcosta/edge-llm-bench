#!/usr/bin/env python3
"""Parse llama.cpp CLI output into structured timing data.

llama.cpp prints timing data in a standard format when run with default verbosity:

    llama_perf_sampler_print:    sampling time =      X.XX ms /    N runs   (    X.XX ms per token,  XXXX.XX tokens per second)
    llama_perf_context_print:        load time =      X.XX ms
    llama_perf_context_print: prompt eval time =      X.XX ms /    N tokens (    X.XX ms per token,  XXXX.XX tokens per second)
    llama_perf_context_print:        eval time =      X.XX ms /    N runs   (    X.XX ms per token,  XXXX.XX tokens per second)
    llama_perf_context_print:       total time =      X.XX ms /    N tokens

This parser extracts these values and returns a structured dict.
"""

import re
import sys
from typing import Optional


def parse_llama_timings(output: str) -> dict:
    """Parse llama.cpp stdout into a timing dict.

    Returns dict with keys:
        load_time_ms, prompt_eval_time_ms, prompt_eval_tokens,
        prompt_eval_ms_per_token, prompt_eval_tps,
        eval_time_ms, eval_tokens, eval_ms_per_token, eval_tps,
        total_time_ms, total_tokens,
        sampling_time_ms, sampling_tokens
    All values are float or int. Missing values are None.
    """
    result = {
        "load_time_ms": None,
        "prompt_eval_time_ms": None,
        "prompt_eval_tokens": None,
        "prompt_eval_ms_per_token": None,
        "prompt_eval_tps": None,
        "eval_time_ms": None,
        "eval_tokens": None,
        "eval_ms_per_token": None,
        "eval_tps": None,
        "total_time_ms": None,
        "total_tokens": None,
        "sampling_time_ms": None,
        "sampling_tokens": None,
    }

    # load time =    1234.56 ms
    m = re.search(r"load time\s*=\s*([\d.]+)\s*ms", output)
    if m:
        result["load_time_ms"] = float(m.group(1))

    # prompt eval time =    1234.56 ms /    42 tokens (   29.39 ms per token,    34.03 tokens per second)
    m = re.search(
        r"prompt eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens?\s*"
        r"\(\s*([\d.]+)\s*ms per token,\s*([\d.]+)\s*tokens per second\)",
        output,
    )
    if m:
        result["prompt_eval_time_ms"] = float(m.group(1))
        result["prompt_eval_tokens"] = int(m.group(2))
        result["prompt_eval_ms_per_token"] = float(m.group(3))
        result["prompt_eval_tps"] = float(m.group(4))

    # eval time =    5678.90 ms /   128 runs   (   44.37 ms per token,    22.54 tokens per second)
    m = re.search(
        r"eval time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*runs?\s*"
        r"\(\s*([\d.]+)\s*ms per token,\s*([\d.]+)\s*tokens per second\)",
        output,
    )
    if m:
        result["eval_time_ms"] = float(m.group(1))
        result["eval_tokens"] = int(m.group(2))
        result["eval_ms_per_token"] = float(m.group(3))
        result["eval_tps"] = float(m.group(4))

    # total time =    6789.12 ms /   170 tokens
    m = re.search(
        r"total time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*tokens?",
        output,
    )
    if m:
        result["total_time_ms"] = float(m.group(1))
        result["total_tokens"] = int(m.group(2))

    # sampling time =     12.34 ms /   129 runs   (    0.10 ms per token, 10456.27 tokens per second)
    m = re.search(
        r"sampling time\s*=\s*([\d.]+)\s*ms\s*/\s*(\d+)\s*runs?",
        output,
    )
    if m:
        result["sampling_time_ms"] = float(m.group(1))
        result["sampling_tokens"] = int(m.group(2))

    return result


def timings_to_metrics(timings: dict) -> dict:
    """Convert raw llama.cpp timings to PRD-aligned metrics.

    Returns dict with:
        prefill_s, prefill_tps, gen_s, decode_tps, e2e_s,
        ttft_s (approximated as prefill time),
        gen_over_prefill, prefill_frac, gen_frac,
        input_tokens, output_tokens
    """
    prefill_ms = timings.get("prompt_eval_time_ms")
    eval_ms = timings.get("eval_time_ms")
    total_ms = timings.get("total_time_ms")
    prompt_tokens = timings.get("prompt_eval_tokens")
    eval_tokens = timings.get("eval_tokens")

    prefill_s = prefill_ms / 1000.0 if prefill_ms is not None else None
    gen_s = eval_ms / 1000.0 if eval_ms is not None else None
    e2e_s = total_ms / 1000.0 if total_ms is not None else None

    # TTFT ≈ prefill time (llama.cpp doesn't separate request overhead)
    ttft_s = prefill_s

    prefill_tps = timings.get("prompt_eval_tps")
    decode_tps = timings.get("eval_tps")

    # Derived ratios
    gen_over_prefill = None
    prefill_frac = None
    gen_frac = None

    if prefill_s and gen_s and prefill_s > 0:
        gen_over_prefill = gen_s / prefill_s

    if prefill_s and e2e_s and e2e_s > 0:
        prefill_frac = prefill_s / e2e_s

    if gen_s and e2e_s and e2e_s > 0:
        gen_frac = gen_s / e2e_s

    return {
        "ttft_s": ttft_s,
        "prefill_s": prefill_s,
        "prefill_tps": prefill_tps,
        "gen_s": gen_s,
        "decode_tps": decode_tps,
        "e2e_s": e2e_s,
        "gen_over_prefill": gen_over_prefill,
        "prefill_frac": prefill_frac,
        "gen_frac": gen_frac,
        "input_tokens": prompt_tokens,
        "output_tokens": eval_tokens,
    }


def has_valid_timings(timings: dict) -> bool:
    """Check if essential timing fields were parsed."""
    return (
        timings.get("prompt_eval_time_ms") is not None
        and timings.get("eval_time_ms") is not None
        and timings.get("total_time_ms") is not None
    )


if __name__ == "__main__":
    import json

    if len(sys.argv) > 1:
        with open(sys.argv[1]) as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    timings = parse_llama_timings(text)
    metrics = timings_to_metrics(timings)

    print("=== Raw Timings ===")
    print(json.dumps(timings, indent=2))
    print("\n=== PRD Metrics ===")
    print(json.dumps(metrics, indent=2))

    if not has_valid_timings(timings):
        print("\nWARNING: Could not parse essential timing fields from output.")
        sys.exit(1)
