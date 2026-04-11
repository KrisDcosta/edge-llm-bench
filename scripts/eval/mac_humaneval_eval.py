#!/usr/bin/env python3
"""Mac-native HumanEval evaluator using llama-cli directly."""
import json, subprocess, re, os, sys, time
from datetime import datetime

LLAMA_CLI = "/opt/homebrew/bin/llama-completion"
MODEL_DIR  = "local-models/llama3_2_3b_gguf"
DATA_FILE  = "data/humaneval_50.jsonl"
N_THREADS  = 4
N_PREDICT  = 256
CTX        = 512
TEMP       = 0.1

PROMPT_TMPL = """Complete the following Python function. Output ONLY the function body, no explanation.

{prompt}"""

VARIANTS = ["Q2_K","Q3_K_M","Q4_K_S","Q4_K_M","Q5_K_M","Q6_K","Q8_0"]

def extract_code(text, entry_point):
    # Try to find function definition
    lines = text.split('\n')
    code_lines = []
    in_func = False
    for line in lines:
        if f'def {entry_point}' in line:
            in_func = True
        if in_func:
            code_lines.append(line)
            # Stop at next top-level def or class (not nested)
            if code_lines and len(code_lines) > 1 and line and not line[0].isspace() and line.strip() and not line.strip().startswith('#'):
                if line.strip().startswith('def ') or line.strip().startswith('class '):
                    code_lines = code_lines[:-1]
                    break
    return '\n'.join(code_lines) if code_lines else text.strip()

def check_syntax(code):
    try:
        compile(code, '<string>', 'exec')
        return True
    except SyntaxError:
        return False

def run_tests(code, test_code, entry_point):
    """Run tests in isolated subprocess."""
    full_code = code + "\n\n" + test_code + f"\n\ncheck({entry_point})\n"
    try:
        result = subprocess.run(
            [sys.executable, "-c", full_code],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False

def run_inference(model_path, prompt_text):
    prompt_file = "/tmp/humaneval_prompt_mac.txt"
    with open(prompt_file, 'w') as f:
        f.write(prompt_text)
    t0 = time.time()
    result = subprocess.run([
        LLAMA_CLI, "-m", model_path,
        "-f", prompt_file,
        "-n", str(N_PREDICT), "-t", str(N_THREADS),
        "-c", str(CTX), "--temp", str(TEMP),
        "-ngl", "99",       # Metal GPU for speed
        "--single-turn",    # Exit cleanly after one response
    ], capture_output=True, text=True, timeout=180)
    elapsed = time.time() - t0
    # Extract model response after "assistant" marker
    out = result.stdout.strip()
    if 'assistant' in out:
        out = out.split('assistant')[-1].strip()
    return out, elapsed

def main():
    problems = [json.loads(l) for l in open(DATA_FILE) if l.strip()]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = f"results/mac_humaneval_{ts}"
    os.makedirs(out_dir, exist_ok=True)
    print(f"Output: {out_dir}")

    for var in VARIANTS:
        model_path = f"{MODEL_DIR}/Llama-3.2-3B-Instruct-{var}.gguf"
        if not os.path.exists(model_path):
            print(f"SKIP {var}: model not found"); continue
        
        out_file = f"{out_dir}/results_{var}.jsonl"
        passed = 0
        print(f"\n=== {var} ===")
        for i, prob in enumerate(problems):
            try:
                prompt_text = PROMPT_TMPL.format(prompt=prob["prompt"])
                gen, elapsed = run_inference(model_path, prompt_text)
                # Prepend the original function signature from prompt
                full_code = prob["prompt"] + "\n" + gen
                code = extract_code(full_code, prob["entry_point"])
                syntax_ok = check_syntax(code)
                test_ok = run_tests(code, prob.get("test",""), prob["entry_point"]) if syntax_ok else False
                if test_ok: passed += 1
                row = {
                    "variant": var, "problem_id": i,
                    "task_id": prob["task_id"], "entry_point": prob["entry_point"],
                    "syntax_ok": syntax_ok, "test_passed": test_ok,
                    "generated_code": gen[:300], "elapsed_s": round(elapsed,2),
                    "device": "Mac-M4", "backend": "CPU-ngl0"
                }
                with open(out_file, 'a') as f:
                    f.write(json.dumps(row) + '\n')
                status = "✓" if test_ok else ("~" if syntax_ok else "✗")
                print(f"  [{i+1:2d}/50] {status} {prob['entry_point'][:30]:30s} ({elapsed:.1f}s)")
            except Exception as e:
                print(f"  [{i+1:2d}/50] ERROR {prob.get('entry_point','?')}: {e}")
        
        acc = passed / len(problems) * 100
        print(f"  => {var}: {passed}/{len(problems)} pass@1 = {acc:.1f}%")

    print("\n=== Summary ===")
    for var in VARIANTS:
        out_file = f"{out_dir}/results_{var}.jsonl"
        if os.path.exists(out_file):
            rows = [json.loads(l) for l in open(out_file)]
            p = sum(1 for r in rows if r["test_passed"])
            s = sum(1 for r in rows if r["syntax_ok"])
            print(f"  {var:10s}: pass@1={p}/{len(rows)} ({p/len(rows)*100:.1f}%)  syntax_ok={s}/{len(rows)}")

if __name__ == "__main__":
    main()
