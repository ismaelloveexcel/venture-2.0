"""
Outbound send eligibility — join prospects.csv with prospect_audit_log.csv (v2.2.7+).

Canonical run_id: VENTURE_RUN_ID or BATCH_RUN_ID.
Shared email normalization: prospect_gate.normalize_email.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from prospect_gate import PROSPECT_AUDIT_HEADER, normalize_email


def canonical_execution_run_id() -> str:
    """Single rule for pipeline + audit join (env-sourced)."""
    import os

    return (
        os.environ.get("VENTURE_RUN_ID", "").strip()
        or os.environ.get("BATCH_RUN_ID", "").strip()
        or ""
    )


def email_normalized(email: str | None) -> str:
    """Alias for audit join — must not re-implement normalization."""
    return normalize_email(email)


SEND_SKIPPED_HEADER = (
    "timestamp_utc,run_id,email,email_normalized,skip_reason,audit_classification"
)


class OutboundEligibilityAuditError(RuntimeError):
    """Missing audit log or header mismatch — pipeline must HALT."""


def _utc_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str) -> float:
    s = (value or "").strip().replace("Z", "+00:00")
    if not s:
        return 0.0
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        return 0.0


def prospect_csv_requires_audit_join(prospects_path: Path) -> bool:
    if not prospects_path.is_file():
        return False
    with prospects_path.open(newline="", encoding="utf-8") as fh:
        r = csv.DictReader(fh)
        cols = set(r.fieldnames or ())
    return "validation_status" in cols


def load_audit_eligibility_index(audit_path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Build dict[(run_id, email_normalized)] -> latest audit row dict.
    Header / fieldname mismatch → OutboundEligibilityAuditError.
    Missing file → OutboundEligibilityAuditError.
    Parse failure while reading body → empty index (fail-safe: no sends).
    """
    if not audit_path.is_file():
        raise OutboundEligibilityAuditError(
            f"prospect audit log missing (required for outbound eligibility): {audit_path}"
        )
    expected_fields = PROSPECT_AUDIT_HEADER.split(",")
    try:
        with audit_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            got = list(reader.fieldnames or [])
            if got != expected_fields:
                raise OutboundEligibilityAuditError(
                    "prospect_audit_log.csv header/field mismatch — cannot verify eligibility.\n"
                    f"  Expected fields: {expected_fields}\n"
                    f"  Found:           {got}"
                )
            rows = list(reader)
    except OutboundEligibilityAuditError:
        raise
    except (OSError, csv.Error, UnicodeDecodeError):
        return {}

    index: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        rid = (row.get("run_id") or "").strip()
        em = email_normalized(row.get("email"))
        if not rid or not em:
            continue
        key = (rid, em)
        ts = _parse_ts(str(row.get("timestamp_utc") or ""))
        prev = index.get(key)
        if prev is None or ts >= _parse_ts(str(prev.get("timestamp_utc") or "")):
            index[key] = dict(row)
    return index


def append_send_skipped_log(
    data_base: Path,
    *,
    run_id: str,
    email: str,
    skip_reason: str,
    audit_classification: str = "",
) -> None:
    path = data_base / "logs" / "send_skipped_log.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = SEND_SKIPPED_HEADER.split(",")
    if path.is_file():
        first = path.read_text(encoding="utf-8").splitlines()[:1]
        got = (first[0].strip() if first else "").replace("\r\n", "\n")
        want = SEND_SKIPPED_HEADER.strip()
        if got != want:
            raise OutboundEligibilityAuditError(
                "send_skipped_log.csv header mismatch — cannot append.\n"
                f"  Expected: {want!r}\n"
                f"  Found:    {got!r}"
            )
    mode = "a" if path.is_file() else "w"
    en = email_normalized(email)
    with path.open(mode, newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if mode == "w":
            w.writeheader()
        w.writerow(
            {
                "timestamp_utc": _utc_iso_z(),
                "run_id": run_id,
                "email": email or "",
                "email_normalized": en,
                "skip_reason": skip_reason,
                "audit_classification": audit_classification or "",
            }
        )


@dataclass
class EligibilityFilterResult:
    prospects: list[dict]
    skipped: int
    original_count: int
    all_ineligible_after_filter: bool


def filter_prospects_for_outbound_send(
    prospects: list[dict],
    *,
    prospects_path: Path,
    data_base: Path,
    current_run_id: str,
) -> EligibilityFilterResult:
    """
    When prospects.csv uses validation_status (gate-era), require audit ELIGIBLE
    for (run_id, email_normalized). Otherwise return prospects unchanged.
    """
    if not prospects or not prospect_csv_requires_audit_join(prospects_path):
        return EligibilityFilterResult(
            prospects=list(prospects),
            skipped=0,
            original_count=len(prospects),
            all_ineligible_after_filter=False,
        )
    audit_path = data_base / "07-kpis" / "prospect_audit_log.csv"
    try:
        index = load_audit_eligibility_index(audit_path)
    except OutboundEligibilityAuditError:
        raise
    if not index:
        # Corrupt / empty parse — fail-safe: no sends
        for p in prospects:
            append_send_skipped_log(
                data_base,
                run_id=current_run_id or canonical_execution_run_id(),
                email=str(p.get("email") or ""),
                skip_reason="audit_log_unreadable_or_empty_index",
                audit_classification="",
            )
        return EligibilityFilterResult(
            prospects=[],
            skipped=len(prospects),
            original_count=len(prospects),
            all_ineligible_after_filter=len(prospects) > 0,
        )

    rid_ctx = (current_run_id or "").strip()
    kept: list[dict] = []
    skipped = 0
    for p in prospects:
        email = str(p.get("email") or "")
        en = email_normalized(email)
        row_rid = str(p.get("run_id") or "").strip()
        vs = (p.get("validation_status") or "").strip().upper()
        lookup_rid = row_rid or rid_ctx

        ar = index.get((lookup_rid, en)) if lookup_rid else None
        ac = (ar.get("classification") or "").strip() if ar else ""

        if vs != "READY":
            append_send_skipped_log(
                data_base,
                run_id=rid_ctx,
                email=email,
                skip_reason="validation_status_not_READY",
                audit_classification=ac,
            )
            skipped += 1
            continue
        if not lookup_rid:
            append_send_skipped_log(
                data_base,
                run_id=rid_ctx,
                email=email,
                skip_reason="missing_run_id_on_prospect_row",
                audit_classification=ac,
            )
            skipped += 1
            continue
        if rid_ctx and row_rid and row_rid != rid_ctx:
            append_send_skipped_log(
                data_base,
                run_id=rid_ctx,
                email=email,
                skip_reason="run_id_mismatch",
                audit_classification=ac,
            )
            skipped += 1
            continue
        if not ar or (ar.get("classification") or "").strip().upper() != "ELIGIBLE":
            append_send_skipped_log(
                data_base,
                run_id=rid_ctx,
                email=email,
                skip_reason="not_ELIGIBLE_in_audit_log",
                audit_classification=ac,
            )
            skipped += 1
            continue
        kept.append(p)

    kept.sort(
        key=lambda x: (
            email_normalized(x.get("email")),
            str(x.get("run_id") or "").strip(),
        )
    )
    orig = len(prospects)
    return EligibilityFilterResult(
        prospects=kept,
        skipped=skipped,
        original_count=orig,
        all_ineligible_after_filter=orig > 0 and len(kept) == 0,
    )


def emit_no_eligible_prospects_event(*, run_id: str) -> None:
    print(
        json.dumps(
            {
                "event": "PIPELINE_NO_ELIGIBLE_PROSPECTS",
                "run_id": run_id,
                "timestamp": _utc_iso_z(),
            },
            sort_keys=True,
        ),
        flush=True,
    )
