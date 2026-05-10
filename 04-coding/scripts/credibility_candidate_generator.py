#!/usr/bin/env python3
"""
Credibility Launch Candidate Generator

Deterministically converts structured source exports into pre-scored Signal Lab
rows. This is a motion-signal filter, not a LinkedIn evaluator.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


BASE = Path(__file__).resolve().parents[2]
SALES_DIR = BASE / "06-sales"
SCHEMA_PATH = SALES_DIR / "credibility-launch-lead-schema.json"
DEFAULT_OUTPUT = SALES_DIR / "credibility-launch-signal-lab.csv"

FOUNDER_TERMS = ("founder", "co-founder", "ceo", "owner", "managing director", "partner")
B2B_TERMS = (
    "b2b",
    "saas",
    "software",
    "enterprise",
    "service",
    "services",
    "agency",
    "consulting",
    "professional",
    "legal",
    "accounting",
    "recruiting",
    "staffing",
    "sales",
)
LAUNCH_TERMS = ("yc", "launch", "launched", "batch", "demo day", "product hunt")
FUNDING_TERMS = ("funding", "funded", "pre-seed", "seed", "raised", "investment")
HIRING_TERMS = ("hiring", "job", "jobs", "careers", "role", "roles")
FOUNDER_VISIBILITY_TERMS = ("posting", "building", "founder-led", "public", "launching", "selling")


@dataclass(frozen=True)
class CandidateScore:
    motion_score: int
    trigger: str
    fit_score: int
    service_angle: str
    reasons: tuple[str, ...]


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


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


def score_candidate(row: dict[str, str]) -> CandidateScore:
    role = _get(row, "role", "title", "founder_role")
    industry = _get(row, "industry", "category", "tags", "description")
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
    employee_raw = _get(row, "employee_count", "employees", "team_size", "team size")
    employee_count = _employee_count(employee_raw)
    jobs_count = _employee_count(_get(row, "jobs_count", "job_count", "open_roles")) or 0

    score = 0
    reasons: list[str] = []

    if _contains_any(role, FOUNDER_TERMS):
        score += 2
        reasons.append("founder_led")

    if _contains_any(industry, B2B_TERMS):
        score += 2
        reasons.append("b2b_or_trust_based_offer")

    if employee_count is not None and 2 <= employee_count <= 20:
        score += 1
        reasons.append("team_2_20")

    has_hiring = jobs_count > 0 or _truthy(_get(row, "hiring", "hiring_signal")) or _contains_any(trigger_text, HIRING_TERMS)
    has_launch = _truthy(_get(row, "launch", "launch_signal")) or _contains_any(trigger_text, LAUNCH_TERMS)
    has_funding = _truthy(_get(row, "funding", "funding_signal")) or _contains_any(trigger_text, FUNDING_TERMS)
    has_founder_visibility = _truthy(_get(row, "founder_visibility", "founder_active")) or _contains_any(trigger_text, FOUNDER_VISIBILITY_TERMS)

    if has_hiring:
        score += 2
        reasons.append("hiring_signal")

    if has_launch:
        score += 2
        reasons.append("launch_or_yc_signal")

    if has_funding:
        score += 2
        reasons.append("funding_signal")

    if has_founder_visibility:
        score += 1
        reasons.append("founder_visibility_signal")

    if _get(row, "website", "company_website", "url"):
        score += 1
        reasons.append("website_present")

    if _lower(_get(row, "website_quality")) == "strong":
        score += 1
        reasons.append("strong_website_proxy")

    if has_hiring:
        trigger = "hiring"
    elif has_funding:
        trigger = "recent_growth"
    elif has_launch:
        trigger = "recently_launched"
    else:
        trigger = "clear_service_offer"

    # This is a pre-LinkedIn motion score. Keep generated rows in Signal Lab.
    fit_score = 6 if score >= 7 else 5
    service_angle = "credibility_gap" if _lower(_get(row, "linkedin_url")) else "linkedin_rebuild"

    return CandidateScore(
        motion_score=min(score, 10),
        trigger=trigger,
        fit_score=fit_score,
        service_angle=service_angle,
        reasons=tuple(reasons),
    )


def to_signal_lab_row(row: dict[str, str], schema_fields: list[str]) -> dict[str, str]:
    score = score_candidate(row)
    company = _get(row, "company", "company_name", "name")
    first_name = _get(row, "first_name", "founder_first_name")
    role = _get(row, "role", "title", "founder_role")
    website = _get(row, "website", "company_website", "url")
    industry = _get(row, "industry", "category", "tags", "description")
    employee_count = _get(row, "employee_count", "employees", "team_size", "team size")
    location = _get(row, "location", "hq", "city")
    linkedin_url = _get(row, "linkedin_url", "company_linkedin", "linkedin")
    website_quality = _lower(_get(row, "website_quality")) or "average"
    if website_quality not in {"strong", "average", "weak"}:
        website_quality = "average"

    notes = "; ".join(
        [
            "candidate_pool=true",
            "linkedin_status=unknown",
            f"motion_score={score.motion_score}",
            f"motion_reasons={'+'.join(score.reasons) or 'none'}",
            "LinkedIn is not scored here; inspect only if this row is in the top review slice.",
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
        "linkedin_quality": "unknown",
        "fit_score": str(score.fit_score),
        "message_version": "credibility_v1",
        "service_angle": score.service_angle,
        "status": "LEARNING",
        "notes": notes,
    }
    return {field: output.get(field, "") for field in schema_fields}


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate pre-scored Credibility Launch Signal Lab candidates.")
    parser.add_argument("--input", required=True, type=Path, help="Structured source CSV export to score.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Signal Lab CSV to write.")
    parser.add_argument("--replace", action="store_true", help="Replace output instead of appending to existing rows.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum generated candidates to keep after ranking.")
    parser.add_argument("--min-motion-score", type=int, default=6, help="Minimum motion score to include.")
    args = parser.parse_args()

    schema = _load_schema()
    fields = list(schema["fields"])

    source_rows = read_csv(args.input)
    generated = [to_signal_lab_row(row, fields) for row in source_rows]
    generated = [row for row in generated if int(row["fit_score"]) >= 5 and f"motion_score=" in row["notes"]]
    generated = [row for row in generated if int(row["notes"].split("motion_score=", 1)[1].split(";", 1)[0]) >= args.min_motion_score]
    generated.sort(
        key=lambda row: int(row["notes"].split("motion_score=", 1)[1].split(";", 1)[0]),
        reverse=True,
    )
    generated = generated[: args.limit]

    existing: list[dict[str, str]] = []
    if args.output.exists() and not args.replace:
        existing = read_csv(args.output)

    rows = dedupe(existing + generated)
    write_csv(args.output, fields, rows)

    print(
        "candidate_generation PASS",
        {
            "source_rows": len(source_rows),
            "generated_rows": len(generated),
            "output_rows": len(rows),
            "output": str(args.output),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())