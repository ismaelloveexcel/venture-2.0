# v1.12 consolidation — delta archive

**Superseded for reading by** `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` **(v1.12 canonical).** Retain this file for git history / diff only; do not treat as a parallel source of truth.

Below: original **merge instructions** and block text used to assemble the canonical plan.

---

## A. Version

Set document title to: **`(v1.12)`**.

---

## B. Replace “Cohort reproducibility fingerprint” block with the following

### Deterministic run snapshot (capture discipline)

Goal is **reconstructability**, not cryptographic purity. At launch lock, record **any** defensible combination of:

- `git rev-parse --short HEAD` (or tag) for message / guard code  
- **Timestamped** note or export of `batch_guard` subject + CTA + caps  
- **Frozen JSON or CSV copy** of cohort inputs (prospects slice, suppression list) **or** file hash + export time  
- **Operator + freeze time** (ISO-8601 UTC)

**Optional extended row** (if cheap—still not mandatory for Batch 1):

| Field | Example |
|-------|---------|
| `prospect_source_snapshot` | hash or export timestamp |
| `suppression_snapshot` | hash or timestamp |
| `eligibility_rule_version` | same as `message_version` if gates ship in repo |

### Execution state model (governance vocabulary)

| State | Meaning |
|-------|---------|
| **eligible** | Passed deterministic filters (**system**). Shipped paths may label **ELIGIBLE** / READY—same idea. |
| **approved** | **Human** explicitly authorized this row for send (Batch 1: no row bypasses this). |
| **sent** | Handed to provider / send path (**may** collapse with **delivered** in tooling if you only log 2xx). |
| **delivered** | Provider accepted (**Resend 2xx**); §0 **Delivered**. |
| **tracked** | Reply/outcome per `07-kpis/reply_intent_log` + runbook (see canonical plan §0 / doc map) |

**Audit chain:** **eligible → approved → sent → delivered → tracked response.** If tooling merges steps, **write which steps are merged** on the run sheet.

**Rules:** **eligible ≠ approved**; **no send without approved**; triage **sent vs delivered** under **Operational separation** (§5).

### Runtime artifacts (execution collapse)

At **run time**, doctrine reduces to **three** artifacts (file, sheet, or repo paths). Everything else is **scaffolding**.

**(1) Cohort lock** — `cohort_id`, ICP one-liner, `message_version`, `cta_version`, `send_window`, `max_batch`

**(2) Eligibility trace** — per row: `email`, `eligible_reason`, `suppression_status`, `audit_status`, `sendable` (Y/N)

**(3) Execution log** — `run_id`, `email`, `status` (sent/skipped/blocked), `block_reason`, `timestamp`

### Decision traceability rule (audit-grade bar)

For **any delivered** email, reconstruct **all** of:

1. Why the row existed — source + inclusion rule  
2. Why it was eligible — deterministic flags  
3. Why it was approved — named operator action  
4. Why it was sent — cohort lock + guard pass + batch identity for that `run_id`

If **any** step is missing → **not compliant** for governance claims until fixed—**regardless** of delivery success.

### Runtime primitives (ship bar)

Only these must be **real** at Batch 1: **cohort lock**, **eligibility row table**, **execution log**, **invalidation rules** (Pre send-off). All other sections are explanatory.

---

## C. Launch lock row — wording

Use **deterministic run snapshot** (not “cryptographic fingerprint”). Note: **capture discipline**, not crypto purity.

---

## D. Live send-off milestone — add pointer

`04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md`

---

## E. §2.2 — add after solo-team paragraph

**Halt resumption:** Only the **Incident owner** may authorize **resuming** after a **halt** triggered under execution invalidation. That decision must be **written** (UTC timestamp + reason) in the incident log. The batch operator (or any other role) does **not** un-halt without incident owner sign-off. **Solo team:** one person holds both hats—still record an explicit **“resume”** entry when changing state.

---

## F. Pre send-off vs §4 — add one line each

**Pre send-off checklist intro:**  
**Pre send-off** = validation criteria and doctrine (what must be true). **§4 Execution checklist** = ordered operator steps (what to do). Criteria live up top; **do not** mentally duplicate the same QA twice—execute checks once in §4 against bars already defined in Pre send-off.

**§4 Execution checklist intro (first line after heading):**  
**Scope:** step-by-step commands and tickboxes. Template / copy **pass-fail** criteria: Pre send-off §2 Outreach; here verify execution-time gates only.

---

## G. §0 Delivered row — align wording

**Delivered:** Provider 2xx; equals **delivered** in the execution state model (doc top). (Remove standalone “executed” label if you had it, or define `executed` := **delivered** for Batch 1.)

---

## H. Cohort & gate bullet — wording

Record **deterministic run snapshot** + execution state model (doc top). Run sheet: **eligible** vs **approved** vs **sent** / **delivered** / **tracked**.

---

## I. §9 reviewer synthesis — append

**v1.12 additions:** **Deterministic run snapshot** (replaces crypto-forward “fingerprint” wording); **runtime artifacts** (3-file collapse); **decision traceability rule**; state chain **eligible → approved → sent → delivered → tracked**; **incident owner only** resumes halt; **Pre send-off vs §4** separation; day-of **`LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md`**.
