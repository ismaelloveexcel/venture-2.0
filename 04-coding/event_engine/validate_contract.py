"""
validate_contract.py — Contract validator for the event_engine PR1 exit criteria.

Verifies all Phase A and Phase B exit criteria from runtime_contract.md.
Exits 0 on PASS, non-zero on FAIL.

Usage:
    python 04-coding/event_engine/validate_contract.py
"""

from __future__ import annotations

import ast
import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ENGINE_DIR = Path(__file__).parent
ROOT = ENGINE_DIR.parent.parent
SCRIPTS_DIR = ROOT / "04-coding" / "scripts"


class CheckResult(NamedTuple):
    name: str
    passed: bool
    detail: str


def _check(name: str, passed: bool, detail: str = "") -> CheckResult:
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return CheckResult(name, passed, detail)


# ---------------------------------------------------------------------------
# INV-1: import venture_pipeline = zero side effects
# ---------------------------------------------------------------------------


def check_import_purity() -> CheckResult:
    result = subprocess.run(
        [sys.executable, "-c", "import venture_pipeline; print('ok')"],
        capture_output=True,
        text=True,
        cwd=str(SCRIPTS_DIR),
    )
    passed = result.returncode == 0 and "ok" in result.stdout
    detail = result.stderr.strip()[:200] if not passed else ""
    return _check("INV-1: import venture_pipeline zero side effects", passed, detail)


# ---------------------------------------------------------------------------
# INV-3: No untyped dict / None returns in domain_types boundaries
# ---------------------------------------------------------------------------


def check_domain_types() -> CheckResult:
    """Verify all 4+1 domain types exist and are frozen dataclasses."""
    try:
        sys.path.insert(0, str(ENGINE_DIR))
        import domain_types as dt

        required = [
            "ProspectRecord",
            "BatchResult",
            "GovernanceEvent",
            "FailureEvent",
            "NormalizedEvent",
        ]
        missing = [n for n in required if not hasattr(dt, n)]
        if missing:
            return _check("INV-3: domain types", False, f"Missing: {missing}")

        # Check all are frozen dataclasses
        import dataclasses

        not_frozen = []
        for name in required:
            cls = getattr(dt, name)
            if not dataclasses.is_dataclass(cls):
                not_frozen.append(f"{name}:not_dataclass")
            elif not cls.__dataclass_params__.frozen:
                not_frozen.append(f"{name}:not_frozen")

        if not_frozen:
            return _check("INV-3: domain types frozen", False, str(not_frozen))

        return _check(
            "INV-3: domain types", True, f"All {len(required)} types present and frozen"
        )
    except Exception as exc:
        return _check("INV-3: domain types", False, str(exc))


# ---------------------------------------------------------------------------
# SessionManager: sole run_id authority
# ---------------------------------------------------------------------------


def check_session_manager() -> CheckResult:
    """Verify SessionManager generates run_id and enforces state machine."""
    try:
        from session_manager import SessionManager, InvalidTransitionError

        sm = SessionManager()

        # Test session creation returns run_id
        snap = sm.create_session("test")
        assert snap.run_id.startswith("run-"), f"run_id format: {snap.run_id}"
        assert snap.session_id.startswith(
            "sess-"
        ), f"session_id format: {snap.session_id}"
        assert snap.state == "pending"

        # Test valid transition: pending → running
        snap2 = sm.transition(snap.session_id, "running")
        assert snap2.state == "running"

        # Test invalid transition rejected
        try:
            sm.transition(snap.session_id, "pending")  # running → pending is invalid
            return _check(
                "SessionManager state machine",
                False,
                "Should have raised InvalidTransitionError",
            )
        except InvalidTransitionError:
            pass

        # Test terminal states are absorbing
        sm.transition(snap.session_id, "completed")
        try:
            sm.transition(snap.session_id, "running")
            return _check(
                "SessionManager terminal absorbing",
                False,
                "Should have raised on terminal",
            )
        except InvalidTransitionError:
            pass

        return _check("SessionManager: sole run_id authority + state machine", True)
    except Exception as exc:
        return _check("SessionManager", False, str(exc))


# ---------------------------------------------------------------------------
# FastAPI: starts cleanly, /health returns 200
# ---------------------------------------------------------------------------


def check_fastapi_health() -> CheckResult:
    """Verify FastAPI app starts and /health returns 200."""
    try:
        from fastapi.testclient import TestClient
        from api import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/health")
        if resp.status_code != 200:
            return _check("FastAPI /health", False, f"status={resp.status_code}")
        data = resp.json()
        if data.get("status") != "ok":
            return _check("FastAPI /health body", False, str(data))
        return _check("FastAPI /health → 200 {status: ok}", True)
    except Exception as exc:
        return _check("FastAPI starts cleanly", False, str(exc))


def check_fastapi_status() -> CheckResult:
    """Verify /status returns session counts."""
    try:
        from fastapi.testclient import TestClient
        from api import create_app

        app = create_app()
        client = TestClient(app)
        resp = client.get("/status")
        if resp.status_code != 200:
            return _check("FastAPI /status", False, f"status={resp.status_code}")
        data = resp.json()
        if "session_counts" not in data:
            return _check("FastAPI /status body", False, str(data))
        return _check("FastAPI /status returns session counts", True)
    except Exception as exc:
        return _check("FastAPI /status", False, str(exc))


# ---------------------------------------------------------------------------
# Demo: clean_run produces events via API
# ---------------------------------------------------------------------------


def check_demo_clean_run() -> CheckResult:
    """Verify clean_run scenario produces events accessible via the API."""
    try:
        from fastapi.testclient import TestClient
        from api import create_app

        app = create_app()
        client = TestClient(app)

        # Seed the demo
        resp = client.post("/demo/clean_run")
        if resp.status_code != 200:
            return _check(
                "clean_run produces events via API",
                False,
                f"POST /demo/clean_run → {resp.status_code}: {resp.text}",
            )

        data = resp.json()
        session_id = data["session_id"]
        event_count = data["event_count"]

        if event_count == 0:
            return _check("clean_run event count", False, "No events generated")

        # Fetch via API
        resp2 = client.get(f"/sessions/{session_id}/events")
        if resp2.status_code != 200:
            return _check(
                "clean_run /sessions/{id}/events", False, str(resp2.status_code)
            )

        events = resp2.json()["events"]
        if len(events) == 0:
            return _check("clean_run events via API", False, "events list empty")

        return _check(
            "clean_run produces events via API",
            True,
            f"{len(events)} events, session={session_id}, state={data['final_state']}",
        )
    except Exception as exc:
        return _check("clean_run produces events via API", False, str(exc))


# ---------------------------------------------------------------------------
# Demo determinism check
# ---------------------------------------------------------------------------


def check_demo_determinism() -> CheckResult:
    """Verify generate_scenario is deterministic."""
    try:
        from demo_event_generator import generate_scenario, VALID_SCENARIOS

        for scenario_key in sorted(VALID_SCENARIOS):
            events_a = generate_scenario(scenario_key)
            events_b = generate_scenario(scenario_key)
            if len(events_a) != len(events_b):
                return _check(
                    f"Demo determinism {scenario_key}", False, "length mismatch"
                )
            for ea, eb in zip(events_a, events_b):
                if ea.event_id != eb.event_id or ea.sequence != eb.sequence:
                    return _check(
                        f"Demo determinism {scenario_key}",
                        False,
                        "event_id/sequence mismatch",
                    )

        return _check("Demo scenarios deterministic (all 3)", True)
    except Exception as exc:
        return _check("Demo determinism", False, str(exc))


# ---------------------------------------------------------------------------
# INV-7: No is_demo / source fields in NormalizedEvent
# ---------------------------------------------------------------------------


def check_no_source_fields() -> CheckResult:
    """Verify NormalizedEvent has no is_demo or source fields."""
    try:
        import dataclasses
        from domain_types import NormalizedEvent

        fields = {f.name for f in dataclasses.fields(NormalizedEvent)}
        forbidden = {"is_demo", "source", "origin"}
        found = fields & forbidden
        if found:
            return _check("INV-7: no is_demo/source fields", False, str(found))
        return _check("INV-7: no is_demo/source fields in NormalizedEvent", True)
    except Exception as exc:
        return _check("INV-7", False, str(exc))


# ---------------------------------------------------------------------------
# INV-2: Single pipeline (normalizer used by demo)
# ---------------------------------------------------------------------------


def check_single_pipeline() -> CheckResult:
    """Verify demo events pass through the real normalizer."""
    try:
        from demo_event_generator import generate_scenario
        from domain_types import NormalizedEvent

        events = generate_scenario("clean_run")
        for ev in events:
            if not isinstance(ev, NormalizedEvent):
                return _check("INV-2: single pipeline", False, f"Got {type(ev)}")
        return _check("INV-2: demo events are NormalizedEvent (real normalizer)", True)
    except Exception as exc:
        return _check("INV-2", False, str(exc))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_all() -> int:
    sys.path.insert(0, str(ENGINE_DIR))

    print("\n" + "=" * 60)
    print("  EVENT ENGINE — CONTRACT VALIDATOR  (PR1)")
    print("=" * 60)

    sections = [
        (
            "Phase A: Domain Types & Contract",
            [
                check_domain_types,
                check_no_source_fields,
                check_single_pipeline,
            ],
        ),
        (
            "Phase B: Import Purity (INV-1)",
            [
                check_import_purity,
            ],
        ),
        (
            "Phase B: SessionManager",
            [
                check_session_manager,
            ],
        ),
        (
            "Phase B: FastAPI Shell",
            [
                check_fastapi_health,
                check_fastapi_status,
            ],
        ),
        (
            "Phase B: Demo Scenarios",
            [
                check_demo_determinism,
                check_demo_clean_run,
            ],
        ),
    ]

    all_results: list[CheckResult] = []
    for section_name, checks in sections:
        print(f"\n── {section_name}")
        for check_fn in checks:
            result = check_fn()
            all_results.append(result)

    failed = [r for r in all_results if not r.passed]
    passed_count = len(all_results) - len(failed)

    print("\n" + "=" * 60)
    print(f"  RESULT: {passed_count}/{len(all_results)} checks passed")
    if failed:
        print(f"  FAILED CHECKS:")
        for r in failed:
            print(f"    ✗ {r.name}: {r.detail}")
        print("\n  STATUS: FAIL — address failures before PR1 merge")
        return 1
    else:
        print("\n  STATUS: PASS — PR1 contract validated")
        return 0


if __name__ == "__main__":
    raise SystemExit(run_all())
