"""Template-driven operator task generation."""

from __future__ import annotations

from typing import Any

from .priority_engine import score_priority


def _contains_any(text: str, needles: list[str]) -> bool:
    lower = text.lower()
    return any(needle in lower for needle in needles)


def generate_operator_tasks(
    *,
    executive_summary: dict[str, Any],
    trend_outputs: dict[str, Any],
    health: dict[str, Any],
    value_summary: dict[str, Any],
) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    status = str(executive_summary.get("campaign_status") or "BASELINE").upper()
    primary_risk = str(executive_summary.get("primary_risk") or "")
    business_impact = str(executive_summary.get("business_impact") or "")
    trend_state = str(
        (trend_outputs.get("trend_projection") or {}).get("projected_state") or status
    )
    risk_probability = str(
        (trend_outputs.get("trend_projection") or {}).get("risk_probability")
        or "MEDIUM"
    ).upper()
    health_label = str(health.get("label") or "BASELINE").upper()

    if status in {"DECLINING", "AT_RISK"} or health_label in {"LOW", "CRITICAL"}:
        tasks.append(
            score_priority(
                action="review messaging",
                severity=85,
                confidence=int(executive_summary.get("confidence") or 0),
                business_impact=70,
                trend_deterioration=90,
                reason=primary_risk or "Campaign trajectory weakened",
            )
        )

    if _contains_any(primary_risk, ["velocity", "reply", "lead"]):
        tasks.append(
            score_priority(
                action="reduce low-performing segment",
                severity=78,
                confidence=int(executive_summary.get("confidence") or 0),
                business_impact=75,
                trend_deterioration=80,
                reason=primary_risk or "Lead velocity below target",
            )
        )

    if status == "IMPROVING" or _contains_any(business_impact, ["improved", "healthy"]):
        tasks.append(
            score_priority(
                action="increase high-performing segment",
                severity=64,
                confidence=int(executive_summary.get("confidence") or 0),
                business_impact=82,
                trend_deterioration=20,
                reason=business_impact or "Top segment is outperforming baseline",
            )
        )
        tasks.append(
            score_priority(
                action="expand ICP",
                severity=60,
                confidence=int(executive_summary.get("confidence") or 0),
                business_impact=78,
                trend_deterioration=15,
                reason=str(
                    executive_summary.get("top_opportunity")
                    or "Strongest segment can be widened"
                ),
            )
        )

    if risk_probability in {"MEDIUM", "HIGH"} or health_label in {"LOW", "CRITICAL"}:
        tasks.append(
            score_priority(
                action="investigate low-volume confidence degradation",
                severity=72,
                confidence=max(30, int(executive_summary.get("confidence") or 0)),
                business_impact=68,
                trend_deterioration=75,
                reason=f"Trend risk probability is {risk_probability.lower()}",
            )
        )

    if not tasks:
        tasks.append(
            score_priority(
                action="maintain current operating plan",
                severity=35,
                confidence=int(executive_summary.get("confidence") or 0),
                business_impact=35,
                trend_deterioration=10,
                reason="No material change detected",
            )
        )

    return sorted(
        tasks,
        key=lambda item: (-int(item.get("score") or 0), str(item.get("action") or "")),
    )
