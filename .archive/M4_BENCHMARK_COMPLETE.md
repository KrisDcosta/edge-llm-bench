# M4 Mac GPU Benchmark - COMPLETE ✅

**Completion Time:** 2026-03-17 08:48 UTC  
**Total Duration:** ~2.5 hours  
**Status:** 420/420 runs (100%) ✅

---

## Data Summary

| Metric | Value |
|--------|-------|
| **Files Generated** | 28 / 28 ✓ |
| **Total Records** | 420 / 420 ✓ |
| **Total Data Size** | 12 GB |
| **Backend** | Metal GPU (M4 Mac) |
| **Model** | Llama-3.2-3B-Instruct |

---

## Quantization Variants (7)

✅ Q2_K (~2.6 bits)  
✅ Q3_K_M (~3.4 bits)  
✅ Q4_K_S (~4.4 bits)  
✅ Q4_K_M (~4.8 bits)  
✅ Q5_K_M (~5.7 bits)  
✅ Q6_K (~6.6 bits)  
✅ Q8_0 (~8.5 bits)

---

## Context Lengths (4)

✅ 256 tokens  
✅ 512 tokens  
✅ 1024 tokens  
✅ 2048 tokens

---

## Sample Results

### TPS Performance (Generation Speed)

**Q2_K ctx256:** 63.4 t/s  
*Expected Metal ordering: Monotonic increase with bit precision*

---

## Files Location

```
~/291_EAI/results/m4_mac_metal_20260317_035638/

m4_Q2_K_ctx256.jsonl      (15 trials)
m4_Q2_K_ctx512.jsonl      (15 trials)
m4_Q2_K_ctx1024.jsonl     (15 trials)
m4_Q2_K_ctx2048.jsonl     (15 trials)
... (similar for Q3_K_M, Q4_K_S, Q4_K_M, Q5_K_M, Q6_K, Q8_0)
```

---

## Next Steps

1. **Analysis Script**
   ```bash
   python3 ~/291_EAI/analysis/generate_figures.py \
     ~/291_EAI/results/m4_mac_metal_20260317_035638/
   ```

2. **Extract Key Metrics**
   - Throughput by variant
   - KV-cache collapse detection
   - Metal GPU vs expected performance

3. **Integration with Paper**
   - Figure 1-3: Throughput/collapse plots
   - Cross-device comparison (Pixel 6a + M4)

---

## Data Integrity ✅

- All 28 files present
- TPS values properly extracted
- JSON structure valid
- Raw output captured (system info + inference output)

---

## Ready for: 
- ✅ Throughput analysis
- ✅ Cross-device comparison (vs Pixel 6a ARM)
- ✅ Paper integration
