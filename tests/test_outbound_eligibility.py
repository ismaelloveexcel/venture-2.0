from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "04-coding" / "scripts"


@pytest.fixture()
def elig_mod(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import outbound_eligibility as oe

    return oe


def _write_audit(path: Path, data_rows: list[dict]) -> None:
    from prospect_gate import PROSPECT_AUDIT_HEADER

    path.parent.mkdir(parents=True, exist_ok=True)
    fields = PROSPECT_AUDIT_HEADER.split(",")
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in data_rows:
            w.writerow(row)


def _write_prospects_csv(path: Path, with_validation: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cols = ["name", "email", "run_id"]
    if with_validation:
        cols.append("validation_status")
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        if with_validation:
            w.writerow(
                {
                    "name": "A",
                    "email": "a@example.com",
                    "run_id": "run1",
                    "validation_status": "READY",
                }
            )
        else:
            w.writerow({"name": "A", "email": "a@example.com", "run_id": "run1"})


def test_prospect_csv_requires_audit_join_only_when_column(elig_mod, tmp_path: Path):
    oe = elig_mod
    p1 = tmp_path / "p1.csv"
    _write_prospects_csv(p1, with_validation=False)
    assert oe.prospect_csv_requires_audit_join(p1) is False
    p2 = tmp_path / "p2.csv"
    _write_prospects_csv(p2, with_validation=True)
    assert oe.prospect_csv_requires_audit_join(p2) is True


def test_load_audit_missing_halts(elig_mod, tmp_path: Path):
    oe = elig_mod
    missing = tmp_path / "07-kpis" / "prospect_audit_log.csv"
    with pytest.raises(oe.OutboundEligibilityAuditError, match="missing"):
        oe.load_audit_eligibility_index(missing)


def test_load_audit_header_mismatch_halts(elig_mod, tmp_path: Path):
    oe = elig_mod
    path = tmp_path / "07-kpis" / "prospect_audit_log.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("wrong,header\n1,2\n", encoding="utf-8")
    with pytest.raises(oe.OutboundEligibilityAuditError, match="mismatch"):
        oe.load_audit_eligibility_index(path)


def test_filter_keeps_only_eligible_same_run(elig_mod, tmp_path: Path):
    oe = elig_mod
    audit = tmp_path / "07-kpis" / "prospect_audit_log.csv"
    base_ts = "2026-01-01T12:00:00Z"
    _write_audit(
        audit,
        [
            {
                "timestamp_utc": base_ts,
                "run_id": "run1",
                "cohort_id": "c1",
                "email": "keep@example.com",
                "name": "K",
                "company_name": "Co",
                "role": "R",
                "domain": "example.com",
                "validation_status": "READY",
                "validation_reason": "ok",
                "dedup_status": "unique",
                "suppression_status": "clear",
                "drop_reason": "",
                "classification": "ELIGIBLE",
            },
            {
                "timestamp_utc": base_ts,
                "run_id": "run1",
                "cohort_id": "c1",
                "email": "drop@example.com",
                "name": "D",
                "company_name": "Co2",
                "role": "R",
                "domain": "example.com",
                "validation_status": "READY",
                "validation_reason": "ok",
                "dedup_status": "unique",
                "suppression_status": "clear",
                "drop_reason": "dedup",
                "classification": "DROP",
            },
        ],
    )
    prospects_path = tmp_path / "06-sales" / "prospects.csv"
    _write_prospects_csv(prospects_path, with_validation=True)

    prospects = [
        {
            "email": "keep@example.com",
            "run_id": "run1",
            "validation_status": "READY",
        },
        {
            "email": "drop@example.com",
            "run_id": "run1",
            "validation_status": "READY",
        },
        {
            "email": "unknown@example.com",
            "run_id": "run1",
            "validation_status": "READY",
        },
    ]
    r = oe.filter_prospects_for_outbound_send(
        prospects,
        prospects_path=prospects_path,
        data_base=tmp_path,
        current_run_id="run1",
    )
    assert len(r.prospects) == 1
    assert r.prospects[0]["email"] == "keep@example.com"
    assert r.skipped == 2
    assert r.all_ineligible_after_filter is False

    skip_path = tmp_path / "logs" / "send_skipped_log.csv"
    assert skip_path.is_file()
    lines = skip_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2 skips


def test_filter_empty_audit_index_fail_safe(elig_mod, tmp_path: Path):
    oe = elig_mod
    audit = tmp_path / "07-kpis" / "prospect_audit_log.csv"
    _write_audit(audit, [])
    prospects_path = tmp_path / "06-sales" / "prospects.csv"
    _write_prospects_csv(prospects_path, with_validation=True)
    prospects = [
        {"email": "a@example.com", "run_id": "run1", "validation_status": "READY"},
    ]
    r = oe.filter_prospects_for_outbound_send(
        prospects,
        prospects_path=prospects_path,
        data_base=tmp_path,
        current_run_id="run1",
    )
    assert r.prospects == []
    assert r.skipped == 1
    assert r.all_ineligible_after_filter is True


def test_emit_no_eligible_prospects_event_json(elig_mod, capsys: pytest.CaptureFixture[str]):
    oe = elig_mod
    oe.emit_no_eligible_prospects_event(run_id="rid-9")
    out = capsys.readouterr().out.strip()
    payload = json.loads(out)
    assert payload["event"] == "PIPELINE_NO_ELIGIBLE_PROSPECTS"
    assert payload["run_id"] == "rid-9"


def test_append_send_skipped_header_mismatch_halts(elig_mod, tmp_path: Path):
    oe = elig_mod
    path = tmp_path / "logs" / "send_skipped_log.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("bad,header\n", encoding="utf-8")
    with pytest.raises(oe.OutboundEligibilityAuditError, match="send_skipped"):
        oe.append_send_skipped_log(
            tmp_path,
            run_id="r",
            email="e@e.com",
            skip_reason="test",
        )
