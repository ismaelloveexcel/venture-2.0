from __future__ import annotations

import sqlite3

import pytest

from resend_webhook_handler import process_resend_event


@pytest.fixture
def insecure_webhooks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VENTURE_ALLOW_INSECURE_WEBHOOKS", "true")


def test_resend_webhook_duplicate_event_id_no_double_row(
    tmp_path, monkeypatch: pytest.MonkeyPatch, insecure_webhooks
) -> None:
    db = tmp_path / "webhook_idem.db"
    monkeypatch.delenv("VENTURE_SQLITE_DB", raising=False)
    payload = {
        "id": "evt_idem_001",
        "type": "email.opened",
        "data": {"to": ["idem@example.com"]},
    }
    r1 = process_resend_event(payload, db_path=str(db))
    r2 = process_resend_event(payload, db_path=str(db))
    assert r1.get("ok") is True
    assert r2.get("ok") is True
    assert r2.get("duplicate") is True

    with sqlite3.connect(str(db)) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM resend_webhook_events WHERE event_id = ?",
            ["evt_idem_001"],
        ).fetchone()[0]
    assert int(n) == 1


def test_suppression_history_single_row_on_duplicate_bounce(
    tmp_path, monkeypatch: pytest.MonkeyPatch, insecure_webhooks
) -> None:
    db = tmp_path / "webhook_sup.db"
    payload = {
        "id": "evt_bounce_002",
        "type": "email.bounced",
        "data": {"to": ["bounce@example.com"]},
    }
    process_resend_event(payload, db_path=str(db))
    process_resend_event(payload, db_path=str(db))
    with sqlite3.connect(str(db)) as conn:
        n = conn.execute(
            """
            SELECT COUNT(*) FROM suppression_history
            WHERE lower(email) = lower(?) AND reason = 'hard_bounce'
            """,
            ["bounce@example.com"],
        ).fetchone()[0]
    assert int(n) == 1
