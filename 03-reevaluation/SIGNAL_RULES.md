# 📊 SIGNAL_RULES.md — Deterministic Failure Detection

**Purpose:** Hard-coded thresholds that trigger diagnostics, warnings, or auto-pause

**Use:** Dashboard reads these rules and evaluates system health automatically

---

## Rule Hierarchy

**HARD STOP** (auto-pause execution)  
↓  
**WARNING** (red flag, needs investigation)  
↓  
**INFO** (monitoring, no action needed yet)

---

## HARD STOP Rules (Auto-Pause Pipeline)

If ANY of these trigger, venture_pipeline.py pauses execution and requires manual review.

### Rule HS-1: Zero Replies After 25+ Sends
```
IF sends ≥ 25 AND replies == 0:
    ACTION: PAUSE execution
    REASON: ICP completely wrong or message invisible
    OPERATOR_ACTION: Review first 5 messages manually, check targeting
```

### Rule HS-2: System Health Check Failed
```
IF OpenAI API down OR Hunter API rate-limited:
    ACTION: PAUSE execution
    REASON: Critical external service failure
    OPERATOR_ACTION: Check .env keys, API quotas
```

### Rule HS-3: Approval Rate Catastrophically Low
```
IF approved ≥ 10 AND approval_rate < 0.20 (< 20%):
    ACTION: PAUSE approval queue
    REASON: Operator is rejecting nearly everything (message problem, not filtering issue)
    OPERATOR_ACTION: Review message prompt, ask "would I reply to these?"
```

### Rule HS-4: Send Success Rate Below Threshold
```
IF attempted_sends ≥ 10 AND send_success_rate < 0.90 (< 90%):
    ACTION: PAUSE execution
    REASON: Infrastructure failure (email delivery, auth issues)
    OPERATOR_ACTION: Check venture_pipeline.py logs, email provider status
```

---

## WARNING Rules (Red Flags, No Auto-Pause)

Dashboard shows 🟡 warning, operator should investigate within 2 hours.

### Rule W-1: Low Reply Rate (But Not Catastrophic)
```
IF sends ≥ 20 AND reply_rate < 0.03 (< 3%):
    STATUS: 🟡 WARNING
    DIAGNOSIS: ICP likely misaligned
    OPERATOR_ACTION: 
      - Review 5 replies (if any) to see who IS replying
      - Tighten prospect filtering
      - Check if targeting wrong buyer persona
```

### Rule W-2: Low Qualified Reply Rate
```
IF replies ≥ 5 AND qualified_rate < 0.25 (< 25%):
    STATUS: 🟡 WARNING
    DIAGNOSIS: Message not clarifying fit
    OPERATOR_ACTION:
      - Review "thanks but not relevant" replies
      - Improve message clarity or call-to-action
      - Check if ICP is attracting wrong people
```

### Rule W-3: Low Call Booking Rate
```
IF qualified_replies ≥ 3 AND booking_rate < 0.40 (< 40%):
    STATUS: 🟡 WARNING
    DIAGNOSIS: Reply-back email or calendar unclear
    OPERATOR_ACTION:
      - Review your follow-up email (is Calendly link clear?)
      - Test your reply flow on yourself
      - Check if prospects getting your email at all
```

### Rule W-4: Low Pilot Closure Rate
```
IF calls_held ≥ 2 AND closure_rate < 0.25 (< 25%):
    STATUS: 🟡 WARNING
    DIAGNOSIS: Offer unclear on call or sales qualification weak
    OPERATOR_ACTION:
      - Listen to call recordings
      - Did you explain pilot scope clearly?
      - Did you ask for commitment at the end?
```

### Rule W-5: Approval Rate Drift
```
IF approved ≥ 20 AND approval_rate < 0.50 (< 50%):
    STATUS: 🟡 WARNING
    DIAGNOSIS: Quality control working, but many rejects = message variance
    OPERATOR_ACTION:
      - Review rejected messages (why rejecting?)
      - Is message prompt consistent?
      - Are you being too picky?
```

---

## INFO Rules (Monitoring, Informational Only)

Dashboard shows 🟢 or 🔵, no action needed unless trending toward WARNING.

### Rule I-1: Campaign Still Running
```
IF last_send < 24h hours ago:
    STATUS: 🟢 ACTIVE
    INFORMATION: Campaign is running normally
```

### Rule I-2: Healthy Approval Rate
```
IF approval_rate ≥ 0.50:
    STATUS: 🟢 GOOD
    INFORMATION: Quality control is working
```

### Rule I-3: Normal Reply Rate
```
IF reply_rate ≥ 0.05 (≥ 5%):
    STATUS: 🟢 HEALTHY
    INFORMATION: ICP targeting is solid
```

### Rule I-4: On Track to Goal
```
IF pilots_closed ≥ (current_day - 7) / 7:
    STATUS: 🟢 ON TRACK
    INFORMATION: You're ahead of pace for Day 14 goal
```

---

## Implementation Rules (For Dashboard & Pipeline)

### Rule Evaluation Order
1. Evaluate HARD STOP rules first
2. If any HS rule triggers → display 🔴 PAUSED
3. Then evaluate WARNING rules
4. Then evaluate INFO rules
5. Display highest-priority rule at dashboard top

### Rule Check Frequency
- Dashboard: Real-time (every refresh, reads execution_state.json)
- Pipeline: Before each send batch (reads execution_state.json)

### Who Owns Updates
- venture_pipeline.py writes to execution_state.json after each run
- dashboard_streamlit.py reads execution_state.json for diagnostics
- Both use same SIGNAL_RULES.md for thresholds

---

## Example Scenario: Day 10

**Execution state:**
- sends: 22
- replies: 0
- approved: 15

**Rule evaluation:**
1. HS-1: sends (22) ≥ 25? NO → skip
2. HS-2: API health? OK → skip
3. HS-3: approved (15) ≥ 10? YES, approval_rate (15/27) = 55% > 20% → skip
4. HS-4: success_rate 95% > 90% → skip
5. **W-1: sends (22) ≥ 20? YES, reply_rate 0/22 = 0% < 3%? YES → TRIGGER**

**Dashboard shows:**
```
🟡 WARNING: ICP misaligned
Reply rate is 0% (target: ≥5%)
Review who is replying. Tighten targeting.
```

**Operator action:** Read day14-failure-analysis-template.md Mode A section, adjust ICP, send next batch

---

## Threshold Rationale

All thresholds are based on industry benchmarks for B2B cold outreach to service companies:

| Metric | Low Alert | Normal | Strong |
|--------|-----------|--------|--------|
| Reply rate | <3% | 3–10% | >10% |
| Qualified rate | <25% | 25–60% | >60% |
| Booking rate | <40% | 40–80% | >80% |
| Approval rate | <20% | 20–80% | >80% |
| Send success | <90% | 90–99% | 99%+ |

---

## Testing Signal Rules

### Test HS-1 (Zero Replies)
```bash
# Manually set sends=25, replies=0 in execution_state.json
# Dashboard should show: 🔴 PAUSED — ICP mismatch likely
# venture_pipeline should refuse to send next batch
```

### Test W-1 (Low Reply Rate)
```bash
# Set sends=20, replies=0
# Dashboard should show: 🟡 WARNING — ICP health
# No auto-pause, but prominent warning
```

### Test I-3 (Healthy)
```bash
# Set sends=20, replies=2
# Dashboard should show: 🟢 HEALTHY
```

---

## Version History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | May 9, 2026 | Initial rules based on expert review feedback |

---

**These rules are the brain of your system. Update thresholds only after Day 14 validation.**
