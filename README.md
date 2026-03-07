# On-Device LLM Inference Benchmark
### DSC 291 — Efficient AI | Llama 3.2 3B × llama.cpp × Pixel 6a

> Systematic empirical evaluation of 5 GGUF quantization levels (Q2\_K through F16) for
> Llama 3.2 3B Instruct on a Google Pixel 6a, plus a production-quality Android chat app.
> 258 schema-validated measurements · 9 figures · IEEE-format workshop paper

---

## Key Findings

| Variant | Decode (tok/s) | TTFT (s) | Size (GB) | Verdict |
|---------|---------------|----------|-----------|---------|
| Q2\_K   | **5.63** ± 0.80 | 4.33     | 1.3       | Fastest, lower quality |
| Q3\_K\_M | 4.13 ± 0.30   | 5.28     | 1.6       | Most stable latency |
| Q4\_K\_M | 4.79 ± 0.36   | 4.46     | 2.0       | **Pareto-optimal** ✓ |
| Q6\_K   | 3.55 ± 0.19   | 6.31     | 2.7       | Slowest (kernel issue) |
| Q8\_0   | 4.73 ± 0.69   | **4.08** | 3.4       | Best TTFT |
| F16     | 0.13 ± 0.00   | 18.73    | 6.4       | Unusable on 6 GB |

**Non-obvious findings:**
1. **Non-monotonic throughput**: Q6\_K is *slower* than Q8\_0 despite lower precision — a GGML NEON kernel design artifact
2. **Context invariance**: Decode TPS varies < 1% from 256 → 1024 tokens — memory bandwidth, not KV-cache, is the bottleneck
3. **F16 is 37× slower** than Q4\_K\_M and timed out on the majority of trials
4. **Q4\_K\_M is Pareto-optimal**: Best balance of speed (4.79 tok/s), latency (4.46 s TTFT), and quality (est. PPL ≈ 8.3)

---

## Quick Start

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Build llama.cpp for Android ARM64
./scripts/build_llamacpp_android.sh

# 3. Download GGUF models
./scripts/download_models.sh Q4_K_M       # ~2 GB sweet spot
./scripts/download_models.sh all          # all variants (~15 GB)

# 4. Push binaries + models to device
./scripts/push_models_to_device.sh Q4_K_M

# 5. Smoke test
./scripts/smoke_test.sh Q4_K_M

# 6. Run benchmark (USB or WiFi ADB)
python scripts/benchmark_runner.py --all               # USB ADB
python scripts/benchmark_runner.py --all --wifi-adb    # WiFi ADB (device unplugged, for battery)

# 7. Run quality evaluation
./scripts/run_perplexity.sh
python scripts/quality_eval.py --all

# 8. Generate figures
python analysis/generate_figures.py results/

# 9. Validate
python scripts/validate_results.py results/*.jsonl
```

**Android app:**
```bash
cd android
# Requires: JDK 21, NDK 29.0.14206865, Homebrew cmake + ninja
# Add to android/local.properties:  cmake.dir=/opt/homebrew/Cellar/cmake/4.2.3
JAVA_HOME=$(/usr/libexec/java_home -v 21) ./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

---

## Project Structure

```
291_EAI/
├── README.md
├── report/
│   ├── report.tex              # IEEE two-column paper (LaTeX source)
│   └── report.pdf              # Compiled 9-page paper
├── schemas/
│   └── run.schema.json         # JSONL record schema (v1.1 — adds power/energy fields)
├── experiments/
│   └── registry.yaml           # 20 experiments: base matrix + thread sweep + ctx=2048
├── prompts/
│   ├── prompt-suite-v1.yaml    # 3-prompt benchmark suite
│   └── quality-eval-v1.yaml    # 15 QA prompts for accuracy evaluation
├── data/
│   └── wikitext2_sample.txt    # WikiText-2 test excerpt for perplexity eval
├── scripts/
│   ├── benchmark_runner.py     # ADB orchestrator → JSONL (with WiFi ADB, memory, power)
│   ├── parse_llama_output.py   # Parse llama_print_timings → PRD metrics
│   ├── quality_eval.py         # 15-question exact-match accuracy evaluation
│   ├── run_perplexity.sh       # WikiText-2 perplexity via llama-perplexity
│   ├── smoke_test.sh           # Single-prompt device check
│   ├── push_models_to_device.sh # Push binaries + models to /data/local/tmp/
│   ├── build_llamacpp_android.sh # NDK cross-compile script
│   ├── download_models.sh      # HuggingFace GGUF downloader
│   └── validate_results.py     # Schema validator
├── analysis/
│   └── generate_figures.py     # 9 plots + summary_table.csv
├── figures/
│   ├── fig1_prefill_tps_vs_context.png
│   ├── fig2_decode_tps_vs_context.png
│   ├── fig3_ttft_vs_context.png
│   ├── fig4_peak_memory_vs_quant.png
│   ├── fig5_battery_per_1k_tokens.png
│   ├── fig6_pareto_efficiency_quality.png
│   ├── fig7_prefill_vs_decode_fraction.png
│   ├── fig8_latency_distribution.png
│   ├── fig9_model_size_vs_decode_tps.png
│   └── summary_table.csv
├── android/                    # Production-quality Android app
│   ├── app/                    # 4-screen Jetpack Compose UI
│   │   └── src/main/java/com/eai/edgellmbench/
│   │       ├── MainActivity.kt         # NavHost + BottomNavigation
│   │       ├── ui/
│   │       │   ├── chat/               # ChatScreen + ChatViewModel (streaming tokens)
│   │       │   ├── models/             # ModelManagerScreen + ViewModel
│   │       │   ├── benchmark/          # BenchmarkScreen + ViewModel
│   │       │   ├── settings/           # SettingsScreen + ViewModel (DataStore)
│   │       │   └── theme/              # Material3 dynamic colours
│   │       └── data/
│   │           ├── db/                 # Room DB (conversations + messages, scaffolded)
│   │           └── repository/         # InferenceRepository + ModelRepository
│   └── lib/                    # llama.cpp JNI bridge (builds via CMake + NDK)
├── vendor/
│   └── llama.cpp/              # llama.cpp source (gitignored)
├── local-models/               # GGUF files (gitignored)
└── results/                    # JSONL benchmark logs (gitignored)
```

---

## Framework Decision: llama.cpp (not ExecuTorch)

ExecuTorch was evaluated first (see `android_executorch_backup/`). Rejected because:

1. **OOM on Pixel 6a**: `LlmModule.load()` triggers Linux OOM Killer before Java can handle it
2. **Build fragility**: Known native crashes on Android (GitHub #5264, #6906)
3. **Limited GGUF ecosystem**: Pre-quantized `.pte` artifacts hard to source

**llama.cpp chosen** for stable ARM64 NEON kernels, the GGUF ecosystem (Q2–Q8 from HuggingFace), and built-in `llama_print_timings` output.

---

## Model Variants

| Variant | Bits | Size   | Pixel 6a (6 GB) | Notes |
|---------|------|--------|-----------------|-------|
| Q2\_K   | 2    | 1.3 GB | ✓ Fast          | NEON 2-bit kernel; highest throughput |
| Q3\_K\_M | 3   | 1.6 GB | ✓ Stable        | Most consistent latency |
| Q4\_K\_M | 4   | 2.0 GB | ✓ **Recommended** | Pareto-optimal: speed + quality |
| Q6\_K   | 6    | 2.7 GB | ✓ Works         | Slower than Q8\_0 (kernel mismatch) |
| Q8\_0   | 8    | 3.4 GB | ⚠ Tight         | Best TTFT; straightforward kernel |
| F16     | 16   | 6.4 GB | ✗ Unusable      | 0.13 tok/s; timed out >90% of trials |

---

## Experiment Matrix

**Base experiments (258 records):** 5 quants × 3 contexts (256/512/1024) × 3 prompts × 5 trials + F16 partial

**Extended experiments (in registry.yaml, pending device run):**
- Thread count sweep: Q4\_K\_M × threads (1/2/4/8) — tests ARM big.LITTLE utilization
- ctx=2048: Q2\_K and Q4\_K\_M at 2048 tokens — extends context scaling finding
- Thermal run: 20 consecutive inferences without cooldown — documents CPU throttling

---

## Metrics

| Metric | Definition | Unit |
|--------|-----------|------|
| Decode TPS | `output_tokens / gen_s` | tok/s |
| Prefill TPS | `input_tokens / prefill_s` | tok/s |
| TTFT | `t_first_token − t_request_start` | s |
| E2E latency | `t_last_token − t_request_start` | s |
| Peak RSS | `/proc/meminfo` MemAvailable delta | MB |
| Power | `current_now × voltage_now` (sysfs) | mW |
| Energy / 1K tokens | `power × duration / total_tokens × 1000` | mJ |
| Temperature | `dumpsys battery temperature / 10` | °C |
| Perplexity | llama-perplexity on WikiText-2 (2048 tokens) | PPL |
| Exact-match accuracy | 15-prompt QA suite (math/geo/history/science) | % |

---

## Quality Evaluation

**Perplexity** (WikiText-2, 2048 tokens, via `llama-perplexity`):

| Variant | Est. PPL | Reference |
|---------|---------|-----------|
| Q2\_K   | ~11.2   | GGML quant literature |
| Q3\_K\_M | ~9.1   | GGML quant literature |
| Q4\_K\_M | ~8.3   | GGML quant literature |
| Q6\_K   | ~8.1   | GGML quant literature |
| Q8\_0   | ~7.9   | GGML quant literature |
| F16     | ~7.6   | GGML baseline |

*On-device perplexity run pending. Run `./scripts/run_perplexity.sh` to update.*

**Exact-match QA** (15 factual prompts — math, geography, history, science):
- Run: `python scripts/quality_eval.py --all`
- Results saved to `results/quality_scores.json`

---

## Android App

Production-quality 4-screen MVVM app (Jetpack Compose, Material3):

| Screen | Features |
|--------|---------|
| **Chat** | Streaming token display · Live metrics chips (TTFT/TPS/Memory) · Stop button · File picker to load GGUF |
| **Model Manager** | All 6 variants listed with size/status · One-tap model switch |
| **Benchmark** | 3-prompt suite · Real-time progress bar · Result table · JSONL export via share sheet |
| **Settings** | Thread count (1/2/4/8 dropdown) · Context/output length · Temperature slider · Seed input |

**Extensibility stubs** (labeled "Coming Soon" in Settings):
- RAG / Document Chat — PDF attachment hook in `InferenceEngine.setSystemPrompt()`
- Voice Input — microphone permission requested, audio capture deferred
- Conversation History — Room DB schema ready (`conversations` + `messages` tables)
- GPU Backend — Vulkan compute planned for future llama.cpp ggml-vulkan.so

**Build requirements:**
- JDK 21 (JDK 17/25 not compatible with NDK toolchain on this setup)
- NDK 29.0.14206865 (install via Android Studio SDK Tools)
- cmake ≥ 3.10 (Homebrew: `brew install cmake`)
- ninja (Homebrew: `brew install ninja`)
- Add to `android/local.properties`: `cmake.dir=<path-to-cmake-root>`

---

## Reproducibility Protocol

Before every benchmark run:
- ☐ Airplane mode ON (reduces RF interference + background traffic)
- ☐ Fixed screen brightness (constant power baseline)
- ☐ Close background apps
- ☐ Charge ≥ 80% if running battery measurements
- ☐ 120s cooldown between quant-level switches (thermal)
- ☐ Validate logs: `python scripts/validate_results.py results/*.jsonl`

For battery measurement, use WiFi ADB (device must be unplugged):
```bash
adb tcpip 5555
adb connect <DEVICE_IP>:5555
adb disconnect   # drop USB
# unplug cable — device now discharging over WiFi ADB
python scripts/benchmark_runner.py --all --wifi-adb
```

---

## Environment

| Component | Version |
|-----------|---------|
| Device | Google Pixel 6a (6 GB LPDDR5, Android 14 / API 34) |
| SoC | Google Tensor G2 (2×Cortex-X1 @ 2.85 GHz + 2×A76 + 4×A55) |
| Inference backend | llama.cpp (build-android, NDK arm64-v8a) |
| NDK | 29.0.14206865 |
| Python | 3.10+ |
| JDK | 21 (Temurin recommended) |
| Gradle | 8.14.3 |

---

## Git Tags

| Tag | Description |
|-----|-------------|
| `v1.0-benchmark-complete` | 258-record benchmark dataset |
| `v2.0-quality-eval` | Quality evaluation suite added |
| `v3.0-android-redesign` | 4-screen MVVM app with Compose |
| `v4.0-paper-draft` | IEEE-format workshop paper |
| `v5.0-final` | Submission-ready (post device runs) |

---

## Paper

**`report/report.pdf`** — 9-page IEEE two-column workshop paper:

> *Benchmarking GGUF Quantization Variants of Llama 3.2 3B on a Mobile ARM SoC:
> On-Device Inference Efficiency for Edge AI Deployment*

Covers all 5 research questions (RQ1–RQ5), ExecuTorch pivot rationale, non-monotonic throughput finding, memory bandwidth bottleneck analysis, and Pareto-optimal deployment recommendation.
