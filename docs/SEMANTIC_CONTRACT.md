# Semantic contract layer (Venture OS)

**Category stability lock.** This file defines **meaning**, not features. It is a **constraint system** for language and interpretation across the repo — not marketing copy, not a narrative pitch, and not a place to invent new capabilities.

**Authority:** `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` is canonical doctrine for product truth. If doctrine and this contract ever disagree, **the launch plan wins**; then **update this contract** so they match.

**Referenced by:** `04-coding/boilerplates/landing-page/index.html`, `04-coding/scripts/dashboard.html`, `OPERATOR_RUNBOOK.md`, `AGENTS.md`, headers/comments on `run_daily.py` / `venture_pipeline.py`, and CI via `validate_repo_contract.py` where applicable.

---

## 1. System definition (tight, non-marketing)

This repository implements a:

- **Controlled outbound execution system** — outbound runs as **constrained batches** under explicit rules, not as open-ended “campaign growth.”
- **Governed message delivery system** — a message is not “sent by the product”; it is **released** only after eligibility, audit, and **operator approval** align with a **fixed cohort policy** for that run.
- **Eligibility + audit + approval constrained execution layer** — the product category is **governance of execution conditions**, not content generation volume, not lead buying, not autonomous outreach.

Do **not** describe it as: AI growth tool, AI SDR, lead generation platform, marketing automation system, or “revenue engine” software.

---

## 2. What the system **is** (non-negotiable)

The following must remain true in **documentation, UI labels, CLI help, and external copy**:

- **Eligibility gating before send** — deterministic readiness/suppression rules; non-eligible rows do not reach send.
- **Append-only audit trail of outbound decisions** — decisions are recorded so a row’s path is reconstructable (see launch plan §3).
- **Operator approval requirement before execution** — no bypass of human sign-off for governed live sends.
- **Fixed cohort-based execution windows** — subject/CTA/cohort policy frozen per lock; drift requires explicit version bump and operator acknowledgment (see launch plan).
- **Constrained outbound batch execution** — caps and no-send-by-default posture over raw throughput.
- **Traceable delivery state chain** (conceptual bar; tooling may merge states if documented):  
  **eligible → approved → sent → delivered → tracked**

---

## 3. What the system **is not** (enforceable reinterpretations)

The following reinterpretations are **forbidden**. If a surface implies them, that surface is **wrong** — fix the surface.

| Forbidden category | Examples of excluded meaning |
|--------------------|-------------------------------|
| AI SDR replacement | “Our AI does outbound for you,” autonomous sequences as the product. |
| Autonomous outreach engine | Autopilot send, “set and forget,” hands-off live delivery. |
| Lead scoring / predictive intent (money path) | Invisible ranking, “best time to send,” “intent signals” as shipped outbound truth. |
| Growth hacking / funnel optimization platform | Pipeline velocity heroics, A/B trust experiments on day one, “10x replies.” |
| Analytics or dashboard product category | Charts as the product; “BI for outbound” positioning. KPI views are **telemetry aids**, not the category. |
| Marketing automation suite | Drip builders, nurture trees, multi-channel campaign orchestration as the core story. |

This section is **normative**: it defines excluded meaning for the **Venture OS outbound governance slice** of the repo, not polite guidance.

---

## 4. Naming and language rules

### 4.1 Allowed external phrases (buyer-safe family)

Use any subset that stays true to shipped behavior:

- Outbound governance system  
- Controlled outbound execution system  
- Eligibility-gated outbound  
- Operator-reviewed sending system  
- Audit-traceable outbound system  
- Governed outbound console (for **local** operator UI only — not a standalone SaaS category)

### 4.2 Forbidden phrases (external / hero / dashboard headers)

Do **not** use in customer-facing or operator-primary surfaces:

- AI-powered outreach  
- AI SDR  
- Intelligent lead generation  
- Revenue engine  
- Growth automation  
- Signal-based targeting (as a **shipped** outbound claim)  
- Autonomous sending system  
- “Intelligence layer” (see launch plan §2.1)  
- Pipeline velocity / fake performance dashboards as proof  

**Internal** filenames and paths may retain `lead-gen` shorthand per launch plan §2.1 — never as **hero** positioning.

---

## 5. Cross-surface enforcement rules

This contract governs **meaning** on:

- Landing page copy and structure  
- Dashboard labels and helper text  
- CLI stdout/stderr and user-facing errors where they categorize the product  
- Runbook and execution-sheet instructions where they categorize the product  
- Logs and reports **only where narrative text** describes the system category (factual field names are exempt)

**Rule:** If any surface **conflicts** with this contract or with `LEAD_GEN_PRODUCT_LAUNCH_PLAN.md`, **the contract + launch plan override** — the surface must change. You do not “reinterpret” the contract to match convenient copy.

---

## 6. Drift prevention rule

If a contributor, operator note, or agent introduces terminology **inconsistent** with §§1–4 (e.g. “AI SDR,” “autonomous pipeline,” “intent engine” as descriptive of this system), treat it as a **semantic regression**: it must be **corrected before merge** (or before send, if outside git).

Silent acceptance of mismatched language is a **governance failure** — same class as audit gaps, not a documentation nit.

---

## 7. Tone constraint on this document

This file must remain:

- **Precise** — definitional, testable claims.  
- **Non-marketing** — no superlatives, no “vision,” no inspiration.  
- **Non-vague** — no “we help you succeed” without mechanical meaning.  
- **Non-expansive** — no new features, no roadmap, no “could also mean.”

If a sentence could apply unchanged to a generic SaaS startup, **delete it**.

---

## 8. Operational bindings (machine checks and prose)

### 8.1 Production vs diagnostic CLI

| Role | Entry |
|------|--------|
| **Production-style orchestrated runs** | `04-coding/scripts/run_daily.py` only (`AGENTS.md`). |
| **`venture_pipeline.py`** | Diagnostic / legacy **dev** path — `__main__` gated on `VENTURE_DEV_MAIN=1`, except `--status` (read-only). **Not** an alternate human production door for governed sends. |

### 8.2 Landing ICP latch (HTML + optional CI)

File: `04-coding/boilerplates/landing-page/index.html` must contain **exactly one** of:

```html
<!-- VENTURE_SEMANTIC:LANDING_ICP=pending -->
```

```html
<!-- VENTURE_SEMANTIC:LANDING_ICP=locked -->
```

**Enforcement:** `validate_repo_contract.py` — if `VENTURE_ENFORCE_LANDING_ICP=1` **or** `04-coding/state/launch_execution_state.json` has `"landing_icp": "locked"`, the **locked** marker is required. See `AGENTS.md`.

### 8.3 Written interpretation (no “AI verdict” layer)

Structured human prose for judgment that must not live in chat alone:

- `03-reevaluation/decision-log.md`  
- `07-kpis/operator_execution_log.csv` where applicable (`OPERATOR_RUNBOOK.md`)

No separate shipped UI that assigns GO/HOLD/SKIP “verdicts” on **ideas** as a substitute for governed outbound row evidence.

### 8.4 Copy vs implementation

If wording **outruns** what the repo can reconstruct from artifacts, **shrink the wording** — never inflate the system (`LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` alignment).

---

## 9. References

- `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md`  
- `AGENTS.md`  
- `OPERATOR_RUNBOOK.md`  
- `04-coding/CURSOR_AGENT_PRIMARY_EXECUTION_PROMPT.md`
