# V3 IMPLEMENTATION PLAN: CONVERSION_INTENT_SCORE
**Author:** Revenue Engine Redesign  
**Date:** May 10, 2026  
**Status:** Code-Level Diff Plan (Ready for Implementation)  
**Risk Level:** MEDIUM (Schema-safe, shadow mode, no live switches yet)  
**Critical Constraint:** Frozen distributions required for statistical validity

---

## ⚠️ CRITICAL PRE-EXECUTION REQUIREMENT

**You MUST NOT start Phase 2 (shadow mode) without frozen baseline distributions.**

If you proceed without this:
- v2 and v3 will contaminate each other's percentile calculations
- Your entire shadow mode results will be statistically invalid
- Decision gate will be meaningless

**Before Phase 1 finishes:**
1. Run generator once with v2+v3 dual routing
2. Freeze baseline distributions from that initial run
3. ONLY THEN start Phase 2

See section "Frozen Distribution Percentile Normalization" for setup.

---

## EXECUTIVE SUMMARY

This plan converts Venture OS from **layered decision stacking** (Spend → Motion → LinkedIn → Pre-send) to **unified intent scoring** (CONVERSION_INTENT_SCORE 0–100 with deterministic bands).

**Changes are non-destructive:**
- Inline CIS computation in existing generator
- Dual shadow-mode routing (v2 + v3 in parallel)
- No schema breaks; all v3 metadata in notes field
- Pre-send safety layer unchanged
- 7–14 day observation before live cutover

---

## PART 1: CONVERSION_INTENT_SCORE IMPLEMENTATION

### 1.1 New CIS Scoring Function

**Location:** Insert after `score_candidate()` function in `credibility_candidate_generator.py`

**Core Formula (with dynamic reweighting, NOT clipping):**
```python
def compute_conversion_intent_score(
    row: dict[str, str],
    motion_score: int,  # 0-10 (already computed)
    buying_intensity: int,  # 0-11 (already computed)
    spend_triggers: tuple[str, ...],
) -> tuple[int, dict[str, int]]:
    """
    Compute unified CONVERSION_INTENT_SCORE (0-100).
    
    CRITICAL: Uses conditional reweighting (not clipping) to preserve distribution shape
    for valid percentile comparison in shadow mode.
    
    Returns: (cis_score, component_breakdown)
    """
    
    # === SPEND TRAJECTORY SCORE (0-100) ===
    # Signals: hiring velocity, sales hiring shift, tool stack, funding, outbound scaling
    spend_score = _compute_spend_trajectory(row, spend_triggers)
    
    # === MOTION SIGNAL SCORE (0-100) ===
    # Maps existing motion_score (0-10) to 0-100 band
    motion_signal_score = motion_score * 10
    
    # === FIRMOGRAPHIC FIT SCORE (0-100) ===
    # Static suitability: industry, stage, ICP alignment
    firmographic_score = _compute_firmographic_fit(row)
    
    # === LINKEDIN CONSTRAINT (0-100, but used as binary filter) ===
    # For scoring: strong=0 (fails), weak=100, missing=100, unknown=50
    linkedin_score = _compute_linkedin_constraint_score(row)
    
    # === DYNAMIC REWEIGHTING (CRITICAL FOR VALIDITY) ===
    # DO NOT clip motion_score. Instead, reweight components conditionally.
    # Clipping destroys distribution shape → invalidates percentile comparison.
    if spend_score < 40:
        # Low spend: prioritize spend signals, reduce motion leverage
        spend_weight = 0.45
        motion_weight = 0.25
        firmographic_weight = 0.20
        linkedin_weight = 0.10
    else:
        # Normal weighting
        spend_weight = 0.30
        motion_weight = 0.40
        firmographic_weight = 0.20
        linkedin_weight = 0.10
    
    # === COMPUTE CIS ===
    cis = int(
        (spend_score * spend_weight) +
        (motion_signal_score * motion_weight) +
        (firmographic_score * firmographic_weight) +
        (linkedin_score * linkedin_weight)
    )
    cis = max(0, min(100, cis))
    
    return cis, {
        "spend_trajectory": spend_score,
        "motion_signal": motion_signal_score,
        "firmographic_fit": firmographic_score,
        "linkedin_constraint": linkedin_score,
        "spend_weight": spend_weight,
        "motion_weight": motion_weight,
        "reweighting_applied": spend_score < 40,
    }


def _compute_spend_trajectory(row: dict[str, str], spend_triggers: tuple[str, ...]) -> int:
    """
    Measure spend probability based on trajectory signals (NOT events).
    
    Cap: no single signal exceeds 70.
    
    Signals:
      - Hiring velocity increase: +25
      - Sales hiring shift (AE/BDR/RevOps): +20
      - Tool stack transition: +15
      - Fundraising/capital events: +20
      - Outbound scaling indicators: +15
    """
    
    trigger_text = " ".join([
        _get(row, "trigger"),
        _get(row, "source"),
        _get(row, "news", "funding_news"),
        _get(row, "jobs", "job_titles", "job_postings"),
        _get(row, "description"),
    ])
    
    score = 0
    
    # Hiring velocity increase
    if _contains_any(trigger_text, ("hiring", "urgent hiring", "repeat hiring", "multiple openings")):
        if _contains_any(trigger_text, ("sales", "bdr", "ae", "revops", "growth")):
            score += 25
    
    # Sales hiring shift
    if _contains_any(trigger_text, ("sales hiring", "bdr hiring", "ae hiring", "revops hiring")):
        score += 20
    
    # Tool stack transition
    if "tool_transition" in spend_triggers:
        score += 15
    
    # Fundraising / capital inflow
    if "budget_release" in spend_triggers or _contains_any(trigger_text, ("funded", "raised", "seed funding")):
        score += 20
    
    # Outbound scaling
    if _contains_any(trigger_text, ("outbound", "demand gen", "lead gen", "pipeline")):
        score += 15
    
    # Cap any single signal > 70
    return min(70, max(0, score))


def _compute_firmographic_fit(row: dict[str, str]) -> int:
    """
    Static suitability: industry match, company stage, ICP alignment.
    
    For now, simplified:
      - B2B SaaS / Service firms: +35
      - 10-500 employees: +25
      - Tech/Software/Agency: +20
      - Geography bonus: +10
      - Weak signal: +10
    
    Max: 100
    """
    
    industry = _get(row, "industry", "category", "tags", "description").lower()
    employee_text = _get(row, "employee_count", "employees", "team_size")
    
    score = 20  # baseline
    
    # Industry ICP fit
    if any(term in industry for term in ("saas", "software", "b2b", "agency", "service", "consulting")):
        score += 35
    
    # Stage alignment (10-500 employees)
    try:
        emp_count = int("".join(c for c in employee_text if c.isdigit()) or "0")
        if 10 <= emp_count <= 500:
            score += 25
        elif 5 <= emp_count < 10:
            score += 15
    except:
        pass
    
    # Tech/Software/Agency vertical bonus
    if any(term in industry for term in ("tech", "software", "digital", "agency")):
        score += 20
    
    # Geography bonus (if relevant later)
    score += 10
    
    return min(100, max(0, score))


def _compute_linkedin_constraint_score(row: dict[str, str]) -> int:
    """
    LinkedIn quality as CONSTRAINT, not predictor.
    
    For CIS scoring purposes only:
      - weak or missing: 100 (fully eligible)
      - unknown: 50 (neutral)
      - strong: 0 (eligibility fail, will be filtered in routing)
    
    This ensures strong LinkedIn profiles don't inflate CIS artificially.
    """
    linkedin_quality = _normalized_linkedin_quality(row)
    
    if linkedin_quality in {"weak", "missing"}:
        return 100
    elif linkedin_quality == "unknown":
        return 50
    else:  # strong
        return 0
```

---

### 1.2 Add CIS to CandidateScore Dataclass

**Location:** Update `CandidateScore` dataclass in `credibility_candidate_generator.py`

Replace:
```python
@dataclass(frozen=True)
class CandidateScore:
    buying_intensity: int
    motion_score: int
    trigger: str
    fit_score: int
    service_angle: str
    pressure_tier: str
    urgency_proxy: bool
    reasons: tuple[str, ...]
```

With:
```python
@dataclass(frozen=True)
class CandidateScore:
    # === V2 Fields (preserved for compatibility) ===
    buying_intensity: int
    motion_score: int
    trigger: str
    fit_score: int
    service_angle: str
    pressure_tier: str
    urgency_proxy: bool
    reasons: tuple[str, ...]
    
    # === V3 Fields (NEW) ===
    conversion_intent_score: int  # 0-100 unified score
    cis_components: dict[str, int]  # breakdown: spend_trajectory, motion_signal, firmographic_fit, linkedin_constraint
    cis_routing_band: str  # "HOT", "POSSIBLE", or "DISCARD" based on CIS
```

---
## CRITICAL: Frozen Distribution Percentile Normalization (Validity Requirement)

**⚠️ MUST RUN BEFORE SHADOW MODE STARTS**

Shadow evaluation must NEVER depend on the same batch being evaluated. Dynamic percentile recomputation creates a leaky evaluation system where v2 and v3 contaminate each other's baselines.

**Solution: Use fixed reference distributions loaded at startup.**

### Setup (One-time, before Phase 2)

```python
import json
from pathlib import Path

BASELINE_DISTRIBUTIONS_PATH = Path("06-sales/baseline_distributions.json")

def initialize_baseline_distributions(shadow_log_path: Path) -> dict[str, list[int]]:
    """
    Extract v2 and v3 score distributions from historical shadow logs.
    
    MUST be run once before switching to shadow mode:
        python -c "from credibility_candidate_generator import initialize_baseline_distributions; \
                   initialize_baseline_distributions(Path('06-sales/shadow_decisions.jsonl'))"
    """
    v2_scores, v3_scores = [], []
    
    if shadow_log_path.exists():
        with shadow_log_path.open("r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    if 'v2_motion_score' in record:
                        v2_scores.append(record['v2_motion_score'] * 10)
                    if 'v3_cis' in record:
                        v3_scores.append(record['v3_cis'])
                except json.JSONDecodeError:
                    continue
    
    v2_scores.sort()
    v3_scores.sort()
    
    distributions = {
        "v2_scores": v2_scores,
        "v3_scores": v3_scores,
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "v2_count": len(v2_scores),
        "v3_count": len(v3_scores),
    }
    
    BASELINE_DISTRIBUTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_DISTRIBUTIONS_PATH.write_text(json.dumps(distributions, indent=2), encoding="utf-8")
    print(f"Frozen baselines: v2={len(v2_scores)}, v3={len(v3_scores)}")
    return distributions


def load_baseline_distributions() -> dict[str, list[int]]:
    """Load pre-computed baseline distributions (frozen, never updated during shadow mode)."""
    if not BASELINE_DISTRIBUTIONS_PATH.exists():
        return {
            "v2_scores": list(range(0, 101)),
            "v3_scores": list(range(0, 101)),
            "frozen_at": "initialization",
            "v2_count": 100,
            "v3_count": 100,
        }
    return json.loads(BASELINE_DISTRIBUTIONS_PATH.read_text(encoding="utf-8"))


def compute_percentile_rank(score: int, baseline_distribution: list[int]) -> int:
    """Compute percentile using FROZEN baseline (never contaminated by current batch)."""
    if not baseline_distribution:
        return 50
    count_below = sum(1 for s in baseline_distribution if s <= score)
    return max(0, min(100, int((count_below / len(baseline_distribution)) * 100)))
```

### In Shadow Logging (main())

```python
    baseline_dists = load_baseline_distributions()
    v2_baseline = baseline_dists["v2_scores"]
    v3_baseline = baseline_dists["v3_scores"]
    
    for candidate in candidates:
        v2_percentile = compute_percentile_rank(candidate.score.motion_score * 10, v2_baseline)
        v3_percentile = compute_percentile_rank(candidate.score.conversion_intent_score, v3_baseline)
        percentile_drift = abs(v2_percentile - v3_percentile)
        
        def bucket(p: int) -> str:
            return "top_20" if p >= 80 else ("top_50" if p >= 50 else "bottom_50")
        
        record = {
            ...
            "v2_percentile": v2_percentile,
            "v3_percentile": v3_percentile,
            "percentile_drift": percentile_drift,
            "bucket_alignment": bucket(v2_percentile) == bucket(v3_percentile),
            ...
        }
```

---
### 1.3 Update `score_candidate()` to Populate CIS

**Location:** In `credibility_candidate_generator.py`, update `score_candidate()` function

After line where `motion_score` is computed:
```python
    motion_score = max(0, min(10, round((buying_intensity / 11) * 10)))
    service_angle = "credibility_gap" if distribution_gap >= 2 else "founder_positioning"
    
    # === V3: COMPUTE CONVERSION_INTENT_SCORE ===
    spend_triggers_temp = _spend_triggers(row)  # compute once here
    cis, cis_components = compute_conversion_intent_score(
        row=row,
        motion_score=motion_score,
        buying_intensity=buying_intensity,
        spend_triggers=spend_triggers_temp,
    )
    cis_routing_band = _cis_routing_band(cis)
    
    return CandidateScore(
        buying_intensity=min(buying_intensity, 11),
        motion_score=motion_score,
        trigger=trigger,
        fit_score=fit_score,
        service_angle=service_angle,
        pressure_tier=pressure_tier,
        urgency_proxy=urgency_proxy,
        reasons=tuple(reasons),
        conversion_intent_score=cis,
        cis_components=cis_components,
        cis_routing_band=cis_routing_band,
    )
```

Add new routing band function:
```python
def _cis_routing_band(cis: int) -> str:
    """Map CIS (0-100) to routing band."""
    if cis >= 80:
        return "HOT"
    if cis >= 50:
        return "POSSIBLE"
    return "DISCARD"
```

---

## PART 2: DUAL SHADOW MODE ROUTING

### 2.1 Update ScoredCandidate Dataclass

**Location:** In `credibility_candidate_generator.py`

Replace:
```python
@dataclass(frozen=True)
class ScoredCandidate:
    row: dict[str, str]
    motion_class: str
    score: CandidateScore
    spend_eligible: bool
    spend_triggers: tuple[str, ...]
    message_angle: str
```

With:
```python
@dataclass(frozen=True)
class ScoredCandidate:
    row: dict[str, str]
    motion_class: str  # V2 routing: "HOT", "POSSIBLE", "NO"
    score: CandidateScore
    spend_eligible: bool
    spend_triggers: tuple[str, ...]
    message_angle: str
    # === V3 NEW FIELDS ===
    v3_routing_band: str  # V3 routing: "HOT", "POSSIBLE", "DISCARD"
    message_variant_id: str  # unique identifier for message treatment
    motion_type_targeted: str  # e.g., "spend_driven", "friction_driven", "transition_driven"
    spend_context_tag: str  # spend trigger type (if any)
    hypothesis_label: str  # message testing hypothesis
```

---

### 2.2 Update `build_candidate_row()` to Add V3 Fields

**Location:** In `build_candidate_row()`, after line where `message_angle` is set:

```python
    # === V3: MESSAGE VARIANT FIELDS ===
    variant_id = f"{_lower(company)[:10]}_{cis_routing_band[:3]}_{datetime.now(timezone.utc).strftime('%s')}"
    motion_type_targeted = _map_motion_type_to_message_family(score.trigger, score.motion_score)
    spend_context_tag = spend_triggers[0] if spend_triggers else "no_trigger"
    hypothesis_label = _generate_hypothesis_label(score.trigger, cis_routing_band)
    v3_routing_band = score.cis_routing_band
    
    # === V3: ADD TO NOTES ===
    cis_notes = "; ".join([
        f"cis={score.conversion_intent_score}",
        f"cis_band={v3_routing_band}",
        f"cis_spend={score.cis_components['spend_trajectory']}",
        f"cis_motion={score.cis_components['motion_signal']}",
        f"cis_firmographic={score.cis_components['firmographic_fit']}",
        f"cis_linkedin={score.cis_components['linkedin_constraint']}",
        f"variant_id={variant_id}",
        f"message_variant={motion_type_targeted}",
        f"hypothesis={hypothesis_label}",
    ])
    
    notes = "; ".join([notes, cis_notes])
```

Add helper functions before `build_candidate_row()`:

```python
def _map_motion_type_to_message_family(trigger: str, motion_score: int) -> str:
    """Map trigger type to message family for testing."""
    if trigger in ("revenue_pressure", "scaling_pressure"):
        return "spend_driven"
    elif trigger in ("talent_pressure", "acquisition_pressure"):
        return "friction_driven"
    elif trigger == "visibility_pressure":
        return "transition_driven"
    return "general_pressure"


def _generate_hypothesis_label(trigger: str, cis_band: str) -> str:
    """Generate message hypothesis for A/B testing."""
    base = {
        "revenue_pressure": "spending_scaling",
        "talent_pressure": "hiring_urgency",
        "scaling_pressure": "founder_growth",
        "acquisition_pressure": "pipeline_building",
        "visibility_pressure": "brand_gap",
    }.get(trigger, "general_fit")
    return f"{base}_{cis_band.lower()}"
```

---

### 2.3 Return Updated ScoredCandidate

In `build_candidate_row()`, update return statement:

```python
    return ScoredCandidate(
        row={field: output.get(field, "") for field in schema_fields},
        motion_class=motion_class,  # V2 band for comparison
        score=score,
        spend_eligible=spend_eligible,
        spend_triggers=spend_triggers,
        message_angle=message_angle,
        v3_routing_band=v3_routing_band,  # NEW
        message_variant_id=variant_id,  # NEW
        motion_type_targeted=motion_type_targeted,  # NEW
        spend_context_tag=spend_context_tag,  # NEW
        hypothesis_label=hypothesis_label,  # NEW
    )
```

---

## PART 3: DUAL ROUTING LOGIC IN `main()`

### 3.1 Replace Routing Logic

**Location:** In `main()`, replace the current routing block (lines ~650-700)

Current code:
```python
    spend_eligible_candidates = [candidate for candidate in candidates if candidate.spend_eligible]
    no_spend_candidates = [candidate for candidate in candidates if not candidate.spend_eligible]
    
    hot_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "HOT"]
    possible_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "POSSIBLE"]
    no_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "NO"]
    
    # ... rest of v2 routing
```

Replace with:

```python
    # === V2 ROUTING (unchanged for comparison) ===
    spend_eligible_candidates = [candidate for candidate in candidates if candidate.spend_eligible]
    no_spend_candidates = [candidate for candidate in candidates if not candidate.spend_eligible]
    
    v2_hot_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "HOT"]
    v2_possible_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "POSSIBLE"]
    v2_no_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "NO"]
    
    # === V3 ROUTING (CIS-based bands) ===
    v3_hot_candidates = [
        c for c in candidates
        if c.v3_routing_band == "HOT" and _lower(c.row.get("linkedin_quality")) in {"weak", "missing"}
    ]
    v3_possible_candidates = [
        c for c in candidates
        if c.v3_routing_band == "POSSIBLE"
    ]
    v3_discard_candidates = [
        c for c in candidates
        if c.v3_routing_band == "DISCARD"
    ]
    
    # === APPLY LINKEDIN GATE TO V3 HOT ===
    v3_hot_linkedin_unverified = [
        c for c in candidates
        if c.v3_routing_band == "HOT" and _lower(c.row.get("linkedin_quality")) not in {"weak", "missing"}
    ]
    v3_hot_candidates = v3_hot_candidates[:settings.hot_cap]
    v3_possible_candidates = v3_possible_candidates + v3_hot_linkedin_unverified
    
    # === APPLY CAPS ===
    v2_hot_candidates.sort(key=lambda c: c.score.motion_score, reverse=True)
    v2_hot_candidates = v2_hot_candidates[:settings.hot_cap]
    
    v3_hot_candidates.sort(key=lambda c: c.score.conversion_intent_score, reverse=True)
    v3_hot_candidates = v3_hot_candidates[:settings.hot_cap]
    
    # === SAMPLE POSSIBLE LANES ===
    v2_possible_sampled = _sample_possible(v2_possible_candidates, settings.possible_sample_size, settings.random_seed)
    v3_possible_sampled = _sample_possible(v3_possible_candidates, settings.possible_sample_size, settings.random_seed)
    
    # === ROUTING DECISION: V2 vs V3 ===
    # For now, write both (dual shadow mode)
    # Later: switch to v3_only by setting env var
    
    routing_mode = os.environ.get("CIS_ROUTING_MODE", "dual_shadow")  # dual_shadow | v2_only | v3_only
    
    if routing_mode in ("dual_shadow", "v2_only"):
        possible_rows = [c.row for c in v2_possible_sampled]
        hot_rows_output = [c.row for c in v2_hot_candidates]
    else:  # v3_only
        possible_rows = [c.row for c in v3_possible_sampled]
        hot_rows_output = [c.row for c in v3_hot_candidates]
    
    possible_merged = _merged_rows(args.output, possible_rows, replace=args.replace)
    write_csv(args.output, fields, possible_merged)
    
    hot_written = 0
    if not settings.shadow_mode and hot_rows_output:
        hot_merged = _merged_rows(args.hot_output, hot_rows_output, replace=args.replace)
        write_csv(args.hot_output, fields, hot_merged)
        hot_written = len(hot_rows_output)
```

---

### 3.2 Update Shadow Logging for Dual Mode

**Location:** In `main()`, replace the shadow logging section (around line 730)

```python
    now = datetime.now(timezone.utc).isoformat()
    shadow_records: list[dict] = []
    
    for candidate in candidates:
        # === V2 ROUTING DECISION ===
        v2_effective_route = candidate.motion_class
        if not candidate.spend_eligible:
            v2_effective_route = "NO_SPEND"
        if candidate.motion_class == "HOT" and _lower(candidate.row.get("linkedin_quality")) not in {"weak", "missing"}:
            v2_effective_route = "POSSIBLE_LINKEDIN_UNVERIFIED"
        if candidate.motion_class == "HOT" and settings.shadow_mode:
            v2_effective_route = "HOT_SHADOW_ONLY"
        
        # === V3 ROUTING DECISION ===
        v3_effective_route = candidate.v3_routing_band
        if _lower(candidate.row.get("linkedin_quality")) == "strong" and candidate.v3_routing_band == "HOT":
            v3_effective_route = "HOT_LINKEDIN_STRONG"
        
        record = {
            "timestamp": now,
            "company": candidate.row.get("company", ""),
            "website": candidate.row.get("website", ""),
            # === V2 FIELDS ===
            "v2_motion_class": candidate.motion_class,
            "v2_motion_score": candidate.score.motion_score,
            "v2_spend_eligible": candidate.spend_eligible,
            "v2_effective_route": v2_effective_route,
            # === V3 FIELDS ===
            "v3_cis": candidate.score.conversion_intent_score,
            "v3_band": candidate.v3_routing_band,
            "v3_spend_component": candidate.score.cis_components['spend_trajectory'],
            "v3_motion_component": candidate.score.cis_components['motion_signal'],
            "v3_firmographic_component": candidate.score.cis_components['firmographic_fit'],
            "v3_linkedin_component": candidate.score.cis_components['linkedin_constraint'],
            "v3_effective_route": v3_effective_route,
            # === DIVERGENCE TRACKING ===
            "v2_v3_alignment": v2_effective_route == v3_effective_route,
            "divergence_type": _classify_divergence(v2_effective_route, v3_effective_route),
            # === MESSAGE VARIANT ===
            "variant_id": candidate.message_variant_id,
            "message_variant": candidate.motion_type_targeted,
            "hypothesis": candidate.hypothesis_label,
            "spend_context": candidate.spend_context_tag,
            # === OTHER ===
            "trigger": candidate.score.trigger,
            "linkedin_quality": candidate.row.get("linkedin_quality", ""),
            "reasons": list(candidate.score.reasons),
            "shadow_mode": settings.shadow_mode,
            "routing_mode": routing_mode,
        }
        shadow_records.append(record)
    
    _append_jsonl(args.shadow_log, shadow_records, replace=args.replace)
```

Add helper:

```python
def _classify_divergence(v2_route: str, v3_route: str) -> str:
    if v2_route == v3_route:
        return "none"
    if v2_route.startswith("HOT") and v3_route.startswith("POSSIBLE"):
        return "v3_downgrade_hot_to_possible"
    if v2_route.startswith("POSSIBLE") and v3_route.startswith("HOT"):
        return "v3_upgrade_possible_to_hot"
    if v2_route == "NO_SPEND" and v3_route != "DISCARD":
        return "v3_removes_spend_filter"
    return f"v2_{v2_route}_vs_v3_{v3_route}"
```

---

### 3.3 Update Final Output Summary

**Location:** Replace the final `print()` statement in `main()`

```python
    print(
        "candidate_generation PASS",
        {
            "source_rows": len(source_rows),
            "evaluated_rows": len(candidates),
            # === V2 STATS ===
            "v2_spend_eligible": len(spend_eligible_candidates),
            "v2_no_spend": len(no_spend_candidates),
            "v2_hot_total": len(v2_hot_candidates),
            "v2_hot_routed": hot_written if routing_mode in ("dual_shadow", "v2_only") else 0,
            "v2_possible_sampled": len(v2_possible_sampled),
            # === V3 STATS ===
            "v3_hot_total": len(v3_hot_candidates),
            "v3_possible_total": len(v3_possible_candidates),
            "v3_discard_total": len(v3_discard_candidates),
            # === DIVERGENCE ===
            "routing_mode": routing_mode,
            "divergence_count": sum(1 for r in shadow_records if not r['v2_v3_alignment']),
            # === CONFIG ===
            "shadow_mode": settings.shadow_mode,
            "possible_output": str(args.output),
            "hot_output": str(args.hot_output),
            "shadow_log": str(args.shadow_log),
        },
    )
```

---

## PART 4: CONFIG & ENV UPDATES

### 4.1 Update `runtime_config.py`

Add to `RuntimeConfig` dataclass:

```python
    cis_routing_mode: str  # "dual_shadow", "v2_only", "v3_only"
    cis_hot_threshold: int  # CIS score >= this is HOT (typically 80)
    cis_possible_threshold: int  # CIS score >= this is POSSIBLE (typically 50)
```

Add to `from_env()` classmethod:

```python
            cis_routing_mode=os.environ.get("CIS_ROUTING_MODE", "dual_shadow").strip(),
            cis_hot_threshold=_env_int("CIS_HOT_THRESHOLD", 80),
            cis_possible_threshold=_env_int("CIS_POSSIBLE_THRESHOLD", 50),
```

---

### 4.2 Update `.env.example`

Add:

```ini
# === V3: CONVERSION_INTENT_SCORE ROUTING ===
CIS_ROUTING_MODE=dual_shadow              # Options: dual_shadow (run both), v2_only (original), v3_only (new)
CIS_HOT_THRESHOLD=80                      # CIS >= this → HOT
CIS_POSSIBLE_THRESHOLD=50                 # CIS >= this → POSSIBLE
```

---

## PART 5: KPI TRACKING ADDITIONS

### 5.1 Update `kpi_tracker.py`

Add new metrics capture section after existing reply tracking:

```python
def extract_message_variant_metrics(shadow_log_path: Path) -> dict[str, dict]:
    """
    Extract per-variant metrics from shadow decisions.
    
    Returns:
    {
        "variant_id_123": {
            "sent_count": N,
            "reply_count": N,
            "positive_reply_count": N,
            "reply_rate": X%,
            "positive_reply_rate": Y%,
            "message_variant": "spend_driven",
            "hypothesis": "spending_scaling_HOT",
        },
        ...
    }
    """
    metrics = {}
    
    if not shadow_log_path.exists():
        return metrics
    
    with shadow_log_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            
            variant_id = record.get("variant_id", "unknown")
            if variant_id not in metrics:
                metrics[variant_id] = {
                    "sent_count": 0,
                    "reply_count": 0,
                    "positive_reply_count": 0,
                    "message_variant": record.get("message_variant", "unknown"),
                    "hypothesis": record.get("hypothesis", "unknown"),
                    "v3_band": record.get("v3_band", "unknown"),
                }
            
            metrics[variant_id]["sent_count"] += 1
    
    # === ENRICH WITH REPLY DATA (from reply tracking system) ===
    # This would come from venture_pipeline.py or external source
    # For now, structure only
    
    return metrics


def publish_variant_metrics(metrics: dict[str, dict]) -> None:
    """
    Log per-variant performance to KPI dashboard.
    """
    for variant_id, data in metrics.items():
        reply_rate = (
            (data["reply_count"] / data["sent_count"] * 100)
            if data["sent_count"] > 0 else 0
        )
        positive_rate = (
            (data["positive_reply_count"] / data["reply_count"] * 100)
            if data["reply_count"] > 0 else 0
        )
        
        print(f"\nVariant {variant_id}:")
        print(f"  Message: {data['message_variant']}")
        print(f"  Hypothesis: {data['hypothesis']}")
        print(f"  CIS Band: {data['v3_band']}")
        print(f"  Sent: {data['sent_count']}")
        print(f"  Replies: {data['reply_count']} ({reply_rate:.1f}%)")
        print(f"  Positive: {data['positive_reply_count']} ({positive_rate:.1f}%)")
```

---

## PART 6: FILE-BY-FILE DIFF MAP

### Summary of Changes

| File | Change Type | Risk | Details |
|------|------------|------|---------|
| `credibility_candidate_generator.py` | Core logic injection | MEDIUM | Add CIS functions, update dataclasses, dual routing, shadow logging |
| `runtime_config.py` | New fields | LOW | Add CIS thresholds + routing mode |
| `.env.example` | New knobs | LOW | CIS_ROUTING_MODE, CIS_HOT_THRESHOLD, CIS_POSSIBLE_THRESHOLD |
| `kpi_tracker.py` | Extensions | LOW | Add message variant metrics extraction |
| `pre_send_check.py` | No change | NONE | Safety layer unchanged |
| `batch_guard.py` | No change | NONE | Batch 1 enforcement unchanged |

---

## PART 7: ROLLOUT CHECKLIST (STRICT SEQUENCE)

### Phase 1: Build & Validate (Today)

- [ ] Add CIS scoring functions to generator
- [ ] Update CandidateScore dataclass with v3 fields
- [ ] Update ScoredCandidate with message variant fields
- [ ] Implement dual routing logic in main()
- [ ] Update shadow logging for divergence tracking
- [ ] Update runtime_config.py with CIS knobs
- [ ] Update .env.example
- [ ] **Dry-run test:** `--shadow-mode --cis-routing-mode dual_shadow` on test CSV
  - Expected: v2 + v3 routing side-by-side, divergence metrics in shadow.jsonl
  - Checkpoint: No schema breaks, leads.csv unchanged format

### Phase 2: Deploy Shadow Mode (7–14 days observation)

- [ ] Set `.env`: `CIS_ROUTING_MODE=dual_shadow` (run both v2 and v3)
- [ ] Run pipeline with `--shadow-mode` flag
- [ ] Collect metrics:
  - [ ] HOT overlap %: v2 ∩ v3 / v2 ∪ v3
  - [ ] Reply rate divergence: |v2_reply_rate - v3_reply_rate| / v2_reply_rate
  - [ ] Positive reply rate divergence
  - [ ] Discard inflation: v3_discards / v2_discards
  - [ ] Sample size: v3_possible vs v2_possible
- [ ] Daily check for regressions (reply rates, volume, quality)

### Phase 3: Decision Gate (After 7–14 days)

**ONLY proceed if ALL conditions met:**

- [ ] Positive reply rate (v3) ≥ v2 OR divergence < 10%
- [ ] HOT volume (v3) ≥ 60% of v2 (avoid over-filtering)
- [ ] No increase in false positives (manually sample discard lane)
- [ ] No divergence type `v3_downgrade_hot_to_possible` > 20% (losing high-intent leads)
- [ ] Schema checks PASS (lead CSVs unchanged structure)
- [ ] Pre-send gate still working (23/23 checks)

**If decision is NO:**
- Revert to `CIS_ROUTING_MODE=v2_only`
- Analyze divergence logs to adjust CIS weighting (spend 30%→20%, motion 40%→50%)
- Retry in 3 days

---

## PART 8: SAFETY CHECKPOINTS (NON-NEGOTIABLE)

Before **any** live switch from v2→v3:

### Schema Integrity

- [ ] `credibility-launch-leads.csv` has same 16 fields
- [ ] `credibility-launch-signal-lab.csv` has same 16 fields
- [ ] No duplicate rows introduced
- [ ] Notes field still parseable (added v3 fields are appended, not replacing)

### Routing Safety

- [ ] No leads appear in both leads.csv and signal-lab.csv
- [ ] HOT cap enforced (≤25 rows)
- [ ] POSSIBLE cap enforced (≤10 rows sampled)
- [ ] LinkedIn gate respected (strong profiles excluded from SEND pools)

### Execution Safety

- [ ] Pre-send checks still run and PASS 23/23
- [ ] No send executed without passing pre_send_check.py
- [ ] Batch 1 lock mechanism unchanged
- [ ] If AUTO_SEND_EMAILS=true, it respects current guards

### Data Hygiene

- [ ] Shadow logs contain all required fields for divergence analysis
- [ ] No JSON errors in shadow.jsonl (each line is valid JSON)
- [ ] Discard logs capture false negatives (for post-hoc analysis)

### Compliance

- [ ] All recipients in SEND pools are non-suppressed
- [ ] No duplicate sends across runs
- [ ] Audit trail preserved (shadow logs retain all decisions)

---

## PART 9: IMPLEMENTATION SEQUENCE

**Do NOT start Part X before Part X-1 passes checkpoints.**

### Step 1: Add CIS Scoring Functions (No Changes to Routing Yet)

1. Insert `_compute_spend_trajectory()`, `_compute_firmographic_fit()`, `_compute_linkedin_constraint_score()` functions
2. Insert `compute_conversion_intent_score()` function
3. Add `_cis_routing_band()` function
4. **Validate:** Import paths, no syntax errors
5. **Test:** Run with `--dry-run` on test CSV, confirm generator compiles

### Step 2: Update Dataclasses

1. Update `CandidateScore` to include `conversion_intent_score`, `cis_components`, `cis_routing_band`
2. Update `ScoredCandidate` to include `v3_routing_band`, message variant fields
3. Update `build_candidate_row()` to compute CIS and populate message variant fields
4. **Validate:** No AttributeError when accessing new fields
5. **Test:** Run on test CSV, check notes field has v3 metadata

### Step 3: Implement Dual Routing

1. Replace routing logic in `main()` with v2/v3 branch
2. Add `routing_mode` env var handling
3. Implement both v2 and v3 hot/possible/discard logic
4. **Validate:** Dual routing produces both lanes (leads.csv and signal-lab.csv)
5. **Test:** Run with `CIS_ROUTING_MODE=dual_shadow`, check shadow logs have divergence tracking

### Step 4: Update Shadow Logging

1. Replace shadow_records construction to include v2/v3 fields
2. Add divergence classification
3. Add message variant fields to logs
4. **Validate:** shadow.jsonl logs have v2_effective_route, v3_effective_route, v2_v3_alignment
5. **Test:** Parse shadow.jsonl, confirm all required fields present

### Step 5: Config & Env

1. Add CIS knobs to runtime_config.py
2. Update .env.example
3. **Validate:** Config loads without errors
4. **Test:** Env vars override defaults correctly

### Step 6: KPI Extensions

1. Add `extract_message_variant_metrics()` to kpi_tracker.py
2. Add `publish_variant_metrics()` function
3. **Validate:** Metrics extraction runs without errors
4. **Test:** Extract metrics from test shadow log, confirm calculations correct

### Step 7: Validation Dry-Run

```bash
# In repo root
python 04-coding/scripts/credibility_candidate_generator.py \
  --input 06-sales/credibility-launch-signal-lab.csv \
  --shadow-mode \
  --limit 10 \
  --replace
```

**Expected Output:**
```
candidate_generation PASS {
  'source_rows': 10,
  'evaluated_rows': 10,
  'v2_hot_total': X,
  'v3_hot_total': Y,
  'divergence_count': Z,
  'routing_mode': 'dual_shadow',
  ...
}
```

**Checkpoints:**
- [ ] No errors or exceptions
- [ ] Schema checks PASS
- [ ] shadow_decisions.jsonl created with v2/v3 fields
- [ ] leads.csv and signal-lab.csv have same structure as v2

## PART 10: UPDATED PHASE 3 DECISION GATE (With Validity Checkpoints)

**CRITICAL: Do NOT proceed to v3_only unless ALL statistical validity checks pass.**

### Statistical Validity (MANDATORY)

- [ ] Frozen baseline distributions loaded (not dynamic)
- [ ] Percentile drift (avg across batch) < 15%
- [ ] Top 20% v2/v3 overlap (percentile-based) > 70%
- [ ] No systematic bias (top 10% v2 not downgraded to bottom 10% v3)
- [ ] Reweighting applied correctly (low spend → reweighting observed in logs)

### Volume Safety

- [ ] HOT volume by percentile maintained (50th percentile v2 → ±15% in v3)
- [ ] POSSIBLE sample stable (v3 count within ±20% of v2)
- [ ] Discard inflation not excessive (v3_discards < 1.5x v2_discards)

### Message Purity (Factorial Design)

- [ ] Variant purity score ≥ 80%
- [ ] Each variant differs on exactly ONE axis (spend/motion/urgency)
- [ ] No variants killed due to false redundancy
- [ ] Message variant tracking operational in kpi_tracker.py

### Safety & Compliance

- [ ] Positive reply rate (v3) ≥ v2 OR percentile-adjusted rate stable
- [ ] Pre-send checks unchanged (23/23 still passing)
- [ ] No schema breaks (leads.csv, signal-lab.csv same structure)
- [ ] Audit trail complete (shadow logs have all divergence tracking)

### Decision Rule

**ONLY proceed if:**
- All Statistical Validity checkpoints ✅
- AND Volume Safety checkpoints ✅
- AND Message Purity checkpoints ✅
- AND Safety checkpoints ✅

**If any ONE fails:**
- Revert to `CIS_ROUTING_MODE=v2_only`
- Analyze root cause in shadow logs
- Adjust weights or variant strategy
- Retry Phase 2 in 3 days

---

---

## PART 12: ROLLBACK PLAN

If Phase 2 or Phase 3 detects regression:

### Immediate (< 5 min)

```bash
# Revert to v2 only
export CIS_ROUTING_MODE=v2_only

# Re-run pipeline
python 04-coding/scripts/credibility_candidate_generator.py ...
```

### Git Rollback (if code changes broke something)

```bash
git revert <commit_hash>
```

### Analysis

1. Pull divergence logs from shadow.jsonl
2. Compute v2_v3_alignment by cis_band
3. Identify which CIS component (spend, motion, firmographic) caused misalignment
4. Adjust weights and retry Phase 2

---

## CRITICAL: Message Variant Purity via Factorial Experiment Design

**⚠️ IMPORTANT: Not for Phase 1, but REQUIRED before Phase 2 full sends**

Message variants must test ONE dimension only (spend framing vs motion framing vs urgency framing), not all at once.

**Use factorial experiment design, NOT hash-based similarity.**

### Why Factorial Design, Not Hashing

Hash-based purity kills exploration (false positives). Factorial design is interpretable and prevents over-enforcement.

### Semantic Dimensions Framework

```python
@dataclass(frozen=True)
class VariantExperimentalDimension:
    """
    Defines the single dimension each message variant tests.
    
    Each variant differs from baseline on exactly ONE axis:
      - spend_axis: signal about budget/spending readiness
      - motion_axis: signal about operational activity level
      - urgency_axis: signal about immediate problem pressure
    
    Levels: 0=baseline, 1=moderate, 2=intense
    """
    spend_axis: int  # 0=no spend signal, 1=medium, 2=strong
    motion_axis: int  # 0=low activity, 1=medium, 2=high
    urgency_axis: int  # 0=low urgency, 1=medium, 2=high
    
    def purity_check(baseline: "VariantExperimentalDimension") -> bool:
        """Variant is pure if it differs from baseline on exactly 1 axis."""
        diffs = (
            (self.spend_axis != baseline.spend_axis) +
            (self.motion_axis != baseline.motion_axis) +
            (self.urgency_axis != baseline.urgency_axis)
        )
        return diffs == 1


def extract_variant_dimension(
    trigger: str,
    spend_context: str,
    hypothesis: str,
    cis_band: str,
) -> VariantExperimentalDimension:
    """
    Map variant characteristics to experimental axes (not via hashing, via semantics).
    
    Returns the dimensional profile of this variant.
    """
    
    # === SPEND AXIS ===
    spend_axis = 0
    if spend_context in ("budget_release", "funding_news"):
        spend_axis = 2  # intense
    elif spend_context in ("tool_transition", "partner_switch"):
        spend_axis = 1  # moderate
    
    # === MOTION AXIS ===
    motion_axis = 0
    if cis_band == "HOT":
        motion_axis = 2  # high activity
    elif cis_band == "POSSIBLE":
        motion_axis = 1  # moderate activity
    
    # === URGENCY AXIS ===
    urgency_axis = 0
    if "urgency" in hypothesis.lower() or trigger == "revenue_pressure":
        urgency_axis = 2  # high urgency
    elif trigger in ("scaling_pressure", "acquisition_pressure"):
        urgency_axis = 1  # moderate urgency
    
    return VariantExperimentalDimension(
        spend_axis=spend_axis,
        motion_axis=motion_axis,
        urgency_axis=urgency_axis,
    )


def validate_variant_purity(shadow_records: list[dict]) -> dict[str, any]:
    """
    Validate that variants follow factorial experiment design.
    
    Each variant should differ from baseline on exactly ONE axis.
    
    Returns:
    {
        "purity_score": X%,
        "variant_count": N,
        "impure_variants": [...],
        "recommendation": "All pure" | "Kill [list]",
    }
    """
    
    # === EXTRACT BASELINE VARIANT ===
    baseline_dim = VariantExperimentalDimension(spend_axis=0, motion_axis=0, urgency_axis=0)
    
    # === COLLECT UNIQUE VARIANTS ===
    variant_dims = {}
    variant_counts = {}
    
    for record in shadow_records:
        variant_id = record.get('variant_id', 'unknown')
        if variant_id not in variant_counts:
            variant_counts[variant_id] = 0
            variant_dims[variant_id] = extract_variant_dimension(
                record.get('trigger', ''),
                record.get('spend_context', ''),
                record.get('hypothesis', ''),
                record.get('v3_band', ''),
            )
        variant_counts[variant_id] += 1
    
    # === CHECK PURITY ===
    impure = []
    for variant_id, dim in variant_dims.items():
        if not dim.purity_check(baseline_dim):
            impure.append({
                'variant_id': variant_id,
                'count': variant_counts[variant_id],
                'dimension': {
                    'spend_axis': dim.spend_axis,
                    'motion_axis': dim.motion_axis,
                    'urgency_axis': dim.urgency_axis,
                },
                'differs_on': (
                    (dim.spend_axis != baseline_dim.spend_axis, 'spend') +
                    (dim.motion_axis != baseline_dim.motion_axis, 'motion') +
                    (dim.urgency_axis != baseline_dim.urgency_axis, 'urgency')
                ),
                'recommendation': f"Kill {variant_id} (violates factorial design)",
            })
    
    purity_score = (len(variant_dims) - len(impure)) / len(variant_dims) * 100 if variant_dims else 0
    
    return {
        "variant_count": len(variant_dims),
        "purity_score": int(purity_score),
        "impure_count": len(impure),
        "impure_variants": impure,
        "recommendation": "All variants pure" if not impure else f"Kill {len(impure)} variants",
    }
```

### Shadow Log Addition

```python
    # In shadow_records, add:
    record = {
        ...
        "variant_dimension": {
            "spend_axis": extract_variant_dimension(...).spend_axis,
            "motion_axis": extract_variant_dimension(...).motion_axis,
            "urgency_axis": extract_variant_dimension(...).urgency_axis,
        },
        ...
    }
```

### Phase 2 Checkpoint

After each week during Phase 2:
1. Run `validate_variant_purity(shadow_records)`
2. If `purity_score < 80%`, kill impure variants immediately
3. Never run variants that differ on multiple axes (breaks experiment validity)

---

## PART 13: SUCCESS CRITERIA

After Phase 3 Decision Gate, system is considered **V3-Ready** if:

1. ✅ Positive reply rate (v3) ≥ v2
2. ✅ HOT volume stable (≥60% of v2)
3. ✅ No increase in false positives
4. ✅ Divergence < 20% across all metrics
5. ✅ Message variant tracking operational
6. ✅ KPI dashboard shows per-variant performance
7. ✅ Pre-send safety unchanged

Then: Switch to `CIS_ROUTING_MODE=v3_only` and monitor for 3 more days.

If all green: **V3 is LIVE. Archive v2 logic as fallback only.**

---

## APPENDIX: CIS FORMULA REFERENCE

```
CONVERSION_INTENT_SCORE (0-100)
= (Spend_Trajectory * 0.30)
+ (Motion_Signal * 0.40)
+ (Firmographic_Fit * 0.20)
+ (LinkedIn_Constraint * 0.10)

Routing Bands:
  80-100 → HOT (send)
  50-79  → POSSIBLE (test messages)
  <50    → DISCARD (filter)

LinkedIn Gate (applied AFTER CIS routing):
  STRONG → exclude from SEND pools
  WEAK/MISSING → eligible for SEND
  UNKNOWN → eligible for SEND (neutral constraint)
```

---

## APPENDIX: MESSAGE VARIANT FRAMEWORK

Each send gets:

```
message_variant_id: unique identifier
message_variant: {spend_driven, friction_driven, transition_driven}
hypothesis: {spend_variant}_{cis_band} e.g., "spending_scaling_HOT"
spend_context: {spend_trigger_type} e.g., "tool_transition"
```

Weekly: Kill lowest-performing variant, test new hypothesis.

---

**End of V3 Implementation Plan**
