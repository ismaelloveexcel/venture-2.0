"""Anonymized case study payload builder."""

from __future__ import annotations

from typing import Any

_INDUSTRY_KEYWORDS = [
    "healthcare",
    "finance",
    "fintech",
    "legal",
    "agency",
    "education",
    "software",
    "saas",
    "marketing",
    "insurance",
    "consulting",
    "real estate",
    "recruiting",
    "hr",
    "coaching",
]


def _infer_industry(*texts: str) -> str:
    combined = " ".join(texts).lower()
    for keyword in _INDUSTRY_KEYWORDS:
        if keyword in combined:
            if keyword == "saas":
                return "SaaS"
            if keyword == "hr":
                return "HR"
            return keyword.title()
    return "Confidential"


def build_case_study(
    *,
    client_id: str,
    executive_outputs: dict[str, Any],
    trend_outputs: dict[str, Any],
    value_summary: dict[str, Any],
    intake_context: dict[str, Any],
    anonymize: bool = True,
) -> dict[str, Any]:
    executive_summary = executive_outputs.get("executive_summary") or {}
    summary = value_summary.get("summary") if isinstance(value_summary, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    trend_projection = trend_outputs.get("trend_projection") or {}
    icp_text = str(
        ((intake_context or {}).get("execution_intent") or {}).get("icp") or ""
    )
    opportunity_text = str(executive_summary.get("top_opportunity") or "")
    industry = _infer_industry(
        icp_text, opportunity_text, str(summary.get("performance_overview") or "")
    )

    problem = str(executive_summary.get("primary_risk") or "Low reply efficiency")
    intervention = str(
        executive_summary.get("recommended_action")
        or "Refined segment allocation and messaging"
    )
    outcome = str(executive_summary.get("business_impact") or "Performance stabilized")
    if anonymize:
        client_label = "Client Account"
        problem = problem.replace(client_id, client_label)
        intervention = intervention.replace(client_id, client_label)
        outcome = outcome.replace(client_id, client_label)
    else:
        client_label = client_id

    return {
        "client_label": client_label,
        "industry": industry,
        "problem": problem,
        "intervention": intervention,
        "outcome": outcome,
        "trajectory": str(trend_projection.get("projected_state") or "STABLE"),
        "anonymized": anonymize,
    }
