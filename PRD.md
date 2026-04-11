# Quantized On-Device LLM Inference Study
## llama.cpp + Llama 3.2 3B on Android (Pixel 6a)

> Goal: a reproducible, measurement-driven benchmark + minimal Android UI demo that quantifies how quantization and context length affect **prefill** and **generation** performance, memory, and energy proxy on Android (Pixel 6a).

---

## 1) Objective

Build a reproducible on-device benchmarking system to analyze how quantization levels **Q8_0/Q6_K/Q4_K_M/Q3_K_M/Q2_K** affect inference performance of **Llama 3.2 3B** on **Android (Pixel 6a)** using **llama.cpp**.

We will measure:

- **TTFT** (time to first token)
- **Prefill TPS**
- **Decode TPS**
- **Generation vs Prefill** (ratio and fractions of total time)
- **End-to-End latency**
- **Peak memory**
- **Battery proxy** (energy estimate)
- **Efficiency vs Quality** tradeoff (perplexity or lightweight quality proxy)

Deliverables:

- Reproducible benchmark harness (config-driven, Python + adb)
- JSONL logs + schema validation
- Auto-generated plots/tables from raw logs
- Minimal Android chat demo with live metrics + log export
- Clear deployment recommendations for 6GB-class Android devices

---

## 2) Framework Decision

### Why llama.cpp (not ExecuTorch)

**ExecuTorch was evaluated first** (see T05–T06 commits in git history). It was rejected for this project because:

1. **OOM on Pixel 6a:** `LlmModule.load()` for Llama 3.2 3B triggers the Linux OOM killer before Java can handle the exception. The 2.4GB `.pte` artifact plus KV-cache overhead exceeds the 6GB device RAM.
2. **Build fragility:** Known native crash issues on Android (GitHub issues #5264, #6906). Documentation is partially out-of-date for cross-compilation.
3. **Limited quantization variants:** Pre-quantized `.pte` artifacts are scarce; custom export requires significant setup.

**llama.cpp advantages:**

1. **Battle-tested Android ARM64 support** via cross-compilation with Android NDK.
2. **GGUF ecosystem:** Pre-quantized models at every bit level (Q2_K through Q8_0) available on HuggingFace.
3. **Built-in timing metrics:** `llama_print_timings` reports prompt eval and eval throughput natively.
4. **Official Android example app** with JNI bridge and Kotlin/Compose UI.
5. **Stability:** Mature project with extensive community testing on ARM devices.

The submitted proposal listed "llama.cpp or MLC-LLM" as framework options. This pivot is fully aligned with the proposal.

---

## 3) Research Questions

### RQ1 — Quantization impact
How do Q8_0/Q6_K/Q4_K_M/Q3_K_M/Q2_K affect:
- TTFT, Prefill TPS, Decode TPS
- Peak memory
- Battery proxy

### RQ2 — Scaling with context length
How do metrics change as context increases?
- Does prefill degrade faster than decode?
- Where do memory limits appear?

### RQ3 — Generation vs Prefill split
How does time split (prefill vs generation) change across:
- Quant levels
- Context lengths

### RQ4 — Efficiency vs quality
What is the Pareto frontier between:
- Performance (TTFT/TPS), memory, battery proxy
- Quality proxy (perplexity or exact-match accuracy)

### RQ5 — Practical deployment limits
- When does OOM happen? (FP16 → OOM; Q8_0 → borderline)
- When does thermal throttling distort performance?
- What is the recommended "default config" for Pixel 6a?
- Why did ExecuTorch fail and what does this imply for framework selection?

---

## 4) Scope

### Included
- **One framework:** llama.cpp (cross-compiled for Android ARM64)
- **One model:** Llama 3.2 3B Instruct (GGUF format)
- **Primary device:** Pixel 6a (6GB RAM)
- **Quantization comparison:** Q2_K, Q3_K_M, Q4_K_M, Q6_K, Q8_0 (maps to 2/3/4/6/8-bit)
- **FP16 attempt:** document OOM as RQ5 finding
- **Context sweep:** at least 3 sizes (256, 512, 1024; attempt 2048)
- **Structured logging** (JSONL) + schema validation
- **Android UI demo** (chat + live metrics + export logs)
- **ExecuTorch evaluation** documented as engineering finding

### Excluded (explicitly not doing)
- Training / fine-tuning
- Multi-framework runtime comparison (ExecuTorch is documented as evaluation, not benchmarked)
- Custom kernel optimizations
- Cloud comparisons
- External power meter hardware (battery proxy via `dumpsys` only)

---

## 5) Experimental Design

### Model artifacts (from HuggingFace: bartowski/Llama-3.2-3B-Instruct-GGUF)

| GGUF Variant | Approx Size | Bit Level | Expected Feasibility |
|-------------|-------------|-----------|---------------------|
| Q2_K | ~1.3 GB | 2-bit | ✓ Runs, quality degraded |
| Q3_K_M | ~1.6 GB | 3-bit | ✓ Bonus data point |
| Q4_K_M | ~2.0 GB | 4-bit | ✓ Sweet spot |
| Q6_K | ~2.7 GB | 6-bit | ✓ Should work |
| Q8_0 | ~3.4 GB | 8-bit | ⚠ Tight on 6GB |
| FP16 | ~6.4 GB | 16-bit | ✗ OOM (document it) |

### Context lengths (target)
- 256
- 512
- 1024
- 2048 (only if stable; otherwise document limit)

### Output length
- Fixed at **128 output tokens** (for fair decode comparisons)

### Trials
- Warmups: **2**
- Recorded: **5**
- Report p50/p90/p99 + mean/std per config

### Prompt suite (minimal, fixed)
- 3 versioned prompts covering: factual QA, summarization, reasoning
- Stored in `prompts/prompt-suite-v1.yaml`
- Prompts are versioned in-repo to keep evaluation reproducible.

---

## 6) Metrics (definitions)

All timestamps derived from llama.cpp `llama_print_timings` output.

**TTFT**
`ttft_s = t_first_token - t_request_start`

**Prefill time** (prompt eval in llama.cpp terms)
`prefill_s` = `prompt_eval_time_ms / 1000`

**Prefill TPS**
`prefill_tps = prompt_eval_tokens / prefill_s`

**Generation (decode) time** (eval in llama.cpp terms)
`gen_s` = `eval_time_ms / 1000`

**Decode TPS**
`decode_tps = eval_tokens / gen_s`

**End-to-End latency**
`e2e_s = total_time_ms / 1000`

**Generation vs Prefill**
- Ratio: `gen_over_prefill = gen_s / prefill_s`
- Fractions:
  - `prefill_frac = prefill_s / e2e_s`
  - `gen_frac = gen_s / e2e_s`

**Peak memory**
- `peak_rss_mb` = from `adb shell dumpsys meminfo <pid>` during inference

**Battery proxy**
- `battery_drop_pct = battery_start_pct - battery_end_pct`
- Normalized:
  - `battery_drop_per_1k_tokens = 1000 * battery_drop_pct / total_tokens`

**Quality proxy**
- Perplexity via `llama-perplexity` on a small WikiText-2 subset, per quant level
- OR: exact-match accuracy on 10 factual QA prompts

---

## 7) Reproducibility Protocol (non-negotiable)

### Device/environment controls
- Airplane mode ON
- Fixed brightness
- Close background apps
- Consistent thermal protocol: 2-min cooldown between quant-level switches

### Run metadata (must be logged)
Each trial record includes:
- device model, Android version
- llama.cpp version / commit hash
- GGUF variant name + artifact SHA256 hash
- quant level, context length, output length
- trial index + warmup flag
- timing values from llama_print_timings
- input/output token counts
- peak memory
- battery start/end (%)
- optional: temperature if accessible

### Log format
- Append-only **JSONL**: one JSON object per trial
- Location: `results/<run_id>.jsonl`

### Schema + validation
- Maintain `schemas/run.schema.json`
- Provide `scripts/validate_results.py` that fails loudly on schema mismatch

### Experiment registry
- Maintain `experiments/registry.yaml` listing every config executed (audit trail)

---

## 8) System Architecture (minimal)

### Components
1. **llama.cpp CLI** (cross-compiled ARM64 binary on device)
2. **Benchmark runner** (Python script orchestrating `adb shell` commands)
3. **Output parser** (Python: parse llama.cpp stdout → schema-valid JSONL)
4. **Analysis** (Python: read JSONL → tables/plots)
5. **Android UI** (llama.cpp Android example app, customized with metrics overlay)

### Dataflow
```
Prompts/config → benchmark_runner.py → adb shell llama-cli → stdout
                                                              ↓
                                           parse_llama_output.py → JSONL logs
                                                                      ↓
                                                     generate_figures.py → plots/report
```

UI app uses the same llama.cpp native library via JNI, logs with the same schema.

---

## 9) Acceptance Tests (definition of "done")

### Smoke test (must pass)
- `adb shell /data/local/tmp/llama-cli -m model.gguf -p "..." -n 32` produces output
- Timing values are captured and parsed into one valid JSONL record

### Benchmark run (must pass)
- Run at least:
  - 4 quant levels (Q2_K, Q4_K_M, Q6_K, Q8_0)
  - 3 context lengths
  - 5 trials each (after warmup)
- Generates plots with one command.

### UI demo (must pass)
- Chat works offline
- Displays TTFT + Prefill TPS + Decode TPS
- Export logs button works

---

## 10) Risks & Mitigations

- **Q8_0 OOM on 6GB device** → document as RQ5 finding; proceed with Q2/Q4/Q6.
- **llama.cpp cross-compile fails** → use pre-built ARM64 binary from releases, or Termux.
- **Battery measurement too coarse** → use longer generation runs (512 tokens) for measurable delta.
- **Thermal throttling** → cooldown protocol + record conditions; report variability.
- **Quality proxy is weak** → use `llama-perplexity` built-in tool on WikiText-2 subset.

---

## 11) Future Extensions (post-course)
- Compare llama.cpp vs ExecuTorch vs MLC-LLM on same device
- Add iOS replication (llama.cpp supports Metal)
- Thread count optimization study
- Paper-style writeup as a measurement study
