# V3 ARCHITECTURE PATCHES (Applied Before Code Implementation)

**Date:** May 10, 2026  
**Status:** Pre-execution validation complete  
**Reason:** Transition from "heuristic routing system" to "measurement system for causal experimentation"

---

## PATCH 1: Motion–Spend Dependency via Reweighting (Not Clipping)

### Problem Identified
Clipping motion_score when spend is low destroys distribution shape, invalidating later percentile comparison.

### Fix Applied
Replace clipping with **conditional reweighting**:

```python
if spend_score < 40:
    motion_weight = 0.25      # reduce from 0.40
    spend_weight = 0.45       # increase from 0.30
else:
    motion_weight = 0.40      # standard
    spend_weight = 0.30       # standard
```

### Why This Matters
- Preserves distribution shape (percentiles remain valid)
- Prevents "active but non-buying" companies from gaming HOT
- Prevents double-weighting of motion inside CIS

### Implementation Location
- `compute_conversion_intent_score()` function, lines ~60-75
- Added `reweighting_applied` flag to `cis_components` for debugging

---

## PATCH 2: Frozen Baseline Distributions for Percentile Normalization

### Problem Identified
Dynamic percentile recomputation creates a **leaky evaluation system**: v2 and v3 distributions contaminate each other's baselines during shadow mode, invalidating the entire experiment.

### Fix Applied
Use **fixed reference distributions** loaded at startup, never updated during shadow mode:

```python
BASELINE_DISTRIBUTIONS_PATH = Path("06-sales/baseline_distributions.json")

def load_baseline_distributions() -> dict[str, list[int]]:
    """Load pre-computed baselines (frozen, never contaminated by current batch)."""
```

### Why This Matters
- Shadow evaluation must be independent (v2 and v3 don't influence each other)
- Percentile comparison becomes statistically valid
- Results are reproducible (frozen distribution = same rank for same score)

### Execution Sequence (Critical)
1. Run generator once with dual routing (v2 + v3)
2. Call `initialize_baseline_distributions()` to freeze that run
3. ONLY THEN proceed to Phase 2 shadow mode (future batches use frozen baselines)

### Implementation Location
- New functions: `initialize_baseline_distributions()`, `load_baseline_distributions()`, `compute_percentile_rank()`
- Shadow logging enriched with `v2_percentile`, `v3_percentile`, `percentile_drift`, `bucket_alignment`
- Phase 3 Decision Gate checks percentile drift (not raw score drift)

---

## PATCH 3: Message Variant Purity via Factorial Design (Not Hashing)

### Problem Identified
Hash-based similarity detection is too rigid, kills exploration, generates false redundancy kills. Also doesn't reflect semantic similarity (e.g., "budget release urgency" vs "funding unlocked urgency" are different strings but same meaning).

### Fix Applied
Use **factorial experiment design** with explicit semantic axes:

```python
@dataclass
class VariantExperimentalDimension:
    spend_axis: int    # 0=baseline, 1=moderate, 2=strong
    motion_axis: int   # 0=baseline, 1=moderate, 2=high
    urgency_axis: int  # 0=baseline, 1=moderate, 2=high
    
    def purity_check(baseline) -> bool:
        """Variant is pure if it differs on exactly 1 axis."""
        diffs = (spend != baseline.spend) + (motion != baseline.motion) + (urgency != baseline.urgency)
        return diffs == 1
```

### Why This Matters
- Interpretable (understand WHAT each variant tests)
- Prevents false positive kills (reduces over-enforcement)
- Aligns with experiment design theory (factorial design)
- Enables statistical analysis of which axis matters most

### Implementation Location
- New class: `VariantExperimentalDimension`
- New function: `extract_variant_dimension()` (semantic mapping, not hashing)
- New function: `validate_variant_purity()` (factorial check, not hash check)
- Shadow log enriched with `variant_dimension` field (spend_axis, motion_axis, urgency_axis)
- Phase 2 checkpoint: weekly purity validation, kill only genuinely impure variants

---

## EXECUTION ORDER (MANDATORY)

### Phase 0: Freeze Distributions (Required before Phase 2)
1. Run generator on test CSV with `--shadow-mode` and `--cis-routing-mode dual_shadow`
2. Call `initialize_baseline_distributions()` from resulting shadow logs
3. Verify `06-sales/baseline_distributions.json` was created

### Phase 1: Build & Validate (Today)
1. Add CIS scoring functions (with reweighting)
2. Update dataclasses with v3 fields
3. Implement dual routing (v2 + v3)
4. Add frozen distribution loading to shadow logging
5. Add factorial design validation to variant tracking
6. Dry-run on test CSV

### Phase 2: Shadow Mode (7–14 days)
1. Run with frozen distributions loaded
2. Collect percentile-based divergence metrics
3. Weekly variant purity validation
4. Decision gate based on percentile alignment (not raw scores)

### Phase 3: Controlled Cutover (If Phase 2 passes)
1. Switch to `CIS_ROUTING_MODE=v3_only`
2. Monitor for 3 days
3. If stable, archive v2 logic

---

## CRITICAL CHECKPOINTS (Non-Negotiable)

### Before Phase 2 Starts
- [ ] Baseline distributions frozen (not dynamic)
- [ ] Percentile computation function tests correctly
- [ ] Shadow logs include `v2_percentile`, `v3_percentile` fields
- [ ] Reweighting logic confirmed (low spend → adjusted weights observed in logs)

### During Phase 2 (Weekly)
- [ ] Percentile drift < 15% (avg per batch)
- [ ] Variant purity score ≥ 80%
- [ ] No false positive variant kills (only factorial violations)
- [ ] Reply rates stable (no regression in v3)

### Before Phase 3 Cutover
- [ ] All Phase 2 checkpoints passed
- [ ] Decision gate checks all validity conditions
- [ ] Pre-send safety unchanged
- [ ] Audit trail complete

---

## SUMMARY: WHY THESE PATCHES MATTER

You were building a system that was:
- ✅ Architecturally sound
- ❌ Statistically invalid

These three patches convert it to:
- ✅ Architecturally sound
- ✅ Statistically valid
- ✅ Experimentally pure (factorial design)

**Key insight:** You're not building a lead scoring system anymore. You're building a **controlled experimentation engine for outbound messaging economics**. That requires statistical rigor, not just clean code.

---

## NEXT ACTION

Update V3_IMPLEMENTATION_PLAN.md has been patched with all three fixes.

**Ready to proceed with Phase 1 implementation?**
