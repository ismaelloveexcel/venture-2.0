#!/usr/bin/env python3
"""
system_state_snapshot.py

Pure read-only state probe of Venture OS operational health.
Produces deterministic JSON snapshot used by policy_engine and dashboards.

NO side effects. NO mutations. Pure observation.
"""

import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict


class StateSnapshot(TypedDict):
    """Snapshot of system health at a point in time."""

    timestamp: str
    dlq_count: int
    dlq_growth_24h: int
    send_volume_24h: int
    reply_rate_7d: float
    failure_rate_24h: float
    cooldown_violations_24h: int
    orphan_outbound_events: int
    duplicate_initial_sends: int
    follow_up_pending: int
    last_outbound_sent: str | None
    compliance_status: str
    health_emoji: str
    system_mode: str


def get_db_path() -> Path:
    """Resolve venture_jobs.db from repo root."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    return repo_root / "venture_jobs.db"


def get_config_path(filename: str) -> Path:
    """Resolve config file path."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent.parent
    return repo_root / "04-coding" / "venture-engine" / "config" / filename


def query_dlq_count(db: sqlite3.Connection) -> int:
    """Count webhook DLQ rows."""
    cursor = db.execute("SELECT COUNT(*) FROM webhook_dlq")
    return cursor.fetchone()[0]


def query_dlq_growth_24h(db: sqlite3.Connection) -> int:
    """Count new DLQ rows in last 24h."""
    cursor = db.execute("""
        SELECT COUNT(*) FROM webhook_dlq
        WHERE created_at > datetime('now', '-1 day')
        """)
    return cursor.fetchone()[0]


def query_send_volume_24h(db: sqlite3.Connection) -> int:
    """Count outbound sends (status='sent') in last 24h."""
    cursor = db.execute("""
        SELECT COUNT(*) FROM outbound_events
        WHERE status = 'sent' AND created_at > datetime('now', '-1 day')
        """)
    return cursor.fetchone()[0]


def query_reply_rate_7d(db: sqlite3.Connection) -> float:
    """Calculate reply rate over last 7 days: replied funnel events / sent outbound events."""
    # Get count of replied funnel events in last 7 days
    replied = db.execute("""
        SELECT COUNT(DISTINCT prospect_id) FROM funnel_events
        WHERE stage = 'replied' AND created_at > datetime('now', '-7 days')
        """).fetchone()[0]

    # Get count of distinct prospects with sent outbound events in last 7 days
    sent = db.execute("""
        SELECT COUNT(DISTINCT prospect_id) FROM outbound_events
        WHERE status = 'sent' AND created_at > datetime('now', '-7 days')
        """).fetchone()[0]

    if sent == 0:
        return 0.0

    return round((replied / sent) * 100, 2)


def query_failure_rate_24h(db: sqlite3.Connection) -> float:
    """Calculate failure rate in last 24h: failures / attempts."""
    cursor = db.execute("""
        SELECT
            CAST(COUNT(CASE WHEN severity IN ('HARD', 'SOFT') THEN 1 END) AS FLOAT)
            / NULLIF(COUNT(*), 0) * 100
        FROM block_logs
        WHERE created_at > datetime('now', '-1 day')
        """)
    rate = cursor.fetchone()[0]
    return round(rate or 0.0, 2)


def query_cooldown_violations_24h(db: sqlite3.Connection) -> int:
    """Count cooldown policy blocks in last 24h."""
    cursor = db.execute("""
        SELECT COUNT(*) FROM block_logs
        WHERE block_type = 'compliance_cooldown'
        AND created_at > datetime('now', '-1 day')
        """)
    return cursor.fetchone()[0]


def query_orphan_outbound_events(db: sqlite3.Connection) -> int:
    """Count sent outbound events with no matching opportunity/prospect projection."""
    cursor = db.execute("""
        SELECT COUNT(*) FROM outbound_events oe
        WHERE oe.status = 'sent'
          AND oe.send_type NOT IN ('transactional', 'transactional_digest')
          AND NOT EXISTS (
              SELECT 1 FROM opportunities o
              WHERE o.business_id = oe.prospect_id
          )
          AND NOT EXISTS (
              SELECT 1 FROM prospect_state ps
              WHERE ps.prospect_id = oe.prospect_id
          )
        """)
    return cursor.fetchone()[0]


def query_duplicate_initial_sends(db: sqlite3.Connection) -> int:
    """Count prospects with duplicate initial sends (data integrity issue)."""
    cursor = db.execute("""
        SELECT COUNT(*) FROM (
            SELECT prospect_id, campaign_key
            FROM outbound_events
            WHERE send_type IN ('initial', 'initial_prospect') AND status = 'sent'
            GROUP BY prospect_id, campaign_key
            HAVING COUNT(*) > 1
        )
        """)
    return cursor.fetchone()[0]


def query_follow_up_pending(db: sqlite3.Connection) -> int:
    """Count prospects with initial send but no followup and no reply."""
    cursor = db.execute("""
        SELECT COUNT(DISTINCT oe.prospect_id) FROM outbound_events oe
        WHERE oe.status = 'sent'
        AND oe.send_type IN ('initial', 'initial_prospect')
        AND NOT EXISTS (
            SELECT 1 FROM outbound_events oe2
            WHERE oe2.prospect_id = oe.prospect_id
            AND oe2.campaign_key = oe.campaign_key
            AND oe2.send_type = 'followup'
            AND oe2.status = 'sent'
        )
        AND NOT EXISTS (
            SELECT 1 FROM funnel_events fe
            WHERE fe.prospect_id = oe.prospect_id
            AND fe.stage = 'replied'
        )
        """)
    return cursor.fetchone()[0]


def query_last_outbound_sent(db: sqlite3.Connection) -> str | None:
    """Get timestamp of last outbound send (status='sent')."""
    cursor = db.execute("""
        SELECT created_at FROM outbound_events
        WHERE status = 'sent'
        ORDER BY created_at DESC
        LIMIT 1
        """)
    result = cursor.fetchone()
    return result[0] if result else None


def query_compliance_status(db: sqlite3.Connection, config_path: Path) -> str:
    """Check if compliance config exists and is readable."""
    try:
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
                if config.get("unsubscribe_footer_enabled"):
                    return "ACTIVE"
                return "DISABLED"
    except Exception as e:
        return f"ERROR: {str(e)[:50]}"
    return "NOT_FOUND"


def load_current_system_mode(state_path: Path) -> str:
    """Load current system mode from system_state.json."""
    try:
        if state_path.exists():
            with open(state_path) as f:
                data = json.load(f)
                return data.get("system_mode", "NORMAL")
    except Exception:
        pass
    return "NORMAL"


def determine_health_emoji(snapshot: dict) -> str:
    """
    Determine health emoji based on snapshot data.

    🟢 Green:  DLQ < 3, failure rate < 5%, no orphans
    🟡 Yellow: DLQ < 10, failure rate < 15%, or minor orphans
    🔴 Red:    DLQ >= 10 or failure rate >= 15% or orphans > 0
    """
    dlq = snapshot["dlq_count"]
    failure_rate = snapshot["failure_rate_24h"]
    orphans = snapshot["orphan_outbound_events"]

    if dlq >= 10 or failure_rate >= 15 or orphans > 0:
        return "🔴"
    elif dlq >= 3 or failure_rate >= 5:
        return "🟡"
    else:
        return "🟢"


def take_snapshot() -> StateSnapshot:
    """
    Capture complete system state snapshot.

    Returns: StateSnapshot dict (JSON-serializable)
    Raises: Exception if DB not accessible
    """
    db_path = get_db_path()
    config_path = get_config_path("compliance.config.json")
    state_path = get_config_path("system_state.json")

    if not db_path.exists():
        raise FileNotFoundError(f"venture_jobs.db not found at {db_path}")

    db = sqlite3.connect(str(db_path))
    try:
        snapshot: StateSnapshot = {
            "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
            "dlq_count": query_dlq_count(db),
            "dlq_growth_24h": query_dlq_growth_24h(db),
            "send_volume_24h": query_send_volume_24h(db),
            "reply_rate_7d": query_reply_rate_7d(db),
            "failure_rate_24h": query_failure_rate_24h(db),
            "cooldown_violations_24h": query_cooldown_violations_24h(db),
            "orphan_outbound_events": query_orphan_outbound_events(db),
            "duplicate_initial_sends": query_duplicate_initial_sends(db),
            "follow_up_pending": query_follow_up_pending(db),
            "last_outbound_sent": query_last_outbound_sent(db),
            "compliance_status": query_compliance_status(db, config_path),
            "health_emoji": "",  # Will fill below
            "system_mode": load_current_system_mode(state_path),
        }

        snapshot["health_emoji"] = determine_health_emoji(snapshot)
        return snapshot
    finally:
        db.close()


def main():
    """CLI: print snapshot as JSON."""
    try:
        snapshot = take_snapshot()
        print(json.dumps(snapshot, indent=2))
        sys.exit(0)
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
