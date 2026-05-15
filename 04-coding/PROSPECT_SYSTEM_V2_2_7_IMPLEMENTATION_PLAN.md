# Prospect System v2.2.7 — Implementation Plan (Canonical)

**Status (2026-05-11):** Core gate + audit append + `DATA_BASE` resolver + forensic `STRICT_PROSPECT_MODE` are implemented (`prospect_gate.py`, `prospect_builder.py`, `runtime_config.py`, `message_generator_solo.py`, `venture_pipeline.py`). Optional LLM enrichment metadata is not implemented (still off by default in spec).

This document is the **canonical implementation contract** for the prospect filtering subsystem. It aligns with the frozen spec chain (v2.2.5–v2.2.7): deterministic gates, SQLite suppression authority, audit as system of record, `DATA_BASE`-scoped artifacts, forensic strict mode, and shared root resolution.

**Non-goals:** outbound send kernel changes; third-party deliverability APIs; async/streaming ingestion unless explicitly added later.

---

## 0) Scope

### In scope

- Prospect intake → normalization → **fixed pipeline order**:
  1. `validate_prospect()` (authoritative; black box)
  2. Dedup (exact, normalized; OR rule)
  3. Suppression (SQLite)
  4. Classification + `drop_reason` (precedence for labeling only)
  5. Append-only audit
  6. Emit **ELIGIBLE-only** `prospects.csv` (strict projection of audit)

- **Suppression (SQLite)**  
  - **Hard:** `suppression_list` (opt-out / do-not-contact)  
  - **Historical:** `outbound_events.recipient_email` where `status = 'sent'` only (exclude `dry_run`, failed, queued, etc.)  
  - Comparisons use canonical normalization on **both** sides.

- **SQLite unavailable:** all rows `classification = DROP`, `suppression_status = UNKNOWN`, `drop_reason = suppression_db_unavailable`; validation + dedup logic still run for auditability; audit still written; **empty ELIGIBLE list**; **`prospect_builder` exit code 0** (per frozen contract).  
  - **Operator / monitoring:** exit `0` must **not** be interpreted as “healthy batch.” Treat **all rows DROP + UNKNOWN suppression** as a **critical operational signal** (dashboards, runbook, `run_report.json` reasons).

- **Optional LLM:** metadata only; invalid output ignored; **never** affects eligibility.

- **`STRICT_PROSPECT_MODE`:** post-execution integrity only; **never** mutates eligibility, `prospects.csv`, or audit rows; **always exit 0** when strict checks run; writes `strict_mode_summary` + console line.

### Out of scope

- Changes to `venture_pipeline.py` send path / Resend integration beyond what already gates sends.

---

## 1) Single root — `DATA_BASE` (Option B, mandatory first)

### Invariant

> All prospect subsystem inputs, outputs, logs, and audit artifacts for a run resolve under **one** canonical base: **`DATA_BASE`**, identical to the existing pipeline definition (`VENTURE_CLIENT_WORKSPACE` → client root; else `REPO_ROOT`). **No mixed-root writes** within a single `run_id`.

### Tasks

1. Introduce or consolidate **`resolve_data_base()`** in a **neutral** module (`runtime_config.py` or a small `paths.py`). **Do not** duplicate `os.getenv("VENTURE_CLIENT_WORKSPACE")` logic in multiple places.
2. **`venture_pipeline.py`** and **`prospect_builder.py`** must call **only** that resolver for prospect-related paths (no importing `venture_pipeline` from `prospect_builder` to avoid cycles).
3. Build paths with **`pathlib.Path`** (no string concatenation), e.g.:
   - `DATA_BASE / "06-sales" / "prospects.csv"`
   - `DATA_BASE / "07-kpis" / "prospect_audit_log.csv"`
   - `DATA_BASE / "07-kpis" / "strict_mode_summary" / f"{run_id_fs}.json"`

### Acceptance

- Repo grep: a single authoritative `DATA_BASE` resolution path for prospect code; no second “almost identical” resolver.

---

## 2) Normalization (global)

```text
email_normalized   = lower(trim(email or ""))
name_normalized    = lower(trim(name or ""))
domain_normalized  = lower(trim(domain or ""))
```

**Rule:** No raw `email` / `name` / `domain` string comparisons in prospect-stage gating logic.

---

## 3) Pipeline gates (execution order — authoritative)

1. **`validate_prospect()`** — `validation_passed` iff return value is **`READY`** (REVIEW/REJECT = fail).
2. **Dedup** — DROP if `email_normalized` already seen **OR** `(name_normalized + "|" + domain_normalized)` already seen (OR rule).
3. **Suppression** — SQLite checks after normalization on both sides.

**Classification**

- `ELIGIBLE` iff `validation_passed` AND dedup passed AND suppression passed.  
- Else `DROP`.

---

## 4) `drop_reason` precedence (labeling only)

When **multiple** failure conditions apply to one prospect, record **exactly one** `drop_reason` using this order (**first match wins**):

1. `suppression_db_unavailable`
2. `hard_suppressed`
3. `historical_suppressed`
4. `validation_failed`
5. `dedup`

> Precedence applies **only at audit-record construction**, not to reorder gate execution.

---

## 5) Audit system of record

### File

- `DATA_BASE / "07-kpis" / "prospect_audit_log.csv"` — append-only.

### Schema

- Canonical header: **UTF-8, no BOM, `\n` newlines**; header match on **decoded strings** (not raw bytes) to avoid OS newline false failures.
- **On header/schema mismatch:** **HALT** with an **operator-friendly** message (what file, what was expected vs found, how to fix).

### Write semantics

- Sort before append: **`(run_id, email_normalized)`** (stable secondary keys optional).
- Every input row must appear in audit for that `run_id` with final `classification` and statuses.

### `prospects.csv` (execution feed)

- **Strict projection:** rows where `classification == ELIGIBLE` only; every emitted row has `validation_status = "READY"`.
- **Invariant:** every row in `prospects.csv` exists in audit for the same `run_id`.

---

## 6) `run_id` and filesystem paths

- **`run_id`** is canonical in JSON and audit.
- **`run_id_fs`:** deterministic `sanitize(run_id)` for filenames (unsafe chars → `_`, etc.).
- Strict summary path: `DATA_BASE / "07-kpis" / "strict_mode_summary" / f"{run_id_fs}.json"` with both `run_id` and `run_id_fs` inside the JSON.

---

## 7) `STRICT_PROSPECT_MODE` (forensic only)

- Does **not** change eligibility, CSV, audit, or suppression behavior.
- When enabled: run post-hoc checks; write **`strict_mode_summary`**; print compact console line (`STRICT_MODE: OK | violations=0` or `STRICT_MODE: VIOLATIONS DETECTED | count=N`).
- **Always exit 0** for the strict phase when invoked as specified.
- **`violations[].type`:** JSON type `string`; documented examples are non-enforcing.
- **Artifact presence:** when strict mode is enabled, **always** write `strict_mode_summary` (even for empty input or all-DROP batches) so CI and operators never depend on “file missing means OK.”

---

## 8) Optional LLM enrichment

- Env-flag **off** by default.
- On failure / invalid JSON: ignore; do not DROP; do not change `ELIGIBLE`.

---

## 9) Integration

- Wire through **`run_daily.py`** + **`prospect_builder.py`** (canonical operator path per `AGENTS.md`).
- Align `run_report.json` `prospect_batch` fields with new semantics (especially: **DB outage + exit 0** must be visible in reasons/metrics, not only exit code).

- **Legacy:** remove or replace prior **`STRICT_PROSPECT_MODE` fail-fast** in `prospect_builder` so it matches forensic-only semantics; update tests.

---

## 10) Test matrix (minimum)

| Area | Cases |
|------|--------|
| Normalization | `None`, empty, whitespace, mixed case |
| Dedup | email dup; identity dup; OR rule |
| Suppression | hard; historical (`sent` only); neither |
| DB unavailable | all DROP, UNKNOWN, audit written, empty `prospects.csv`, exit 0 + report signal |
| Precedence | table-driven multi-failure → single `drop_reason` |
| Audit | append-only; sort key; header mismatch → HALT with clear message |
| Projection | `prospects.csv` ⊆ audit; all READY |
| Strict | summary always written when enabled; violations possible; exit 0; no mutation |
| LLM optional | garbage output does not change eligibility |

---

## 11) CI / repo hygiene

- Contract or grep check: no duplicate `VENTURE_CLIENT_WORKSPACE` / `DATA_BASE` resolution outside the neutral module.
- Optional: forbid string-concat paths in prospect modules (lint or simple script).

---

## 12) Rollout

1. Land resolver + path alignment first (no behavior change if gated behind feature flag, else coordinate with team).
2. Land audit + projection + suppression + tests.
3. Land strict forensic package + update operator docs for **DB outage visibility** and **strict summary path**.
4. Full `pytest tests -q` + `validate_repo_contract.py` before merge.

---

## 13) Definition of done

- Single `DATA_BASE` tree per run; no mixed-root writes.
- Audit is canonical; `prospects.csv` is ELIGIBLE-only projection.
- SQLite suppression rules + normalization locked; historical = `sent` only.
- Drop-reason precedence deterministic; strict mode forensic-only with pinned artifacts.
- Tests + contract validator green.

---

## Reference

- Operator flow: `OPERATOR_RUNBOOK.md`
- Agent contract: `AGENTS.md`
- Related contract notes: `04-coding/LEAD_GEN_SYSTEM_V1_4_EXECUTION_CONTRACT.md` (Phase 4 / strict prospect context)
