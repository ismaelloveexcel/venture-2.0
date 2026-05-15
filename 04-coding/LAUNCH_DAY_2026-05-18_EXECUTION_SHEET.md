# Live send-off — 18 May 2026 execution sheet (operator only)

**Not technical?** Start with **`04-coding/OPERATOR_SIMPLE_GUIDE.md`** (plain steps + one command). **This file** is the detailed audit checklist for people who need every field spelled out.

**Purpose:** Run-day steps and blanks only. Doctrine: `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` (v1.12 canonical). Delta archive: `LEAD_GEN_LAUNCH_V1_12_MERGE_FRAGMENT.md` (optional).

**Execution window:** Machine-readable clock and last baseline record → `04-coding/state/launch_execution_state.json`.

---

## 0. Pre-launch execution (before 18 May)

Tick as you complete; doctrine dates in `LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` (Milestones).

- [x] Baseline green: `pytest tests -q` + `validate_repo_contract.py` + `run_daily.py bridge validate` (recorded in `launch_execution_state.json` on open).
- [x] Full-stack dry rehearsal once: `run_daily.py --generate-prospects --prospects-demo --execute-outbound --dry-run` (no send; stub messages).
- [ ] **Launch lock** (target **13 May** EOD): ICP one-liner, cohort bundle, domain/DNS, deterministic snapshot per plan.
- [ ] **Dry-run lock** (target **15 May** EOD): repeat dry path after any copy/cohort change; operator sign-off on `run_report.json` + digest.
- [ ] **Live send-off** (**18 May**): complete sections 1–7 below; no live send until checks green.

---

## 1. Names (§2.2)

| Role | Name / initials |
|------|-----------------|
| Batch operator | |
| Incident owner | |
| Reviewer (optional) | |

**Halt resumption:** Only **Incident owner** authorizes **resume** after a halt. Written: time (UTC) + reason. Solo: same person, incident-owner hat, same rule.

---

## 2. Three runtime artifacts (fill before send)

### (1) Cohort lock — intent

| Field | Value |
|-------|-------|
| `cohort_id` | |
| ICP one-liner (exact) | |
| `message_version` (e.g. git SHA) | |
| `cta_version` | |
| `send_window` | |
| `max_batch` | |

### (2) Eligibility trace — per row (export or sheet)

| email | eligible_reason | suppression_status | audit_status | sendable (Y/N) |
|-------|-----------------|--------------------|--------------|----------------|
| | | | | |

### (3) Execution log — what happened

| run_id | email | status (sent/skipped/blocked) | block_reason | timestamp (UTC) |
|--------|-------|----------------------------------|----------------|-----------------|
| | | | | |

---

## 3. Decision traceability (before you claim “compliant”)

For **each delivered** email you must be able to show **all** of:

1. Why the row existed (source + inclusion rule)  
2. Why it was eligible (flags / trace)  
3. Why it was approved (operator)  
4. Why it was sent (cohort lock + guard pass + this `run_id`)

**Any step missing → not compliant for governance claims** (fix before narrating success).

---

## 4. Pre-send cohort integrity (tick)

- [ ] Deterministic run snapshot recorded (git SHA and/or timestamped export of cohort + guards—**not** crypto purity)
- [ ] Suppression list frozen for window
- [ ] Eligibility rules version noted (can match `message_version`)
- [ ] One sample row traced: eligible → approved → sent → delivered → tracked
- [ ] Operator confirms `cohort_id` / segment matches run sheet

---

## 5. Execution steps (order)

- [ ] `.env` + Resend + `YOUR_SERVICE` OK  
- [ ] Pre-send QA: canonical subject; body contains exact `CTA_STRING`; no forbidden patterns  
- [ ] `send_outreach_test.py` → approve → confirm when batch matches lock  
- [ ] `run_daily.py --execute-outbound` **without** `--dry-run` per `OPERATOR_RUNBOOK.md`  
- [ ] Append replies to `07-kpis/reply_intent_log.csv` (frozen headers)

---

## 6. Triage (do not conflate)

| Bucket | Ask first |
|--------|-----------|
| Deliverability | Provider / domain / placement |
| Eligibility | Data / suppression / drift / snapshot |
| Copy | Subject / body / facts |

---

## 7. Invalidation = stop

On audit gap, subject/CTA drift, suppression bypass, or eligibility drift: **halt** per launch plan. **Incident owner** owns resume decision.

---

## 8. Links

- `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` (doctrine — stable)  
- `OPERATOR_RUNBOOK.md`  
- `04-coding/OPERATOR_EXECUTION_SHEET_V1.md` (days 2–14)  
