#!/usr/bin/env python3
"""
quality_eval_m4_server.py — safer M4 quality evaluation via llama-server.

This replaces the unsafe per-question llama-cli workflow. The old runner loaded a
multi-GB GGUF once per question, which caused timeouts and memory pressure. This
runner starts one persistent llama-server per variant, evaluates one dataset, and
saves progress after every question.

Examples:
  python3 scripts/quality_eval_m4_server.py --dataset data/boolq_100.yaml --tag boolq Q4_K_M
  python3 scripts/quality_eval_m4_server.py --dataset data/boolq_100.yaml --tag boolq --limit 10 Q2_K
  python3 scripts/quality_eval_m4_server.py --dataset data/arc_easy_100.yaml --tag arc_easy --ngl 99 Q2_K Q4_K_M
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
MODELS_DIR = PROJECT_ROOT / "local-models" / "llama3_2_3b_gguf"
OUTPUT_FILE = PROJECT_ROOT / "results" / "quality_metrics_m4_server.json"
LOG_DIR = PROJECT_ROOT / "results" / "m4_quality_server_logs"

ALL_VARIANTS = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
YESNO_GRAMMAR = 'root ::= ("yes" | "no" | "Yes" | "No")'
MODEL_SIZES_GB = {
    "Q2_K": 1.3,
    "Q3_K_M": 1.6,
    "Q4_K_S": 1.8,
    "Q4_K_M": 1.9,
    "Q5_K_M": 2.2,
    "Q6_K": 2.5,
    "Q8_0": 3.2,
}


def get_model_path(variant: str) -> Path:
    return MODELS_DIR / f"Llama-3.2-3B-Instruct-{variant}.gguf"


def format_llama3_instruct(user_message: str, assistant_prefix: str = "") -> str:
    return (
        "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\n"
        f"{user_message}"
        "<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        f"{assistant_prefix}"
    )


def load_prompts_from_yaml(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "prompts" in data:
        prompts = data["prompts"]
    elif isinstance(data, list):
        prompts = data
    else:
        raise ValueError(f"Unexpected YAML structure: {path}")
    for prompt in prompts:
        prompt.setdefault("answer_type", "substring")
        prompt.setdefault("category", "unknown")
    return prompts


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def score_substring(model_output: str, expected: str) -> bool:
    return expected.lower().strip() in model_output.lower()


def score_choice(model_output: str, expected: str) -> bool:
    letter = expected.upper().strip()
    if letter not in ("A", "B", "C", "D"):
        return score_substring(model_output, expected)
    out = model_output.strip()
    if re.match(rf"^{letter}(?:[.):\s]|$)", out, re.IGNORECASE):
        return True
    if re.search(rf"\bAnswer\s*(?:is\s*)?:?\s*{letter}\b", out, re.IGNORECASE):
        return True
    if re.search(rf"\b\(?{letter}[.):]?\b", out, re.IGNORECASE):
        return True
    if re.search(rf"\bthe\s+(?:correct\s+)?answer\s+is\s+{letter}\b", out, re.IGNORECASE):
        return True
    return False


def score_yesno(model_output: str, expected: str) -> bool:
    target = expected.lower().strip()
    if target not in ("yes", "no"):
        return score_substring(model_output, expected)
    out = model_output.strip().lower()
    if re.match(rf"^{target}\b", out):
        return True
    if re.search(rf"\banswer\s*(?:is\s*)?:?\s*{target}\b", out):
        return True
    if len(out) <= 20 and re.search(rf"\b{target}\b", out):
        return True
    first_word = re.split(r"[\s.,!?]", out)[0].strip()
    return first_word == target


def score_answer(model_output: str, expected: str, answer_type: str) -> bool:
    if answer_type == "choice":
        return score_choice(model_output, expected)
    if answer_type == "yesno":
        return score_yesno(model_output, expected)
    return score_substring(model_output, expected)


def parse_choice_options(prompt: str) -> dict[str, str]:
    """Extract A-D option text from compact MCQ prompts."""
    pattern = re.compile(
        r"\b([ABCD])\)\s*(.*?)(?=\s+\b[ABCD]\)\s*|\s+Answer\s+with|$)",
        re.DOTALL,
    )
    return {
        match.group(1).upper(): re.sub(r"\s+", " ", match.group(2)).strip(" .")
        for match in pattern.finditer(prompt)
    }


def normalize_choice_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def map_option_text_to_label(model_output: str, prompt: str) -> str | None:
    """Map generated option text back to A-D when the model emits content."""
    output_norm = normalize_choice_text(model_output)
    if not output_norm:
        return None

    candidates: list[tuple[int, str]] = []
    for label, option_text in parse_choice_options(prompt).items():
        option_norm = normalize_choice_text(option_text)
        if not option_norm:
            continue
        if output_norm == option_norm:
            candidates.append((1000 + len(option_norm), label))
        elif len(output_norm) >= 2 and option_norm.startswith(output_norm):
            candidates.append((500 + len(output_norm), label))
        elif len(option_norm) >= 2 and output_norm.startswith(option_norm):
            candidates.append((400 + len(option_norm), label))

    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def extract_answer(content: str, answer_type: str, prompt: str) -> str:
    content = content.strip()
    if answer_type == "choice":
        if match := re.match(r"^([ABCD])(?:[.):\s]|$)", content, re.IGNORECASE):
            return match.group(1).upper()
        if match := re.search(
            r"(?:\banswer\s*(?:is\s*)?:?\s*|\bthe\s+(?:correct\s+)?answer\s+is\s+|\()"
            r"([ABCD])\b",
            content[:200],
            re.IGNORECASE,
        ):
            return match.group(1).upper()
        if mapped := map_option_text_to_label(content, prompt):
            return mapped
    if answer_type == "yesno":
        if match := re.match(r"^(yes|no)(?:[.,!?\s]|$)", content, re.IGNORECASE):
            return match.group(1).capitalize()
        if match := re.search(
            r"(?:\banswer\s*(?:is\s*)?:?\s*|\bthe\s+answer\s+is\s+)(yes|no)\b",
            content[:200],
            re.IGNORECASE,
        ):
            return match.group(1).capitalize()
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    return (lines[0] if lines else content.strip())[:500]


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(method: str, url: str, payload: dict[str, Any] | None = None,
              timeout: float = 10.0) -> dict[str, Any] | None:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return json.loads(body) if body else {}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def wait_for_server(base_url: str, proc: subprocess.Popen, timeout_s: int) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        for endpoint in ("/health", "/props", "/v1/models"):
            response = http_json("GET", base_url + endpoint, timeout=2.0)
            if response is not None:
                return True
        time.sleep(1)
    return False


def start_server(args: argparse.Namespace, variant: str, port: int) -> tuple[subprocess.Popen, Path]:
    llama_server = shutil.which("llama-server")
    if not llama_server:
        raise RuntimeError("llama-server not found on PATH")

    model_path = get_model_path(variant)
    if not model_path.exists():
        raise FileNotFoundError(model_path)

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"{args.tag}_{variant}_{ts}.log"
    log_fh = log_path.open("w", encoding="utf-8")

    cmd = [
        llama_server,
        "-m", str(model_path),
        "-c", str(args.ctx_size),
        "-ngl", str(args.ngl),
        "-t", str(args.threads),
        "--host", "127.0.0.1",
        "--port", str(port),
        "-np", "1",
        "--no-cont-batching",
        "--timeout", str(args.server_io_timeout),
        "--alias", f"m4-{variant}",
        "--log-disable",
    ]
    print(f"  [{variant}] starting llama-server on port {port}")
    print(f"  [{variant}] log: {log_path}")
    proc = subprocess.Popen(
        cmd,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=PROJECT_ROOT,
        text=True,
        start_new_session=True,
    )
    # Keep the file handle alive via proc object so logs are not closed immediately.
    proc._codex_log_fh = log_fh  # type: ignore[attr-defined]
    return proc, log_path


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
    log_fh = getattr(proc, "_codex_log_fh", None)
    if log_fh:
        log_fh.close()


def request_completion(base_url: str, prompt: str, answer_type: str,
                       n_tokens: int, timeout_s: int) -> str | None:
    # Multiple-choice generation is biased if the model must emit A/B/C/D
    # immediately after the assistant header. Prefixing "Answer:" turns the
    # task into a normal answer-completion next-token decision.
    assistant_prefix = "Answer: " if answer_type == "choice" else ""
    payload = {
        "prompt": format_llama3_instruct(prompt, assistant_prefix=assistant_prefix),
        "n_predict": n_tokens,
        "temperature": 0.0,
        "seed": 42,
        "stream": False,
        "cache_prompt": False,
        "stop": ["<|eot_id|>", "<|end_of_text|>"],
    }
    if answer_type == "yesno":
        payload["grammar"] = YESNO_GRAMMAR
    response = http_json("POST", base_url + "/completion", payload, timeout=timeout_s)
    if not response:
        return None
    content = response.get("content")
    if content is None and isinstance(response.get("choices"), list):
        choice = response["choices"][0]
        content = choice.get("text") or choice.get("message", {}).get("content")
    if not isinstance(content, str):
        return None
    return extract_answer(content, answer_type, prompt)


def wilson_ci(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    p_hat = correct / total
    z = 1.96
    denom = 1 + z * z / total
    margin = (z * (p_hat * (1 - p_hat) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return round(margin * 100, 1)


def build_result(variant: str, args: argparse.Namespace, prompts: list[dict[str, Any]],
                 per_question: list[dict[str, Any]], status: str) -> dict[str, Any]:
    correct = sum(1 for q in per_question if q.get("correct"))
    total = len(per_question)
    categories: dict[str, dict[str, int]] = {}
    for q in per_question:
        cat = q.get("category", "unknown")
        categories.setdefault(cat, {"correct": 0, "total": 0})
        categories[cat]["total"] += 1
        if q.get("correct"):
            categories[cat]["correct"] += 1
    choice_outputs = [
        q.get("model_output", "").strip().upper()
        for q in per_question
        if q.get("status") == "success"
        and q.get("answer_type") == "choice"
        and q.get("model_output", "").strip().upper() in {"A", "B", "C", "D"}
    ]
    choice_distribution = {label: choice_outputs.count(label) for label in ("A", "B", "C", "D")}
    choice_label_collapse = False
    if len(choice_outputs) >= 20:
        max_share = max(choice_distribution.values()) / len(choice_outputs)
        choice_label_collapse = max_share > args.max_choice_label_share

    result = {
        "variant": variant,
        "tag": args.tag,
        "status": status,
        "runner": "llama-server",
        "dataset": args.dataset_name,
        "dataset_sha256": args.dataset_sha256,
        "model_size_gb": MODEL_SIZES_GB.get(variant, 0.0),
        "accuracy_pct": round(100.0 * correct / total, 1) if total else None,
        "wilson_ci_95_pct": wilson_ci(correct, total) if total else None,
        "correct": correct,
        "total": total,
        "expected_total": len(prompts),
        "per_category": {
            cat: {"accuracy_pct": round(100.0 * v["correct"] / v["total"], 1), **v}
            for cat, v in categories.items()
        },
        "per_question": per_question,
    }
    if choice_outputs:
        result["choice_prediction_distribution"] = choice_distribution
        result["choice_label_collapse"] = choice_label_collapse
        result["max_choice_label_share"] = round(
            max(choice_distribution.values()) / len(choice_outputs), 3
        )
    return result


def save_results(path: Path, results: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(results, indent=2), encoding="utf-8")
    tmp.replace(path)


def evaluate_variant(args: argparse.Namespace, variant: str, prompts: list[dict[str, Any]],
                     results: dict[str, Any], output_path: Path) -> None:
    key = f"{args.tag}:{variant}"
    existing = results.get(key, {})
    dataset_matches = existing.get("dataset_sha256") == args.dataset_sha256
    if (
        existing.get("status") == "success"
        and existing.get("total") == len(prompts)
        and dataset_matches
        and not args.force
    ):
        print(f"  [{variant}] skip complete result in {output_path}")
        return

    completed_by_id = {
        q["prompt_id"]: q
        for q in existing.get("per_question", [])
        if q.get("status") == "success" and dataset_matches and not args.force
    }
    per_question = [completed_by_id[p["id"]] for p in prompts if p["id"] in completed_by_id]

    port = args.port or find_free_port()
    proc, _ = start_server(args, variant, port)
    base_url = f"http://127.0.0.1:{port}"
    try:
        if not wait_for_server(base_url, proc, args.server_start_timeout):
            raise RuntimeError(f"llama-server did not become ready for {variant}")

        consecutive_failures = 0
        done_ids = {q["prompt_id"] for q in per_question}
        total = len(prompts)
        for idx, prompt in enumerate(prompts, 1):
            if prompt["id"] in done_ids:
                continue

            answer_type = prompt.get("answer_type", "substring")
            n_tokens = 4 if answer_type in ("choice", "yesno") else 32
            print(f"    [{variant} {idx:3d}/{total}] {prompt['id']:<30} ... ", end="", flush=True)

            model_output = request_completion(
                base_url,
                prompt["prompt"],
                answer_type=answer_type,
                n_tokens=n_tokens,
                timeout_s=args.request_timeout,
            )

            if model_output is None:
                consecutive_failures += 1
                row = {
                    "prompt_id": prompt["id"],
                    "category": prompt.get("category", "unknown"),
                    "answer_type": answer_type,
                    "expected": prompt["answer"],
                    "model_output": None,
                    "correct": False,
                    "status": "timeout",
                }
                print("TIMEOUT")
            else:
                consecutive_failures = 0
                correct = score_answer(model_output, prompt["answer"], answer_type)
                row = {
                    "prompt_id": prompt["id"],
                    "category": prompt.get("category", "unknown"),
                    "answer_type": answer_type,
                    "expected": prompt["answer"],
                    "model_output": model_output[:200],
                    "correct": correct,
                    "status": "success",
                }
                print(f"{'✓' if correct else '✗'} got={model_output[:40]!r}")

            per_question.append(row)
            status = "running" if len(per_question) < len(prompts) else "success"
            results[key] = build_result(variant, args, prompts, per_question, status)
            save_results(output_path, results)

            if consecutive_failures >= args.max_consecutive_failures:
                results[key] = build_result(variant, args, prompts, per_question, "failed")
                save_results(output_path, results)
                raise RuntimeError(
                    f"{variant}: aborting after {consecutive_failures} consecutive failures"
                )

        final = build_result(variant, args, prompts, per_question, "success")
        if final.get("choice_label_collapse") and not args.allow_choice_collapse:
            final["status"] = "failed_label_collapse"
            results[key] = final
            save_results(output_path, results)
            raise RuntimeError(
                f"{variant}: suspicious choice-label collapse "
                f"({final['choice_prediction_distribution']}, "
                f"max_share={final['max_choice_label_share']})"
            )
        results[key] = final
        save_results(output_path, results)
    finally:
        stop_server(proc)


def main() -> int:
    parser = argparse.ArgumentParser(description="M4 quality eval using persistent llama-server")
    parser.add_argument("variants", nargs="*", help="Variants to evaluate")
    parser.add_argument("--all", action="store_true", help="Run all 7 K-quant variants")
    parser.add_argument("--dataset", required=True, help="YAML dataset path, e.g. data/boolq_100.yaml")
    parser.add_argument("--tag", required=True, help="Result tag, e.g. boolq")
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    parser.add_argument("--limit", type=int, default=None, help="Limit questions for smoke tests")
    parser.add_argument("--force", action="store_true", help="Recompute even if result exists")
    parser.add_argument("--ctx-size", type=int, default=2048)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--ngl", type=int, default=99, help="GPU layers; use 0 for CPU-only")
    parser.add_argument("--port", type=int, default=0, help="Fixed port; default picks a free port")
    parser.add_argument("--server-start-timeout", type=int, default=180)
    parser.add_argument("--server-io-timeout", type=int, default=600)
    parser.add_argument("--request-timeout", type=int, default=120)
    parser.add_argument("--max-consecutive-failures", type=int, default=5)
    parser.add_argument(
        "--max-choice-label-share",
        type=float,
        default=0.80,
        help="Fail choice evals when one predicted label exceeds this share",
    )
    parser.add_argument(
        "--allow-choice-collapse",
        action="store_true",
        help="Record but do not fail suspicious choice-label collapse",
    )
    args = parser.parse_args()

    variants = ALL_VARIANTS if args.all or not args.variants else args.variants
    unknown = [v for v in variants if v not in ALL_VARIANTS]
    if unknown:
        print(f"Unknown variants: {unknown}", file=sys.stderr)
        return 1

    dataset_path = Path(args.dataset)
    if not dataset_path.is_absolute():
        dataset_path = PROJECT_ROOT / dataset_path
    args.dataset_name = dataset_path.name
    args.dataset_sha256 = file_sha256(dataset_path)
    prompts = load_prompts_from_yaml(dataset_path)
    if args.limit is not None:
        prompts = prompts[:args.limit]

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    if output_path.exists():
        results = json.loads(output_path.read_text(encoding="utf-8"))
    else:
        results = {}

    print("=== M4 quality eval via llama-server ===")
    print(f"dataset : {dataset_path.name} ({len(prompts)} questions)")
    print(f"tag     : {args.tag}")
    print(f"variants: {' '.join(variants)}")
    print(f"output  : {output_path}")
    print(f"ngl     : {args.ngl}")

    for variant in variants:
        evaluate_variant(args, variant, prompts, results, output_path)

    print("\nSummary")
    for variant in variants:
        r = results.get(f"{args.tag}:{variant}", {})
        print(
            f"{variant:<8} status={r.get('status')} "
            f"acc={r.get('accuracy_pct')} correct={r.get('correct')}/{r.get('total')}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        raise SystemExit(130)
