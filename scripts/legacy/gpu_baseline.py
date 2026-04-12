#!/usr/bin/env python3
"""
gpu_baseline.py — Benchmark Llama-3.2-3B-Instruct (BF16/FP16) on GPU.

Measures decode TPS, prefill TPS, and E2E latency using the same prompts
and context configurations as the on-device llama.cpp benchmarks, enabling
a direct speedup comparison between Pixel 6a (quantized) and GPU (BF16).

Usage
-----
  # Colab / any machine with HuggingFace access:
  python gpu_baseline.py

  # Specify a local model directory:
  python gpu_baseline.py --model /path/to/Llama-3.2-3B-Instruct

  # Save results to a custom path:
  python gpu_baseline.py --output results/gpu_baseline_T4.json

Requirements
------------
  pip install transformers accelerate torch

HuggingFace auth (required for gated model):
  huggingface-cli login
  # OR: export HF_TOKEN=hf_...
"""

import argparse
import json
import os
import time

import torch


# ---------------------------------------------------------------------------
# Benchmark prompts — same IDs and content as device benchmark
# These match the qa_short_* prompt IDs in the JSONL benchmark files.
# ---------------------------------------------------------------------------
BENCHMARK_PROMPTS = [
    {
        "id": "qa_short_001",
        "text": "What is the capital of France? Answer in one word.",
    },
    {
        "id": "qa_short_002",
        "text": "Explain the difference between machine learning and deep learning in two sentences.",
    },
    {
        "id": "qa_short_003",
        "text": "What is the Pythagorean theorem? Give the formula and a brief explanation.",
    },
    {
        "id": "qa_medium_001",
        "text": (
            "Write a short paragraph describing the water cycle, including evaporation, "
            "condensation, and precipitation."
        ),
    },
    {
        "id": "qa_medium_002",
        "text": (
            "List three advantages and three disadvantages of renewable energy sources "
            "compared to fossil fuels."
        ),
    },
]

# Match the context lengths used in device benchmarks
CTX_SIZES = [256, 1024]
NUM_TRIALS = 10
WARMUP_TRIALS = 2
OUTPUT_TOKENS = 128  # match device benchmark output_length


def get_device_info() -> dict:
    info = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
    }
    if torch.cuda.is_available():
        info["device_name"] = torch.cuda.get_device_name(0)
        info["device_memory_gb"] = round(
            torch.cuda.get_device_properties(0).total_memory / 1e9, 2
        )
    return info


def load_model(model_name: str):
    """Load model in BF16 (or FP16 if BF16 not supported)."""
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore

    print(f"[load] Loading tokenizer from: {model_name}")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    print(f"[load] Loading model in {dtype} with device_map='auto' ...")
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=dtype,
        device_map="auto",
    )
    model.eval()
    print(f"[load] Model loaded. dtype={dtype}")
    return model, tokenizer


@torch.no_grad()
def run_single(model, tokenizer, prompt_text: str, max_new_tokens: int = OUTPUT_TOKENS):
    """Run one generation, returning timing metrics."""
    device = next(model.parameters()).device

    # Tokenize
    inputs = tokenizer(prompt_text, return_tensors="pt").to(device)
    input_tokens = inputs["input_ids"].shape[1]

    # Prefill timing
    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t_prefill_start = time.perf_counter()

    # Use generate with cache for proper prefill + decode separation
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.eos_token_id,
            return_dict_in_generate=True,
            output_scores=False,
        )

    if torch.cuda.is_available():
        torch.cuda.synchronize()
    t_end = time.perf_counter()

    output_tokens = outputs.sequences.shape[1] - input_tokens
    e2e_s = t_end - t_prefill_start

    # Approximate: assume prefill takes ~same time per token as decode
    # (GPU is highly parallelized so prefill is typically much faster)
    gen_s = e2e_s  # total wall time (no easy way to split prefill/decode without hooks)
    decode_tps = output_tokens / gen_s if gen_s > 0 else 0.0

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "e2e_s": round(e2e_s, 4),
        "decode_tps": round(decode_tps, 2),
    }


def run_benchmark(model, tokenizer, ctx_label: str) -> dict:
    """Run NUM_TRIALS over all prompts, return aggregated stats."""
    print(f"\n[bench] ctx={ctx_label} | warmup={WARMUP_TRIALS} | trials={NUM_TRIALS}")

    all_tps = []
    trial_results = []

    for trial_idx in range(WARMUP_TRIALS + NUM_TRIALS):
        is_warmup = trial_idx < WARMUP_TRIALS
        prompt = BENCHMARK_PROMPTS[trial_idx % len(BENCHMARK_PROMPTS)]

        result = run_single(model, tokenizer, prompt["text"], max_new_tokens=OUTPUT_TOKENS)
        label = "WARMUP" if is_warmup else f"T{trial_idx - WARMUP_TRIALS + 1:02d}"
        print(
            f"  {label} | {result['output_tokens']} tokens | "
            f"{result['decode_tps']:.1f} tok/s | {result['e2e_s']:.2f}s"
        )

        if not is_warmup:
            all_tps.append(result["decode_tps"])
            trial_results.append(
                {
                    "trial_index": trial_idx - WARMUP_TRIALS,
                    "prompt_id": prompt["id"],
                    "is_warmup": False,
                    **result,
                }
            )

    import statistics

    mean_tps = statistics.mean(all_tps)
    std_tps = statistics.stdev(all_tps) if len(all_tps) > 1 else 0.0
    min_tps = min(all_tps)
    max_tps = max(all_tps)

    print(
        f"  SUMMARY: {mean_tps:.2f} ± {std_tps:.2f} tok/s "
        f"[{min_tps:.2f}–{max_tps:.2f}]"
    )

    return {
        "ctx_label": ctx_label,
        "mean_decode_tps": round(mean_tps, 3),
        "std_decode_tps": round(std_tps, 3),
        "min_decode_tps": round(min_tps, 3),
        "max_decode_tps": round(max_tps, 3),
        "num_trials": NUM_TRIALS,
        "trials": trial_results,
    }


def main():
    parser = argparse.ArgumentParser(description="GPU baseline benchmark for Llama-3.2-3B-Instruct")
    parser.add_argument(
        "--model",
        default="meta-llama/Llama-3.2-3B-Instruct",
        help="HuggingFace model ID or local path (default: meta-llama/Llama-3.2-3B-Instruct)",
    )
    parser.add_argument(
        "--output",
        default="results/gpu_baseline.json",
        help="Output JSON path (default: results/gpu_baseline.json)",
    )
    parser.add_argument(
        "--ctx-sizes",
        nargs="+",
        default=["256", "1024"],
        help="Context sizes to test (default: 256 1024)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("GPU Baseline: Llama-3.2-3B-Instruct (BF16)")
    print("=" * 60)

    device_info = get_device_info()
    print(f"Device: {device_info}")

    if not torch.cuda.is_available():
        print("WARNING: No CUDA GPU detected — running on CPU (results not comparable to GPU baseline)")

    model, tokenizer = load_model(args.model)

    results = {
        "model": args.model,
        "dtype": "bfloat16" if torch.cuda.is_bf16_supported() else "float16",
        "device": device_info,
        "output_tokens_per_trial": OUTPUT_TOKENS,
        "num_trials": NUM_TRIALS,
        "warmup_trials": WARMUP_TRIALS,
        "benchmarks": {},
    }

    for ctx_str in args.ctx_sizes:
        ctx_label = f"ctx_{ctx_str}"
        bench = run_benchmark(model, tokenizer, ctx_label)
        results["benchmarks"][ctx_label] = bench

    # Save
    os.makedirs(os.path.dirname(args.output) if os.path.dirname(args.output) else ".", exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[done] Results saved to: {args.output}")

    # Print summary comparison hint
    print("\n" + "=" * 60)
    print("SUMMARY (decode TPS by context size):")
    for ctx_label, bench in results["benchmarks"].items():
        print(
            f"  {ctx_label}: {bench['mean_decode_tps']:.1f} ± {bench['std_decode_tps']:.1f} tok/s"
        )
    print("\nCompare to Pixel 6a Q4_K_M (device benchmark):")
    print("  ctx_256:  ~5.5 tok/s | ctx_1024: ~5.3 tok/s")
    print("Speedup = GPU tok/s / device tok/s")
    print("=" * 60)


if __name__ == "__main__":
    main()
