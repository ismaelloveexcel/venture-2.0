# Day 8 Launch Pack (Operator-Ready)

Complete Day 8 execution toolkit: ICP prompt + prospect gate + operational flow.

---

# 1. ICP-TUNED OUTREACH PROMPT (Copy This Into Your Generator)

**Purpose:** Generate messages for B2B service companies with low-reply-rate pain, positioned for $300 14-day pilot.

**Use this EXACTLY as your message generation instruction.**

---

## SYSTEM INSTRUCTION

You are writing high-conversion outbound messages for a B2B service pilot offer.

### Objective
Book a 15–20 minute call to assess fit for a paid pilot ($300, 7–14 days).

### ICP Rule
Only write to prospects where there is a **clear operational pain signal**:
- Inconsistent lead flow
- Low conversion from outbound
- Weak sales pipeline
- Underperforming acquisition system

If no pain signal exists → mark as invalid. Do not fabricate.

---

## CORE MESSAGE STRUCTURE (STRICT)

Every message must include these 5 elements in order:

### 1. Personalized Hook (1–2 lines max)
- Must reference a specific observable fact (role, company activity, context)
- No generic greetings ("Hope you're doing well")
- No fluff intros

Example:
"Saw you recently posted about bringing on a sales hire—usually that means you're trying to scale outbound."

### 2. Pain Hypothesis (1–2 lines)
- Must explicitly connect to one operational bottleneck
- Must sound like a diagnosis, not a pitch

Example:
"You're likely dealing with inconsistent inbound, which makes it hard to predict pipeline week to week."

### 3. Micro-Relevance Bridge (1–2 lines)
- Explain why this is relevant NOW
- Grounded in logic, not persuasion

Example:
"That's exactly where most service companies get stuck before they scale."

### 4. Offer Framing (1–2 lines)
- Position as a small pilot
- Must include: time bound + low friction + fixed fee

Example:
"We run a short pilot—14 days, focused on one specific outcome, flat fee covers everything."

### 5. CTA (ONE ONLY)
Pick one, no alternatives:
- "Open to a quick 15–20 min call this week?"
- "Worth exploring briefly on a call?"
- "Should I show you how this would work in your setup?"

---

## STYLE RULES (NON-NEGOTIABLE)

- Max 90–130 words (not "up to 150")
- No hype language ("game-changing", "revolutionary", "scalable")
- No marketing phrases ("AI-powered", "cutting-edge", "proven solution")
- No bullet points in final message
- Must read like operator-to-operator (peer level)
- No exclamation marks unless absolutely natural

---

## HARD REJECT FILTERS

Reject message if ANY of these apply:
- Generic opening line
- No clear pain hypothesis stated
- No specific context reference
- CTA is not call-based
- Exceeds 130 words
- Sounds like marketing copy
- Multiple CTAs
- Uses templated language

---

# 2. PROSPECT VALIDATION CHECKLIST

Use BEFORE generating messages. Ensures batch quality.

## Required Fields Per Prospect

| Field    | Rule |
|----------|------|
| Name     | real identifiable person |
| Company  | verifiable business |
| Role     | decision influence (Founder/Owner/Head/Director) |
| Contact  | email or company domain (reachable path) |
| Industry | B2B service (agency, coach, SaaS founder, local service) |
| Pain     | explicit or strongly inferred signal |

## Pain Signal Validation

A prospect is ONLY valid if **at least ONE** of these exists:

- **Hiring signal:** posted for sales, marketing, operations roles
- **Weak inbound signal:** outdated website, low digital presence, not ranking
- **Active outreach dependency:** agency, coaching, or consulting business
- **Growth signal:** recent funding, expansion phase, ads/funnel mentions
- **Operational inefficiency clue:** mentions scaling challenges, hiring, systems

If **no signal exists → REJECT**. Do not guess.

## Send-Ready Classification

Assign each prospect a status:

### 🟢 SEND-READY
- 2+ pain signals OR strong explicit pain
- Decision-maker role confirmed (not gatekeeper)
- Reachable contact (email or domain)
- **Action:** Generate message immediately

### 🟡 CONDITIONAL
- 1 weak or indirect pain signal
- Unclear role authority
- **Action:** Manual review only (decide to send or skip)

### 🔴 REJECT
- No observable pain signal
- Non-decision role (coordinator, assistant, etc.)
- No contact path
- Industry mismatch
- **Action:** Remove from batch

---

## Implementation (Manual)

Create a CSV column:

```
readiness_status: send_ready | conditional | reject
pain_confidence_score: 1-5
notes: (why send-ready or why rejected)
```

Filter to **send_ready only** before message generation.

---

# 3. DAY 8 OPERATIONAL FLOW (Complete Sequence)

## Step 1 — Prospect Gate (Pre-Generation)
1. Load 50–100 raw prospects
2. Apply validation checklist above
3. Classify each row (send_ready | conditional | reject)
4. **Keep only 🟢 send_ready rows**
5. Expected output: 30–50 valid prospects

## Step 2 — Message Generation
1. Use ICP-Tuned Prompt (copy from Section 1 above)
2. Generate one message per send_ready prospect
3. **No deviations from prompt allowed**
4. **No re-prompting or custom tweaks**

## Step 3 — Teardown Filter (Your Existing System)
1. Apply 5-layer scoring (see [06-sales/day8-message-teardown.md](day8-message-teardown.md))
2. Keep messages scoring 4/5 or 5/5 only
3. Light edits on 4/5 messages only
4. **Expected output: 20–30 approved messages**

## Step 4 — Log Quality Metrics
Fill daily scorecard (see [03-reevaluation/daily-scorecard-template.md](../03-reevaluation/daily-scorecard-template.md)):
- Messages reviewed: [count]
- Messages approved (5/5): [count]
- Messages fixable (4/5): [count]
- Messages rejected (0-3/5): [count]
- Most common fail layer: [Relevance | Problem | Clarity | Credibility | Action]

## Step 5 — Ready for Day 9 Send
- 20–30 approved messages in queue
- No further modifications
- Day 9 execution uses send caps (20 messages max)

---

# 4. EXPECTED OUTCOMES (Realistic Benchmarks)

If executed correctly:

### Message Quality
- Teardown rejection rate: 30–40% (expected, normal)
- Approval rate: 60–70% of generated messages

### Reply Signal
- From 20–30 sent: 1–3 positive replies (3–10% reply rate early stage)
- Positive replies: will reference your specific pain hypothesis back to you
- Generic replies: "Tell me more" = skip these (they're curious, not qualified)

### Call Booking
- From 1–3 positive replies: expect 0–1 call booked this cycle
- This is normal. You're testing fit, not volume.

---

# 5. ANTI-PATTERN ALERTS (Stop If You See These)

### ❌ You're Deviating If:
- "Let me customize the prompt for my niche"
- "Let me add a 6th layer to the teardown"
- "Let me try reaching out to 100 instead of 50"

✅ **Stay disciplined.** Run clean execution first.

### ❌ Your Prospects Are Bad If:
- No role titles (just company names)
- No contact path at all
- Roles like "coordinator", "assistant" (not decision makers)
- Industries unrelated to B2B services

✅ **Validate before generating.**

### ❌ Your Messages Are Weak If:
- Majority fail "Relevance" layer (generic hook)
- Majority fail "Problem" layer (no diagnosis)
- Majority fail "Action" layer (soft CTA)

✅ **This tells you the ICP prompt needs tightening after Day 8** (not now).

---

# 6. POST-DAY 8 DECISION POINT

After filtering, log these metrics:

| Metric | Target | Action if Below |
|--------|--------|-----------------|
| Approval rate | 60%+ | Review prompt quality or prospect quality |
| Most common reject layer | ≤1 (not distributed) | Tighten that specific layer in next iteration |
| Total approved | 20–30 | If <15, stop; if >40, standards too low |

## If Everything Passes
→ Move to Day 9 (send first 20)

## If Approval Rate < 50%
→ Review prospect validation (are they actually valid?)
→ Do NOT re-run with modified prompt yet

## If >50% Fail Same Layer
→ Note it for post-pilot learning (don't change now)

---

# 7. QUICK REFERENCE

### Prospect Validation (Copy This)
```
Must have:
- Real name
- Verifiable company
- Decision-maker role
- Contact path
- At least 1 pain signal

Reject if missing any above.
```

### Message Checklist (5 Elements)
```
1. Personalized hook (specific fact, not generic)
2. Pain hypothesis (diagnosis)
3. Relevance bridge (why now)
4. Offer frame (pilot positioning)
5. CTA (call-based only)

Max 130 words. No hype. Operator tone.
```

### Day 8 Output Targets
```
Input: 50 prospects
After validation gate: 30–50 send-ready
After message generation: 50 messages
After teardown filter: 20–30 approved
Readiness: LIVE for Day 9 sends
```

---

Use this exactly as written. No customization. No "what ifs."

Day 8 is signal acquisition, not optimization.

Clean execution first.
