#!/usr/bin/env python3
"""
Prospect Builder — Rule-Based Sourcing Engine

Primary source: Apollo.io People Search API (B2B leads by title/industry/company size)
Fallback:       Hunter.io domain search
Demo mode:      Template dataset (--demo flag)

Output: CSV with validation_status (READY | REVIEW | REJECT), validation_reason,
source (demo_template | apollo | hunter_enriched | fallback_template), run_id.
Each run overwrites DATA_BASE/06-sales/prospects.csv by default (no append).

Usage:
    python prospect_builder.py                          # Apollo (real leads)
    python prospect_builder.py --demo                  # template data for testing
    python prospect_builder.py --output-file 06-sales/prospects.csv
    python prospect_builder.py --count 25 --cohort1-csv 06-sales/cohort1-prospects-template.csv
"""

import argparse
import csv
import json
import random
import sys
import pathlib
import time
import uuid
from typing import Optional
import httpx
from dotenv import load_dotenv
import os

BASE = pathlib.Path(__file__).resolve().parents[2]
REPO_ROOT = BASE
load_dotenv(BASE / ".env")

from runtime_config import resolve_data_base, resolve_venture_db_path

DATA_BASE = resolve_data_base(REPO_ROOT)

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
OUTPUT_FILE = DATA_BASE / "06-sales" / "prospects.csv"

# ── Apollo ICP targeting — Cohort 1 (Auditbound outbound agencies) ───────────
# Titles: founder / co-founder / owner (Apollo matches similar phrasing).
APOLLO_TITLES = [
    "founder",
    "co-founder",
    "owner",
]

# Industry tag names (Apollo taxonomy; relax strings if API returns 422).
APOLLO_INDUSTRIES = [
    "marketing services",
    "lead generation",
    "sales consulting",
    "outbound agency",
]

# Keyword filter across people + orgs (Apollo q_keywords).
APOLLO_Q_KEYWORDS = "outbound cold email done-for-you lead gen"

# Employer headcount range "min,max" per Apollo docs.
APOLLO_EMPLOYEE_RANGES = ["1,10"]

# Pain-signal heuristics mapped from industry/title combos
_PAIN_SIGNAL_MAP = {
    "marketing services": "client_acquisition",
    "lead generation": "scaling_outbound",
    "sales consulting": "pipeline_visibility",
    "outbound agency": "scaling_outbound",
}


def _infer_pain_signal(industry: str, title: str) -> str:
    industry_lower = (industry or "").lower()
    for key, signal in _PAIN_SIGNAL_MAP.items():
        if key in industry_lower:
            return signal
    title_lower = (title or "").lower()
    if any(w in title_lower for w in ("sales", "revenue", "growth")):
        return "scaling_outbound"
    if any(w in title_lower for w in ("founder", "owner", "ceo")):
        return "client_acquisition"
    return "outreach_efficiency"


def fetch_prospects_from_apollo(count: int = 50) -> list[dict]:
    """
    Pull verified B2B leads from Apollo.io People Search API.

    Filters by decision-maker titles and target industries.
    Maps Apollo response fields → prospect_builder CSV schema.
    Free tier: 50 verified contact exports/month.

    Apollo docs: People Search (POST /v1/people/search). Emails may require separate enrichment on some tiers.
    """
    if not APOLLO_API_KEY:
        print("[warn] APOLLO_API_KEY not set — skipping Apollo sourcing")
        return []

    prospects = []
    page = 1
    per_page = min(count, 25)  # Apollo free tier caps per-page at 25

    try:
        with httpx.Client(timeout=15) as client:
            while len(prospects) < count:
                payload = {
                    "person_titles": APOLLO_TITLES,
                    "include_similar_titles": False,
                    "organization_industry_tag_ids": [],
                    "q_organization_industry_tag_names": APOLLO_INDUSTRIES,
                    "organization_num_employees_ranges": APOLLO_EMPLOYEE_RANGES,
                    "q_keywords": APOLLO_Q_KEYWORDS,
                    "contact_email_status": ["verified"],
                    "per_page": per_page,
                    "page": page,
                }

                r = client.post(
                    "https://api.apollo.io/v1/people/search",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
                        "X-Api-Key": APOLLO_API_KEY,
                    },
                )

                if r.status_code == 401:
                    print("[fail] Apollo API key invalid (401). Check APOLLO_API_KEY.")
                    break
                if r.status_code == 422:
                    print(f"[fail] Apollo request error (422): {r.text[:300]}")
                    break
                if r.status_code != 200:
                    print(f"[warn] Apollo returned {r.status_code}: {r.text[:200]}")
                    break

                data = r.json()
                people = data.get("people") or data.get("contacts") or []

                if not people:
                    break  # exhausted results

                for person in people:
                    # Map Apollo fields → prospect_builder schema
                    org = person.get("organization") or {}
                    first = (person.get("first_name") or "").strip()
                    last = (person.get("last_name") or "").strip()
                    name = f"{first} {last}".strip() or person.get("name", "")
                    email = (person.get("email") or "").strip()
                    title = (person.get("title") or "").strip()
                    company = (
                        org.get("name") or person.get("organization_name") or ""
                    ).strip()
                    domain = (
                        org.get("primary_domain")
                        or person.get("organization_domain")
                        or ""
                    ).strip()
                    industry = (
                        org.get("industry") or person.get("industry") or ""
                    ).strip()
                    linkedin = (person.get("linkedin_url") or "").strip()
                    founded_raw = org.get("founded_year")
                    if founded_raw is None or founded_raw == "":
                        founded_year: str | int = ""
                    else:
                        founded_year = founded_raw
                    ps = _infer_pain_signal(industry, title)
                    pers_note = ""
                    if company and ps:
                        pers_note = f"{company}: {ps.replace('_', ' ')}."
                    elif ps:
                        pers_note = ps.replace("_", " ")

                    prospects.append(
                        {
                            "company_name": company,
                            "domain": domain,
                            "name": name,
                            "first_name": first,
                            "last_name": last,
                            "email": email,
                            "role": title,
                            "industry": industry,
                            "pain_signal": ps,
                            "linkedin_url": linkedin,
                            "founded_year": founded_year,
                            "estimated_clients": "",
                            "personalisation_note": pers_note,
                            "source": "apollo",
                        }
                    )

                    if len(prospects) >= count:
                        break

                total_pages = data.get("pagination", {}).get("total_pages", 1)
                if page >= total_pages:
                    break
                page += 1

    except Exception as e:
        print(f"[warn] Apollo API call failed: {e}")

    print(f"[ok] Apollo sourced {len(prospects)} prospects")
    return prospects


# Hard filter rules (deterministic only)
REJECT_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"}
EXCLUDE_TITLE_MARKERS = (
    "assistant",
    "intern",
    "coordinator",
    " receptionist",
    "associate ",
    " junior",
    "jr.",
)

DECISION_TITLE_MARKERS = (
    "founder",
    "co-founder",
    "ceo",
    "coo",
    "cfo",
    "cto",
    "owner",
    "president",
    "chief ",
    "head ",
    " head",
    "director",
    "vp",
    "vice president",
    "principal",
    "partner",
    "managing director",
    "general manager",
)


def _title_excluded(title_lower: str) -> bool:
    return any(m in title_lower for m in EXCLUDE_TITLE_MARKERS)


def _title_decision_like(title_lower: str) -> bool:
    if _title_excluded(title_lower):
        return False
    return any(m in title_lower for m in DECISION_TITLE_MARKERS)


PROSPECT_CSV_FIELDNAMES = [
    "company_name",
    "domain",
    "name",
    "email",
    "role",
    "industry",
    "pain_signal",
    "linkedin_url",
    "validation_status",
    "validation_reason",
    "source",
    "run_id",
]
REQUIRED_PROSPECT_COLUMNS = frozenset(PROSPECT_CSV_FIELDNAMES)

# Cohort 1 list shape (06-sales/cohort1-prospects-template.csv); optional second export.
COHORT1_CSV_FIELDNAMES: tuple[str, ...] = (
    "first_name",
    "last_name",
    "company",
    "role",
    "linkedin_url",
    "founded_year",
    "estimated_clients",
    "email",
    "personalisation_note",
)


def _split_display_name(full: str) -> tuple[str, str]:
    n = (full or "").strip()
    if not n:
        return "", ""
    parts = n.split(None, 1)
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def eligible_row_to_cohort1_fields(row: dict) -> dict[str, str]:
    """Map internal READY row → cohort1 CSV columns (never emits non-row secrets)."""
    first = (row.get("first_name") or "").strip()
    last = (row.get("last_name") or "").strip()
    if not first and not last:
        first, last = _split_display_name(str(row.get("name") or ""))
    fy_raw = row.get("founded_year")
    if fy_raw is None or fy_raw == "":
        fy_s = ""
    else:
        fy_s = str(fy_raw).strip()
    ps = (row.get("pain_signal") or "").strip()
    co = (row.get("company_name") or "").strip()
    role = (row.get("role") or "").strip()
    note = (row.get("personalisation_note") or "").strip()
    if not note and co and ps:
        note = f"{co}: {ps.replace('_', ' ')}."
    elif not note and ps:
        note = ps.replace("_", " ")
    return {
        "first_name": first,
        "last_name": last,
        "company": co,
        "role": role,
        "linkedin_url": (row.get("linkedin_url") or "").strip(),
        "founded_year": fy_s,
        "estimated_clients": (row.get("estimated_clients") or "").strip(),
        "email": (row.get("email") or "").strip(),
        "personalisation_note": note,
    }


def write_cohort1_prospects_csv(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=list(COHORT1_CSV_FIELDNAMES), extrasaction="ignore"
        )
        w.writeheader()
        for r in rows:
            w.writerow(eligible_row_to_cohort1_fields(r))


def resolve_cli_data_path(rel_or_abs: str) -> pathlib.Path:
    """Resolve --output-file / --cohort1-csv: absolute, or relative to DATA_BASE."""
    p = pathlib.Path(rel_or_abs.strip())
    if p.is_absolute():
        return p.resolve()
    return (DATA_BASE / p).resolve()


def validate_prospect(row: dict) -> tuple[str, str]:
    """
    Apply hard rules to classify prospect.

    Returns: (validation_status, validation_reason)
    - READY: decision-like title + valid email + domain
    - REVIEW: ambiguous title, or missing email with strong domain + decision title
    - REJECT: fails hard structural / generic-domain / excluded-title rules
    """

    company = (row.get("company_name") or "").strip()
    domain = (row.get("domain") or "").strip()
    role = (row.get("role") or "").strip()
    role_lower = role.lower()
    email = (row.get("email") or "").strip()

    if not company:
        return "REJECT", "missing_company"

    if not domain:
        return "REJECT", "missing_domain"

    if not role:
        return "REJECT", "missing_role"

    if domain.lower() in REJECT_DOMAINS:
        return "REJECT", "generic_domain"

    if _title_excluded(role_lower):
        return "REJECT", "excluded_title"

    if not _title_decision_like(role_lower):
        return "REVIEW", "ambiguous_title"

    if email and "@" in email and domain.lower() not in REJECT_DOMAINS:
        return "READY", "complete_profile"
    if domain:
        return "REVIEW", "missing_email_strong_domain"
    return "REJECT", "incomplete_profile"


def _assert_prospect_batch_schema(rows: list[dict], run_id: str) -> None:
    from prospect_gate import normalize_email

    rid = (run_id or "").strip()
    for i, r in enumerate(rows):
        missing = sorted(REQUIRED_PROSPECT_COLUMNS - set(r.keys()))
        if missing:
            raise ValueError(f"prospect row {i} missing keys: {missing}")
        if (r.get("validation_status") or "").strip().upper() != "READY":
            raise ValueError(f"prospect row {i}: validation_status must be READY for CSV export")
        if (r.get("run_id") or "").strip() != rid:
            raise ValueError(
                f"prospect row {i}: run_id mismatch (expected {rid!r}, got {r.get('run_id')!r})"
            )
        em = normalize_email(r.get("email"))
        if not em:
            raise ValueError(f"prospect row {i}: email required after gate")
        if (r.get("email") or "") != em:
            raise ValueError(
                f"prospect row {i}: email must be canonical lower(trim); use prospect_gate.normalize_email"
            )


def fetch_prospects_from_hunter(domain_keyword: str, count: int = 50) -> list[dict]:
    """
    Fetch prospects from Hunter.io domain search API.

    Retries with exponential backoff (3 retries after first attempt; delays 2s, 4s, 8s)
    on rate limits / transient errors. On total failure logs a warning and returns [].
    """
    if not HUNTER_API_KEY:
        print("[warn] HUNTER_API_KEY not set. Using template data.")
        return []

    url = "https://api.hunter.io/v2/domain-search"
    params = {
        "domain": domain_keyword,
        "limit": min(count, 100),
        "api_key": HUNTER_API_KEY,
    }

    max_attempts = 4  # initial + 3 retries
    base_delay_s = 2.0

    for attempt in range(max_attempts):
        if attempt > 0:
            delay = base_delay_s * (2 ** (attempt - 1))
            print(
                f"[warn] Hunter retry {attempt}/{max_attempts - 1} after {delay:.0f}s backoff"
            )
            time.sleep(delay)
        try:
            with httpx.Client(timeout=10) as client:
                r = client.get(url, params=params)
        except (httpx.HTTPError, OSError) as e:
            print(f"[warn] Hunter request error: {e}")
            if attempt == max_attempts - 1:
                print(
                    "[warn] Hunter unreachable after retries — skipping Hunter sourcing "
                    "(template fallback may apply if no other source filled quota)."
                )
            continue

        if r.status_code == 200:
            prospects: list[dict] = []
            try:
                data = r.json()
            except json.JSONDecodeError:
                print("[warn] Hunter returned non-JSON body")
                if attempt < max_attempts - 1:
                    continue
                print(
                    "[warn] Hunter unreachable after retries — skipping Hunter sourcing "
                    "(template fallback may apply if no other source filled quota)."
                )
                return []

            for emp in data.get("data", {}).get("employees", []):
                pos = (emp.get("position") or "").strip()
                prospects.append(
                    {
                        "company_name": emp.get("company", ""),
                        "domain": emp.get("domain", ""),
                        "name": emp.get("first_name", ""),
                        "email": emp.get("email", ""),
                        "role": pos,
                        "industry": "saas",
                        "pain_signal": _infer_pain_signal("saas", pos),
                        "linkedin_url": "",
                        "source": "hunter_enriched",
                    }
                )
            return prospects

        retryable = r.status_code == 429 or (500 <= r.status_code < 600)
        print(f"[warn] Hunter API HTTP {r.status_code}: {r.text[:200]!r}")
        if retryable and attempt < max_attempts - 1:
            continue
        if attempt == max_attempts - 1:
            print(
                "[warn] Hunter failed after retries — skipping Hunter sourcing "
                "(template fallback may apply if no other source filled quota)."
            )
        break

    return []


def build_prospect_list(
    industry_keywords: list[str], count: int = 50, allow_template: bool = False
) -> list[dict]:
    """
    Build prospect list from Hunter API.

    Args:
        industry_keywords: domains/keywords to search
        count: number of prospects to fetch
        allow_template: if True, use template data (demo only)
    """

    prospects = []

    # Template dataset (DEMO ONLY - for testing without Hunter API)
    # 50 diverse B2B prospects across ICP verticals
    template_prospects = [
        {
            "company_name": "Digital Growth Agency",
            "domain": "digitalgrowth.io",
            "name": "Sarah Chen",
            "email": "sarah@digitalgrowth.io",
            "role": "Founder",
            "industry": "agency",
            "pain_signal": "hiring_for_sales",
        },
        {
            "company_name": "RevOps Coaching",
            "domain": "revenueops.coach",
            "name": "Mike Torres",
            "email": "mike@revenueops.coach",
            "role": "Head of Growth",
            "industry": "coaching",
            "pain_signal": "scaling_outbound",
        },
        {
            "company_name": "SaaS Analytics Pro",
            "domain": "saasanalytics.com",
            "name": "James Liu",
            "email": None,
            "role": "CEO",
            "industry": "saas",
            "pain_signal": "low_reply_rate",
        },
        {
            "company_name": "Marketing Forge",
            "domain": "marketing-forge.com",
            "name": "Lisa Wong",
            "email": "lisa@marketing-forge.com",
            "role": "Director of Sales",
            "industry": "agency",
            "pain_signal": "leads_declining",
        },
        {
            "company_name": "Sales Acceleration Corp",
            "domain": "salesacc.io",
            "name": "David Park",
            "email": "david@salesacc.io",
            "role": "CEO",
            "industry": "consulting",
            "pain_signal": "competitor_pressure",
        },
        {
            "company_name": "Legal Tech Solutions",
            "domain": "legaltech.ai",
            "name": "Jessica Brown",
            "email": "j.brown@legaltech.ai",
            "role": "Founder",
            "industry": "saas",
            "pain_signal": "churn_rate_high",
        },
        {
            "company_name": "Accounting Plus",
            "domain": "accounting-plus.com",
            "name": "Robert Singh",
            "email": "robert@accounting-plus.com",
            "role": "Managing Partner",
            "industry": "services",
            "pain_signal": "staff_turnover",
        },
        {
            "company_name": "Brand Strategy Labs",
            "domain": "brandstrategy.co",
            "name": "Amanda Foster",
            "email": "amanda@brandstrategy.co",
            "role": "Principal",
            "industry": "agency",
            "pain_signal": "client_acquisition",
        },
        {
            "company_name": "Growth Hacking Academy",
            "domain": "growthhack.academy",
            "name": "Chris Johnson",
            "email": "chris@growthhack.academy",
            "role": "Head of Operations",
            "industry": "coaching",
            "pain_signal": "course_completion_low",
        },
        {
            "company_name": "Consulting Partners LLC",
            "domain": "consulting-partners.com",
            "name": "Michelle Torres",
            "email": "michelle@consulting-partners.com",
            "role": "Director",
            "industry": "consulting",
            "pain_signal": "pipeline_visibility",
        },
        {
            "company_name": "Executive Search Firm",
            "domain": "execsearch.io",
            "name": "Thomas Anderson",
            "email": "thomas@execsearch.io",
            "role": "CEO",
            "industry": "services",
            "pain_signal": "candidate_shortage",
        },
        {
            "company_name": "Content Marketing Co",
            "domain": "contentmarketing.pro",
            "name": "Nicole Davis",
            "email": "nicole@contentmarketing.pro",
            "role": "Founder",
            "industry": "agency",
            "pain_signal": "low_roi",
        },
        {
            "company_name": "Business Coaching Hub",
            "domain": "businesscoach.pro",
            "name": "Kevin Lee",
            "email": "kevin@businesscoach.pro",
            "role": "Owner",
            "industry": "coaching",
            "pain_signal": "client_retention",
        },
        {
            "company_name": "Software Consultancy",
            "domain": "softconsult.net",
            "name": "Amanda Patel",
            "email": "amanda@softconsult.net",
            "role": "Managing Director",
            "industry": "consulting",
            "pain_signal": "project_delivery",
        },
        {
            "company_name": "Financial Advisory Group",
            "domain": "financialadv.com",
            "name": "Paul Henricks",
            "email": "paul@financialadv.com",
            "role": "Partner",
            "industry": "services",
            "pain_signal": "client_lifetime_value",
        },
        {
            "company_name": "Digital Marketing Studios",
            "domain": "digmarketstudio.com",
            "name": "Rachel Green",
            "email": "rachel@digmarketstudio.com",
            "role": "CEO",
            "industry": "agency",
            "pain_signal": "scaling_team",
        },
        {
            "company_name": "Executive Coaching Pro",
            "domain": "excoach.io",
            "name": "Marcus Brown",
            "email": "marcus@excoach.io",
            "role": "Founder",
            "industry": "coaching",
            "pain_signal": "market_awareness",
        },
        {
            "company_name": "Tech Consulting Group",
            "domain": "techconsult.pro",
            "name": "Elena Rodriguez",
            "email": "elena@techconsult.pro",
            "role": "VP of Sales",
            "industry": "consulting",
            "pain_signal": "deal_cycles_long",
        },
        {
            "company_name": "Law Office Management",
            "domain": "lawmgmt.com",
            "name": "Jennifer Martinez",
            "email": "j.martinez@lawmgmt.com",
            "role": "Managing Partner",
            "industry": "services",
            "pain_signal": "client_communication",
        },
        {
            "company_name": "Growth PR Agency",
            "domain": "growthpr.io",
            "name": "Alexander Scott",
            "email": "alexander@growthpr.io",
            "role": "Director",
            "industry": "agency",
            "pain_signal": "media_placement_low",
        },
        {
            "company_name": "Leadership Development",
            "domain": "leadershipdev.net",
            "name": "Sophia Washington",
            "email": "sophia@leadershipdev.net",
            "role": "Owner",
            "industry": "coaching",
            "pain_signal": "program_enrollment",
        },
        {
            "company_name": "Enterprise Solutions",
            "domain": "enterprise-sol.com",
            "name": "George White",
            "email": "george@enterprise-sol.com",
            "role": "CEO",
            "industry": "consulting",
            "pain_signal": "market_differentiation",
        },
        {
            "company_name": "HR Consulting Plus",
            "domain": "hrconsult.io",
            "name": "Victoria Harris",
            "email": "victoria@hrconsult.io",
            "role": "Founder",
            "industry": "services",
            "pain_signal": "employee_retention",
        },
        {
            "company_name": "Performance Marketing",
            "domain": "perfmkt.io",
            "name": "James Mitchell",
            "email": "james@perfmkt.io",
            "role": "Chief Growth Officer",
            "industry": "agency",
            "pain_signal": "attribution_tracking",
        },
        {
            "company_name": "Career Coaching Plus",
            "domain": "careercoach.pro",
            "name": "Patricia Young",
            "email": "patricia@careercoach.pro",
            "role": "Principal Coach",
            "industry": "coaching",
            "pain_signal": "client_onboarding",
        },
        {
            "company_name": "Management Consulting",
            "domain": "mgmtconsult.com",
            "name": "Daniel Chen",
            "email": "daniel@mgmtconsult.com",
            "role": "Managing Partner",
            "industry": "consulting",
            "pain_signal": "proposal_quality",
        },
        {
            "company_name": "Accounting Services LLC",
            "domain": "acctservices.io",
            "name": "Ruth Peterson",
            "email": "ruth@acctservices.io",
            "role": "Director",
            "industry": "services",
            "pain_signal": "tax_deadline_stress",
        },
        {
            "company_name": "Brand Design Studio",
            "domain": "branddesign.pro",
            "name": "Michael Jordan",
            "email": "m.jordan@branddesign.pro",
            "role": "Founder",
            "industry": "agency",
            "pain_signal": "project_scope_creep",
        },
        {
            "company_name": "Sales Training Academy",
            "domain": "salestraining.pro",
            "name": "Linda Evans",
            "email": "linda@salestraining.pro",
            "role": "CEO",
            "industry": "coaching",
            "pain_signal": "rep_performance_tracking",
        },
        {
            "company_name": "Business Strategy Inc",
            "domain": "bizcstrategy.com",
            "name": "Christopher Davis",
            "email": "chris@bizcstrategy.com",
            "role": "Principal Consultant",
            "industry": "consulting",
            "pain_signal": "strategy_execution",
        },
        {
            "company_name": "Tax Advisory Group",
            "domain": "taxadvisory.io",
            "name": "Lauren Wright",
            "email": "lauren@taxadvisory.io",
            "role": "Partner",
            "industry": "services",
            "pain_signal": "client_planning_engagement",
        },
        {
            "company_name": "Social Media Agency",
            "domain": "socialmedia-pro.com",
            "name": "Brandon Lee",
            "email": "brandon@socialmedia-pro.com",
            "role": "Founder",
            "industry": "agency",
            "pain_signal": "content_performance",
        },
        {
            "company_name": "Executive Branding",
            "domain": "exbrand.io",
            "name": "Diane Moore",
            "email": "diane@exbrand.io",
            "role": "Founder",
            "industry": "coaching",
            "pain_signal": "linkedin_profile_optimization",
        },
        {
            "company_name": "Operations Consulting",
            "domain": "opsconsult.net",
            "name": "Raymond Taylor",
            "email": "raymond@opsconsult.net",
            "role": "Senior Partner",
            "industry": "consulting",
            "pain_signal": "process_improvement",
        },
        {
            "company_name": "Commercial Real Estate",
            "domain": "cre-advisors.com",
            "name": "Nancy Anderson",
            "email": "nancy@cre-advisors.com",
            "role": "VP",
            "industry": "services",
            "pain_signal": "transaction_velocity",
        },
        {
            "company_name": "Creative Agency Group",
            "domain": "creativeag.io",
            "name": "Steven Martinez",
            "email": "steven@creativeag.io",
            "role": "Creative Director",
            "industry": "agency",
            "pain_signal": "talent_recruitment",
        },
        {
            "company_name": "Business Mindset Coach",
            "domain": "mindsetcoach.pro",
            "name": "Karen Thompson",
            "email": "karen@mindsetcoach.pro",
            "role": "Head Coach",
            "industry": "coaching",
            "pain_signal": "student_results_proof",
        },
        {
            "company_name": "Strategy & Design",
            "domain": "stratanddesign.com",
            "name": "Eric Anderson",
            "email": "eric@stratanddesign.com",
            "role": "Managing Director",
            "industry": "consulting",
            "pain_signal": "stakeholder_alignment",
        },
        {
            "company_name": "Insurance Advisory",
            "domain": "insadvisory.io",
            "name": "Betty Johnson",
            "email": "betty@insadvisory.io",
            "role": "Principal",
            "industry": "services",
            "pain_signal": "policy_placement_rate",
        },
        {
            "company_name": "Video Production House",
            "domain": "videoprod.pro",
            "name": "Kevin Martinez",
            "email": "kevin@videoprod.pro",
            "role": "Producer/Founder",
            "industry": "agency",
            "pain_signal": "client_turnaround",
        },
        {
            "company_name": "Health Coaching Academy",
            "domain": "healthcoach.academy",
            "name": "Sharon White",
            "email": "sharon@healthcoach.academy",
            "role": "Program Director",
            "industry": "coaching",
            "pain_signal": "certification_value",
        },
        {
            "company_name": "Strategic IT Consulting",
            "domain": "stratit.io",
            "name": "Matthew Garcia",
            "email": "matthew@stratit.io",
            "role": "CTO/Founder",
            "industry": "consulting",
            "pain_signal": "technology_adoption",
        },
        {
            "company_name": "Wealth Management Advisors",
            "domain": "wealthmgmt.pro",
            "name": "Susan Lee",
            "email": "susan@wealthmgmt.pro",
            "role": "Managing Principal",
            "industry": "services",
            "pain_signal": "hnw_client_acquisition",
        },
        {
            "company_name": "Experiential Marketing",
            "domain": "expmarkt.io",
            "name": "Anthony Brown",
            "email": "anthony@expmarkt.io",
            "role": "Chief Creative Officer",
            "industry": "agency",
            "pain_signal": "event_attendance",
        },
        {
            "company_name": "Corporate Wellness Coach",
            "domain": "corpwellness.pro",
            "name": "Patricia Anderson",
            "email": "patricia.anderson@corpwellness.pro",
            "role": "Wellness Director",
            "industry": "coaching",
            "pain_signal": "employee_engagement_metrics",
        },
        {
            "company_name": "Organizational Development",
            "domain": "orgdev.net",
            "name": "Donald Miller",
            "email": "donald@orgdev.net",
            "role": "Chief Consultant",
            "industry": "consulting",
            "pain_signal": "change_management_adoption",
        },
        {
            "company_name": "Employment Law Services",
            "domain": "emplaw.io",
            "name": "Heather Garcia",
            "email": "heather@emplaw.io",
            "role": "Partner",
            "industry": "services",
            "pain_signal": "litigation_volume",
        },
        {
            "company_name": "Performance Marketing Group",
            "domain": "perfmktgroup.com",
            "name": "Joshua Wilson",
            "email": "joshua@perfmktgroup.com",
            "role": "VP Growth",
            "industry": "agency",
            "pain_signal": "cpa_optimization",
        },
        {
            "company_name": "Transformational Coaching",
            "domain": "transformcoach.io",
            "name": "Lisa Garcia",
            "email": "lisa.garcia@transformcoach.io",
            "role": "Senior Coach",
            "industry": "coaching",
            "pain_signal": "transformation_ROI_proof",
        },
        {
            "company_name": "Market Research Consulting",
            "domain": "mktresearch.pro",
            "name": "Brian Taylor",
            "email": "brian@mktresearch.pro",
            "role": "Research Director",
            "industry": "consulting",
            "pain_signal": "insights_actionability",
        },
        {
            "company_name": "Intellectual Property Law",
            "domain": "iplaw.io",
            "name": "Karen Miller",
            "email": "karen@iplaw.io",
            "role": "Senior Partner",
            "industry": "services",
            "pain_signal": "patent_prosecution_backlog",
        },
    ]

    if allow_template:
        tpl = list(template_prospects)
        random.shuffle(tpl)
        return [
            dict(x)
            | {
                "linkedin_url": (x.get("linkedin_url") or ""),
                "source": "demo_template",
            }
            for x in tpl[:count]
        ]

    # ── Source priority: Apollo → Hunter → template ──────────────────────────
    # 1. Apollo (real verified B2B leads — primary source)
    if APOLLO_API_KEY:
        apollo_results = fetch_prospects_from_apollo(count)
        prospects.extend(apollo_results)

    # 2. Hunter domain search (secondary, if Apollo didn't fill quota)
    if len(prospects) < count and HUNTER_API_KEY:
        remaining = count - len(prospects)
        for keyword in industry_keywords[:3]:
            api_results = fetch_prospects_from_hunter(keyword, remaining // 3 + 1)
            prospects.extend(api_results)
            if len(prospects) >= count:
                break

    # 3. Template fallback (no API keys) — shuffled copy so each run order differs
    if not prospects:
        tpl = list(template_prospects)
        random.shuffle(tpl)
        for x in tpl:
            prospects.append(
                dict(x)
                | {
                    "linkedin_url": (x.get("linkedin_url") or ""),
                    "source": "fallback_template",
                }
            )

    return prospects[:count]


def run(
    industry_keywords: list[str] | None = None,
    *,
    count: int = 50,
    allow_template: bool = False,
    output_file: pathlib.Path | None = None,
    cohort1_csv: pathlib.Path | None = None,
) -> int:
    """
    Main execution: source prospects, validate, output CSV
    """

    if industry_keywords is None:
        industry_keywords = ["agency", "coaching", "saas"]

    run_id = os.environ.get("VENTURE_RUN_ID", "").strip() or uuid.uuid4().hex[:16]

    out_path = output_file if output_file is not None else OUTPUT_FILE

    print(f"\n=== Prospect Builder ===\n")
    print(f"[info] Sourcing {count} prospects")
    print(f"[info] run_id: {run_id}")
    print(f"[info] DATA_BASE: {DATA_BASE}")
    print(f"[info] Output: overwrite {out_path} (single batch per run)")
    if cohort1_csv is not None:
        print(f"[info] Cohort1 CSV: {cohort1_csv} ({len(COHORT1_CSV_FIELDNAMES)} columns)")
    print(f"[info] Industries: {', '.join(industry_keywords)}")
    if allow_template:
        print("[info] Primary source: template (--demo, shuffled; no API calls)")
    elif APOLLO_API_KEY:
        print("[info] Primary source: Apollo.io")
    elif HUNTER_API_KEY:
        print("[info] Primary source: Hunter.io (no Apollo key)")
    else:
        print("[info] Primary source: template (no API keys)")

    raw_prospects = build_prospect_list(
        industry_keywords, count, allow_template=allow_template
    )

    if not raw_prospects:
        print(
            "[fail] No prospects sourced. Set APOLLO_API_KEY / HUNTER_API_KEY or use --demo."
        )
        return 1

    print(f"[ok] Sourced {len(raw_prospects)} raw prospects")

    from prospect_gate import (
        append_prospect_audit_log,
        normalize_email,
        run_prospect_gate,
        run_strict_forensic_checks,
        verify_gate_eligible_audit_parity,
        verify_written_eligible_prospects_csv,
        write_eligible_prospects_csv,
        write_prospect_generation_digest,
        write_strict_mode_summary,
    )

    db_path = resolve_venture_db_path(DATA_BASE, REPO_ROOT)
    cohort_id = os.environ.get("VENTURE_COHORT_ID", "").strip()
    try:
        gate = run_prospect_gate(
            raw_rows=raw_prospects,
            run_id=run_id,
            validate_prospect_fn=validate_prospect,
            db_path=db_path,
            cohort_id=cohort_id,
        )
    except ValueError as exc:
        print(f"\n[fail] Audit log schema error: {exc}")
        return 1

    eligible = gate.eligible_rows
    parity_pre = verify_gate_eligible_audit_parity(
        eligible_rows=eligible, audit_rows=gate.audit_rows, run_id=run_id
    )
    if parity_pre:
        print("\n[fail] Gate invariant broken (eligible vs audit ELIGIBLE mismatch):")
        for line in parity_pre:
            print(f"  - {line}")
        return 2

    try:
        append_prospect_audit_log(DATA_BASE, gate.audit_rows)
    except ValueError as exc:
        print(f"\n[fail] Audit log schema error: {exc}")
        return 1

    if not gate.db_ok:
        print(
            "\n[warn] SQLite suppression DB unavailable — rows classified DROP "
            "(suppression_db_unavailable). Audit: DATA_BASE/07-kpis/prospect_audit_log.csv. "
            "Exit 0 per contract; treat as CRITICAL before outbound.\n"
        )

    for row in eligible:
        for k in PROSPECT_CSV_FIELDNAMES:
            row.setdefault(k, "")
        row["email"] = normalize_email(row.get("email"))

    review_count = sum(
        1
        for r in gate.audit_rows
        if (r.get("validation_status") or "").strip().upper() == "REVIEW"
    )
    reject_count = sum(
        1
        for r in gate.audit_rows
        if (r.get("validation_status") or "").strip().upper() == "REJECT"
    )
    ready_count = len(eligible)

    print(f"\n[ok] Gate results ({len(gate.audit_rows)} audited):")
    print(f"  ELIGIBLE (READY, written to prospects.csv): {ready_count}")
    print(f"  REVIEW (audit only): {review_count}")
    print(f"  REJECT (audit only): {reject_count}")

    strict_prospect = os.environ.get("STRICT_PROSPECT_MODE", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    strict_audit_halt = os.environ.get("VENTURE_STRICT_PROSPECT_AUDIT", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    if not eligible:
        print(
            "\n[warn] No ELIGIBLE prospects after gate (prospects.csv will be header-only)."
        )

    _assert_prospect_batch_schema(eligible, run_id)

    write_eligible_prospects_csv(out_path, eligible, list(PROSPECT_CSV_FIELDNAMES))

    rt_errs = verify_written_eligible_prospects_csv(
        out_path,
        eligible_rows=eligible,
        run_id=run_id,
        fieldnames=list(PROSPECT_CSV_FIELDNAMES),
    )
    if rt_errs:
        print("\n[fail] prospects.csv round-trip verification failed:")
        for line in rt_errs:
            print(f"  - {line}")
        return 3

    if cohort1_csv is not None:
        write_cohort1_prospects_csv(cohort1_csv, eligible)

    if strict_prospect or strict_audit_halt:
        summary = run_strict_forensic_checks(
            audit_rows=gate.audit_rows,
            eligible_rows=eligible,
            run_id=run_id,
        )
        if strict_prospect:
            write_strict_mode_summary(DATA_BASE, summary)
            n_viol = sum(int(v.get("count") or 0) for v in summary.get("violations") or [])
            if summary.get("strict_ok"):
                print("STRICT_MODE: OK | violations=0")
            else:
                print(f"STRICT_MODE: VIOLATIONS DETECTED | count={n_viol}")
        if strict_audit_halt and not summary.get("strict_ok"):
            print("\n[fail] VENTURE_STRICT_PROSPECT_AUDIT: forensic / parity checks failed (halt).")
            return 11

    write_prospect_generation_digest(
        DATA_BASE,
        run_id=run_id,
        payload={
            "gate_eligible_audit_parity_ok": True,
            "csv_round_trip_ok": True,
            "rows_written": len(eligible),
            "output_path": str(out_path.resolve()),
            "cohort1_csv_path": str(cohort1_csv.resolve()) if cohort1_csv else "",
        },
    )

    from operator_ux import print_prospect_builder_success_banner

    print_prospect_builder_success_banner(
        output_file=out_path,
        data_base=DATA_BASE,
        run_id=run_id,
        rows_written=ready_count,
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Source prospects into 06-sales/prospects.csv (READY/REVIEW/REJECT).",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Merge template prospects (testing; also use when no API keys)",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=50,
        metavar="N",
        help="Max prospects to write (default 50)",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        metavar="PATH",
        help="Canonical prospects CSV (READY rows). Default: DATA_BASE/06-sales/prospects.csv",
    )
    parser.add_argument(
        "--cohort1-csv",
        default=None,
        metavar="PATH",
        help="Also write Cohort 1 template CSV (paths relative to DATA_BASE unless absolute).",
    )
    args = parser.parse_args()
    out_override = (
        resolve_cli_data_path(args.output_file) if args.output_file else None
    )
    c1_path = resolve_cli_data_path(args.cohort1_csv) if args.cohort1_csv else None
    return run(
        count=args.count,
        allow_template=args.demo,
        output_file=out_override,
        cohort1_csv=c1_path,
    )


if __name__ == "__main__":
    _exit_code = main()
    if _exit_code != 0:
        from operator_ux import print_prospect_builder_exit_card

        print_prospect_builder_exit_card(_exit_code)
    sys.exit(_exit_code)
