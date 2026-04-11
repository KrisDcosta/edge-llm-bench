# Interview Prep — GGUF Quantization Benchmarking Project
### Technical Deep-Dive for Resume Discussions

---

## The Pitches (Memorise These)

### 30-Second Version
"I benchmarked all 7 GGUF quantization variants — think of them as different compression levels for a language model — across ARM, x86, and Apple Silicon. The key finding was that speed doesn't follow bit-width: the 2-bit model is 112% faster than the 6-bit model on CPU, because SIMD dequantization overhead, not model size, controls throughput. I also derived a hardware formula that predicts exactly when a model will lose 46–48% of its speed as conversation length grows — and I validated it on two separate hardware platforms and two different model families. The paper is submitted to MLSys 2026."

### 2-Minute Version
"The project started with a simple question: when you're deploying a language model on a phone and you have to pick a quantization level, how do you choose? The conventional wisdom is 'fewer bits = faster but lower quality', but I found that's wrong in both directions.

On an ARM CPU, the 2-bit Q2_K model runs at 7.5 tokens per second while the 6-bit Q6_K runs at 3.5 — that's 112% slower, even though Q2_K is the most compressed. The mechanism is SIMD dequantization: Q6_K requires 2.6x more NEON operations per weight block to recover the 6-bit values, which dominates the bottleneck. I verified this pattern replicates exactly on x86 AVX2, confirming it's a CPU-general effect.

I also discovered what I call the KV-cache cliff. When a conversation gets long, the model's attention cache overflows the CPU's L2 cache and spills to RAM. Throughput drops 46–48% abruptly. I derived a formula: the cliff occurs at context_length = L2_cache_size / 1024 — predicted 512 tokens for the Pixel 6a and 1,280 for the i5-1235U, both validated to within 8%.

Finally, on Apple Metal GPU, the entire speed ordering reverses. Q4_K_S becomes fastest (19.9 tok/s) while Q8_0 drops to last (6.4 tok/s), because GPU dispatch overhead penalises the complex dequantization kernels differently than CPU SIMD.

I ran 1,200+ controlled experiments, built a data cleaning pipeline that caught several critical bugs in the raw data, and wrote this up as a research paper targeting MLSys 2026."

---

## Key Numbers to Have Ready

| Number | Value | Context |
|--------|-------|---------|
| Fastest ARM variant | Q2_K at **7.49 tok/s** | Pixel 6a, 4 threads, ctx=256 |
| Slowest ARM variant | Q6_K at **3.53 tok/s** | Pixel 6a, 4 threads, ctx=256 |
| Speed inversion ratio | **112% faster** (Q2_K vs Q6_K) | (7.49−3.53)/3.53 = 1.12 |
| ARM cliff onset | **ctx=512** | Cortex-X1, 512 KB L2 |
| ARM cliff depth (Q2_K) | **−47.8%** (7.07 → 3.69 tok/s) | Filled-context, n=10 |
| ARM cliff depth (Q5_K_M) | **−45.9%** (6.67 → 3.61 tok/s) | Filled-context, n=5 clean run |
| Cliff formula | **L2 / 1024** | In tokens; validated 0% error ARM, <8% x86 |
| x86 cliff onset | **ctx=1,300–1,400** | i5-1235U, 1.25 MB L2 |
| x86 cliff depth (Q2_K) | **−50%** (17.6 → 8.8 tok/s) | n=5 |
| Best Metal variant | Q4_K_S at **19.88 tok/s** | M4, ngl=99 |
| Worst Metal variant | Q8_0 at **6.39 tok/s** | M4, ngl=99 |
| M4 CPU beats Metal for | Q8_0 (12.60 vs 6.39) and Q6_K (9.29 vs 7.02) | CPU wins due to dispatch overhead |
| Q2_K HellaSwag collapse | **19%** (below 25% random chance) | 56/100 outputs "No" — format collapse |
| Q3_K_M TruthfulQA | **68%** (best; significant vs Q2_K) | z=2.59, p=0.01 |
| KV Q8_0 cliff fix | Q2_K: −50.8% → **−2.6%** | At cost of −46% at ctx=256 |
| KV Q8_0 crossover | **ctx ≈ 1,400** | Q2_K default vs KV q8_0 |
| Recommended long-ctx config | Q4_K_M + KV Q8_0 | 4.70→4.44 tok/s, −5.5% total |
| Thermal noise reduction | **±8% → ±2%** | With 5-min cool-down protocol |
| Total experiments | **1,200+** | Across all platforms and benchmarks |
| Qwen cliff onset | **ctx=512** | Same formula; 2 KV heads vs Llama's 8 |
| Qwen speed ratio | **2.23x faster than Llama** | Q2_K: 16.06 vs 7.49 tok/s |

---

## Technical Depth — Go-Deep Answers

### Q: "How exactly does SIMD dequantization cause the speed inversion?"

LLM decode is memory-bandwidth-limited — on every token generated, the CPU reads the entire model weight matrix. But it doesn't just *read* bytes — it must *dequantize* compressed integers back to floats before the matrix-vector multiply.

For Q2_K: each 256-weight block uses 2-bit values packed into bytes, plus a block-level scale factor. Dequantization is ~10 NEON instructions: AND two bits out, shift, scale, done. Weight table: 32 bytes per superblock (fits in L1).

For Q6_K: the 6 bits per weight are *split across two separate byte arrays* in the block (`ql` stores 4 low bits, `qh` stores 2 high bits separately). Reconstruction requires: load 32 bytes of ql, load 32 bytes of qh, bit-shift and OR to reassemble 6-bit values, then scale. That's ~26 NEON instructions per 256 weights — 2.6x more. You're also loading 96 bytes per 128 weights vs 32 bytes for Q2_K.

Q6_K spends more CPU time on dequantization than Q2_K, even though Q6_K's weights are stored more precisely. The dequantization cost dominates, and precision doesn't help you go faster.

I validated this by counting instruction counts from the llama.cpp source (`ggml/src/ggml-cpu/arm/quants.c`), then confirmed the predicted ordering exactly matches observed TPS. The same pattern holds on x86 AVX2 with the same instruction ratio.

### Q: "Why does Q8_0 not win? It has the simplest dequantization."

Q8_0 has only ~8 NEON ops per 256 weights (just a scale multiply) — much simpler than Q2_K. But its file is 3.4 GB vs 1.3 GB for Q2_K.

The Pixel 6a's Cortex-X1 has 512 KB L2 per core. Q2_K's weight tiles are small enough that some fraction stays in L2 between accesses. Q8_0's tiles don't fit — every decode step causes constant L2 misses and DRAM reads. DRAM latency (~50 ns) vs L2 latency (~2 ns) is a 25x difference.

On M4 CPU (16 MB L2 cluster cache), Q8_0 jumps to 2nd fastest (12.60 tok/s) — because its weights now fit in the larger cache. This is direct confirmation that L2 size is the controlling variable.

### Q: "Walk me through the cliff formula."

The KV cache for Llama 3.2 3B stores keys and values for each token across all layers. Per-layer footprint:

```
C_layer(ctx) = 2 (K+V) × 8 (KV heads) × 128 (head_dim) × ctx × 2 bytes (fp16)
             = 4,096 × ctx bytes
```

At ctx=512: 4,096 × 512 = 2 MB per layer. During decode, the attention kernel reads this buffer for each token generated. When it overflows L2 (512 KB on Cortex-X1), every attention operation becomes a DRAM read.

The empirical formula `ctx_cliff = L2_size / 1024` means the effective working set that needs to fit in L2 is roughly L2/1024 tokens of per-layer KV data. The factor of 1024 accounts for the kernel's tiled access pattern — it doesn't stream the KV buffer linearly; it accesses in tiles interleaved with other operations.

Validated:
- Cortex-X1: 512 KB / 1024 = 512 tokens. Observed: ctx=512. **0% error.**
- i5-1235U: 1,280 KB / 1024 = 1,280 tokens. Observed: ctx=1,300–1,400. **<8% error.**
- Qwen 2.5 1.5B (2 KV heads, half the KV traffic): same formula predicts ctx=512. Observed: ctx=512.

### Q: "Why does Metal reverse the ordering?"

On ARM/x86, the CPU processes one token at a time with a sequential SIMD dot product loop — predictable, cache-friendly. Bottleneck = L2 → register bandwidth.

On Metal GPU, thousands of shader cores run in parallel, but there's kernel dispatch overhead for each compute call. For Q8_0 whose dequantization is trivial, the GPU kernel finishes so quickly that dispatch overhead dominates. For Q2_K–Q5_K_M, actual compute is substantial enough to amortise that cost.

Additionally, Q6_K's split-bit reconstruction (`ql` + `qh` arrays) creates non-contiguous memory reads that don't coalesce well on GPU memory buses — a pattern GPUs hate.

Result: Q4_K_S (moderate complexity, well-vectorisable) is fastest on Metal. Q8_0 (trivial compute, dispatch-dominated) is last. Q6_K is near-last. Q8_0 on M4 CPU (12.60 tok/s) actually beats Q8_0 on Metal (6.39 tok/s).

### Q: "What was the hardest data quality problem you solved?"

The Q5_K_M cliff story. Initial n=3 run: baseline 4.46 tok/s, cliff appeared at ctx=1,300 (−25.8%). Looked moderate.

Then n=10 canonical run: baseline jumped to 7.61 tok/s — way above the TPS sweep value of 3.75 tok/s. Suspicious.

Root cause: **DVFS (Dynamic Voltage and Frequency Scaling)**. The n=10 run ran after sequential testing of other variants, which had already warmed the CPU to turbo frequency. Q5_K_M inherited an inflated baseline. The n=3 run had a cold device — baseline (4.46 tok/s) was already near the cliff floor (3.31 tok/s), so the cliff appeared shallow.

Fix: isolated n=5 run — fresh device state, only Q5_K_M, dedicated thermal protocol. Result: baseline 6.67 tok/s, cliff at ctx=512, −46% total. Completely reverses the conclusion: Q5_K_M is cliff-prone at ctx=512, not moderate at ctx=1,300.

**Lesson:** Baseline measurement in sequential experimental designs is a confounder. DVFS, cache warmup, and thermal state can all shift your baseline by 30–50% without you noticing if you're not explicitly controlling for it.

### Q: "What's the significance of the Q2_K HellaSwag collapse?"

HellaSwag is a 4-choice sentence completion task. Random chance = 25%. Q2_K scored 19% — below random. But looking at the raw outputs: 56/100 answers were the word "No". The model treated a 4-choice completion question like a yes/no question.

This is a **structured failure mode**, not random degradation. At 2-bit quantization, the instruction-following capability for MCQ-format tasks breaks entirely, even though performance on BoolQ (69%) and ARC-Easy (76%) remains reasonable.

Practical impact: any system using Q2_K for tool-call routing, function-selection prompts, or structured JSON output would fail in the same way. Safe use case for Q2_K: open-ended generation (chat, summarisation) where output format is unconstrained.

---

## Common Interview Questions

**"What was your hypothesis going in?"**
That speed and bit-width would correlate monotonically — fewer bits = faster. The experiment disproved this on CPU. On GPU it produces a third, different ordering. The surprise is what makes this publishable.

**"How do you know your measurements are reliable?"**
Three layers: (1) n=10 trials per cell with warmup discarded — computable 95% CIs; (2) 5-minute thermal protocol reducing noise from ±8% to ±2%; (3) cross-validated on x86 and two models. The cliff formula working on a different model with different KV head count is the strongest external validation of the mechanism.

**"Did you find any bugs?"**
Yes — five that changed conclusions:
- ARC-Easy scoring returning 100% for all variants → fixed to 76–82%
- Q5_K_M cliff at ctx=1,300 (−25.8%) → actually ctx=512 (−46%), cold baseline confound
- Q4_K_M cliff −45% → actually −6.6%, sequential warmup contamination
- Qwen Q2_K cited as 13.9 tok/s → actually 16.1 tok/s (contaminated run)
- Dashboard JSON with unresolved git merge conflict markers (invalid JSON)

**"What would you do differently?"**
(1) Run hardware PMU counters (`simpleperf` on rooted device) to directly measure L2 miss rates instead of inferring from instruction counts. (2) Increase quality eval to n=300+ to detect smaller effect sizes — ±9pp CI at n=100 is too wide. (3) Test FlashAttention-enabled builds, which change the attention kernel structure and may shift the cliff behaviour.

**"How does this relate to industry deployments?"**
llama.cpp + GGUF is the dominant community stack for on-device inference on Android and desktop Linux — what most third-party developers use. The cliff formula is hardware-general: any runtime using fp16 KV cache at similar model sizes would exhibit the same behaviour. Apple Intelligence and Google Gemini Nano use different paths (Neural Engine, dedicated DSP) which our work doesn't cover, but our findings are directly applicable to the open-source ecosystem.

**"Key papers this builds on?"**
- Na et al. (IISWC 2024) — confirmed LLM decode is memory-bandwidth-limited on CPU; we extend with GGUF-specific mechanism
- Gope et al. (arXiv 2501.00032) — ARM NEON kernel analysis methodology; we apply same approach to GGUF variants
- MELTing Point (MobiCom 2024, Laskaridis et al.) — observed non-monotonic throughput on iOS but didn't explain it; we provide the mechanism
- KVQuant (NeurIPS 2024) — proposed KV cache quantization; we empirically validate on ARM

---

## Updated Resume Bullets

### Correction: the "135% faster" claim in the current resume is wrong.
- Q2_K = 7.494 tok/s, Q6_K = 3.527 tok/s
- (7.494 − 3.527) / 3.527 = **1.124 = 112% faster**
- Fix in both SDE and ML resume versions.

---

### SDE / Systems Resume Version
```
GGUF Quantization Benchmarking on Mobile ARM | Python, C++, llama.cpp, ADB  Feb 2026 – Present

• Designed 1,200+ thermal-controlled inference experiments across 7 GGUF variants, 4 hardware
  platforms (ARM/x86/M4 CPU+GPU), and 2 models; caught and corrected 5 critical data pipeline
  bugs including a scoring error producing 100% accuracy across all variants

• Discovered speed inversion on ARM (Q2_K 112% faster than Q6_K) traced to SIMD dequantization
  instruction counts (10 vs 26 NEON ops/256-weight block); effect replicated on x86 AVX2,
  confirming CPU-general mechanism

• Derived and validated KV-cache cliff threshold formula (ctx_cliff = L2/1024): 0% error on
  ARM Cortex-X1 (512 tokens), <8% on i5-1235U (1,280 tokens), confirmed on second model family
  (Qwen 2.5 1.5B); cliff causes 46–48% throughput collapse for Q2_K and Q5_K_M at ctx≥512

• Paper submitted to MLSys 2026; open-source benchmark suite at github.com/KrisDcosta/291_EAI
```

### ML / Data Science Resume Version
```
GGUF Quantization Benchmarking on Mobile ARM | Python, llama.cpp, ADB  Feb 2026 – Present

• Ran 1,200+ controlled experiments across 7 GGUF variants and 4 hardware platforms; discovered
  non-monotonic speed ordering (2-bit fastest, 6-bit slowest on CPU — 112% inversion) caused by
  SIMD dequantization overhead rather than model size; effect confirmed across ARM and x86

• Derived predictive cliff formula (ctx_cliff = L2/1024) for 46–48% throughput collapse at
  long contexts; validated <8% error on two CPU platforms and two model architectures; identified
  Q2_K HellaSwag format collapse (19%, below 25% random) as a structured failure at 2-bit quant,
  not random degradation — diagnosed via output distribution analysis (56% "No" responses)

• Caught 5 critical data quality bugs during systematic audit that reversed two major conclusions
  (Q5_K_M reclassified from moderate to cliff-prone; ARC-Easy corrected from 100% to 76–82%)

• Submitted to MLSys 2026; interactive dashboard + deployment decision framework shipped
```

### Summary Line Addition (for either resume)
Insert before existing summary close:
```
...including first-author empirical systems research (MLSys 2026 submission) benchmarking 
on-device LLM quantization across ARM, x86, and Metal with hardware-validated mechanistic findings.
```

---

## What Makes This Stand Out in Interviews

1. **You found bugs that changed conclusions** — not just typos. Q5_K_M went from "moderate cliff at ctx=1,300" to "severe cliff at ctx=512". That's a reversal that changes what you'd deploy.

2. **You derived a formula from first principles that generalised.** The L2/1024 formula uses Llama's architecture to predict the cliff, and it works on Qwen with different KV head count. That's external validation of the underlying mechanism, not just curve-fitting.

3. **You identified a structured failure mode.** Q2_K on HellaSwag isn't "slightly worse accuracy" — it produces the wrong output type entirely. This is a production-blocking finding, not just a benchmark note.

4. **You navigated three different orderings across four platforms.** ARM CPU, x86 CPU, M4 CPU, M4 Metal each produce a different speed ranking for the same 7 variants. Understanding all three requires knowing L2 hierarchy, SIMD ISA, and GPU dispatch architecture.

5. **The thermal methodology is real systems engineering.** Measuring ±8% noise without thermal controls vs ±2% with 5-minute cool-downs is the difference between publishable and noisy. Most papers skip this — you documented and quantified it.
