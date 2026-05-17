"""test_pr2.py -- PR2 exit criteria: command validator, command endpoint, WebSocket stream."""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Path setup (handled by conftest.py -- sys.path already includes event_engine)
# ---------------------------------------------------------------------------

from command_validator import VALID_COMMANDS, COMMAND_TRANSITIONS, InvalidCommandError, CommandValidator
from domain_types import EVENT_TYPE_STATE_CHANGE
from event_store import EventStore
from session_manager import SessionManager
from api import create_app

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    """Fresh app with isolated SessionManager and EventStore. Poll interval 0 for speed."""
    sm = SessionManager()
    es = EventStore()
    app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture()
def seeded_client():
    """App pre-seeded with a clean_run demo session (terminal: completed)."""
    sm = SessionManager()
    es = EventStore()
    app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
    client = TestClient(app, raise_server_exceptions=True)
    resp = client.post("/demo/clean_run")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return client, data["session_id"]


# ---------------------------------------------------------------------------
# TestCommandValidator -- stateless unit tests
# ---------------------------------------------------------------------------


class TestCommandValidator:
    def test_validate_all_valid_commands(self):
        v = CommandValidator()
        for cmd in VALID_COMMANDS:
            result = v.validate(cmd)
            assert result == cmd

    def test_validate_invalid_command_raises(self):
        v = CommandValidator()
        with pytest.raises(InvalidCommandError):
            v.validate("LAUNCH")

    def test_validate_empty_string_raises(self):
        v = CommandValidator()
        with pytest.raises(InvalidCommandError):
            v.validate("")

    def test_target_state_start(self):
        v = CommandValidator()
        assert v.target_state("start") == "running"

    def test_target_state_reject(self):
        v = CommandValidator()
        assert v.target_state("reject") == "failed"

    def test_target_state_approve(self):
        v = CommandValidator()
        assert v.target_state("approve") == "running"

    def test_target_state_invalid_raises(self):
        v = CommandValidator()
        with pytest.raises(InvalidCommandError):
            v.target_state("NOOP")

    def test_commandvalidator_is_stateless(self):
        """Two instances must behave identically -- no shared state."""
        v1 = CommandValidator()
        v2 = CommandValidator()
        for cmd in VALID_COMMANDS:
            assert v1.target_state(cmd) == v2.target_state(cmd)

    def test_valid_commands_constant(self):
        assert "start" in VALID_COMMANDS
        assert "pause" in VALID_COMMANDS
        assert "resume" in VALID_COMMANDS
        assert "approve" in VALID_COMMANDS
        assert "reject" in VALID_COMMANDS

    def test_command_transitions_coverage(self):
        """Every valid command must have a transition entry."""
        for cmd in VALID_COMMANDS:
            assert cmd in COMMAND_TRANSITIONS


# ---------------------------------------------------------------------------
# TestCommandEndpoint -- POST /sessions/{id}/command
# ---------------------------------------------------------------------------


class TestCommandEndpoint:
    def test_command_start_pending_session(self, client):
        """Start command transitions pending -> running."""
        # Create a fresh pending session via /demo/clean_run but intercept before terminal
        # Instead, create directly via session_manager indirectly by hitting status first
        # then seeding a session that is not terminal.
        # Use the POST /demo/clean_run and then check final_state is completed.
        # For a non-terminal test: create a new session directly.

        # The cleanest way: create a raw session via POST /demo then verify state
        # Actually we need a pending session. Let's use the SM fixture approach.
        sm = SessionManager()
        es = EventStore()
        app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
        c = TestClient(app, raise_server_exceptions=True)

        # Create a session (pending state)
        sess = sm.create_session(scenario="test")
        session_id = sess.session_id

        resp = c.post(f"/sessions/{session_id}/command", json={"command": "start"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["command"] == "start"
        assert data["previous_state"] == "pending"
        assert data["new_state"] == "running"
        assert data["session_id"] == session_id
        assert "event_id" in data

    def test_command_invalid_name_returns_400(self, client):
        """Unknown command name returns 400."""
        sm = SessionManager()
        es = EventStore()
        app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
        c = TestClient(app, raise_server_exceptions=True)
        sess = sm.create_session(scenario="test")

        resp = c.post(f"/sessions/{sess.session_id}/command", json={"command": "LAUNCH"})
        assert resp.status_code == 400

    def test_command_session_not_found_returns_404(self, client):
        """Non-existent session returns 404."""
        resp = client.post("/sessions/nonexistent/command", json={"command": "start"})
        assert resp.status_code == 404

    def test_command_invalid_transition_returns_409(self, client):
        """Pause on a pending session is an invalid transition -- expect 409."""
        sm = SessionManager()
        es = EventStore()
        app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
        c = TestClient(app, raise_server_exceptions=True)
        sess = sm.create_session(scenario="test")

        # "pause" -> "paused" is not valid from "pending" (pending can only go to running)
        resp = c.post(f"/sessions/{sess.session_id}/command", json={"command": "pause"})
        assert resp.status_code == 409

    def test_command_appends_state_change_event(self, client):
        """After command, EventStore must contain a state_change event."""
        sm = SessionManager()
        es = EventStore()
        app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
        c = TestClient(app, raise_server_exceptions=True)
        sess = sm.create_session(scenario="test")
        session_id = sess.session_id

        c.post(f"/sessions/{session_id}/command", json={"command": "start"})

        events = es.get_session_events(session_id)
        assert len(events) == 1
        assert events[0].event_type == EVENT_TYPE_STATE_CHANGE

    def test_command_returns_event_id(self, client):
        """Returned event_id must start with evt- prefix."""
        sm = SessionManager()
        es = EventStore()
        app = create_app(session_manager=sm, event_store=es, _poll_interval=0)
        c = TestClient(app, raise_server_exceptions=True)
        sess = sm.create_session(scenario="test")

        resp = c.post(f"/sessions/{sess.session_id}/command", json={"command": "start"})
        assert resp.status_code == 200
        assert resp.json()["event_id"].startswith("evt-")


# ---------------------------------------------------------------------------
# TestWebSocketStream -- WS /sessions/{id}/stream
# ---------------------------------------------------------------------------


class TestWebSocketStream:
    def test_websocket_receives_events_for_terminal_session(self, seeded_client):
        """Connect to a completed session, receive all events then stream_end."""
        client, session_id = seeded_client
        messages = []
        with client.websocket_connect(f"/sessions/{session_id}/stream") as ws:
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "stream_end":
                    break

        # Must have received at least some events plus stream_end
        assert len(messages) >= 2
        assert messages[-1]["type"] == "stream_end"
        assert messages[-1]["session_id"] == session_id

    def test_websocket_nonexistent_session_closes(self, client):
        """Connect to non-existent session -- expect WebSocketDisconnect with code 4004."""
        from starlette.websockets import WebSocketDisconnect as _Disconnect
        with pytest.raises(_Disconnect) as exc_info:
            with client.websocket_connect("/sessions/nonexistent-id/stream") as ws:
                ws.receive_json()
        assert exc_info.value.code == 4004

    def test_websocket_stream_end_has_final_state(self, seeded_client):
        """stream_end message must include final_state field."""
        client, session_id = seeded_client
        messages = []
        with client.websocket_connect(f"/sessions/{session_id}/stream") as ws:
            while True:
                msg = ws.receive_json()
                messages.append(msg)
                if msg.get("type") == "stream_end":
                    break

        end_msg = messages[-1]
        assert end_msg["type"] == "stream_end"
        assert "final_state" in end_msg
        assert end_msg["final_state"] == "completed"
