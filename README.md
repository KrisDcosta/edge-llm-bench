# On-Device LLM Inference Benchmark
### DSC 291 — Efficient AI | Llama 3.2 3B × llama.cpp × Pixel 6a

> Reproducible benchmark measuring how quantization and context length affect prefill/decode throughput, peak memory, and energy proxy on a 6GB Android device.

---

## Quick Start

```bash
# 1. Install Python deps
pip install -r requirements.txt

# 2. Build llama.cpp for Android ARM64
# → First install NDK via Android Studio > SDK Manager > SDK Tools > NDK (Side by side)
./scripts/build_llamacpp_android.sh

# 3. Download GGUF models
./scripts/download_models.sh Q4_K_M       # ~2 GB, sweet spot
./scripts/download_models.sh all          # all variants (~12 GB total)

# 4. Push to device
adb push vendor/llama.cpp/build-android/bin/llama-cli /data/local/tmp/
adb push vendor/llama.cpp/build-android/bin/libc++_shared.so /data/local/tmp/
adb push local-models/llama3_2_3b_gguf/Q4_K_M.gguf /data/local/tmp/Llama-3.2-3B-Instruct-Q4_K_M.gguf

# 5. Smoke test (verify everything works)
./scripts/smoke_test.sh Q4_K_M

# 6. Run full benchmark
python scripts/benchmark_runner.py --smoke          # 1 trial
python scripts/benchmark_runner.py --quant Q4_K_M   # all contexts for one quant
python scripts/benchmark_runner.py --all             # full sweep (takes ~2-3 hours)

# 7. Generate figures
python analysis/generate_figures.py results/

# 8. Validate logs
python scripts/validate_results.py results/*.jsonl
```

---

## Project Structure

```
291_EAI/
├── PRD.md                    # Requirements, research questions, metrics
├── plan.md                   # Phased execution plan
├── agent.md                  # Agent operating rules
├── requirements.txt          # Python deps (pip install -r)
├── schemas/
│   └── run.schema.json       # JSONL record schema (v1.0)
├── experiments/
│   └── registry.yaml         # 16 planned configs (quant × context)
├── prompts/
│   └── prompt-suite-v1.yaml  # Fixed, versioned prompt set
├── scripts/
│   ├── benchmark_runner.py   # adb orchestrator → JSONL logs
│   ├── parse_llama_output.py # Parse llama_print_timings → PRD metrics
│   ├── smoke_test.sh         # Single-prompt device check
│   ├── build_llamacpp_android.sh  # NDK cross-compile script
│   ├── download_models.sh    # HuggingFace GGUF downloader
│   └── validate_results.py   # Schema validator
├── analysis/
│   └── generate_figures.py   # 9 plots + summary_table.csv
├── artifacts/
│   └── manifest.yaml         # Model artifact tracking
├── android/                  # Android app (llama.cpp + custom UI)
│   ├── lib/                  # llama.cpp JNI lib (builds via NDK)
│   └── app/                  # Chat UI + live metrics + benchmark mode
├── vendor/
│   └── llama.cpp/            # llama.cpp source (git cloned, not committed)
├── local-models/             # GGUF files (not committed, gitignored)
└── results/                  # JSONL benchmark logs (not committed)
```

---

## Framework Decision: llama.cpp (not ExecuTorch)

ExecuTorch was evaluated first (see `android_executorch_backup/`). It was rejected because:

1. **OOM on Pixel 6a**: `LlmModule.load()` triggers Linux OOM killer before Java can handle it
2. **Build fragility**: Known native crashes on Android (GitHub #5264, #6906)
3. **Limited GGUF variants**: Pre-quantized `.pte` artifacts hard to source

**llama.cpp was chosen** for stable ARM64 support, the GGUF ecosystem (Q2–Q8 from HuggingFace), and built-in `llama_print_timings` output.

---

## Model Variants (Llama 3.2 3B Instruct GGUF)

| Variant | Bit level | Size   | Pixel 6a feasibility |
|---------|-----------|--------|----------------------|
| Q2_K    | 2-bit     | ~1.3 GB | ✓ Works              |
| Q3_K_M  | 3-bit     | ~1.6 GB | ✓ Works (bonus)      |
| Q4_K_M  | 4-bit     | ~2.0 GB | ✓ **Sweet spot**     |
| Q6_K    | 6-bit     | ~2.7 GB | ✓ Works              |
| Q8_0    | 8-bit     | ~3.4 GB | ⚠ Tight on 6 GB     |
| F16     | 16-bit    | ~6.4 GB | ✗ OOM (documented)   |

---

## Experiment Matrix

16 planned experiments: Q2_K/Q3_K_M/Q4_K_M/Q6_K/Q8_0 × 3 context lengths (256/512/1024) + FP16 OOM test.

Each: 2 warmup + 5 recorded trials, 128 output tokens, fixed prompt suite.

Status tracked in `experiments/registry.yaml`.

---

## Metrics Definitions

| Metric | Definition |
|--------|-----------|
| TTFT | `t_first_token − t_request_start` |
| Prefill TPS | `input_tokens / prefill_s` |
| Decode TPS | `output_tokens / gen_s` |
| E2E latency | `t_last_token − t_request_start` |
| Gen/Prefill ratio | `gen_s / prefill_s` |
| Peak RSS | `dumpsys meminfo` during inference |
| Battery proxy | `% drop per 1K tokens` |

---

## Reproducibility Protocol

Before every benchmark run:
- ✅ Airplane mode ON
- ✅ Fixed screen brightness
- ✅ Close background apps
- ✅ 2-min cooldown between quant-level switches
- ✅ All logs validated against schema before analysis

---

## Android App

**Build** (requires NDK installed via Android Studio):
```bash
cd android && ./gradlew assembleDebug
adb install app/build/outputs/apk/debug/app-debug.apk
```

**Features:**
- Offline chat with live metrics overlay (TTFT, Prefill TPS, Decode TPS, Gen/Prefill ratio)
- Quant selector dropdown (Q2_K → Q8_0)
- Benchmark mode: runs 3-prompt fixed suite, writes JSONL
- Export log button (shares via Android share sheet)

---

## Environment

- **Device**: Pixel 6a (6 GB RAM, Android 14)
- **Framework**: llama.cpp (cross-compiled for arm64-v8a)
- **NDK**: r27c (install via Android Studio SDK Manager)
- **Python**: 3.10+, `pip install -r requirements.txt`
- **Android SDK**: `/Users/krisdcosta/Library/Android/sdk`
- **JDK**: 17–21 (Temurin 21 recommended)
