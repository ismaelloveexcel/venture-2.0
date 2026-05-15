"""Deterministic validators for client onboarding intake payloads."""

from __future__ import annotations

from typing import Any

from .intake_schema import REQUIRED_CONFIG_KEYS


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def validate_raw_config(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_CONFIG_KEYS:
        if key not in payload:
            errors.append(f"missing_key:{key}")
        elif _is_blank(payload.get(key)):
            errors.append(f"blank_value:{key}")

    email = str(payload.get("reporting_email") or "").strip()
    if email and "@" not in email:
        errors.append("invalid_reporting_email")

    if "messaging_constraints" in payload and not isinstance(
        payload.get("messaging_constraints"), (list, tuple)
    ):
        errors.append("invalid_type:messaging_constraints")

    if "success_metrics" in payload and not isinstance(
        payload.get("success_metrics"), dict
    ):
        errors.append("invalid_type:success_metrics")

    return sorted(errors)
