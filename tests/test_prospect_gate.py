from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"


@pytest.fixture()
def gate_mod(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import prospect_gate as pg

    return pg


def _mk_db(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE suppression_list (email TEXT NOT NULL, reason TEXT, source TEXT, created_at TEXT)"
    )
    conn.execute(
        """CREATE TABLE outbound_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prospect_id TEXT NOT NULL,
            campaign_key TEXT NOT NULL,
            recipient_email TEXT NOT NULL,
            message_hash TEXT NOT NULL,
            status TEXT NOT NULL,
            provider_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            send_type TEXT NOT NULL DEFAULT 'initial'
        )"""
    )
    conn.commit()
    conn.close()


def test_gate_dedup_second_row_drop(gate_mod, tmp_path: Path):
    pg = gate_mod
    db = tmp_path / "q.db"
    _mk_db(db)
    rows = [
        {
            "company_name": "Co",
            "domain": "co.io",
            "name": "N",
            "email": "n@co.io",
            "role": "CEO",
            "industry": "saas",
            "pain_signal": "x",
        },
        {
            "company_name": "Co",
            "domain": "co.io",
            "name": "N",
            "email": "n@co.io",
            "role": "CEO",
            "industry": "saas",
            "pain_signal": "x",
        },
    ]

    def val(row):
        return "READY", "complete_profile"

    r = pg.run_prospect_gate(
        raw_rows=rows,
        run_id="t1",
        validate_prospect_fn=val,
        db_path=db,
    )
    assert len(r.eligible_rows) == 1
    assert sum(1 for a in r.audit_rows if a["classification"] == "DROP") == 1
    assert any(a["drop_reason"] == "dedup" for a in r.audit_rows)


def test_gate_hard_suppression_dominates_dedup(gate_mod, tmp_path: Path):
    pg = gate_mod
    db = tmp_path / "q2.db"
    _mk_db(db)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO suppression_list VALUES (?,?,?,?)",
        ["n@co.io", "opt", "manual", "2026-01-01"],
    )
    conn.commit()
    conn.close()
    rows = [
        {
            "company_name": "Co",
            "domain": "co.io",
            "name": "N",
            "email": "n@co.io",
            "role": "CEO",
            "industry": "saas",
            "pain_signal": "x",
        },
    ]

    def val(row):
        return "READY", "complete_profile"

    r = pg.run_prospect_gate(
        raw_rows=rows,
        run_id="t2",
        validate_prospect_fn=val,
        db_path=db,
    )
    assert r.eligible_rows == []
    ar = r.audit_rows[0]
    assert ar["drop_reason"] == "hard_suppressed"


def test_gate_db_unavailable_all_drop(gate_mod, tmp_path: Path):
    pg = gate_mod
    bad = tmp_path / "missing_dir" / "nope.db"
    rows = [
        {
            "company_name": "Co",
            "domain": "co.io",
            "name": "N",
            "email": "n@co.io",
            "role": "CEO",
            "industry": "saas",
            "pain_signal": "x",
        },
    ]

    def val(row):
        return "READY", "complete_profile"

    r = pg.run_prospect_gate(
        raw_rows=rows,
        run_id="t3",
        validate_prospect_fn=val,
        db_path=bad,
    )
    assert r.db_ok is False
    assert r.eligible_rows == []
    assert r.audit_rows[0]["drop_reason"] == "suppression_db_unavailable"


def test_audit_header_mismatch_raises(gate_mod, tmp_path: Path):
    pg = gate_mod
    p = tmp_path / "07-kpis" / "prospect_audit_log.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("wrong,header\n", encoding="utf-8")
    with pytest.raises(ValueError, match="header mismatch"):
        pg.append_prospect_audit_log(tmp_path, [{"timestamp_utc": "x", "run_id": "r"}])


def test_append_audit_creates_file(gate_mod, tmp_path: Path):
    pg = gate_mod
    row = {
        "timestamp_utc": "2026-01-01T00:00:00Z",
        "run_id": "r1",
        "cohort_id": "",
        "email": "a@b.co",
        "name": "A",
        "company_name": "B",
        "role": "CEO",
        "domain": "b.co",
        "validation_status": "READY",
        "validation_reason": "complete_profile",
        "dedup_status": "PASS",
        "suppression_status": "PASS",
        "drop_reason": "",
        "classification": "ELIGIBLE",
    }
    pg.append_prospect_audit_log(tmp_path, [row])
    out = tmp_path / "07-kpis" / "prospect_audit_log.csv"
    assert out.is_file()
    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == pg.PROSPECT_AUDIT_HEADER
    assert "a@b.co" in lines[1]
