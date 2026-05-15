"""Campaign state persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .state_machine import normalize_campaign_state, transition_campaign_state


def campaign_state_path(repo_root: Path, client_id: str, campaign_id: str) -> Path:
    return (
        repo_root
        / "clients"
        / str(client_id)
        / "campaigns"
        / str(campaign_id)
        / "state.json"
    )


def _default_state(client_id: str, campaign_id: str) -> dict[str, Any]:
    return {
        "client_id": str(client_id),
        "campaign_id": str(campaign_id),
        "state": "draft",
        "history": [{"from": None, "to": "draft", "reason": "initialized"}],
    }


def load_campaign_state(
    repo_root: Path, client_id: str, campaign_id: str
) -> dict[str, Any]:
    path = campaign_state_path(repo_root, client_id, campaign_id)
    if not path.is_file():
        return _default_state(client_id, campaign_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _default_state(client_id, campaign_id)
    if not isinstance(payload, dict):
        return _default_state(client_id, campaign_id)
    payload.setdefault("client_id", str(client_id))
    payload.setdefault("campaign_id", str(campaign_id))
    payload.setdefault("state", "draft")
    payload.setdefault("history", [])
    payload["state"] = normalize_campaign_state(str(payload.get("state") or "draft"))
    return payload


def save_campaign_state(
    repo_root: Path,
    client_id: str,
    campaign_id: str,
    payload: dict[str, Any],
) -> Path:
    path = campaign_state_path(repo_root, client_id, campaign_id)
    return atomic_write_json(path, payload)


def transition_campaign_state_file(
    *,
    repo_root: Path,
    client_id: str,
    campaign_id: str,
    to_state: str,
    reason: str,
) -> dict[str, Any]:
    payload = load_campaign_state(repo_root, client_id, campaign_id)
    from_state = str(payload.get("state") or "draft")
    new_state = transition_campaign_state(from_state, to_state)
    payload["state"] = new_state
    history = payload.get("history")
    if not isinstance(history, list):
        history = []
    history.append({"from": from_state, "to": new_state, "reason": str(reason or "")})
    payload["history"] = history
    save_campaign_state(repo_root, client_id, campaign_id, payload)
    return payload
