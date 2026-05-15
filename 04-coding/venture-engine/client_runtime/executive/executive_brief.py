"""Render a minimal executive brief HTML artifact."""

from __future__ import annotations

from html import escape
from typing import Any


def render_executive_brief_html(
    *,
    client_id: str,
    executive_summary: dict[str, Any],
    roi_projection: dict[str, Any],
    stakeholder_snapshot: dict[str, Any],
) -> str:
    status = escape(str(executive_summary.get("campaign_status") or "BASELINE"))
    impact = escape(
        str(executive_summary.get("business_impact") or "No comparative impact yet.")
    )
    risk = escape(
        str(executive_summary.get("primary_risk") or "No material risk identified")
    )
    opportunity = escape(
        str(executive_summary.get("top_opportunity") or "No clear opportunity detected")
    )
    action = escape(
        str(executive_summary.get("recommended_action") or "Maintain current approach")
    )
    confidence = escape(str(executive_summary.get("confidence") or 0))
    projected_replies = escape(str(roi_projection.get("projected_replies_30d") or 0))
    projected_qualified = escape(
        str(roi_projection.get("projected_qualified_30d") or 0)
    )
    trajectory = escape(str(roi_projection.get("trajectory") or "STABLE"))
    roi_confidence = escape(str(roi_projection.get("confidence") or "MEDIUM"))
    audience = escape(str(stakeholder_snapshot.get("audience") or "executive"))

    return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Executive Brief - {client_id}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #1f2937; background: #fff; }}
    .card {{ border: 1px solid #d1d5db; border-radius: 10px; padding: 14px; margin-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); gap: 12px; }}
    .kpi {{ background: #f9fafb; }}
    h1, h2 {{ margin: 0 0 10px 0; }}
    p {{ margin: 6px 0; }}
    ul {{ margin: 8px 0 0 18px; }}
  </style>
</head>
<body>
  <h1>Executive Brief</h1>
  <p>Client: <strong>{client_id}</strong></p>
  <p>Audience: <strong>{audience}</strong></p>

  <section class=\"card grid\">
    <div class=\"card kpi\"><strong>Status</strong><p>{status}</p></div>
    <div class=\"card kpi\"><strong>Confidence</strong><p>{confidence}</p></div>
    <div class=\"card kpi\"><strong>30d Replies</strong><p>{projected_replies}</p></div>
    <div class=\"card kpi\"><strong>30d Qualified</strong><p>{projected_qualified}</p></div>
  </section>

  <section class=\"card\">
    <h2>Business Narrative</h2>
    <p>{impact}</p>
  </section>

  <section class=\"card grid\">
    <div class=\"card\"><h2>Campaign Trajectory</h2><p>{trajectory}</p></div>
    <div class=\"card\"><h2>Top Risk</h2><p>{risk}</p></div>
    <div class=\"card\"><h2>Top Opportunity</h2><p>{opportunity}</p></div>
    <div class=\"card\"><h2>Next Step</h2><p>{action}</p></div>
  </section>

  <section class=\"card\">
    <h2>ROI Projection Summary</h2>
    <p>Projected replies: <strong>{projected_replies}</strong></p>
    <p>Projected qualified conversations: <strong>{projected_qualified}</strong></p>
    <p>Projection confidence: <strong>{roi_confidence}</strong></p>
  </section>
</body>
</html>
"""
