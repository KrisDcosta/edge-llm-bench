# Pixel 6a WikiText-2 PPL Benchmark Status

**Backup Created:** 2026-03-17 03:52 UTC  
**Backup Location:** `/Users/krisdcosta/291_EAI/results/pixel_6a_ppl_backup_20260317_035205/`  
**Total Time Invested:** ~2 days

---

## Results Summary

### ✅ COMPLETE (Ready for Paper)
| Variant | File Size | Chunks Processed | Status |
|---------|-----------|------------------|--------|
| Q2_K | 20K | 568/568 | DONE - Mar 08 |
| Q3_K_M | 20K | 568/568 | DONE - Mar 09 |
| Q4_K_M | 20K | 568/568 | DONE - Mar 16 |
| Q5_K_M | 20K | 568/568 | DONE - Mar 16 |

### ⚠️ INCOMPLETE (Need to Resume)
| Variant | File Size | Chunks Processed | Issue |
|---------|-----------|------------------|-------|
| Q4_K_S | 12K | ~1-10 | Stopped at initialization (Mar 17 03:39) |
| Q6_K | 12K | ~1-10 | Stopped early (Mar 17 03:46) |

### ❌ NOT STARTED
| Variant | Status |
|---------|--------|
| Q8_0 | Queued for next run |

---

## What's in the Backup
```
ppl_full_Q2_K.txt     ✅ Complete PPL values for 568 chunks
ppl_full_Q3_K_M.txt   ✅ Complete PPL values for 568 chunks
ppl_full_Q4_K_M.txt   ✅ Complete PPL values for 568 chunks
ppl_full_Q4_K_S.txt   ⚠️ Partial (8-9 chunks only)
ppl_full_Q5_K_M.txt   ✅ Complete PPL values for 568 chunks
ppl_full_Q6_K.txt     ⚠️ Partial (4-5 chunks only)
```

---

## Next Steps

### Priority 1: Resume Q4_K_S & Q6_K
These are close to completion and should be finished ASAP:
```bash
# On Pixel device via adb shell:
LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/llama-perplexity \
  -m /data/local/tmp/Llama-3.2-3B-Instruct-Q4_K_S.gguf \
  -f /data/local/tmp/wikitext2_full.txt \
  --ctx-size 512 \
  -t 4 \
  2>&1 | tee /data/local/tmp/ppl_full_Q4_K_S.txt

# Then Q6_K (already has partial results)
LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/llama-perplexity \
  -m /data/local/tmp/Llama-3.2-3B-Instruct-Q6_K.gguf \
  -f /data/local/tmp/wikitext2_full.txt \
  --ctx-size 512 \
  -t 4 \
  2>&1 | tee /data/local/tmp/ppl_full_Q6_K.txt
```

### Priority 2: Run Q8_0
Once Q6_K finishes:
```bash
LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/llama-perplexity \
  -m /data/local/tmp/Llama-3.2-3B-Instruct-Q8_0.gguf \
  -f /data/local/tmp/wikitext2_full.txt \
  --ctx-size 512 \
  -t 4 \
  2>&1 | tee /data/local/tmp/ppl_full_Q8_0.txt
```

### Priority 3: Paper Integration
Once all 7 variants complete, run:
```bash
python3 ~/291_EAI/scripts/parse_ppl_full.py \
  ~/291_EAI/results/pixel_6a_ppl_backup_20260317_035205/ \
  --output ~/291_EAI/results/ppl_final_table.json
```

---

## Checksum Verification
```
dc3bbb0e167ce94a7acb70c99665ad77  ppl_full_Q2_K.txt
c3530bd2a009016fb13f477a4670d6b0  ppl_full_Q3_K_M.txt
88a08d06e76d7ec4d1d7efca4046ecdf  ppl_full_Q4_K_M.txt
f1a88399a545a02bb46fb5df330e11a1  ppl_full_Q4_K_S.txt
ad0dd82fc940c8c6ace03fcc60ae9c7b  ppl_full_Q5_K_M.txt
34838867ba1740d8cc8070b4f1da0fbf  ppl_full_Q6_K.txt
```

Verify with: `md5sum -c ~/291_EAI/results/_checksums.txt`

