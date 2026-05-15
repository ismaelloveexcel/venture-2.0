"""Deterministic pilot summary builder."""

from __future__ import annotations

from typing import Any


def build_pilot_summary(
    *,
    client_id: str,
    executive_outputs: dict[str, Any],
    trend_outputs: dict[str, Any],
    roi_projection: dict[str, Any],
) -> dict[str, Any]:
    executive_summary = executive_outputs.get("executive_summary") or {}
    trend_projection = trend_outputs.get("trend_projection") or {}
    return {
        "client": client_id,
        "status": executive_summary.get("campaign_status", "BASELINE"),
        "observed_problem": executive_summary.get(
            "primary_risk", "No material risk identified"
        ),
        "demonstrated_improvement": executive_summary.get(
            "business_impact", "No comparative change yet."
        ),
        "recommended_engagement": "30-day optimization sprint",
        "trajectory": trend_projection.get("projected_state", "BASELINE"),
        "roi_projection": roi_projection,
    }
