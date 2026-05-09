# Venture OS Brutal + Investor Due Diligence Audit Prompt

Use this as the first message to the agent:

---

You are performing a dual audit of the Venture OS toolchain and workflow:
- Track A: Brutal founder-first operating audit
- Track B: Investor-grade due diligence audit

Context:
- Goal: build a real venture that reaches at least $10,000/month revenue.
- Operator: solo, non-technical founder.
- Constraint: system must be reliable, low-maintenance, clear to operate, and resilient to user mistakes.
- Priority order: revenue impact > reliability > usability > speed of setup > elegance.

Audit mode:
- Run BOTH tracks in one response.
- If evidence is insufficient, state assumptions explicitly and label confidence.

Your task:
1. Review the whole system end-to-end (pipeline, scripts, scheduler, dashboard, queue/retry/logging, integrations, data flow, and operations).
2. Identify all issues, weaknesses, hidden risks, missing controls, and bottlenecks.
3. Identify strategic gaps that block reaching $10k/month (not just code bugs).
4. Recommend concrete improvements/enhancements with implementation details.
5. Prioritize fixes by impact and urgency for a solo non-technical operator.
6. Assess investor readiness: operational risk, governance, defensibility, scale readiness, and go-to-market viability.

Audit style requirements:
- Be brutally honest and specific.
- Do not sugarcoat.
- Assume this system will fail in production unless proven otherwise.
- Flag false confidence areas, fragile assumptions, and silent failure paths.
- Include product, operational, GTM, and technical risks.
- Evaluate as if an investor IC memo will be written from your output.

What to evaluate:
- Reliability: retries, rate limits, queue semantics, idempotency, recovery after crashes.
- Safety: bad input handling, CSV injection, accidental sends, secret handling, permission boundaries.
- Observability: logs, error visibility, dashboard usefulness, alerts, run health, **`block_logs` severity (HARD/SOFT/INFO)**, **`funnel_health_snapshots` per run**, **`reply_intent_training_data` feedback loop**, **`state_engine_version` / replay drift** (see repo `README.md`).
- Solo-operator UX: setup complexity, runbook clarity, confusing steps, manual burden.
- Revenue engine readiness: lead quality, outreach quality, follow-up effectiveness, KPI feedback loops.
- Scalability: what breaks at 10x leads or 10x outbound volume.
- Compliance/reputation risk: cold email risk, bounce handling, domain health, basic guardrails.
- Investor DD: TAM/SAM/SOM clarity, unit economics assumptions, retention signals, customer acquisition dependency risk, concentration risk, vendor/platform risk, legal/compliance posture, and execution risk.
- Moat/defensibility: data flywheel potential, workflow lock-in, switching costs, unique distribution advantages, and IP/process defensibility.

Output format (mandatory):

## Executive Verdict
- 1 paragraph: Is this system currently capable of supporting a path to $10k/mo for a solo non-technical user? Yes/No + why.

## Investor Verdict
- 1 paragraph: Is this venture currently investable at pre-seed on execution quality and risk profile? Yes/No + why.
- Include current stage risk class: Low / Medium / High / Critical.

## Critical Findings (P0)
- List only severe blockers.
- For each item include:
  - Problem
  - Why it matters for $10k/mo
  - Evidence (file/function/behavior)
  - Recommended fix

## Critical Due Diligence Risks (P0-DD)
- For each item include:
  - Risk category (Market, Product, GTM, Ops, Security, Compliance, Finance)
  - Why this blocks funding confidence
  - Evidence and missing evidence
  - Mitigation required before serious investor conversations

## High-Impact Improvements (P1)
- Same structure as above.

## Medium Improvements (P2)
- Same structure as above.

## Missing Capabilities
- What does not exist but must exist to achieve the business goal.

## Investor Due Diligence Gaps
- What a serious investor will ask for that is currently missing.
- Include: metrics, reporting, controls, legal docs/process, revenue proof, and operating cadence.

## 30-Day Improvement Plan
- Week-by-week plan with clear milestones and expected business effect.

## 30-Day Investor Readiness Plan
- Week-by-week plan to reach credible pre-seed diligence readiness.

## Implementation Backlog
- Table with columns:
  - Priority
  - Change
  - Effort (S/M/L)
  - Risk if skipped
  - Owner (Agent/User)
  - Definition of done

## Solo-Operator Runbook Fixes
- Exact changes needed to make this operable by a non-technical founder.

## Diligence Data Room Checklist
- Provide a concise checklist of artifacts to prepare:
  - Product and architecture docs
  - KPI history and cohort signals
  - GTM funnel baseline
  - Reliability and incident logs
  - Security/privacy basics
  - Compliance/email deliverability posture

Final instruction:
- End with “Top 5 actions to do next” in strict order.
- Be decisive. If tradeoffs exist, choose the option that maximizes reliable revenue generation for a solo operator.
- Also end with “Top 5 investor confidence unlocks” in strict order.

---
