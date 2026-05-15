"""Outbound SQLite: UPSERT dry_run → sent; follow-up eligibility for initial_prospect."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JQ = ROOT / "venture-mcp-server"


@pytest.fixture()
def jq(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(JQ))
    from job_queue import get_queue

    db = tmp_path / "test_outbound.db"
    return get_queue(str(db))


def test_record_outbound_upsert_dry_run_then_sent(jq):
    jq.record_outbound(
        "pid-a",
        "outreach_initial",
        "a@example.com",
        "Subject",
        "<p>one</p>",
        "dry_run",
        "",
        "initial_prospect",
    )
    jq.record_outbound(
        "pid-a",
        "outreach_initial",
        "a@example.com",
        "Subject",
        "<p>one</p>",
        "sent",
        "re_123",
        "initial_prospect",
    )
    db_path = Path(jq.db_path)
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute(
            "SELECT status, provider_id FROM outbound_events WHERE prospect_id=?",
            ["pid-a"],
        ).fetchone()
    assert row is not None
    assert row[0] == "sent"
    assert row[1] == "re_123"


def test_list_followup_eligible_accepts_initial_prospect(jq):
    old = (datetime.now() - timedelta(days=30)).isoformat()
    jq.record_outbound(
        "pid-fu",
        "outreach_initial",
        "fu@example.com",
        "Subject",
        "<p>old</p>",
        "sent",
        "",
        "initial_prospect",
    )
    # Backdate created_at for eligibility window
    db_path = Path(jq.db_path)
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "UPDATE outbound_events SET created_at = ? WHERE prospect_id = ?",
            [old, "pid-fu"],
        )
        conn.commit()
    rows = jq.list_followup_eligible_rows(min_days_since_initial=7)
    emails = {r.get("recipient_email") for r in rows}
    assert "fu@example.com" in emails
