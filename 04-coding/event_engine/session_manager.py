"""
session_manager.py — Sole authority for run_id generation and session lifecycle.

Rules:
- ONLY this module generates run_id values (no uuid4 elsewhere)
- Enforces state machine transitions — invalid transitions raise InvalidTransitionError
- Thread-safe (RLock on shared state)
- Zero import-time side effects (INV-1)
"""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Optional

from domain_types import (
    SESSION_STATE_PENDING,
    SESSION_STATE_RUNNING,
    TERMINAL_STATES,
    VALID_STATES,
    VALID_TRANSITIONS,
    SessionState,
)


class InvalidTransitionError(ValueError):
    """Raised when a state transition violates the state machine contract."""

    def __init__(self, session_id: str, from_state: str, to_state: str) -> None:
        super().__init__(
            f"Invalid transition: {from_state!r} → {to_state!r} "
            f"for session {session_id!r}"
        )
        self.session_id = session_id
        self.from_state = from_state
        self.to_state = to_state


class SessionNotFoundError(KeyError):
    """Raised when a session_id does not exist."""

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Session not found: {session_id!r}")
        self.session_id = session_id


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _generate_run_id(session_id: str, sequence: int) -> str:
    """
    Deterministic run_id from session_id + sequence.
    Format: run-{12-hex-chars}

    ONLY called by SessionManager. No uuid4 anywhere.
    """
    raw = f"{session_id}:{sequence}:run"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"run-{digest[:12]}"


def _generate_session_id(scenario: str, sequence: int) -> str:
    """
    Deterministic session_id from scenario + monotonic sequence.
    Format: sess-{12-hex-chars}
    """
    ts = str(int(time.monotonic_ns()))
    raw = f"{scenario}:{sequence}:{ts}"
    digest = hashlib.sha256(raw.encode()).hexdigest()
    return f"sess-{digest[:12]}"


# Internal mutable session record (not exposed externally)
class _SessionRecord:
    __slots__ = (
        "session_id",
        "run_id",
        "state",
        "created_at",
        "updated_at",
        "scenario",
        "event_count",
    )

    def __init__(
        self,
        session_id: str,
        run_id: str,
        scenario: str,
        created_at: str,
    ) -> None:
        self.session_id = session_id
        self.run_id = run_id
        self.state = SESSION_STATE_PENDING
        self.created_at = created_at
        self.updated_at = created_at
        self.scenario = scenario
        self.event_count = 0

    def to_snapshot(self) -> SessionState:
        return SessionState(
            session_id=self.session_id,
            run_id=self.run_id,
            state=self.state,
            created_at=self.created_at,
            updated_at=self.updated_at,
            scenario=self.scenario,
            event_count=self.event_count,
        )


class SessionManager:
    """
    Sole authority for run_id generation and session lifecycle.

    - Thread-safe via RLock
    - create_session() is the ONLY valid source of run_id
    - transition() enforces the state machine; raises InvalidTransitionError on violations
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sessions: dict[str, _SessionRecord] = {}
        self._sequence = 0  # monotonic session counter

    # ------------------------------------------------------------------
    # Session creation (sole run_id source)
    # ------------------------------------------------------------------

    def create_session(self, scenario: str = "live") -> SessionState:
        """
        Create a new session and its run_id.

        Returns the immutable SessionState snapshot.
        run_id is ONLY generated here — nowhere else in the codebase.
        """
        with self._lock:
            self._sequence += 1
            session_id = _generate_session_id(scenario, self._sequence)
            run_id = _generate_run_id(session_id, self._sequence)
            now = _utc_now_iso()
            record = _SessionRecord(
                session_id=session_id,
                run_id=run_id,
                scenario=scenario,
                created_at=now,
            )
            self._sessions[session_id] = record
            return record.to_snapshot()

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def transition(self, session_id: str, to_state: str) -> SessionState:
        """
        Apply a state transition.

        Raises:
            SessionNotFoundError: session_id unknown
            InvalidTransitionError: transition not in VALID_TRANSITIONS
            ValueError: to_state not in VALID_STATES
        """
        if to_state not in VALID_STATES:
            raise ValueError(f"Unknown state: {to_state!r}")

        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                raise SessionNotFoundError(session_id)

            from_state = record.state

            # Terminal states are absorbing
            if from_state in TERMINAL_STATES:
                raise InvalidTransitionError(session_id, from_state, to_state)

            if (from_state, to_state) not in VALID_TRANSITIONS:
                raise InvalidTransitionError(session_id, from_state, to_state)

            record.state = to_state
            record.updated_at = _utc_now_iso()
            return record.to_snapshot()

    def increment_event_count(self, session_id: str) -> None:
        """Record that an event was emitted for this session."""
        with self._lock:
            record = self._sessions.get(session_id)
            if record is not None:
                record.event_count += 1

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_session(self, session_id: str) -> SessionState:
        """
        Get a point-in-time snapshot of a session.

        Raises SessionNotFoundError if session_id unknown.
        """
        with self._lock:
            record = self._sessions.get(session_id)
            if record is None:
                raise SessionNotFoundError(session_id)
            return record.to_snapshot()

    def get_run_id(self, session_id: str) -> str:
        """Return the run_id for a session."""
        return self.get_session(session_id).run_id

    def list_sessions(self) -> list[SessionState]:
        """Return all sessions as immutable snapshots."""
        with self._lock:
            return [r.to_snapshot() for r in self._sessions.values()]

    def count_by_state(self) -> dict[str, int]:
        """Return session counts grouped by state."""
        with self._lock:
            counts: dict[str, int] = {}
            for r in self._sessions.values():
                counts[r.state] = counts.get(r.state, 0) + 1
            return counts

    def session_exists(self, session_id: str) -> bool:
        with self._lock:
            return session_id in self._sessions

    # ------------------------------------------------------------------
    # Convenience: start a session (pending → running)
    # ------------------------------------------------------------------

    def start_session(self, session_id: str) -> SessionState:
        return self.transition(session_id, SESSION_STATE_RUNNING)


# ---------------------------------------------------------------------------
# Module-level singleton (for use by API and event normalizer)
# No side effects at module scope — singleton is not instantiated here.
# Callers instantiate or inject their own SessionManager.
# ---------------------------------------------------------------------------
