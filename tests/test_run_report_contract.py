from __future__ import annotations

import json
from pathlib import Path

from run_report_schema import CohortMetadataModel, OutboundSection, RunReport
from run_report_writer import parse_run_report, write_run_report_atomic


def test_run_report_schema_roundtrip():
    r = RunReport(run_id="abc", timestamp_utc="2026-01-01T00:00:00Z")
    data = json.loads(r.model_dump_json())
    r2 = RunReport.model_validate(data)
    assert r2.run_id == "abc"
    assert r2.schema_version == "1.0"
    assert r2.outbound.money_path_source == "none"


def test_outbound_pipeline_telemetry_roundtrip(tmp_path: Path):
    p = tmp_path / "rr_telemetry.json"
    r = RunReport(
        run_id="t2",
        timestamp_utc="2026-01-03T00:00:00Z",
        outbound=OutboundSection(
            status="SUCCESS",
            pipeline_telemetry={"schema_version": 1, "run_health": {"sent": 2, "blocked": 1}},
        ),
    )
    write_run_report_atomic(p, r)
    back = parse_run_report(p)
    assert back.outbound.pipeline_telemetry.schema_version == 1
    assert isinstance(back.outbound.pipeline_telemetry.run_health, dict)


def test_outbound_phase1_structured_telemetry_roundtrip(tmp_path: Path):
    p = tmp_path / "rr_phase1_telemetry.json"
    r = RunReport(
        run_id="p1",
        timestamp_utc="2026-05-15T00:00:00Z",
        outbound=OutboundSection(
            status="SUCCESS",
            pipeline_telemetry={
                "schema_version": 1,
                "phase1_structured": {
                    "version": 1,
                    "events": [
                        {"event": "queue_operations", "jobs_total_delta": 3},
                        {"event": "governance_blocks", "block_logs_delta": 1},
                    ],
                },
            },
            orchestrator_telemetry={
                "started_at_utc": "2026-05-15T00:00:00Z",
                "finished_at_utc": "2026-05-15T00:00:12Z",
                "execute_outbound": True,
                "dry_run": True,
                "venture_pipeline_subprocess_ran": True,
                "subprocess_return_code": 0,
            },
        ),
    )
    write_run_report_atomic(p, r)
    back = parse_run_report(p)
    assert isinstance(back.outbound.pipeline_telemetry.phase1_structured, dict)
    assert back.outbound.orchestrator_telemetry.execute_outbound is True
    assert back.outbound.orchestrator_telemetry.subprocess_return_code == 0


def test_cohort_metadata_policy_fingerprint_matches_batch_guard() -> None:
    import hashlib

    from batch_guard import CANONICAL_SUBJECT, CTA_STRING

    expected = hashlib.sha256(
        (CANONICAL_SUBJECT + "\n" + CTA_STRING).encode("utf-8")
    ).hexdigest()[:12]
    cm = CohortMetadataModel(
        cohort_id="c",
        run_id="r",
        message_version="m",
        guard_version="g",
        generator_version="x",
        git_sha="unknown",
        freeze_timestamp_utc="2026-01-01T00:00:00+00:00",
        subject_cta_fingerprint=expected,
    )
    assert cm.subject_cta_fingerprint == expected


def test_cohort_metadata_roundtrip(tmp_path: Path):
    p = tmp_path / "rr_cohort.json"
    cm = CohortMetadataModel(
        cohort_id="c1",
        run_id="r1",
        message_version="mv",
        guard_version="gv",
        generator_version="xv",
        git_sha="unknown",
    )
    r = RunReport(
        run_id="coh",
        timestamp_utc="2026-02-01T00:00:00Z",
        outbound=OutboundSection(status="SUCCESS", cohort_metadata=cm),
    )
    write_run_report_atomic(p, r)
    back = parse_run_report(p)
    assert back.outbound.cohort_metadata is not None
    assert back.outbound.cohort_metadata.cohort_id == "c1"
    assert back.outbound.cohort_metadata.git_sha == "unknown"


def test_atomic_write_roundtrip(tmp_path: Path):
    p = tmp_path / "run_report.json"
    r = RunReport(
        run_id="x1",
        timestamp_utc="2026-01-02T00:00:00Z",
        outbound=OutboundSection(status="SKIPPED", phases=["test"]),
    )
    write_run_report_atomic(p, r)
    back = parse_run_report(p)
    assert back.outbound.status == "SKIPPED"
    assert back.run_id == "x1"
