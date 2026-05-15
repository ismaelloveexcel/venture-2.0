"""
Non-interactive outbound preflight checks (import-only library).

Used by run_daily bridge preflight and may be invoked before live sends.
"""

from __future__ import annotations

import os
import re
import socket
from typing import Iterable

_PLACEHOLDER_SUBSTRINGS = (
    "YOUR_",
    "PLACEHOLDER",
    "CHANGE_ME",
    "EXAMPLE",
    "TEST_KEY",
)

_DISALLOWED_DOMAINS = frozenset(
    {
        "test.com",
        "example.com",
        "demo.com",
        "localhost",
        "mailinator.com",
    }
)


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _extra_deny_domains() -> set[str]:
    raw = (os.environ.get("VENTURE_PREFLIGHT_DOMAIN_DENYLIST", "") or "").strip().lower()
    if not raw:
        return set()
    parts = re.split(r"[\s,;]+", raw)
    return {p.strip() for p in parts if p.strip()}


def _extract_email_domain(addr: str) -> str:
    s = (addr or "").strip().lower()
    if "<" in s and ">" in s:
        s = s.split("<", 1)[1].split(">", 1)[0].strip()
    if "@" in s:
        return s.rsplit("@", 1)[-1].strip()
    return ""


def _check_placeholder_values() -> list[str]:
    errs: list[str] = []
    keys = (
        "RESEND_API_KEY",
        "RESEND_FROM_EMAIL",
        "OPENAI_API_KEY",
        "LIST_UNSUBSCRIBE_URL",
        "CALENDLY_BOOKING_URL",
    )
    for key in keys:
        val = (os.environ.get(key, "") or "").strip()
        if not val:
            continue
        low = val.lower()
        for sub in _PLACEHOLDER_SUBSTRINGS:
            if sub.lower() in low:
                errs.append(f"placeholder token {sub!r} detected in {key}")
                break
    return errs


def _iter_candidate_emails() -> Iterable[str]:
    for key in (
        "RESEND_FROM_EMAIL",
        "DIGEST_TO_EMAIL",
        "OUTREACH_TEST_TO",
        "INTERNAL_TEST_RECIPIENTS",
    ):
        raw = (os.environ.get(key, "") or "").strip()
        if not raw:
            continue
        for part in raw.replace(";", ",").split(","):
            em = part.strip()
            if em:
                yield em


def _check_disallowed_domains() -> list[str]:
    errs: list[str] = []
    deny = _DISALLOWED_DOMAINS | _extra_deny_domains()
    for em in _iter_candidate_emails():
        dom = _extract_email_domain(em)
        if dom in deny:
            errs.append(f"disallowed domain {dom!r} in email context: {em!r}")
    return errs


def _check_sender_domain_alignment() -> list[str]:
    errs: list[str] = []
    from_email = (os.environ.get("RESEND_FROM_EMAIL", "") or "").strip()
    dom = _extract_email_domain(from_email)
    allowed_raw = (os.environ.get("ALLOWED_SENDER_DOMAINS", "") or "").strip().lower()
    allowed = {p.strip() for p in re.split(r"[\s,;]+", allowed_raw) if p.strip()}
    if dom and allowed and dom not in allowed:
        errs.append(f"RESEND_FROM_EMAIL domain {dom!r} not in ALLOWED_SENDER_DOMAINS={sorted(allowed)}")
    return errs


def _check_dns_mx(domain: str) -> list[str]:
    errs: list[str] = []
    if _truthy_env("VENTURE_SKIP_DNS_CHECKS"):
        return errs
    if not domain:
        return errs
    try:
        socket.getaddrinfo(domain, None)
    except OSError as exc:
        errs.append(f"DNS lookup failed for {domain!r}: {exc}")
    return errs


def run_preflight_checks() -> tuple[bool, list[str]]:
    """
    Return (ok, reasons). When ok is False, reasons are human-readable lines.
    """
    reasons: list[str] = []
    reasons.extend(_check_placeholder_values())
    reasons.extend(_check_disallowed_domains())
    reasons.extend(_check_sender_domain_alignment())
    dom = _extract_email_domain((os.environ.get("RESEND_FROM_EMAIL", "") or "").strip())
    reasons.extend(_check_dns_mx(dom))
    return (len(reasons) == 0, reasons)


def format_preflight_report(ok: bool, reasons: list[str]) -> str:
    status = "PASS" if ok else "FAIL"
    lines = [f"PREFLIGHT\t{status}"]
    for r in reasons:
        lines.append(f"REASON\t{r}")
    if ok and not reasons:
        lines.append("REASON\t(no issues)")
    return "\n".join(lines) + "\n"
