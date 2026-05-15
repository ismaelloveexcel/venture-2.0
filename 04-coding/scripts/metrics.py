"""Join send_log + reply_intent_log metrics (import-only; no CLI)."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


def canonical_message_hash(subject: str, html_body: str) -> str:
    """Must match ``JobQueue.message_hash`` (subject + HTML as sent)."""
    payload = f"{subject.strip()}::{html_body.strip()}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def safe_div(n: float, d: float) -> float:
    return float(n) / float(d) if d else 0.0


@dataclass
class MetricsResult:
    delivered: int
    positive_replies: int
    walkthrough_yes: int
    not_now: int
    not_a_fit: int
    unsubscribe: int
    unknown_or_missing_intent: int
    positive_reply_rate: float
    walkthrough_yes_rate: float
    conversion_ratio: float


def _read_send_delivered_by_email_cohort(
    send_log_path: Path,
) -> dict[tuple[str, str], bool]:
    """Map (email_lower, cohort_id) -> True if at least one row with send_status sent."""
    out: dict[tuple[str, str], bool] = {}
    if not send_log_path.is_file():
        return out
    with send_log_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if (row.get("send_status") or "").strip().lower() != "sent":
                continue
            email = (row.get("email") or "").strip().lower()
            cid = (row.get("cohort_id") or "").strip()
            if email and cid:
                out[(email, cid)] = True
    return out


def _first_reply_rows(reply_log_path: Path) -> list[dict[str, str]]:
    if not reply_log_path.is_file():
        return []
    rows: list[dict[str, str]] = []
    with reply_log_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append({k: (v or "") for k, v in row.items()})
    # Dedupe: first reply per (email, cohort_id) in file order
    seen: set[tuple[str, str]] = set()
    first: list[dict[str, str]] = []
    for row in rows:
        email = (row.get("prospect_email") or row.get("email") or "").strip().lower()
        cid = (row.get("cohort_id") or "").strip()
        if not email or not cid:
            continue
        key = (email, cid)
        if key in seen:
            continue
        seen.add(key)
        first.append(row)
    return first


def compute_metrics(
    reply_log_path: Path | str,
    send_log_path: Path | str,
) -> MetricsResult:
    """
    v1 delivered = count of distinct (email, cohort_id) with send_status sent in send_log.
    Reply counts from first reply per (email, cohort_id) in reply log, joined to delivered.
    """
    reply_log_path = Path(reply_log_path)
    send_log_path = Path(send_log_path)
    delivered_map = _read_send_delivered_by_email_cohort(send_log_path)
    delivered = len(delivered_map)

    pos = wt = nn = naf = unsub = unk = 0
    for row in _first_reply_rows(reply_log_path):
        email = (row.get("prospect_email") or row.get("email") or "").strip().lower()
        cid = (row.get("cohort_id") or "").strip()
        if (email, cid) not in delivered_map:
            continue
        intent = (row.get("reply_classification") or "").strip().lower()
        if intent == "positive_reply":
            pos += 1
        elif intent == "walkthrough_yes":
            wt += 1
        elif intent == "not_now":
            nn += 1
        elif intent == "not_a_fit":
            naf += 1
        elif intent == "unsubscribe":
            unsub += 1
        elif intent in (
            "ooo_auto",
            "neutral_question",
            "referral",
            "other_ambiguous",
            "",
        ):
            unk += 1
        else:
            unk += 1

    if pos > delivered or wt > delivered:
        raise ValueError(
            f"reply counts exceed delivered: positive_reply={pos} walkthrough_yes={wt} delivered={delivered}"
        )

    return MetricsResult(
        delivered=delivered,
        positive_replies=pos,
        walkthrough_yes=wt,
        not_now=nn,
        not_a_fit=naf,
        unsubscribe=unsub,
        unknown_or_missing_intent=unk,
        positive_reply_rate=safe_div(pos, delivered),
        walkthrough_yes_rate=safe_div(wt, delivered),
        conversion_ratio=safe_div(wt, pos),
    )


def iter_send_log_header_ok(send_log_path: Path, expected_header: Iterable[str]) -> bool:
    if not send_log_path.is_file():
        return False
    line = send_log_path.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if not line:
        return False
    actual = next(csv.reader([line[0]]))
    return list(actual) == list(expected_header)
