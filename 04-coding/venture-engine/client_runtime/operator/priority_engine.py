"""Deterministic priority scoring for operator actions."""

from __future__ import annotations

from typing import Any


def score_priority(
    *,
    action: str,
    severity: int,
    confidence: int,
    business_impact: int,
    trend_deterioration: int,
    reason: str,
) -> dict[str, Any]:
    score = (
        max(0, min(100, severity)) * 0.40
        + max(0, min(100, confidence)) * 0.30
        + max(0, min(100, business_impact)) * 0.20
        + max(0, min(100, trend_deterioration)) * 0.10
    )
    priority_score = int(round(score))
    if priority_score >= 70:
        priority = "HIGH"
    elif priority_score >= 40:
        priority = "MEDIUM"
    else:
        priority = "LOW"
    return {
        "priority": priority,
        "action": action,
        "reason": reason,
        "score": priority_score,
    }
