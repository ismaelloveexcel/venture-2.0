#!/usr/bin/env python3
"""
Replay audit — recompute outreach_state + evidence from lifecycle_events (+ snapshots)
and compare to opportunities row. Exit 1 if any mismatch.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys
from typing import Any, Dict, List

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent.parent / "venture-mcp-server"))

from job_queue import JobQueue
from lifecycle_engine import STATE_ENGINE_VERSION, extract_evidence_score_from_rows, replay_outreach_state_from_rows


def main() -> int:
    base = pathlib.Path(__file__).resolve().parent.parent.parent
    db = base / "venture_jobs.db"
    if not db.exists():
        print(f"[replay_audit] No DB at {db}")
        return 0

    jq = JobQueue(db_path=str(db))
    mismatches = []
    engine_drift: List[Dict[str, Any]] = []
    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM opportunities").fetchall()

    for row in rows:
        bid = str(row["business_id"])
        stored_state = row["outreach_state"]
        stored_evid = row["evidence_score"]
        stored_ver = row["state_engine_version"] if "state_engine_version" in row.keys() else ""
        if stored_ver and str(stored_ver) != STATE_ENGINE_VERSION:
            engine_drift.append({
                "business_id": bid,
                "stored_engine_version": stored_ver,
                "current_code_version": STATE_ENGINE_VERSION,
                "note": "replay logic may differ from when events were written; review migration",
            })
        opp_id = jq.opportunity_id_for(bid)
        with sqlite3.connect(db) as conn:
            ev_rows = jq._fetch_lifecycle_rows(conn, opp_id)
            snap = jq._get_lifecycle_snapshot(conn, opp_id)
        if not ev_rows:
            continue
        r_state, _ = replay_outreach_state_from_rows(ev_rows, snap)
        r_evid = extract_evidence_score_from_rows(ev_rows, snap)
        if str(stored_state) != str(r_state) or abs(float(stored_evid or 0) - float(r_evid or 0)) > 1e-6:
            mismatches.append({
                "business_id": bid,
                "stored_state": stored_state,
                "recomputed_state": r_state,
                "stored_evidence": stored_evid,
                "recomputed_evidence": r_evid,
                "stored_engine_version": stored_ver,
                "event_count": len(ev_rows),
            })

    out = {
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "state_engine_version_code": STATE_ENGINE_VERSION,
        "engine_version_drift_warnings": engine_drift,
    }
    print(json.dumps(out, indent=2))
    return 1 if mismatches else 0


if __name__ == "__main__":
    sys.exit(main())
