"""Deterministic proposal seed builder."""

from __future__ import annotations

from typing import Any


def build_proposal_seed(
    *,
    client_id: str,
    executive_outputs: dict[str, Any],
    trend_outputs: dict[str, Any],
    value_summary: dict[str, Any],
) -> dict[str, Any]:
    executive_summary = executive_outputs.get("executive_summary") or {}
    summary = value_summary.get("summary") if isinstance(value_summary, dict) else {}
    summary = summary if isinstance(summary, dict) else {}
    observed_problem = str(
        executive_summary.get("primary_risk") or "Low reply efficiency"
    )
    demonstrated_improvement = str(
        executive_summary.get("business_impact") or "Stable execution observed"
    )
    recommended_engagement = "30-day optimization sprint"
    if (
        str(
            (trend_outputs.get("trend_projection") or {}).get("projected_state")
            or "STABLE"
        )
        == "DECLINING"
    ):
        recommended_engagement = "30-day recovery sprint"

    if summary.get("what_is_working"):
        demonstrated_improvement = str(summary.get("what_is_working")[0])

    return {
        "client": client_id,
        "observed_problem": observed_problem,
        "demonstrated_improvement": demonstrated_improvement,
        "recommended_engagement": recommended_engagement,
    }
