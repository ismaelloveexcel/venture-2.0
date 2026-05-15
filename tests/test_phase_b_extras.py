from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"
MCP = ROOT / "venture-mcp-server"
ENG = ROOT / "04-coding" / "venture-engine"
for p in (SCRIPTS, MCP, ENG):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from batch_guard import (  # noqa: E402
    LockIntegrityError,
    load_lock,
    sign_lock,
    write_lock,
)
from job_queue import JobQueue  # noqa: E402
from reply_intent_trainer import run_weekly_retrain  # noqa: E402
from state_engine import replay_from_artifacts, transition  # noqa: E402


def test_write_lock_sets_auditbound_schema(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BATCH_LOCK_SECRET", "unit-test-secret-phase-b")
    p = tmp_path / "batch.lock"
    body = {"version": 1, "batch_hash": "abc", "lock_schema": "replypilot-v1"}
    write_lock(body, path=p)
    lock = load_lock(p, allow_missing=False)
    assert lock.get("lock_schema") == "auditbound-v1"


def test_load_lock_accepts_replypilot_schema(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BATCH_LOCK_SECRET", "unit-test-secret-phase-b-2")
    p = tmp_path / "batch2.lock"
    raw = {
        "version": 1,
        "batch_hash": "bh2",
        "lock_schema": "replypilot-v1",
    }
    signed = sign_lock(raw)
    p.write_text(json.dumps(signed, indent=2), encoding="utf-8")
    lock = load_lock(p, allow_missing=False)
    assert lock.get("lock_schema") == "replypilot-v1"


def test_load_lock_rejects_unknown_schema(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BATCH_LOCK_SECRET", "unit-test-secret-phase-b-3")
    p = tmp_path / "batch3.lock"
    raw = {"version": 1, "batch_hash": "bh3", "lock_schema": "other-v9"}
    signed = sign_lock(raw)
    p.write_text(json.dumps(signed, indent=2), encoding="utf-8")
    with pytest.raises(LockIntegrityError):
        load_lock(p, allow_missing=False)


def test_delivery_ratio_metrics_empty_db(tmp_path) -> None:
    db = tmp_path / "m.db"
    jq = JobQueue(str(db))
    m = jq.get_delivery_ratio_metrics(7)
    assert m["sent"] == 0
    assert m["bounce_ratio"] == 0.0


def test_replay_from_artifacts_orders_by_timestamp() -> None:
    snaps = [{"send_timestamp": "2026-01-02T00:00:00Z", "k": 2}]
    sup = [{"created_at": "2026-01-01T00:00:00Z", "email": "a@b.co"}]
    rows, digest = replay_from_artifacts(snapshots=snaps, suppression_rows=sup)
    assert rows[0].source == "suppression_history"
    assert rows[1].source == "funnel_health_snapshot"
    assert len(digest) > 10


def test_trainer_missing_db(tmp_path) -> None:
    missing = tmp_path / "nope.db"
    r = run_weekly_retrain(db_path=missing)
    assert r.get("ok") is False


@pytest.mark.parametrize(
    ("cur", "ev", "nxt"),
    [
        ("READY", "SEND", "SENT"),
        ("SENT", "REPLY", "REPLIED"),
        ("SENT", "SUPPRESS", "SUPPRESSED"),
        ("SENT", "FAIL", "FAILED"),
    ],
)
def test_state_transition_table(cur, ev, nxt) -> None:
    assert transition(cur, ev) == nxt  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("cur", "ev"),
    [
        ("READY", "REPLY"),
        ("SENT", "SEND"),
        ("REPLIED", "SEND"),
    ],
)
def test_state_transition_invalid_raises(cur, ev) -> None:
    with pytest.raises(ValueError):
        transition(cur, ev)  # type: ignore[arg-type]


def test_trainer_writes_when_contrast_rows(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "train.db"
    out = tmp_path / "reply_intent.model.json"
    jq = JobQueue(str(db))
    for outcome in ("replied", "no_reply"):
        jq.record_reply_intent_training(
            "bid1",
            campaign_key="c1",
            message_hash="h1",
            features={"log_word_count": 120.0 if outcome == "replied" else 20.0},
            predicted_prob=0.5,
            actual_outcome=outcome,
        )
    r = run_weekly_retrain(db_path=db, model_path=out)
    assert r.get("ok") is True
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "weights" in data


def test_run_report_funnel_snapshots_default_empty() -> None:
    from run_report_schema import RunReport

    r = RunReport(run_id="x", timestamp_utc="2026-01-01T00:00:00Z")
    assert r.outbound.funnel_health_snapshots == []


def test_extract_event_id_synthetic_prefix() -> None:
    from resend_webhook_handler import _extract_event_id

    p = {"type": "email.opened", "data": {"to": ["z@z.com"]}}
    assert _extract_event_id(p).startswith("synthetic:")
