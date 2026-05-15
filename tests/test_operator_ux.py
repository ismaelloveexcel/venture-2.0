from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"


@pytest.fixture()
def ux_mod(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import operator_ux as ux

    return ux


def test_humanize_skip_reason_known(ux_mod):
    assert "READY" in ux_mod.humanize_skip_reason("validation_status_not_READY")


def test_humanize_skip_reason_unknown(ux_mod):
    h = ux_mod.humanize_skip_reason("custom_code_xyz")
    assert "custom_code_xyz" in h


def test_operator_status_payload_reads_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    from operator_ux import operator_status_payload

    repo = tmp_path / "repo"
    repo.mkdir()
    db = tmp_path / "data"
    (db / "06-sales").mkdir(parents=True)
    (db / "logs").mkdir(parents=True)
    skip = db / "logs" / "send_skipped_log.csv"
    skip.write_text(
        "timestamp_utc,run_id,email,email_normalized,skip_reason,audit_classification\n"
        "2026-01-01T00:00:00Z,r1,a@b.com,a@b.com,not_ELIGIBLE_in_audit_log,DROP\n",
        encoding="utf-8",
    )
    report = {
        "run_id": "r1",
        "outbound": {"status": "SUCCESS"},
    }
    (repo / "run_report.json").write_text(json.dumps(report), encoding="utf-8")

    monkeypatch.setenv("VENTURE_CLIENT_WORKSPACE", str(db))
    payload = operator_status_payload(repo_root=repo, data_base=db)
    assert payload["run_id"] == "r1"
    assert len(payload["skipped_rows"]) == 1
    assert "ELIGIBLE" in payload["skipped_rows"][0]["why"]


def test_no_color_disables_escapes(ux_mod, monkeypatch: pytest.MonkeyPatch):
    ux = ux_mod
    monkeypatch.setenv("NO_COLOR", "1")
    s = ux._c("\033[31m", "hello")
    assert s == "hello"
