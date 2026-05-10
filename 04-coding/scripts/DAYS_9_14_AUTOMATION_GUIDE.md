# 🤖 DAYS 9–14 MEASUREMENT AUTOMATION — What Can Be Automated

**Status:** Design phase (Phase 2 work, not Day 8 blocker)  
**Purpose:** Reduce daily manual logging burden from 10–15 min to <2 min  
**Scope:** Reply detection, classification, call tracking, metric persistence

---

## Current State (Manual)

**Days 9–14 workflow currently requires:**

1. **Operator monitors email** for replies (manual checking)
2. **Operator manually logs** each reply in CSV
3. **Operator decides** if reply is qualified (judgment call)
4. **Operator schedules call** manually (Calendly/email)
5. **Operator logs call outcome** after call (manual entry)
6. **Dashboard reads** CSV to show metrics
7. **execution_state.json** not auto-updated

**Pain points:**
- Missing replies (operator doesn't check constantly)
- Manual logging errors (typos, wrong classification)
- Time lag between event and metric (reply comes in Day 10, logged Day 12)
- No audit trail of decisions
- Daily push to remember to update

**Time cost:** 10–15 min/day × 14 days = ~2.5 hours manual labor

---

## Automation Opportunity: 3 Layers

### Layer 1: Email Monitoring (Automated Reply Detection)

**What to automate:** Detect when replies come in, fetch them, classify

**Implementation:**

```python
# 1. Email API Integration (Gmail or Outlook)
# Monitor INBOX for replies to sent emails

# 2. Reply Extraction
# For each email from prospects in prospects.csv:
#   Extract: sender, subject, body, timestamp

# 3. Reply Classification
# Use OpenAI to classify: QUALIFIED / NOT_QUALIFIED
# Rule: Does this person agree to a call in next 48 hours?

# 4. Auto-Log
# Write to: 07-kpis/call-log.csv
# Columns: date, prospect_name, reply_status, qualified_y_n, logged_at
```

**Tools needed:**
- `email_monitor.py` (new) — runs every 30 min, checks inbox
- `reply_classifier.py` (new) — OpenAI-based classification
- Gmail/Outlook API credentials in .env

**Output:**
- `07-kpis/call-log.csv` auto-populated with replies + classification
- execution_state.json updated with reply_count, qualified_replies

**Time to build:** 4–6 hours (Phase 2)

**Complexity:** Medium (API integration, error handling)

---

### Layer 2: Call Scheduling & Calendar Monitoring (Automated Booking Tracking)

**What to automate:** Detect when calls are booked, track them

**Implementation:**

```python
# 1. Calendar Sync
# Monitor operator's Google Calendar / Outlook
# Look for events with "call:" prefix

# 2. Call Detection
# Extract: prospect name, scheduled time, call link
# Match to prospects.csv

# 3. Auto-Log Booking
# Write to: 07-kpis/call-log.csv
# Set: call_booked_status = yes, scheduled_time = [timestamp]

# 4. Reminder
# Day before call: send operator reminder with prospect context
```

**Tools needed:**
- `calendar_monitor.py` (new) — syncs Google Calendar / Outlook
- Calendar API credentials in .env
- Call template (Zoom link, script reminder)

**Output:**
- Call log auto-populated with booked calls
- execution_state.json updated with calls_booked, calls_scheduled

**Time to build:** 3–4 hours (Phase 2)

**Complexity:** Medium (calendar API, timezone handling)

---

### Layer 3: Call Outcome Recording (Automated Transcription & Logging)

**What to automate:** Record calls, extract outcomes, log results

**Implementation:**

```python
# Option A: Recording + Transcription
# 1. Zoom/Meet API: Record calls automatically
# 2. Whisper API: Transcribe recordings
# 3. OpenAI: Extract outcome ("did prospect agree to pilot?")
# 4. Auto-log: Write to call-log.csv with outcome

# Option B: Manual Recording with Auto-Extraction
# 1. Operator records call manually (Zoom/Meet native)
# 2. Webhook: Automatically fetches recording after call ends
# 3. Whisper API: Transcribe
# 4. OpenAI: Extract outcome
# 5. Auto-log: Write to call-log.csv

# Option C: Lightweight (No Recording)
# 1. Operator speaks outcome into voice memo
# 2. Whisper API: Transcribe
# 3. OpenAI: Extract structured outcome
# 4. Auto-log: Write to call-log.csv
```

**Tools needed:**
- `call_outcome_recorder.py` (new) — integrates with Zoom/Meet API
- Whisper API (OpenAI)
- Recording storage (Google Drive / S3)

**Output:**
- Call log auto-populated with outcomes (BOOKED / INTERESTED / NOT_NOW / NO_FIT)
- execution_state.json updated with calls_held, call_outcomes
- Transcript stored for reference

**Time to build:**
- Option A: 8–10 hours (most automated, complex)
- Option B: 5–7 hours (medium automation)
- Option C: 2–3 hours (lightweight, operator-friendly)

**Complexity:**
- Option A: High
- Option B: Medium
- Option C: Low

**Recommended:** Start with Option C (simplest, fastest to implement)

---

## Automation Stack (Recommended Phase 2)

### Minimum Viable Automation (Week 1, Phase 2)

```
Email monitoring
    ↓
Reply classification (QUALIFIED/NOT_QUALIFIED)
    ↓
Call-log.csv auto-populated
    ↓
execution_state.json auto-updated
    ↓
Dashboard refreshes in real-time
```

**Time to build:** 6–8 hours  
**Dependencies:** Gmail API, OpenAI API  
**Effort:** Medium (3–4 session management flows)

**Benefit:** 
- Operator checks email → system auto-logs
- Dashboard always current
- No manual CSV editing needed
- Reduces daily time from 10 min to 2 min

---

### Full Automation Stack (Week 2–3, Phase 2)

```
Email monitoring → Reply classification
    ↓
Calendar monitoring → Call booking detection
    ↓
Call recording → Transcription → Outcome extraction
    ↓
Call-log.csv + execution_state.json auto-updated
    ↓
Dashboard real-time + signal rules auto-evaluate
    ↓
pre_send_check.py blocks if rules triggered
```

**Time to build:** 15–20 hours total  
**Dependencies:** Gmail API, Calendar API, Zoom/Meet API, Whisper API  
**Effort:** High (complex integration)

**Benefit:**
- Fully hands-off pipeline tracking
- Zero manual logging
- Real-time signal detection
- Auto-pause if failures detected

---

## Which Tier to Pick (Decision Matrix)

| Operator Profile | Recommended | Reason |
|------------------|-------------|--------|
| **Wants minimal code** | Option C (lightweight) | Simplest, fast to build, operator friendly |
| **Wants full automation** | Full stack | Build after Day 14 signal validates direction |
| **Testing first run** | Minimum viable | Auto-logging only, add calendar/call tracking in Week 2 |

**For YOUR case (Day 8–14 solo operator):**

→ **Minimum viable automation** (6–8 hours, Phase 2)
→ Start after Day 14 GO verdict
→ Focus on email + reply classification first
→ Add calendar/call tracking Week 2

---

## Implementation Roadmap (Post-Day 14)

### Day 15–16: Decide on Automation Tier
- If pilot signals strong (3+ calls): Invest in full stack
- If pilot signals weak (0–1 calls): Minimal automation OK, focus on ICP fix

### Week 2 (Phase 2): Build Minimum Viable
```
email_monitor.py → Gmail API → fetch replies every 30 min
reply_classifier.py → OpenAI → classify QUALIFIED/NOT_QUALIFIED
call_log_updater.py → write to 07-kpis/call-log.csv
execution_state_writer.py → update 07-kpis/execution_state.json
```

### Week 3 (Phase 2): Add Calendar Monitoring
```
calendar_monitor.py → Google Calendar API → detect booked calls
auto_reminder.py → send operator call context before call
```

### Week 4 (Phase 2): Add Call Outcome Recording
```
call_outcome_recorder.py → integrates with Zoom/Meet
transcription.py → Whisper API
outcome_extractor.py → OpenAI structured extraction
```

---

## What NOT to Automate (Stay Manual)

❌ **Actual call facilitation** — operator does the talking  
❌ **Final decision on closure** — operator decides if prospect is "real" pilot  
❌ **Pricing negotiation** — operator owns the deal  
❌ **Follow-up sequencing** — depends on operator judgment  

These require human judgment and can't be deterministically automated.

---

## Estimated Time Savings (Phase 2)

| Activity | Current | Automated | Savings |
|----------|---------|-----------|---------|
| Check email for replies | 3 min/day | 0 (auto) | 3 min |
| Log reply in CSV | 2 min per reply | 0 (auto) | 10 min/week |
| Classify reply quality | 1 min per reply | 0.5 min auto + verify | 5 min/week |
| Log call booking | 2 min per call | 0 (auto) | 2 min/week |
| Log call outcome | 3 min per call | 1 min auto + verify | 5 min/week |
| Update metrics | 2 min/day | 0 (auto) | 2 min/day |
| **Total daily** | ~12 min | ~1 min | **~11 min/day** |

**Over 14 days:** ~2.5 hours saved → 2 hours available for actual work

---

## Build vs. Buy Decision

### Build (Recommended)
- Time: 6–20 hours (depends on tier)
- Cost: $0 upfront (uses existing OpenAI/Gmail APIs)
- Control: Full customization
- Risk: Maintenance burden

### Buy (Third-party)
- Examples: HubSpot, Pipedrive, Outreach.io
- Time: Setup 2–4 hours
- Cost: $99–500/month
- Control: Limited customization
- Risk: Overkill for solo operator

**For solo operator:** Build is better (cheaper, custom, learning)

---

## When to Start Building Automation

**Rule:**

Only build Phase 2 automation **after** Day 14 validates signal.

**Why:**
- If pilot fails: automation built is wasted effort
- If pilot succeeds: automation reduces friction for scaling
- Discipline: Execute faithfully first, optimize after signal

**Trigger:** Day 14 verdict is GO and 3+ metrics are healthy

---

## Files to Create (Phase 2)

```
04-coding/scripts/
├── email_monitor.py               (Gmail/Outlook API integration)
├── reply_classifier.py            (OpenAI classification)
├── calendar_monitor.py            (Google Calendar API)
├── call_outcome_recorder.py       (Zoom/Meet integration)
├── transcription_service.py       (Whisper API)
├── call_log_updater.py           (CSV + JSON writer)
└── automation_config.json         (API keys, schedules)

07-kpis/
├── email_replies.csv             (raw reply log from email monitor)
├── classified_replies.csv        (with QUALIFIED flag)
└── call_outcomes.csv             (enhanced from calendar + recording)
```

---

## Quick Start (If Building Phase 2)

**Easiest first feature to build:**

```python
# Step 1: Email Monitor
# Check inbox every 30 min for new emails from prospects.csv
# If from prospect: fetch and log to call-log.csv

# Dependencies:
# - Gmail API key + credentials.json
# - List of prospect emails
# - 30-min cron job

# LOC: ~150 lines
# Time: 2–3 hours
# Payoff: Eliminates manual email checking
```

This single feature saves ~3 min/day and creates audit trail.

---

## Summary

**Current (Days 9–14):** Manual logging, 10–15 min/day

**Phase 2 Option A (Minimum):** Auto email + reply classification, ~2 min/day, 6 hours to build

**Phase 2 Option B (Full):** Email + calendar + calls + outcomes, ~1 min/day, 15 hours to build

**Recommendation:** Build Phase 2A after Day 14 GO verdict. Option B can wait for Week 3.

Don't build before Day 14 signal validates direction.

Build only what reduces genuine friction, not complexity.

🚀
