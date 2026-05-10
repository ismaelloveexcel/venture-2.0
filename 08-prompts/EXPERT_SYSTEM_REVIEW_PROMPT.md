# Expert System Review Prompt — Venture OS Day 8–14 Solo Operator Pack

**Context:** Solo founder, side-hustle operator, targeting $10,000/month revenue. System is architecturally complete with Day 8–14 execution scripts, offer definition, and quality gates. This is a **critical external review** before real execution.

---

## System Summary (for reviewer context)

### Core Offer
- **Target ICP:** B2B service companies (law, accounting, consulting, marketing agencies) with low reply rates on cold outreach
- **Outcome:** Generate 5–10 qualified replies from 50 messages in 14 days
- **Pricing:** $300 flat fee per pilot (50 prospects + 14-day execution)
- **Risk Reversal:** If <5 replies, extend free
- **Execution Model:** Operator handles all messaging, call facilitation, and reporting

### Execution System (Operator-facing)
1. **prospect_builder.py** — Rule-based sourcing (Hunter API + template fallback), READY/REVIEW/REJECT classification
2. **message_generator_solo.py** — ICP-tuned prompt, 3-tier validation (PASS/RETRY/FAIL), auto-regenerate on RETRY
3. **review_queue.py** — Binary APPROVE/REJECT review (no editing), call logging interface
4. **venture_pipeline.py** — Send automation, comply gates, lifecycle tracking
5. **Daily scorecard template** — Tracks sends, replies, calls booked, calls held, pilot offers, pilots closed
6. **Sales call script** — 15–20 min fit-check, binary qualification, exact pilot CTA
7. **offer_builder.md** — Locked $300 scope + risk reversal positioning

### Operator Constraints
- **Non-technical** (runs CLI commands, fills spreadsheets, logs calls)
- **Side hustle** (limited daily time budget)
- **Solo** (no team, no contractors yet)
- **Target volume:** 4 pilots/month = $1,200 MRR → 8–9 pilots/month for $10k (assumes ~$1,200 pilot value, not $300)

---

## Questions for Expert Review

**CRITICAL:** Please answer with brutally honest assessment. Assume operator follows instructions exactly.

### A. VIABILITY & REVENUE

1. **Revenue Model Feasibility:** Is $300/pilot sustainable long-term? Can operator realistically book 8–9 pilots/month from cold outreach with this offer?
   - What's the realistic pipeline needed? (e.g., if you need 4–5 qualified calls to close 1 pilot, what send volume is required?)
   - Is the $300 entry point too low to attract serious buyers? (Risk: attracting bargain hunters who won't actually execute)
   - Should the offer be scoped higher ($500–$1000) to increase deal value and pre-filter for commitment?

2. **$10k/month viability:** This requires either (a) $300 pilots at scale OR (b) move upmarket to $1000+ pilots after signal validation. 
   - Is the current Day 8–14 system positioned to validate which direction (scale volume vs move upmarket) by Day 15?
   - What single metric should the operator watch after pilot 1 that indicates "you're on the right track"?

3. **Pilot-to-Retainer Potential:** Can the operator convert pilots into recurring revenue (retainer, subscription)?
   - Current system doesn't include post-pilot conversion. Is that a blocker for $10k?
   - Should the offer include a "graduate to ongoing" option at Day 14 check-in?

---

### B. GAPS & BLOCKERS (Execution)

4. **Prospect Quality Gate:** prospect_builder.py uses Hunter API (third-party, rate limits, cost). 
   - Is the fallback to template data good enough if Hunter API fails? (Risk: stale/low-quality fallback prospects)
   - Should there be a manual override to allow operator to paste LinkedIn URL + auto-enrich, or paste raw prospect list?

5. **Message Quality Variance:**
   - 3-tier validation (PASS/RETRY/FAIL) is rule-based (word count, CTA presence). Will OpenAI actually produce coherent, differentiated messages at scale?
   - What happens if 40% of PASS messages are generic/low-signal and operator approves them anyway?
   - Should there be a **sample review** before Day 9 send (e.g., operator reviews first 5 messages, can ask for regeneration)?

6. **Reply Processing:** System generates reply-intent training data, but operator doesn't review replies or auto-classify them.
   - Who decides which replies are "qualified" for a call? (Current: no clear rule)
   - Risk: operator wastes call time on "thanks, not interested" replies
   - Should review_queue.py include a **reply classifier** (qualified/not qualified) before scheduling calls?

7. **Call Scheduling:** Sales call script assumes operator gets reply → schedules call → calls prospect.
   - How does operator schedule the call? (Email back? Calendar link? Phone number?)
   - System doesn't include automated calendar/scheduling. Is that OK, or should venture_pipeline.py include Calendly/Outlook API integration?

8. **Offer Lock-In:** Offer is locked ($300, 50 prospects, 14 days, 5+ replies target).
   - What if operator realizes ICP is wrong mid-pilot (e.g., replies are from wrong buyer persona)?
   - Is there a **pivot gate** at Day 7 to pause and re-evaluate, or does operator have to run full 14 days?

---

### C. SIMPLIFICATION (for non-technical operator)

9. **CLI Complexity:** Operator runs 3 scripts sequentially (prospect_builder.py → message_generator_solo.py → review_queue.py).
   - Should these be merged into a single "Day 8 Launcher" script that runs all three with one command?
   - Or a simple web UI (Flask/Streamlit) instead of CLI prompts?

10. **Configuration Burden:** Scripts read from .env (OPENAI_API_KEY, HUNTER_API_KEY).
    - Is .env sufficiently obvious? (Risk: operator puts keys in wrong place, scripts fail silently)
    - Should there be a **preflight check** that runs automatically and reports "keys found: ✅ / ❌"?

11. **Spreadsheet Overhead:** Operator fills daily-scorecard-template.md (manual text edit).
    - Should this be a **Google Form** or **Airtable form** that populates a database, rather than manual markdown editing?
    - Current friction: operator must remember to fill scorecard daily. How is this enforced?

12. **Call Logging:** review_queue.py has optional `--log-calls` mode (4-state dropdown).
    - Is the CLI prompt/dropdown interface intuitive for non-technical users?
    - Should call logging integrate with the Google Form or Airtable mentioned in #11?

---

### D. AUTOMATION (what can be improved)

13. **Reply Detection & Classification:**
    - Currently: operator monitors replies manually, decides which are qualified
    - Could be automated: OpenAI classifier (trained on reply-intent data) auto-scores replies as "qualified" or "not_qualified"
    - Should this be added to Day 8 system, or defer to Phase 2?

14. **Call Transcription & Outcome Logging:**
    - Operator currently types call outcomes manually
    - Could be automated: record call → transcribe → extract outcome automatically
    - Worth adding, or over-engineering for solo side hustle?

15. **Message Regeneration Trigger:**
    - Currently: operator can manually ask for regeneration in review_queue.py
    - Could be automated: if reply rate drops below 5% by Day 10, auto-regenerate remaining messages with adjusted prompt
    - Risky (could spam), or necessary failsafe?

16. **Notion Sync (Phase 2):**
    - Current design defers Notion sync to Phase 2 (post-signal)
    - When should Phase 2 automation kick in? (After 50 sends? 5 replies? 1 pilot closed?)
    - What Notion sync would unblock operator: ideas database? Prospect CRM? KPI dashboard? All three?

---

### E. PREMIUM-NESS & DIFFERENTIATION

17. **Message Quality vs. Competitor Junk Mail:**
    - System generates 90–130 word messages with company name + role mention (basic personalization)
    - How does this compare to: (a) mass mail, (b) GPT-4 generic cold email, (c) human-written personalized outreach?
    - **Risk:** Prospects receive 100+ cold emails/month. What makes these 5 stand out?
    - Should the prompt include: research on prospect's recent hires, company news, or specific pain signals (LinkedIn scraping)?
    - Or is "basic personalization + ICP-tuned outcome" differentiated enough for 3–10% reply rate target?

18. **Outcome Credibility:**
    - Offer promises "5–10 qualified replies from 50 messages in 14 days"
    - Implied assumption: 10–20% reply rate is achievable for cold outreach to service companies
    - Is this realistic? (Industry benchmarks: 1–5% for untargeted, 5–15% for ICP-targeted)
    - If prospects see this offer, will they believe it?

19. **Positioning vs. "Cheap Outreach Service":**
    - $300 for 50 prospects + 14 days is ~$6/prospect or ~$21/reply (at 5 replies)
    - Competitor positioning: "We write outreach for you" (positioning: labor savings, not results)
    - Your positioning: "We generate qualified replies" (positioning: outcome, not labor)
    - **Problem:** If outcome-based, is $300 entry too low? (Risks operator undercuts self, attracts deal-hunters, or can't sustain on failed pilots)
    - **Suggestion:** Should pricing be outcome-contingent? (e.g., $300 + $500 if 5+ replies, $0 if <3 replies)

20. **Differentiation Moat:**
    - What can't competitors copy? (Your scripts are on GitHub, message prompt is visible, call script is standard, offer is transparent)
    - Long-term moat: operator's reputation, case studies, results data, proprietary ICP targeting
    - Is there a mechanism to **build proprietary knowledge** from early pilots (e.g., "we've run 50 pilots, here's what works for law firms vs agencies")?

---

### F. RISK ASSESSMENT

21. **Worst Case Scenario:** Operator runs Day 8–14 exactly as scripted, Day 14 arrives with 0 pilots closed, 1 reply.
    - What does operator do next? (Pivot? Kill? Iterate once more?)
    - System should include a **GO/PIVOT/KILL decision framework** at Day 14. Does it?

22. **Operator Burnout Risk:** 4–8 pilots/month requires 200–400 sends (at 50:1 send:pilot ratio). That's 15–30 sends/day.
    - Current system caps at 20 sends/day. Operator will be at daily max for 10–20 days straight.
    - Is this sustainable as a side hustle, or will operator burn out?
    - Should there be a **break week** scheduled into the 90-day plan?

23. **Technical Debt:** Scripts use openai_api_call resilience wrapper, Hunter API, venture_pipeline.py integration.
    - What happens if OpenAI API rate-limits? (Fallback: skip generation, use template? Or hard stop?)
    - What happens if Hunter API is down? (Fallback: template prospects, but quality drops)
    - Are these failure modes documented? (Risk: operator hits unexpected error, doesn't know how to recover)

---

### G. FINAL SYNTHESIS

24. **1-Sentence Recommendation:** Given operator constraints (non-technical, solo, side hustle), time budget (30-40 min Day 8, ~10 min/day ongoing), and $10k/month target — is this system:
    - ✅ **READY TO EXECUTE** (launch Day 8 immediately)
    - ⚠️ **READY WITH CAVEATS** (launch Day 8, but fix X/Y/Z first)
    - ❌ **NOT READY** (redesign required before Day 8)

25. **Top 3 Priority Fixes (if needed):** If the system is not "ready to execute," list the three highest-leverage fixes that would unlock execution. For each:
    - **What's broken:** [specific gap/risk]
    - **Why it matters:** [impact on revenue/operator experience]
    - **How to fix (2–3 sentence):** [concrete action]
    - **Can it wait until Phase 2, or must it be fixed before Day 8:** [Phase 1 blocker vs. nice-to-have]

---

## Context Files (for reviewer)

The following files document the system in detail:

- **Execution Scripts:** [prospect_builder.py](04-coding/scripts/prospect_builder.py), [message_generator_solo.py](04-coding/scripts/message_generator_solo.py), [review_queue.py](04-coding/scripts/review_queue.py)
- **Day 8 Guide:** [DAY8_EXECUTION_GUIDE.md](04-coding/scripts/DAY8_EXECUTION_GUIDE.md)
- **Offer Definition:** [offer_builder.md](06-sales/offer_builder.md)
- **Call Script:** [sales-call-script.md](06-sales/sales-call-script.md)
- **Message Framework:** [day8-message-teardown.md](06-sales/day8-message-teardown.md)
- **Launch Pack:** [day8-launch-pack.md](06-sales/day8-launch-pack.md)
- **Daily Tracking:** [daily-scorecard-template.md](03-reevaluation/daily-scorecard-template.md)

---

## Reviewer Instructions

**You are an expert in:** SaaS sales, cold outreach, B2B pricing, solo founder operations, and Python automation.

**Your role:** Identify gaps, risks, and simplification opportunities that could prevent this solo operator from reaching $10k/month.

**Your tone:** Brutally honest. This is pre-execution, so now is the time for hard feedback. Assume operator will follow instructions exactly (no heroic freelancing).

**Your output format:** Answer questions A–G above. For question 25, provide exactly 3 prioritized fixes with rationale. If no fixes needed, state "✅ READY TO EXECUTE" and explain why.

**Deadline assumption:** Operator wants to start Day 8 in the next 48 hours. Is that realistic?
