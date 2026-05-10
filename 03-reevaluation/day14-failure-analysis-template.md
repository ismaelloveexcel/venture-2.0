# Day 8–14 Failure Analysis Template

**Purpose:** Distinguish system failure (process broken) from ICP failure (targeting wrong) by Day 14.

When Day 14 arrives with unexpected results, this template prevents operator from chasing the wrong fix.

---

## THE CRITICAL DISTINCTION

### System Failure
- System is working fine
- Output is clean, process is sound
- **Problem:** You're targeting the wrong people

**Symptom:** <5% reply rate, 0 qualified replies

**Signal:** "Our targeting/ICP is wrong, not our system"

**Fix:** Adjust ICP, not code

### Execution Failure
- Targeting is sound (ICP is right)
- **Problem:** Messages are weak or process has bugs

**Symptom:** 15%+ reply rate but <20% qualified, or high bounces

**Signal:** "Our messaging or qualification is wrong"

**Fix:** Adjust prompt or call script

### Operator Failure
- System works, ICP is good, messaging is fine
- **Problem:** Operator didn't actually approve quality messages

**Symptom:** High reply rate, but operator realizes "I approved garbage"

**Signal:** "I need stricter approval standards"

**Fix:** Tighten sample quality gate

---

## DAY 14 VERDICT FRAMEWORK

**Run this template at Day 14 checkpoint. Fill in actual data.**

### INPUT METRICS (What you sent)

```
Total messages sent: ___
Days active: ___
Send-per-day average: ___

Message quality (estimate):
  [ ] 90%+ of approved messages were compelling
  [ ] 70-90% were compelling
  [ ] <70% were compelling (weak approval)

Prospect quality (estimate):
  [ ] ICP was tight (all decision-makers in target role)
  [ ] ICP was loose (mixed buyer personas)
  [ ] ICP was wrong (mostly wrong persona)
```

### OUTPUT METRICS (What you got)

```
Total replies: ___
Reply rate (%): ___ (replies / sends × 100)

Qualified replies: ___
Qualified reply rate (%): ___ (qualified / replies × 100)

Calls booked: ___
Call booking rate: ___ (calls / qualified replies × 100)

Calls held: ___
Qualified calls: ___ (calls where pain + attempted solution matched)
```

### DIAGNOSIS (Which failure bucket?)

**1. Did you get 2%+ reply rate?**

- **YES** → Go to Question 2
- **NO** → **ICP FAILURE.** Your targeting is wrong. Pivot to new niche or new buyer persona before next batch.

---

**2. Of replies you got, were 30%+ from actual decision-makers asking real questions?**

- **YES** → Go to Question 3
- **NO** → **MESSAGING FAILURE.** You're getting curious replies, not qualified ones. Adjust pain hypothesis in message prompt. Re-run with same ICP.

---

**3. Of qualified replies, did you book calls with 50%+ of them?**

- **YES** → Go to Question 4
- **NO** → **CALL SCHEDULING FAILURE.** You're not converting replies to calls. Add calendar link or clearer CTA in reply email.

---

**4. Of calls held, were 50%+ actually qualified (pain + impact + attempted solution)?**

- **YES** → **SYSTEM IS WORKING.** Move to pilot conversion. Scale this ICP.
- **NO** → **QUALIFICATION FAILURE.** Your call script is admitting unqualified calls. Tighten binary gate on sales call (step 2).

---

## DECISION LOGIC (GO / ITERATE / KILL)

### GO (System is working, scale)

**All of these must be true:**

- [ ] Reply rate ≥ 5%
- [ ] Qualified reply rate ≥ 30% of replies
- [ ] Call booking rate ≥ 50%
- [ ] Qualified call rate ≥ 50%
- [ ] At least 1 pilot offered
- [ ] At least 1 pilot accepted

**Action:** Lock this ICP. Scale send volume. Begin Phase 2 (retainer conversion).

---

### ITERATE (One clear failure bucket, fixable)

**Pick ONE and only ONE to fix:**

#### Option A: ICP was wrong (reply rate <2%)

- [ ] Identify which ICP signal failed (role? company size? industry?)
- [ ] Define NEW ICP with one change (different role OR different industry OR different company size)
- [ ] Run Day 8–14 again with new ICP
- [ ] Do NOT change messaging or process

#### Option B: Messaging was weak (qualified reply <20%)

- [ ] Review 3 rejected replies (ones that said "not interested")
- [ ] What pain did you miss? What were they actually solving?
- [ ] Adjust pain hypothesis in message prompt
- [ ] Rerun generation with SAME ICP, new prompt
- [ ] Do NOT change targeting or qualification

#### Option C: Call booking was low (<50% of qualified replies)

- [ ] What was the objection in replies? (Too salesy? Wrong timing? Unclear ask?)
- [ ] Add Calendly link to reply email
- [ ] Simplify CTA ("Let's sync for 15 min Tuesday or Wednesday?")
- [ ] Do NOT change messaging or ICP

---

### KILL (Unfixable in one variable, time to pivot)

**Any of these is true:**

- [ ] Reply rate < 1% after 100+ sends + good delivery
- [ ] Qualified reply rate < 15% after reply rate ≥ 5% + 3 rejections analyzed
- [ ] Call booking rate < 20% after 10+ replied
- [ ] Qualified call rate < 20% after 5+ calls held

**Action:** Stop. This ICP / offer / positioning does not work in cold channel. Pivot to:

1. Warm channel (referrals, warm intros)
2. Different ICP entirely
3. Different offer (not $300 pilot)

---

## QUALITY AUDIT (Did operator approve garbage?)

**Before you conclude "messaging failed", check approval quality:**

```
Review 5 APPROVED messages from the batch.

For each, answer: "Would I (the operator) reply to this?"

If 3+ = "No, this is generic": Approval standards were too low.

Action: Rerun same ICP with stricter sample gate (first 5 messages must be 5/5 on relevance + problem layers).
```

---

## ONE-PAGE CHECKLISTE (Print this for Day 14)

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Reply rate | ≥5% | ___ | 🟢🟡🔴 |
| Qualified reply % | ≥30% | ___ | 🟢🟡🔴 |
| Call booking rate | ≥50% | ___ | 🟢🟡🔴 |
| Qualified call rate | ≥50% | ___ | 🟢🟡🔴 |
| Pilot offers | ≥1 | ___ | 🟢🟡🔴 |
| Pilot closes | ≥1 | ___ | 🟢🟡🔴 |

**Green (all targets met):** GO — scale and lock ICP

**Yellow (1–2 miss):** ITERATE — pick one variable to fix

**Red (3+ miss):** KILL — pivot to warm channel or different ICP

---

## EXAMPLE: Reading Day 14 Results (NOT INSTRUCTIONS)

### Scenario A: "We got 40 replies from 50 sends, but 0 pilots"

```
Reply rate: 80%✅
Qualified replies: 10% of 40 = 4 ✅
Calls booked: 3 of 4 = 75% ✅
Calls held: 2 of 3 = 67%

Problem: Reply rate is HIGH (targeting is good), but qualified rate is LOW (messaging is weak).

Diagnosis: MESSAGING FAILURE

Fix: Review 3–5 non-qualified replies. What pain did you miss? Adjust prompt, rerun.
```

### Scenario B: "We got 2 replies from 50 sends, 0 pilots"

```
Reply rate: 4% 🟡 (borderline)
Qualified replies: 1 of 2 = 50% ✅
Calls booked: 1 of 1 = 100% ✅
Calls held: 1
Calls qualified: 1, but prospect said "not now"

Problem: Reply rate is LOW (targeting is weak).

Diagnosis: ICP FAILURE

Fix: Was wrong role? Wrong company size? Wrong industry? Change ONE variable, rerun.
```

### Scenario C: "We got 8 replies, 5 qualified, booked 2 calls, 0 pilots"

```
Reply rate: 16% ✅
Qualified reply rate: 62% ✅
Call booking: 25% 🔴 (too low)
Calls held: 2
Calls qualified: 1

Problem: Replies are good, but operator didn't convert to calls OR call script wasn't tight.

Diagnosis: CALL BOOKING or QUALIFICATION FAILURE

Fix: Add Calendly to reply email, simplify CTA, and/or tighten call qualification gate.
```

---

## HOW TO USE THIS TEMPLATE

### Before Day 8 Execution
- Print this or save as bookmark
- Understand the decision tree (GO / ITERATE / KILL)
- Know what metrics matter (reply rate → qualified rate → call rate)

### On Days 9–14
- Log daily: sends, replies, calls booked
- Fill daily scorecard as usual

### On Day 14 (Evening)
1. Fill in OUTPUT METRICS (actual data)
2. Run DIAGNOSIS (answer yes/no questions)
3. Check DECISION LOGIC (which bucket?)
4. Decide: GO or ITERATE or KILL

### By Day 15 (Morning)
- Clear next action (scale, iterate, or pivot)
- If ITERATE: pick one variable and rerun Day 8–14
- If GO: move to Phase 2 (retainer conversion)
- If KILL: pivot to warm channel or new ICP

---

## KEY PRINCIPLE

> **One variable at a time.**

If you change ICP AND messaging AND call script at once, you won't know which fix worked.

So:

- **Reply rate too low?** Change ICP only.
- **Qualified replies too low?** Change messaging only.
- **Calls booked too low?** Change reply handling / CTA only.
- **Calls qualified too low?** Change call script only.

This is how you avoid infinite iteration loops.

---

## EXPECTED DISTRIBUTIONS (For Reference)

If your system is working normally:

| Metric | Normal Range |
|--------|--------------|
| Reply rate (cold B2B) | 2–15% |
| Qualified of replies | 30–70% |
| Calls booked of qualified | 40–80% |
| Qualified calls | 40–80% |
| Pilot close rate | 20–50% |

If you're outside these ranges, diagnostic tree above will point to which variable broke.

---

## MOST IMPORTANT REMINDER

When Day 14 arrives, you will WANT to believe:

> "The system failed."

But most of the time, it will actually be:

> "We were targeting the wrong person."

Use this template to know the difference.

Because:

- System failure = fix code
- ICP failure = fix targeting

And they require completely different actions.

---

**Print this. Reference it daily starting Day 9. Annotate it with your actual numbers.**

By Day 14, you'll have the clearest signal you could possibly have about what to fix next.
