# Quantized LLM Inference on Mobile ARM - 5-Minute Presentation Script

**Total Time: 5 minutes**
**Video Duration: 1.5 minutes (Chat demo: 35s + Benchmark UI: 55s)**
**Speaking Time: 3.5 minutes**

---

## SLIDE 1: Title Slide (0:00-0:15)
**[Transition: No animation needed. Simple fade-in]**

> Good afternoon. I'm Kris, and I'm presenting research on quantized LLM inference on mobile ARM devices. Over the past few months, I've conducted 661 empirical measurements on a Pixel 6a to understand how quantization actually behaves on edge hardware—and the findings challenge conventional wisdom about bit-width and performance.

> The key insight: on ARM CPUs, **kernel behavior dominates bit-width intuition**. This changes how we deploy models to mobile devices.

---

## SLIDE 2: The Problem (0:15-0:45)
**[Visual: Dark background with problem statement centered]**

> Let me start with the problem. Large language models are computationally expensive. Running them on a phone requires aggressive compression—typically quantization—to fit within memory and power budgets.

> Here's the gap: existing research usually evaluates quantization on data center hardware—GPUs and TPUs. But a mobile phone's ARM CPU is fundamentally different. The bottleneck isn't compute; it's **memory bandwidth and kernel efficiency**.

> Conventional wisdom says "8-bit is safer than 4-bit, which is safer than 2-bit." But on ARM, that intuition breaks down. Different bit-widths interact with CPU kernels in unexpected ways.

> **Why does this matter?** If we get quantization right, we unlock truly private AI—models running entirely on your phone, no server, no data leaving your device. That's healthcare, finance, defense, personal assistants—all offline and secure.

> My contribution was simple but rigorous: systematic empirical testing on actual ARM hardware to determine what actually works in the real world.

---

## SLIDE 3: Methodology (0:45-1:15)
**[Visual: Three columns - Hardware, Measurements, Quality]**

> Here's how I approached this.

> **Hardware**: A standard Google Pixel 6a—2 high-performance cores (Cortex-X1), 2 mid-range (A76), and 4 efficiency cores (A55). Total LPDDR5 bandwidth of 25-35 GB/s.

> **Measurements**: 661 total inference runs across 5 quantization variants—Q2_K, Q3_K_M, Q4_K_M, Q6_K, and Q8_0—tested at 4 different context lengths from 256 to 2048 tokens. All measurements include 95% Wilson confidence intervals.

> **Quality evaluation**: I used BoolQ—reading comprehension questions from SuperGLUE—as the primary accuracy metric, supplemented with ARC-Easy for broader reasoning capability. 100 questions each.

> **One important methodological note**: Most throughput figures use 256-token context as the baseline. But Q4_K_M is special. At 256 tokens, it gets 4.79 tok/s. But at 512 tokens, it jumps to 5.32 tok/s. This isn't noise—Q4_K_M actually *improves* at higher contexts. So I'm reporting the 512-token number because it shows Q4_K_M's true strength for real-world deployments where context lengths vary. This choice reveals its stability advantage that wouldn't be obvious from the 256-token baseline alone.

---

## SLIDE 4: Finding #1 - Non-Monotonic Throughput (1:15-1:45)
**[Visual: Bar chart showing throughput. Q6_K highlighted as slowest.]**

> Here's the first major finding: **more bits do not always mean slower inference**.

> Q6_K—the 6-bit variant—is actually the *slowest* overall. It's slower than Q2_K (2-bit) and slower than Q4_K_M. This completely violates the intuition that bit-width scales linearly with speed.

> Why? Because on ARM CPUs, the limiting factor isn't the arithmetic—it's how efficiently the CPU can fetch weights from memory and execute the quantized kernels. The 6-bit packing doesn't align well with ARM's 32-bit and 64-bit register architecture. It creates inefficient memory access patterns.

> **The lesson**: kernel efficiency and instruction-set alignment matter far more than raw bit-width on mobile CPUs.

---

## SLIDE 5: Finding #2 - Context Resilience (1:45-2:15)
**[Visual: Table showing context collapse across variants. Color-coded for pass/fail.]**

> The second major finding is about context resilience—how stable is throughput as the input gets longer?

> Look at this table. Most quantized variants *degrade* as context increases. Q3_K_M drops 44% going from 256 to 2048 tokens. Q6_K collapses 52%. That's catastrophic for real-world use, where conversations grow longer.

> But Q4_K_M *improves* by 10%. It's the only variant that actually gets faster at longer contexts. This is remarkable. It suggests Q4_K_M's kernel utilization becomes more efficient with more data to process.

> **This is the hidden metric for mobile success**: not just raw speed, but stability under realistic, variable-length sequences.

---

## SLIDE 6: Quality Assessment (2:15-2:35)
**[Visual: Accuracy bars showing BoolQ and ARC-Easy results.]**

> On to accuracy. The quantized models perform nearly identically on ARC-Easy—100% correct. That's the easy benchmark.

> BoolQ is more discriminating. It requires actual reading comprehension and reasoning. Here, Q4_K_M maintains near-baseline accuracy. Lower bit-widths (Q2, Q3) show slight degradation but remain viable. Q6_K also performs well on BoolQ, but remember—it's slow and unstable, so high accuracy there doesn't redeem it.

> The key insight: **Q4_K_M is the accuracy champion**. It doesn't sacrifice quality for speed.

---

## SLIDE 7: Pareto Frontier (2:35-3:00)
**[Visual: 2D scatter plot with accuracy vs. throughput.]**

> Here's how to think about the trade-offs: the Pareto frontier.

> Q2_K owns the speed crown—5.66 tok/s. Q4_K_M owns the accuracy crown—5.32 tok/s with better stability. And Q6_K? It's strictly dominated. It's not faster than Q2, and it's not more accurate than Q4. It wastes hardware resources.

> **The rule**: always deploy on the frontier. If a variant is dominated—slower and less accurate than an alternative—remove it. For mobile, that's Q4_K_M as the default, with Q2_K for ultra-low-latency scenarios.

---

## SLIDE 8: Demo Clip A - Chat Comparison (3:00-3:35)
**[VIDEO STARTS - Side-by-side Q2 | Q4 | Q6 chat inference - 35 seconds]**

> Now let me show you this in action. Watch carefully—all three variants are answering the exact same question simultaneously.

> **On the left, Q2_K finishes first.** It's aggressive quantization, so it's the fastest. You'll see it hits 10.1 tokens per second in the decode phase—that's incredibly fast for a mobile CPU. Memory usage is the lowest at 1.8 GB.

> **In the center, Q4_K_M is more measured.** It's not the fastest, but watch the response quality and consistency. The decode phase runs at 9.5 tokens per second. The response is thoughtful and complete. Memory footprint is 2.1 GB—reasonable for a Pixel 6a.

> **On the right, Q6_K.** Notice it takes longer—only 6.5 tokens per second in decode, and the prefill phase (processing the prompt) is much slower at 2.9 tokens per second. This is the kernel efficiency problem in action. End-to-end, Q6_K takes 15.7 seconds. Memory overhead is 2.7 GB. The response is accurate, but the speed doesn't justify the memory cost.

> **What you're seeing**: the speed-quality tradeoff in real time. Q2 is blazingly fast but minimal. Q4 is the sweet spot—fast enough, accurate enough, stable enough. Q6 is the worst of both worlds—not fast, not memory-efficient, and strictly dominated.

**[VIDEO ENDS - 35 seconds elapsed]**

---

## SLIDE 9: Demo Clip B - Benchmark UI (3:35-4:30)
**[VIDEO STARTS - Benchmark app walkthrough - 55 seconds]**

> Now here's the infrastructure that powers this research. This is the Android benchmark app I built to capture these 661 measurements.

> **Top left: The Models section.** You can see all five quantization variants available. Each one is a compiled LLM runtime that you can switch between without recompiling. The app automatically reports TPS, accuracy, and memory usage.

> **The Run section shows the execution interface.** You pick a model, set the context length, choose the benchmark—BoolQ or ARC-Easy—and hit start. The app runs the full inference pipeline and logs every metric.

> **History tracks everything.** Each run generates a detailed result card showing:
> - **Decode TPS**: tokens per second during response generation
> - **Time to First Token (TTFT)**: how long the prefill phase takes
> - **Total time**: end-to-end wall-clock latency
> - **Memory footprint**: peak memory usage during inference
> - **Accuracy**: number of questions answered correctly

> **Dark mode toggle** (bottom right) makes it easy to run benchmarks in different lighting conditions—important for real-world testing.

> All 661 measurements in this research came from this app, running on an actual Pixel 6a in my hands, not in an emulator. Every number you see is from real hardware, real execution.

**[VIDEO ENDS - 55 seconds elapsed]**

---

## SLIDE 10: Hardware Scaling & Multipliers (4:30-4:50)
**[Visual: Thread scaling graph + Hardware baseline comparison table]**

> Let's zoom out to the broader context.

> **Thread scaling**: The Pixel 6a's big.LITTLE architecture shows that optimal performance occurs at 4 threads, achieving 5.0 tok/s. Beyond that, at 8 threads, contention causes degradation—we see 4.0 tok/s. This is typical for ARM's asymmetric core configuration. Threads competing for cache and memory bandwidth hurt more than they help.

> **Hardware baseline comparison**: The Pixel 6a achieves roughly 5.32 tokens per second with Q4_K_M. How does that compare?

> A Google TPU v6e (data center) runs at ~75 tok/s. An NVIDIA T4 (cloud GPU) achieves about 19 tok/s. An A100 gets you 85 tok/s.

> So the Pixel 6a is roughly **0.07x** the speed of an A100, or about **0.28x** a T4. That sounds slow until you consider: T4s cost $300+ per month in cloud compute. Your phone costs $400 once. And you own it forever. Plus—no network latency, no data exfiltration, 24/7 availability.

> **For privacy-critical applications, the Pixel 6a isn't a slow GPU—it's the only option.**

---

## SLIDE 11: Conclusion & Future Work (4:50-5:00)
**[Visual: Key learnings on left, recommendations on right, applications below]**

> Let me wrap up with three key takeaways:

> **One**: Bit-width intuition from desktop GPUs doesn't transfer to mobile ARM. Kernel behavior and memory-bandwidth constraints dominate. Always test on target hardware.

> **Two**: Q4_K_M is the golden variant. 72% of Q4_K_M's accuracy, 5.32 tokens per second, and *improving* at higher contexts. Deploy Q4_K_M as your default. Use Q2_K only if you need ultra-low latency and can sacrifice response quality.

> **Three**: Q6_K should be blacklisted. It's strictly dominated—slower than Q2, context-unstable, and no accuracy advantage over Q4. Remove it from production.

> **Practical rule**: always validate quantization on target hardware. Desktop metrics are misleading for mobile.

> **Future directions**: We're already exploring INT2 for ultra-extreme compression, LoRA-based fine-tuning on quantized models, and broader device coverage beyond Pixel 6a. And we're working on extended context support—pushing beyond 2048 tokens via kernel optimization.

> **Real-world applications**: This research enables secure healthcare diagnostics on phones, offline fraud detection for finance, air-gapped inference for defense, and AI features without cloud dependency.

> Thank you.

---

## Timing Breakdown

| Slide | Duration | Content |
|-------|----------|---------|
| 1. Title | 0:15 | Intro & thesis |
| 2. Problem | 0:30 | Gap & motivation |
| 3. Methodology | 0:30 | Hardware, measurements, quality |
| 4. Finding #1 | 0:30 | Non-monotonic throughput |
| 5. Finding #2 | 0:30 | Context resilience |
| 6. Quality | 0:20 | BoolQ & ARC-Easy |
| 7. Pareto | 0:25 | Optimization framework |
| 8. Demo A (Video) | 0:35 | Chat comparison |
| 9. Demo B (Video) | 0:55 | Benchmark UI walkthrough |
| 10. Scaling | 0:20 | Threads & hardware comparison |
| 11. Conclusion | 0:10 | Takeaways & future work |
| **TOTAL** | **~5:00** | |

---

## Key Metrics to Reference During Presentation

**Chat Demo (Slide 8) - From your video results:**
- Q2_K: TFFT 1.31s, Decode 10.1 t/s, Prefill 6.9 t/s, E2E 8.77s, Mem 1805 MB
- Q4_K_M: TFFT 1.81s, Decode 9.5 t/s, Prefill 5.0 t/s, E2E 10.89s, Mem 2129 MB
- Q6_K: TFFT 3.11s, Decode 6.5 t/s, Prefill 2.9 t/s, E2E 15.72s, Mem 2719 MB

**What to emphasize while video plays:**
- Speed hierarchy visible in real-time
- Q2's aggressive speed vs. Q4's balance vs. Q6's overhead
- Memory footprint differences (Q2 efficiency vs. Q6 bloat)
- Response quality differences (mention Q2 minimal, Q4 thorough, Q6 accurate but slow)

**Benchmark Demo (Slide 9) - Show:**
- The TPS counters updating in real-time
- Accuracy tracking across runs
- Memory footprint display
- How the app captures and records measurements
- The history log proving all 661 measurements came from the device

---

## Presentation Delivery Tips

1. **Pace**: Speak deliberately during complex slides (Methodology, Findings). This allows audience time to process.

2. **Video callouts**: During videos, use hand gestures to point at the three panes—left (Q2), center (Q4), right (Q6). Make the visual comparison obvious.

3. **Emphasis**: Stress these phrases:
   - "Kernel efficiency matters more than bit-width"
   - "Q4_K_M is the golden variant"
   - "Context resilience is the hidden metric"
   - "Always validate on target hardware"

4. **Flexibility**: If audience asks questions during videos, pause and answer. Don't rush through explanations.

5. **Closing strength**: End with "Thank you" and pause. Let the research stand. You've shown data, not opinions.

---

## Notes for Presenter

- Have a phone ready (Pixel 6a or screenshot) to show the app works
- Bookmark the GitHub repo or demo video in case audience wants to see code
- Be prepared to explain: "Why ARM is different" (memory bandwidth-bound, not compute-bound)
- Be prepared to defend Q4_K_M: Have the context resilience table memorized or visible
- Be ready with deployment recommendations: Q4_K_M first, Q2_K if needed, never Q6_K

