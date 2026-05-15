from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"


@pytest.fixture()
def pg_mod(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import prospect_gate as pg

    return pg


def test_verify_gate_eligible_audit_parity_ok(pg_mod, tmp_path: Path):
    pg = pg_mod
    audit = [
        {
            "run_id": "r1",
            "email": "A@Example.COM",
            "classification": "ELIGIBLE",
        },
        {
            "run_id": "r1",
            "email": "b@example.com",
            "classification": "DROP",
        },
    ]
    eligible_ok = [{"email": "a@example.com"}]
    audit_ok = [audit[0], audit[1]]
    assert pg.verify_gate_eligible_audit_parity(
        eligible_rows=eligible_ok, audit_rows=audit_ok, run_id="r1"
    ) == []


def test_verify_gate_eligible_audit_parity_mismatch(pg_mod):
    pg = pg_mod
    audit = [
        {"run_id": "r1", "email": "only@audit.com", "classification": "ELIGIBLE"},
    ]
    eligible = [{"email": "only@csv.com"}]
    err = pg.verify_gate_eligible_audit_parity(
        eligible_rows=eligible, audit_rows=audit, run_id="r1"
    )
    assert err


def test_verify_written_round_trip(pg_mod, tmp_path: Path):
    pg = pg_mod
    out = tmp_path / "06-sales" / "prospects.csv"
    rows = [
        {
            "company_name": "C",
            "domain": "c.io",
            "name": "N",
            "email": "User@C.io",
            "role": "CEO",
            "industry": "x",
            "pain_signal": "p",
            "linkedin_url": "",
            "validation_status": "READY",
            "validation_reason": "ok",
            "source": "t",
            "run_id": "run9",
        }
    ]
    fields = list(rows[0].keys())
    pg.write_eligible_prospects_csv(out, rows, fields)
    errs = pg.verify_written_eligible_prospects_csv(
        out, eligible_rows=rows, run_id="run9", fieldnames=fields
    )
    assert errs == []
    text = out.read_text(encoding="utf-8")
    assert "user@c.io" in text


def test_write_eligible_normalizes_email(pg_mod, tmp_path: Path):
    pg = pg_mod
    out = tmp_path / "p.csv"
    pg.write_eligible_prospects_csv(
        out,
        [
            {
                "company_name": "C",
                "domain": "c.io",
                "name": "N",
                "email": "  Mix@Case.IO ",
                "role": "CEO",
                "industry": "x",
                "pain_signal": "p",
                "linkedin_url": "",
                "validation_status": "READY",
                "validation_reason": "ok",
                "source": "t",
                "run_id": "r",
            }
        ],
        [
            "company_name",
            "domain",
            "name",
            "email",
            "role",
            "industry",
            "pain_signal",
            "linkedin_url",
            "validation_status",
            "validation_reason",
            "source",
            "run_id",
        ],
    )
    body = out.read_text(encoding="utf-8").lower()
    assert "mix@case.io" in body
