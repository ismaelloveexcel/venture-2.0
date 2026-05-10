# Day 8 Message Teardown Worksheet

Purpose: filter generated outreach into a high-signal send list.

## Runbook (fast mode)
1. Generate 50 messages.
2. Review in batches of 10.
3. Score each message in under 60 seconds.
4. Keep 20-30 strongest messages.
5. Apply light edits only on 4/5 messages.

If you keep more than 45, standards are too low.
If you keep fewer than 15, fix the generation prompt before Day 9 sends.

## 5-Layer Filter (all required)

### 1) Relevance
Question: Is this clearly for this specific person?

Pass requires:
- One real prospect signal (review, hiring, behavior, tool usage, public evidence)
- Detail that cannot be reused across many prospects

Fail if:
- Generic opener (for example: "I saw your company...")
- Could be sent unchanged to 10+ prospects

### 2) Problem
Question: Is there a clear implied pain the prospect recognizes?

Pass requires:
- Concrete operational or revenue pain
- Pain is specific enough to feel familiar to the role

Fail if:
- Abstract phrasing (for example: "improve your business")
- Vague workflow claims (for example: "optimize operations")

### 3) Clarity
Question: Can this be understood in less than 5 seconds?

Pass requires:
- One idea only
- Short, plain-language sentences

Fail if:
- Multiple ideas in one message
- Long explanations or jargon

### 4) Credibility
Question: Does this feel human and believable?

Pass requires:
- Grounded tone
- No hype claims

Fail if:
- Generic sales language (for example: "we help businesses like yours")
- Inflated language (for example: "revolutionary solution")

### 5) Action (CTA)
Question: Is the next step obvious, binary, and low commitment?

Pass requires:
- Yes/no CTA
- One clear next step

Good CTA examples:
- "Worth exploring?"
- "Should I send a quick breakdown?"

Fail if:
- Soft CTA (for example: "let me know your thoughts")
- Multiple CTAs in a single message

## Hard Reject Triggers (auto-fail)
- Template variables or unresolved placeholders (`{}`, `{{name}}`, etc.)
- `lorem` or obvious filler artifacts
- More than 120-150 words
- More than one CTA
- Paragraph blocks over 3 lines
- Obvious AI tone

## Scoring Grid
Use binary scoring per layer:

- Relevance: 0 or 1
- Problem: 0 or 1
- Clarity: 0 or 1
- Credibility: 0 or 1
- Action: 0 or 1

Total score = sum of all five layers.

Decision rule:
- 5/5 -> SEND
- 4/5 -> FIX (light edit only)
- 0-3/5 -> REJECT

## Batch Review Sheet (copy for each 10-message batch)
| ID | Relevance | Problem | Clarity | Credibility | Action | Total | Decision | Light Edit Note |
|----|-----------|---------|---------|-------------|--------|-------|----------|-----------------|
| 1  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 2  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 3  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 4  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 5  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 6  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 7  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 8  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 9  | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |
| 10 | 0/1       | 0/1     | 0/1     | 0/1         | 0/1    | 0-5   | SEND/FIX/REJECT | |

## Operator Targets for Day 8
- Approved for send: 20-30
- Rejected: expected 20+
- Rewrites: 0 (light edits only)
- Timebox: 60-90 minutes for all 50
