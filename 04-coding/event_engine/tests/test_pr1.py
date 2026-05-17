"""
test_pr1.py — PR1 exit criteria tests for the event_engine.

These tests cover the Phase A and Phase B exit criteria from runtime_contract.md.
All 7 PR1 exit criteria are represented.

Exit criteria:
  1. `import venture_pipeline` produces zero side effects                (INV-1)
  2. pytest passes across the whole test suite                           (CI gate)
  3. All 5 domain types present and frozen                               (INV-3)
  4. SessionManager is sole run_id authority; state machine enforced     (SessionManager)
  5. FastAPI starts cleanly; /health returns 200                         (API shell)
  6. /status returns session counts                                      (projection)
  7. clean_run scenario produces events accessible via API               (INV-2)
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add engine directory to path (also done by conftest.py but explicit here)
ENGINE_DIR = Path(__file__).parent.parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

SCRIPTS_DIR = ENGINE_DIR.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


# ---------------------------------------------------------------------------
# Criterion 1: INV-1 — import venture_pipeline = zero side effects
# ---------------------------------------------------------------------------


def test_import_venture_pipeline_zero_side_effects():
    """
    INV-1: import venture_pipeline must produce zero side effects.
    No load_dotenv, no logging setup, no DB connection at module scope.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import venture_pipeline; print('import-ok')"],
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS_DIR),
    )
    assert (
        result.returncode == 0
    ), f"venture_pipeline import failed.\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "import-ok" in result.stdout
    # Must NOT print startup banners at import time
    assert (
        "Pipeline started" not in result.stdout
    ), "Module-scope logging detected (INV-1 violation)"
    assert (
        "Pipeline started" not in result.stderr
    ), "Module-scope logging detected (INV-1 violation)"


# ---------------------------------------------------------------------------
# Criterion 3: Domain types
# ---------------------------------------------------------------------------


class TestDomainTypes:
    """INV-3: All 5 domain types present, frozen, and type-correct."""

    def test_all_types_importable(self):
        from domain_types import (
            ProspectRecord,
            BatchResult,
            GovernanceEvent,
            FailureEvent,
            NormalizedEvent,
        )

        for cls in (
            ProspectRecord,
            BatchResult,
            GovernanceEvent,
            FailureEvent,
            NormalizedEvent,
        ):
            assert dataclasses.is_dataclass(cls), f"{cls.__name__} is not a dataclass"
            assert cls.__dataclass_params__.frozen, f"{cls.__name__} is not frozen"

    def test_batch_result_empty_classmethod(self):
        from domain_types import BatchResult

        empty = BatchResult.empty(run_id="run-test", session_id="sess-test")
        assert empty.attempted == 0
        assert empty.sent == 0
        assert empty.blocked == 0

    def test_normalized_event_to_dict(self):
        from event_normalizer import normalize

        ev = normalize(
            session_id="sess-abc",
            run_id="run-abc",
            event_type="batch_start",
            severity="INFO",
            sequence=1,
            description="test",
        )
        d = ev.to_dict()
        assert d["event_type"] == "batch_start"
        assert d["sequence"] == 1
        assert "event_id" in d

    def test_session_state_is_terminal(self):
        from domain_types import SessionState, TERMINAL_STATES

        for state in TERMINAL_STATES:
            snap = SessionState(
                session_id="s",
                run_id="r",
                state=state,
                scenario="x",
                created_at="t",
                updated_at="t",
                event_count=0,
            )
            assert snap.is_terminal(), f"{state} should be terminal"

    def test_normalized_event_no_source_field(self):
        """INV-7: NormalizedEvent must not have is_demo or source fields."""
        from domain_types import NormalizedEvent

        fields = {f.name for f in dataclasses.fields(NormalizedEvent)}
        for forbidden in ("is_demo", "source", "origin"):
            assert (
                forbidden not in fields
            ), f"Forbidden field {forbidden!r} in NormalizedEvent"


# ---------------------------------------------------------------------------
# Criterion 4: SessionManager
# ---------------------------------------------------------------------------


class TestSessionManager:
    """SessionManager is sole run_id authority."""

    def test_create_session_returns_run_id(self):
        from session_manager import SessionManager

        sm = SessionManager()
        snap = sm.create_session("test_scenario")
        assert snap.run_id.startswith("run-")
        assert snap.session_id.startswith("sess-")
        assert snap.state == "pending"

    def test_valid_state_transitions(self):
        from session_manager import SessionManager

        sm = SessionManager()
        snap = sm.create_session("test")
        snap = sm.transition(snap.session_id, "running")
        assert snap.state == "running"
        snap = sm.transition(snap.session_id, "completed")
        assert snap.state == "completed"

    def test_invalid_transition_raises(self):
        from session_manager import SessionManager, InvalidTransitionError

        sm = SessionManager()
        snap = sm.create_session("test")
        sm.transition(snap.session_id, "running")
        with pytest.raises(InvalidTransitionError):
            sm.transition(snap.session_id, "pending")  # running → pending invalid

    def test_terminal_state_absorbing(self):
        from session_manager import SessionManager, InvalidTransitionError

        sm = SessionManager()
        snap = sm.create_session("test")
        sm.transition(snap.session_id, "running")
        sm.transition(snap.session_id, "completed")
        with pytest.raises(InvalidTransitionError):
            sm.transition(snap.session_id, "running")

    def test_run_id_deterministic_per_session(self):
        from session_manager import SessionManager

        sm = SessionManager()
        snap = sm.create_session("test")
        run_id = sm.get_run_id(snap.session_id)
        # Same session always returns same run_id
        assert sm.get_run_id(snap.session_id) == run_id

    def test_count_by_state(self):
        from session_manager import SessionManager

        sm = SessionManager()
        snap1 = sm.create_session("s1")
        snap2 = sm.create_session("s2")
        sm.transition(snap1.session_id, "running")

        counts = sm.count_by_state()
        assert counts.get("running", 0) >= 1
        assert counts.get("pending", 0) >= 1


# ---------------------------------------------------------------------------
# Criterion 5: FastAPI starts cleanly
# ---------------------------------------------------------------------------


class TestFastAPIShell:
    """FastAPI starts cleanly; /health returns 200."""

    @pytest.fixture
    def client(self):
        from api import create_app

        return TestClient(create_app())

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body(self, client):
        resp = client.get("/health")
        assert resp.json() == {"status": "ok"}

    def test_nonexistent_endpoint_returns_404(self, client):
        resp = client.get("/not-a-real-endpoint-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Criterion 6: /status returns session counts
# ---------------------------------------------------------------------------


class TestStatusEndpoint:
    """/status returns session counts by state."""

    @pytest.fixture
    def client(self):
        from api import create_app

        return TestClient(create_app())

    def test_status_200(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200

    def test_status_has_session_counts(self, client):
        resp = client.get("/status")
        data = resp.json()
        assert "session_counts" in data
        assert "total_sessions" in data
        assert isinstance(data["total_sessions"], int)

    def test_sessions_endpoint_returns_list(self, client):
        resp = client.get("/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)

    def test_session_not_found_returns_404(self, client):
        resp = client.get("/sessions/nonexistent-session-id")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Criterion 7: clean_run scenario produces events via API
# ---------------------------------------------------------------------------


class TestDemoScenarioAPI:
    """clean_run scenario produces events accessible via the API (INV-2)."""

    @pytest.fixture
    def client(self):
        from api import create_app

        return TestClient(create_app())

    def test_demo_clean_run_creates_session(self, client):
        resp = client.post("/demo/clean_run")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "run_id" in data
        assert data["event_count"] > 0

    def test_demo_clean_run_events_accessible_via_api(self, client):
        resp = client.post("/demo/clean_run")
        session_id = resp.json()["session_id"]

        events_resp = client.get(f"/sessions/{session_id}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()["events"]
        assert len(events) > 0

    def test_demo_clean_run_session_terminal(self, client):
        resp = client.post("/demo/clean_run")
        data = resp.json()
        assert data["final_state"] in {"completed", "failed"}

    def test_demo_replay_matches_events(self, client):
        resp = client.post("/demo/clean_run")
        session_id = resp.json()["session_id"]

        replay_resp = client.get(f"/sessions/{session_id}/replay")
        events_resp = client.get(f"/sessions/{session_id}/events")

        assert replay_resp.status_code == 200
        assert len(replay_resp.json()["replay"]) == len(events_resp.json()["events"])

    def test_demo_unknown_scenario_returns_400(self, client):
        resp = client.post("/demo/not_a_real_scenario")
        assert resp.status_code == 400

    def test_demo_governance_escalation(self, client):
        resp = client.post("/demo/governance_escalation")
        assert resp.status_code == 200
        assert resp.json()["event_count"] > 0

    def test_demo_retry_failure(self, client):
        resp = client.post("/demo/retry_failure")
        assert resp.status_code == 200
        assert resp.json()["event_count"] > 0

    def test_query_scenarios_lists_all(self, client):
        resp = client.get("/query/scenarios")
        assert resp.status_code == 200
        data = resp.json()
        assert "clean_run" in data["scenarios"]
        assert "governance_escalation" in data["scenarios"]
        assert "retry_failure" in data["scenarios"]

    def test_query_sessions_by_state(self, client):
        client.post("/demo/clean_run")
        resp = client.get("/query/sessions/by-state/completed")
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions" in data


# ---------------------------------------------------------------------------
# Event normalizer
# ---------------------------------------------------------------------------


class TestEventNormalizer:
    """event_normalizer produces valid NormalizedEvent from raw inputs."""

    def test_normalize_valid_event(self):
        from event_normalizer import normalize

        ev = normalize(
            session_id="sess-abc",
            run_id="run-abc",
            event_type="batch_start",
            severity="INFO",
            sequence=1,
            description="test event",
        )
        assert ev.event_type == "batch_start"
        assert ev.event_id.startswith("evt-")
        assert ev.sequence == 1

    def test_normalize_rejects_invalid_event_type(self):
        from event_normalizer import normalize, NormalizationError

        with pytest.raises(NormalizationError):
            normalize(
                session_id="sess-abc",
                run_id="run-abc",
                event_type="NOT_A_REAL_EVENT",
                severity="INFO",
                sequence=1,
                description="test",
            )

    def test_normalize_rejects_invalid_severity(self):
        from event_normalizer import normalize, NormalizationError

        with pytest.raises(NormalizationError):
            normalize(
                session_id="sess-abc",
                run_id="run-abc",
                event_type="batch_start",
                severity="CRITICAL",
                sequence=1,
                description="test",
            )

    def test_normalize_deterministic_event_id(self):
        from event_normalizer import normalize

        ev1 = normalize(
            session_id="sess-abc",
            run_id="run-abc",
            event_type="batch_start",
            severity="INFO",
            sequence=1,
            description="test",
        )
        ev2 = normalize(
            session_id="sess-abc",
            run_id="run-abc",
            event_type="batch_start",
            severity="INFO",
            sequence=1,
            description="test",
        )
        assert ev1.event_id == ev2.event_id


# ---------------------------------------------------------------------------
# Event store
# ---------------------------------------------------------------------------


class TestEventStore:
    """EventStore is append-only and thread-safe."""

    def test_append_and_retrieve(self):
        from event_store import EventStore
        from event_normalizer import normalize

        store = EventStore()
        ev = normalize(
            session_id="sess-store",
            run_id="run-store",
            event_type="batch_start",
            severity="INFO",
            sequence=1,
            description="store test",
        )
        store.append(ev)
        events = store.get_session_events("sess-store")
        assert len(events) == 1
        assert events[0].event_id == ev.event_id

    def test_replay_in_sequence_order(self):
        from event_store import EventStore
        from event_normalizer import normalize

        store = EventStore()
        for seq in (3, 1, 2):
            ev = normalize(
                session_id="sess-replay",
                run_id="run-replay",
                event_type="batch_start",
                severity="INFO",
                sequence=seq,
                description="replay test",
            )
            store.append(ev)

        replayed = store.replay("sess-replay")
        sequences = [e.sequence for e in replayed]
        assert sequences == sorted(sequences)

    def test_append_batch(self):
        from event_store import EventStore
        from demo_event_generator import generate_scenario

        store = EventStore()
        events = generate_scenario("clean_run")
        store.append_batch(events)
        sid = events[0].session_id
        assert store.event_count(sid) == len(events)
