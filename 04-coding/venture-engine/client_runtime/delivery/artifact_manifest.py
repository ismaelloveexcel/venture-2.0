"""Delivery manifest builder."""

from __future__ import annotations

from typing import Any

REQUIRED_KEYS: tuple[str, ...] = (
    "client_id",
    "run_id",
    "delivery_items",
    "execution_metadata",
)


def build_artifact_manifest(bundle_payload: dict[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    for key in REQUIRED_KEYS:
        manifest[key] = bundle_payload.get(key)

    # Preserve optional intake context when present.
    if "intake_context" in bundle_payload:
        manifest["intake_context"] = bundle_payload["intake_context"]

    return manifest
