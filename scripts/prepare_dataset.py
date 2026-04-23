#!/usr/bin/env python3
"""
prepare_dataset.py
------------------
Reads all result files from /results/, normalises across the three schema
formats used in the project, filters to clean records, and writes one
Parquet file per split to /dataset/ ready for HuggingFace upload.

Output splits
─────────────
  dataset/pixel_inference.parquet      — Pixel 6a inference runs
  dataset/m4_inference.parquet         — M4 Mac Metal inference runs
  dataset/x86_inference.parquet        — x86 / Intel inference runs
  dataset/quality_benchmarks.parquet   — accuracy scores (6 benchmarks)
  dataset/perplexity.parquet           — WikiText-2 PPL scores

Usage
─────
  pip install pandas pyarrow
  python3 scripts/prepare_dataset.py

  Optional flags:
    --results-dir  PATH   (default: project_root/results)
    --dataset-dir  PATH   (default: project_root/dataset)
    --verbose             print per-file record counts
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────

PROJECT_ROOT   = Path(__file__).resolve().parent.parent
DEFAULT_RESULTS = PROJECT_ROOT / "results"
DEFAULT_DATASET = PROJECT_ROOT / "dataset"

MODEL_LLAMA = "Llama-3.2-3B-Instruct"
MODEL_QWEN  = "Qwen2.5-1.5B-Instruct"

# Canonical column order for all inference splits
INFERENCE_COLS = [
    "device",           # Pixel6a | M4Mac | x86
    "backend",          # CPU | Metal
    "model",            # Llama-3.2-3B-Instruct | Qwen2.5-1.5B-Instruct
    "variant",          # Q2_K … Q8_0
    "context_len",      # 256 | 512 | 1024 | 2048 | …
    "trial",            # trial index (1-based)
    "threads",          # thread count (null if not varied)
    "decode_tps",       # tokens / second during generation
    "decode_tps_std",   # stddev for pre-aggregated rows (null for individual trials)
    "prefill_tps",      # tokens / second during prompt processing
    "prefill_tps_std",  # stddev for pre-aggregated rows (null for individual trials)
    "ttft_s",           # time to first token (seconds)
    "e2e_s",            # end-to-end latency (seconds)
    "n_output_tokens",  # number of generated tokens
    "n_trials",         # number of trials represented by this row
    "experiment_type",  # cliff_sweep | standard_sweep | thread_sweep | kv_cache_quant | tps_sweep
    "kv_quant",         # KV cache quantization setting, null = default
    "ngl",              # GPU layers offloaded (M4 Metal only)
    "ts",               # ISO-8601 timestamp of the run
    "source_file",      # originating filename for traceability
]

# ── I/O helpers ───────────────────────────────────────────────────────────────

def load_jsonl(path: Path, verbose: bool = False) -> list[dict]:
    """Read a .jsonl file, skipping malformed lines silently."""
    records, skipped = [], 0
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    if verbose and skipped:
        print(f"    [warn] {path.name}: skipped {skipped} malformed lines")
    return records


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def infer_model(path: Path) -> str:
    return MODEL_QWEN if "qwen" in str(path).lower() else MODEL_LLAMA

# ── Record parsers ─────────────────────────────────────────────────────────────

def parse_flat(rec: dict, source_file: str, experiment_type: str,
               device: str, model: str) -> Optional[dict]:
    """
    Flat format used by: canonical cliff, thread sweep, kv_cache_quant,
    M4 cliff, Qwen cliff.
    Fields: variant, context, trial, decode_tps, prefill_tps, device,
            backend, ts, [threads], [kv_quant], [ngl], [n_output_tokens]
    """
    # Skip probe / metadata records
    if "probe" in rec or "fa_supported" in rec:
        return None
    decode = rec.get("decode_tps")
    if not decode or decode <= 0:
        return None
    variant = rec.get("variant")
    if not variant:
        return None

    return {
        "device":          device or rec.get("device", "Pixel6a"),
        "backend":         rec.get("backend", "CPU"),
        "model":           model,
        "variant":         variant,
        "context_len":     rec.get("context"),
        "trial":           rec.get("trial"),
        "threads":         rec.get("threads"),
        "decode_tps":      decode,
        "decode_tps_std":  rec.get("decode_std"),
        "prefill_tps":     rec.get("prefill_tps"),
        "prefill_tps_std": rec.get("prefill_std"),
        "ttft_s":          None,
        "e2e_s":           None,
        "n_output_tokens": rec.get("n_output_tokens"),
        "n_trials":        rec.get("n_trials", 1),
        "experiment_type": experiment_type,
        "kv_quant":        rec.get("kv_quant"),
        "ngl":             rec.get("ngl"),
        "ts":              rec.get("ts"),
        "source_file":     source_file,
    }


def parse_tps_aggregate(rec: dict, source_file: str, experiment_type: str,
                        device: str, model: str) -> Optional[dict]:
    """Parse pre-aggregated llama-bench TPS rows produced by M4/x86 TPS scripts."""
    if rec.get("test_type") != "tg":
        return None
    decode = rec.get("tps_mean")
    if not decode or decode <= 0:
        return None
    variant = rec.get("variant")
    if not variant:
        return None
    return {
        "device":          device or rec.get("device"),
        "backend":         rec.get("backend", "CPU"),
        "model":           model,
        "variant":         variant,
        # Pure decode rows use n_prompt=0; keep context_len=0 to make the contract explicit.
        "context_len":     rec.get("context", 0),
        "trial":           None,
        "threads":         rec.get("threads"),
        "decode_tps":      decode,
        "decode_tps_std":  rec.get("tps_std"),
        "prefill_tps":     None,
        "prefill_tps_std": None,
        "ttft_s":          None,
        "e2e_s":           None,
        "n_output_tokens": rec.get("n_gen"),
        "n_trials":        rec.get("n_trials", 1),
        "experiment_type": experiment_type,
        "kv_quant":        None,
        "ngl":             rec.get("ngl"),
        "ts":              rec.get("ts"),
        "source_file":     source_file,
    }


def parse_nested_v1(rec: dict, source_file: str) -> Optional[dict]:
    """
    Nested schema v1.0 used by the early run-* files (standard sweep).
    Fields: record_version, run_id, status, device{}, build{}, model{},
            trial{}, timing_s{}, tokens{}, metrics{}, resources{}
    """
    if rec.get("status") != "success":
        return None
    if rec.get("trial", {}).get("is_warmup", False):
        return None
    metrics = rec.get("metrics", {})
    decode  = metrics.get("decode_tps")
    if not decode or decode <= 0:
        return None
    variant = rec.get("build", {}).get("gguf_variant")
    if not variant:
        return None

    return {
        "device":          "Pixel6a",
        "backend":         "CPU",
        "model":           rec.get("model", {}).get("name", MODEL_LLAMA),
        "variant":         variant,
        "context_len":     rec.get("trial", {}).get("context_length"),
        "trial":           rec.get("trial", {}).get("trial_index"),
        "threads":         None,
        "decode_tps":      decode,
        "decode_tps_std":  None,
        "prefill_tps":     metrics.get("prefill_tps"),
        "prefill_tps_std": None,
        "ttft_s":          metrics.get("ttft_s"),
        "e2e_s":           metrics.get("e2e_s"),
        "n_output_tokens": rec.get("tokens", {}).get("output_tokens"),
        "n_trials":        1,
        "experiment_type": "standard_sweep",
        "kv_quant":        None,
        "ngl":             None,
        "ts":              None,
        "source_file":     source_file,
    }

# ── Per-device collectors ──────────────────────────────────────────────────────

def collect_pixel(results: Path, verbose: bool) -> list[dict]:
    rows = []

    def add_flat(directory: Path, etype: str, model: str = MODEL_LLAMA):
        if not directory.exists():
            return
        for f in sorted(directory.glob("*.jsonl")):
            m = infer_model(f) if model is None else model
            for rec in load_jsonl(f, verbose):
                r = parse_flat(rec, f.name, etype, device="Pixel6a", model=m)
                if r:
                    rows.append(r)
            if verbose:
                print(f"    {f.name}: +{len(rows)} total so far")

    def add_variant_files(directory: Path, etype: str, variants: list[str], model: str = MODEL_LLAMA):
        if not directory.exists():
            return
        for variant in variants:
            file_path = directory / f"cliff_filled_{variant}.jsonl"
            if not file_path.exists():
                if verbose:
                    print(f"    [warn] missing {file_path.name} in {directory.name}")
                continue
            for rec in load_jsonl(file_path, verbose):
                r = parse_flat(rec, file_path.name, etype, device="Pixel6a", model=model)
                if r:
                    rows.append(r)
            if verbose:
                print(f"    {file_path.name}: +{len(rows)} total so far")

    # 1. Canonical cliff (primary Pixel dataset — per-variant clean sources only)
    # Q2_K, Q3_K_M, Q4_K_S, Q8_0 come from the clean n=10 batch.
    # Q4_K_M, Q5_K_M, and Q6_K require dedicated reruns because the batch baselines are
    # thermally distorted or otherwise superseded. See results/CANONICAL.md.
    add_variant_files(
        results / "pixel_llama_cliff_filled_20260329_162354",
        "cliff_sweep",
        ["Q2_K", "Q3_K_M", "Q4_K_S", "Q8_0"],
    )
    add_variant_files(
        results / "pixel_llama_cliff_filled_20260326_132101",
        "cliff_sweep",
        ["Q4_K_M"],
    )
    add_variant_files(
        results / "pixel_llama_cliff_filled_20260410_142752",
        "cliff_sweep",
        ["Q5_K_M"],
    )
    add_variant_files(
        results / "pixel_llama_cliff_filled_20260330_212946",
        "cliff_sweep",
        ["Q6_K"],
    )

    # 2. Thread sweep (Q4_K_M, threads 1/2/4/8, ctx=256)
    add_flat(results / "pixel_threads_q4km_20260406_100148", "thread_sweep")

    # 3. KV cache quantization mitigation
    add_flat(results / "pixel_kvcache_quant_20260331_062405", "kv_cache_quant")

    # 4. Standard sweep — canonical Pixel TPS batch
    # Earlier run-*.jsonl files are kept in /results for audit, but the public dataset
    # uses the canonical tps directory cited in README.md and results/CANONICAL.md.
    add_flat(results / "pixel_llama_tps_20260325_120022", "standard_sweep")

    # 5. Qwen cross-model validation (Pixel)
    # IMPORTANT: Use ONLY the clean run (235410).
    # Run 004954 is contaminated (concurrent llama-perplexity process during collection;
    # baselines 4–6 tok/s vs 8–16 tok/s in the clean run). See results/CANONICAL.md.
    add_flat(results / "pixel_qwen_cliff_filled_20260330_235410", "cliff_sweep", model=MODEL_QWEN)
    # TPS sweep (4 standard contexts × 5 trials) — standard_sweep, NOT cliff_sweep
    add_flat(results / "pixel_qwen_tps_20260326_033619", "standard_sweep", model=MODEL_QWEN)

    return rows


def collect_m4(results: Path, verbose: bool) -> list[dict]:
    rows = []

    def add_flat(directory: Path, etype: str, model: str = MODEL_LLAMA):
        if not directory.exists():
            return
        for f in sorted(Path(directory).glob("*.jsonl")):
            # Skip corrupted CPU files (m4_mac_cpu format is broken)
            if "cpu" in f.stem.lower() and "mac" in str(directory).lower():
                if verbose:
                    print(f"    [skip] {f.name}: M4 CPU format corrupted")
                continue
            m = infer_model(f) if model is None else model
            for rec in load_jsonl(f, verbose):
                r = parse_flat(rec, f.name, etype, device="M4Mac", model=m)
                if r:
                    rows.append(r)

    def add_tps_aggregate(directory: Path, etype: str, model: str):
        if not directory.exists():
            if verbose:
                print(f"    [warn] missing {directory.name}")
            return
        for f in sorted(Path(directory).glob("tps_*.jsonl")):
            for rec in load_jsonl(f, verbose):
                r = parse_tps_aggregate(rec, f.name, etype, device="M4Mac", model=model)
                if r:
                    rows.append(r)

    # M4 Metal cliff sweeps — Llama
    for pattern in ("m4_metal_cliff_*", "m4_llama_cliff_*"):
        for d in sorted(results.glob(pattern)):
            add_flat(d, "cliff_sweep")

    # M4 CPU cliff sweeps — Llama (ngl=0, backend=CPU; bake script filters by backend+ngl)
    for d in sorted(results.glob("m4_cpu_cliff_*")):
        add_flat(d, "cliff_sweep")

    # M4 TPS sweeps — Llama (use tps_aggregate parser for llama-bench tps_*.jsonl format)
    for d in sorted(results.glob("m4_llama_tps_*")):
        add_tps_aggregate(d, "standard_sweep", MODEL_LLAMA)

    # M4 CPU TPS — Llama, clean idle rerun (ngl=0, n=10, tg128).
    # Older M4 CPU TPS attempts remain in /results for audit but are not public evidence.
    add_tps_aggregate(results / "m4_cpu_tps_20260415_231524", "standard_sweep", MODEL_LLAMA)

    # M4 Qwen extension — promoted after clean reruns on 2026-04-15/16.
    add_tps_aggregate(results / "m4_qwen_tps_20260415_130955", "standard_sweep", MODEL_QWEN)
    add_flat(results / "m4_qwen_cliff_20260416_021323", "cliff_sweep", model=MODEL_QWEN)

    return rows


def collect_x86(results: Path) -> list[dict]:
    rows = []

    # 1. Single-context TPS reference run (n=1 per variant, ctx unrecorded)
    tps_path = results / "x86_tps_results.json"
    if tps_path.exists():
        data = load_json(tps_path)
        meta = data.get("meta", {})
        for variant, result in data.get("results", {}).items():
            if result.get("status") != "ok":
                continue
            decode = result.get("decode_tps")
            if not decode or decode <= 0:
                continue
            rows.append({
                "device":          "x86",
                "backend":         "CPU",
                "model":           MODEL_LLAMA,
                "variant":         variant,
                "context_len":     256,
                "trial":           1,
                "threads":         meta.get("threads"),
                "decode_tps":      decode,
                "decode_tps_std":  None,
                "prefill_tps":     result.get("prefill_tps"),
                "prefill_tps_std": None,
                "ttft_s":          None,
                "e2e_s":           None,
                "n_output_tokens": None,
                "n_trials":        1,
                "experiment_type": "standard_sweep",
                "kv_quant":        None,
                "ngl":             None,
                "ts":              meta.get("timestamp"),
                "source_file":     "x86_tps_results.json",
            })
    else:
        print("  [warn] x86_tps_results.json not found — skipping single-run x86 data")

    # 2. GAP-5 cliff sweep (n=5 per variant × 11 context sizes, filled-context methodology)
    cliff_dir = results / "x86_llama_cliff_20260408_070924"
    if cliff_dir.exists():
        for f in sorted(cliff_dir.glob("cliff_filled_*.jsonl")):
            for rec in load_jsonl(f):
                decode = rec.get("decode_tps")
                if not decode or decode <= 0:
                    continue
                variant = rec.get("variant")
                if not variant:
                    continue
                rows.append({
                    "device":          "x86",
                    "backend":         "CPU",
                    "model":           MODEL_LLAMA,
                    "variant":         variant,
                    "context_len":     rec.get("context"),
                    "trial":           rec.get("trial"),
                    "threads":         rec.get("threads"),
                    "decode_tps":      decode,
                    "decode_tps_std":  rec.get("decode_std"),
                    "prefill_tps":     rec.get("prefill_tps"),
                    "prefill_tps_std": rec.get("prefill_std"),
                    "ttft_s":          None,
                    "e2e_s":           None,
                    "n_output_tokens": rec.get("n_output_tokens"),
                    "n_trials":        rec.get("n_trials", 1),
                    "experiment_type": "cliff_sweep",
                    "kv_quant":        None,
                    "ngl":             None,
                    "ts":              rec.get("ts"),
                    "source_file":     f.name,
                })
    else:
        print("  [warn] x86_llama_cliff_20260408_070924/ not found — GAP-5 cliff data missing")

    # 3. x86 Qwen TPS sweep — output by x86_qwen_tps.sh
    # Format: tps_{VARIANT}.jsonl with fields: variant, test_type, tps_mean, n_prompt, threads, ts
    for qwen_dir in sorted(results.glob("x86_qwen_tps_*")):
        for f in sorted(qwen_dir.glob("tps_*.jsonl")):
            for rec in load_jsonl(f):
                if rec.get("test_type") != "tg":  # only decode (tg) rows
                    continue
                decode = rec.get("tps_mean")
                if not decode or decode <= 0:
                    continue
                variant = rec.get("variant")
                if not variant:
                    continue
                # pp rows tell us the context size (n_prompt * 2 = ctx); tg uses n_prompt=0
                # Extract context from filename hint: script uses pp=128,256,512,1024 → ctx=256
                rows.append({
                    "device":          "x86",
                    "backend":         "CPU",
                    "model":           MODEL_QWEN,
                    "variant":         variant,
                    "context_len":     256,
                    "trial":           1,
                    "threads":         rec.get("threads"),
                    "decode_tps":      decode,
                    "decode_tps_std":  rec.get("tps_std"),
                    "prefill_tps":     None,
                    "prefill_tps_std": None,
                    "ttft_s":          None,
                    "e2e_s":           None,
                    "n_output_tokens": None,
                    "n_trials":        rec.get("n_trials", 1),
                    "experiment_type": "standard_sweep",
                    "kv_quant":        None,
                    "ngl":             rec.get("ngl", 0),
                    "ts":              rec.get("ts"),
                    "source_file":     f.name,
                })

    return rows


def collect_quality(results: Path) -> list[dict]:
    rows = []
    path = results / "quality_scores.json"
    if not path.exists():
        print("  [warn] quality_scores.json not found")
    else:
        data = load_json(path)
        for key, entry in data.items():
            if not isinstance(entry, dict):
                continue
            acc = entry.get("accuracy_pct")
            if acc is None:
                continue
            # Skip any stale zero entries that slipped through
            if acc == 0.0 and entry.get("total", 0) > 0:
                print(f"  [skip] quality entry '{key}': accuracy=0% with n={entry['total']} — likely evaluation failure")
                continue

            # Parse composite key  "benchmark:variant"  or bare  "variant"
            if ":" in key:
                benchmark, variant = key.split(":", 1)
            else:
                # Bare keys are exploratory ad-hoc QA and are not part of the public dataset.
                continue

            # Device: x86_ prefix in benchmark key → x86, otherwise Pixel6a
            device = "x86" if benchmark.startswith("x86_") else "Pixel6a"
            # Strip x86_ prefix from benchmark name for clean public schema
            if benchmark.startswith("x86_"):
                benchmark = benchmark[len("x86_"):]

            # imatrix entries have "imatrix" in the benchmark prefix or suffix
            calibration = "imatrix" if "imatrix" in benchmark.lower() else "standard"
            # Normalise imatrix benchmark name — strip all imatrix decorators
            if calibration == "imatrix":
                benchmark = (benchmark
                             .replace("imatrix_", "")      # imatrix_boolq_all7_imatrix → boolq_all7_imatrix
                             .replace("_all7_imatrix", "")  # boolq_all7_imatrix → boolq
                             .replace("_imatrix", ""))      # boolq_imatrix → boolq, truthfulqa_imatrix → truthfulqa

            # Public schema uses the cleaned benchmark name.
            if benchmark == "arc_easy_fixed":
                benchmark = "arc_easy"

            rows.append({
                "benchmark":   benchmark,
                "variant":     variant,
                "device":      device,
                "model":       MODEL_LLAMA,
                "calibration": calibration,
                "accuracy_pct": acc,
                "correct":     entry.get("correct"),
                "total":       entry.get("total"),
                "status":      entry.get("status", "success"),
            })

    m4_path = results / "quality_metrics_m4_server.json"
    if not m4_path.exists():
        print("  [warn] quality_metrics_m4_server.json not found — M4 quality rows missing")
    else:
        m4_data = load_json(m4_path)
        expected = 7 * 6
        if len(m4_data) != expected:
            print(f"  [warn] M4 quality has {len(m4_data)} entries, expected {expected}")

        for key, entry in m4_data.items():
            if not isinstance(entry, dict):
                continue
            acc = entry.get("accuracy_pct")
            if acc is None:
                continue
            if ":" in key:
                benchmark, variant = key.split(":", 1)
            else:
                benchmark = entry.get("tag")
                variant = entry.get("variant")
            if not benchmark or not variant:
                print(f"  [skip] M4 quality entry '{key}': missing benchmark or variant")
                continue
            if benchmark == "arc_easy_fixed":
                benchmark = "arc_easy"

            status = entry.get("status", "success")
            total = entry.get("total")
            expected_total = entry.get("expected_total", total)
            if status != "success" or total != expected_total:
                print(f"  [skip] M4 quality entry '{key}': status={status}, total={total}, expected={expected_total}")
                continue

            rows.append({
                "benchmark":   benchmark,
                "variant":     variant,
                "device":      "M4Mac",
                "model":       MODEL_LLAMA,
                "calibration": "standard",
                "accuracy_pct": acc,
                "correct":     entry.get("correct"),
                "total":       total,
                "status":      status,
            })

    # Deduplicate: keep the last (most recent) entry per (device, benchmark, variant, calibration).
    # Device must be in the key so that Pixel6a arc_easy and x86 arc_easy are not collapsed.
    # When the same benchmark+variant was re-run, the newer key appears later in the JSON,
    # so last-write-wins preserves the most up-to-date measurement.
    seen: dict = {}
    for row in rows:
        key = (row["device"], row["benchmark"], row["variant"], row["calibration"])
        seen[key] = row
    return list(seen.values())


def collect_perplexity(results: Path) -> list[dict]:
    rows = []

    # ── Pixel 6a PPL (perplexity_scores.json) ──
    path = results / "perplexity_scores.json"
    if not path.exists():
        print("  [warn] perplexity_scores.json not found — Pixel PPL data missing")
    else:
        data = load_json(path)
        for variant, entry in data.items():
            if not isinstance(entry, dict):
                continue
            rows.append({
                "variant":           variant,
                "model":             MODEL_LLAMA,
                "device":            "Pixel6a",
                "perplexity":        entry.get("perplexity"),
                "perplexity_status": entry.get("perplexity_status", "success"),
                "corpus":            entry.get("corpus"),
                "tokens_approx":     entry.get("tokens_approx"),
                "note":              entry.get("note"),
            })

    # ── x86 PPL (x86_perplexity_results.json — full WikiText-2 corpus) ──
    x86_path = results / "x86_perplexity_results.json"
    if x86_path.exists():
        x86_data = load_json(x86_path)
        for variant, entry in x86_data.get("results", {}).items():
            if not isinstance(entry, dict) or entry.get("status") != "ok":
                continue
            rows.append({
                "variant":           variant,
                "model":             MODEL_LLAMA,
                "device":            "x86",
                "perplexity":        entry.get("perplexity"),
                "perplexity_status": "success",
                "corpus":            "wikitext2_full",
                "tokens_approx":     290817,
                "note":              "Measured on x86 i5-1235U (full WikiText-2 corpus, ~290K tokens)",
            })

    return rows

# ── Deduplication ─────────────────────────────────────────────────────────────

def dedup_inference(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove exact duplicates across (device, model, variant, context_len,
    trial, decode_tps).  Keeps the first occurrence (earliest source_file
    alphabetically after the sort in the collectors).
    """
    key = ["device", "model", "variant", "context_len", "trial", "decode_tps"]
    key = [c for c in key if c in df.columns]
    before = len(df)
    df = df.drop_duplicates(subset=key, keep="first")
    dropped = before - len(df)
    if dropped:
        print(f"    dedup: removed {dropped} exact duplicate rows")
    return df

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Prepare edge-llm-bench HuggingFace dataset")
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--dataset-dir", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    results: Path = args.results_dir
    dataset: Path = args.dataset_dir

    if not results.exists():
        sys.exit(f"[error] Results directory not found: {results}")

    dataset.mkdir(parents=True, exist_ok=True)
    print(f"Results : {results}")
    print(f"Dataset : {dataset}\n")

    # ── Pixel 6a ──────────────────────────────────────────────────────────────
    print("── Pixel 6a inference ──")
    pixel_rows = collect_pixel(results, args.verbose)
    df_pixel = pd.DataFrame(pixel_rows, columns=INFERENCE_COLS)
    df_pixel = df_pixel.dropna(subset=["decode_tps", "variant"])
    df_pixel = dedup_inference(df_pixel)
    out = dataset / "pixel_inference.parquet"
    df_pixel.to_parquet(out, index=False)
    print(f"  ✓ {len(df_pixel):,} rows → {out.name}\n")

    # ── M4 Mac ────────────────────────────────────────────────────────────────
    print("── M4 Mac Metal inference ──")
    m4_rows = collect_m4(results, args.verbose)
    df_m4 = pd.DataFrame(m4_rows, columns=INFERENCE_COLS)
    df_m4 = df_m4.dropna(subset=["decode_tps", "variant"])
    df_m4 = dedup_inference(df_m4)
    out = dataset / "m4_inference.parquet"
    df_m4.to_parquet(out, index=False)
    print(f"  ✓ {len(df_m4):,} rows → {out.name}\n")

    # ── x86 ───────────────────────────────────────────────────────────────────
    print("── x86 inference ──")
    x86_rows = collect_x86(results)
    df_x86 = pd.DataFrame(x86_rows, columns=INFERENCE_COLS)
    out = dataset / "x86_inference.parquet"
    df_x86.to_parquet(out, index=False)
    print(f"  ✓ {len(df_x86):,} rows → {out.name}\n")

    # ── Quality benchmarks ────────────────────────────────────────────────────
    print("── Quality benchmarks ──")
    quality_rows = collect_quality(results)
    df_quality = pd.DataFrame(quality_rows)
    out = dataset / "quality_benchmarks.parquet"
    df_quality.to_parquet(out, index=False)
    print(f"  ✓ {len(df_quality):,} rows → {out.name}\n")

    # ── Perplexity ────────────────────────────────────────────────────────────
    print("── Perplexity scores ──")
    ppl_rows = collect_perplexity(results)
    df_ppl = pd.DataFrame(ppl_rows)
    out = dataset / "perplexity.parquet"
    df_ppl.to_parquet(out, index=False)
    print(f"  ✓ {len(df_ppl):,} rows → {out.name}\n")

    # ── Summary ───────────────────────────────────────────────────────────────
    total = len(df_pixel) + len(df_m4) + len(df_x86) + len(df_quality) + len(df_ppl)
    print("═" * 50)
    print(f"  pixel_inference      {len(df_pixel):>6,} rows")
    print(f"  m4_inference         {len(df_m4):>6,} rows")
    print(f"  x86_inference        {len(df_x86):>6,} rows")
    print(f"  quality_benchmarks   {len(df_quality):>6,} rows")
    print(f"  perplexity           {len(df_ppl):>6,} rows")
    print(f"  {'TOTAL':20}   {total:>6,} rows")
    print("═" * 50)

    # ── Sanity checks ─────────────────────────────────────────────────────────
    print("\nSanity checks:")
    issues = 0

    # No 0% accuracy in quality
    if "accuracy_pct" in df_quality.columns:
        zero_acc = df_quality[df_quality["accuracy_pct"] == 0.0]
        if not zero_acc.empty:
            print(f"  [FAIL] quality_benchmarks: {len(zero_acc)} entries with 0% accuracy")
            print(df_quality[df_quality["accuracy_pct"] == 0.0][["benchmark", "variant", "accuracy_pct"]].to_string())
            issues += 1

    # No negative TPS
    for name, df in [("pixel", df_pixel), ("m4", df_m4), ("x86", df_x86)]:
        neg = df[df["decode_tps"] <= 0]
        if not neg.empty:
            print(f"  [FAIL] {name}_inference: {len(neg)} records with decode_tps <= 0")
            issues += 1

    # Pixel should have all 7 variants
    expected_variants = {"Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"}
    if "variant" in df_pixel.columns:
        missing = expected_variants - set(df_pixel["variant"].unique())
        if missing:
            print(f"  [WARN] pixel_inference: missing variants {missing}")
            issues += 1

    # All 7 variants should have at least one full-corpus PPL measurement (Pixel or x86)
    if "perplexity_status" in df_ppl.columns and "corpus" in df_ppl.columns:
        full_corpus = df_ppl[
            (df_ppl["perplexity_status"] == "success") &
            (df_ppl["corpus"] == "wikitext2_full")
        ]
        expected_variants = {"Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"}
        covered = set(full_corpus["variant"].unique())
        missing_ppl = expected_variants - covered
        if missing_ppl:
            print(f"  [WARN] perplexity: variants missing full-corpus PPL: {missing_ppl}")
            issues += 1
    # Quality split should contain both Pixel6a and x86 rows
    if "device" in df_quality.columns:
        devices_found = set(df_quality["device"].unique())
        if "x86" not in devices_found:
            print("  [WARN] quality_benchmarks: no x86 rows found — expected x86_* benchmarks")
            issues += 1
        if "Pixel6a" not in devices_found:
            print("  [WARN] quality_benchmarks: no Pixel6a rows found")
            issues += 1
    # Qwen Pixel rows should have correct experiment_type split
    if "model" in df_pixel.columns and "experiment_type" in df_pixel.columns:
        qwen = df_pixel[df_pixel["model"].str.contains("Qwen", na=False)]
        if not qwen.empty:
            qwen_etypes = set(qwen["experiment_type"].unique())
            if qwen_etypes == {"cliff_sweep"}:
                print("  [WARN] pixel_inference: Qwen rows all tagged cliff_sweep — TPS rows should be standard_sweep")
                issues += 1
    # M4 Qwen extension should be deliberately present after promotion.
    if "model" in df_m4.columns:
        m4_qwen_rows = df_m4[df_m4["model"].str.contains("Qwen", na=False)]
        qwen_counts = m4_qwen_rows["experiment_type"].value_counts().to_dict()
        expected_qwen_counts = {"cliff_sweep": 91, "standard_sweep": 7}
        if qwen_counts != expected_qwen_counts:
            print(f"  [WARN] m4_inference: M4 Qwen counts mismatch: {qwen_counts}, expected {expected_qwen_counts}")
            issues += 1

    if issues == 0:
        print("  All checks passed ✓")
    else:
        print(f"\n  {issues} issue(s) found — review before upload")


if __name__ == "__main__":
    main()
