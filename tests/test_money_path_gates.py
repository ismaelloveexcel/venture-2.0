"""
P1 money-path safety: policy / credential gates before Resend; send_guard never hits httpx when blocked or dry_run.

Uses production modules with monkeypatch only (no second business-logic source).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import send_guard as sg

# test-only import for invariant: allowed exception
import venture_pipeline as vp  # test-only: allowed by orchestrator invariant
from batch1_release_gate import _canonical_payload
from send_guard import SendGuardBlocked


def test_send_email_returns_false_when_policy_gate_blocks_without_resend_call(
    monkeypatch,
):
    """Gatekeeper runs before credentials / _resend_request (money path order)."""
    calls: list[tuple] = []

    def _boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("_resend_request must not be called when policy blocks")

    monkeypatch.setattr(
        vp, "check_policy_gatekeeper", lambda: (False, "pytest_policy_block")
    )
    monkeypatch.setattr(vp, "_resend_request", _boom)

    ok = vp.send_email(
        "nobody@example.com",
        "No",
        "quick question",
        "<p>ignored</p>",
        prospect_id="pytest_policy",
    )
    assert ok is False
    assert calls == []


def test_send_email_returns_false_when_resend_not_configured_no_http(monkeypatch):
    monkeypatch.setattr(vp, "check_policy_gatekeeper", lambda: (True, ""))
    monkeypatch.setattr(vp, "RESEND_API_KEY", "")
    monkeypatch.setattr(vp, "RESEND_FROM_EMAIL", "")
    monkeypatch.setattr(
        vp,
        "_resend_request",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no HTTP")),
    )

    ok = vp.send_email(
        "nobody@example.com",
        "No",
        "quick question",
        "<p>x</p>",
        prospect_id="pytest_no_resend",
    )
    assert ok is False


def test_send_guard_blocks_unknown_send_type_without_httpx(monkeypatch):
    posts: list[object] = []
    monkeypatch.setattr(
        sg.httpx, "post", lambda *a, **k: posts.append(1) or MagicMock()
    )

    with pytest.raises(SendGuardBlocked, match="send_type"):
        sg.send_email_safe(
            payload=_canonical_payload(),
            api_key="re_fake_key_for_test",
            send_type="not_a_real_send_type",
            run_id="r1",
            dry_run=False,
            source="pytest",
        )
    assert posts == []


def test_send_guard_dry_run_initial_prospect_never_calls_httpx_post(monkeypatch):
    posts: list[object] = []

    def _no_live_http(*_a, **_k):
        raise AssertionError("httpx.post must not run in dry_run")

    monkeypatch.setattr(sg.httpx, "post", _no_live_http)

    resp = sg.send_email_safe(
        payload=_canonical_payload(),
        api_key="re_fake_key_for_test",
        send_type="initial_prospect",
        run_id="pytest_dry_run",
        dry_run=True,
        source="pytest",
    )

    assert resp.status_code == 200
    assert posts == []


def test_check_policy_gatekeeper_blocks_safe_mode(tmp_path, monkeypatch):
    pol = tmp_path / "policy.json"
    pol.write_text(
        '{"mode":"SAFE_MODE","send_velocity":"normal","followup_depth":0,'
        '"cooldown_multiplier":1.0,"reason":"pytest","decided_at":"","replay_enabled":false,'
        '"manual_reset_required":true}',
        encoding="utf-8",
    )
    monkeypatch.setenv("VENTURE_POLICY_JSON", str(pol))
    allowed, reason = vp.check_policy_gatekeeper()
    assert allowed is False
    assert "SAFE_MODE" in reason
