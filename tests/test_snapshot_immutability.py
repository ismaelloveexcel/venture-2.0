from __future__ import annotations

import sqlite3

import pytest
from pydantic import ValidationError

from job_queue import JobQueue
from run_report_schema import FunnelHealthSnapshotModel, OutboundSection


def test_funnel_health_snapshot_model_is_frozen() -> None:
    snap = FunnelHealthSnapshotModel(send_timestamp="2026-01-01T00:00:00Z")
    with pytest.raises(ValidationError):
        snap.send_timestamp = "x"  # type: ignore[misc]


def test_outbound_snapshots_only_append() -> None:
    a = FunnelHealthSnapshotModel(prospect_id="1", send_timestamp="t1")
    b = FunnelHealthSnapshotModel(prospect_id="2", send_timestamp="t2")
    o = OutboundSection()
    o2 = o.model_copy(update={"funnel_health_snapshots": list(o.funnel_health_snapshots) + [a]})
    o3 = o2.model_copy(update={"funnel_health_snapshots": list(o2.funnel_health_snapshots) + [b]})
    assert len(o3.funnel_health_snapshots) == 2
    assert o3.funnel_health_snapshots[0].prospect_id == "1"


def test_sqlite_funnel_snapshots_insert_only(tmp_path) -> None:
    db = tmp_path / "snap.db"
    jq = JobQueue(str(db))
    for _ in range(3):
        jq.save_funnel_health_snapshot(
            dry_run=True,
            generated=1,
            qualified=1,
            sent=0,
            blocked=0,
            reply_rate_estimate=0.0,
            extra={"k": 1},
        )
    with sqlite3.connect(str(db)) as conn:
        n = conn.execute("SELECT COUNT(*) FROM funnel_health_snapshots").fetchone()[0]
    assert int(n) == 3
