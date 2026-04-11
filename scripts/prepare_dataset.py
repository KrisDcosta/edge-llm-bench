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
    "prefill_tps",      # tokens / second during prompt processing
    "ttft_s",           # time to first token (seconds)
    "e2e_s",            # end-to-end latency (seconds)
    "n_output_tokens",  # number of generated tokens
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
        "prefill_tps":     rec.get("prefill_tps"),
        "ttft_s":          None,
        "e2e_s":           None,
        "n_output_tokens": rec.get("n_output_tokens"),
        "experiment_type": experiment_type,
        "kv_quant":        rec.get("kv_quant"),
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
        "prefill_tps":     metrics.get("prefill_tps"),
        "ttft_s":          metrics.get("ttft_s"),
        "e2e_s":           metrics.get("e2e_s"),
        "n_output_tokens": rec.get("tokens", {}).get("output_tokens"),
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

    # 1. Canonical cliff (primary Pixel dataset — n=10, provenance-documented)
    add_flat(results / "pixel_llama_cliff_filled_canonical_n10", "cliff_sweep")

    # 2. Thread sweep (Q4_K_M, threads 1/2/4/8, ctx=256)
    add_flat(results / "pixel_threads_q4km_20260406_100148", "thread_sweep")

    # 3. KV cache quantization mitigation
    add_flat(results / "pixel_kvcache_quant_20260331_062405", "kv_cache_quant")

    # 4. Standard sweep — early run-* files (nested schema v1.0)
    for f in sorted(results.glob("run-*.jsonl")):
        before = len(rows)
        for rec in load_jsonl(f, verbose):
            r = parse_nested_v1(rec, f.name)
            if r:
                rows.append(r)
        if verbose:
            print(f"    {f.name}: +{len(rows)-before} records")

    # 5. Qwen cross-model validation (Pixel)
    for pattern in ("pixel_qwen_cliff_filled_*", "pixel_qwen_tps_*"):
        for d in sorted(results.glob(pattern)):
            add_flat(Path(d), "cliff_sweep", model=MODEL_QWEN)

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

    # M4 Metal cliff sweeps — Llama
    for pattern in ("m4_metal_cliff_*", "m4_llama_cliff_*"):
        for d in sorted(results.glob(pattern)):
            add_flat(d, "cliff_sweep")

    # M4 TPS sweeps — Llama
    for d in sorted(results.glob("m4_llama_tps_*")):
        add_flat(d, "tps_sweep")

    # M4 Qwen cross-model
    for pattern in ("m4_metal_qwen_cliff_*", "m4_qwen_cliff_*", "m4_qwen_tps_*"):
        for d in sorted(results.glob(pattern)):
            add_flat(d, "cliff_sweep", model=MODEL_QWEN)

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
                "prefill_tps":     result.get("prefill_tps"),
                "ttft_s":          None,
                "e2e_s":           None,
                "n_output_tokens": None,
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
                    "prefill_tps":     rec.get("prefill_tps"),
                    "ttft_s":          None,
                    "e2e_s":           None,
                    "n_output_tokens": rec.get("n_output_tokens"),
                    "experiment_type": "cliff_sweep",
                    "kv_quant":        None,
                    "ngl":             None,
                    "ts":              rec.get("ts"),
                    "source_file":     f.name,
                })
    else:
        print("  [warn] x86_llama_cliff_20260408_070924/ not found — GAP-5 cliff data missing")

    return rows


def collect_quality(results: Path) -> list[dict]:
    rows = []
    path = results / "quality_scores.json"
    if not path.exists():
        print("  [warn] quality_scores.json not found")
        return rows

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
            benchmark = "custom_qa"
            variant   = key

        # imatrix entries have "imatrix" in the benchmark prefix or suffix
        calibration = "imatrix" if "imatrix" in benchmark.lower() else "standard"
        # Normalise imatrix benchmark name — strip all imatrix decorators
        if calibration == "imatrix":
            benchmark = (benchmark
                         .replace("imatrix_", "")      # imatrix_boolq_all7_imatrix → boolq_all7_imatrix
                         .replace("_all7_imatrix", "")  # boolq_all7_imatrix → boolq
                         .replace("_imatrix", ""))      # boolq_imatrix → boolq, truthfulqa_imatrix → truthfulqa

        rows.append({
            "benchmark":   benchmark,
            "variant":     variant,
            "device":      "Pixel6a",
            "model":       MODEL_LLAMA,
            "calibration": calibration,
            "accuracy_pct": acc,
            "correct":     entry.get("correct"),
            "total":       entry.get("total"),
            "status":      entry.get("status", "success"),
        })

    # Deduplicate: keep the last (most recent) entry per (benchmark, variant, calibration).
    # When the same benchmark+variant was re-run, the newer key appears later in the JSON,
    # so last-write-wins preserves the most up-to-date measurement.
    seen: dict = {}
    for row in rows:
        key = (row["benchmark"], row["variant"], row["calibration"])
        seen[key] = row
    return list(seen.values())


def collect_perplexity(results: Path) -> list[dict]:
    rows = []
    path = results / "perplexity_scores.json"
    if not path.exists():
        print("  [warn] perplexity_scores.json not found")
        return rows

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

    # M4 perplexity not_evaluated entries exist
    if "perplexity_status" in df_ppl.columns:
        not_eval = df_ppl[df_ppl["perplexity_status"] == "not_evaluated"]
        if not_eval.empty:
            print("  [WARN] perplexity: expected not_evaluated entries for Q4_K_S / Q5_K_M")
            issues += 1

    if issues == 0:
        print("  All checks passed ✓")
    else:
        print(f"\n  {issues} issue(s) found — review before upload")


if __name__ == "__main__":
    main()
