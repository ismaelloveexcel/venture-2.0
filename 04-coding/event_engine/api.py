"""
api.py -- FastAPI control plane for the execution state machine.

Architecture role: CONTROL PLANE (stateless).
- No computation on execution state -- only projection and command dispatch
- Session state is owned by SessionManager
- Events are owned by EventStore
- This module wires them together behind HTTP endpoints

PR1 endpoints (section 8 of runtime_contract.md):
    GET  /health
    GET  /status
    GET  /sessions
    GET  /sessions/{id}
    GET  /sessions/{id}/events
    GET  /sessions/{id}/replay
    GET  /query/{path}

PR2 endpoints (section 8 of runtime_contract.md):
    WS   /sessions/{id}/stream    -- live event stream (polling, closes on terminal)
    POST /sessions/{id}/command   -- send operator command to session

Rules:
- Zero import-time side effects (INV-1)
- No execution logic in API handlers (INV-5 extended)
- All responses return typed Pydantic models or typed dicts
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from domain_types import (
    NormalizedEvent,
    SessionState,
    EVENT_TYPE_STATE_CHANGE,
    SEVERITY_INFO,
)
from event_store import EventStore
from session_manager import SessionManager, SessionNotFoundError
from demo_event_generator import generate_scenario, VALID_SCENARIOS
from command_validator import CommandValidator, InvalidCommandError

# ---------------------------------------------------------------------------
# Request models (Pydantic -- validated at the boundary)
# ---------------------------------------------------------------------------


class CommandRequest(BaseModel):
    """Body for POST /sessions/{id}/command."""

    command: str


# ---------------------------------------------------------------------------
# Application factory -- dependency-injected (testable, no module-level state)
# ---------------------------------------------------------------------------


def create_app(
    session_manager: SessionManager | None = None,
    event_store: EventStore | None = None,
    _poll_interval: float = 0.05,
) -> FastAPI:
    """
    Create and configure the FastAPI application.

    Args:
        session_manager: Injected SessionManager (default: new instance).
        event_store: Injected EventStore (default: new instance).
        _poll_interval: WebSocket polling interval in seconds (injectable for tests).

    Returns:
        Configured FastAPI application.
    """
    _session_manager = session_manager or SessionManager()
    _event_store = event_store or EventStore()
    _validator = CommandValidator()

    app = FastAPI(
        title="Venture OS -- Execution State Machine",
        version="1.0.0",
        description=(
            "Replayable event-sourced execution state machine. "
            "Backend: event-sourced kernel. "
            "API: stateless control plane. "
            "UI: projection layer only."
        ),
    )

    # -----------------------------------------------------------------------
    # GET /health -- liveness check
    # -----------------------------------------------------------------------

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Liveness probe. Returns 200 when the API is up."""
        return {"status": "ok"}

    # -----------------------------------------------------------------------
    # GET /status -- session counts by state
    # -----------------------------------------------------------------------

    @app.get("/status")
    async def status() -> dict[str, Any]:
        """Return session counts grouped by state."""
        counts = _session_manager.count_by_state()
        total = sum(counts.values())
        return {
            "session_counts": counts,
            "total_sessions": total,
        }

    # -----------------------------------------------------------------------
    # GET /sessions -- list all sessions
    # -----------------------------------------------------------------------

    @app.get("/sessions")
    async def list_sessions() -> dict[str, Any]:
        """List all sessions as immutable snapshots."""
        sessions = _session_manager.list_sessions()
        return {
            "sessions": [_session_to_dict(s) for s in sessions],
            "count": len(sessions),
        }

    # -----------------------------------------------------------------------
    # GET /sessions/{id} -- session detail
    # -----------------------------------------------------------------------

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: str) -> dict[str, Any]:
        """Get session detail including current state and event count."""
        try:
            snapshot = _session_manager.get_session(session_id)
        except SessionNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Session {session_id!r} not found"
            )
        event_count = _event_store.event_count(session_id)
        return {
            **_session_to_dict(snapshot),
            "event_count": event_count,
        }

    # -----------------------------------------------------------------------
    # GET /sessions/{id}/events -- all events for session
    # -----------------------------------------------------------------------

    @app.get("/sessions/{session_id}/events")
    async def get_session_events(
        session_id: str,
        from_sequence: int = 0,
    ) -> dict[str, Any]:
        """Get all events for a session, ordered by sequence."""
        if not _session_manager.session_exists(session_id):
            raise HTTPException(
                status_code=404, detail=f"Session {session_id!r} not found"
            )
        events = _event_store.get_session_events(
            session_id, from_sequence=from_sequence
        )
        return {
            "session_id": session_id,
            "events": [e.to_dict() for e in events],
            "count": len(events),
        }

    # -----------------------------------------------------------------------
    # GET /sessions/{id}/replay -- full replay in sequence order
    # -----------------------------------------------------------------------

    @app.get("/sessions/{session_id}/replay")
    async def replay_session(session_id: str) -> dict[str, Any]:
        """Replay all events for a session in sequence order."""
        if not _session_manager.session_exists(session_id):
            raise HTTPException(
                status_code=404, detail=f"Session {session_id!r} not found"
            )
        events = _event_store.replay(session_id)
        return {
            "session_id": session_id,
            "replay": [e.to_dict() for e in events],
            "event_count": len(events),
        }

    # -----------------------------------------------------------------------
    # GET /query/{path} -- generic query pass-through
    # -----------------------------------------------------------------------

    @app.get("/query/{query_path:path}")
    async def query(query_path: str) -> dict[str, Any]:
        """Generic query endpoint for arbitrary projection queries."""
        parts = query_path.strip("/").split("/")

        if parts == ["scenarios"]:
            return {"scenarios": sorted(VALID_SCENARIOS)}

        if len(parts) == 3 and parts[:2] == ["sessions", "by-state"]:
            target_state = parts[2]
            sessions = _session_manager.list_sessions()
            matched = [_session_to_dict(s) for s in sessions if s.state == target_state]
            return {"state": target_state, "sessions": matched, "count": len(matched)}

        if len(parts) == 3 and parts[:2] == ["events", "by-type"]:
            target_type = parts[2]
            all_sessions = _event_store.get_all_sessions()
            matched: list[dict[str, Any]] = []
            for sid in all_sessions:
                for ev in _event_store.get_session_events(sid):
                    if ev.event_type == target_type:
                        matched.append(ev.to_dict())
            matched.sort(key=lambda e: (e["session_id"], e["sequence"]))
            return {"event_type": target_type, "events": matched, "count": len(matched)}

        raise HTTPException(
            status_code=404, detail=f"Unknown query path: {query_path!r}"
        )

    # -----------------------------------------------------------------------
    # POST /demo/{scenario} -- seed a demo scenario
    # -----------------------------------------------------------------------

    @app.post("/demo/{scenario_key}")
    async def seed_demo(scenario_key: str) -> dict[str, Any]:
        """Seed a demo scenario into the state machine."""
        if scenario_key not in VALID_SCENARIOS:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown scenario {scenario_key!r}. Valid: {sorted(VALID_SCENARIOS)}",
            )

        snapshot = _session_manager.create_session(scenario=scenario_key)
        session_id = snapshot.session_id
        run_id = snapshot.run_id

        events = generate_scenario(scenario_key)

        from event_normalizer import normalize as _normalize

        bound_events = []
        for ev in events:
            bound = _normalize(
                session_id=session_id,
                run_id=run_id,
                event_type=ev.event_type,
                severity=ev.severity,
                sequence=ev.sequence,
                description=ev.description,
                metadata=dict(ev.metadata),
                timestamp=ev.timestamp,
            )
            bound_events.append(bound)

        _event_store.append_batch(bound_events)
        _apply_demo_state_transitions(_session_manager, session_id, bound_events)

        final = _session_manager.get_session(session_id)
        return {
            "session_id": session_id,
            "run_id": run_id,
            "scenario": scenario_key,
            "event_count": len(bound_events),
            "final_state": final.state,
        }

    # -----------------------------------------------------------------------
    # POST /sessions/{id}/command -- dispatch operator command (PR2)
    # -----------------------------------------------------------------------

    @app.post("/sessions/{session_id}/command")
    async def send_command(session_id: str, body: CommandRequest) -> dict[str, Any]:
        """
        Send an operator command to a session.

        Status codes:
            200 -- command applied, returns new session state
            400 -- unknown command name
            404 -- session not found
            409 -- command not valid in current state (invalid transition)
        """
        try:
            _validator.validate(body.command)
        except InvalidCommandError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

        target = _validator.target_state(body.command)

        if not _session_manager.session_exists(session_id):
            raise HTTPException(
                status_code=404, detail=f"Session {session_id!r} not found"
            )

        from_snapshot = _session_manager.get_session(session_id)
        from_state = from_snapshot.state

        from session_manager import InvalidTransitionError

        try:
            new_snapshot = _session_manager.transition(session_id, target)
        except InvalidTransitionError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

        from event_normalizer import normalize as _normalize

        seq = _event_store.event_count(session_id) + 1
        run_id = _session_manager.get_run_id(session_id)
        ev = _normalize(
            session_id=session_id,
            run_id=run_id,
            event_type=EVENT_TYPE_STATE_CHANGE,
            severity=SEVERITY_INFO,
            sequence=seq,
            description=f"Command applied: {body.command} ({from_state} to {target})",
            metadata={
                "command": body.command,
                "from_state": from_state,
                "to_state": target,
            },
        )
        _event_store.append(ev)

        return {
            "session_id": session_id,
            "command": body.command,
            "previous_state": from_state,
            "new_state": new_snapshot.state,
            "event_id": ev.event_id,
        }

    # -----------------------------------------------------------------------
    # WS /sessions/{id}/stream -- live event stream (PR2)
    # -----------------------------------------------------------------------

    @app.websocket("/sessions/{session_id}/stream")
    async def stream_events(websocket: WebSocket, session_id: str) -> None:
        """
        Stream events for a session over WebSocket.

        Projection-only (INV-5). Polls every _poll_interval seconds.
        Closes with 4004 if session not found, 1000 on terminal completion.
        """
        if not _session_manager.session_exists(session_id):
            await websocket.close(code=4004, reason=f"Session {session_id!r} not found")
            return

        await websocket.accept()
        cursor = 0

        try:
            while True:
                new_events = _event_store.get_session_events(
                    session_id, from_sequence=cursor
                )
                for ev in new_events:
                    await websocket.send_json(ev.to_dict())
                    cursor = ev.sequence

                session = _session_manager.get_session(session_id)
                if session.is_terminal() and not new_events:
                    await websocket.send_json(
                        {
                            "type": "stream_end",
                            "session_id": session_id,
                            "final_state": session.state,
                        }
                    )
                    await websocket.close(code=1000)
                    return

                await asyncio.sleep(_poll_interval)
        except WebSocketDisconnect:
            pass

    return app


# ---------------------------------------------------------------------------
# Helper functions (pure -- no side effects, module-level)
# ---------------------------------------------------------------------------


def _session_to_dict(s: SessionState) -> dict[str, Any]:
    return {
        "session_id": s.session_id,
        "run_id": s.run_id,
        "state": s.state,
        "scenario": s.scenario,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
        "event_count": s.event_count,
        "is_terminal": s.is_terminal(),
    }


def _apply_demo_state_transitions(
    sm: SessionManager,
    session_id: str,
    events: list[NormalizedEvent],
) -> None:
    """Replay state_change events to drive session to its demo terminal state."""
    from domain_types import EVENT_TYPE_STATE_CHANGE

    for ev in sorted(events, key=lambda e: e.sequence):
        if ev.event_type == EVENT_TYPE_STATE_CHANGE:
            to_state = ev.metadata.get("to_state")
            if isinstance(to_state, str):
                try:
                    sm.transition(session_id, to_state)
                except Exception:
                    pass
