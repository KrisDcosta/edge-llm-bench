#!/usr/bin/env python3
"""
Debug script: Run a single BoolQ question with Q8_0 and print the raw output
to understand why extraction fails for larger quantization variants.
"""
import sys
import subprocess
import yaml

sys.path.insert(0, 'scripts')
import quality_eval as qe

DEVICE_DIR         = "/data/local/tmp"
LLAMA_CLI          = f"{DEVICE_DIR}/llama-completion"
PROMPT_DEVICE_PATH = f"{DEVICE_DIR}/eval_prompt.txt"
MODEL_Q8_0         = f"{DEVICE_DIR}/Llama-3.2-3B-Instruct-Q8_0.gguf"

# Load first 5 BoolQ questions
with open("data/boolq_100.yaml") as f:
    data = yaml.safe_load(f)

prompts = data["prompts"][:5]

print("=== Q8_0 Extraction Debug ===\n")

for i, p in enumerate(prompts):
    print(f"\n--- Question {i+1}: {p['id']} (expected: {p['answer']}) ---")
    prompt_text = p["prompt"]
    formatted   = qe.format_llama3_instruct(prompt_text)

    # Push prompt to device
    try:
        qe.push_prompt_to_device(formatted)
    except Exception as e:
        print(f"  Push failed: {e}")
        continue

    cmd = (
        f"LD_LIBRARY_PATH={DEVICE_DIR} {LLAMA_CLI} "
        f"-m {MODEL_Q8_0} "
        f"-c 2048 -n 32 --temp 0.0 --seed 42 -t 4 -no-cnv "
        f"-f {PROMPT_DEVICE_PATH}"
    )

    raw = qe.adb_shell(cmd, timeout=120)

    print(f"  RAW OUTPUT (repr, first 600 chars):")
    print(f"  {repr(raw[:600])}")
    print()

    # Show what the current extraction function does
    extracted = qe.extract_model_answer(raw)
    print(f"  EXTRACTED: {repr(extracted)}")

    # Manual check: does the primary regex match?
    import re
    m = re.search(r"Answer with only yes or no:\s*assistant", raw, re.IGNORECASE)
    print(f"  Primary regex match: {bool(m)}")
    if m:
        after = raw[m.end():]
        print(f"  Text after match (repr, first 100): {repr(after[:100])}")
