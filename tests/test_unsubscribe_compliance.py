"""Phase A: MIME + List-Unsubscribe + footer behavior via send_guard."""

from __future__ import annotations

import send_guard as sg


def _canonical_cold() -> str:
    return "\n".join(
        [
            "Hi Alex,",
            "",
            "Noticed BrightOps Studio works with founder-led B2B teams on growth and acquisition.",
            "",
            "A lot of B2B service firms have a strong service, but outbound tends to break once it moves beyond referrals: unclear target accounts, inconsistent first-touch messaging, and no clear way to see what is actually working.",
            "",
            "I build client-owned outbound systems focused on one market with structured targeting, message review, sending controls, and reply tracking.",
            "",
            "If this might help, hit Reply, type yes, and send — subject unchanged is fine. "
            "I will follow up with a short walkthrough. Not a fit? No need to reply.",
        ]
    )


def test_list_unsubscribe_headers_and_footers_when_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_LIST_UNSUBSCRIBE", "true")
    monkeypatch.setenv("LIST_UNSUBSCRIBE_URL", "https://auditbound.io/unsubscribe-test")
    monkeypatch.setenv("ENABLE_LIST_UNSUBSCRIBE_POST", "true")
    p = sg.build_batch1_resend_payload(
        from_header="Ismael Sudally <outreach@abtmail.co>",
        to=["operator@example.com"],
        subject="outbound fit for your venture",
        cold_body_text=_canonical_cold(),
    )
    assert p.get("headers")
    assert "List-Unsubscribe" in p["headers"]
    assert "<https://auditbound.io/unsubscribe-test>" in p["headers"]["List-Unsubscribe"]
    assert p["headers"].get("List-Unsubscribe-Post") == "List-Unsubscribe=One-Click"
    assert "Unsubscribe:" in p["text"]
    assert "https://auditbound.io/unsubscribe-test" in p["text"]
    assert "Reply STOP" in p["text"]
    assert "unsubscribe-test" in p["html"]


def test_list_unsubscribe_post_off_by_default(monkeypatch):
    monkeypatch.setenv("ENABLE_LIST_UNSUBSCRIBE", "true")
    monkeypatch.setenv("LIST_UNSUBSCRIBE_URL", "https://auditbound.io/unsubscribe-test")
    monkeypatch.delenv("ENABLE_LIST_UNSUBSCRIBE_POST", raising=False)
    p = sg.build_batch1_resend_payload(
        from_header="Ismael Sudally <outreach@abtmail.co>",
        to=["operator@example.com"],
        subject="outbound fit for your venture",
        cold_body_text=_canonical_cold(),
    )
    assert "List-Unsubscribe" in (p.get("headers") or {})
    assert "List-Unsubscribe-Post" not in (p.get("headers") or {})
