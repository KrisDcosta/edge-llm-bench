#!/usr/bin/env python3
"""
benchmark_runner.py — Orchestrate llama.cpp benchmarks on Android via adb.

Usage:
    python scripts/benchmark_runner.py --quant Q4_K_M --context 256
    python scripts/benchmark_runner.py --all              # run entire registry
    python scripts/benchmark_runner.py --id q4km-ctx256   # run one registry entry
    python scripts/benchmark_runner.py --smoke            # one prompt, one trial

Device requirements:
    - llama-cli at /data/local/tmp/llama-cli (push via adb)
    - libc++_shared.so at /data/local/tmp/ (if using shared STL)
    - GGUF model at /data/local/tmp/<variant>.gguf

Output:
    results/<run_id>.jsonl  — one JSONL record per trial
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path for imports
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from parse_llama_output import has_valid_timings, parse_llama_timings, timings_to_metrics

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEVICE_WORK_DIR = "/data/local/tmp"
LLAMA_CLI_DEVICE = f"{DEVICE_WORK_DIR}/llama-cli"
RESULTS_DIR = PROJECT_ROOT / "results"
SCHEMA_FILE = PROJECT_ROOT / "schemas" / "run.schema.json"
REGISTRY_FILE = PROJECT_ROOT / "experiments" / "registry.yaml"
PROMPTS_FILE = PROJECT_ROOT / "prompts" / "prompt-suite-v1.yaml"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

# Model files on device — keyed by gguf_variant
GGUF_DEVICE_PATHS = {
    "Q2_K":   f"{DEVICE_WORK_DIR}/Llama-3.2-3B-Instruct-Q2_K.gguf",
    "Q3_K_M": f"{DEVICE_WORK_DIR}/Llama-3.2-3B-Instruct-Q3_K_M.gguf",
    "Q4_K_M": f"{DEVICE_WORK_DIR}/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    "Q6_K":   f"{DEVICE_WORK_DIR}/Llama-3.2-3B-Instruct-Q6_K.gguf",
    "Q8_0":   f"{DEVICE_WORK_DIR}/Llama-3.2-3B-Instruct-Q8_0.gguf",
    "F16":    f"{DEVICE_WORK_DIR}/Llama-3.2-3B-Instruct-F16.gguf",
}

# Default smoke test prompt
SMOKE_PROMPT = "Answer in one sentence: what is 2 + 2?"

# ---------------------------------------------------------------------------
# ADB helpers
# ---------------------------------------------------------------------------

def adb(cmd: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    """Run an adb command."""
    full_cmd = ["adb"] + cmd
    try:
        result = subprocess.run(
            full_cmd, capture_output=True, text=True, timeout=timeout, check=check
        )
        return result
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"adb command timed out after {timeout}s: {' '.join(cmd)}")


def adb_shell(cmd: str, timeout: int = 300, check: bool = False) -> subprocess.CompletedProcess:
    """Run a shell command on device via adb."""
    return adb(["shell", cmd], timeout=timeout, check=check)


def check_device() -> dict:
    """Verify device is connected and return device info."""
    result = adb(["devices"], timeout=10)
    lines = [l for l in result.stdout.strip().splitlines() if "\tdevice" in l]
    if not lines:
        raise RuntimeError(
            "No Android device connected. Connect Pixel 6a and enable USB debugging."
        )

    # Get device properties
    info = {}
    props = {
        "manufacturer": "ro.product.manufacturer",
        "model": "ro.product.model",
        "android_version": "ro.build.version.release",
        "build_fingerprint": "ro.build.fingerprint",
    }
    for key, prop in props.items():
        r = adb_shell(f"getprop {prop}", timeout=10)
        info[key] = r.stdout.strip() or "unknown"

    return info


def get_llama_version() -> str:
    """Get llama.cpp version string from device binary."""
    r = adb_shell(f"LD_LIBRARY_PATH={DEVICE_WORK_DIR} {LLAMA_CLI_DEVICE} --version 2>&1 | head -1", timeout=15)
    version = r.stdout.strip()
    if not version:
        return "unknown"
    # Extract version/commit if present
    m = re.search(r"(version[:\s]+[\w.-]+|b\d{4}|[0-9a-f]{7,8})", version, re.I)
    return m.group(1) if m else version[:40]


def get_battery_pct() -> float | None:
    """Read battery percentage from device."""
    r = adb_shell("dumpsys battery | grep level", timeout=10)
    m = re.search(r"level:\s*(\d+)", r.stdout)
    return float(m.group(1)) if m else None


def get_peak_rss_mb(pid: str) -> float | None:
    """Sample peak RSS for a PID via dumpsys meminfo."""
    r = adb_shell(f"dumpsys meminfo {pid} 2>/dev/null | grep -E 'TOTAL|PSS|RSS' | head -5", timeout=15)
    # Look for "TOTAL PSS" or "Pss Total" line
    for line in r.stdout.splitlines():
        m = re.search(r"TOTAL\s+(\d+)", line)
        if m:
            return float(m.group(1)) / 1024.0  # KB → MB
    return None


def compute_file_sha256(path: Path) -> str | None:
    """Compute SHA256 of a local file."""
    if not path.exists():
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:16]  # short hash for logging


# ---------------------------------------------------------------------------
# Prompt loading
# ---------------------------------------------------------------------------

def load_prompts(prompt_set_id: str) -> dict[str, str]:
    """Load prompt suite from YAML file. Returns {prompt_id: text}."""
    try:
        import yaml
        with open(PROMPTS_FILE) as f:
            data = yaml.safe_load(f)
        prompts = {}
        for p in data.get("prompts", []):
            prompts[p["id"]] = p["text"]
        return prompts
    except ImportError:
        # Fallback: parse manually without yaml library
        prompts = {}
        current_id = None
        with open(PROMPTS_FILE) as f:
            for line in f:
                m = re.match(r'\s*id:\s*["\']?(\S+?)["\']?\s*$', line)
                if m:
                    current_id = m.group(1)
                m = re.match(r'\s*text:\s*["\'](.+?)["\']?\s*$', line)
                if m and current_id:
                    prompts[current_id] = m.group(1)
        return prompts


# ---------------------------------------------------------------------------
# Experiment registry loading
# ---------------------------------------------------------------------------

def load_registry() -> list[dict]:
    """Load experiment registry from YAML."""
    try:
        import yaml
        with open(REGISTRY_FILE) as f:
            data = yaml.safe_load(f)
        return data.get("experiments", [])
    except ImportError:
        raise RuntimeError("PyYAML required: pip install pyyaml")


# ---------------------------------------------------------------------------
# Core inference run
# ---------------------------------------------------------------------------

def run_trial(
    prompt: str,
    gguf_variant: str,
    context_length: int,
    output_length: int,
    device_info: dict,
    llama_version: str,
    artifact_hash: str | None,
    prompt_id: str,
    quant_bits: int,
    trial_index: int,
    is_warmup: bool,
) -> dict:
    """Run one inference trial on device. Returns schema-valid dict."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + f"-{uuid.uuid4().hex[:6]}"
    model_path = GGUF_DEVICE_PATHS.get(gguf_variant)

    if not model_path:
        return _failure_record(
            run_id, device_info, llama_version, gguf_variant, quant_bits,
            prompt_id, context_length, output_length, trial_index, is_warmup,
            artifact_hash, "UNSUPPORTED_VARIANT", "inference",
            f"No device path configured for variant {gguf_variant}", retryable=False,
        )

    # Build llama-cli command
    llama_cmd = (
        f"LD_LIBRARY_PATH={DEVICE_WORK_DIR} "
        f"{LLAMA_CLI_DEVICE} "
        f"-m {model_path} "
        f"-c {context_length} "
        f"-n {output_length} "
        f"--temp 0.0 "          # deterministic
        f"--seed 42 "
        f"-t 4 "                # 4 threads (Pixel 6a has 8 cores, 4 big)
        f"-p \"{prompt}\""
    )

    # Battery before
    battery_start = get_battery_pct()
    t_request_start = time.monotonic()

    try:
        result = adb_shell(llama_cmd, timeout=600)
    except RuntimeError as e:
        return _failure_record(
            run_id, device_info, llama_version, gguf_variant, quant_bits,
            prompt_id, context_length, output_length, trial_index, is_warmup,
            artifact_hash, "TIMEOUT", "inference", str(e), retryable=True,
        )

    t_end = time.monotonic()
    battery_end = get_battery_pct()

    # Check for OOM (process killed)
    if result.returncode == 137 or "Killed" in result.stderr or "out of memory" in result.stderr.lower():
        return _failure_record(
            run_id, device_info, llama_version, gguf_variant, quant_bits,
            prompt_id, context_length, output_length, trial_index, is_warmup,
            artifact_hash, "OOM", "inference",
            f"Process killed (OOM). returncode={result.returncode}", retryable=False,
        )

    # Combine stdout+stderr (llama.cpp logs timings to stderr)
    full_output = result.stdout + "\n" + result.stderr

    # Parse timings
    timings = parse_llama_timings(full_output)

    if not has_valid_timings(timings):
        return _failure_record(
            run_id, device_info, llama_version, gguf_variant, quant_bits,
            prompt_id, context_length, output_length, trial_index, is_warmup,
            artifact_hash, "PARSE_FAILURE", "inference",
            f"Could not parse timings from output. returncode={result.returncode}. stderr={result.stderr[:200]}",
            retryable=True,
        )

    metrics = timings_to_metrics(timings)

    # Peak RSS (best-effort — sampled post-run from proc info)
    # Note: for better accuracy, a background sampler during inference is ideal;
    # dumpsys meminfo post-run gives ~peak RSS estimate
    peak_rss = None  # populated by caller if PID tracking is added

    # Battery delta
    battery_drop = None
    battery_drop_per_1k = None
    if battery_start is not None and battery_end is not None:
        battery_drop = max(0.0, battery_start - battery_end)
        total_tokens = (metrics.get("input_tokens") or 0) + (metrics.get("output_tokens") or 0)
        if total_tokens > 0:
            battery_drop_per_1k = 1000.0 * battery_drop / total_tokens

    # Timing: use llama's own t_request_start as epoch 0; offset by wall clock
    prefill_s = metrics.get("prefill_s")
    gen_s = metrics.get("gen_s")
    e2e_s = metrics.get("e2e_s")

    # Reconstruct absolute timestamps from relative offsets
    t_model_forward_start = t_request_start  # load already done; forward starts at request
    t_first_token = t_request_start + prefill_s if prefill_s else None
    t_last_token = t_request_start + e2e_s if e2e_s else None

    return {
        "record_version": "1.0",
        "run_id": run_id,
        "status": "success",
        "device": device_info,
        "build": {
            "framework": "llama.cpp",
            "framework_version": llama_version,
            "gguf_variant": gguf_variant,
        },
        "model": {
            "name": "Llama-3.2-3B-Instruct",
            "artifact_hash": artifact_hash,
            "quant_bits": quant_bits,
        },
        "trial": {
            "prompt_id": prompt_id,
            "context_length": context_length,
            "output_length": output_length,
            "trial_index": trial_index,
            "is_warmup": is_warmup,
        },
        "timing_s": {
            "t_request_start": round(t_request_start, 4),
            "t_model_forward_start": round(t_model_forward_start, 4),
            "t_first_token": round(t_first_token, 4) if t_first_token else None,
            "t_last_token": round(t_last_token, 4) if t_last_token else None,
        },
        "tokens": {
            "input_tokens": metrics.get("input_tokens"),
            "output_tokens": metrics.get("output_tokens"),
        },
        "metrics": {
            "ttft_s": round(metrics["ttft_s"], 4) if metrics.get("ttft_s") else None,
            "prefill_s": round(prefill_s, 4) if prefill_s else None,
            "prefill_tps": round(metrics["prefill_tps"], 2) if metrics.get("prefill_tps") else None,
            "gen_s": round(gen_s, 4) if gen_s else None,
            "decode_tps": round(metrics["decode_tps"], 2) if metrics.get("decode_tps") else None,
            "e2e_s": round(e2e_s, 4) if e2e_s else None,
            "gen_over_prefill": round(metrics["gen_over_prefill"], 4) if metrics.get("gen_over_prefill") else None,
            "prefill_frac": round(metrics["prefill_frac"], 4) if metrics.get("prefill_frac") else None,
            "gen_frac": round(metrics["gen_frac"], 4) if metrics.get("gen_frac") else None,
        },
        "resources": {
            "peak_rss_mb": peak_rss,
            "battery_start_pct": battery_start,
            "battery_end_pct": battery_end,
            "battery_drop_pct": round(battery_drop, 4) if battery_drop is not None else None,
            "battery_drop_per_1k_tokens": round(battery_drop_per_1k, 6) if battery_drop_per_1k is not None else None,
            "temperature_c": None,
        },
        "failure": None,
    }


def _failure_record(
    run_id, device_info, llama_version, gguf_variant, quant_bits,
    prompt_id, context_length, output_length, trial_index, is_warmup,
    artifact_hash, code, stage, message, retryable: bool,
) -> dict:
    """Build a schema-valid failure record."""
    t_now = time.monotonic()
    return {
        "record_version": "1.0",
        "run_id": run_id,
        "status": "failed",
        "device": device_info,
        "build": {
            "framework": "llama.cpp",
            "framework_version": llama_version,
            "gguf_variant": gguf_variant,
        },
        "model": {
            "name": "Llama-3.2-3B-Instruct",
            "artifact_hash": artifact_hash,
            "quant_bits": quant_bits,
        },
        "trial": {
            "prompt_id": prompt_id,
            "context_length": context_length,
            "output_length": output_length,
            "trial_index": trial_index,
            "is_warmup": is_warmup,
        },
        "timing_s": {
            "t_request_start": round(t_now, 4),
            "t_model_forward_start": None,
            "t_first_token": None,
            "t_last_token": None,
        },
        "tokens": {"input_tokens": None, "output_tokens": None},
        "metrics": {
            "ttft_s": None, "prefill_s": None, "prefill_tps": None,
            "gen_s": None, "decode_tps": None, "e2e_s": None,
            "gen_over_prefill": None, "prefill_frac": None, "gen_frac": None,
        },
        "resources": {
            "peak_rss_mb": None, "battery_start_pct": None, "battery_end_pct": None,
            "battery_drop_pct": None, "battery_drop_per_1k_tokens": None, "temperature_c": None,
        },
        "failure": {
            "code": code,
            "stage": stage,
            "message": message[:500],
            "retryable": retryable,
        },
    }


# ---------------------------------------------------------------------------
# Experiment runner
# ---------------------------------------------------------------------------

def run_experiment(entry: dict, prompts: dict, device_info: dict, llama_version: str,
                   output_file: Path, artifact_hash: str | None = None) -> dict:
    """Run all trials for one registry entry. Returns summary stats."""
    gguf_variant = entry["gguf_variant"]
    quant_bits = entry["quant_bits"]
    context_length = entry["context_length"]
    output_length = entry["output_length"]
    warmups = entry.get("warmups", 2)
    trials = entry.get("trials", 5)
    prompt_set_id = entry.get("prompt_set_id", "prompt-suite-v1")
    exp_id = entry["id"]

    print(f"\n{'='*60}")
    print(f"Experiment: {exp_id}")
    print(f"  Quant: {gguf_variant} ({quant_bits}-bit)")
    print(f"  Context: {context_length} | Output: {output_length} tokens")
    print(f"  Warmups: {warmups} | Trials: {trials}")
    print(f"{'='*60}")

    # Use first prompt in suite for now (extend for full suite sweep later)
    prompt_id = list(prompts.keys())[0]
    prompt_text = prompts[prompt_id]

    output_file.parent.mkdir(parents=True, exist_ok=True)
    records = []

    total_runs = warmups + trials
    for i in range(total_runs):
        is_warmup = i < warmups
        trial_index = i if is_warmup else i - warmups
        label = f"warmup {i+1}/{warmups}" if is_warmup else f"trial {trial_index+1}/{trials}"
        print(f"  [{label}] running...", end=" ", flush=True)

        record = run_trial(
            prompt=prompt_text,
            gguf_variant=gguf_variant,
            context_length=context_length,
            output_length=output_length,
            device_info=device_info,
            llama_version=llama_version,
            artifact_hash=artifact_hash,
            prompt_id=prompt_id,
            quant_bits=quant_bits,
            trial_index=trial_index,
            is_warmup=is_warmup,
        )

        status = record["status"]
        if status == "success":
            tps = record["metrics"].get("decode_tps")
            ttft = record["metrics"].get("ttft_s")
            print(f"OK  decode={tps:.1f} tok/s  TTFT={ttft:.2f}s" if tps and ttft else "OK")
        else:
            code = record["failure"]["code"] if record.get("failure") else "?"
            print(f"FAIL [{code}]")

        # Append to JSONL (append-only, one record per line)
        with open(output_file, "a") as f:
            f.write(json.dumps(record) + "\n")

        records.append(record)

        # No cooldown between trials within same experiment
        # (2-min cooldown is between experiments — caller's responsibility)

    # Summary for this experiment
    success_records = [r for r in records if r["status"] == "success" and not r["trial"]["is_warmup"]]
    failed = trials - len(success_records)

    print(f"\n  Summary: {len(success_records)}/{trials} trials OK, {failed} failed")
    if success_records:
        tps_values = [r["metrics"]["decode_tps"] for r in success_records if r["metrics"].get("decode_tps")]
        if tps_values:
            print(f"  Decode TPS: mean={sum(tps_values)/len(tps_values):.1f}  "
                  f"min={min(tps_values):.1f}  max={max(tps_values):.1f}")

    return {"exp_id": exp_id, "success": len(success_records), "failed": failed}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Run llama.cpp benchmarks on Android via adb")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--smoke", action="store_true", help="Run one smoke test (1 trial, Q4_K_M, ctx=256)")
    group.add_argument("--id", metavar="EXP_ID", help="Run a single registry entry by ID")
    group.add_argument("--quant", metavar="VARIANT", help="Run all registry entries for a quant variant (e.g. Q4_K_M)")
    group.add_argument("--all", action="store_true", help="Run all planned registry entries")

    args = parser.parse_args()

    # Check device
    print("Checking device connection...")
    try:
        device_info = check_device()
        print(f"  Device: {device_info['manufacturer']} {device_info['model']} (Android {device_info['android_version']})")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # Check llama-cli
    r = adb_shell(f"ls {LLAMA_CLI_DEVICE} 2>&1")
    if "No such file" in r.stdout:
        print(f"ERROR: llama-cli not found at {LLAMA_CLI_DEVICE}")
        print("Build and push it first: ./scripts/build_llamacpp_android.sh then adb push")
        sys.exit(1)

    # Get version
    llama_version = get_llama_version()
    print(f"  llama.cpp: {llama_version}")

    # Load prompts
    try:
        prompts = load_prompts("prompt-suite-v1")
    except Exception as e:
        print(f"ERROR loading prompts: {e}")
        sys.exit(1)

    # Ensure results dir exists
    RESULTS_DIR.mkdir(exist_ok=True)

    # ---- Smoke test ----
    if args.smoke:
        print(f"\nSmoke test: Q4_K_M, ctx=256, 1 trial")
        out_file = RESULTS_DIR / f"smoke-{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"
        entry = {
            "id": "smoke",
            "gguf_variant": "Q4_K_M",
            "quant_bits": 4,
            "context_length": 256,
            "output_length": 64,
            "warmups": 0,
            "trials": 1,
            "prompt_set_id": "prompt-suite-v1",
        }
        summary = run_experiment(entry, prompts, device_info, llama_version, out_file)
        print(f"\nSmoke test complete. Log: {out_file}")
        return

    # ---- Registry runs ----
    registry = load_registry()

    if args.id:
        entries = [e for e in registry if e["id"] == args.id]
        if not entries:
            print(f"ERROR: No experiment with id '{args.id}' in registry")
            sys.exit(1)
    elif args.quant:
        entries = [e for e in registry if e.get("gguf_variant") == args.quant and e.get("status") == "planned"]
        if not entries:
            print(f"ERROR: No planned experiments for variant '{args.quant}'")
            sys.exit(1)
    else:  # --all
        entries = [e for e in registry if e.get("status") == "planned"]

    print(f"\nRunning {len(entries)} experiment(s)...")
    out_file = RESULTS_DIR / f"run-{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"
    print(f"Output: {out_file}")

    all_summaries = []
    for i, entry in enumerate(entries):
        if i > 0:
            print(f"\n[2-minute cooldown between experiments...]")
            time.sleep(120)

        summary = run_experiment(entry, prompts, device_info, llama_version, out_file)
        all_summaries.append(summary)

    # Final summary
    total_ok = sum(s["success"] for s in all_summaries)
    total_fail = sum(s["failed"] for s in all_summaries)
    print(f"\n{'='*60}")
    print(f"RUN COMPLETE: {len(entries)} experiments | {total_ok} trials OK | {total_fail} failed")
    print(f"Results: {out_file}")
    print(f"\nValidate: python scripts/validate_results.py {out_file}")
    print(f"Figures:  python analysis/generate_figures.py {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
