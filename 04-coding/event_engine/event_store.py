"""
event_store.py — In-memory append-only event store (INV-6: persistence via event sinks).

Rules:
- Append-only: events cannot be modified or deleted after emission
- Thread-safe
- Events ordered by sequence within a session
- Zero import-time side effects (INV-1)
"""

from __future__ import annotations

import threading
from collections import defaultdict

from domain_types import NormalizedEvent


class EventStore:
    """
    In-memory append-only store for NormalizedEvents.

    This is the persistence layer for the event-sourced state machine.
    All mutations go through append() — no update, no delete (INV-6).
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # session_id → list of events in append order
        self._store: dict[str, list[NormalizedEvent]] = defaultdict(list)

    def append(self, event: NormalizedEvent) -> None:
        """Append an immutable event to the store."""
        with self._lock:
            self._store[event.session_id].append(event)

    def append_batch(self, events: list[NormalizedEvent]) -> None:
        """Append multiple events atomically within the lock."""
        with self._lock:
            for event in events:
                self._store[event.session_id].append(event)

    def get_session_events(
        self,
        session_id: str,
        *,
        from_sequence: int = 0,
    ) -> list[NormalizedEvent]:
        """
        Return all events for a session, sorted by sequence.

        Args:
            session_id: Target session.
            from_sequence: If > 0, return only events with sequence > from_sequence.
        """
        with self._lock:
            events = list(self._store.get(session_id, []))

        events.sort(key=lambda e: e.sequence)
        if from_sequence > 0:
            events = [e for e in events if e.sequence > from_sequence]
        return events

    def replay(self, session_id: str) -> list[NormalizedEvent]:
        """Return all events for a session in replay order (sequence ascending)."""
        return self.get_session_events(session_id)

    def get_all_sessions(self) -> list[str]:
        """Return all known session_ids."""
        with self._lock:
            return list(self._store.keys())

    def event_count(self, session_id: str) -> int:
        with self._lock:
            return len(self._store.get(session_id, []))

    def clear(self) -> None:
        """Reset store (test use only — never in production)."""
        with self._lock:
            self._store.clear()
