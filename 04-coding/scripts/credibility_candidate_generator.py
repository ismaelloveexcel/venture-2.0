#!/usr/bin/env python3
"""
Credibility Launch Candidate Generator

Deterministically converts structured source exports into pre-scored Signal Lab
rows. This is a commercial-intent filter, not a LinkedIn evaluator.

Inputs can come from YC, Wellfound, job boards, funding/news sheets, or any CSV
with matching/near-matching columns. LinkedIn quality is always kept as unknown;
Send Pool promotion happens only after a later binary LinkedIn check.

Usage:
    python 04-coding/scripts/credibility_candidate_generator.py --input raw.csv
    python 04-coding/scripts/credibility_candidate_generator.py --input raw.csv --replace
    python 04-coding/scripts/credibility_candidate_generator.py --input raw.csv --limit 20
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from runtime_config import RuntimeConfig


BASE = Path(__file__).resolve().parents[2]
SALES_DIR = BASE / "06-sales"
SCHEMA_PATH = SALES_DIR / "credibility-launch-lead-schema.json"
DEFAULT_POSSIBLE_OUTPUT = SALES_DIR / "credibility-launch-signal-lab.csv"
DEFAULT_HOT_OUTPUT = SALES_DIR / "credibility-launch-leads.csv"
DEFAULT_SHADOW_LOG = SALES_DIR / "shadow_decisions.jsonl"
DEFAULT_DISCARD_LOG = SALES_DIR / "credibility-discard.jsonl"

FOUNDER_TERMS = ("founder", "co-founder", "ceo", "owner", "managing director", "partner")
SERVICE_MODEL_HIGH_PRESSURE_TERMS = (
    "agency",
    "consultancy",
    "consulting",
    "msp",
    "managed service",
    "service firm",
    "professional services",
    "outsourced",
    "fractional",
)
SERVICE_MODEL_MEDIUM_PRESSURE_TERMS = (
    "b2b",
    "saas",
    "software",
    "enterprise",
    "platform",
)
HIRE_INTENT_TERMS = (
    "sales",
    "growth",
    "marketing",
    "sdr",
    "bdr",
    "revops",
    "demand gen",
    "account executive",
    "lead generation",
    "business development",
)
HIRE_NON_INTENT_TERMS = (
    "engineer",
    "engineering",
    "developer",
    "product",
    "designer",
    "ops",
    "operations",
)
FOUNDER_GROWTH_TERMS = (
    "scaling",
    "need more leads",
    "expanding pipeline",
    "looking for clients",
    "book more meetings",
    "growing revenue",
    "hiring sales",
    "hiring growth",
    "launch",
    "launched",
    "yc",
    "demo day",
    "product hunt",
)
FUNDING_TERMS = ("funding", "funded", "pre-seed", "seed", "raised", "investment")
VISIBILITY_STRONG_TERMS = ("active content", "daily posts", "ads running", "newsletter")
VISIBILITY_WEAK_TERMS = ("no content", "inactive", "underbuilt", "no outbound", "no ads", "no linkedin")

ALLOWED_LINKEDIN_QUALITY = {"unknown", "strong", "weak", "missing"}

SPEND_TRIGGER_TOOLING_TRANSITION_TERMS = (
    "alternative to",
    "replacing",
    "migrating from",
    "moving off",
    "manual process",
    "spreadsheet",
    "legacy stack",
)
SPEND_TRIGGER_FAILED_BUILD_TERMS = (
    "urgent hiring",
    "still hiring",
    "repeat hiring",
    "contract-to-hire",
    "outsourcing",
    "outsource",
    "fractional",
)
SPEND_TRIGGER_BUDGET_RELEASE_TERMS = (
    "funding",
    "raised",
    "seed",
    "series a",
    "new team",
    "new department",
    "expanding to",
    "new market",
)
SPEND_TRIGGER_EXECUTION_BOTTLENECK_TERMS = (
    "overloaded",
    "bottleneck",
    "inefficiency",
    "behind on",
    "cannot keep up",
    "operational drag",
    "slow execution",
)
SPEND_TRIGGER_PARTNER_SWITCH_TERMS = (
    "switching agency",
    "changing agency",
    "rethinking strategy",
    "rethinking stack",
    "looking for partner",
    "replace partner",
)

SPEND_ANGLE_BY_TRIGGER = {
    "tool_transition": "replacement_positioning",
    "failed_internal_build": "execution_relief",
    "budget_release": "scaling_acceleration",
    "execution_bottleneck": "operational_unblock",
    "partner_switch": "efficiency_cost_reduction",
}


@dataclass(frozen=True)
class MotionSettings:
    hot_threshold: int
    possible_threshold: int
    hot_cap: int
    possible_sample_size: int
    shadow_mode: bool
    spend_filter_required: bool
    spend_min_trigger_count: int
    random_seed: int


@dataclass(frozen=True)
class VariantExperimentalDimension:
    """Factorial experiment design: each variant differs on exactly ONE semantic axis."""
    spend_axis: int  # 0=baseline, 1=moderate, 2=strong
    motion_axis: int  # 0=baseline, 1=moderate, 2=high
    urgency_axis: int  # 0=baseline, 1=moderate, 2=high
    
    def purity_check(self, baseline: "VariantExperimentalDimension") -> bool:
        """Variant is pure if it differs from baseline on exactly 1 axis."""
        diffs = sum([
            self.spend_axis != baseline.spend_axis,
            self.motion_axis != baseline.motion_axis,
            self.urgency_axis != baseline.urgency_axis,
        ])
        return diffs == 1


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
    # === V3 FIELDS (NEW) ===
    conversion_intent_score: int  # 0-100 unified score
    cis_components: dict[str, int]  # breakdown: spend, motion, firmographic, linkedin, weights
    cis_routing_band: str  # "HOT", "POSSIBLE", or "DISCARD"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_motion_settings() -> MotionSettings:
    cfg = RuntimeConfig.from_env()
    hot_threshold = max(0, min(10, cfg.motion_hot_threshold))
    possible_threshold = max(0, min(hot_threshold, cfg.motion_possible_threshold))
    return MotionSettings(
        hot_threshold=hot_threshold,
        possible_threshold=possible_threshold,
        hot_cap=max(1, cfg.motion_hot_cap),
        possible_sample_size=max(0, cfg.motion_possible_sample_size),
        shadow_mode=cfg.motion_shadow_mode,
        spend_filter_required=cfg.spend_filter_required,
        spend_min_trigger_count=max(1, cfg.spend_min_trigger_count),
        random_seed=42,
    )


# === V3: FROZEN BASELINE DISTRIBUTIONS (CRITICAL FOR STATISTICAL VALIDITY) ===
BASELINE_DISTRIBUTIONS_PATH = SALES_DIR / "baseline_distributions.json"


def initialize_baseline_distributions(shadow_log_path: Path) -> dict:
    """Extract and freeze v2/v3 score distributions from shadow logs (run once before Phase 2).
    
    This function should NOT be called during Phase 2 shadow mode.
    Use phase0_freeze_baselines.py as the standalone Phase 0 execution.
    """
    from shadow_drift_tracker import compute_percentile_buckets
    
    v2_scores, v3_scores = [], []
    record_count = 0
    
    if shadow_log_path.exists():
        with shadow_log_path.open("r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    record_count += 1
                    if "v2_motion_score" in record:
                        v2_scores.append(int(record["v2_motion_score"] * 10))
                    if "v3_cis" in record:
                        v3_scores.append(int(record["v3_cis"]))
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
    
    v2_scores.sort()
    v3_scores.sort()
    
    distributions = {
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "v2": {
            "count": len(v2_scores),
            "mean": int(sum(v2_scores) / len(v2_scores)) if v2_scores else 0,
            "min": min(v2_scores) if v2_scores else 0,
            "max": max(v2_scores) if v2_scores else 100,
            "scores": v2_scores,
            "percentiles": compute_percentile_buckets(v2_scores),
        },
        "v3": {
            "count": len(v3_scores),
            "mean": int(sum(v3_scores) / len(v3_scores)) if v3_scores else 0,
            "min": min(v3_scores) if v3_scores else 0,
            "max": max(v3_scores) if v3_scores else 100,
            "scores": v3_scores,
            "percentiles": compute_percentile_buckets(v3_scores),
        },
        "source_record_count": record_count,
    }
    
    BASELINE_DISTRIBUTIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_DISTRIBUTIONS_PATH.write_text(json.dumps(distributions, indent=2), encoding="utf-8")
    return distributions


def load_baseline_distributions() -> dict:
    """Load pre-computed baseline distributions (frozen, never updated during shadow mode).
    
    PHASE 2 REQUIREMENT: File MUST exist. If missing, baseline freeze was not run.
    Error indicates Phase 0 was skipped.
    """
    if not BASELINE_DISTRIBUTIONS_PATH.exists():
        raise FileNotFoundError(
            f"\n\n❌ BASELINE DISTRIBUTIONS NOT FROZEN (Phase 0 not executed)\n"
            f"Path: {BASELINE_DISTRIBUTIONS_PATH}\n\n"
            f"BEFORE running Phase 2 shadow mode, you must:\n"
            f"  python -c \"from credibility_candidate_generator import initialize_baseline_distributions; "
            f"from pathlib import Path; initialize_baseline_distributions(Path('06-sales/shadow_decisions.jsonl'))\"\n\n"
            f"See: V3_IMPLEMENTATION_PLAN.md Section 6.2 (Phase 0)"
        )
    return json.loads(BASELINE_DISTRIBUTIONS_PATH.read_text(encoding="utf-8"))


def compute_percentile_rank(score: int, baseline_distribution: list[int]) -> int:
    """Compute percentile using FROZEN baseline (never contaminated by current batch).
    
    Args:
        score: The score to rank
        baseline_distribution: Sorted list of scores from frozen baseline
    
    Returns:
        Percentile rank 0-100
    """
    if not baseline_distribution:
        return 50
    count_below = sum(1 for s in baseline_distribution if s <= score)
    return max(0, min(100, int((count_below / len(baseline_distribution)) * 100)))


def _lower(value: object) -> str:
    return str(value or "").strip().lower()


def _get(row: dict[str, str], *names: str) -> str:
    aliases = {key.lower().strip(): value for key, value in row.items()}
    for name in names:
        value = aliases.get(name.lower())
        if value:
            return value.strip()
    return ""


def _truthy(value: str) -> bool:
    return _lower(value) in {"1", "true", "yes", "y", "found", "present"}


def _employee_count(value: str) -> int | None:
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    text_lower = _lower(text)
    return any(term in text_lower for term in terms)


def _score_hiring_intent(trigger_text: str, jobs_text: str, has_hiring_flag: bool) -> tuple[int, str]:
    if _contains_any(jobs_text, HIRE_INTENT_TERMS):
        high_hits = sum(1 for term in HIRE_INTENT_TERMS if term in _lower(jobs_text))
        return (3 if high_hits >= 2 else 2), "hiring_intent_roles"
    if has_hiring_flag and not _contains_any(jobs_text, HIRE_NON_INTENT_TERMS):
        return 1, "generic_hiring_signal"
    if has_hiring_flag and _contains_any(jobs_text, HIRE_NON_INTENT_TERMS):
        return 0, "non_revenue_hiring_only"
    if _contains_any(trigger_text, HIRE_INTENT_TERMS):
        return 2, "hiring_intent_in_source"
    return 0, "no_hiring_intent"


def _score_founder_growth_signal(founder_led: bool, trigger_text: str) -> tuple[int, str]:
    if founder_led and _contains_any(trigger_text, FOUNDER_GROWTH_TERMS):
        return 3, "founder_growth_push"
    if _contains_any(trigger_text, FOUNDER_GROWTH_TERMS):
        return 2, "growth_push_no_founder_confirmation"
    if founder_led and ("growing" in _lower(trigger_text) or "hiring" in _lower(trigger_text)):
        return 1, "founder_motion_hint"
    return 0, "no_growth_push"


def _score_revenue_model_pressure(industry_text: str, role_text: str) -> tuple[int, str]:
    combined = f"{industry_text} {role_text}"
    if _contains_any(combined, SERVICE_MODEL_HIGH_PRESSURE_TERMS):
        return 2, "revenue_dependency_high"
    if _contains_any(combined, SERVICE_MODEL_MEDIUM_PRESSURE_TERMS):
        return 1, "revenue_dependency_medium"
    return 0, "revenue_dependency_low"


def _score_distribution_gap(
    website_present: bool,
    website_quality: str,
    linkedin_url_present: bool,
    distribution_text: str,
) -> tuple[int, str]:
    has_strong_visibility = _contains_any(distribution_text, VISIBILITY_STRONG_TERMS)
    has_weak_visibility = _contains_any(distribution_text, VISIBILITY_WEAK_TERMS)

    if website_present and website_quality == "strong" and not linkedin_url_present and not has_strong_visibility:
        return 3, "strong_offer_weak_distribution"
    if website_present and website_quality in {"strong", "average"} and has_weak_visibility:
        return 3, "explicit_distribution_gap"
    if website_present and website_quality in {"strong", "average"} and not has_strong_visibility:
        return 2, "distribution_gap_likely"
    if website_present:
        return 1, "partial_distribution_gap"
    return 0, "insufficient_distribution_signal"


def _pressure_type(
    hiring_intent: int,
    founder_growth_signal: int,
    revenue_model_pressure: int,
    distribution_gap: int,
    trigger_text: str,
) -> str:
    has_funding = _contains_any(trigger_text, FUNDING_TERMS)
    if revenue_model_pressure >= 2 and (hiring_intent >= 2 or founder_growth_signal >= 2):
        return "revenue_pressure"
    if hiring_intent >= 2:
        return "talent_pressure"
    if founder_growth_signal >= 2 and has_funding:
        return "scaling_pressure"
    if founder_growth_signal >= 2:
        return "acquisition_pressure"
    if distribution_gap >= 2:
        return "visibility_pressure"
    return "acquisition_pressure"


def _fit_from_buying_intensity(score: int) -> int:
    if score >= 10:
        return 10
    if score >= 7:
        return 8
    if score >= 5:
        return 6
    return 3


def _pressure_tier(score: int) -> str:
    if score >= 10:
        return "priority_send_candidate"
    if score >= 7:
        return "send_pool_candidate"
    if score >= 5:
        return "signal_lab"
    return "discard"


def _motion_class(motion_score: int, settings: MotionSettings) -> str:
    if motion_score >= settings.hot_threshold:
        return "HOT"
    if motion_score >= settings.possible_threshold:
        return "POSSIBLE"
    return "NO"


# === V3: CIS SCORING FUNCTIONS (CONVERSION INTENT SCORE) ===

def _compute_spend_trajectory(row: dict[str, str], spend_triggers: tuple[str, ...]) -> int:
    """Spend trajectory score (0-100). Signals: hiring velocity, sales shift, tool stack, funding, outbound scaling."""
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
    
    return min(70, max(0, score))


def _compute_firmographic_fit(row: dict[str, str]) -> int:
    """Firmographic fit (0-100): industry match, stage, ICP alignment."""
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
    except Exception:
        pass
    
    # Tech/Software/Agency vertical bonus
    if any(term in industry for term in ("tech", "software", "digital", "agency")):
        score += 20
    
    # Geography bonus
    score += 10
    
    return min(100, max(0, score))


def _compute_linkedin_constraint_score(row: dict[str, str]) -> int:
    """LinkedIn quality as constraint (0-100): weak/missing=100, unknown=50, strong=0."""
    linkedin_quality = _normalized_linkedin_quality(row)
    
    if linkedin_quality in {"weak", "missing"}:
        return 100
    elif linkedin_quality == "unknown":
        return 50
    else:  # strong
        return 0


def compute_conversion_intent_score(
    row: dict[str, str],
    motion_score: int,
    buying_intensity: int,
    spend_triggers: tuple[str, ...],
) -> tuple[int, dict]:
    """
    Compute unified CONVERSION_INTENT_SCORE (0-100).
    Uses dynamic reweighting (not clipping) to preserve distribution shape for percentile validity.
    """
    spend_score = _compute_spend_trajectory(row, spend_triggers)
    motion_signal_score = motion_score * 10
    firmographic_score = _compute_firmographic_fit(row)
    linkedin_score = _compute_linkedin_constraint_score(row)
    
    # === DYNAMIC REWEIGHTING (low spend reduces motion leverage) ===
    if spend_score < 40:
        motion_weight = 0.25
        spend_weight = 0.45
    else:
        motion_weight = 0.40
        spend_weight = 0.30
    
    firmographic_weight = 0.20
    linkedin_weight = 0.10
    
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


def compute_conversion_intent_score_divergent(
    row: dict[str, str],
    motion_score: int,
    buying_intensity: int,
    spend_triggers: tuple[str, ...],
) -> int:
    """
    V3 DIVERGENT SCORING: Forced reweighting to intentionally differ from v2.
    
    Strategy: Amplify intent signals, reduce spend dominance, penalize weak signals.
    Target: 10-30% rank inversions while maintaining Spearman >= 0.6.
    """
    spend_score = _compute_spend_trajectory(row, spend_triggers)
    motion_signal_score = motion_score * 10
    firmographic_score = _compute_firmographic_fit(row)
    linkedin_score = _compute_linkedin_constraint_score(row)
    
    # === FORCED DIVERGENCE WEIGHTS ===
    # Amplify motion (buying pressure signal)
    motion_weight = 0.50  # ↑ from 0.25/0.40
    
    # Reduce spend dominance
    spend_weight = 0.25  # ↓ from 0.30/0.45
    
    # Increase firmographic + LinkedIn (intent constraints)
    firmographic_weight = 0.15  # ↓ slightly (less is more for constraints)
    linkedin_weight = 0.10  # maintain (gatekeeping value)
    
    # Compute base score
    base_cis = (
        (spend_score * spend_weight) +
        (motion_signal_score * motion_weight) +
        (firmographic_score * firmographic_weight) +
        (linkedin_score * linkedin_weight)
    )
    
    # === INTENT AMPLIFICATION ===
    # Explicitly penalize weak trigger signals
    trigger_text = " ".join(str(v) for v in row.values() if v).lower()
    explicit_intent_bonus = 0
    if any(t in trigger_text for t in ("revenue_pressure", "budget_release", "urgency")):
        explicit_intent_bonus = 15
    elif any(t in trigger_text for t in ("scaling_pressure", "hiring")):
        explicit_intent_bonus = 8
    
    # Penalize weak/missing signals
    noise_penalty = 0
    if linkedin_score < 30:
        noise_penalty += 10
    if motion_signal_score < 20:
        noise_penalty += 5
    
    # Final score (normalized 0-100)
    v3_div_score = int(base_cis + explicit_intent_bonus - noise_penalty)
    v3_div_score = max(0, min(100, v3_div_score))
    
    return v3_div_score


def _cis_routing_band(cis: int) -> str:
    """Map CIS (0-100) to routing band."""
    if cis >= 80:
        return "HOT"
    if cis >= 50:
        return "POSSIBLE"
    return "DISCARD"


def _extract_variant_dimension(
    trigger: str,
    spend_context: str,
    hypothesis: str,
    cis_band: str,
) -> VariantExperimentalDimension:
    """Map variant characteristics to experimental axes (factorial design)."""
    spend_axis = 0
    if spend_context in ("budget_release", "funding_news"):
        spend_axis = 2
    elif spend_context in ("tool_transition", "partner_switch"):
        spend_axis = 1
    
    motion_axis = 0
    if cis_band == "HOT":
        motion_axis = 2
    elif cis_band == "POSSIBLE":
        motion_axis = 1
    
    urgency_axis = 0
    if "urgency" in hypothesis.lower() or trigger == "revenue_pressure":
        urgency_axis = 2
    elif trigger in ("scaling_pressure", "acquisition_pressure"):
        urgency_axis = 1
    
    return VariantExperimentalDimension(
        spend_axis=spend_axis,
        motion_axis=motion_axis,
        urgency_axis=urgency_axis,
    )


def score_candidate(row: dict[str, str]) -> CandidateScore:
    role = _get(row, "role", "title", "founder_role")
    industry = _get(row, "industry", "category", "tags", "description")
    website_quality = _lower(_get(row, "website_quality")) or "average"
    if website_quality not in {"strong", "average", "weak"}:
        website_quality = "average"
    trigger_text = " ".join(
        [
            _get(row, "trigger"),
            _get(row, "source"),
            _get(row, "yc_batch", "batch"),
            _get(row, "news", "funding_news"),
            _get(row, "jobs", "job_titles", "job_postings"),
            _get(row, "description"),
        ]
    )
    jobs_text = " ".join(
        [
            _get(row, "jobs", "job_titles", "job_postings"),
            _get(row, "hiring_roles", "open_roles"),
            _get(row, "description"),
        ]
    )
    distribution_text = " ".join(
        [
            _get(row, "distribution_notes"),
            _get(row, "visibility_signal"),
            _get(row, "content_signal"),
            _get(row, "description"),
        ]
    )

    reasons: list[str] = []

    founder_led = _contains_any(role, FOUNDER_TERMS)
    has_hiring_flag = _truthy(_get(row, "hiring", "hiring_signal")) or _employee_count(_get(row, "jobs_count", "job_count", "open_roles")) not in {None, 0}

    hiring_intent, hiring_reason = _score_hiring_intent(trigger_text, jobs_text, has_hiring_flag)
    founder_growth_signal, founder_growth_reason = _score_founder_growth_signal(founder_led, trigger_text)
    revenue_model_pressure, revenue_reason = _score_revenue_model_pressure(industry, role)
    distribution_gap, gap_reason = _score_distribution_gap(
        website_present=bool(_get(row, "website", "company_website", "url")),
        website_quality=website_quality,
        linkedin_url_present=bool(_get(row, "linkedin_url", "company_linkedin", "linkedin")),
        distribution_text=distribution_text,
    )

    reasons.extend([hiring_reason, founder_growth_reason, revenue_reason, gap_reason])
    if founder_led:
        reasons.append("founder_led")

    buying_intensity = hiring_intent + founder_growth_signal + revenue_model_pressure + distribution_gap
    urgency_proxy = bool((hiring_intent >= 2 or founder_growth_signal >= 2) and revenue_model_pressure >= 1)
    pressure_tier = _pressure_tier(buying_intensity)

    trigger = _pressure_type(
        hiring_intent=hiring_intent,
        founder_growth_signal=founder_growth_signal,
        revenue_model_pressure=revenue_model_pressure,
        distribution_gap=distribution_gap,
        trigger_text=trigger_text,
    )

    fit_score = _fit_from_buying_intensity(buying_intensity)
    motion_score = max(0, min(10, round((buying_intensity / 11) * 10)))
    service_angle = "credibility_gap" if distribution_gap >= 2 else "founder_positioning"

    # === V3: COMPUTE CONVERSION_INTENT_SCORE ===
    spend_triggers_temp = _spend_triggers(row)
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
    variant_dimension: VariantExperimentalDimension  # factorial experiment design


def _spend_triggers(row: dict[str, str]) -> tuple[str, ...]:
    source_text = " ".join(
        [
            _get(row, "trigger"),
            _get(row, "source"),
            _get(row, "news", "funding_news"),
            _get(row, "jobs", "job_titles", "job_postings"),
            _get(row, "description"),
            _get(row, "distribution_notes"),
            _get(row, "visibility_signal"),
        ]
    )
    triggers: list[str] = []
    if _contains_any(source_text, SPEND_TRIGGER_TOOLING_TRANSITION_TERMS):
        triggers.append("tool_transition")
    if _contains_any(source_text, SPEND_TRIGGER_FAILED_BUILD_TERMS):
        triggers.append("failed_internal_build")
    if _contains_any(source_text, SPEND_TRIGGER_BUDGET_RELEASE_TERMS):
        triggers.append("budget_release")
    if _contains_any(source_text, SPEND_TRIGGER_EXECUTION_BOTTLENECK_TERMS):
        triggers.append("execution_bottleneck")
    if _contains_any(source_text, SPEND_TRIGGER_PARTNER_SWITCH_TERMS):
        triggers.append("partner_switch")
    return tuple(dict.fromkeys(triggers))


def _normalized_linkedin_quality(row: dict[str, str]) -> str:
    raw = _lower(_get(row, "linkedin_quality"))
    if raw in ALLOWED_LINKEDIN_QUALITY:
        return raw
    return "unknown"


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


def build_candidate_row(row: dict[str, str], schema_fields: list[str], settings: MotionSettings) -> ScoredCandidate:
    score = score_candidate(row)
    motion_class = _motion_class(score.motion_score, settings)
    spend_triggers = _spend_triggers(row)
    spend_eligible = (len(spend_triggers) >= settings.spend_min_trigger_count) if settings.spend_filter_required else True
    message_angle = SPEND_ANGLE_BY_TRIGGER.get(spend_triggers[0], "general_pressure") if spend_triggers else "general_pressure"
    company = _get(row, "company", "company_name", "name")
    first_name = _get(row, "first_name", "founder_first_name")
    role = _get(row, "role", "title", "founder_role")
    website = _get(row, "website", "company_website", "url")
    industry = _get(row, "industry", "category", "tags", "description")
    employee_count = _get(row, "employee_count", "employees", "team_size", "team size")
    location = _get(row, "location", "hq", "city")
    linkedin_url = _get(row, "linkedin_url", "company_linkedin", "linkedin")
    linkedin_quality = _normalized_linkedin_quality(row)
    website_quality = _lower(_get(row, "website_quality")) or "average"
    if website_quality not in {"strong", "average", "weak"}:
        website_quality = "average"

    # === V3: MESSAGE VARIANT FIELDS ===
    variant_id = f"{_lower(company[:10] if company else 'unknown')}_{score.cis_routing_band[:3]}_{int(datetime.now(timezone.utc).timestamp())}"
    motion_type_targeted = _map_motion_type_to_message_family(score.trigger, score.motion_score)
    spend_context_tag = spend_triggers[0] if spend_triggers else "no_trigger"
    hypothesis_label = _generate_hypothesis_label(score.trigger, score.cis_routing_band)
    v3_routing_band = score.cis_routing_band
    variant_dimension = _extract_variant_dimension(score.trigger, spend_context_tag, hypothesis_label, v3_routing_band)

    # === VARIANT PURITY ENFORCEMENT (NEW) ===
    # PHASE 2 requires: each variant differs on exactly ONE axis from baseline (0,0,0)
    baseline_variant = VariantExperimentalDimension(spend_axis=0, motion_axis=0, urgency_axis=0)
    is_pure = variant_dimension.purity_check(baseline_variant)
    
    if not is_pure:
        # Safety: variant violates factorial design; reset to baseline
        # This prevents contamination of learning signal
        variant_dimension = baseline_variant
        purity_note = f"; PURITY_RESET: was {variant_dimension.spend_axis}{variant_dimension.motion_axis}{variant_dimension.urgency_axis}, reset to baseline"
    else:
        purity_note = ""

    # === V3: ADD TO NOTES ===
    cis_notes = "; ".join([
        f"cis={score.conversion_intent_score}",
        f"cis_band={v3_routing_band}",
        f"cis_spend={score.cis_components['spend_trajectory']}",
        f"cis_motion={score.cis_components['motion_signal']}",
        f"cis_firmographic={score.cis_components['firmographic_fit']}",
        f"cis_linkedin={score.cis_components['linkedin_constraint']}",
        f"variant_id={variant_id}",
        f"variant_dim=spend{variant_dimension.spend_axis}motion{variant_dimension.motion_axis}urgency{variant_dimension.urgency_axis}",
        f"variant_purity={'✓' if is_pure else '✗ RESET'}{purity_note}",
    ])

    notes = "; ".join(
        [
            "candidate_pool=true",
            f"spend_eligible={'true' if spend_eligible else 'false'}",
            f"spend_trigger_count={len(spend_triggers)}",
            f"spend_triggers={'+'.join(spend_triggers) if spend_triggers else 'none'}",
            f"message_angle={message_angle}",
            f"motion_class={motion_class}",
            f"motion_score={score.motion_score}",
            f"buying_intensity_score={score.buying_intensity}",
            f"motion_signals={score.trigger}+{'+'.join(score.reasons) or 'none'}",
            f"pressure_tier={score.pressure_tier}",
            f"urgency_proxy={'true' if score.urgency_proxy else 'false'}",
            f"pressure_reasons={'+'.join(score.reasons) or 'none'}",
            cis_notes,
            "LinkedIn is not scored here; use it only as final binary verification before send.",
        ]
    )

    output = {
        "company": company,
        "website": website,
        "first_name": first_name,
        "role": role,
        "industry": industry,
        "employee_count": employee_count,
        "location": location,
        "trigger": score.trigger,
        "linkedin_url": linkedin_url,
        "website_quality": website_quality,
        "linkedin_quality": linkedin_quality,
        "fit_score": str(score.fit_score),
        "message_version": "credibility_v1",
        "service_angle": score.service_angle,
        "status": "LEARNING",
        "notes": notes,
    }
    return ScoredCandidate(
        row={field: output.get(field, "") for field in schema_fields},
        motion_class=motion_class,
        score=score,
        spend_eligible=spend_eligible,
        spend_triggers=spend_triggers,
        message_angle=message_angle,
        v3_routing_band=v3_routing_band,
        message_variant_id=variant_id,
        motion_type_targeted=motion_type_targeted,
        spend_context_tag=spend_context_tag,
        hypothesis_label=hypothesis_label,
        variant_dimension=variant_dimension,
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def dedupe(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for row in rows:
        key = (_lower(row.get("company")), _lower(row.get("website")))
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _append_jsonl(path: Path, records: list[dict], *, replace: bool) -> None:
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if replace else "a"
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


def _merged_rows(path: Path, rows: list[dict[str, str]], *, replace: bool) -> list[dict[str, str]]:
    existing: list[dict[str, str]] = []
    if path.exists() and not replace:
        existing = read_csv(path)
    return dedupe(existing + rows)


def _sample_possible(candidates: list[ScoredCandidate], size: int, seed: int) -> list[ScoredCandidate]:
    if size <= 0 or len(candidates) <= size:
        return candidates
    indexed = list(enumerate(candidates))
    rng = random.Random(seed)
    sampled_idx = {idx for idx, _ in rng.sample(indexed, size)}
    return [candidate for idx, candidate in enumerate(candidates) if idx in sampled_idx]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate motion-classified Credibility Launch candidates.")
    parser.add_argument("--input", required=True, type=Path, help="Structured source CSV export to score.")
    parser.add_argument("--output", type=Path, default=DEFAULT_POSSIBLE_OUTPUT, help="POSSIBLE lane CSV to write.")
    parser.add_argument("--hot-output", type=Path, default=DEFAULT_HOT_OUTPUT, help="HOT lane CSV to write when live routing is enabled.")
    parser.add_argument("--shadow-log", type=Path, default=DEFAULT_SHADOW_LOG, help="JSONL decision log for shadow-mode analysis.")
    parser.add_argument("--discard-log", type=Path, default=DEFAULT_DISCARD_LOG, help="JSONL log for NO-motion candidates.")
    parser.add_argument("--replace", action="store_true", help="Replace output instead of appending to existing rows.")
    parser.add_argument("--limit", type=int, default=1000, help="Maximum source candidates to evaluate before routing.")
    parser.add_argument("--min-buying-intensity", type=int, default=0, help="Optional minimum Buying Intensity Score to keep for routing/logging.")
    parser.add_argument("--hot-threshold", type=int, help="Override MOTION_HOT_THRESHOLD.")
    parser.add_argument("--possible-threshold", type=int, help="Override MOTION_POSSIBLE_THRESHOLD.")
    parser.add_argument("--hot-cap", type=int, help="Override MOTION_HOT_CAP.")
    parser.add_argument("--possible-sample-size", type=int, help="Override MOTION_POSSIBLE_SAMPLE_SIZE.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for POSSIBLE sampling.")
    parser.add_argument("--shadow-mode", action="store_true", help="Force shadow mode (no HOT routing writes).")
    parser.add_argument("--live-route", action="store_true", help="Force live HOT routing writes.")
    args = parser.parse_args()

    if args.shadow_mode and args.live_route:
        raise SystemExit("Use only one of --shadow-mode or --live-route")

    schema = _load_schema()
    fields = list(schema["fields"])

    settings = _load_motion_settings()
    if args.hot_threshold is not None:
        settings = MotionSettings(
            hot_threshold=max(0, min(10, args.hot_threshold)),
            possible_threshold=settings.possible_threshold,
            hot_cap=settings.hot_cap,
            possible_sample_size=settings.possible_sample_size,
            shadow_mode=settings.shadow_mode,
            spend_filter_required=settings.spend_filter_required,
            spend_min_trigger_count=settings.spend_min_trigger_count,
            random_seed=settings.random_seed,
        )
    if args.possible_threshold is not None:
        settings = MotionSettings(
            hot_threshold=settings.hot_threshold,
            possible_threshold=max(0, min(settings.hot_threshold, args.possible_threshold)),
            hot_cap=settings.hot_cap,
            possible_sample_size=settings.possible_sample_size,
            shadow_mode=settings.shadow_mode,
            spend_filter_required=settings.spend_filter_required,
            spend_min_trigger_count=settings.spend_min_trigger_count,
            random_seed=settings.random_seed,
        )
    if args.hot_cap is not None:
        settings = MotionSettings(
            hot_threshold=settings.hot_threshold,
            possible_threshold=settings.possible_threshold,
            hot_cap=max(1, args.hot_cap),
            possible_sample_size=settings.possible_sample_size,
            shadow_mode=settings.shadow_mode,
            spend_filter_required=settings.spend_filter_required,
            spend_min_trigger_count=settings.spend_min_trigger_count,
            random_seed=settings.random_seed,
        )
    if args.possible_sample_size is not None:
        settings = MotionSettings(
            hot_threshold=settings.hot_threshold,
            possible_threshold=settings.possible_threshold,
            hot_cap=settings.hot_cap,
            possible_sample_size=max(0, args.possible_sample_size),
            shadow_mode=settings.shadow_mode,
            spend_filter_required=settings.spend_filter_required,
            spend_min_trigger_count=settings.spend_min_trigger_count,
            random_seed=settings.random_seed,
        )
    settings = MotionSettings(
        hot_threshold=settings.hot_threshold,
        possible_threshold=settings.possible_threshold,
        hot_cap=settings.hot_cap,
        possible_sample_size=settings.possible_sample_size,
        shadow_mode=(True if args.shadow_mode else False if args.live_route else settings.shadow_mode),
        spend_filter_required=settings.spend_filter_required,
        spend_min_trigger_count=settings.spend_min_trigger_count,
        random_seed=args.seed,
    )

    source_rows = read_csv(args.input)

    candidates = [build_candidate_row(row, fields, settings) for row in source_rows[: args.limit]]
    candidates = [candidate for candidate in candidates if candidate.score.buying_intensity >= args.min_buying_intensity]

    spend_eligible_candidates = [candidate for candidate in candidates if candidate.spend_eligible]
    no_spend_candidates = [candidate for candidate in candidates if not candidate.spend_eligible]

    hot_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "HOT"]
    possible_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "POSSIBLE"]
    no_candidates = [candidate for candidate in spend_eligible_candidates if candidate.motion_class == "NO"]

    hot_candidates.sort(key=lambda candidate: candidate.score.motion_score, reverse=True)
    hot_candidates = hot_candidates[: settings.hot_cap]

    live_hot_candidates: list[ScoredCandidate] = []
    blocked_hot_candidates: list[ScoredCandidate] = []
    for candidate in hot_candidates:
        linkedin_quality = _lower(candidate.row.get("linkedin_quality"))
        if linkedin_quality in {"weak", "missing"}:
            live_hot_candidates.append(candidate)
        else:
            blocked_hot_candidates.append(candidate)

    possible_candidates = possible_candidates + blocked_hot_candidates
    sampled_possible = _sample_possible(
        possible_candidates,
        settings.possible_sample_size,
        settings.random_seed,
    )

    possible_rows = [candidate.row for candidate in sampled_possible]
    possible_merged = _merged_rows(args.output, possible_rows, replace=args.replace)
    write_csv(args.output, fields, possible_merged)

    hot_written = 0
    hot_output_rows = [candidate.row for candidate in live_hot_candidates]
    if not settings.shadow_mode and hot_output_rows:
        hot_merged = _merged_rows(args.hot_output, hot_output_rows, replace=args.replace)
        write_csv(args.hot_output, fields, hot_merged)
        hot_written = len(hot_output_rows)

    now = datetime.now(timezone.utc).isoformat()
    
    # === V3: LOAD BASELINE DISTRIBUTIONS (FROZEN, NEVER UPDATED) ===
    baselines = load_baseline_distributions()
    v2_baseline = baselines.get("v2", {}).get("scores", [])
    v3_baseline = baselines.get("v3", {}).get("scores", [])
    
    shadow_records: list[dict] = []
    for candidate in candidates:
        effective_route = candidate.motion_class
        if not candidate.spend_eligible:
            effective_route = "NO_SPEND"
        if candidate.motion_class == "HOT" and _lower(candidate.row.get("linkedin_quality")) not in {"weak", "missing"}:
            effective_route = "POSSIBLE_LINKEDIN_UNVERIFIED"
        if candidate.motion_class == "HOT" and settings.shadow_mode:
            effective_route = "HOT_SHADOW_ONLY"
        
        # === V3: COMPUTE PERCENTILE RANKS ===
        v2_score_scaled = int(candidate.score.motion_score * 10)
        v3_score = candidate.score.conversion_intent_score
        
        # === V3 DIVERGENT: COMPUTE FORCED DIVERGENCE SCORE ===
        v3_divergent_score = compute_conversion_intent_score_divergent(
            candidate.row,
            candidate.score.motion_score,
            candidate.score.buying_intensity,
            candidate.spend_triggers,
        )
        
        v2_percentile = compute_percentile_rank(v2_score_scaled, v2_baseline)
        v3_percentile = compute_percentile_rank(v3_score, v3_baseline)
        v3_divergent_percentile = compute_percentile_rank(v3_divergent_score, v3_baseline)
        percentile_drift = abs(v3_percentile - v2_percentile)
        bucket_alignment = "aligned" if percentile_drift <= 15 else "diverged"
        
        # === V3: EXTRACT VARIANT DETAILS ===
        variant_dim_str = f"spend_{candidate.variant_dimension.spend_axis}_motion_{candidate.variant_dimension.motion_axis}_urgency_{candidate.variant_dimension.urgency_axis}"
        
        record = {
            "timestamp": now,
            "company": candidate.row.get("company", ""),
            "website": candidate.row.get("website", ""),
            "motion_class": candidate.motion_class,
            "motion_score": candidate.score.motion_score,
            "buying_intensity_score": candidate.score.buying_intensity,
            "trigger": candidate.score.trigger,
            "spend_eligible": candidate.spend_eligible,
            "spend_triggers": list(candidate.spend_triggers),
            "message_angle": candidate.message_angle,
            "linkedin_quality": candidate.row.get("linkedin_quality", ""),
            "effective_route": effective_route,
            "reasons": list(candidate.score.reasons),
            "shadow_mode": settings.shadow_mode,
            # === V3 ENRICHMENT ===
            "v2_motion_score": candidate.score.motion_score,
            "v2_percentile": v2_percentile,
            "v3_cis": v3_score,
            "v3_percentile": v3_percentile,
            "v3_divergent_cis": v3_divergent_score,
            "v3_divergent_percentile": v3_divergent_percentile,
            "v3_routing_band": candidate.v3_routing_band,
            "percentile_drift": percentile_drift,
            "bucket_alignment": bucket_alignment,
            "message_variant_id": candidate.message_variant_id,
            "variant_dimension": variant_dim_str,
            "motion_type_targeted": candidate.motion_type_targeted,
            "spend_context_tag": candidate.spend_context_tag,
            "hypothesis_label": candidate.hypothesis_label,
            "cis_components": candidate.score.cis_components,
        }
        shadow_records.append(record)

    _append_jsonl(args.shadow_log, shadow_records, replace=args.replace)

    discard_records = [
        {
            "timestamp": now,
            "company": candidate.row.get("company", ""),
            "website": candidate.row.get("website", ""),
            "motion_class": "NO",
            "motion_score": candidate.score.motion_score,
            "buying_intensity_score": candidate.score.buying_intensity,
            "trigger": candidate.score.trigger,
            "spend_eligible": candidate.spend_eligible,
            "spend_triggers": list(candidate.spend_triggers),
            "message_angle": candidate.message_angle,
            "reasons": list(candidate.score.reasons),
        }
        for candidate in no_candidates
    ] + [
        {
            "timestamp": now,
            "company": candidate.row.get("company", ""),
            "website": candidate.row.get("website", ""),
            "motion_class": candidate.motion_class,
            "motion_score": candidate.score.motion_score,
            "buying_intensity_score": candidate.score.buying_intensity,
            "trigger": candidate.score.trigger,
            "spend_eligible": False,
            "spend_triggers": list(candidate.spend_triggers),
            "message_angle": candidate.message_angle,
            "reasons": list(candidate.score.reasons),
            "discard_reason": "no_spend_trigger",
        }
        for candidate in no_spend_candidates
    ]
    _append_jsonl(args.discard_log, discard_records, replace=args.replace)

    print(
        "candidate_generation PASS",
        {
            "source_rows": len(source_rows),
            "evaluated_rows": len(candidates),
            "spend_eligible": len(spend_eligible_candidates),
            "no_spend": len(no_spend_candidates),
            "hot_total": len(hot_candidates),
            "hot_routed": hot_written,
            "possible_sampled": len(sampled_possible),
            "discarded": len(no_candidates) + len(no_spend_candidates),
            "shadow_mode": settings.shadow_mode,
            "possible_output": str(args.output),
            "hot_output": str(args.hot_output),
            "shadow_log": str(args.shadow_log),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())