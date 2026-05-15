from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PB_DIR = ROOT / "04-coding" / "scripts"


@pytest.fixture()
def prospect_builder(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(PB_DIR))
    import prospect_builder as pb

    return pb


def test_strict_prospect_mode_exit_zero_when_not_ready_forensic_only(
    prospect_builder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """STRICT_PROSPECT_MODE is forensic-only; builder exits 0; summary file is written."""
    pb = prospect_builder
    monkeypatch.setenv("STRICT_PROSPECT_MODE", "1")
    monkeypatch.setattr(pb, "DATA_BASE", tmp_path)
    monkeypatch.setattr(pb, "OUTPUT_FILE", tmp_path / "06-sales" / "prospects.csv")
    monkeypatch.setattr(pb, "REPO_ROOT", tmp_path)
    db = tmp_path / "venture_jobs.db"
    monkeypatch.setenv("VENTURE_DB_PATH", str(db))
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE suppression_list (email TEXT, reason TEXT, source TEXT, created_at TEXT)"
    )
    conn.execute(
        """CREATE TABLE outbound_events (
            id INTEGER PRIMARY KEY, prospect_id TEXT, campaign_key TEXT,
            recipient_email TEXT, message_hash TEXT, status TEXT,
            provider_id TEXT, created_at TEXT, send_type TEXT
        )"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        pb,
        "build_prospect_list",
        lambda *a, **k: [
            {
                "company_name": "Co",
                "domain": "co.io",
                "name": "N",
                "email": "n@co.io",
                "role": "CEO",
                "industry": "saas",
                "pain_signal": "x",
                "linkedin_url": "",
                "source": "demo",
            }
        ],
    )
    monkeypatch.setattr(pb, "validate_prospect", lambda row: ("REVIEW", "ambiguous_title"))
    assert pb.run(count=1, allow_template=True) == 0
    summ_dir = tmp_path / "07-kpis" / "strict_mode_summary"
    assert summ_dir.is_dir()
    assert any(summ_dir.glob("*.json"))


def test_strict_prospect_mode_ok_when_all_ready(
    prospect_builder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    pb = prospect_builder
    monkeypatch.setenv("STRICT_PROSPECT_MODE", "1")
    monkeypatch.setattr(pb, "DATA_BASE", tmp_path)
    monkeypatch.setattr(pb, "OUTPUT_FILE", tmp_path / "06-sales" / "prospects.csv")
    monkeypatch.setattr(pb, "REPO_ROOT", tmp_path)
    db = tmp_path / "vj.db"
    monkeypatch.setenv("VENTURE_DB_PATH", str(db))
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE suppression_list (email TEXT, reason TEXT, source TEXT, created_at TEXT)"
    )
    conn.execute(
        """CREATE TABLE outbound_events (
            id INTEGER PRIMARY KEY, prospect_id TEXT, campaign_key TEXT,
            recipient_email TEXT, message_hash TEXT, status TEXT,
            provider_id TEXT, created_at TEXT, send_type TEXT
        )"""
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(
        pb,
        "build_prospect_list",
        lambda *a, **k: [
            {
                "company_name": "Co",
                "domain": "co.io",
                "name": "N",
                "email": "n@co.io",
                "role": "CEO",
                "industry": "saas",
                "pain_signal": "x",
                "linkedin_url": "",
                "source": "demo",
            }
        ],
    )
    monkeypatch.setattr(pb, "validate_prospect", lambda row: ("READY", "complete_profile"))
    assert pb.run(count=1, allow_template=True) == 0
    assert (tmp_path / "06-sales" / "prospects.csv").is_file()
