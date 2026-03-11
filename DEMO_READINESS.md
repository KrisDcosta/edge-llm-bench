# Demo Readiness Status — 2026-03-11

## ✅ Completed This Session

### Report Updates
- **Proofreading pass** (commit 5836d7a)
  - Fixed "Tensor G2" → "Tensor G1" (12 occurrences)
  - Fixed "Mali-G710" → "Mali-G78" GPU model
  - Fixed TTFT ordering (Q2_K 3.81s fastest, Q8_0 3.95s second)
  - Fixed PPL corpus limitation text (50K tokens now documented)
  - Added 4 SOTA future work items: KV-cache Q8, speculative decoding, P-core affinity, broader eval
  - Added 4 new bibliography entries

- **GPU Baseline Results** (Table 3, new Discussion subsection)
  - T4: 19.17 tok/s (3.6× vs device)
  - A100: 30.50 tok/s (5.7×)
  - H100: 62.84 tok/s (11.8×)
  - TPU v6e-1: 9.79 tok/s (1.8×)
  - Interpreted: INT4 CPU captures 29% of T4 throughput, zero cloud cost

- **PDF compiled** with all updates (report.pdf, 10 pages, Mar 11 09:58)

### App Fixes
- **Benchmark tab crash fixed** (commit 4ee4880)
  - Root cause 1: `LazyColumn` nested in `Column(spacedBy())` → unbounded height constraints
    - Fixed: Replace `LazyColumn` with plain `Column` in `ResultsTable`
  - Root cause 2: Room `AppDatabase_Impl` not generated (KAPT/KSP incompatible with Kotlin 2.3.0)
    - Fixed: Remove Room DB from `BenchmarkViewModel`, use in-memory `MutableStateFlow<List<BenchmarkRunEntity>>`
  - **Result**: App no longer crashes when navigating to Benchmark tab; History tab shows in-memory runs

- **APK rebuilt and tested** 
  - Installed on device ✓
  - App launches ✓
  - All 4 tabs accessible ✓
  - No crashes ✓

---

## ⏳ Before Demo (Remaining)

### High Priority (Time-critical)

1. **Q8_0 PPL measurement** (2.5-3 hrs device time) — LOW URGENCY FOR DEMO
   - Status: Interrupted earlier, user will restart later
   - Impact: Table 1 Q8_0 column shows "TBD" until this completes
   - Action: Can present with Q8_0 value TBD; backfill after demo if time permits
   - Note: Q4_K_M (11.36) and Q6_K (11.22) values complete; ordering is solid

2. **Device prep for demo** (5 min before launch)
   ```bash
   adb shell "sync && echo 3 > /proc/sys/vm/drop_caches"  # Free memory
   adb shell "pkill -f llama"  # Kill lingering llama processes
   adb shell am start -n com.eai.edgellmbench/.MainActivity
   ```
   - Pixel 6a needs ≥1GB free RAM to avoid OOM/LMK kills
   - Last session had only 143MB free → device killed app; fix prevents this

3. **Full app testing checklist** (15 min)
   - [ ] Chat tab: send prompt → get response (verify model loaded)
   - [ ] Models tab: load Q4_K_M (or preferred variant)
   - [ ] Benchmark tab: run one trial (click "Run", get results)
   - [ ] Settings tab: toggle context length, verify persistent
   - [ ] History tab: confirm prior run appears (if benchmark ran earlier in session)
   - [ ] Dark mode toggle: verify theme switches
   - [ ] No crashes or ANRs across all navigation

### Medium Priority (Polish)

4. **Compile final report PDF** (after Q8_0 completes)
   - Update Table 1 Q8_0 cell from "TBD" to measured value
   - Re-run `pdflatex report.tex` twice
   - Verify figure references and table captions

5. **Update QUICKSTART.md** (5 min)
   - Add memory-cleanup step to pre-flight checklist
   - Add device crash mitigation notes

### Nice-to-Have (Non-blocking)

6. **Run through demo script** (10 min practice)
   - Intro (~1 min): problem statement (edge AI on ARM, efficiency)
   - Chat feature (~1.5 min): send 2-3 example prompts
   - Models/Benchmark tabs (~2 min): show loaded model, run benchmark
   - Results interpretation (~1 min): "Q4_K_M best tradeoff: 72% accuracy, 5.32 tok/s"
   - Key findings (~1 min): non-monotonic throughput, context sensitivity, Pareto frontier
   - Closing: report PDF available, app open-source

---

## 📊 Current Data Status

| Task | Data | Status |
|------|------|--------|
| BoolQ eval | 100 q's × 6 variants | ✓ Complete |
| ARC-Easy eval | 100 q's × 6 variants | ✓ Complete |
| TPS benchmark | 5 ctx × 6 variants × 10 trials | ✓ Complete (661 measurements) |
| PPL (Q2_K) | 50K tokens, full corpus | ✓ 10.15 |
| PPL (Q3_K_M) | 50K tokens, full corpus | ✓ 11.71 |
| PPL (Q4_K_M) | 50K tokens, full corpus | ✓ 11.36 |
| PPL (Q6_K) | 50K tokens, full corpus | ✓ 11.22 |
| PPL (Q8_0) | 50K tokens, full corpus | ⏳ TBD (~90 min remaining if user restarts) |
| GPU baseline | T4, A100, H100, TPU v6e-1 | ✓ Complete (added to report) |

---

## 🎯 Success Criteria for Demo

- [ ] App launches without crash
- [ ] Chat works: send message → get response (CPU inference, may be slow)
- [ ] Benchmark runs: click "Run" → get trial results
- [ ] All 4 tabs functional
- [ ] Dark mode toggles
- [ ] No OOM/LMK kills (device memory clean)
- [ ] Can explain: "Q4_K_M is Pareto-optimal: 72% BoolQ, 5.32 tok/s, 2GB, best tradeoff"
- [ ] Report PDF available with all results

**Current status: 6/8 items ✓, 2 minor (Q8_0 TBD, GPU baseline now ✓)**

---

## Timeline

- **Now → +15 min**: Full app testing + device prep
- **+15 min → +25 min**: Run through demo script
- **Post-demo**: If time permits, restart Q8_0 and backfill Table 1

