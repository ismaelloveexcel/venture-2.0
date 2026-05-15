# Phase 0 → Phase 2: Execution Reference

## Current State

```
PHASE: SHADOW OBSERVATION ACTIVE
MODE: Dual v2 + v3 routing (parallel evaluation)
BASELINE: FROZEN (immutable)
DECISION: PENDING (statistical validation in progress)
```

---

## Phase 0: Baseline Freeze (✅ COMPLETE)

Freezes statistical distributions from shadow logs. **Run once before Phase 2.**

```bash
cd "c:\Users\isuda\Dev\VENTURE 2.0"
python 04-coding/scripts/phase0_freeze_baselines.py
```

### Output
- **File:** `06-sales/baseline_distributions.json`
- **Contents:** Frozen v2 and v3 score distributions with percentile buckets
- **Safety:** Rejects overwrites; delete manually to reset

### Baseline Stats (Current)
| Metric | V2 Motion | V3 CIS |
|--------|-----------|--------|
| Count | 15 | 15 |
| Mean | 47 | 30 |
| Min | 40 | 28 |
| Max | 60 | 35 |
| p50 | 50 | 30 |

---

## Phase 2: Shadow Mode (✅ ACTIVE)

Runs daily/weekly with frozen baselines. Measures v2 vs v3 alignment without changing production routing.

### Daily Shadow Run

```bash
cd "c:\Users\isuda\Dev\VENTURE 2.0"

# Generate shadow logs with v2/v3 parallel scoring
python 04-coding/scripts/credibility_candidate_generator.py \
  --input 06-sales/credibility-launch-signal-lab.csv \
  --shadow-mode \
  --replace

# Generate dashboard + decision metrics
python 04-coding/scripts/shadow_drift_tracker.py
```

### Output Files
- `06-sales/shadow_decisions.jsonl` — v2 + v3 routing decisions (appended each run)
- `06-sales/experiment_dashboard.json` — Latest metrics + recommendation

### Dashboard Metrics

```json
{
  "phase": "SHADOW OBSERVATION ACTIVE",
  "decision_status": "INCONCLUSIVE | PASS | FAIL",
  "recommendation": "CONTINUE_SHADOW | MODIFY_MODEL | CUTOVER",
  "metrics": {
    "avg_percentile_drift": <float>,           // Current: 15%
    "top_20_percent_overlap_rate": <float>,    // Current: 0%
    "hot_overlap_rate": <float>,               // Current: 0%
    "possible_overlap_rate": <float>,          // Current: 0%
    "variant_purity_score": <float>,           // Current: 60%
    "discard_rate_v2": <float>,
    "discard_rate_v3": <float>,
    "systematic_bias": <bool>,
    "distribution_shift": <bool>
  },
  "records_evaluated": <int>,
  "baseline_frozen_at": "<timestamp>"
}
```

### Success Criteria (Phase 2 → Phase 3)

**PASS (cutover allowed):**
- Percentile drift < 15%
- Top 20% overlap > 70%
- Variant purity ≥ 80%
- No systematic bias in top decile
- No distribution shift > 20%

**INCONCLUSIVE (continue shadow):**
- Metrics between success and fail thresholds
- Recommendation: gather more data

**FAIL (modify model):**
- Percentile drift > 25%
- HOT collapse > 30%
- Top decile inversion detected

---

## Phase 2 Safety Constraints

✅ **Frozen baselines never update** — Re-run Phase 0 creates new file only if none exists  
✅ **v2 logic never changes** — Shadow mode observation only  
✅ **No production routing changes** — All decisions logged, none acted upon  
✅ **Backward compatible** — All v3 data in shadow logs, no schema breaks  
✅ **Autonomous decision gate required** — Operator must review before Phase 3 cutover

---

## Phase 3: Decision Gate (⏳ PENDING)

When Phase 2 metrics pass success criteria:

```bash
# Manual step: Review dashboard
cat 06-sales/experiment_dashboard.json | python -m json.tool

# If decision_status == "PASS":
# 1. Update .env: CIS_ROUTING_MODE=v3_only
# 2. Re-run generator (v3 goes live)
# 3. Monitor 3 days for regressions
# 4. Archive v2 logic (optional)
```

---

## Troubleshooting

### Error: "BASELINE DISTRIBUTIONS NOT FROZEN"
**Cause:** Phase 0 was skipped; Phase 2 requires frozen baselines  
**Fix:** Run Phase 0 first
```bash
python 04-coding/scripts/phase0_freeze_baselines.py
```

### Error: "FileNotFoundError: baseline_distributions.json"
**Same as above**

### Phase 2 metrics not updating
**Cause:** Generator appends to shadow logs; old logs may have stale data  
**Fix:** Check file timestamps
```bash
ls -la 06-sales/shadow_decisions.jsonl 06-sales/baseline_distributions.json
```

### Baseline file won't reset
**Cause:** Phase 0 detects existing file, refuses overwrite  
**Fix:** Delete manually
```bash
rm 06-sales/baseline_distributions.json
python 04-coding/scripts/phase0_freeze_baselines.py
```

---

## Timeline

| Phase | Start | Duration | Status |
|-------|-------|----------|--------|
| Phase 1 | 2026-05-10 | ~30 min | ✅ COMPLETE |
| Phase 0 | 2026-05-10 | ~5 min | ✅ COMPLETE |
| Phase 2 | 2026-05-10 | 7-14 days | ✅ ACTIVE |
| Phase 3 | TBD | 3 days | ⏳ PENDING |

**Phase 2 Recommendation:** Run shadow mode for 7-14 days to collect sufficient data for statistical validity (current: 10-15 records, target: 50+ for robust percentile comparison).

---

## References

- Implementation: [04-coding/venture-implementation-notes.md](../venture-implementation-notes.md)
- V3 Architecture: [08-prompts/VENTURE_2_FULL_AUDIT_PROMPT.md](../../08-prompts/VENTURE_2_FULL_AUDIT_PROMPT.md)
- Code: `credibility_candidate_generator.py`, `phase0_freeze_baselines.py`, `shadow_drift_tracker.py`
