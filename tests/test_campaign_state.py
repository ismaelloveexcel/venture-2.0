from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.campaigns import transition_campaign_state, update_campaign_state


def test_transition_campaign_state_valid_and_invalid() -> None:
    assert transition_campaign_state("draft", "approved") == "approved"
    assert transition_campaign_state("approved", "queued") == "queued"
    with pytest.raises(ValueError):
        transition_campaign_state("draft", "completed")


def test_update_campaign_state_persists(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    result = update_campaign_state(
        repo_root=tmp_path,
        client_id="acme-demo",
        campaign_id="spring-launch",
        run_id="run-1",
        outbound_status="SUCCESS",
        run_dir=run_dir,
    )

    state_path = (
        tmp_path
        / "clients"
        / "acme-demo"
        / "campaigns"
        / "spring-launch"
        / "state.json"
    )
    assert state_path.is_file()
    assert (run_dir / "campaign_state.json").is_file()
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["state"] == "completed"
    assert result["state"] == "completed"
