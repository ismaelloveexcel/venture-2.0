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


@dataclass(frozen=True)
class MotionSettings:
    hot_threshold: int
    possible_threshold: int
    hot_cap: int
    possible_sample_size: int
    shadow_mode: bool
    random_seed: int


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
        random_seed=42,
    )


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

    return CandidateScore(
        buying_intensity=min(buying_intensity, 11),
        motion_score=motion_score,
        trigger=trigger,
        fit_score=fit_score,
        service_angle=service_angle,
        pressure_tier=pressure_tier,
        urgency_proxy=urgency_proxy,
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class ScoredCandidate:
    row: dict[str, str]
    motion_class: str
    score: CandidateScore


def _normalized_linkedin_quality(row: dict[str, str]) -> str:
    raw = _lower(_get(row, "linkedin_quality"))
    if raw in ALLOWED_LINKEDIN_QUALITY:
        return raw
    return "unknown"


def build_candidate_row(row: dict[str, str], schema_fields: list[str], settings: MotionSettings) -> ScoredCandidate:
    score = score_candidate(row)
    motion_class = _motion_class(score.motion_score, settings)
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

    notes = "; ".join(
        [
            "candidate_pool=true",
            f"motion_class={motion_class}",
            f"motion_score={score.motion_score}",
            f"buying_intensity_score={score.buying_intensity}",
            f"motion_signals={score.trigger}+{'+'.join(score.reasons) or 'none'}",
            f"pressure_tier={score.pressure_tier}",
            f"urgency_proxy={'true' if score.urgency_proxy else 'false'}",
            f"pressure_reasons={'+'.join(score.reasons) or 'none'}",
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
            random_seed=settings.random_seed,
        )
    if args.possible_threshold is not None:
        settings = MotionSettings(
            hot_threshold=settings.hot_threshold,
            possible_threshold=max(0, min(settings.hot_threshold, args.possible_threshold)),
            hot_cap=settings.hot_cap,
            possible_sample_size=settings.possible_sample_size,
            shadow_mode=settings.shadow_mode,
            random_seed=settings.random_seed,
        )
    if args.hot_cap is not None:
        settings = MotionSettings(
            hot_threshold=settings.hot_threshold,
            possible_threshold=settings.possible_threshold,
            hot_cap=max(1, args.hot_cap),
            possible_sample_size=settings.possible_sample_size,
            shadow_mode=settings.shadow_mode,
            random_seed=settings.random_seed,
        )
    if args.possible_sample_size is not None:
        settings = MotionSettings(
            hot_threshold=settings.hot_threshold,
            possible_threshold=settings.possible_threshold,
            hot_cap=settings.hot_cap,
            possible_sample_size=max(0, args.possible_sample_size),
            shadow_mode=settings.shadow_mode,
            random_seed=settings.random_seed,
        )
    settings = MotionSettings(
        hot_threshold=settings.hot_threshold,
        possible_threshold=settings.possible_threshold,
        hot_cap=settings.hot_cap,
        possible_sample_size=settings.possible_sample_size,
        shadow_mode=(True if args.shadow_mode else False if args.live_route else settings.shadow_mode),
        random_seed=args.seed,
    )

    source_rows = read_csv(args.input)

    candidates = [build_candidate_row(row, fields, settings) for row in source_rows[: args.limit]]
    candidates = [candidate for candidate in candidates if candidate.score.buying_intensity >= args.min_buying_intensity]

    hot_candidates = [candidate for candidate in candidates if candidate.motion_class == "HOT"]
    possible_candidates = [candidate for candidate in candidates if candidate.motion_class == "POSSIBLE"]
    no_candidates = [candidate for candidate in candidates if candidate.motion_class == "NO"]

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
    shadow_records: list[dict] = []
    for candidate in candidates:
        effective_route = candidate.motion_class
        if candidate.motion_class == "HOT" and _lower(candidate.row.get("linkedin_quality")) not in {"weak", "missing"}:
            effective_route = "POSSIBLE_LINKEDIN_UNVERIFIED"
        if candidate.motion_class == "HOT" and settings.shadow_mode:
            effective_route = "HOT_SHADOW_ONLY"
        record = {
            "timestamp": now,
            "company": candidate.row.get("company", ""),
            "website": candidate.row.get("website", ""),
            "motion_class": candidate.motion_class,
            "motion_score": candidate.score.motion_score,
            "buying_intensity_score": candidate.score.buying_intensity,
            "trigger": candidate.score.trigger,
            "linkedin_quality": candidate.row.get("linkedin_quality", ""),
            "effective_route": effective_route,
            "reasons": list(candidate.score.reasons),
            "shadow_mode": settings.shadow_mode,
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
            "reasons": list(candidate.score.reasons),
        }
        for candidate in no_candidates
    ]
    _append_jsonl(args.discard_log, discard_records, replace=args.replace)

    print(
        "candidate_generation PASS",
        {
            "source_rows": len(source_rows),
            "evaluated_rows": len(candidates),
            "hot_total": len(hot_candidates),
            "hot_routed": hot_written,
            "possible_sampled": len(sampled_possible),
            "discarded": len(no_candidates),
            "shadow_mode": settings.shadow_mode,
            "possible_output": str(args.output),
            "hot_output": str(args.hot_output),
            "shadow_log": str(args.shadow_log),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())