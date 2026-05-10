#!/usr/bin/env python3
"""
Prospect Builder — Rule-Based Sourcing Engine

Primary source: Apollo.io People Search API (B2B leads by title/industry/company size)
Fallback:       Hunter.io domain search
Demo mode:      Template dataset (--demo flag)

Output: CSV with readiness_status (READY | REVIEW | REJECT)

Usage:
    python prospect_builder.py                          # Apollo (real leads)
    python prospect_builder.py --demo                  # template data for testing
    python prospect_builder.py --input-csv path/to/prospects.csv
"""

import csv
import sys
import pathlib
from typing import Optional
import httpx
from dotenv import load_dotenv
import os

BASE = pathlib.Path(__file__).resolve().parents[2]
load_dotenv(BASE / ".env")

APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "").strip()
OUTPUT_FILE = BASE / "06-sales" / "prospects.csv"

# ── Apollo ICP targeting defaults ────────────────────────────────────────────
# Titles that indicate decision-maker authority for B2B outreach automation
APOLLO_TITLES = [
    "founder",
    "co-founder",
    "ceo",
    "chief executive officer",
    "owner",
    "managing director",
    "director of sales",
    "head of sales",
    "vp of sales",
    "chief revenue officer",
    "head of growth",
    "director of marketing",
]

# Apollo industry tags (use Apollo's taxonomy)
APOLLO_INDUSTRIES = [
    "marketing and advertising",
    "management consulting",
    "staffing and recruiting",
    "computer software",
    "internet",
    "information technology and services",
    "professional training and coaching",
    "financial services",
]

# Pain-signal heuristics mapped from industry/title combos
_PAIN_SIGNAL_MAP = {
    "marketing and advertising": "client_acquisition",
    "management consulting": "pipeline_visibility",
    "staffing and recruiting": "candidate_shortage",
    "computer software": "low_reply_rate",
    "internet": "scaling_outbound",
    "information technology and services": "deal_cycles_long",
    "professional training and coaching": "program_enrollment",
    "financial services": "hnw_client_acquisition",
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

    Apollo docs: https://docs.apollo.io/reference/people-search
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
                    "api_key": APOLLO_API_KEY,
                    "person_titles": APOLLO_TITLES,
                    "organization_industry_tag_ids": [],  # use q_organization_industry instead
                    "q_organization_industry_tag_names": APOLLO_INDUSTRIES,
                    "contact_email_status": ["verified"],
                    "per_page": per_page,
                    "page": page,
                }

                r = client.post(
                    "https://api.apollo.io/v1/mixed_people/search",
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Cache-Control": "no-cache",
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
                people = data.get("people", [])

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
                    company = (org.get("name") or person.get("organization_name") or "").strip()
                    domain = (org.get("primary_domain") or person.get("organization_domain") or "").strip()
                    industry = (org.get("industry") or person.get("industry") or "").strip()
                    linkedin = (person.get("linkedin_url") or "").strip()

                    prospects.append({
                        "company_name": company,
                        "domain": domain,
                        "name": name,
                        "email": email,
                        "role": title,
                        "industry": industry,
                        "pain_signal": _infer_pain_signal(industry, title),
                        "linkedin_url": linkedin,
                    })

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
REQUIRED_ROLES = {
    "founder",
    "owner",
    "ceo",
    "cto",
    "director",
    "head",
    "manager",
    "lead",
}
ICP_INDUSTRIES = {"agency", "coaching", "saas", "consulting", "services"}


def validate_prospect(row: dict) -> tuple[str, str]:
    """
    Apply hard rules to classify prospect.

    Returns: (status, reason)
    - READY: valid email + domain + role
    - REVIEW: missing email but strong domain + role
    - REJECT: fails hard rules
    """

    # Extract fields (handle None values)
    company = (row.get("company_name") or "").strip()
    domain = (row.get("domain") or "").strip()
    role = (row.get("role") or "").strip().lower()
    email = (row.get("email") or "").strip()

    # Hard rejects
    if not company:
        return "REJECT", "missing_company"

    if not domain:
        return "REJECT", "missing_domain"

    if not role:
        return "REJECT", "missing_role"

    # Domain validation
    if domain.lower() in REJECT_DOMAINS:
        return "REJECT", "generic_domain"

    # Role authority check
    role_match = any(req in role for req in REQUIRED_ROLES)
    if not role_match:
        return "REJECT", "non_decision_role"

    # Classify by completeness
    if email and "@" in email and domain.lower() not in REJECT_DOMAINS:
        return "READY", "complete_profile"
    elif domain and role_match:
        return "REVIEW", "missing_email_strong_domain"
    else:
        return "REJECT", "incomplete_profile"


def fetch_prospects_from_hunter(domain_keyword: str, count: int = 50) -> list[dict]:
    """
    Fetch prospects from Hunter.io domain search API.

    Note: This requires Hunter API with domain search access.
    Falls back to returning template if API unavailable.
    """

    if not HUNTER_API_KEY:
        print("[warn] HUNTER_API_KEY not set. Using template data.")
        return []

    prospects = []

    try:
        # Hunter.io domain search endpoint
        # Note: this is a simplified example; actual implementation would paginate
        url = f"https://api.hunter.io/v2/domain-search"
        params = {
            "domain": domain_keyword,
            "limit": min(count, 100),
            "api_key": HUNTER_API_KEY,
        }

        with httpx.Client(timeout=10) as client:
            r = client.get(url, params=params)

            if r.status_code == 200:
                data = r.json()
                for emp in data.get("data", {}).get("employees", []):
                    prospects.append(
                        {
                            "company_name": emp.get("company", ""),
                            "domain": emp.get("domain", ""),
                            "name": emp.get("first_name", ""),
                            "email": emp.get("email", ""),
                            "role": emp.get("position", ""),
                            "industry": "saas",
                        }
                    )
            else:
                print(f"[warn] Hunter API returned {r.status_code}")

    except Exception as e:
        print(f"[warn] Hunter API call failed: {e}")

    return prospects


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

    # 3. Template fallback (demo / no API keys)
    if not prospects or allow_template:
        prospects.extend(template_prospects)

    return prospects[:count]


def run(industry_keywords: list[str] = None, count: int = 50) -> int:
    """
    Main execution: source prospects, validate, output CSV
    """

    if industry_keywords is None:
        industry_keywords = ["agency", "coaching", "saas"]

    print(f"\n=== Prospect Builder ===\n")
    print(f"[info] Sourcing {count} prospects")
    print(f"[info] Industries: {', '.join(industry_keywords)}")

    # Source prospects
    raw_prospects = build_prospect_list(industry_keywords, count)

    if not raw_prospects:
        print("[fail] No prospects sourced. Check Hunter API key.")
        return 1

    print(f"[ok] Sourced {len(raw_prospects)} raw prospects")

    # Apply rules and classify
    validated = []
    ready_count = 0
    review_count = 0
    reject_count = 0

    for prospect in raw_prospects:
        status, reason = validate_prospect(prospect)

        prospect["readiness_status"] = status
        prospect["validation_reason"] = reason

        validated.append(prospect)

        if status == "READY":
            ready_count += 1
        elif status == "REVIEW":
            review_count += 1
        else:
            reject_count += 1

    print(f"\n[ok] Validated {len(validated)} prospects:")
    print(f"  READY: {ready_count}")
    print(f"  REVIEW: {review_count}")
    print(f"  REJECT: {reject_count}")

    # Write output CSV
    if not validated:
        print("[fail] No valid prospects after filtering.")
        return 1

    fieldnames = [
        "company_name",
        "domain",
        "name",
        "email",
        "role",
        "industry",
        "pain_signal",
        "readiness_status",
        "validation_reason",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for prospect in validated:
            writer.writerow({k: prospect.get(k, "") for k in fieldnames})

    print(f"\n[ok] Prospects written to {OUTPUT_FILE}")
    print(f"\nNext: run message_generator.py\n")

    return 0


if __name__ == "__main__":
    sys.exit(run())
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
            "company_name": "Intellectual Property Law",
            "domain": "iplaw.io",
            "name": "Karen Miller",
            "email": "karen@iplaw.io",
            "role": "Senior Partner",
            "industry": "services",
            "pain_signal": "patent_prosecution_backlog",
        },
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

    # 3. Template fallback (demo / no API keys)
    if not prospects or allow_template:
        prospects.extend(template_prospects)

    return prospects[:count]


def run(industry_keywords: list[str] = None, count: int = 50) -> int:
    """
    Main execution: source prospects, validate, output CSV
    """

    if industry_keywords is None:
        industry_keywords = ["agency", "coaching", "saas"]

    print(f"\n=== Prospect Builder ===\n")
    print(f"[info] Sourcing {count} prospects")
    print(f"[info] Industries: {', '.join(industry_keywords)}")
    if APOLLO_API_KEY:
        print(f"[info] Primary source: Apollo.io")
    elif HUNTER_API_KEY:
        print(f"[info] Primary source: Hunter.io (no Apollo key)")
    else:
        print(f"[info] Primary source: template data (no API keys set)")

    # Source prospects
    raw_prospects = build_prospect_list(industry_keywords, count)

    if not raw_prospects:
        print("[fail] No prospects sourced. Check APOLLO_API_KEY or HUNTER_API_KEY.")
        return 1

    print(f"[ok] Sourced {len(raw_prospects)} raw prospects")

    # Apply rules and classify
    validated = []
    ready_count = 0
    review_count = 0
    reject_count = 0

    for prospect in raw_prospects:
        status, reason = validate_prospect(prospect)

        prospect["readiness_status"] = status
        prospect["validation_reason"] = reason

        validated.append(prospect)

        if status == "READY":
            ready_count += 1
        elif status == "REVIEW":
            review_count += 1
        else:
            reject_count += 1

    print(f"\n[ok] Validated {len(validated)} prospects:")
    print(f"  READY: {ready_count}")
    print(f"  REVIEW: {review_count}")
    print(f"  REJECT: {reject_count}")

    # Write output CSV
    if not validated:
        print("[fail] No valid prospects after filtering.")
        return 1

    fieldnames = [
        "company_name",
        "domain",
        "name",
        "email",
        "role",
        "industry",
        "pain_signal",
        "linkedin_url",
        "readiness_status",
        "validation_reason",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for prospect in validated:
            writer.writerow({k: prospect.get(k, "") for k in fieldnames})

    print(f"\n[ok] Prospects written to {OUTPUT_FILE}")
    print(f"\nNext: run message_generator_solo.py\n")

    return 0


if __name__ == "__main__":
    sys.exit(run())
fallback (demo / no API keys)
    if not prospects or allow_template:
        prospects.extend(template_prospects)

    return prospects[:count]


def run(industry_keywords: list[str] = None, count: int = 50) -> int:
    if industry_keywords is None:
        industry_keywords = ["agency", "coaching", "saas"]

    print(f"\n=== Prospect Builder ===\n")
    print(f"[info] Sourcing {count} prospects")
    print(f"[info] Industries: {', '.join(industry_keywords)}")
    if APOLLO_API_KEY:
        print(f"[info] Primary source: Apollo.io")
    elif HUNTER_API_KEY:
        print(f"[info] Primary source: Hunter.io (no Apollo key)")
    else:
        print(f"[info] Primary source: template data (no API keys set)")

    raw_prospects = build_prospect_list(industry_keywords, count)

    if not raw_prospects:
        print("[fail] No prospects sourced. Check APOLLO_API_KEY or HUNTER_API_KEY.")
        return 1

    print(f"[ok] Sourced {len(raw_prospects)} raw prospects")

    validated = []
    ready_count = review_count = reject_count = 0

    for prospect in raw_prospects:
        status, reason = validate_prospect(prospect)
        prospect["readiness_status"] = status
        prospect["validation_reason"] = reason
        validated.append(prospect)
        if status == "READY":
            ready_count += 1
        elif status == "REVIEW":
            review_count += 1
        else:
            reject_count += 1

    print(f"\n[ok] Validated {len(validated)} prospects:")
    print(f"  READY: {ready_count}")
    print(f"  REVIEW: {review_count}")
    print(f"  REJECT: {reject_count}")

    if not validated:
        print("[fail] No valid prospects after filtering.")
        return 1

    fieldnames = [
        "company_name", "domain", "name", "email", "role",
        "industry", "pain_signal", "linkedin_url",
        "readiness_status", "validation_reason",
    ]

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for prospect in validated:
            writer.writerow({k: prospect.get(k, "") for k in fieldnames})

    print(f"\n[ok] Prospects written to {OUTPUT_FILE}")
    print(f"\nNext: run message_generator_solo.py\n")
    return 0


if __name__ == "__main__":
    sys.exit(run())
