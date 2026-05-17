"""
demo_event_generator.py — Deterministic demo event sequences (§6 of runtime_contract.md).

Rules:
- Feeds the REAL normalizer — no separate demo pipeline (single pipeline rule §4)
- Deterministic: same scenario_key always produces identical event sequences
- Three scenarios: clean_run, governance_escalation, retry_failure
- No is_demo / source fields — post-normalization events are indistinguishable
- Zero import-time side effects (INV-1)
"""

from __future__ import annotations

from datetime import datetime, timezone

from domain_types import (
    EVENT_TYPE_APPROVAL_REQUESTED,
    EVENT_TYPE_APPROVED,
    EVENT_TYPE_BATCH_COMPLETE,
    EVENT_TYPE_BATCH_START,
    EVENT_TYPE_FAILURE,
    EVENT_TYPE_GOVERNANCE,
    EVENT_TYPE_REJECTED,
    EVENT_TYPE_RETRY,
    EVENT_TYPE_SEND_ATTEMPT,
    EVENT_TYPE_SEND_BLOCKED,
    EVENT_TYPE_STATE_CHANGE,
    SEVERITY_HARD,
    SEVERITY_INFO,
    SEVERITY_SOFT,
    NormalizedEvent,
)
from event_normalizer import normalize

# Deterministic base timestamp for reproducibility
_BASE_TIMESTAMP = "2026-05-17T09:00:00.000000Z"

# Registered scenario keys
SCENARIO_CLEAN_RUN = "clean_run"
SCENARIO_GOVERNANCE_ESCALATION = "governance_escalation"
SCENARIO_RETRY_FAILURE = "retry_failure"

VALID_SCENARIOS = frozenset(
    {SCENARIO_CLEAN_RUN, SCENARIO_GOVERNANCE_ESCALATION, SCENARIO_RETRY_FAILURE}
)


def _ts(offset_seconds: int) -> str:
    """Deterministic timestamp: base + offset_seconds."""
    base = datetime.fromisoformat(_BASE_TIMESTAMP.replace("Z", "+00:00"))
    from datetime import timedelta

    result = base + timedelta(seconds=offset_seconds)
    return result.isoformat().replace("+00:00", "Z")


class UnknownScenarioError(KeyError):
    def __init__(self, key: str) -> None:
        super().__init__(f"Unknown scenario: {key!r}. Valid: {sorted(VALID_SCENARIOS)}")


def generate_scenario(scenario_key: str) -> list[NormalizedEvent]:
    """
    Generate a deterministic event sequence for the given scenario.

    These events feed the REAL normalizer (single pipeline rule §4).
    The output is identical for the same scenario_key — guaranteed deterministic.

    Args:
        scenario_key: One of SCENARIO_* constants.

    Returns:
        Ordered list of NormalizedEvent (immutable, sequence-ascending).

    Raises:
        UnknownScenarioError: if scenario_key is not recognized.
    """
    if scenario_key not in VALID_SCENARIOS:
        raise UnknownScenarioError(scenario_key)

    if scenario_key == SCENARIO_CLEAN_RUN:
        return _generate_clean_run()
    if scenario_key == SCENARIO_GOVERNANCE_ESCALATION:
        return _generate_governance_escalation()
    return _generate_retry_failure()


# ---------------------------------------------------------------------------
# Scenario 1: clean_run — happy path, all sends succeed
# ---------------------------------------------------------------------------


def _make_session_run_ids(scenario_key: str) -> tuple[str, str]:
    """Deterministic session_id and run_id for a scenario (no randomness)."""
    import hashlib

    s_raw = f"demo:{scenario_key}:session"
    r_raw = f"demo:{scenario_key}:run"
    s_hex = hashlib.sha256(s_raw.encode()).hexdigest()[:12]
    r_hex = hashlib.sha256(r_raw.encode()).hexdigest()[:12]
    return f"sess-{s_hex}", f"run-{r_hex}"


def _generate_clean_run() -> list[NormalizedEvent]:
    """
    Scenario: clean_run
    Flow: pending → running → [3 sends] → completed
    Terminal state: completed
    """
    session_id, run_id = _make_session_run_ids(SCENARIO_CLEAN_RUN)

    raw: list[dict] = [
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_INFO,
            "sequence": 1,
            "timestamp": _ts(0),
            "description": "Session started — state pending → running",
            "metadata": {"from_state": "pending", "to_state": "running"},
        },
        {
            "event_type": EVENT_TYPE_BATCH_START,
            "severity": SEVERITY_INFO,
            "sequence": 2,
            "timestamp": _ts(1),
            "description": "Batch execution started",
            "metadata": {"prospect_count": 3},
        },
        {
            "event_type": EVENT_TYPE_SEND_ATTEMPT,
            "severity": SEVERITY_INFO,
            "sequence": 3,
            "timestamp": _ts(5),
            "description": "Send attempt: prospect-001@example.com",
            "metadata": {"email": "prospect-001@example.com", "status": "sent"},
        },
        {
            "event_type": EVENT_TYPE_SEND_ATTEMPT,
            "severity": SEVERITY_INFO,
            "sequence": 4,
            "timestamp": _ts(10),
            "description": "Send attempt: prospect-002@example.com",
            "metadata": {"email": "prospect-002@example.com", "status": "sent"},
        },
        {
            "event_type": EVENT_TYPE_SEND_ATTEMPT,
            "severity": SEVERITY_INFO,
            "sequence": 5,
            "timestamp": _ts(15),
            "description": "Send attempt: prospect-003@example.com",
            "metadata": {"email": "prospect-003@example.com", "status": "sent"},
        },
        {
            "event_type": EVENT_TYPE_BATCH_COMPLETE,
            "severity": SEVERITY_INFO,
            "sequence": 6,
            "timestamp": _ts(20),
            "description": "Batch complete — 3/3 sent",
            "metadata": {"attempted": 3, "sent": 3, "blocked": 0},
        },
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_INFO,
            "sequence": 7,
            "timestamp": _ts(21),
            "description": "Session completed — state running → completed",
            "metadata": {"from_state": "running", "to_state": "completed"},
        },
    ]
    return _build_events(raw, session_id, run_id)


# ---------------------------------------------------------------------------
# Scenario 2: governance_escalation — HARD block → awaiting_approval → approved
# ---------------------------------------------------------------------------


def _generate_governance_escalation() -> list[NormalizedEvent]:
    """
    Scenario: governance_escalation
    Flow: running → HARD governance → awaiting_approval → approved → running → completed
    The HARD governance event is visible via WebSocket (PR2 exit criterion).
    Terminal state: completed
    """
    session_id, run_id = _make_session_run_ids(SCENARIO_GOVERNANCE_ESCALATION)

    raw: list[dict] = [
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_INFO,
            "sequence": 1,
            "timestamp": _ts(0),
            "description": "Session started — state pending → running",
            "metadata": {"from_state": "pending", "to_state": "running"},
        },
        {
            "event_type": EVENT_TYPE_BATCH_START,
            "severity": SEVERITY_INFO,
            "sequence": 2,
            "timestamp": _ts(1),
            "description": "Batch execution started",
            "metadata": {"prospect_count": 5},
        },
        {
            "event_type": EVENT_TYPE_SEND_ATTEMPT,
            "severity": SEVERITY_INFO,
            "sequence": 3,
            "timestamp": _ts(5),
            "description": "Send attempt: prospect-001@example.com",
            "metadata": {"email": "prospect-001@example.com", "status": "sent"},
        },
        {
            "event_type": EVENT_TYPE_GOVERNANCE,
            "severity": SEVERITY_HARD,
            "sequence": 4,
            "timestamp": _ts(8),
            "description": "HARD governance block: daily send cap exceeded",
            "metadata": {
                "rule": "DAILY_CAP",
                "threshold": 40,
                "current_count": 41,
                "action": "escalate_to_operator",
            },
        },
        {
            "event_type": EVENT_TYPE_SEND_BLOCKED,
            "severity": SEVERITY_HARD,
            "sequence": 5,
            "timestamp": _ts(9),
            "description": "Send blocked due to governance HARD block",
            "metadata": {
                "email": "prospect-002@example.com",
                "block_reason": "DAILY_CAP",
            },
        },
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_HARD,
            "sequence": 6,
            "timestamp": _ts(10),
            "description": "State escalated — running → awaiting_approval",
            "metadata": {
                "from_state": "running",
                "to_state": "awaiting_approval",
                "trigger": "governance_hard",
            },
        },
        {
            "event_type": EVENT_TYPE_APPROVAL_REQUESTED,
            "severity": SEVERITY_HARD,
            "sequence": 7,
            "timestamp": _ts(11),
            "description": "Operator approval requested — HARD block requires review",
            "metadata": {"governance_rule": "DAILY_CAP"},
        },
        {
            "event_type": EVENT_TYPE_APPROVED,
            "severity": SEVERITY_INFO,
            "sequence": 8,
            "timestamp": _ts(120),
            "description": "Operator approved — resuming execution",
            "metadata": {"operator_note": "cap reset for today"},
        },
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_INFO,
            "sequence": 9,
            "timestamp": _ts(121),
            "description": "State restored — awaiting_approval → running",
            "metadata": {"from_state": "awaiting_approval", "to_state": "running"},
        },
        {
            "event_type": EVENT_TYPE_SEND_ATTEMPT,
            "severity": SEVERITY_INFO,
            "sequence": 10,
            "timestamp": _ts(125),
            "description": "Send attempt: prospect-002@example.com (post-approval)",
            "metadata": {"email": "prospect-002@example.com", "status": "sent"},
        },
        {
            "event_type": EVENT_TYPE_BATCH_COMPLETE,
            "severity": SEVERITY_INFO,
            "sequence": 11,
            "timestamp": _ts(130),
            "description": "Batch complete — 2/5 sent (3 deferred to next run)",
            "metadata": {"attempted": 5, "sent": 2, "blocked": 3},
        },
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_INFO,
            "sequence": 12,
            "timestamp": _ts(131),
            "description": "Session completed — running → completed",
            "metadata": {"from_state": "running", "to_state": "completed"},
        },
    ]
    return _build_events(raw, session_id, run_id)


# ---------------------------------------------------------------------------
# Scenario 3: retry_failure — retry cycle → terminal failure
# ---------------------------------------------------------------------------


def _generate_retry_failure() -> list[NormalizedEvent]:
    """
    Scenario: retry_failure
    Flow: running → SOFT block → retry × 2 → failure → failed
    Both retry and failure events are visible (PR2 exit criterion).
    Terminal state: failed
    """
    session_id, run_id = _make_session_run_ids(SCENARIO_RETRY_FAILURE)

    raw: list[dict] = [
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_INFO,
            "sequence": 1,
            "timestamp": _ts(0),
            "description": "Session started — state pending → running",
            "metadata": {"from_state": "pending", "to_state": "running"},
        },
        {
            "event_type": EVENT_TYPE_BATCH_START,
            "severity": SEVERITY_INFO,
            "sequence": 2,
            "timestamp": _ts(1),
            "description": "Batch execution started",
            "metadata": {"prospect_count": 2},
        },
        {
            "event_type": EVENT_TYPE_SEND_ATTEMPT,
            "severity": SEVERITY_INFO,
            "sequence": 3,
            "timestamp": _ts(5),
            "description": "Send attempt: prospect-001@example.com",
            "metadata": {"email": "prospect-001@example.com", "status": "sent"},
        },
        {
            "event_type": EVENT_TYPE_GOVERNANCE,
            "severity": SEVERITY_SOFT,
            "sequence": 4,
            "timestamp": _ts(10),
            "description": "SOFT governance block: provider timeout on send attempt",
            "metadata": {
                "rule": "PROVIDER_TIMEOUT",
                "job_id": "job-abc123",
                "attempt": 1,
            },
        },
        {
            "event_type": EVENT_TYPE_RETRY,
            "severity": SEVERITY_SOFT,
            "sequence": 5,
            "timestamp": _ts(15),
            "description": "Retry attempt 1/2 for job-abc123",
            "metadata": {
                "job_id": "job-abc123",
                "retry_count": 1,
                "max_retries": 2,
                "email": "prospect-002@example.com",
            },
        },
        {
            "event_type": EVENT_TYPE_GOVERNANCE,
            "severity": SEVERITY_SOFT,
            "sequence": 6,
            "timestamp": _ts(25),
            "description": "SOFT governance block: provider timeout on retry 1",
            "metadata": {
                "rule": "PROVIDER_TIMEOUT",
                "job_id": "job-abc123",
                "attempt": 2,
            },
        },
        {
            "event_type": EVENT_TYPE_RETRY,
            "severity": SEVERITY_SOFT,
            "sequence": 7,
            "timestamp": _ts(30),
            "description": "Retry attempt 2/2 for job-abc123",
            "metadata": {
                "job_id": "job-abc123",
                "retry_count": 2,
                "max_retries": 2,
                "email": "prospect-002@example.com",
            },
        },
        {
            "event_type": EVENT_TYPE_FAILURE,
            "severity": SEVERITY_HARD,
            "sequence": 8,
            "timestamp": _ts(40),
            "description": "Terminal failure: max retries exhausted for job-abc123",
            "metadata": {
                "job_id": "job-abc123",
                "retry_count": 2,
                "reason": "PROVIDER_TIMEOUT_MAX_RETRIES",
                "email": "prospect-002@example.com",
            },
        },
        {
            "event_type": EVENT_TYPE_STATE_CHANGE,
            "severity": SEVERITY_HARD,
            "sequence": 9,
            "timestamp": _ts(41),
            "description": "Session failed — running → failed",
            "metadata": {
                "from_state": "running",
                "to_state": "failed",
                "trigger": "fail",
                "reason": "max_retries_exhausted",
            },
        },
    ]
    return _build_events(raw, session_id, run_id)


# ---------------------------------------------------------------------------
# Internal: build events through the real normalizer
# ---------------------------------------------------------------------------


def _build_events(
    raw: list[dict],
    session_id: str,
    run_id: str,
) -> list[NormalizedEvent]:
    """
    Build NormalizedEvents by passing each raw dict through the real normalizer.
    This enforces the single pipeline rule (§4): demo feeds the real normalizer.
    """
    from event_normalizer import normalize

    events: list[NormalizedEvent] = []
    for item in raw:
        event = normalize(
            session_id=session_id,
            run_id=run_id,
            event_type=item["event_type"],
            severity=item.get("severity", SEVERITY_INFO),
            sequence=item["sequence"],
            description=item.get("description", ""),
            metadata=item.get("metadata"),
            timestamp=item.get("timestamp"),
        )
        events.append(event)
    events.sort(key=lambda e: e.sequence)
    return events
