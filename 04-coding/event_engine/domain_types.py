"""
domain_types.py — All canonical domain types for the execution state machine.

Rules:
- All types are frozen dataclasses (INV-7: immutable post-normalization)
- No untyped dict / None returns at boundaries (INV-3)
- Zero import-time side effects (INV-1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Core domain records (§3 of runtime_contract.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProspectRecord:
    """A validated prospect ready for outbound consideration."""

    company_name: str
    domain: str
    name: str
    email: str
    role: str
    industry: str
    validation_status: str
    run_id: str


@dataclass(frozen=True)
class BatchConfig:
    """Configuration envelope for a single outbound batch execution."""

    run_id: str
    session_id: str
    dry_run: bool
    prospect_limit: int
    scenario: str  # "live" | "clean_run" | "governance_escalation" | "retry_failure"


@dataclass(frozen=True)
class BatchResult:
    """Result of a completed outbound batch (INV-3: typed, never dict/None)."""

    run_id: str
    session_id: str
    attempted: int
    sent: int
    blocked: int
    events: tuple[Any, ...]  # tuple for immutability
    reasons: tuple[str, ...]

    @classmethod
    def empty(cls, run_id: str, session_id: str) -> "BatchResult":
        return cls(
            run_id=run_id,
            session_id=session_id,
            attempted=0,
            sent=0,
            blocked=0,
            events=(),
            reasons=(),
        )


@dataclass(frozen=True)
class GovernanceEvent:
    """A governance decision event (HARD blocks go to awaiting_approval)."""

    event_id: str
    session_id: str
    severity: str  # INFO | SOFT | HARD
    description: str
    timestamp: str


@dataclass(frozen=True)
class FailureEvent:
    """A job failure event with retry tracking."""

    event_id: str
    session_id: str
    job_id: str
    reason: str
    retry_count: int
    timestamp: str


@dataclass(frozen=True)
class ComplianceResult:
    """Result of a compliance cooldown evaluation."""

    allowed: bool
    reason: str
    cooldown_days: int


@dataclass(frozen=True)
class RuntimeGovernanceModel:
    """Built governance configuration for a run."""

    run_id: str
    session_id: str
    hard_block_threshold: int
    soft_block_threshold: int
    max_retries: int


# ---------------------------------------------------------------------------
# Normalized Event — the single type flowing through the pipeline (INV-2/7)
# ---------------------------------------------------------------------------

# Valid event types
EVENT_TYPE_STATE_CHANGE = "state_change"
EVENT_TYPE_SEND_ATTEMPT = "send_attempt"
EVENT_TYPE_SEND_BLOCKED = "send_blocked"
EVENT_TYPE_GOVERNANCE = "governance"
EVENT_TYPE_RETRY = "retry"
EVENT_TYPE_FAILURE = "failure"
EVENT_TYPE_BATCH_START = "batch_start"
EVENT_TYPE_BATCH_COMPLETE = "batch_complete"
EVENT_TYPE_APPROVAL_REQUESTED = "approval_requested"
EVENT_TYPE_APPROVED = "approved"
EVENT_TYPE_REJECTED = "rejected"

VALID_EVENT_TYPES = frozenset(
    {
        EVENT_TYPE_STATE_CHANGE,
        EVENT_TYPE_SEND_ATTEMPT,
        EVENT_TYPE_SEND_BLOCKED,
        EVENT_TYPE_GOVERNANCE,
        EVENT_TYPE_RETRY,
        EVENT_TYPE_FAILURE,
        EVENT_TYPE_BATCH_START,
        EVENT_TYPE_BATCH_COMPLETE,
        EVENT_TYPE_APPROVAL_REQUESTED,
        EVENT_TYPE_APPROVED,
        EVENT_TYPE_REJECTED,
    }
)

# Valid severities
SEVERITY_INFO = "INFO"
SEVERITY_SOFT = "SOFT"
SEVERITY_HARD = "HARD"

VALID_SEVERITIES = frozenset({SEVERITY_INFO, SEVERITY_SOFT, SEVERITY_HARD})


@dataclass(frozen=True)
class NormalizedEvent:
    """
    The single event type flowing through the entire pipeline post-normalization.

    Invariants:
    - Immutable (frozen=True) — INV-7
    - No is_demo / source fields — INV-7
    - sequence is monotonically increasing within a session
    - metadata uses typed dict[str, object] — not untyped dict — INV-3
    """

    event_id: str
    session_id: str
    run_id: str
    event_type: str  # one of VALID_EVENT_TYPES
    severity: str  # one of VALID_SEVERITIES
    timestamp: str  # ISO-8601 UTC
    sequence: int  # monotonic within session, 1-based
    description: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        """Serialize to wire format (for JSON/WS)."""
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "run_id": self.run_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
            "description": self.description,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Session state model (§5 of runtime_contract.md)
# ---------------------------------------------------------------------------

SESSION_STATE_PENDING = "pending"
SESSION_STATE_RUNNING = "running"
SESSION_STATE_PAUSED = "paused"
SESSION_STATE_AWAITING_APPROVAL = "awaiting_approval"
SESSION_STATE_FAILED = "failed"
SESSION_STATE_COMPLETED = "completed"

TERMINAL_STATES = frozenset({SESSION_STATE_FAILED, SESSION_STATE_COMPLETED})

VALID_STATES = frozenset(
    {
        SESSION_STATE_PENDING,
        SESSION_STATE_RUNNING,
        SESSION_STATE_PAUSED,
        SESSION_STATE_AWAITING_APPROVAL,
        SESSION_STATE_FAILED,
        SESSION_STATE_COMPLETED,
    }
)

# (from_state, to_state) → command that triggers it
VALID_TRANSITIONS: dict[tuple[str, str], str] = {
    (SESSION_STATE_PENDING, SESSION_STATE_RUNNING): "start",
    (SESSION_STATE_RUNNING, SESSION_STATE_PAUSED): "pause",
    (SESSION_STATE_RUNNING, SESSION_STATE_AWAITING_APPROVAL): "governance_hard",
    (SESSION_STATE_RUNNING, SESSION_STATE_FAILED): "fail",
    (SESSION_STATE_RUNNING, SESSION_STATE_COMPLETED): "complete",
    (SESSION_STATE_PAUSED, SESSION_STATE_RUNNING): "resume",
    (SESSION_STATE_AWAITING_APPROVAL, SESSION_STATE_RUNNING): "approve",
    (SESSION_STATE_AWAITING_APPROVAL, SESSION_STATE_FAILED): "reject",
}


@dataclass(frozen=True)
class SessionState:
    """Immutable snapshot of a session's current state."""

    session_id: str
    run_id: str
    state: str
    created_at: str  # ISO-8601 UTC
    updated_at: str  # ISO-8601 UTC
    scenario: str
    event_count: int

    def is_terminal(self) -> bool:
        return self.state in TERMINAL_STATES
