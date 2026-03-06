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
import threading
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
# llama.cpp b1+ split the old llama-cli into:
#   llama-cli      → interactive chat (default mode)
#   llama-completion → single-shot completion (what we need for benchmarking)
LLAMA_CLI_DEVICE = f"{DEVICE_WORK_DIR}/llama-completion"
RESULTS_DIR = PROJECT_ROOT / "results"
SCHEMA_FILE = PROJECT_ROOT / "schemas" / "run.schema.json"
REGISTRY_FILE = PROJECT_ROOT / "experiments" / "registry.yaml"
PROMPTS_FILE = PROJECT_ROOT / "prompts" / "prompt-suite-v1.yaml"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

# Global WiFi ADB IP (set by --wifi-adb flag so reconnection logic can reference it)
_WIFI_IP: str | None = None

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

def _find_adb() -> str:
    """Find adb binary — checks PATH, then common Android SDK locations."""
    import shutil
    # 1. Use ADB env var if set
    if adb_env := os.environ.get("ADB"):
        return adb_env
    # 2. Check PATH
    if shutil.which("adb"):
        return "adb"
    # 3. Check common macOS / Linux SDK locations
    candidates = [
        Path.home() / "Library/Android/sdk/platform-tools/adb",   # macOS default
        Path("/usr/local/lib/android/sdk/platform-tools/adb"),     # CI / Linux
        Path("/opt/android-sdk/platform-tools/adb"),
        Path("/opt/homebrew/bin/adb"),
    ]
    if android_home := os.environ.get("ANDROID_HOME"):
        candidates.insert(0, Path(android_home) / "platform-tools/adb")
    for c in candidates:
        if c.exists():
            return str(c)
    raise RuntimeError(
        "adb not found. Add Android SDK platform-tools to PATH or set ADB=/path/to/adb"
    )

ADB_BIN = _find_adb()


def adb(cmd: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess:
    """Run an adb command."""
    full_cmd = [ADB_BIN] + cmd
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


def compute_model_hash(gguf_variant: str) -> str | None:
    """Compute SHA256 of local GGUF model file. Returns hex string or None."""
    model_dir = PROJECT_ROOT / "local-models" / "llama3_2_3b_gguf"
    candidates = [
        model_dir / f"{gguf_variant}.gguf",
        model_dir / f"Llama-3.2-3B-Instruct-{gguf_variant}.gguf",
    ]
    import hashlib
    for path in candidates:
        if path.exists():
            sha = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
                    sha.update(chunk)
            return sha.hexdigest()
    return None


def setup_wifi_adb() -> str | None:
    """Switch ADB to TCP mode, connect over WiFi. Returns device IP or None on failure.

    Call once before the benchmark sweep. The device must be connected via USB first.
    After calling this, unplug the USB cable so the device genuinely discharges —
    making dumpsys battery measurements valid.
    """
    print("  Switching to WiFi ADB mode (for battery discharge measurements)...")
    # Enable TCP/IP mode on device
    r = adb(["tcpip", "5555"], timeout=15, check=False)
    time.sleep(3)  # Device needs a moment to switch modes

    # Get device WiFi IP
    device_ip = None
    for iface in ("wlan0", "wlan"):
        r2 = adb_shell(f"ip addr show {iface} 2>/dev/null | grep 'inet ' | awk '{{print $2}}' | cut -d/ -f1", timeout=10)
        candidate = r2.stdout.strip()
        if candidate and re.match(r"^\d+\.\d+\.\d+\.\d+$", candidate):
            device_ip = candidate
            break

    if not device_ip:
        print("  WARNING: Could not detect device WiFi IP. Continuing with USB ADB.")
        print("           Battery measurements may be zero (device is charging over USB).")
        return None

    # Connect over WiFi
    r3 = adb(["connect", f"{device_ip}:5555"], timeout=15, check=False)
    if "connected" in r3.stdout.lower() or "already" in r3.stdout.lower():
        print(f"  WiFi ADB ready: {device_ip}:5555")
        print()
        print("  *** Unplug the USB cable now for accurate battery measurements. ***")
        print("  *** The benchmark will continue via WiFi.                        ***")
        print()
        input("  Press ENTER after unplugging USB (or ENTER to continue with USB connected)... ")
        return device_ip
    else:
        print(f"  WARNING: WiFi ADB connection failed ({r3.stdout.strip()!r}). Staying on USB.")
        return None


def ensure_adb_connected(wifi_ip: str | None = None, max_retries: int = 3) -> bool:
    """Check ADB is responsive; reconnect via WiFi if IP is known. Returns True if connected."""
    for attempt in range(max_retries):
        try:
            result = adb(["devices"], timeout=10, check=False)
            if "\tdevice" in result.stdout:
                return True
        except Exception:
            pass
        if wifi_ip:
            print(f"  ADB disconnected — reconnecting to {wifi_ip}:5555 (attempt {attempt+1}/{max_retries})...")
            try:
                adb(["connect", f"{wifi_ip}:5555"], timeout=15, check=False)
            except Exception:
                pass
        time.sleep(3)
    return False


def get_battery_pct() -> float | None:
    """Read battery percentage from device."""
    r = adb_shell("dumpsys battery | grep level", timeout=10)
    m = re.search(r"level:\s*(\d+)", r.stdout)
    return float(m.group(1)) if m else None


def get_temperature_c() -> float | None:
    """Read device temperature from dumpsys battery (reports in tenths of Celsius)."""
    r = adb_shell("dumpsys battery | grep temperature", timeout=10)
    m = re.search(r"temperature:\s*(\d+)", r.stdout)
    return round(float(m.group(1)) / 10.0, 1) if m else None


def get_mem_available_kb() -> int | None:
    """Read MemAvailable from /proc/meminfo (KB). Fast, no root required."""
    r = adb_shell("grep MemAvailable /proc/meminfo", timeout=10)
    m = re.search(r"MemAvailable:\s+(\d+)\s+kB", r.stdout)
    return int(m.group(1)) if m else None


class PowerSampler:
    """Background thread that samples current_now + voltage_now every ~2 seconds.

    Works in two modes:
    - Device DISCHARGING (WiFi ADB, USB unplugged): current_now is negative; |current| × voltage = power.
    - Device CHARGING (USB connected): current_now is positive (net charging); delta between idle and
      inference states gives marginal inference power draw.

    The sampler records raw values; the caller decides how to interpret them.
    """

    SAMPLE_INTERVAL_S = 2.0
    SYSFS_CURRENT = "cat /sys/class/power_supply/battery/current_now"
    SYSFS_VOLTAGE = "cat /sys/class/power_supply/battery/voltage_now"

    def __init__(self) -> None:
        self._samples: list[dict] = []
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._samples.clear()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="PowerSampler")
        self._thread.start()

    def stop(self) -> dict:
        """Stop sampling. Returns stats dict with power_mw_mean, energy_mj, n_samples."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=10)
        return self._compute_stats()

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            current_ua = self._read_int(self.SYSFS_CURRENT)
            voltage_uv = self._read_int(self.SYSFS_VOLTAGE)
            ts = time.monotonic()
            if current_ua is not None and voltage_uv is not None and voltage_uv > 0:
                self._samples.append({"ts": ts, "current_ua": current_ua, "voltage_uv": voltage_uv})
            self._stop_event.wait(timeout=self.SAMPLE_INTERVAL_S)

    def _read_int(self, cmd: str) -> int | None:
        try:
            r = adb_shell(cmd, timeout=5)
            s = r.stdout.strip()
            return int(s) if s.lstrip("-").isdigit() else None
        except Exception:
            return None

    def _compute_stats(self) -> dict:
        if not self._samples:
            return {"power_mw_mean": None, "energy_mj": None, "n_samples": 0, "sysfs_accessible": False}

        # Power (mW) = |current_ua| × voltage_uv / 1e9
        power_mw_list = [abs(s["current_ua"]) * s["voltage_uv"] / 1e9 for s in self._samples]
        power_mw_mean = sum(power_mw_list) / len(power_mw_list)

        duration_s = 0.0
        if len(self._samples) >= 2:
            duration_s = self._samples[-1]["ts"] - self._samples[0]["ts"]

        energy_mj = round(power_mw_mean * duration_s, 2) if duration_s > 0 else None

        return {
            "power_mw_mean": round(power_mw_mean, 2),
            "energy_mj": energy_mj,
            "n_samples": len(self._samples),
            "sysfs_accessible": True,
        }


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
            # Support both 'text' and 'prompt' field names
            text = p.get("text") or p.get("prompt", "")
            prompts[p["id"]] = text.strip()
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
                # Support both 'text:' and 'prompt:' field names
                m = re.match(r'\s*(?:text|prompt):\s*["\'](.+?)["\']?\s*$', line)
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
    threads: int = 4,
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

    # Build llama-completion command
    # -no-cnv: disable conversation mode (llama.cpp b1+), run single-shot
    llama_cmd = (
        f"LD_LIBRARY_PATH={DEVICE_WORK_DIR} "
        f"{LLAMA_CLI_DEVICE} "
        f"-m {model_path} "
        f"-c {context_length} "
        f"-n {output_length} "
        f"--temp 0.0 "          # deterministic
        f"--seed 42 "
        f"-t {threads} "        # configurable thread count (default 4)
        f"-no-cnv "             # disable chat/conversation mode, single-shot only
        f"-p \"{prompt}\""
    )

    # --- Pre-inference measurements ---
    mem_before_kb = get_mem_available_kb()
    temp_before = get_temperature_c()
    battery_start = get_battery_pct()

    # Start background power sampler
    sampler = PowerSampler()
    sampler.start()

    t_request_start = time.monotonic()

    try:
        result = adb_shell(llama_cmd, timeout=600)
    except RuntimeError as e:
        power_stats = sampler.stop()
        return _failure_record(
            run_id, device_info, llama_version, gguf_variant, quant_bits,
            prompt_id, context_length, output_length, trial_index, is_warmup,
            artifact_hash, "TIMEOUT", "inference", str(e), retryable=True,
        )

    t_end = time.monotonic()  # noqa: F841  (wall time available if needed)

    # --- Post-inference measurements ---
    power_stats = sampler.stop()
    mem_after_kb = get_mem_available_kb()
    temp_after = get_temperature_c()
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

    # --- Compute derived metrics ---

    # Peak RSS: MemAvailable delta (mem consumed by inference ≈ mem_before - mem_after)
    # OS background noise is ±20-50 MB; negative delta (OS freed memory) → treat as None
    peak_rss_mb = None
    if mem_before_kb is not None and mem_after_kb is not None:
        delta_kb = mem_before_kb - mem_after_kb
        if delta_kb > 0:
            peak_rss_mb = round(delta_kb / 1024.0, 1)

    # Temperature: average of before/after readings
    temperature_c: float | None = None
    if temp_before is not None and temp_after is not None:
        temperature_c = round((temp_before + temp_after) / 2.0, 1)
    elif temp_after is not None:
        temperature_c = temp_after
    elif temp_before is not None:
        temperature_c = temp_before

    # Battery delta
    battery_drop: float | None = None
    battery_drop_per_1k: float | None = None
    if battery_start is not None and battery_end is not None:
        battery_drop = max(0.0, battery_start - battery_end)

    total_tokens = (metrics.get("input_tokens") or 0) + (metrics.get("output_tokens") or 0)

    if battery_drop is not None and total_tokens > 0:
        battery_drop_per_1k = 1000.0 * battery_drop / total_tokens

    # Energy per 1K tokens from power sampler
    energy_per_1k_tokens_mj: float | None = None
    if power_stats.get("energy_mj") is not None and total_tokens > 0:
        energy_per_1k_tokens_mj = round(1000.0 * power_stats["energy_mj"] / total_tokens, 4)

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
            "peak_rss_mb": peak_rss_mb,
            "battery_start_pct": battery_start,
            "battery_end_pct": battery_end,
            "battery_drop_pct": round(battery_drop, 4) if battery_drop is not None else None,
            "battery_drop_per_1k_tokens": round(battery_drop_per_1k, 6) if battery_drop_per_1k is not None else None,
            "temperature_c": temperature_c,
            "power_mw_mean": power_stats.get("power_mw_mean"),
            "energy_mj": power_stats.get("energy_mj"),
            "energy_per_1k_tokens_mj": energy_per_1k_tokens_mj,
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
            "power_mw_mean": None, "energy_mj": None, "energy_per_1k_tokens_mj": None,
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
    """Run all trials for one registry entry. Returns summary stats.

    Protocol: 2 warmup runs using the first prompt (to warm CPU caches),
    then for every prompt in the suite: trials recorded runs.
    Total recorded runs = len(prompts) × trials.
    """
    gguf_variant = entry["gguf_variant"]
    quant_bits = entry["quant_bits"]
    context_length = entry["context_length"]
    output_length = entry["output_length"]
    warmups = entry.get("warmups", 2)
    trials = entry.get("trials", 5)
    threads = entry.get("threads", 4)  # thread count (default 4; configurable for sweep)
    exp_id = entry["id"]

    prompt_list = list(prompts.items())  # [(id, text), ...]
    n_prompts = len(prompt_list)
    total_recorded = n_prompts * trials

    print(f"\n{'='*60}")
    print(f"Experiment: {exp_id}")
    print(f"  Quant: {gguf_variant} ({quant_bits}-bit)")
    print(f"  Context: {context_length} | Output: {output_length} tokens")
    print(f"  Warmups: {warmups} | Prompts: {n_prompts} | Trials/prompt: {trials} "
          f"→ {total_recorded} recorded runs")
    print(f"{'='*60}")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    records = []

    # --- Warmup runs (using first prompt) ---
    warmup_prompt_id, warmup_text = prompt_list[0]
    for i in range(warmups):
        label = f"warmup {i+1}/{warmups} [{warmup_prompt_id}]"
        print(f"  [{label}] running...", end=" ", flush=True)

        record = run_trial(
            prompt=warmup_text,
            gguf_variant=gguf_variant,
            context_length=context_length,
            output_length=output_length,
            device_info=device_info,
            llama_version=llama_version,
            artifact_hash=artifact_hash,
            prompt_id=warmup_prompt_id,
            quant_bits=quant_bits,
            trial_index=i,
            is_warmup=True,
            threads=threads,
        )

        status = record["status"]
        if status == "success":
            tps = record["metrics"].get("decode_tps")
            ttft = record["metrics"].get("ttft_s")
            print(f"OK  decode={tps:.1f} tok/s  TTFT={ttft:.2f}s" if tps and ttft else "OK")
        else:
            code = record["failure"]["code"] if record.get("failure") else "?"
            print(f"FAIL [{code}]")
            if code == "OOM":
                # If we OOM during warmup, abort this experiment — no point continuing
                print(f"  OOM during warmup — aborting experiment {exp_id}")
                with open(output_file, "a") as f:
                    f.write(json.dumps(record) + "\n")
                return {"exp_id": exp_id, "success": 0, "failed": total_recorded, "oom": True}

        with open(output_file, "a") as f:
            f.write(json.dumps(record) + "\n")
        records.append(record)

    # --- Recorded runs (all prompts × trials) ---
    success_count = 0
    fail_count = 0
    for prompt_id, prompt_text in prompt_list:
        for t in range(trials):
            label = f"trial {t+1}/{trials} [{prompt_id}]"
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
                trial_index=t,
                is_warmup=False,
                threads=threads,
            )

            status = record["status"]
            if status == "success":
                tps = record["metrics"].get("decode_tps")
                ttft = record["metrics"].get("ttft_s")
                print(f"OK  decode={tps:.1f} tok/s  TTFT={ttft:.2f}s" if tps and ttft else "OK")
                success_count += 1
            else:
                code = record["failure"]["code"] if record.get("failure") else "?"
                print(f"FAIL [{code}]")
                fail_count += 1
                if code == "OOM":
                    # OOM is non-retryable — abort remaining trials for this experiment
                    print(f"  OOM during inference — aborting remaining trials for {exp_id}")
                    with open(output_file, "a") as f:
                        f.write(json.dumps(record) + "\n")
                    records.append(record)
                    return {"exp_id": exp_id, "success": success_count, "failed": fail_count + (total_recorded - success_count - fail_count), "oom": True}

            with open(output_file, "a") as f:
                f.write(json.dumps(record) + "\n")
            records.append(record)

    # Summary for this experiment
    print(f"\n  Summary: {success_count}/{total_recorded} recorded runs OK, {fail_count} failed")
    success_records = [r for r in records if r["status"] == "success" and not r["trial"]["is_warmup"]]
    if success_records:
        tps_values = [r["metrics"]["decode_tps"] for r in success_records if r["metrics"].get("decode_tps")]
        if tps_values:
            print(f"  Decode TPS: mean={sum(tps_values)/len(tps_values):.1f}  "
                  f"min={min(tps_values):.1f}  max={max(tps_values):.1f}")

    return {"exp_id": exp_id, "success": success_count, "failed": fail_count}


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
    parser.add_argument(
        "--wifi-adb", action="store_true",
        help="Switch to WiFi ADB before sweep (unplug USB for accurate battery/power measurements)"
    )

    args = parser.parse_args()

    # Check device
    print("Checking device connection...")
    try:
        device_info = check_device()
        print(f"  Device: {device_info['manufacturer']} {device_info['model']} (Android {device_info['android_version']})")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        sys.exit(1)

    # WiFi ADB setup (optional — for battery discharge measurement)
    global _WIFI_IP
    if args.wifi_adb:
        _WIFI_IP = setup_wifi_adb()
    else:
        print("  Note: Running with USB ADB. Battery drop will likely be 0% (device is charging).")
        print("  Use --wifi-adb to switch to WiFi ADB and get real battery measurements.")

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
        print("  Computing model hash (may take ~30s for 2GB file)...", end=" ", flush=True)
        artifact_hash = compute_model_hash("Q4_K_M")
        print("done" if artifact_hash else "not found (local model missing)")
        summary = run_experiment(entry, prompts, device_info, llama_version, out_file, artifact_hash=artifact_hash)
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

    # Pre-compute model hashes (once per variant, not per trial)
    _hash_cache: dict[str, str | None] = {}

    all_summaries = []
    for i, entry in enumerate(entries):
        if i > 0:
            print(f"\n[2-minute cooldown between experiments...]")
            time.sleep(120)

        # Re-verify ADB connection before each experiment (WiFi ADB may have dropped)
        if not ensure_adb_connected(wifi_ip=_WIFI_IP):
            print(f"  ERROR: ADB connection lost and could not be restored. Aborting sweep.")
            break

        variant = entry.get("gguf_variant", "")
        if variant not in _hash_cache:
            _hash_cache[variant] = compute_model_hash(variant)

        summary = run_experiment(
            entry, prompts, device_info, llama_version, out_file,
            artifact_hash=_hash_cache.get(variant)
        )
        all_summaries.append(summary)

    # Final summary
    total_ok = sum(s["success"] for s in all_summaries)
    total_fail = sum(s["failed"] for s in all_summaries)
    oom_exps = [s["exp_id"] for s in all_summaries if s.get("oom")]
    print(f"\n{'='*60}")
    print(f"RUN COMPLETE: {len(entries)} experiments | {total_ok} runs OK | {total_fail} failed")
    if oom_exps:
        print(f"  OOM experiments (expected on 6GB device): {', '.join(oom_exps)}")
    print(f"Results: {out_file}")
    print(f"\nValidate: python scripts/validate_results.py {out_file}")
    print(f"Figures:  python analysis/generate_figures.py {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
