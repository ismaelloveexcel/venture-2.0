"""
Prospect gate v2.2.7 — deterministic dedup, SQLite suppression, audit log, ELIGIBLE projection.

See: 04-coding/PROSPECT_SYSTEM_V2_2_7_IMPLEMENTATION_PLAN.md
"""

from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# UTF-8, no BOM, LF only — compared as decoded strings
PROSPECT_AUDIT_HEADER = (
    "timestamp_utc,run_id,cohort_id,email,name,company_name,role,domain,"
    "validation_status,validation_reason,dedup_status,suppression_status,"
    "drop_reason,classification"
)

_DROP_PRIORITY: dict[str, int] = {
    "suppression_db_unavailable": 1,
    "hard_suppressed": 2,
    "historical_suppressed": 3,
    "validation_failed": 4,
    "dedup": 5,
}


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_name(name: str | None) -> str:
    return (name or "").strip().lower()


def normalize_domain(domain: str | None) -> str:
    return (domain or "").strip().lower()


def sanitize_run_id_fs(run_id: str) -> str:
    rid = (run_id or "").strip().lower()
    unsafe = set('\\/:*?"<>| \t\n\r')
    out = "".join("_" if c in unsafe else c for c in rid)
    return (out[:200] if out else "unknown_run")


def _utc_iso_z() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _pick_drop_reason(candidates: list[str]) -> str:
    if not candidates:
        return ""
    return min(candidates, key=lambda r: _DROP_PRIORITY.get(r, 99))


def fetch_suppression_sets(db_path: Path) -> tuple[set[str], set[str], bool]:
    """
    Returns (hard_emails_normalized, historical_emails_normalized, db_ok).
    On any failure, db_ok=False and sets are empty.
    """
    hard: set[str] = set()
    hist: set[str] = set()
    try:
        conn = sqlite3.connect(str(db_path), timeout=10)
        try:
            cur = conn.execute("SELECT email FROM suppression_list")
            for (em,) in cur.fetchall():
                n = normalize_email(str(em) if em is not None else "")
                if n:
                    hard.add(n)
            cur = conn.execute(
                """
                SELECT recipient_email FROM outbound_events
                WHERE lower(trim(status)) = 'sent'
                """
            )
            for (em,) in cur.fetchall():
                n = normalize_email(str(em) if em is not None else "")
                if n:
                    hist.add(n)
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return set(), set(), False
    return hard, hist, True


@dataclass
class GateBatchResult:
    eligible_rows: list[dict] = field(default_factory=list)
    audit_rows: list[dict] = field(default_factory=list)
    db_ok: bool = True
    input_count: int = 0


def run_prospect_gate(
    *,
    raw_rows: list[dict],
    run_id: str,
    validate_prospect_fn: Callable[[dict], tuple[str, str]],
    db_path: Path,
    cohort_id: str = "",
) -> GateBatchResult:
    """
    Pipeline: validate_prospect → dedup → suppression → classification.
    Every input row produces exactly one audit row.
    """
    hard, hist, db_ok = fetch_suppression_sets(db_path)
    seen_emails: set[str] = set()
    seen_identity: set[str] = set()
    audit_rows: list[dict] = []
    eligible: list[dict] = []

    for raw in raw_rows:
        row = dict(raw)
        row.setdefault("linkedin_url", "")
        row.setdefault("source", "unknown_source")

        val_status, val_reason = validate_prospect_fn(row)
        row["validation_status"] = val_status
        row["validation_reason"] = val_reason
        validation_pass = val_status.strip().upper() == "READY"

        email_n = normalize_email(row.get("email"))
        name_n = normalize_name(row.get("name"))
        domain_n = normalize_domain(row.get("domain"))
        identity = f"{name_n}|{domain_n}"

        dedup_fail = (bool(email_n) and email_n in seen_emails) or (
            identity in seen_identity
        )
        if not dedup_fail:
            if email_n:
                seen_emails.add(email_n)
            seen_identity.add(identity)
        dedup_status = "FAIL" if dedup_fail else "PASS"

        hard_hit = db_ok and email_n and email_n in hard
        hist_hit = db_ok and email_n and email_n in hist
        if not db_ok:
            sup_status = "UNKNOWN"
        elif hard_hit:
            sup_status = "HARD"
        elif hist_hit:
            sup_status = "HISTORICAL"
        else:
            sup_status = "PASS"

        suppression_pass = db_ok and not hard_hit and not hist_hit

        eligible_flags = validation_pass and not dedup_fail and suppression_pass
        classification = "ELIGIBLE" if eligible_flags else "DROP"

        reasons: list[str] = []
        if not db_ok:
            reasons.append("suppression_db_unavailable")
        elif hard_hit:
            reasons.append("hard_suppressed")
        elif hist_hit:
            reasons.append("historical_suppressed")
        elif not validation_pass:
            reasons.append("validation_failed")
        elif dedup_fail:
            reasons.append("dedup")

        drop_reason = _pick_drop_reason(reasons) if classification == "DROP" else ""

        audit_row = {
            "timestamp_utc": _utc_iso_z(),
            "run_id": run_id,
            "cohort_id": (cohort_id or "").strip(),
            "email": (row.get("email") or "").strip(),
            "name": (row.get("name") or "").strip(),
            "company_name": (row.get("company_name") or "").strip(),
            "role": (row.get("role") or "").strip(),
            "domain": (row.get("domain") or "").strip(),
            "validation_status": val_status,
            "validation_reason": val_reason,
            "dedup_status": dedup_status,
            "suppression_status": sup_status,
            "drop_reason": drop_reason,
            "classification": classification,
        }
        audit_rows.append(audit_row)

        if classification == "ELIGIBLE":
            row["run_id"] = run_id
            eligible.append(row)

    audit_rows.sort(key=lambda r: (r["run_id"], normalize_email(r.get("email"))))
    return GateBatchResult(
        eligible_rows=eligible,
        audit_rows=audit_rows,
        db_ok=db_ok,
        input_count=len(raw_rows),
    )


def append_prospect_audit_log(data_base: Path, rows: list[dict]) -> None:
    path = data_base / "07-kpis" / "prospect_audit_log.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = PROSPECT_AUDIT_HEADER.split(",")

    if path.is_file():
        first = path.read_text(encoding="utf-8").splitlines()[:1]
        got = (first[0].strip() if first else "").replace("\r\n", "\n")
        want = PROSPECT_AUDIT_HEADER.strip()
        if got != want:
            raise ValueError(
                "prospect_audit_log.csv header mismatch — cannot append safely.\n"
                f"  Expected (exact): {want!r}\n"
                f"  Found:            {got!r}\n"
                "  Fix: rename/remove the file to recreate with canonical header, or align header."
            )

    mode = "a" if path.is_file() else "w"
    with path.open(mode, newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        if mode == "w":
            w.writeheader()
        for r in rows:
            w.writerow({k: (r.get(k) or "") for k in fieldnames})


def write_eligible_prospects_csv(
    path: Path, rows: list[dict], fieldnames: list[str]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            out = {k: (r.get(k) or "") for k in fieldnames}
            out["validation_status"] = "READY"
            out["email"] = normalize_email(out.get("email"))
            w.writerow(out)


def verify_gate_eligible_audit_parity(
    *,
    eligible_rows: list[dict],
    audit_rows: list[dict],
    run_id: str,
) -> list[str]:
    """
    In-memory invariant: ELIGIBLE audit rows for this run match eligible_rows emails (normalized).
    Call before append_prospect_audit_log so a failed run does not poison the audit file.
    """
    rid = (run_id or "").strip()
    errs: list[str] = []
    e_emails = sorted(
        {normalize_email(r.get("email")) for r in eligible_rows if normalize_email(r.get("email"))}
    )
    a_elig = [
        r
        for r in audit_rows
        if (r.get("classification") or "").strip().upper() == "ELIGIBLE"
        and (r.get("run_id") or "").strip() == rid
    ]
    a_emails = sorted(
        {normalize_email(r.get("email")) for r in a_elig if normalize_email(r.get("email"))}
    )
    if e_emails != a_emails:
        only_e = sorted(set(e_emails) - set(a_emails))[:8]
        only_a = sorted(set(a_emails) - set(e_emails))[:8]
        errs.append(
            f"eligible_vs_audit_ELIGIBLE_email_mismatch only_eligible={only_e!r} only_audit={only_a!r}"
        )
    if len(eligible_rows) != len(a_elig):
        errs.append(
            f"eligible_vs_audit_ELIGIBLE_row_count eligible={len(eligible_rows)} audit_ELIGIBLE={len(a_elig)}"
        )
    return errs


def verify_written_eligible_prospects_csv(
    path: Path,
    *,
    eligible_rows: list[dict],
    run_id: str,
    fieldnames: list[str],
) -> list[str]:
    """After write: CSV READY rows for run_id match eligible_rows (normalized emails + counts)."""
    rid = (run_id or "").strip()
    errs: list[str] = []
    if not path.is_file():
        return [f"prospects_csv_missing:{path}"]
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header_fields = list(reader.fieldnames or ())
        rows = list(reader)
    want = sorted(
        {normalize_email(r.get("email")) for r in eligible_rows if normalize_email(r.get("email"))}
    )
    got_rows = [
        r
        for r in rows
        if (r.get("validation_status") or "").strip().upper() == "READY"
        and (r.get("run_id") or "").strip() == rid
    ]
    got = sorted(
        {normalize_email(r.get("email")) for r in got_rows if normalize_email(r.get("email"))}
    )
    if want != got:
        errs.append(
            f"csv_round_trip_email_mismatch want_vs_got extra_in_csv={sorted(set(got)-set(want))[:5]!r}"
        )
    if len(eligible_rows) != len(got_rows):
        errs.append(
            f"csv_round_trip_row_count eligible={len(eligible_rows)} csv_READY_for_run={len(got_rows)}"
        )
    cols = set(header_fields)
    missing = [c for c in fieldnames if c not in cols]
    if missing:
        errs.append(f"csv_missing_columns:{missing}")
    return errs


def write_prospect_generation_digest(
    data_base: Path,
    *,
    run_id: str,
    payload: dict[str, Any],
) -> Path:
    """Append-only audit companion: one JSON per run_id for operator / run_report merge."""
    rid_fs = sanitize_run_id_fs(run_id)
    d = data_base / "07-kpis" / "prospect_generation_digest"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rid_fs}.json"
    body = {
        "timestamp_utc": _utc_iso_z(),
        "run_id": run_id,
        **payload,
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True), encoding="utf-8")
    return path


def run_strict_forensic_checks(
    *,
    audit_rows: list[dict],
    eligible_rows: list[dict],
    run_id: str,
) -> dict[str, Any]:
    """Post-execution integrity checks only; never mutates data."""
    violations: list[dict[str, Any]] = []

    def add_v(t: str, count: int, examples: list[Any]) -> None:
        violations.append({"type": t, "count": count, "examples": examples[:5]})

    # Every audit row has classification + drop_reason rules
    bad_class = [r for r in audit_rows if r.get("classification") not in ("ELIGIBLE", "DROP")]
    if bad_class:
        add_v("schema_violation", len(bad_class), bad_class)

    drop_missing = [
        r
        for r in audit_rows
        if r.get("classification") == "DROP" and not (r.get("drop_reason") or "").strip()
    ]
    if drop_missing:
        add_v("validation_gap", len(drop_missing), drop_missing)

    ne = [
        normalize_email(r.get("email"))
        for r in eligible_rows
        if normalize_email(r.get("email"))
    ]
    if len(ne) != len(set(ne)):
        add_v("dedup_anomaly", 1, ["eligible duplicate email_normalized"])

    for r in eligible_rows:
        if (r.get("validation_status") or "").strip().upper() != "READY":
            add_v("validation_gap", 1, [r])
            break

    for r in audit_rows:
        if r.get("classification") == "ELIGIBLE" and (
            r.get("validation_status") or ""
        ).strip().upper() != "READY":
            add_v("suppression_mismatch", 1, [r])
            break

    parity = verify_gate_eligible_audit_parity(
        eligible_rows=eligible_rows, audit_rows=audit_rows, run_id=run_id
    )
    if parity:
        add_v("eligible_audit_parity_fail", len(parity), parity)

    ok = sum(1 for v in violations if v.get("count", 0) > 0) == 0
    summary = {
        "run_id": run_id,
        "run_id_fs": sanitize_run_id_fs(run_id),
        "strict_mode_enabled": True,
        "violations": violations,
        "total_rows_checked": len(audit_rows),
        "timestamp_utc": _utc_iso_z(),
        "strict_ok": ok,
    }
    return summary


def write_strict_mode_summary(data_base: Path, summary: dict[str, Any]) -> Path:
    rid_fs = summary.get("run_id_fs") or sanitize_run_id_fs(str(summary.get("run_id", "")))
    d = data_base / "07-kpis" / "strict_mode_summary"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rid_fs}.json"
    path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return path
