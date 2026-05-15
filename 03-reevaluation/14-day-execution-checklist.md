# 14-Day Execution Checklist

Purpose: convert the audit into daily execution for one operator.

## Day 1: Baseline and keys
- [ ] Set valid `OPENAI_API_KEY` and `HUNTER_API_KEY` in `.env`
- [ ] Run `VENTURE_CANONICAL_ENTRY=1 python 04-coding/scripts/run_daily.py --execute --dry-run`
- [ ] Confirm no `401 Unauthorized` errors

Exit criteria:
- Dry run finishes with provider calls working.

## Day 2: Qualification config lock
- [x] Move qualification assumptions out of hardcoded values into config
- [x] Add qualification block to `offer.config.json`
- [ ] Verify one live prospect passes/fails based on config change only

Exit criteria:
- Qualification economics are configurable without code edits.

## Day 3: Integrity truthfulness
- [x] Implement non-stub orphan detection in `system_state_snapshot.py`
- [x] Count duplicate initial sends only for `status='sent'`
- [ ] Run snapshot and inspect new metrics

Exit criteria:
- Snapshot integrity metrics reflect real DB state.

## Day 4: Source-of-truth workflow
- [ ] Document CSV -> pipeline -> SQLite ownership rules in scripts README
- [ ] Decide final CRM path: Notion-only or Airtable-only (not both)
- [ ] Remove inactive sync path from routine operations

Exit criteria:
- No ambiguity on where statuses are authoritative.

## Day 5: Offer lock
- [ ] Finalize one ICP + one offer promise + one pricing model
- [ ] Update `06-sales/offer-builder.md` with real offer details
- [ ] Align `offer.config.json` with final commercial terms

Exit criteria:
- Offer is explicit and sellable in one paragraph.

## Day 6: Prospect fuel build (batch 1)
- [ ] Add first 100 real prospects to `06-sales/prospects.csv`
- [ ] Include source tag and evidence note in working sheet/process
- [ ] Validate contactability quality (email/domain completeness)

Exit criteria:
- 100 qualified prospects loaded.

## Day 7: Prospect fuel build (batch 2)
- [ ] Add second 100 real prospects
- [ ] Deduplicate by company + contact
- [ ] Prepare send-ready segment of 50 best-fit prospects

Exit criteria:
- 200 qualified prospects loaded.

## Day 8: Message quality and approvals
- [ ] Generate outreach for top 50 in dry-run
- [ ] Review in 5 batches of 10 using `06-sales/day8-message-teardown.md`
- [ ] Score each message across 5 layers (Relevance, Problem, Clarity, Credibility, Action)
- [ ] Keep only high-confidence set (target 20-30 approved)
- [ ] Apply light edits only to 4/5 messages (no full rewrites)

Exit criteria:
- 20-30 approved messages ready to send, each passing structural and scoring gates.

Hard reject triggers (auto-fail):
- Contains template placeholders (`{}`, `{{}}`, unresolved tokens)
- Contains `lorem` or obvious filler text
- Overly long (more than ~150 words)
- Multiple CTAs in one message
- Wall-of-text paragraph blocks (more than 3 lines)
- Obvious AI-sales tone or exaggerated claims

Scoring rule:
- 5/5 = SEND
- 4/5 = FIX (light edit only)
- 0-3/5 = REJECT

## Day 9: Controlled live sending
- [ ] Enable conservative sending caps
- [ ] Send first 20 live messages
- [ ] Monitor block logs and provider responses

Exit criteria:
- First live batch sent without safety violations.

## Day 10: Follow-up readiness
- [ ] Verify follow-up eligibility logic from SQLite
- [ ] Confirm follow-up copy quality and compliance footer
- [ ] Send or schedule first follow-up batch

Exit criteria:
- Follow-up loop runs predictably.

## Day 11: Sales handoff and delivery prep
- [ ] Finalize call script and objection handling
- [ ] Create onboarding checklist for closed prospects
- [ ] Draft weekly delivery status template

Exit criteria:
- Post-close service delivery has a repeatable SOP.

## Day 12: KPI instrumentation
- [ ] Log reply, call booked, call held, proposal, close metrics
- [ ] Run weekly KPI review script
- [ ] Identify biggest funnel bottleneck

Exit criteria:
- KPI tracking drives next-day decisions.

## Day 13: Risk and rollback drills
- [ ] Test policy HOLD behavior and safe-mode response
- [ ] Confirm dashboard and webhook paths are local-only or secured
- [ ] Verify replay/audit commands for incident recovery

Exit criteria:
- You can safely pause, inspect, and recover.

## Day 14: Decision day
- [ ] Review 14-day funnel metrics and closed revenue
- [ ] Keep, pivot niche, or pivot offer based on evidence
- [ ] Set next 30-day sprint targets

Exit criteria:
- Clear GO/PIVOT decision with measured rationale.

## Weekly KPI Targets (minimum)
- Reply rate: >= 3%
- Call booked rate: >= 1.5%
- Calls held to proposal: >= 40%
- Proposal to close: >= 20%

## Daily non-negotiables (execution constraints)

### 2-minute scorecard (mandatory)
Use `03-reevaluation/daily-scorecard-template.md` every day. No send day is complete without this entry.

### Message quality filter (reject before send)
Reject if any are true:
- Sounds templated
- No specific prospect signal
- Weak CTA (for example: "open to chat?")
- Over-explains the product before validating pain

Accept only if all are true:
- Mentions one real signal (review, hiring, behavior, or public evidence)
- States one concrete outcome
- Uses binary CTA (yes/no decision)

### Prospect quality gate (before list entry)
Every prospect must pass all checks:
- Clear business identity (not vague)
- Can afford at least a $1k pilot
- Visible and relevant problem
- Reachable contact method
- Problem can be solved in 14 days

If any check fails, do not add to active send list.

### Send control rule (14-day sprint)
- Day 9: max 20 sends
- Day 10: max 15 sends
- Day 11: max 15 sends
- Hard cap: 20 sends/day

Do not scale above cap during this sprint.

### Reply classification (immediate handling)
- Positive: book call immediately
- Curious: clarify quickly and push to call
- Neutral: ignore
- Negative: extract objection and log it
- Hostile: suppress

### Call objective (single goal)
Each call must confirm at least one:
- Problem exists
- Budget range is real
- Urgency exists now

If none are confirmed, mark as low-quality call.

### Pilot offer structure (no improvisation)
- Setup fee: $1k-$2k
- Timeline: 14 days
- Outcome: one measurable improvement
- Risk control: revision or refund clause

### Daily bottleneck rule
End each day with one explicit answer:

What is the ONE thing blocking progress?

Then apply exactly one fix:
- Replies low: fix message quality and signal specificity
- Calls low: fix CTA
- Closes low: fix offer framing
- Prospects low: fix sourcing

### Hard anti-drift rule
Until all are true:
- 50 sends completed
- Real replies received
- Real calls held

Do not do any of the following:
- New scripts
- New integrations
- New automation features
- Reddit pipelines
- Scoring model changes

## Current status from this implementation pass
- [x] P0 patch applied: config-driven qualification inputs
- [x] P0 patch applied: orphan metric no longer stubbed
- [x] P0 patch applied: duplicate initial send metric tightened to sent rows
- [x] Validation: integration test passed
- [ ] Remaining blocker: set valid provider credentials for live-quality outputs
