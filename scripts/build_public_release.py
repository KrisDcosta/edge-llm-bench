#!/usr/bin/env python3
"""
build_public_release.py
-----------------------
Canonical public-release entrypoint for EdgeLLMBench.

This script:
1. Rebuilds the published parquet dataset from raw results
2. Re-bakes dashboard JSON from the parquet splits
3. Generates a machine-readable release manifest
4. Generates a public truth table for key headline metrics
5. Fails fast if public-facing artifacts drift from the verified build

Usage
-----
  python3 scripts/build_public_release.py

  Optional flags:
    --skip-prepare   Skip parquet rebuild
    --skip-bake      Skip dashboard JSON bake
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parent.parent
DATASET = PROJECT / "dataset"
DASHBOARD = PROJECT / "dashboard" / "data"
ARTIFACTS = PROJECT / "artifacts"

README = PROJECT / "README.md"
DATASET_README = DATASET / "README.md"
CONTRIBUTING = PROJECT / "CONTRIBUTING.md"
CANONICAL = PROJECT / "results" / "CANONICAL.md"
PLAIN_REPORT = PROJECT / "PROJECT_REPORT_PLAIN_ENGLISH.md"
DASHBOARD_INDEX = PROJECT / "dashboard" / "index.html"

MODEL_LLAMA = "Llama-3.2-3B-Instruct"
MODEL_QWEN = "Qwen2.5-1.5B-Instruct"
VARIANT_ORDER = ["Q2_K", "Q3_K_M", "Q4_K_S", "Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
CLIFF_RELIABLE_VARIANTS = {"Q2_K", "Q3_K_M", "Q4_K_S", "Q6_K", "Q8_0"}
EXPECTED_BENCHMARKS = {"arc_easy", "arc_challenge", "boolq", "hellaswag", "mmlu", "truthfulqa"}

EXPECTED_COLUMNS = {
    "pixel_inference.parquet": [
        "device", "backend", "model", "variant", "context_len", "trial", "threads",
        "decode_tps", "decode_tps_std", "prefill_tps", "prefill_tps_std",
        "ttft_s", "e2e_s", "n_output_tokens", "n_trials",
        "experiment_type", "kv_quant", "ngl", "ts", "source_file",
    ],
    "m4_inference.parquet": [
        "device", "backend", "model", "variant", "context_len", "trial", "threads",
        "decode_tps", "decode_tps_std", "prefill_tps", "prefill_tps_std",
        "ttft_s", "e2e_s", "n_output_tokens", "n_trials",
        "experiment_type", "kv_quant", "ngl", "ts", "source_file",
    ],
    "x86_inference.parquet": [
        "device", "backend", "model", "variant", "context_len", "trial", "threads",
        "decode_tps", "decode_tps_std", "prefill_tps", "prefill_tps_std",
        "ttft_s", "e2e_s", "n_output_tokens", "n_trials",
        "experiment_type", "kv_quant", "ngl", "ts", "source_file",
    ],
    "quality_benchmarks.parquet": [
        "benchmark", "variant", "device", "model", "calibration",
        "accuracy_pct", "correct", "total", "status",
    ],
    "perplexity.parquet": [
        "variant", "model", "device", "perplexity",
        "perplexity_status", "corpus", "tokens_approx", "note",
    ],
}


def run_step(cmd: list[str]) -> None:
    print(f"→ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=PROJECT, check=True)


def safe_float(value):
    if value is None or pd.isna(value):
        return None
    return round(float(value), 4)


def pct_drop(baseline: float, value: float) -> float | None:
    if not baseline or pd.isna(baseline) or pd.isna(value):
        return None
    return round(((value / baseline) - 1.0) * 100.0, 1)


def fmt_int(value: int) -> str:
    return f"{value:,}"


def fmt_float(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"


def load_frames():
    pixel = pd.read_parquet(DATASET / "pixel_inference.parquet")
    m4 = pd.read_parquet(DATASET / "m4_inference.parquet")
    x86 = pd.read_parquet(DATASET / "x86_inference.parquet")
    quality = pd.read_parquet(DATASET / "quality_benchmarks.parquet")
    ppl = pd.read_parquet(DATASET / "perplexity.parquet")
    return pixel, m4, x86, quality, ppl


def load_dashboard():
    return {
        "tps_by_variant": json.loads((DASHBOARD / "tps_by_variant.json").read_text()),
        "cliff_curves": json.loads((DASHBOARD / "cliff_curves.json").read_text()),
        "quality_scores": json.loads((DASHBOARD / "quality_scores.json").read_text()),
        "cross_device": json.loads((DASHBOARD / "cross_device.json").read_text()),
        "thread_sweep": json.loads((DASHBOARD / "thread_sweep.json").read_text()),
        "kv_quant": json.loads((DASHBOARD / "kv_quant.json").read_text()),
        "perplexity": json.loads((DASHBOARD / "perplexity.json").read_text()),
        "raw_table": json.loads((DASHBOARD / "raw_table.json").read_text()),
    }


def pixel_display_baseline(pixel_llama: pd.DataFrame, variant: str) -> float | None:
    rows = pixel_llama[
        (pixel_llama["experiment_type"] == "standard_sweep") &
        (pixel_llama["variant"] == variant) &
        (pixel_llama["context_len"] == 256)
    ]
    if rows.empty:
        return None
    return safe_float(rows["decode_tps"].mean())


def cliff_metric_table(pixel: pd.DataFrame, quality: pd.DataFrame) -> list[dict]:
    pixel_llama = pixel[pixel["model"] == MODEL_LLAMA]
    pixel_boolq = quality[
        (quality["benchmark"] == "boolq") &
        (quality["device"] == "Pixel6a") &
        (quality["calibration"] == "standard")
    ]
    rows = []
    for variant in VARIANT_ORDER:
        cliff_rows = pixel_llama[
            (pixel_llama["experiment_type"] == "cliff_sweep") &
            (pixel_llama["variant"] == variant)
        ]
        if cliff_rows.empty:
            continue
        ctx256 = safe_float(cliff_rows[cliff_rows["context_len"] == 256]["decode_tps"].mean())
        ctx2048 = safe_float(cliff_rows[cliff_rows["context_len"] == 2048]["decode_tps"].mean())
        display_ctx256 = pixel_display_baseline(pixel_llama, variant)
        boolq_row = pixel_boolq[pixel_boolq["variant"] == variant]
        boolq = None if boolq_row.empty else safe_float(boolq_row.iloc[0]["accuracy_pct"])
        rows.append({
            "variant": variant,
            "display_ctx256_tps": display_ctx256,
            "cliff_ctx256_tps": ctx256,
            "ctx2048_tps": ctx2048,
            "cliff_pct": pct_drop(ctx256, ctx2048),
            "boolq_pct": boolq,
        })
    return rows


def qwen_summary(pixel: pd.DataFrame) -> dict:
    qwen = pixel[pixel["model"] == MODEL_QWEN]
    standard = qwen[qwen["experiment_type"] == "standard_sweep"]
    cliff = qwen[qwen["experiment_type"] == "cliff_sweep"]
    ctx256 = standard[standard["context_len"] == 256]
    q2 = ctx256[ctx256["variant"] == "Q2_K"]["decode_tps"].mean()
    q6 = ctx256[ctx256["variant"] == "Q6_K"]["decode_tps"].mean()
    return {
        "rows_total": int(len(qwen)),
        "rows_by_experiment_type": {
            key: int(value) for key, value in qwen.groupby("experiment_type").size().to_dict().items()
        },
        "ctx256_q2k_tps": safe_float(q2),
        "ctx256_q6k_tps": safe_float(q6),
        "cliff_ctx2048_q2k_tps": safe_float(
            cliff[(cliff["variant"] == "Q2_K") & (cliff["context_len"] == 2048)]["decode_tps"].mean()
        ),
    }


def m4_qwen_summary(m4: pd.DataFrame) -> dict:
    qwen = m4[m4["model"] == MODEL_QWEN]
    standard = qwen[qwen["experiment_type"] == "standard_sweep"]
    cliff = qwen[qwen["experiment_type"] == "cliff_sweep"]
    q2_1024 = cliff[(cliff["variant"] == "Q2_K") & (cliff["context_len"] == 1024)]["decode_tps"].mean()
    q2_2048 = cliff[(cliff["variant"] == "Q2_K") & (cliff["context_len"] == 2048)]["decode_tps"].mean()
    q8_1024 = cliff[(cliff["variant"] == "Q8_0") & (cliff["context_len"] == 1024)]["decode_tps"].mean()
    q8_2048 = cliff[(cliff["variant"] == "Q8_0") & (cliff["context_len"] == 2048)]["decode_tps"].mean()
    return {
        "rows_total": int(len(qwen)),
        "rows_by_experiment_type": {
            key: int(value) for key, value in qwen.groupby("experiment_type").size().to_dict().items()
        },
        "tg128_q2k_tps": safe_float(
            standard[(standard["variant"] == "Q2_K") & (standard["context_len"] == 0)]["decode_tps"].mean()
        ),
        "tg128_q8_tps": safe_float(
            standard[(standard["variant"] == "Q8_0") & (standard["context_len"] == 0)]["decode_tps"].mean()
        ),
        "q2k_cliff_pct_1024_to_2048": pct_drop(q2_1024, q2_2048),
        "q8_cliff_pct_1024_to_2048": pct_drop(q8_1024, q8_2048),
    }


def cross_device_summary(m4: pd.DataFrame, x86: pd.DataFrame) -> dict:
    m4_llama = m4[
        (m4["model"] == MODEL_LLAMA) &
        (m4["backend"] == "Metal") &
        (m4["experiment_type"] == "tps_sweep")
    ]
    x86_llama = x86[
        (x86["model"] == MODEL_LLAMA) &
        (x86["experiment_type"] == "standard_sweep")
    ]
    return {
        "x86_ctx256_q2k_tps": safe_float(x86_llama[x86_llama["variant"] == "Q2_K"]["decode_tps"].mean()),
        "x86_ctx256_q6k_tps": safe_float(x86_llama[x86_llama["variant"] == "Q6_K"]["decode_tps"].mean()),
        "m4_q4ks_tps": safe_float(m4_llama[m4_llama["variant"] == "Q4_K_S"]["decode_tps"].mean()),
        "m4_q8_tps": safe_float(m4_llama[m4_llama["variant"] == "Q8_0"]["decode_tps"].mean()),
    }


def build_manifest(pixel, m4, x86, quality, ppl, dashboard) -> dict:
    split_counts = {
        "pixel_inference": int(len(pixel)),
        "m4_inference": int(len(m4)),
        "x86_inference": int(len(x86)),
        "quality_benchmarks": int(len(quality)),
        "perplexity": int(len(ppl)),
    }
    inference_total = split_counts["pixel_inference"] + split_counts["m4_inference"] + split_counts["x86_inference"]
    total_records = inference_total + split_counts["quality_benchmarks"] + split_counts["perplexity"]

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "build_command": "python3 scripts/build_public_release.py",
        "split_counts": split_counts,
        "inference_total": inference_total,
        "total_records": total_records,
        "quality_devices": {
            str(key): int(value) for key, value in quality.groupby("device").size().to_dict().items()
        },
        "dashboard_contract": {
            "raw_table_rows": len(dashboard["raw_table"]["rows"]),
            "collapse_threshold": dashboard["cliff_curves"]["collapse_threshold"],
            "tps_devices": dashboard["tps_by_variant"]["devices"],
            "quality_devices": dashboard["quality_scores"]["devices"],
        },
        "pixel_llama_core_table": cliff_metric_table(pixel, quality),
        "pixel_qwen_summary": qwen_summary(pixel),
        "m4_qwen_summary": m4_qwen_summary(m4),
        "cross_device_summary": cross_device_summary(m4, x86),
    }


def truth_table_markdown(manifest: dict) -> str:
    rows = manifest["pixel_llama_core_table"]
    threshold = manifest["dashboard_contract"]["collapse_threshold"]
    qwen = manifest["pixel_qwen_summary"]
    m4_qwen = manifest["m4_qwen_summary"]
    xplat = manifest["cross_device_summary"]
    split_counts = manifest["split_counts"]
    quality_devices = manifest["quality_devices"]

    lines = [
        "# Public Truth Table",
        "",
        f"Generated by `python3 scripts/build_public_release.py` on {manifest['generated_at_utc']}.",
        "",
        "## Artifact Counts",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Pixel inference rows | {fmt_int(split_counts['pixel_inference'])} |",
        f"| M4 inference rows | {fmt_int(split_counts['m4_inference'])} |",
        f"| x86 inference rows | {fmt_int(split_counts['x86_inference'])} |",
        f"| Quality rows | {fmt_int(split_counts['quality_benchmarks'])} |",
        f"| Perplexity rows | {fmt_int(split_counts['perplexity'])} |",
        f"| Total inference rows | {fmt_int(manifest['inference_total'])} |",
        f"| Total published records | {fmt_int(manifest['total_records'])} |",
        f"| Quality device split | Pixel6a={quality_devices.get('Pixel6a', 0)}, x86={quality_devices.get('x86', 0)} |",
        "",
        "## Pixel Llama Core Metrics",
        "",
        "| Variant | Display TPS @ ctx=256 | Cliff baseline @ ctx=256 | TPS @ ctx=2048 | Cliff % | BoolQ |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['variant']} | {fmt_float(row['display_ctx256_tps'])} | "
            f"{fmt_float(row['cliff_ctx256_tps'])} | {fmt_float(row['ctx2048_tps'])} | "
            f"{fmt_float(row['cliff_pct'], 1)}% | {fmt_float(row['boolq_pct'], 1)}% |"
        )

    lines.extend([
        "",
        "## Cross-Model and Cross-Device Highlights",
        "",
        "| Claim | Value |",
        "|---|---:|",
        f"| Pixel Qwen rows in published parquet | {fmt_int(qwen['rows_total'])} |",
        f"| Pixel Qwen cliff rows | {fmt_int(qwen['rows_by_experiment_type'].get('cliff_sweep', 0))} |",
        f"| Pixel Qwen standard rows | {fmt_int(qwen['rows_by_experiment_type'].get('standard_sweep', 0))} |",
        f"| Pixel Qwen Q2_K TPS @ ctx=256 | {fmt_float(qwen['ctx256_q2k_tps'])} |",
        f"| Pixel Qwen Q6_K TPS @ ctx=256 | {fmt_float(qwen['ctx256_q6k_tps'])} |",
        f"| M4 Qwen rows in published parquet | {fmt_int(m4_qwen['rows_total'])} |",
        f"| M4 Qwen standard rows | {fmt_int(m4_qwen['rows_by_experiment_type'].get('standard_sweep', 0))} |",
        f"| M4 Qwen cliff rows | {fmt_int(m4_qwen['rows_by_experiment_type'].get('cliff_sweep', 0))} |",
        f"| M4 Qwen Q2_K tg128 TPS | {fmt_float(m4_qwen['tg128_q2k_tps'])} |",
        f"| M4 Qwen Q8_0 tg128 TPS | {fmt_float(m4_qwen['tg128_q8_tps'])} |",
        f"| M4 Qwen Q2_K ctx=1024→2048 change | {fmt_float(m4_qwen['q2k_cliff_pct_1024_to_2048'], 1)}% |",
        f"| M4 Qwen Q8_0 ctx=1024→2048 change | {fmt_float(m4_qwen['q8_cliff_pct_1024_to_2048'], 1)}% |",
        f"| x86 Q2_K TPS @ ctx=256 | {fmt_float(xplat['x86_ctx256_q2k_tps'])} |",
        f"| x86 Q6_K TPS @ ctx=256 | {fmt_float(xplat['x86_ctx256_q6k_tps'])} |",
        f"| M4 Metal Q4_K_S TPS | {fmt_float(xplat['m4_q4ks_tps'])} |",
        f"| M4 Metal Q8_0 TPS | {fmt_float(xplat['m4_q8_tps'])} |",
        "",
        "## Dashboard Threshold Contract",
        "",
        "| Source | Threshold |",
        "|---|---|",
        f"| Pixel6a_Llama | ctx={threshold['Pixel6a_Llama']['start']} |",
        f"| Pixel6a_Qwen | ctx={threshold['Pixel6a_Qwen']['start']} |",
        f"| x86_Llama | ctx={threshold['x86_Llama']['start']}–{threshold['x86_Llama']['end']} |",
        "| M4Mac_Llama | none |",
        "| M4Mac_Qwen | none |",
        "",
        "## Release Notes",
        "",
        "- M4 Qwen rows are promoted from `results/m4_qwen_tps_20260415_130955/` and `results/m4_qwen_cliff_20260416_021323/` after validation. Older M4 Qwen attempts remain archived and excluded.",
        "- x86 Qwen cliff reruns remain excluded because the pushed result files contain missing/zero-throughput rows at larger contexts.",
        "- Q4_K_M and Q5_K_M display TPS use thermally settled `standard_sweep` baselines; cliff percentages use canonical filled-context baselines.",
        "- Raw result provenance remains in `results/`, with mapping documented in `results/CANONICAL.md`.",
        "",
    ])
    return "\n".join(lines)


def validate(manifest: dict, pixel, m4, x86, quality, ppl, dashboard) -> list[str]:
    failures: list[str] = []

    for name, expected_cols in EXPECTED_COLUMNS.items():
        df = {
            "pixel_inference.parquet": pixel,
            "m4_inference.parquet": m4,
            "x86_inference.parquet": x86,
            "quality_benchmarks.parquet": quality,
            "perplexity.parquet": ppl,
        }[name]
        if list(df.columns) != expected_cols:
            failures.append(f"{name}: schema drift detected")

    if len(dashboard["raw_table"]["rows"]) != manifest["inference_total"]:
        failures.append("dashboard/raw_table.json row count does not match published inference total")

    if set(quality["device"].unique()) != {"Pixel6a", "x86"}:
        failures.append("quality_benchmarks.parquet device set must be exactly {Pixel6a, x86}")

    if quality["benchmark"].str.startswith("x86_").any():
        failures.append("quality_benchmarks.parquet still contains x86_ benchmark prefixes")

    if set(quality["benchmark"].unique()) != EXPECTED_BENCHMARKS:
        failures.append("quality_benchmarks.parquet benchmark set drifted from expected 6-task contract")

    pixel_ppl = ppl[ppl["device"] == "Pixel6a"]
    pixel_ppl_full = pixel_ppl[
        (pixel_ppl["perplexity_status"] == "success") &
        (pixel_ppl["corpus"] == "wikitext2_full") &
        (pixel_ppl["perplexity"].notna())
    ]
    if set(pixel_ppl_full["variant"].unique()) != set(VARIANT_ORDER):
        failures.append("perplexity.parquet must contain Pixel full-corpus PPL for all 7 variants")

    if pixel_ppl["corpus"].isin(["wikitext2_sample"]).any() or pixel_ppl["perplexity"].isna().any():
        failures.append("Pixel perplexity rows must not contain sample-corpus or null PPL values")

    dashboard_ppl = dashboard["perplexity"]["data"]
    if len(dashboard_ppl) != len(VARIANT_ORDER):
        failures.append("dashboard/perplexity.json must expose exactly one canonical row per variant")
    for row in dashboard_ppl:
        if (
            row.get("device") != "Pixel6a" or
            row.get("corpus") != "wikitext2_full" or
            row.get("status") != "success" or
            row.get("perplexity") is None
        ):
            failures.append("dashboard/perplexity.json must use Pixel full-corpus PPL for every variant")
            break

    m4_qwen = m4[m4["model"] == MODEL_QWEN]
    m4_qwen_counts = m4_qwen["experiment_type"].value_counts().to_dict()
    if m4_qwen_counts != {"cliff_sweep": 91, "standard_sweep": 7}:
        failures.append(f"m4_inference.parquet M4 Qwen counts drifted: {m4_qwen_counts}")

    m4_qwen_standard_variants = set(
        m4_qwen[
            (m4_qwen["experiment_type"] == "standard_sweep") &
            (m4_qwen["context_len"] == 0)
        ]["variant"].unique()
    )
    if m4_qwen_standard_variants != set(VARIANT_ORDER):
        failures.append("M4 Qwen standard_sweep rows do not cover all 7 variants")

    pixel_qwen = pixel[pixel["model"] == MODEL_QWEN]
    pixel_qwen_etypes = set(pixel_qwen["experiment_type"].unique())
    if pixel_qwen_etypes != {"cliff_sweep", "standard_sweep"}:
        failures.append("pixel_inference.parquet Qwen rows must include both cliff_sweep and standard_sweep")

    ctx256_variants = set(
        pixel_qwen[
            (pixel_qwen["experiment_type"] == "standard_sweep") &
            (pixel_qwen["context_len"] == 256)
        ]["variant"].unique()
    )
    if ctx256_variants != set(VARIANT_ORDER):
        failures.append("Pixel Qwen standard ctx=256 rows do not cover all 7 variants")

    threshold = dashboard["cliff_curves"]["collapse_threshold"]
    expected_threshold = {
        "Pixel6a_Llama": {"start": 512, "end": 512, "label": "ARM cliff onset (Q2_K, Q5_K_M)"},
        "Pixel6a_Qwen": {"start": 512, "end": 512, "label": "ARM cliff onset (Q2_K)"},
        "x86_Llama": {"start": 1300, "end": 1400, "label": "x86 KV-cache collapse zone"},
        "M4Mac_Llama": None,
        "M4Mac_Qwen": None,
    }
    if threshold != expected_threshold:
        failures.append("dashboard cliff threshold map drifted from the validated contract")

    docs_expect_absent = {
        README: [
            "4," + "062 individual inference measurements",
            "x86_llama_cliff_20260329_002333",
            "VERIFIED_METRICS_MASTER_TABLE.md",
        ],
        CONTRIBUTING: [
            "The parquet files in `dataset/` are the source of truth.",
            "VERIFIED_METRICS_MASTER_TABLE.md",
        ],
        CANONICAL: [
            "VERIFIED_METRICS_MASTER_TABLE.md",
            "All primary experiments finished as of 2026-04-02.",
            "flat ±2%, no cliff",
        ],
        DASHBOARD_INDEX: [
            "Inference Records",
            "4,000+ controlled inference runs",
            "4,000+ inference records",
        ],
        PLAIN_REPORT: [
            "VERIFIED_METRICS_MASTER_TABLE.md",
        ],
    }
    for path, phrases in docs_expect_absent.items():
        text = path.read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase in text:
                failures.append(f"{path.relative_to(PROJECT)} still contains stale text: {phrase}")

    docs_expect_present = {
        README: ["scripts/build_public_release.py", "artifacts/public_truth_table.md"],
        CONTRIBUTING: ["scripts/build_public_release.py", "artifacts/public_release_manifest.json"],
        CANONICAL: ["artifacts/public_truth_table.md"],
    }
    for path, phrases in docs_expect_present.items():
        text = path.read_text(encoding="utf-8")
        for phrase in phrases:
            if phrase not in text:
                failures.append(f"{path.relative_to(PROJECT)} missing required public-release reference: {phrase}")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and validate the public EdgeLLMBench release")
    parser.add_argument("--skip-prepare", action="store_true", help="skip parquet rebuild")
    parser.add_argument("--skip-bake", action="store_true", help="skip dashboard JSON bake")
    args = parser.parse_args()

    if not args.skip_prepare:
        run_step([sys.executable, str(PROJECT / "scripts" / "prepare_dataset.py")])
    if not args.skip_bake:
        run_step([sys.executable, str(PROJECT / "scripts" / "bake_dashboard_data.py")])

    pixel, m4, x86, quality, ppl = load_frames()
    dashboard = load_dashboard()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(pixel, m4, x86, quality, ppl, dashboard)
    truth_md = truth_table_markdown(manifest)

    manifest_path = ARTIFACTS / "public_release_manifest.json"
    truth_path = ARTIFACTS / "public_truth_table.md"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    truth_path.write_text(truth_md, encoding="utf-8")

    failures = validate(manifest, pixel, m4, x86, quality, ppl, dashboard)
    if failures:
        print("\n[FAIL] public release validation failed:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\n✓ Public release validated")
    print(f"  Manifest   : {manifest_path.relative_to(PROJECT)}")
    print(f"  Truth table: {truth_path.relative_to(PROJECT)}")
    print(f"  Total rows : {manifest['total_records']:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
