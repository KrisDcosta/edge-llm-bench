# Canonical Llama 3.2 3B Cliff Dataset — n=10 trials
## Source directories
- Q2_K, Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q8_0: results/pixel_llama_cliff_filled_20260329_162354/
- Q6_K: results/pixel_llama_cliff_filled_20260330_212946/  (CLEAN solo re-run)

## Why Q6_K was re-run
The 20260329 Q6_K run was contaminated by a background llama-perplexity process
on the device (orphaned from the WikiText PPL sweep). This caused Q6_K to show
+113% "improvement" from ctx=256→2048, which is physically impossible.
The clean solo run (20260330) shows the correct -10.6% mild degradation.

## Contamination corrections (2026-03-31)
- Q4_K_M n=10 (20260329): EXCLUDED — thermal recovery artifact.
  Device cooled overnight; ctx=1800-2048 trials are 35% faster than ctx=256.
  Used n=3 original (20260326) which shows correct stable -6.6% behaviour.
- Q5_K_M n=10 (20260329): EXCLUDED — Qwen parallel contamination.
  llama-perplexity and pixel_qwen_cliff_filled ran concurrently starting ~12:49 AM.
  ctx=1500+ crashed to 1.6 t/s (vs clean -26% in n=3 original).
  Used n=3 original (20260326).
