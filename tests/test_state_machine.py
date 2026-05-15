from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "04-coding" / "venture-engine"))

from state_engine import (  # noqa: E402
    STATE_ENGINE_VERSION,
    detect_drift,
    transition,
    validate_path,
)


def test_valid_ready_sent_replied() -> None:
    s1 = transition("READY", "SEND")
    assert s1 == "SENT"
    s2 = transition(s1, "REPLY")
    assert s2 == "REPLIED"


def test_validate_path_accepts_canonical_chain() -> None:
    validate_path(["READY", "SENT", "REPLIED"])


def test_invalid_skip_sent_rejected() -> None:
    with pytest.raises(ValueError):
        validate_path(["READY", "REPLIED"])


def test_invalid_transition_event() -> None:
    with pytest.raises(ValueError):
        transition("READY", "REPLY")


def test_version_drift_flag() -> None:
    assert detect_drift(expected_version=STATE_ENGINE_VERSION, observed_version="0") is True
    assert detect_drift(expected_version=STATE_ENGINE_VERSION, observed_version=STATE_ENGINE_VERSION) is False
