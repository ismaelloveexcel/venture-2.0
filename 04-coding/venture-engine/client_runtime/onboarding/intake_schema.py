"""Schema constants for client onboarding intake normalization."""

from __future__ import annotations

REQUIRED_CONFIG_KEYS: tuple[str, ...] = (
    "client_id",
    "campaign_name",
    "icp_definition",
    "offer_context",
    "target_source",
    "messaging_constraints",
    "success_metrics",
    "reporting_email",
)

INTAKE_VERSION = "1.0"
