#!/usr/bin/env python3
"""Mac-native GSM8K evaluator using llama-cli directly."""
import json, subprocess, re, os, sys, time, statistics
from datetime import datetime

LLAMA_CLI = "/opt/homebrew/bin/llama-completion"
MODEL_DIR  = "local-models/llama3_2_3b_gguf"
DATA_FILE  = "data/gsm8k_test.jsonl"
N_THREADS  = 4
N_PREDICT  = 128
CTX        = 512
TEMP       = 0.0  # greedy

FEWSHOT = """Solve these math problems step by step, then give the numeric answer after "Answer:".

Q: There are 15 trees in the grove. Grove workers will plant trees in the grove today. After they are done, there will be 21 trees. How many trees did the grove workers plant today?
A: There are 15 trees originally. Then there were 21 trees after more were planted. So 21 - 15 = 6 trees were planted. Answer: 6

Q: If there are 3 cars in the parking lot and 2 more cars arrive, how many cars are in the parking lot?
A: There are originally 3 cars. 2 more cars arrive. 3 + 2 = 5. Answer: 5

Q: Leah had 32 chocolates and her sister had 42. If they ate 35, how many pieces do they have left in total?
A: Originally, Leah had 32 chocolates. Her sister had 42. That means 32 + 42 = 74. After eating 35, they had 74 - 35 = 39. Answer: 39

Q: Jason had 20 lollipops. He gave Denny some lollipops. Now Jason has 12 lollipops. How many lollipops did Jason give to Denny?
A: Jason started with 20 lollipops. Then he had 12 after giving some to Denny. So he gave Denny 20 - 12 = 8. Answer: 8

Q: Shawn has five toys. For Christmas, he got two toys each from his mom and dad. How many toys does he have now?
A: Shawn started with 5 toys. If he got 2 toys each from his mom and dad, then he got 2 + 2 = 4 more toys. 5 + 4 = 9. Answer: 9

Q: {question}
A:"""

VARIANTS = ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

def extract_answer(text):
    # Only look at the model's actual response (after "assistant" marker or last "A:")
    # Split on "assistant" to get the model's turn only
    if 'assistant' in text:
        text = text.split('assistant')[-1]
    elif '\nA:' in text:
        text = text.split('\nA:')[-1]
    # Look for "Answer: <number>" pattern (prefer last occurrence)
    matches = re.findall(r'[Aa]nswer[:\s]+\$?\s*([0-9,]+(?:\.[0-9]+)?)', text)
    if matches:
        return matches[-1].replace(',','')
    # Fallback: last standalone number
    nums = re.findall(r'\b([0-9]+(?:\.[0-9]+)?)\b', text)
    return nums[-1] if nums else ""

def run_question(model_path, question):
    prompt = FEWSHOT.format(question=question)
    prompt_file = "/tmp/gsm8k_prompt_mac.txt"
    with open(prompt_file, 'w') as f:
        f.write(prompt)

    t0 = time.time()
    # Pipe empty string as stdin so llama-completion exits after generating
    result = subprocess.run([
        LLAMA_CLI,
        "-m", model_path,
        "-f", prompt_file,
        "-n", str(N_PREDICT),
        "-t", str(N_THREADS),
        "-c", str(CTX),
        "--temp", str(TEMP),
        "-ngl", "99",   # Use Metal GPU for speed
        "--single-turn",  # Exit cleanly after one response
    ], capture_output=True, text=True, timeout=180)
    elapsed = time.time() - t0

    output = result.stdout.strip()
    # Extract only the generated text: strip llama.cpp startup noise from stderr
    # stdout contains the generated tokens; stderr has model-load info
    skip_prefixes = ('ggml','llm','load','print','sam','sched','common','build','main:',
                     'llama','system_info','generate','==','>>','-')
    lines = [l for l in output.split('\n')
             if l.strip() and not any(l.startswith(p) for p in skip_prefixes)]
    clean = '\n'.join(lines).strip()
    # If nothing left, use full output (model may have written to stdout directly)
    if not clean:
        clean = output
    return clean, elapsed

def main():
    questions = [json.loads(l) for l in open(DATA_FILE) if l.strip()]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results/mac_gsm8k_{ts}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"Output: {out_dir}")

    for var in VARIANTS:
        model_path = f"{MODEL_DIR}/Llama-3.2-3B-Instruct-{var}.gguf"
        if not os.path.exists(model_path):
            print(f"SKIP {var}: model not found"); continue
        
        out_file = f"{out_dir}/results_{var}.jsonl"
        correct = 0
        print(f"\n=== {var} ===")
        for i, q in enumerate(questions):
            try:
                gen, elapsed = run_question(model_path, q["question"])
                pred = extract_answer(gen)
                is_correct = pred == str(q["answer"]).replace(',','')
                if is_correct: correct += 1
                row = {
                    "variant": var, "question_id": q["question_id"],
                    "question": q["question"][:80], "answer": q["answer"],
                    "predicted": pred, "correct": is_correct,
                    "generated": gen[:200], "elapsed_s": round(elapsed,2),
                    "device": "Mac-M4", "backend": "CPU-ngl0"
                }
                with open(out_file, 'a') as f:
                    f.write(json.dumps(row) + '\n')
                status = "✓" if is_correct else "✗"
                print(f"  [{i+1:2d}/50] {status} pred={pred!r:6s} ans={q['answer']!r:6s}  ({elapsed:.1f}s)")
            except Exception as e:
                print(f"  [{i+1:2d}/50] ERROR: {e}")
        
        acc = correct / len(questions) * 100
        print(f"  => {var}: {correct}/{len(questions)} = {acc:.1f}%")
    
    print("\n=== Summary ===")
    for var in VARIANTS:
        out_file = f"{out_dir}/results_{var}.jsonl"
        if os.path.exists(out_file):
            rows = [json.loads(l) for l in open(out_file)]
            c = sum(1 for r in rows if r["correct"])
            print(f"  {var:10s}: {c}/{len(rows)} = {c/len(rows)*100:.1f}%")

if __name__ == "__main__":
    main()
