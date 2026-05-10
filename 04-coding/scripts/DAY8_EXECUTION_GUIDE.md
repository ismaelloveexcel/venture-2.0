# Day 8 Execution Scripts (Solo Operator)

Three-script execution pack for Day 8-14 automation.

---

## 📋 Scripts Overview

### 1. `prospect_builder.py`
**Purpose:** Source and validate prospects using rule-based filtering

**What it does:**
- Pulls prospects (from Hunter.io API if configured, or template data)
- Applies hard rules: READY | REVIEW | REJECT
- Outputs: `06-sales/prospects.csv` with readiness_status

**Rules:**
- READY: valid email + domain + decision-maker role
- REVIEW: missing email but strong domain + role
- REJECT: missing company, domain, role, or non-decision role

**Usage:**
```bash
python 04-coding/scripts/prospect_builder.py
```

**Output:** `06-sales/prospects.csv` (READY prospects only)

---

### 2. `message_generator_solo.py`
**Purpose:** Generate and validate messages (3-tier output)

**What it does:**
- Generates messages using ICP prompt
- Validates with hard rules (PASS | RETRY | FAIL)
- Auto-regenerates RETRY messages once
- Outputs: `06-sales/generated-outreach.csv`

**Validation Rules:**
- PASS: 90-130 words, call-based CTA, personalized, no filler
- RETRY: fixable issue (e.g., too short, missing personalization)
- FAIL: structural problem (too long, no CTA, generic, filler artifacts)

**Usage:**
```bash
python 04-coding/scripts/message_generator_solo.py
```

**Output:** `06-sales/generated-outreach.csv` (PASS messages only)

---

### 3. `review_queue.py`
**Purpose:** Ultra-simple review interface (binary decisions only)

**What it does:**
- Displays each PASS message
- Operator: APPROVE or REJECT (no editing)
- Outputs: `06-sales/approved-messages.csv`
- Optional: log call outcomes (BOOKED | INTERESTED | NOT_NOW | NO_FIT)

**Usage:**
```bash
# Review and approve messages
python 04-coding/scripts/review_queue.py

# Log call outcomes
python 04-coding/scripts/review_queue.py --log-calls
```

**Output:** 
- `06-sales/approved-messages.csv` (approved messages only)
- `07-kpis/call-log.csv` (call outcomes)

---

## 🚀 Execution Sequence (Day 8)

### Step 1: Build Prospect List (5 minutes)
```bash
python 04-coding/scripts/prospect_builder.py
```
Expected output: 30-50 READY prospects in `06-sales/prospects.csv`

### Step 2: Generate Messages (10 minutes)
```bash
python 04-coding/scripts/message_generator_solo.py
```
Expected output: PASS messages in `06-sales/generated-outreach.csv`

### Step 3: Review & Approve (20-30 minutes)
```bash
python 04-coding/scripts/review_queue.py
```
For each message: press 'a' (approve) or 'r' (reject)
Expected output: 20-30 approved messages in `06-sales/approved-messages.csv`

### Step 4: Send (Automated)
```bash
python 04-coding/scripts/venture_pipeline.py --dry-run
# Verify no errors, then:
python 04-coding/scripts/venture_pipeline.py
```
Sends approved messages at 20/day cap (configurable)

### Step 5: Log Call Outcomes (As calls come in)
```bash
python 04-coding/scripts/review_queue.py --log-calls
```
Enter: prospect name, company, outcome (BOOKED|INTERESTED|NOT_NOW|NO_FIT), notes

---

## ⏱️ Operator Time Budget

| Task | Time | Frequency |
|------|------|-----------|
| Prospect sourcing | 5 min | Day 8 (once) |
| Message generation | 10 min | Day 8 (once) |
| Message review | 20-30 min | Day 8 (once) |
| Call logging | 5 min/call | Daily (as needed) |
| Daily scorecard | 5 min | Daily |

**Total daily overhead:** ~10 min (after Day 8 setup)

---

## 🔧 Configuration

All scripts read from `.env` (already configured in repo root):
- `OPENAI_API_KEY` — message generation
- `HUNTER_API_KEY` — prospect sourcing (optional)

No additional setup needed.

---

## 📊 Expected Outcomes

**After Day 8 (prospect sourcing + generation + review):**
- Input: 50 raw prospects
- After validation: 30-50 READY prospects
- After generation: 30-50 messages
- After review: 20-30 approved messages

**Quality metrics:**
- Generation pass rate: 60-70% (normal)
- Approval rate: 60-80% (your decision)

**After Day 9 (send first 20):**
- Send cap: 20 messages
- Expected replies: 1-3 (3-10% reply rate early stage)
- Expected calls booked: 0-1

---

## 🚫 Anti-Patterns (Do NOT Do)

❌ Edit messages in review (causes scope creep)
❌ Add extra validation layers (defeats simplicity)
❌ Automate call logging (loses signal richness)
❌ Sync to Notion yet (Phase 2 only)
❌ Regenerate prospects daily (validate once per 50-day batch)

---

## ✅ Next Steps

1. Ensure `.env` has valid keys
2. Run Day 8 scripts in order (1 → 2 → 3)
3. Send approved messages on Day 9
4. Log call outcomes daily
5. Fill daily scorecard each evening

**You are fully execution-ready.**
