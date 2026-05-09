"""
Outreach state machine with enforceable stage permissions.

Canonical copy for venture-mcp-server (lifecycle_engine, job_queue). Scripts import
via shim in 04-coding/scripts/outreach_state_machine.py.

Transition guards: illegal jumps (e.g. COLD -> QUALIFIED, WARM -> CLOSED) return
the current state (no-op) so replay cannot corrupt the graph.
"""

from __future__ import annotations

from typing import Dict


STATE_ORDER = ["COLD", "WARM", "ENGAGED", "QUALIFIED", "CLOSED"]
SIDE_STATES = {"NURTURE", "DISQUALIFIED"}


def allowed_call_cta(state: str) -> bool:
    return state in {"ENGAGED", "QUALIFIED", "CLOSED"}


def proposal_depth_for_state(state: str, evidence_confidence: float) -> str:
    if state == "COLD":
        return "NONE"
    if state == "WARM":
        return "MINI" if evidence_confidence >= 0.7 else "LIGHT"
    if state == "ENGAGED":
        return "STRUCTURED"
    if state == "QUALIFIED":
        return "FULL"
    return "LIGHT"


def next_state_from_signal(current_state: str, signal: str) -> str:
    """
    Strict transition graph. Unknown or illegal combinations leave state unchanged.
    """
    if signal == "no_response_decay":
        if current_state == "ENGAGED":
            return "WARM"
        if current_state == "WARM":
            return "COLD"
        return current_state

    if signal == "reply_received":
        if current_state == "COLD":
            return "WARM"
        if current_state in {"WARM", "ENGAGED", "QUALIFIED"}:
            return current_state
        if current_state == "CLOSED":
            return "CLOSED"
        if current_state in SIDE_STATES:
            return current_state
        return current_state

    if signal == "high_intent":
        if current_state == "WARM":
            return "ENGAGED"
        if current_state == "ENGAGED":
            return "ENGAGED"
        return current_state

    if signal == "qualified_pain_budget_timeline":
        if current_state in {"WARM", "ENGAGED"}:
            return "QUALIFIED"
        return current_state

    if signal == "closed_won":
        if current_state in {"QUALIFIED", "ENGAGED"}:
            return "CLOSED"
        return current_state

    if signal == "disqualified":
        return "DISQUALIFIED"

    if signal == "nurture":
        if current_state == "CLOSED":
            return "CLOSED"
        return "NURTURE"

    return current_state


def state_policy(state: str) -> Dict[str, bool]:
    return {
        "allow_call_cta": allowed_call_cta(state),
        "allow_calendar_link": state in {"QUALIFIED", "CLOSED"},
        "allow_full_proposal": state in {"QUALIFIED", "CLOSED"},
    }
