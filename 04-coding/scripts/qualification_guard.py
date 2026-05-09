"""
Economic and execution viability guard for opportunities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class QualificationResult:
    qualified: bool
    reasons: List[str]


def evaluate_qualification(
    evidence_confidence: float,
    has_direct_contact: bool,
    estimated_value: float,
    min_viable_deal: float,
    implementation_days: int,
    max_delivery_days: int,
    has_compliance_risk: bool,
    capacity_available: bool,
) -> QualificationResult:
    reasons: List[str] = []
    if evidence_confidence < 0.7:
        reasons.append(f"evidence_confidence_below_threshold:{evidence_confidence:.2f}")
    if not has_direct_contact:
        reasons.append("missing_direct_contact")
    if estimated_value < min_viable_deal:
        reasons.append(f"estimated_value_below_min:{estimated_value:.2f}<{min_viable_deal:.2f}")
    if implementation_days > max_delivery_days:
        reasons.append(f"implementation_too_slow:{implementation_days}>{max_delivery_days}")
    if has_compliance_risk:
        reasons.append("compliance_risk_detected")
    if not capacity_available:
        reasons.append("delivery_capacity_unavailable")
    return QualificationResult(qualified=len(reasons) == 0, reasons=reasons)
