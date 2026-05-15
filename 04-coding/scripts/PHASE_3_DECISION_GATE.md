# Phase 3: Final Decision Gate

**Purpose:** Locked criteria for v3 CIS cutover to production routing.

**Status:** Pending — requires Phase 2 validation + stress testing.

---

## Cutover Checklist (All Must Pass)

```
✅ REQUIRED (non-negotiable)

□ spearman >= 0.7
  Evidence: 06-sales/experiment_dashboard.json → metrics.spearman_rank_correlation
  Why: Ranking alignment strong enough for production routing decisions

□ collapse_ratio >= 0.7
  Evidence: 06-sales/experiment_dashboard.json → metrics.distribution_collapse_ratio
  Why: V3 distribution not compressed relative to v2; percentiles stable

□ drift <= 15%
  Evidence: 06-sales/experiment_dashboard.json → metrics.avg_percentile_drift
  Why: v2 and v3 agree on ranking movement magnitude

□ variant_purity >= 0.8
  Evidence: 06-sales/experiment_dashboard.json → metrics.variant_purity_score
  Why: Experimental design maintained; learning signal not contaminated

□ sample_size >= 50
  Evidence: 06-sales/experiment_dashboard.json → records_evaluated
  Why: Statistical power threshold for valid inference (7-14 days of daily runs)

□ no_systematic_bias
  Evidence: 06-sales/experiment_dashboard.json → metrics.systematic_bias = false
  Why: Top decile ranking stable (no inversion)

□ no_distribution_shift > 20%
  Evidence: 06-sales/experiment_dashboard.json → metrics.distribution_shift = false
  Why: Baseline stability maintained throughout observation period
```

---

## Decision Logic

### If ALL criteria pass:
```
decision_status = PASS
→ Proceed to Phase 3 (controlled cutover)

Steps:
1. Review experiment_dashboard.json reasons + metrics
2. Update .env: CIS_ROUTING_MODE=v3_only
3. Re-run generator: v3 routing goes live
4. Monitor 3 days: reply rates, discard rates, variant performance
5. If regression >10%: rollback to dual_shadow and investigate
6. If stable: archive v2 logic (optional)
```

### If ANY criterion fails:
```
decision_status = FAIL
→ NO CUTOVER. Model modification required.

Investigation:
- If collapse_ratio < 0.7: Check CIS score distribution compression
- If spearman < 0.7: Check for ranking inversions in scoring logic
- If drift > 15%: Check for weight rebalancing issues
- If variant_purity < 0.8: Check variant assignment logic
- If bias detected: Check percentile bucket alignment

Action:
1. Identify root cause
2. Adjust CIS weights (spend_weight, motion_weight, etc.)
3. Re-run Phase 0 (freeze new baselines)
4. Re-run Phase 2 (fresh observation)
5. Repeat until criteria met or abandon v3
```

---

## Stress-Test Validation (Before Cutover)

Before Phase 3, run stress test to validate under pressure:

```bash
python 04-coding/scripts/credibility_candidate_generator.py \
  --input 06-sales/stress-test-cohort.csv \
  --shadow-mode \
  --replace --append

python 04-coding/scripts/shadow_drift_tracker.py
```

**Expected:** Spearman stable (≥ 0.6), collapse_ratio unchanged  
**If fails:** CIS reweighting logic broken; modify and retry

---

## NO OVERRIDE ALLOWED

These criteria are **non-negotiable**. Exception approval requires:
- Root cause analysis documented
- Manual review of top 100 candidates (v2 vs v3 ranking)
- Sign-off from business stakeholder

---

## Current State

```
Phase: SHADOW OBSERVATION ACTIVE
Decision Status: INCONCLUSIVE
Recommendation: CONTINUE_SHADOW (accumulate data)

Metrics (as of 2026-05-10T18:05:20Z):
  spearman: 1.0 ✅ (excellent, but small sample)
  collapse_ratio: 1.0 ✅ (healthy)
  drift: 7.6% ✅ (excellent)
  variant_purity: 100.0% ✅ (perfect)
  sample_size: 5 ❌ (insufficient; need 50+)
  
Timeline: 7-14 days (daily Phase 2 runs)
Next milestone: Stress-test cohort validation
```

---

## Post-Cutover Monitoring (Phase 3a)

**Duration:** 3 days after cutover

**Watch for:**
- Reply rate changes (baseline: track from v2 period)
- Discard rate increase >10%
- Variant performance divergence
- Top 20 candidate agreement with v2

**Automatic rollback trigger:**
- Reply rate drops >10% → revert to dual_shadow
- Discard rate spike >15% → revert to dual_shadow
- Top 20 ranking divergence >30% → revert to dual_shadow

---

## Archive Decision (Phase 3b)

**Timing:** After 7-14 days of stable v3 routing

**Decision:** Keep or remove v2 logic?

**Option A: Archive v2**
- Simplify code (remove motion_score computation)
- Reduce tech debt
- Commit: "v3 CIS production; v2 legacy archived"

**Option B: Keep Dual Mode**
- Maintain fallback capability
- Continue running v2 in shadow for comparison
- Commit: "v3 CIS production; v2 shadow enabled"

**Recommendation:** Archive only after 30 days of stable v3 performance.

---

## Related Documents

- [PHASE_2_OPERATING_RUNBOOK.py](PHASE_2_OPERATING_RUNBOOK.py) — Daily checklist + interpretation rules
- [PHASE_2_CORRECTIONS.md](PHASE_2_CORRECTIONS.md) — Statistical fixes applied
- [06-sales/stress-test-cohort.csv](../06-sales/stress-test-cohort.csv) — Adversarial test candidates
