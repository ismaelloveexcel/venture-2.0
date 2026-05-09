"""
CTA router based on outreach state, trust score, and evidence confidence.
"""

from __future__ import annotations


def choose_cta(state: str, trust_score: float, evidence_confidence: float) -> str:
    if state == "COLD":
        return "show_example"
    if state == "WARM":
        if evidence_confidence >= 0.7 and trust_score >= 0.3:
            return "choice_breakdown_or_10min"
        return "send_breakdown"
    if state == "ENGAGED":
        return "call_optional"
    if state == "QUALIFIED":
        return "calendar_allowed"
    return "soft_followup"
