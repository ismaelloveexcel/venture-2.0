"""
Job Queue for Venture OS — SQLite-backed fault-tolerant operation tracking.

Tracks all operations (email lookups, Notion syncs, etc.) with:
- Automatic retry of failed jobs
- Prevent duplicate operations
- Audit trail of all work done
- Resume interrupted pipelines without data loss
"""

import contextlib
import sqlite3
import json
import logging
import hashlib
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from lifecycle_engine import (
    LifecycleEventType,
    LifecycleSnapshot,
    STATE_ENGINE_VERSION,
    extract_evidence_score_from_rows,
    last_block_reason,
    replay_outreach_state_from_rows,
)
from lifecycle_validation import (
    LifecycleEventValidationError,
    normalize_lifecycle_payload,
    validate_lifecycle_event,
)

logger = logging.getLogger(__name__)

LIFECYCLE_SNAPSHOT_INTERVAL = 20

# Default severity when log_block(..., severity=None)
BLOCK_SEVERITY_DEFAULTS: Dict[str, str] = {
    "INTEGRITY_BLOCK": "HARD",
    "COMPLIANCE_BLOCK": "HARD",
    "CAPACITY_BLOCK": "HARD",
    "QUALITY_BLOCK": "SOFT",
    "GENERAL_BLOCK": "SOFT",
    "DELIVERY_BLOCK": "HARD",
    "DELIVERY_WARN": "SOFT",
    "OPERATOR_PAUSE_BLOCK": "HARD",
}

SUPPRESSION_REASONS_ALLOWED: frozenset[str] = frozenset(
    {"unsubscribe", "hard_bounce", "soft_bounce", "complaint", "manual"}
)
SUPPRESSION_SOURCES_ALLOWED: frozenset[str] = frozenset(
    {"link", "stop_reply", "resend_webhook", "operator"}
)
OUTBOUND_EVENT_STATUSES_ALLOWED: frozenset[str] = frozenset({"sent", "dry_run"})


def _parse_json_dict(raw: Optional[str]) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


class JobStatus(Enum):
    """Job lifecycle states."""
    PENDING = "pending"           # Queued, waiting to run
    IN_PROGRESS = "in_progress"   # Currently running
    COMPLETED = "completed"       # Finished successfully
    FAILED = "failed"             # Failed, will retry
    ABANDONED = "abandoned"       # Failed max retries, gave up


class JobAction(Enum):
    """Types of work that can be queued."""
    EMAIL_LOOKUP = "email_lookup"           # Hunter.io email enrichment
    GENERATE_MESSAGE = "generate_message"   # OpenAI outreach generation
    NOTION_SYNC = "notion_sync"             # Sync prospect/KPI to Notion
    AIRTABLE_SYNC = "airtable_sync"         # Sync to Airtable
    SEND_EMAIL = "send_email"               # Resend email delivery
    SCORE_IDEA = "score_idea"               # OpenAI idea scoring


@dataclass
class Job:
    """A single unit of work with retry semantics."""
    id: str                          # UUID
    prospect_id: Optional[str]       # FK to prospect in CSV
    action: JobAction                # What work to do
    status: JobStatus = JobStatus.PENDING
    context: Dict[str, Any] = field(default_factory=dict)  # Serialized args (email, company, etc.)
    result: Optional[str] = ""       # What came back (email found, error message, etc.)
    error: str = ""                  # Error message if failed
    retry_count: int = 0             # How many times we've tried
    max_retries: int = 3             # Give up after this many failures
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            **asdict(self),
            "action": self.action.value,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "context": json.dumps(self.context),
        }


class JobQueue:
    """SQLite-backed queue for resilient async operations."""
    
    def __init__(self, db_path: str = "venture_jobs.db"):
        """
        Initialize job queue.
        
        Args:
            db_path: Path to SQLite database (default: workspace root)
        """
        self.db_path = Path(db_path)
        self._init_db()
    
    @staticmethod
    def _configure_connection(conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")

    def _connect(self) -> sqlite3.Connection:
        """Open SQLite with WAL, NORMAL sync, and busy_timeout on every connection."""
        conn = sqlite3.connect(self.db_path)
        self._configure_connection(conn)
        return conn

    @contextlib.contextmanager
    def transaction(self):
        """
        One configured connection with BEGIN IMMEDIATE, commit on success, rollback on error.
        Use for atomic multi-statement updates (lifecycle + projections). Do not call
        sqlite3.connect(self.db_path) directly for transactional work.
        """
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    prospect_id TEXT,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    context TEXT DEFAULT '{}',
                    result TEXT,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_prospect ON jobs(prospect_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_action_status ON jobs(action, status)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS outbound_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prospect_id TEXT NOT NULL,
                    campaign_key TEXT NOT NULL,
                    recipient_email TEXT NOT NULL,
                    message_hash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    provider_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outbound_email
                ON outbound_events(recipient_email, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suppression_list (
                    email TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS suppression_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT,
                    reason TEXT,
                    source TEXT,
                    operator TEXT,
                    notes TEXT,
                    created_at TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS resend_webhook_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    email TEXT,
                    payload TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_resend_webhook_events_type_time
                ON resend_webhook_events(event_type, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS funnel_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prospect_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_funnel_stage_time
                ON funnel_events(stage, created_at)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_funnel_prospect_stage_time
                ON funnel_events(prospect_id, stage, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS prospect_state (
                    prospect_id TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    stage TEXT NOT NULL,
                    status_reason TEXT DEFAULT '',
                    trust_score REAL NOT NULL DEFAULT 0.0,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reasons TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_decision_entity
                ON decision_logs(entity_type, entity_id, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS block_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_type TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    block_type TEXT NOT NULL DEFAULT 'GENERAL_BLOCK',
                    reason TEXT NOT NULL,
                    details TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_block_entity
                ON block_logs(entity_type, entity_id, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trust_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    trust_delta REAL NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trust_business_time
                ON trust_events(business_id, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS client_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id TEXT NOT NULL UNIQUE,
                    name TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_control (
                    control_key TEXT PRIMARY KEY,
                    control_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO system_control (control_key, control_value, updated_at)
                VALUES ('outreach_frozen', 'false', ?)
            """, [datetime.now().isoformat()])
            conn.execute("""
                CREATE TABLE IF NOT EXISTS opportunities (
                    id TEXT PRIMARY KEY,
                    business_id TEXT NOT NULL UNIQUE,
                    outreach_state TEXT NOT NULL DEFAULT 'COLD',
                    evidence_score REAL NOT NULL DEFAULT 0.0,
                    pipeline_stage TEXT NOT NULL DEFAULT '',
                    name TEXT DEFAULT '',
                    company TEXT DEFAULT '',
                    email TEXT DEFAULT '',
                    status_reason TEXT DEFAULT '',
                    trust_score_cached REAL NOT NULL DEFAULT 0.0,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lifecycle_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    opportunity_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT DEFAULT '{}',
                    source TEXT NOT NULL DEFAULT 'system',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_lifecycle_opp_id
                ON lifecycle_events(opportunity_id, id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lifecycle_snapshots (
                    opportunity_id TEXT PRIMARY KEY,
                    after_event_id INTEGER NOT NULL,
                    outreach_state TEXT NOT NULL,
                    opened_count INTEGER NOT NULL DEFAULT 0,
                    evidence_score REAL NOT NULL DEFAULT 0.0,
                    state_engine_version TEXT NOT NULL DEFAULT '1.0.0',
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS reply_intent_training_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    business_id TEXT NOT NULL,
                    campaign_key TEXT NOT NULL DEFAULT '',
                    message_hash TEXT NOT NULL DEFAULT '',
                    features_json TEXT NOT NULL DEFAULT '{}',
                    predicted_prob REAL NOT NULL,
                    actual_outcome TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    resolved_at TEXT DEFAULT ''
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_reply_intent_business
                ON reply_intent_training_data(business_id, actual_outcome, created_at)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS funnel_health_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_at TEXT NOT NULL,
                    dry_run INTEGER NOT NULL DEFAULT 0,
                    generated INTEGER NOT NULL DEFAULT 0,
                    qualified INTEGER NOT NULL DEFAULT 0,
                    sent INTEGER NOT NULL DEFAULT 0,
                    blocked INTEGER NOT NULL DEFAULT 0,
                    reply_rate_estimate REAL NOT NULL DEFAULT 0.0,
                    payload_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS webhook_dlq (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source TEXT NOT NULL DEFAULT 'resend',
                    payload TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            self._ensure_column(conn, "prospect_state", "trust_score", "REAL NOT NULL DEFAULT 0.0")
            self._ensure_column(conn, "prospect_state", "outreach_state", "TEXT NOT NULL DEFAULT 'COLD'")
            self._ensure_column(conn, "block_logs", "block_type", "TEXT NOT NULL DEFAULT 'GENERAL_BLOCK'")
            self._ensure_column(conn, "block_logs", "severity", "TEXT NOT NULL DEFAULT 'SOFT'")
            self._ensure_column(conn, "opportunities", "state_engine_version", "TEXT NOT NULL DEFAULT '1.0.0'")
            self._ensure_column(
                conn, "lifecycle_snapshots", "state_engine_version", "TEXT NOT NULL DEFAULT '1.0.0'"
            )
            self._migrate_outbound_behavior_constraint(conn)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outbound_initial_sent_time
                ON outbound_events(send_type, status, created_at)
            """)
            conn.commit()

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
        """
        Add a column when migrating older local SQLite files.
        """
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        existing = {r[1] for r in rows}
        if column in existing:
            return
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _migrate_outbound_behavior_constraint(self, conn: sqlite3.Connection) -> None:
        """
        One logical send per (prospect_id, campaign_key, send_type).
        Replaces message_hash-based dedupe for behavioral idempotency.
        """
        self._ensure_column(conn, "outbound_events", "send_type", "TEXT NOT NULL DEFAULT 'initial'")
        conn.execute("DROP INDEX IF EXISTS idx_outbound_dedupe")
        conn.execute("""
            DELETE FROM outbound_events WHERE id NOT IN (
                SELECT MIN(id) FROM outbound_events GROUP BY prospect_id, campaign_key, send_type
            )
        """)
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_outbound_behavior
            ON outbound_events(prospect_id, campaign_key, send_type)
        """)

    def record_webhook_dlq(self, source: str, payload: str, error: str) -> None:
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO webhook_dlq (source, payload, error, created_at)
                VALUES (?, ?, ?, ?)
            """, [source, payload, error, ts])
            conn.commit()

    def count_webhook_dlq(self) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM webhook_dlq").fetchone()
        return int(row[0] if row else 0)

    def list_webhook_dlq(
        self,
        limit: int = 50,
        offset: int = 0,
        ids: Optional[List[int]] = None,
    ) -> List[Dict[str, Any]]:
        """Oldest-first for fair replay. When ids is set, limit/offset are ignored."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            if ids:
                qs = ",".join("?" * len(ids))
                rows = conn.execute(
                    f"""SELECT id, source, payload, error, created_at FROM webhook_dlq
                        WHERE id IN ({qs}) ORDER BY id ASC""",
                    [int(i) for i in ids],
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT id, source, payload, error, created_at FROM webhook_dlq
                       ORDER BY id ASC LIMIT ? OFFSET ?""",
                    [max(1, int(limit)), max(0, int(offset))],
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_webhook_dlq(self, dlq_id: int) -> bool:
        """Remove one DLQ row after successful replay."""
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM webhook_dlq WHERE id = ?", [int(dlq_id)])
            conn.commit()
            return cur.rowcount > 0

    def last_outbound_sent_at(self) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT MAX(created_at) FROM outbound_events WHERE status = 'sent'"
            ).fetchone()
        return str(row[0]) if row and row[0] else None

    @staticmethod
    def opportunity_id_for(business_id: str) -> str:
        return f"opp:{(business_id or '').strip()}"

    def resolve_lifecycle_business_id(self, email: str) -> str:
        """Prefer stable prospect_id from prospect_state when email matches (webhook alignment)."""
        em = (email or "").strip()
        if not em:
            return ""
        with self._connect() as conn:
            row = conn.execute("""
                SELECT prospect_id FROM prospect_state
                WHERE lower(email) = lower(?)
                LIMIT 1
            """, [em]).fetchone()
        if row and row[0]:
            return str(row[0])
        return em

    def _fetch_lifecycle_rows(self, conn: sqlite3.Connection, opp_id: str) -> List[Tuple[int, str, str]]:
        rows = conn.execute("""
            SELECT id, event_type, payload FROM lifecycle_events
            WHERE opportunity_id = ?
            ORDER BY id ASC
        """, [opp_id]).fetchall()
        return [(int(r[0]), str(r[1]), str(r[2] or "")) for r in rows]

    def _get_lifecycle_snapshot(self, conn: sqlite3.Connection, opp_id: str) -> Optional[LifecycleSnapshot]:
        row = conn.execute("""
            SELECT after_event_id, outreach_state, opened_count, evidence_score,
                   COALESCE(state_engine_version, '1.0.0')
            FROM lifecycle_snapshots WHERE opportunity_id = ?
        """, [opp_id]).fetchone()
        if not row:
            return None
        ver = str(row[4])
        if ver != STATE_ENGINE_VERSION:
            return None
        return LifecycleSnapshot(
            after_event_id=int(row[0]),
            outreach_state=str(row[1]),
            opened_count=int(row[2]),
            evidence_score=float(row[3]),
            state_engine_version=ver,
        )

    def _save_lifecycle_snapshot(
        self,
        conn: sqlite3.Connection,
        opp_id: str,
        after_event_id: int,
        outreach_state: str,
        opened_count: int,
        evidence_score: float,
    ) -> None:
        ts = datetime.now().isoformat()
        conn.execute("""
            INSERT INTO lifecycle_snapshots (
                opportunity_id, after_event_id, outreach_state, opened_count, evidence_score,
                state_engine_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(opportunity_id) DO UPDATE SET
                after_event_id = excluded.after_event_id,
                outreach_state = excluded.outreach_state,
                opened_count = excluded.opened_count,
                evidence_score = excluded.evidence_score,
                state_engine_version = excluded.state_engine_version,
                updated_at = excluded.updated_at
        """, [opp_id, after_event_id, outreach_state, opened_count, evidence_score, STATE_ENGINE_VERSION, ts])

    def get_trust_score_in_conn(self, conn: sqlite3.Connection, business_id: str, half_life_days: float = 21.0) -> float:
        bid = (business_id or "").strip()
        if not bid:
            return 0.0
        rows = conn.execute(
            "SELECT trust_delta, created_at FROM trust_events WHERE business_id = ?",
            [bid],
        ).fetchall()
        if not rows:
            return 0.0
        now = datetime.now()
        score = 0.0
        for trust_delta, created_at in rows:
            try:
                event_time = datetime.fromisoformat(created_at)
            except Exception:
                event_time = now
            age_days = max((now - event_time).total_seconds() / 86400.0, 0.0)
            decay = math.exp(-math.log(2) * age_days / max(half_life_days, 0.1))
            score += float(trust_delta) * decay
        return score

    def record_lifecycle_event(
        self,
        business_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        source: str = "pipeline",
        name: str = "",
        company: str = "",
        email: str = "",
        pipeline_stage: str = "",
        status_reason: str = "",
        sync_funnel: bool = True,
        skip_validation: bool = False,
        validation_mode: str = "default",
        event_timestamp_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Append a canonical lifecycle event, replay state (snapshot-accelerated), validate
        unless skip_validation=True (tests / emergency).
        """
        bid = (business_id or "").strip()
        if not bid:
            raise ValueError("business_id required for lifecycle event")
        opp_id = self.opportunity_id_for(bid)
        now = datetime.now().isoformat()
        event_ts = (event_timestamp_iso or now).strip()
        norm = normalize_lifecycle_payload(payload)
        payload_json = json.dumps(norm)

        funnel_map = {
            LifecycleEventType.PROSPECT_LOADED: "prospect_loaded",
            LifecycleEventType.EMAIL_ENRICHED: "email_found",
            LifecycleEventType.MESSAGE_DRAFTED: "message_generated",
            LifecycleEventType.OUTREACH_SENT: "email_sent",
            LifecycleEventType.FOLLOWUP_SENT: "followup_sent",
            LifecycleEventType.DELIVERED: "delivered",
            LifecycleEventType.OPENED: "opened",
            LifecycleEventType.CLICKED: "clicked",
            LifecycleEventType.REPLIED: "replied",
            LifecycleEventType.BOUNCED: "bounced",
            LifecycleEventType.COMPLAINED: "complained",
            LifecycleEventType.UNSUBSCRIBED: "unsubscribed",
        }

        prev_stage, prev_name, prev_company, prev_email, prev_reason = ("", "", "", "", "")
        outreach_state = "COLD"
        opened_count = 0
        evidence_score = 0.0
        block_hint = ""
        trust_cached = 0.0
        eff_name = ""
        eff_company = ""
        eff_email = ""
        eff_stage = ""
        eff_reason = ""

        with self.transaction() as conn:
            prev_row = conn.execute("""
                SELECT pipeline_stage, name, company, email, status_reason
                FROM opportunities WHERE business_id = ?
            """, [bid]).fetchone()
            if prev_row:
                prev_stage = prev_row[0] or ""
                prev_name = prev_row[1] or ""
                prev_company = prev_row[2] or ""
                prev_email = prev_row[3] or ""
                prev_reason = prev_row[4] or ""

            conn.execute("""
                INSERT OR IGNORE INTO opportunities (
                    id, business_id, outreach_state, evidence_score, pipeline_stage,
                    name, company, email, status_reason, trust_score_cached,
                    state_engine_version, updated_at
                ) VALUES (?, ?, 'COLD', 0.0, '', '', '', '', '', 0.0, ?, ?)
            """, [opp_id, bid, STATE_ENGINE_VERSION, now])

            snap_before = self._get_lifecycle_snapshot(conn, opp_id)
            prev_rows = self._fetch_lifecycle_rows(conn, opp_id)
            state_before, _ = replay_outreach_state_from_rows(prev_rows, snap_before)
            prior_types = [t for _, t, _ in prev_rows]

            if not skip_validation:
                validate_lifecycle_event(
                    event_type,
                    norm,
                    current_outreach_state=state_before,
                    prior_event_types=prior_types,
                    created_at_iso=event_ts,
                    engagement_requires_send=(validation_mode != "webhook"),
                )

            conn.execute("""
                INSERT INTO lifecycle_events (opportunity_id, event_type, payload, source, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, [opp_id, event_type, payload_json, source, event_ts])
            all_rows = self._fetch_lifecycle_rows(conn, opp_id)
            snap = self._get_lifecycle_snapshot(conn, opp_id)
            outreach_state, opened_count = replay_outreach_state_from_rows(all_rows, snap)
            evidence_score = extract_evidence_score_from_rows(all_rows, snap)
            block_hint = last_block_reason([(t, p) for _, t, p in all_rows])

            if all_rows and len(all_rows) % LIFECYCLE_SNAPSHOT_INTERVAL == 0:
                last_id = all_rows[-1][0]
                self._save_lifecycle_snapshot(
                    conn,
                    opp_id,
                    last_id,
                    outreach_state,
                    opened_count,
                    evidence_score,
                )

            trust_cached = self.get_trust_score_in_conn(conn, bid)
            eff_name = name or prev_name
            eff_company = company or prev_company
            eff_email = email or prev_email
            eff_stage = pipeline_stage or prev_stage
            eff_reason = status_reason or block_hint or prev_reason

            conn.execute("""
                INSERT INTO opportunities (
                    id, business_id, outreach_state, evidence_score, pipeline_stage,
                    name, company, email, status_reason, trust_score_cached,
                    state_engine_version, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    outreach_state = excluded.outreach_state,
                    evidence_score = excluded.evidence_score,
                    pipeline_stage = excluded.pipeline_stage,
                    name = excluded.name,
                    company = excluded.company,
                    email = excluded.email,
                    status_reason = excluded.status_reason,
                    trust_score_cached = excluded.trust_score_cached,
                    state_engine_version = excluded.state_engine_version,
                    updated_at = excluded.updated_at
            """, [
                opp_id,
                bid,
                outreach_state,
                evidence_score,
                eff_stage,
                eff_name,
                eff_company,
                eff_email,
                eff_reason,
                trust_cached,
                STATE_ENGINE_VERSION,
                now,
            ])

            conn.execute("""
                INSERT INTO prospect_state (prospect_id, name, company, email, stage, status_reason, trust_score, outreach_state, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prospect_id) DO UPDATE SET
                    name = excluded.name,
                    company = excluded.company,
                    email = excluded.email,
                    stage = excluded.stage,
                    status_reason = excluded.status_reason,
                    trust_score = excluded.trust_score,
                    outreach_state = excluded.outreach_state,
                    updated_at = excluded.updated_at
            """, [
                bid,
                eff_name,
                eff_company,
                eff_email,
                eff_stage or "lifecycle",
                eff_reason,
                trust_cached,
                outreach_state,
                now,
            ])

            if sync_funnel and event_type in funnel_map:
                conn.execute("""
                    INSERT INTO funnel_events (prospect_id, stage, metadata, created_at)
                    VALUES (?, ?, ?, ?)
                """, [
                    bid,
                    funnel_map[event_type],
                    json.dumps({"source": source, **norm}),
                    now,
                ])

            if event_type == LifecycleEventType.REPLIED:
                conn.execute("""
                    UPDATE reply_intent_training_data
                    SET actual_outcome = 'replied', resolved_at = ?
                    WHERE id = (
                        SELECT id FROM reply_intent_training_data
                        WHERE business_id = ? AND actual_outcome = 'pending'
                        ORDER BY id DESC LIMIT 1
                    )
                """, [now, bid])

        return {
            "opportunity_id": opp_id,
            "business_id": bid,
            "outreach_state": outreach_state,
            "evidence_score": evidence_score,
            "pipeline_stage": eff_stage,
            "trust_score_cached": trust_cached,
            "state_engine_version": STATE_ENGINE_VERSION,
        }

    def get_lifecycle_events(self, business_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        opp_id = self.opportunity_id_for(business_id)
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT id, event_type, payload, source, created_at
                FROM lifecycle_events
                WHERE opportunity_id = ?
                ORDER BY id ASC
                LIMIT ?
            """, [opp_id, limit]).fetchall()
        out: List[Dict[str, Any]] = []
        for row in rows:
            out.append({
                "id": row["id"],
                "event_type": row["event_type"],
                "payload": _parse_json_dict(row["payload"]),
                "source": row["source"],
                "created_at": row["created_at"],
            })
        return out

    def get_opportunity(self, business_id: str) -> Optional[Dict[str, Any]]:
        bid = (business_id or "").strip()
        if not bid:
            return None
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT * FROM opportunities WHERE business_id = ?
            """, [bid]).fetchone()
        if not row:
            return None
        sev = row["state_engine_version"] if "state_engine_version" in row.keys() else "1.0.0"
        return {
            "id": row["id"],
            "business_id": row["business_id"],
            "state": row["outreach_state"],
            "outreach_state": row["outreach_state"],
            "evidence_score": row["evidence_score"],
            "pipeline_stage": row["pipeline_stage"],
            "trust_score": row["trust_score_cached"],
            "state_engine_version": sev,
            "name": row["name"],
            "company": row["company"],
            "email": row["email"],
            "status_reason": row["status_reason"],
            "updated_at": row["updated_at"],
            "lifecycle_events": self.get_lifecycle_events(bid),
        }

    def replay_opportunity_from_db(self, business_id: str) -> Dict[str, Any]:
        """
        Recompute outreach_state from stored events and persist (for migrations / audits).
        """
        bid = (business_id or "").strip()
        if not bid:
            return {}
        opp_id = self.opportunity_id_for(bid)
        with self._connect() as conn:
            rows = self._fetch_lifecycle_rows(conn, opp_id)
            snap = self._get_lifecycle_snapshot(conn, opp_id)
        outreach_state, _ = replay_outreach_state_from_rows(rows, snap)
        evidence_score = extract_evidence_score_from_rows(rows, snap)
        trust_cached = self.get_trust_score(bid)
        now = datetime.now().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT name, company, email, status_reason, pipeline_stage FROM opportunities WHERE business_id = ?",
                [bid],
            ).fetchone()
            if row:
                name, company, email, status_reason, pipeline_stage = row[0], row[1], row[2], row[3], row[4]
            else:
                name, company, email, status_reason, pipeline_stage = "", "", "", "", ""
            conn.execute("""
                UPDATE opportunities SET
                    outreach_state = ?,
                    evidence_score = ?,
                    trust_score_cached = ?,
                    updated_at = ?
                WHERE business_id = ?
            """, [outreach_state, evidence_score, trust_cached, now, bid])
            conn.commit()
        self.upsert_prospect_state(
            prospect_id=bid,
            stage=pipeline_stage or "replay",
            name=name or "",
            company=company or "",
            email=email or "",
            status_reason=status_reason or "",
            trust_score=trust_cached,
            outreach_state=outreach_state,
        )
        return {
            "business_id": bid,
            "outreach_state": outreach_state,
            "evidence_score": evidence_score,
            "trust_score_cached": trust_cached,
        }

    @staticmethod
    def message_hash(subject: str, html_body: str) -> str:
        payload = f"{subject.strip()}::{html_body.strip()}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def is_suppressed(self, email: str) -> bool:
        if not email:
            return True
        with self._connect() as conn:
            row = conn.execute(
                "SELECT email FROM suppression_list WHERE lower(email) = lower(?)",
                [email.strip()]
            ).fetchone()
        return row is not None

    def suppress_email(
        self,
        email: str,
        reason: str,
        source: str = "manual",
        *,
        operator: str = "",
        notes: str = "",
    ) -> None:
        if not email:
            return
        em = (email or "").strip().lower()
        r = (reason or "").strip().lower() or "manual"
        if r not in SUPPRESSION_REASONS_ALLOWED:
            r = "manual"
        s = (source or "").strip().lower() or "operator"
        if s not in SUPPRESSION_SOURCES_ALLOWED:
            s = "operator"
        ts = datetime.now().isoformat()
        op = (operator or "").strip()
        note = (notes or "").strip()
        with self.transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO suppression_list (email, reason, source, created_at)
                VALUES (?, ?, ?, ?)
                """,
                [em, r, s, ts],
            )
            conn.execute(
                """
                INSERT INTO suppression_history (email, reason, source, operator, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [em, r, s, op, note, ts],
            )

    def gate_outbound_send(
        self,
        prospect_id: str,
        campaign_key: str,
        recipient_email: str,
        *,
        send_type: str = "initial",
        cooldown_days: int = 0,
        policy_block_reason: Optional[str] = None,
    ) -> tuple[bool, str]:
        """
        Central send gate: suppression, one sent row per (prospect_id, campaign_key, send_type),
        and optional compliance cooldown when there has been no reply since the last non-transactional send.
        """
        if policy_block_reason:
            return False, policy_block_reason
        em = (recipient_email or "").strip()
        if self.is_suppressed(em):
            return False, "recipient is in suppression list"
        st = (send_type or "initial").strip().lower()

        pid = prospect_id or em
        ck = campaign_key or "outreach_initial"

        with self._connect() as conn:
            row = conn.execute("""
                SELECT 1 FROM outbound_events
                WHERE prospect_id = ? AND campaign_key = ? AND send_type = ? AND status = 'sent'
                LIMIT 1
            """, [pid, ck, st]).fetchone()
            if row:
                return False, f"duplicate_{st}_send_for_campaign"

            cd = int(cooldown_days or 0)
            if cd > 0 and st in ("initial", "followup", "manual"):
                last_row = conn.execute("""
                    SELECT MAX(created_at) FROM outbound_events
                    WHERE status = 'sent' AND send_type != 'transactional'
                      AND (prospect_id = ? OR lower(recipient_email) = lower(?))
                """, [pid, em]).fetchone()
                last_iso = last_row[0] if last_row and last_row[0] else None
                if last_iso:
                    rep = conn.execute("""
                        SELECT 1 FROM funnel_events
                        WHERE prospect_id = ? AND stage = 'replied' AND created_at > ?
                        LIMIT 1
                    """, [pid, last_iso]).fetchone()
                    if not rep:
                        try:
                            last_t = datetime.fromisoformat(str(last_iso))
                            days = (datetime.now() - last_t).total_seconds() / 86400.0
                        except Exception:
                            days = 999.0
                        if days < float(cd):
                            return False, f"compliance_cooldown:{cd}d_no_reply_since_last_send"

        return True, ""

    def can_send_outbound(self, prospect_id: str, campaign_key: str, recipient_email: str, subject: str, html_body: str) -> tuple[bool, str]:
        """Backward-compatible wrapper (ignores subject/html for gating; cooldown not applied)."""
        _ = self.message_hash(subject, html_body)
        return self.gate_outbound_send(
            prospect_id, campaign_key, recipient_email, send_type="initial", cooldown_days=0
        )

    def record_outbound(
        self,
        prospect_id: str,
        campaign_key: str,
        recipient_email: str,
        subject: str,
        html_body: str,
        status: str,
        provider_id: str = "",
        send_type: str = "initial",
    ) -> None:
        message_hash = self.message_hash(subject, html_body)
        ts = datetime.now().isoformat()
        st = (send_type or "initial").strip().lower()
        out_st = (status or "").strip().lower()
        if out_st not in OUTBOUND_EVENT_STATUSES_ALLOWED:
            raise ValueError(f"invalid outbound_events.status: {status!r}")
        with self._connect() as conn:
            # UPSERT: one row per (prospect_id, campaign_key, send_type); dry_run can become sent.
            conn.execute("""
                INSERT INTO outbound_events
                (prospect_id, campaign_key, recipient_email, message_hash, status, provider_id, created_at, send_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prospect_id, campaign_key, send_type) DO UPDATE SET
                    recipient_email=excluded.recipient_email,
                    message_hash=excluded.message_hash,
                    status=excluded.status,
                    provider_id=excluded.provider_id,
                    created_at=excluded.created_at
            """, [
                prospect_id,
                campaign_key,
                recipient_email,
                message_hash,
                out_st,
                provider_id,
                ts,
                st,
            ])
            conn.commit()

    def list_followup_eligible_rows(self, min_days_since_initial: int) -> List[Dict[str, Any]]:
        """
        Follow-up candidates from SQLite only (CSV is not authoritative).
        Requires initial outbound_events row with send_type=initial, sent, older than threshold,
        no followup sent for same campaign, no replied funnel event after initial send.
        """
        cutoff = (datetime.now() - timedelta(days=max(0, int(min_days_since_initial)))).isoformat()
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT o.prospect_id, o.recipient_email, o.campaign_key, o.created_at AS initial_sent_at,
                       COALESCE(ps.name, '') AS name, COALESCE(ps.company, '') AS company
                FROM outbound_events o
                LEFT JOIN prospect_state ps ON ps.prospect_id = o.prospect_id
                WHERE o.send_type IN ('initial', 'initial_prospect')
                  AND o.status = 'sent'
                  AND o.created_at < ?
                  AND NOT EXISTS (
                      SELECT 1 FROM outbound_events f
                      WHERE f.prospect_id = o.prospect_id AND f.campaign_key = o.campaign_key
                        AND f.send_type = 'followup' AND f.status = 'sent'
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM funnel_events fe
                      WHERE fe.prospect_id = o.prospect_id AND fe.stage = 'replied'
                        AND datetime(fe.created_at) > datetime(o.created_at)
                  )
            """, [cutoff]).fetchall()
        return [dict(r) for r in rows]

    def count_outbound_since(self, since_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM outbound_events WHERE created_at >= ?",
                [since_iso],
            ).fetchone()
        return int(row[0] if row else 0)

    def record_funnel_event(self, prospect_id: str, stage: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO funnel_events (prospect_id, stage, metadata, created_at)
                VALUES (?, ?, ?, ?)
            """, [
                prospect_id,
                stage,
                json.dumps(metadata or {}),
                datetime.now().isoformat(),
            ])
            conn.commit()

    def get_funnel_counts(self, days: int = 7) -> Dict[str, int]:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT stage, COUNT(*) AS c
                FROM funnel_events
                WHERE created_at >= ?
                GROUP BY stage
            """, [cutoff]).fetchall()
        return {str(stage): int(count) for stage, count in rows}

    def get_funnel_counts_since_hours(self, hours: int) -> Dict[str, int]:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT stage, COUNT(*) AS c
                FROM funnel_events
                WHERE created_at >= ?
                GROUP BY stage
            """, [cutoff]).fetchall()
        return {str(stage): int(count) for stage, count in rows}

    def upsert_prospect_state(
        self,
        prospect_id: str,
        stage: str,
        name: str = "",
        company: str = "",
        email: str = "",
        status_reason: str = "",
        trust_score: Optional[float] = None,
        outreach_state: Optional[str] = None,
    ) -> None:
        score_value = trust_score if trust_score is not None else self.get_trust_score(prospect_id)
        now = datetime.now().isoformat()
        with self._connect() as conn:
            if outreach_state is None:
                row = conn.execute(
                    "SELECT outreach_state FROM prospect_state WHERE prospect_id = ?",
                    [prospect_id],
                ).fetchone()
                outreach_state = str(row[0]) if row and row[0] else "COLD"
            conn.execute("""
                INSERT INTO prospect_state (prospect_id, name, company, email, stage, status_reason, trust_score, outreach_state, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(prospect_id) DO UPDATE SET
                    name = excluded.name,
                    company = excluded.company,
                    email = excluded.email,
                    stage = excluded.stage,
                    status_reason = excluded.status_reason,
                    trust_score = excluded.trust_score,
                    outreach_state = excluded.outreach_state,
                    updated_at = excluded.updated_at
            """, [
                prospect_id,
                name,
                company,
                email,
                stage,
                status_reason,
                score_value,
                outreach_state,
                now,
            ])
            conn.commit()

    def get_blocked_prospects(self, limit: int = 25) -> List[Dict[str, str]]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT prospect_id, name, company, email, stage, status_reason, trust_score, outreach_state, updated_at
                FROM prospect_state
                WHERE stage LIKE 'blocked_%'
                ORDER BY updated_at DESC
                LIMIT ?
            """, [limit]).fetchall()
        return [dict(row) for row in rows]

    def log_decision(self, entity_type: str, entity_id: str, decision: str, reasons: List[str]) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO decision_logs (entity_type, entity_id, decision, reasons, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, [
                entity_type,
                entity_id,
                decision,
                json.dumps(reasons),
                datetime.now().isoformat(),
            ])
            conn.commit()

    def log_block(
        self,
        entity_type: str,
        entity_id: str,
        reason: str,
        details: str = "",
        block_type: str = "GENERAL_BLOCK",
        severity: Optional[str] = None,
    ) -> None:
        sev = (severity or BLOCK_SEVERITY_DEFAULTS.get(block_type, "SOFT")).upper()
        if sev not in ("HARD", "SOFT", "INFO"):
            sev = "SOFT"
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO block_logs (entity_type, entity_id, block_type, severity, reason, details, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                entity_type,
                entity_id,
                block_type,
                sev,
                reason,
                details,
                ts,
            ])
            conn.commit()
        if sev == "HARD":
            self.set_outreach_freeze(True, reason=f"hard_block:{block_type}:{reason}")

    def record_reply_intent_training(
        self,
        business_id: str,
        *,
        campaign_key: str,
        message_hash: str,
        features: Dict[str, Any],
        predicted_prob: float,
        actual_outcome: str = "pending",
    ) -> int:
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute("""
                INSERT INTO reply_intent_training_data (
                    business_id, campaign_key, message_hash, features_json, predicted_prob,
                    actual_outcome, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (business_id or "").strip(),
                campaign_key,
                message_hash,
                json.dumps(features),
                float(predicted_prob),
                actual_outcome,
                ts,
                ts if actual_outcome in {"replied", "no_reply", "not_sent"} else "",
            ])
            conn.commit()
            return int(cur.lastrowid)

    def resolve_reply_intent_on_replied(self, business_id: str) -> None:
        bid = (business_id or "").strip()
        if not bid:
            return
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                UPDATE reply_intent_training_data
                SET actual_outcome = 'replied', resolved_at = ?
                WHERE id = (
                    SELECT id FROM reply_intent_training_data
                    WHERE business_id = ? AND actual_outcome = 'pending'
                    ORDER BY id DESC LIMIT 1
                )
            """, [ts, bid])
            conn.commit()

    def settle_reply_intent_stale_pending(self, older_than_days: float = 10.0) -> int:
        cutoff = (datetime.now() - timedelta(days=older_than_days)).isoformat()
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute("""
                UPDATE reply_intent_training_data
                SET actual_outcome = 'no_reply', resolved_at = ?
                WHERE actual_outcome = 'pending' AND created_at < ?
            """, [ts, cutoff])
            conn.commit()
            return int(cur.rowcount or 0)

    def count_weekly_outbound_sends(self, days: int = 7) -> int:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        return self.count_outbound_since(cutoff)

    def try_register_resend_webhook_event(
        self,
        event_id: str,
        event_type: str,
        email: str,
        payload: str,
    ) -> bool:
        """
        Insert webhook event_id exactly once.
        Returns True if this is the first time (caller should apply side effects),
        False if duplicate (idempotent no-op).
        """
        eid = (event_id or "").strip()
        if not eid:
            return True
        ts = datetime.now().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO resend_webhook_events (event_id, event_type, email, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [eid, (event_type or "").strip().lower(), (email or "").strip().lower(), payload or "{}", ts],
            )
            conn.commit()
            return bool(cur.rowcount and cur.rowcount > 0)

    def get_delivery_ratio_metrics(self, days: int = 7) -> Dict[str, Any]:
        """Rolling-window delivery health for auto-pause / send-time gates."""
        cutoff = (datetime.now() - timedelta(days=max(1, int(days)))).isoformat()
        with self._connect() as conn:
            row_sent = conn.execute(
                """
                SELECT COUNT(*) FROM outbound_events
                WHERE status = 'sent' AND created_at >= ?
                """,
                [cutoff],
            ).fetchone()
            sent = int(row_sent[0] if row_sent else 0)
            row_b = conn.execute(
                """
                SELECT COUNT(*) FROM resend_webhook_events
                WHERE event_type IN ('email.bounced', 'email.hard_bounced', 'email.bounce')
                  AND created_at >= ?
                """,
                [cutoff],
            ).fetchone()
            bounced = int(row_b[0] if row_b else 0)
            row_c = conn.execute(
                """
                SELECT COUNT(*) FROM resend_webhook_events
                WHERE event_type IN ('email.complained', 'email.complaint')
                  AND created_at >= ?
                """,
                [cutoff],
            ).fetchone()
            complained = int(row_c[0] if row_c else 0)
        denom = max(sent, 1)
        return {
            "window_days": int(days),
            "sent": sent,
            "bounced_events": bounced,
            "complained_events": complained,
            "bounce_ratio": float(bounced) / float(denom),
            "complaint_ratio": float(complained) / float(denom),
        }

    def save_funnel_health_snapshot(
        self,
        *,
        dry_run: bool,
        generated: int,
        qualified: int,
        sent: int,
        blocked: int,
        reply_rate_estimate: float,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        run_at = datetime.now().isoformat()
        payload = dict(extra or {})
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO funnel_health_snapshots (
                    run_at, dry_run, generated, qualified, sent, blocked, reply_rate_estimate, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                run_at,
                1 if dry_run else 0,
                generated,
                qualified,
                sent,
                blocked,
                float(reply_rate_estimate),
                json.dumps(payload),
            ])
            conn.commit()

    def record_trust_event(
        self,
        business_id: str,
        event_type: str,
        trust_delta: float,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> float:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO trust_events (business_id, event_type, trust_delta, metadata, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, [
                business_id,
                event_type,
                trust_delta,
                json.dumps(metadata or {}),
                datetime.now().isoformat(),
            ])
            conn.commit()
        return self.get_trust_score(business_id)

    def get_trust_score(self, business_id: str, half_life_days: float = 21.0) -> float:
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT trust_delta, created_at FROM trust_events WHERE business_id = ?
            """, [business_id]).fetchall()
        if not rows:
            return 0.0
        now = datetime.now()
        score = 0.0
        for trust_delta, created_at in rows:
            try:
                event_time = datetime.fromisoformat(created_at)
            except Exception:
                event_time = now
            age_days = max((now - event_time).total_seconds() / 86400.0, 0.0)
            decay = math.exp(-math.log(2) * age_days / max(half_life_days, 0.1))
            score += float(trust_delta) * decay
        return score

    def upsert_client_account(self, business_id: str, name: str, status: str = "active") -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO client_accounts (business_id, name, status, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(business_id) DO UPDATE SET
                    name = excluded.name,
                    status = excluded.status,
                    updated_at = excluded.updated_at
            """, [business_id, name, status, datetime.now().isoformat()])
            conn.commit()

    def count_active_clients(self) -> int:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT COUNT(*) FROM client_accounts WHERE status = 'active'
            """).fetchone()
        return int(row[0] if row else 0)

    def set_outreach_freeze(self, frozen: bool, reason: str = "") -> None:
        value = "true" if frozen else "false"
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO system_control (control_key, control_value, updated_at)
                VALUES ('outreach_frozen', ?, ?)
                ON CONFLICT(control_key) DO UPDATE SET
                    control_value = excluded.control_value,
                    updated_at = excluded.updated_at
            """, [value, datetime.now().isoformat()])
            conn.commit()
        self.log_decision(
            "system_control",
            "outreach_frozen",
            "freeze_enabled" if frozen else "freeze_disabled",
            [reason or "manual_or_automatic"],
        )

    def is_outreach_frozen(self) -> bool:
        with self._connect() as conn:
            row = conn.execute("""
                SELECT control_value FROM system_control WHERE control_key = 'outreach_frozen'
            """).fetchone()
        if not row:
            return False
        return str(row[0]).lower() == "true"
    
    def add_job(
        self,
        job_id: str,
        action: JobAction,
        prospect_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 3,
    ) -> Job:
        """
        Queue a new job.
        
        Args:
            job_id: Unique job ID (e.g., f"{prospect_id}_{action.value}_{timestamp}")
            action: What work to do
            prospect_id: Associated prospect (optional)
            context: Serialized arguments (email, company, etc.)
            max_retries: Max retry attempts
        
        Returns:
            Job object
        """
        job = Job(
            id=job_id,
            prospect_id=prospect_id,
            action=action,
            context=context or {},
            max_retries=max_retries,
        )
        
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO jobs (id, prospect_id, action, status, context, retry_count, max_retries, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                job.id,
                job.prospect_id,
                job.action.value,
                job.status.value,
                json.dumps(job.context),
                job.retry_count,
                job.max_retries,
                job.created_at.isoformat(),
            ))
            conn.commit()
        
        logger.info(f"Queued job {job_id}: {action.value} for prospect {prospect_id}")
        return job
    
    def get_pending_jobs(self, limit: Optional[int] = None) -> List[Job]:
        """
        Get all pending jobs ready to run.
        
        Args:
            limit: Max jobs to return (default: all)
        
        Returns:
            List of Job objects
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM jobs WHERE status = ? ORDER BY created_at ASC"
            args = [JobStatus.PENDING.value]
            
            if limit:
                query += " LIMIT ?"
                args.append(limit)
            
            rows = conn.execute(query, args).fetchall()
        
        return [self._row_to_job(row) for row in rows]
    
    def get_failed_jobs(self) -> List[Job]:
        """
        Get jobs that failed but haven't exceeded retry limit.
        Ready for next attempt.
        
        Returns:
            List of Job objects eligible for retry
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM jobs
                WHERE status = ? AND retry_count < max_retries
                ORDER BY retry_count DESC, created_at ASC
            """, [JobStatus.FAILED.value]).fetchall()
        
        return [self._row_to_job(row) for row in rows]
    
    def get_job(self, job_id: str) -> Optional[Job]:
        """Get a single job by ID."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", [job_id]).fetchone()
        
        return self._row_to_job(row) if row else None
    
    def start_job(self, job_id: str) -> None:
        """Mark a job as in-progress."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE jobs SET status = ?, started_at = ?
                WHERE id = ?
            """, [JobStatus.IN_PROGRESS.value, datetime.now().isoformat(), job_id])
            conn.commit()
        
        logger.debug(f"Started job {job_id}")
    
    def complete_job(self, job_id: str, result: str = "") -> None:
        """Mark a job as completed successfully."""
        with self._connect() as conn:
            conn.execute("""
                UPDATE jobs SET status = ?, result = ?, completed_at = ?
                WHERE id = ?
            """, [JobStatus.COMPLETED.value, result, datetime.now().isoformat(), job_id])
            conn.commit()
        
        logger.info(f"Completed job {job_id}")
    
    def fail_job(self, job_id: str, error: str = "", retry: bool = True) -> None:
        """
        Mark a job as failed.
        
        Args:
            job_id: Job ID
            error: Error message
            retry: If True and retry_count < max_retries, status = FAILED (will retry)
                   If False or max retries exceeded, status = ABANDONED
        """
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return
        
        new_status = JobStatus.ABANDONED
        new_retry_count = job.retry_count + 1
        
        if retry and new_retry_count < job.max_retries:
            new_status = JobStatus.FAILED
        
        with self._connect() as conn:
            conn.execute("""
                UPDATE jobs SET status = ?, error = ?, retry_count = ?, completed_at = ?
                WHERE id = ?
            """, [new_status.value, error, new_retry_count, datetime.now().isoformat(), job_id])
            conn.commit()
        
        level = logging.WARNING if new_status == JobStatus.FAILED else logging.ERROR
        logger.log(level, f"Failed job {job_id} (attempt {new_retry_count}/{job.max_retries}): {error}")
    
    def get_jobs_for_prospect(self, prospect_id: str) -> List[Job]:
        """Get all jobs (completed, failed, pending) for a prospect."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM jobs WHERE prospect_id = ? ORDER BY created_at ASC",
                [prospect_id]
            ).fetchall()
        
        return [self._row_to_job(row) for row in rows]
    
    def get_summary(self) -> Dict[str, int]:
        """Get job queue statistics."""
        with self._connect() as conn:
            summary = {}
            for status in JobStatus:
                count = conn.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status = ?",
                    [status.value]
                ).fetchone()[0]
                summary[status.value] = count
        
        return summary
    
    def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Delete completed/abandoned jobs older than N days.
        Keep failed jobs (pending retry).
        
        Args:
            days: Age threshold
        
        Returns:
            Number of rows deleted
        """
        cutoff = datetime.now() - timedelta(days=days)
        with self._connect() as conn:
            cursor = conn.execute("""
                DELETE FROM jobs
                WHERE (status = ? OR status = ?)
                AND completed_at < ?
            """, [JobStatus.COMPLETED.value, JobStatus.ABANDONED.value, cutoff.isoformat()])
            conn.commit()
            deleted = cursor.rowcount
        
        logger.info(f"Cleaned up {deleted} old jobs (older than {days} days)")
        return deleted
    
    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> Job:
        """Convert sqlite3.Row to Job dataclass."""
        return Job(
            id=row["id"],
            prospect_id=row["prospect_id"],
            action=JobAction(row["action"]),
            status=JobStatus(row["status"]),
            context=json.loads(row["context"] or "{}"),
            result=row["result"],
            error=row["error"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            created_at=datetime.fromisoformat(row["created_at"]),
            started_at=datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
        )


# Global queue instance
_queue: Optional[JobQueue] = None


def get_queue(db_path: str = "venture_jobs.db") -> JobQueue:
    """Get or create global job queue."""
    global _queue
    if _queue is None:
        _queue = JobQueue(db_path)
    return _queue
