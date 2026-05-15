"""Campaign status tracker for canonical run execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .campaign_state import (
    campaign_state_path,
    load_campaign_state,
    save_campaign_state,
    transition_campaign_state_file,
)


def _target_state_from_outbound_status(outbound_status: str) -> str:
    token = (outbound_status or "").strip().upper()
    if token == "SUCCESS":
        return "completed"
    if token in {"FAILED", "BLOCKED"}:
        return "failed"
    if token in {"SKIPPED", "NOT_EXECUTED"}:
        return "paused"
    return "running"


def update_campaign_state(
    *,
    repo_root: Path,
    client_id: str,
    campaign_id: str,
    run_id: str,
    outbound_status: str,
    run_dir: Path | None = None,
) -> dict[str, Any]:
    payload = load_campaign_state(repo_root, client_id, campaign_id)
    current = str(payload.get("state") or "draft")

    # Progressive lifecycle before run terminalization.
    for checkpoint in ("approved", "queued", "running"):
        if current == checkpoint:
            break
        try:
            payload = transition_campaign_state_file(
                repo_root=repo_root,
                client_id=client_id,
                campaign_id=campaign_id,
                to_state=checkpoint,
                reason=f"run:{run_id}:preflight",
            )
            current = checkpoint
        except Exception:
            current = str(payload.get("state") or current)
            break

    final_state = _target_state_from_outbound_status(outbound_status)
    try:
        payload = transition_campaign_state_file(
            repo_root=repo_root,
            client_id=client_id,
            campaign_id=campaign_id,
            to_state=final_state,
            reason=f"run:{run_id}:outbound_status={outbound_status}",
        )
    except Exception:
        payload["state"] = current
        save_campaign_state(repo_root, client_id, campaign_id, payload)

    state_path = campaign_state_path(repo_root, client_id, campaign_id)
    run_state_path = None
    if run_dir is not None:
        run_state_path = atomic_write_json(run_dir / "campaign_state.json", payload)
    return {
        "campaign_id": campaign_id,
        "state": str(payload.get("state") or "draft"),
        "path": str(state_path),
        "run_path": str(run_state_path) if run_state_path is not None else "",
    }
