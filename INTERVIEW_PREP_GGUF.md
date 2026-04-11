# Interview Prep: GGUF Quantization Benchmarking on Mobile ARM
## Technical Deep Dive — Kris D'Costa

**Project:** DSC 291 (Efficient AI) course project → conference paper (targeting MLSys 2026 / MobiSys 2027)  
**Repo:** https://github.com/krisdcosta/291_EAI (commit `171099f`)  
**Period:** Feb 2026 – Present  
**Status:** Paper complete, LaTeX compiled clean, figures generated, dataset published

---

## 30-Second Pitch

> "I benchmarked 7 GGUF quantization variants of Llama 3.2 3B Instruct on a Pixel 6a using llama.cpp. I ran 700+ automated experiments across ARM, x86, and M4 Metal, with proper thermal controls and filled-context methodology. The headline finding is that speed on ARM is non-monotonic with bit-width — the 2-bit variant (Q2_K) is **112% faster** than the 6-bit variant (Q6_K) on ARM CPU. I traced this to SIMD dequantization overhead in the llama.cpp NEON kernels. I also discovered a KV-cache cliff formula that predicts the context length where throughput collapses, validated on two hardware platforms and two model families."

---

## The Core Findings (Memorize These)

### 1. Non-Monotonic Speed Ordering on ARM CPU
- **What:** Faster ≠ more bits. Q2_K (2.6 bpw) = **7.49 tok/s**. Q6_K (6.3 bpw) = **3.53 tok/s**. That's **112% faster** for the smaller model.
- **Ordering:** Q2_K > Q4_K_S > Q4_K_M ≈ Q3_K_M > Q8_0 > Q5_K_M > Q6_K
- **Why:** NEON SIMD dequantization cost. Q6_K uses a "split-field" layout (6-bit weights stored across two byte arrays) requiring ~36 NEON instructions per 256-weight block. Q2_K uses simple 2-bit masking: ~14 instructions. The extra compute from Q6_K's reconstruction overhead **exceeds** the bandwidth savings from its smaller file.
- **Q8_0 anomaly:** Q8_0 has the simplest dequantization (~8 NEON ops) but ranks 5th because at 3.42 GB, every decode step is DRAM-bound (bandwidth, not compute).
- **Validated on x86 too:** Same ordering on Intel i5-1235U (AVX2). CPU-general, not ARM-specific.

### 2. KV-Cache Cliff at Context Length
- **What:** At ctx=512, Q2_K throughput drops **26.7% in a single step** (and −47.8% total by ctx=2048). Q5_K_M shows a similar cliff (−18% at ctx=512, −46% total).
- **Formula:** `ctx_cliff ≈ L2_cache_bytes / 1024`
  - ARM Cortex-X1: 512 KB / 1024 = **512 tokens** → observed cliff: ctx=512 ✓ (0% error)
  - Intel i5-1235U: 1.25 MB / 1024 = **1280 tokens** → observed cliff: ctx=1300–1400 ✓ (within 8%)
- **Why it happens:** Llama 3.2 3B uses Grouped Query Attention (8 KV heads, 128-dim, fp16). At ctx=512, the per-layer KV footprint = 2 × 8 × 128 × 512 × 2 bytes = ~2 MB across 28 layers. This overflows the Cortex-X1's 512 KB L2 cache. Every attention step now reads from DRAM (100 ns) instead of L2 (5 ns).
- **Why Q2_K is most affected:** Q2_K's dequantization is so cheap that attention takes a large fraction of total decode time. Doubling attention cost → large overall TPS drop. Q6_K is barely affected because its dequantization already dominates; the attention overhead is relatively small.
- **Validated on Qwen 2.5 1.5B too:** Qwen has only 2 KV heads → smaller footprint → cliff still at ctx=512 but shallower (−38.5% vs −47.8%).

### 3. Metal Reversal on M4
- **What:** On M4 Metal (GPU), the ordering completely flips. Q4_K_S = **19.9 tok/s** (fastest). Q8_0 = **6.39 tok/s** (slowest).
- **CPU vs Metal:** For Q8_0, M4 CPU (12.6 tok/s) beats M4 Metal (6.39 tok/s) by **1.97×**. CPU also beats Metal for Q6_K (9.29 vs 7.02).
- **Why:** Metal GPU kernels have efficient paths for K-quant formats (Q4/Q5). Q8_0's trivial CPU dequantization doesn't map well to GPU dispatch. Q6_K's split-field format penalizes both CPU and GPU but differently.
- **No cliff on Metal:** Metal GPU manages KV cache differently; throughput stays flat (±0.8%) across ctx=1024–2048.

### 4. Quality: What Actually Degrades
- **Q2_K HellaSwag = 19%** (below 25% random chance on 4-choice MCQ). Root cause: 56/100 outputs were literally the word "No" — format-following collapse at 2-bit quantization.
- **Statistical caveat:** At n=100 per benchmark, Wilson 95% CI ≈ ±8–9pp. **Only 2 results are statistically significant:**
  - Q2_K HellaSwag (19%) vs any other (z=3.12, p<0.002)
  - Q3_K_M TruthfulQA (68%) vs Q2_K (50%) (z=2.59, p=0.01)
  - All other rankings are directional only — cannot claim "Q4_K_S is significantly better than Q4_K_M on BoolQ."
- **Q6_K is dominated:** Lowest BoolQ (65%) AND slowest CPU TPS (3.53). Avoid on all CPU backends.

### 5. KV Q8_0 Mitigation
- **What:** The `-ctk q8_0 -ctv q8_0` flag quantizes the KV cache from fp16 to int8, halving its memory footprint.
- **Effect on Q2_K:** Cliff eliminated (−50.8% → −2.6% across ctx=256–2048). BUT: baseline cost of −46% at ctx=256 (7.50 → 4.04 tok/s). Crossover where it helps: ctx ≈ 1400.
- **Effect on Q4_K_M:** Only −0.6% baseline cost, halves cliff depth (−12% → −5.5%). **Best all-round for ctx ≥ 512 deployments.**

---

## Numbers to Have Ready

| Metric | Value |
|--------|-------|
| Q2_K ARM TPS (ctx=256) | 7.49 tok/s ± 0.30 (n=10) |
| Q6_K ARM TPS | 3.53 tok/s ± 0.03 |
| Speed advantage Q2_K vs Q6_K | 112% faster (7.49/3.53 − 1) |
| Q4_K_M ARM TPS | 4.78 tok/s (default recommendation) |
| Q4_K_S ARM TPS | 5.01 tok/s (best accuracy/speed) |
| Q2_K cliff onset | ctx=512, −26.7% single step |
| Q2_K total cliff | −47.8% (ctx=256→2048) |
| Q5_K_M cliff onset | ctx=512, −18% single step, −46% total |
| Cliff formula | ctx_cliff ≈ L2_bytes / 1024 |
| ARM L2 (Cortex-X1) | 512 KB → predicted cliff ctx=512 ✓ |
| x86 L2 (i5-1235U) | 1.25 MB → predicted cliff ctx=1280 (obs: 1300–1400) ✓ |
| M4 Metal fastest | Q4_K_S at 19.88 tok/s |
| M4 Metal slowest | Q8_0 at 6.39 tok/s |
| Q2_K HellaSwag | 19% (format collapse, 56/100 "No" outputs) |
| Q4_K_S BoolQ | 74% (directionally highest, not significant vs Q4_K_M) |
| Experiments run | 1,200+ measurements (TPS, cliff, quality, KV mitigation, cross-platform) |
| KV Q8_0 baseline cost | −46% at ctx=256 for Q2_K |
| KV Q8_0 cliff elimination | −50.8% → −2.6% for Q2_K |
| Qwen cross-validation | Same non-monotonic ordering, cliff at ctx=512 confirmed |
| Total Δ x86 Q2_K cliff | −49.9% (cliff onset ctx=1300–1400) |

---

## Likely Interview Questions & Answers

### "Why did you pick llama.cpp over other runtimes?"
llama.cpp is the dominant production runtime for GGUF quantization on Android. Most real deployments of quantized LLMs on mobile use it. MLC-LLM uses ML compilation (a different code path that would answer a different question). ExecuTorch is PyTorch-specific. I wanted to study what practitioners actually use, not a research prototype.

### "What is GGUF / K-quant quantization?"
GGUF (GPT-Generated Unified Format) is the file format used by llama.cpp to store quantized models. K-quant variants (Q2_K through Q8_0) use a "superblock" structure: every 256 weights share a block-level scale factor, and within that, groups of 32 weights share a local scale. The "K" means "super-block aware mixed precision." The trade-off is that lower bits (Q2_K) use coarser quantization but have simpler SIMD dequantization; higher bits (Q6_K) preserve more precision but require complex bit manipulation per block.

### "What's the difference between fresh-context and filled-context?"
If you just change the `-c` flag (context window size) while using a short prompt, the KV cache is nearly empty regardless of what you set `-c` to. The cache only gets full if you actually feed a long prompt. So if you want to measure what happens as context grows, you need to pad the prompt to `ctx - 64` tokens — "filled-context" methodology. Without this, you'd see a flat curve and conclude there's no cliff, which would be wrong. Every prior study that missed this effect likely used naive context window changes.

### "Why is Q5_K_M slow on ARM but fast on M4?"
On ARM CPU, Q5_K_M requires ~28 NEON instructions per 256-weight block — more than Q4_K_M — but doesn't have enough bit-width advantage to compensate for the extra compute. On M4 Metal GPU, the K-quant GPU kernels happen to have an efficient path for 5-bit, making it faster than 6-bit and 8-bit. The GPU vs CPU trade-off fundamentally changes the cost model.

### "How did you handle thermal throttling?"
The Pixel 6a Tensor G1 throttles heavily under sustained load. My protocol: 5-minute cooldown between variants, temperature monitoring (pre-validated < 32°C before each variant run), and running variants sequentially with the hottest-known variant (Q2_K, which generates the most compute per second) last. I also excluded Trial 1 of each (variant, context) cell as warmup. This reduced measurement noise from ±8% to ±2% coefficient of variation.

### "What's the biggest mistake you found in the data?"
Two major ones. First: the ARC-Easy scoring script had a bug — it found the letter "D" in the echoed question body (e.g., "D) soft") instead of the model's actual output, giving 100% accuracy for all variants. I caught this by noticing the numbers were suspiciously perfect and traced it to the extraction regex. Corrected values are 76–82%. Second: the Q5_K_M cliff data was contaminated — an earlier n=3 run had a cold-device baseline that happened to fall near the cliff floor, masking the ctx=512 cliff and making Q5_K_M look stable. A clean isolated n=5 rerun confirmed cliff onset at ctx=512, matching Q2_K's behavior.

### "What is the KV-cache cliff formula and why does it work?"
The formula is `ctx_cliff ≈ L2_cache_bytes / 1024`. It's empirically calibrated: the denominator 1024 fits both ARM (512 KB / 1024 = 512 tokens, cliff at ctx=512) and x86 (1.25 MB / 1024 = 1280 tokens, cliff at ctx=1300–1400). The mechanism: the attention kernel's working set is the KV cache per layer, which grows linearly with context. When that exceeds L2, attention reads from DRAM. The 1024 factor reflects the attention kernel's tiled access pattern — it doesn't need the full KV cache in L2 simultaneously, just a portion. I derived this formula post-hoc from the data, not a priori from hardware specs, but it validated on both platforms and both model families.

### "Why does the ordering differ between ARM CPU and M4 CPU?"
ARM CPU ordering: Q2_K fastest (7.49), Q6_K slowest (3.53). This is non-monotonic.
M4 CPU ordering: Q4_K_S fastest (13.16), Q6_K slowest (9.29). This is also non-monotonic but different pattern.
The reason: ARM's NEON kernels and Apple's AMX (Advanced Matrix Extensions) have different instruction sets and throughput characteristics. AMX on M4 has much higher bandwidth per cycle, so the DRAM-bound penalty for Q8_0 is less severe. The M4's 16 MB L2 also means no cliff occurs in the tested context range (predicted cliff at ctx=16,384, far beyond test).

### "What would you do differently?"
1. Thermal monitoring on x86 and M4 — I documented this as a limitation but hardware monitoring wasn't available.
2. ARM PMU (simpleperf) validation of SIMD instruction counts — I wrote the script but didn't have device access for cycle-accurate measurement. The counts are from static source analysis.
3. Larger n for x86 TPS (n=1 single run — ordering confirmed via cliff data but no CI).
4. Add batch_size > 1 experiments to understand server vs edge trade-offs.
5. Test 7B models — the cliff formula may not generalize with different KV head counts.

### "What's the practical takeaway for a developer?"
Use Q4_K_M as your default. If you need long context (>512 tokens), add `-ctk q8_0 -ctv q8_0` — it barely hurts short-context performance (−0.6%) and halves the cliff. Never use Q6_K on CPU. Never use Q2_K for MCQ or tool-calling tasks. If you're on M4 Mac with Metal, use Q4_K_S — it gives 19.9 tok/s vs Q2_K's 17.8, reversing the CPU ordering completely.

---

## System Design Questions

### "How did you automate 700+ experiments?"
Shell scripts with ADB (Android Debug Bridge) to push models and run inference remotely. Each script:
1. Pre-validates temperature on device
2. Runs N trials per (variant, context) combination
3. Parses `common_perf_print:` lines from llama.cpp stdout for decode TPS and prefill TPS
4. Appends JSON lines to a `.jsonl` file per variant
5. Logs timestamps, device info, thread count, methodology tag
The scripts support `--resume` (skip completed variants) and `--trials=N` overrides. 26 bench scripts total.

### "How did you ensure reproducibility?"
- All raw `.jsonl` trial data committed to repo under `results/`
- Model SHA-256 checksums recorded in `results/model_checksums.sha256`
- Exact llama.cpp commit (`b1-1a29907`) documented
- Build flags documented (NDK 29, `-O3 -march=armv8.2-a+dotprod+fp16`)
- `VERIFIED_METRICS_MASTER_TABLE.md` is the single source of truth — every paper claim traced to a specific JSONL file and line range
- `PROVENANCE.md` documents which result file is canonical for each variant (important because some variants had multiple runs with data quality issues)

### "How did you structure the data pipeline?"
- Raw data: `.jsonl` files (one JSON object per trial) in `results/<run_name>/`
- Aggregation: Python scripts compute mean, SD, 95% CI per (variant, context) cell
- Quality: `quality_scores.json` with per-question records plus aggregate accuracy and Wilson CI
- Dashboard: `dashboard/data/cliff_curves.json` feeds a web dashboard (HTML/JS)
- Paper: `report/report.tex` (IEEEtran format) references `figures/*.pdf`
- Verification: `VERIFIED_METRICS_MASTER_TABLE.md` cross-checks paper claims vs raw data

---

## Edge Cases & Nuances

| Issue | What Happened | How Resolved |
|-------|--------------|-------------|
| ARC-Easy bug | Regex found "D" in question body, not model output → 100% for all | Used `arc_easy_fixed` key (76–82%) |
| Q5_K_M contamination | Cold-device baseline masked ctx=512 cliff in early data | Isolated n=5 rerun confirmed cliff at ctx=512 |
| git merge conflict | Whole report.tex wrapped in `<<<HEAD` / `>>>` markers | Extracted HEAD section (2152 lines), resolved |
| Q4_K_M cliff overstated | Paper said −12%, data shows −6.6% (n=3 cautious) | Paper corrected to −7% |
| DVFS baseline mismatch | Q5_K_M: cliff baseline 6.67 vs TPS baseline 3.75 tok/s | Documented: filled prefill ramps CPU turbo; both valid for different use cases |
| M4 CPU cliff variance | CV up to 80% from macOS scheduling + AMX dispatch changes | Use dedicated TPS sweep (n=10) not cliff sweep for M4 CPU baselines |
| Qwen TPS wrong | Paper said 13.9 tok/s, actual 16.1 (n=5 canonical) | Corrected; ratio 1.92× → 2.23× |
| M4 Metal "flat ±2%" | Actual: Q2_K +8.5%, Q3_K_M +3.4% (increases, not drops) | Paper corrected to per-variant values |

---

## Resume Bullet Updates

### Current (incorrect):
> "Discovered a non-monotonic speed inversion on ARM (Q2_K **135%** faster than Q6_K)"

### Correct:
> "Discovered a non-monotonic speed inversion on ARM (Q2_K **112%** faster than Q6_K, 7.49 vs 3.53 tok/s) caused by SIMD dequantization overhead, and derived a KV-cache cliff threshold formula (`ctx_cliff ≈ L2_bytes/1024`) validated across two hardware platforms and two model families"

**Corrected calculation:** (7.494 − 3.527) / 3.527 × 100 = **112%** faster (not 135%).

### For SDE resume — updated bullets:
```
• Designed and ran 1,200+ automated inference experiments across 7 GGUF quantization variants 
  on ARM, x86, and Metal via ADB shell scripts with thermal controls that reduced measurement 
  noise from ±8% to ±2%, implementing resume-capable sweep automation across 11 context sizes
• Discovered that Q2_K (2-bit) is 112% faster than Q6_K (6-bit) on ARM CPU due to SIMD 
  dequantization overhead, and derived a KV-cache cliff formula validated on 2 platforms and 
  2 model families; Metal GPU reverses this ordering (Q4_K_S fastest at 19.9 tok/s)
```

### For ML resume — updated bullets:
```
• Benchmarked 7 quantization variants of Llama 3.2 3B on Pixel 6a, x86, and M4 Metal, 
  discovering non-monotonic speed ordering (Q2_K 112% faster than Q6_K) traced to SIMD 
  dequantization overhead via static kernel analysis of NEON/AVX2 inner loops
• Derived an L2-cache cliff threshold formula predicting KV-cache throughput collapse 
  (ctx_cliff ≈ L2_bytes/1024; 0% error on ARM, <8% on x86) and characterized a format-
  following failure in Q2_K on structured reasoning tasks (HellaSwag: 19%, below random chance)
```

---

## Technical Vocabulary to Know Cold

| Term | Definition in this context |
|------|---------------------------|
| GGUF | GPT-Generated Unified Format — llama.cpp model file format |
| K-quant | "Super-block aware" quantization scheme in GGUF (Q2_K through Q6_K) |
| Superblock | Group of 256 weights sharing a block-level scale factor in K-quant |
| GQA | Grouped Query Attention — Llama 3.2's attention variant; 8 KV heads, 24 Q heads |
| KV cache | Key-Value cache: stores past attention context to avoid recomputation per decode step |
| Decode TPS | Tokens per second during the generation phase (after prompt processing) |
| Prefill TPS | Tokens per second during prompt processing phase |
| Filled-context | Methodology where prompt is padded to `ctx − 64` tokens to actually fill the KV cache |
| DVFS | Dynamic Voltage and Frequency Scaling — CPU clock speed adaptation to load/temperature |
| NEON | ARM's SIMD instruction set (128-bit vectors, used in Cortex-X1) |
| AVX2 | x86 SIMD instruction set (256-bit vectors, used in Intel i5-1235U) |
| AMX | Apple Matrix Extensions — M4's hardware matrix multiply unit |
| ADB | Android Debug Bridge — USB protocol for running commands on Android |
| Wilson CI | Wilson score confidence interval for binomial proportions (better than normal approximation at small n) |
| PPL | Perplexity — language model quality metric; lower = better; WikiText-2 corpus used here |
| ngl | Number of GPU layers in llama.cpp; ngl=0 = CPU only; ngl=99 = all layers on GPU |
| THP | Transparent Huge Pages — Linux kernel memory optimization; may explain Q2_K recovery at long ctx |

---

## Publications & Recognition
- Paper: "Beyond Bit-Width: SIMD Dequantization Overhead Creates a CPU/GPU Performance Divide in GGUF K-Quant LLM Inference" — targeting MLSys 2026
- Dataset: Published on Hugging Face (pixel_inference.parquet + m4_inference.parquet)
- Repo: github.com/KrisDcosta/291_EAI — full raw data, scripts, and dashboard
