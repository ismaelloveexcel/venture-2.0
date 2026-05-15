"""Phase A: canonical send-state tokens + outbound_events status validation."""

from __future__ import annotations

import pytest

from send_state import (
    CANONICAL_SEND_STATES,
    OUTBOUND_EVENT_STATUSES,
    SendStateValidationError,
    validate_canonical_send_state,
    validate_outbound_event_status,
)


def test_canonical_send_states_contains_expected_set():
    assert {"READY", "SENT", "FAILED", "SUPPRESSED"}.issubset(CANONICAL_SEND_STATES)


def test_validate_canonical_send_state_accepts_sent():
    assert validate_canonical_send_state("sent") == "SENT"


def test_validate_canonical_send_state_rejects_unknown():
    with pytest.raises(SendStateValidationError):
        validate_canonical_send_state("QUEUED")


def test_outbound_event_status_round_trip():
    assert validate_outbound_event_status("sent") == "sent"
    assert validate_outbound_event_status("DRY_RUN") == "dry_run"


def test_outbound_event_status_rejects_unknown():
    with pytest.raises(SendStateValidationError):
        validate_outbound_event_status("queued")


def test_outbound_event_statuses_matches_job_queue_contract():
    from job_queue import OUTBOUND_EVENT_STATUSES_ALLOWED  # noqa: PLC0415

    assert OUTBOUND_EVENT_STATUSES == OUTBOUND_EVENT_STATUSES_ALLOWED
