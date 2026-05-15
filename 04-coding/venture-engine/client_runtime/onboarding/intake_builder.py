"""Build normalized execution intent from raw client config."""

from __future__ import annotations

from typing import Any

from .intake_schema import INTAKE_VERSION
from .intake_validator import validate_raw_config


def _as_list_of_text(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _normalize_targeting_mode(target_source: Any) -> str:
    if isinstance(target_source, dict):
        source_type = str(target_source.get("type") or "").strip().lower()
        if source_type:
            return source_type
    if isinstance(target_source, str) and target_source.strip():
        return target_source.strip().lower()
    return "unknown"


def _normalize_icp(icp_definition: Any) -> str:
    if isinstance(icp_definition, str):
        return icp_definition.strip()
    if isinstance(icp_definition, dict):
        parts: list[str] = []
        for key in sorted(icp_definition):
            value = icp_definition.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                parts.append(f"{key}:{text}")
        return " | ".join(parts)
    return str(icp_definition or "").strip()


def _normalize_offer(offer_context: Any) -> str:
    if isinstance(offer_context, str):
        return offer_context.strip()
    if isinstance(offer_context, dict):
        parts: list[str] = []
        for key in sorted(offer_context):
            value = offer_context.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                parts.append(f"{key}:{text}")
        return " | ".join(parts)
    return str(offer_context or "").strip()


def _normalize_success_definition(success_metrics: Any) -> dict[str, Any]:
    if isinstance(success_metrics, dict):
        out: dict[str, Any] = {}
        for key in sorted(success_metrics):
            out[str(key)] = success_metrics[key]
        return out
    return {"raw": success_metrics}


def build_intake_context(raw_config: dict[str, Any]) -> dict[str, Any]:
    errors = validate_raw_config(raw_config)
    if errors:
        raise ValueError(";".join(errors))

    return {
        "client_id": str(raw_config.get("client_id") or "").strip(),
        "execution_intent": {
            "icp": _normalize_icp(raw_config.get("icp_definition")),
            "offer": _normalize_offer(raw_config.get("offer_context")),
            "constraints": _as_list_of_text(raw_config.get("messaging_constraints")),
            "targeting_mode": _normalize_targeting_mode(
                raw_config.get("target_source")
            ),
            "success_definition": _normalize_success_definition(
                raw_config.get("success_metrics")
            ),
        },
        "intake_version": INTAKE_VERSION,
    }
