"""
Final pre-send enforcement choke point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from outreach_state_machine import state_policy


@dataclass
class FirewallResult:
    allowed: bool
    reasons: List[str]


def final_send_check(
    compliance_pass: bool,
    capacity_pass: bool,
    integrity_pass: bool,
    state: str,
    qualification_pass: bool,
    message_lint_pass: bool,
    request_call_cta: bool,
) -> FirewallResult:
    reasons: List[str] = []
    if not compliance_pass:
        reasons.append("COMPLIANCE_BLOCK")
    if not capacity_pass:
        reasons.append("CAPACITY_BLOCK")
    if not integrity_pass:
        reasons.append("INTEGRITY_BLOCK")
    if not qualification_pass:
        reasons.append("QUALITY_BLOCK")
    if not message_lint_pass:
        reasons.append("QUALITY_BLOCK")

    policy = state_policy(state)
    if request_call_cta and not policy["allow_call_cta"]:
        reasons.append("STATE_POLICY_BLOCK")

    return FirewallResult(allowed=len(reasons) == 0, reasons=reasons)
