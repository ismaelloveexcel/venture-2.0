# Lead-gen product — launch roadmap & execution plan (v1.12 canonical)

### Active documents (navigation — under stress, use this order)

1. **Canonical plan (this file)** → system truth: doctrine, state model, invalidation, traceability bars.  
2. **Execution sheet** → `04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` — live run: tickboxes, blanks, day-of only.  
3. **Runbook** → `OPERATOR_RUNBOOK.md` — procedure: commands, paths, approvals, ongoing ops.

**This document does NOT contain** operational step-by-step for live send-off, CLI sequences, or day-of execution instructions — those live in the execution sheet and runbook only.

**Read this file for:** doctrine, structure, cohort model, traceability, invalidation doctrine.  
**Procedure (commands, paths, approvals):** `OPERATOR_RUNBOOK.md`.

`LEAD_GEN_LAUNCH_V1_12_MERGE_FRAGMENT.md` is **archival** (delta used to assemble this doc). **Do not** use it as a fallback authority—if anything disagrees with this file, **this file wins**.

---

## Three-plane architecture (authority)

| Plane | File | Purpose | Stability |
|-------|------|---------|-----------|
| **Execution** | `LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` | What do I do today (live send-off) | Volatile |
| **Procedure** | `OPERATOR_RUNBOOK.md` | How do I operate the repo / CLI | Semi-stable |
| **System / doctrine** | *this file* | What the system is; bars for compliance | Stable |

**Rule:** No overlap — execution sheet stays **runtime only**; runbook stays **procedure**; this plan stays **doctrine + structure** only.

---

## Milestones (calendar)

| Milestone | When | Pointer |
|-----------|------|---------|
| Launch lock | Wed **13 May 2026** EOD | ICP + terminology + **deterministic run snapshot** + cohort bundle recorded |
| Dry-run | Fri **15 May 2026** EOD | `run_daily.py` dry path green; evidence frame for Loom/landing if used |
| Live send-off | Mon **18 May 2026** | `LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` + `OPERATOR_RUNBOOK.md` |
| 14-day window | 18–31 May 2026 | `04-coding/OPERATOR_EXECUTION_SHEET_V1.md` |

**Live send-off CLI:** `04-coding/scripts/run_daily.py` per `AGENTS.md`. First wedge = **controlled outbound execution** (not commodity volume).

---

## §0. Metric anchor

| Term | Definition |
|------|------------|
| **Delivered** | Provider accepted send (Resend 2xx); not “queued intent.” Same as **delivered** in the execution state model below. |

Strict vs broad reply taxonomy and CSV headers: `07-kpis/reply_intent_log.template.csv` and `OPERATOR_RUNBOOK.md`.

---

## §2. Positioning & terminology

**We:** **Controlled outbound execution system** — eligibility enforcement, frozen cohort, caps, append-only audit, operator sign-off at the edge.

**Not:** Commodity lead lists, “AI SDR” blasters, or **lead gen agency** phrasing in live copy (`batch_guard` patterns).

### §2.1 Canonical terminology (freeze at launch lock)

| Layer | Phrase | Use |
|-------|--------|-----|
| Internal | *lead-gen* (paths / filename) | Repo shorthand — not hero copy |
| External category | **Outbound governance** | Decks, one-liners |
| Functional | **Controlled outbound execution system** | Product detail, demos |

**Canonical eligibility sentence:**  
Every outbound row must pass **deterministic eligibility checks**, be recorded in an **append-only audit log**, and receive **explicit operator approval** before **execution**.

Do **not** use customer-facing **“intelligence layer.”** Prefer execution layer, governance layer, eligibility gating.

### §2.2 Operator accountability

| Role | Responsibility |
|------|----------------|
| **Batch operator** | Final row-level approval before send |
| **Incident owner** | Halt authority; incident log until resolved |
| **Reviewer (optional)** | Second read on sample / sensitive slice |

**Halt resumption:** Only the **Incident owner** authorizes **resuming** after a halt under invalidation doctrine. Decision must be **written** (UTC timestamp + reason). No other role un-halts without that sign-off. **Solo:** same person — explicit **“resume”** log entry when changing state.

### §2.3 ICP sharpness (mandatory)

One **defensible** segment; two operators should not disagree on row membership. If they would → ICP too broad.

### §2.4 Customer-facing surfaces (alignment)

- **Static landing draft:** `04-coding/boilerplates/landing-page/index.html` — evidence-first, **no** fabricated dashboards or predictive claims; hero ICP must be replaced at **launch lock** (§2.3) so the page is not reusable generic “B2B.” Every visible claim must map to shipped CLI + file artifacts (`run_report.json`, audit/skip logs, `run_daily.py` path per `OPERATOR_RUNBOOK.md`).
- **Local operator console:** `04-coding/scripts/dashboard.html` — **governed outbound console** (local); not a standalone analytics product. If shown externally, it must not imply intelligence or autopilot not implemented in repo.

If copy outruns implementation: **reduce the copy** — never inflate the system.

**Semantic contract (interpretation guardrails):** `docs/SEMANTIC_CONTRACT.md` — category stability lock (§§1–8): prevents drift into agency / reporting / automation / generic AI outbound tool; ties landing **ICP latch** (`§8.2`) to contract checks.

---

## §3. Cohort, snapshot, state, runtime collapse

### Cohort version bundle (record at lock)

| Field | Example |
|-------|---------|
| `cohort_id` | `lg-2026-05-18-a` |
| `segment_name` | (vertical slice) |
| `message_version` | `git rev-parse --short HEAD` |
| `cta_version` | `batch_guard.CTA_STRING` as deployed |
| `send_window` | e.g. `2026-05-18T08:00Z`–`18:00Z` |

Each orchestrated run also persists **`run_report.json` → `outbound.cohort_metadata`**: `git_sha`, guard/generator file hashes, **`freeze_timestamp_utc`** (when the cohort metadata was built), and **`subject_cta_fingerprint`** (first 12 hex chars of SHA-256 over canonical subject + CTA from `batch_guard.py`) so policy drift is checkable against what was frozen for that run.

### Deterministic run snapshot (capture discipline)

Goal: **reconstructability**, not cryptographic purity. At launch lock, record **any** defensible mix of: git SHA for guards/template; timestamped export of subject/CTA/caps; frozen CSV/JSON of prospects + suppression or hash + time; operator + freeze time (ISO-8601 UTC).

Optional: `prospect_source_snapshot`, `suppression_snapshot`, `eligibility_rule_version` (may match `message_version`).

### Execution state model

| State | Meaning |
|-------|---------|
| **eligible** | System deterministic pass (may show as ELIGIBLE/READY in tooling) |
| **approved** | Human authorized row (Batch 1: no bypass) |
| **sent** | Handed to provider (may merge with delivered in logs) |
| **delivered** | Provider 2xx |
| **tracked** | Reply/outcome logged post-send per `07-kpis/reply_intent_log.template.csv` and `OPERATOR_RUNBOOK.md` |

**Chain:** eligible → approved → sent → delivered → tracked. If steps merge in tooling, **document merges** on the run sheet.

### Runtime artifacts (everything collapses here)

**(1) Cohort lock** — `cohort_id`, ICP one-liner, `message_version`, `cta_version`, `send_window`, `max_batch`  
**(2) Eligibility trace** — per row: `email`, `eligible_reason`, `suppression_status`, `audit_status`, `sendable` (Y/N)  
**(3) Execution log** — `run_id`, `email`, `status` (sent/skipped/blocked), `block_reason`, `timestamp`

### Decision traceability rule

For **any delivered** email, reconstruct: (1) why row existed — source + inclusion rule; (2) why eligible — flags; (3) why approved — operator; (4) why sent — cohort lock + guard pass + `run_id`. **Any step missing → not compliant** for governance claims until fixed.

### Runtime primitives (ship bar)

**Cohort lock**, **eligibility row table**, **execution log**, **invalidation rules** (below) must be real. Other narrative in older notes is **scaffolding**.

---

## §4. Pre send-off vs execution checklist (separation)

- **Pre send-off** (prep phase): validation criteria — what must be true before live send.  
- **Execution** (live day): **only** `LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` — ordered steps and blanks.  
- **§4 in this doc:** no duplicate tickbox list; doctrine only.

Template/copy pass-fail criteria belong in prep; **execution-time** verification runs against those bars once, on the sheet.

---

## §5. Operational separation & invalidation

### Triage (never conflate)

| Bucket | Nature |
|--------|--------|
| Deliverability | Provider / domain / placement |
| Eligibility | Data / suppression / drift / snapshot |
| Copy | Subject / body / facts |

### Invalidation doctrine (hard stops)

| Condition | Action |
|-----------|--------|
| Audit gap (delivered without audit row) | Immediate halt; incident |
| Subject ≠ `CANONICAL_SUBJECT` | Halt |
| Body ≠ `CTA_STRING` / forbidden fired | Halt |
| Suppression bypass | Halt + incident log |
| Complaints over threshold | Pause + review |
| Unverifiable claim in body | Remove row |
| Outside frozen `send_window` / `cohort_id` | Pause + re-approve |
| Eligibility drift after lock | Pause batch + re-approve cohort |

Resume only per **§2.2** (Incident owner, written).

---

## §6. Scope guard

Batch 1: only what is **implemented, auditable, operator-verified**. No unproven ML, no category vapor in outbound.

**Anti-overengineering:** If it does not change **eligibility**, **audit traceability**, or **send safety**, it is **out** of Batch 1 scope.

---

## Doc map

| Asset | Role |
|-------|------|
| `AGENTS.md` | Agent / CLI contract |
| `04-coding/FOUNDER_WHERE_WE_ARE.md` | Founder: goals vs shipped vs best use of pre-launch days |
| `04-coding/LEAD_GEN_SYSTEM_V1_4_EXECUTION_CONTRACT.md` | Technical execution contract |
| `04-coding/OPERATOR_SIMPLE_GUIDE.md` | **Non-technical operator:** minimal steps, plain language |
| `04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` | Live send-off runtime (detailed audit checklist) |
| `04-coding/LEAD_GEN_LAUNCH_V1_12_MERGE_FRAGMENT.md` | v1.12 delta archive |
| `04-coding/reports/PRE_LAUNCH_READINESS_QA.md` | Honest bar: revenue + inbox expectations (pre-launch) |
| `04-coding/reports/OUTREACH_REVIEW_PACK.md` | Prospect list pointers + sample email + test-send commands |
| `07-kpis/reply_intent_log.template.csv` | Reply CSV schema |

---

## Reviewer note (v1.12 canonical)

Assembled from **`LEAD_GEN_LAUNCH_V1_12_MERGE_FRAGMENT.md`**: deterministic run snapshot; runtime collapse; decision traceability; state chain; incident-owner halt resume; pre-send vs execution separation; operational triage. **No further doctrine expansion** — implementation discipline only from here.

**Version freeze:** **v1.12** is frozen as the canonical doctrine surface. Future changes must be **explicit deltas** (new section, dated addendum, or version bump with changelog)—**not** silent inline rewrites that blur what shipped for Batch 1.
