# ✅ DAY 8 FINAL CHECKLIST — System Complete, Ready to Execute

**Status:** All systems built and tested  
**Time estimate:** 60 minutes total  
**Output:** 20–30 approved messages ready to send Day 9  

---

## Pre-Day 8 (5 minutes)

These should already be done, but verify:

- [ ] .env file exists with OPENAI_API_KEY and HUNTER_API_KEY
- [ ] Read DAY8_EXECUTION_GUIDE_V2.md (the step-by-step guide)
- [ ] Read SIGNAL_INTERPRETATION_MAP.md (what failures mean)
- [ ] Read SYSTEM_CLASSIFICATION.md (understand what you built)

---

## Day 8 Execution (60 minutes)

### Step 0: Preflight Check (2 minutes)

```bash
python 04-coding/scripts/preflight_check_day8.py
```

**You should see:**
```
✅ OPENAI_API_KEY: Found
✅ HUNTER_API_KEY: Found (optional)
✅ Dependencies: All present
✅ Directories: All present
✅ READY TO EXECUTE
```

**If you see errors:** Fix them before proceeding. Check .env keys, missing Python packages.

---

### Step 1: Generate Prospects (5 minutes)

```bash
python 04-coding/scripts/prospect_builder.py
```

**You will be prompted:**
```
Use Hunter API? (y/n):
```

**If yes (have Hunter key):** Fetches real prospects from Hunter  
**If no:** Uses template prospects (for demo/testing)  

**Output file:** `06-sales/prospects.csv`

**You should see:** 50 prospects with name, company, role, email

---

### Step 2: Generate Messages (10 minutes)

```bash
python 04-coding/scripts/message_generator_solo.py
```

**What it does:**
- Reads prospects from prospects.csv
- Uses ICP-tuned prompt to generate personalized messages
- Validates each (word count 90–130, CTA present, personalization)
- Marks as PASS, RETRY, or FAIL

**Output file:** `06-sales/generated-outreach.csv`

**You should see:** 20–40 PASS messages, some RETRY or FAIL

---

### Step 3: Sample Quality Gate (5 minutes) ⚠️ CRITICAL

**Open:** `06-sales/generated-outreach.csv`

**Review:** First 5 messages marked as PASS

**For each message, ask yourself:**
> "If I got 100+ cold emails today, would I reply to this?"

**Score:** 0 (no) or 1 (yes)

**Decision:**
- If ≥4/5 score "yes" → proceed to Step 4
- If <4/5 score "yes" → **STOP**, fix prompt, regenerate

**Why:** Prevents approving 30 generic messages and misdiagnosing as system failure on Day 14

---

### Step 4: Review & Approve Messages (30–40 minutes)

```bash
python 04-coding/scripts/review_queue.py
```

**What happens:**
- Shows each PASS message
- You decide: APPROVE (a) or REJECT (r)
- Approved messages added to CSV with `approved: yes` flag
- No editing, binary only

**Target:** Approve 20–30 messages

**Tip:** Be honest. You're not trying to approve everything. You're trying to approve messages you'd actually send.

**Output:** Updated `06-sales/generated-outreach.csv` with `approved` column

---

### Step 5: Verify & Save (2 minutes)

**Check:**
- [ ] prospects.csv has 50+ rows
- [ ] generated-outreach.csv has 20–30 rows with `approved: yes`
- [ ] No errors in any output

**Save:** Backup copies locally if you want (optional)

---

## After Day 8: Day 9 Onward

### Day 9 Morning: First Send

```bash
# Preview (safe, no emails sent)
python 04-coding/scripts/pre_send_check.py
python 04-coding/scripts/run_daily.py bridge status
VENTURE_CANONICAL_ENTRY=1 python 04-coding/scripts/run_daily.py --execute --dry-run

# Actual send
python 04-coding/scripts/pre_send_check.py
VENTURE_CANONICAL_ENTRY=1 python 04-coding/scripts/run_daily.py --execute
```

**What happens:**
- Sends first 20 approved messages
- Logs sends in venture_jobs.db
- Updates execution_state.json

### Days 10–13: Daily Monitoring

```bash
# Each morning or evening
streamlit run 04-coding/scripts/dashboard_streamlit.py
```

**Check:**
- System status (green/yellow/red)
- Issues panel (any warnings?)
- Pipeline progress (sends/replies/calls)

**Log:**
- Replies (when they come in)
- Calls booked (if any)
- Call outcomes (BOOKED / INTERESTED / NOT_NOW / NO_FIT)

### Day 14 Evening: Analysis

```
Open: 03-reevaluation/day14-failure-analysis-template.md
Fill in: Actual metrics (sends, replies, calls, pilots)
Run: Diagnosis tree (answer yes/no questions)
Get: GO / ITERATE / KILL verdict
```

---

## Critical Rules (Don't Skip)

### Rule 1: Preflight Always
Always run pre_send_check before venture_pipeline.

It catches broken states automatically.

### Rule 2: Quality Gate Before Approval
Review first 5 messages manually.

Don't approve 30 generic messages.

### Rule 3: One Variable at a Time
If Day 14 results are bad, change ONE thing:
- ICP (if reply rate low)
- Message (if qualified rate low)
- Call script (if booking rate low)

Not all three.

### Rule 4: Trust the Dashboard Diagnosis
When dashboard shows "ICP mismatch," that's your next hypothesis to test.

It's not absolute truth, but it points you in the right direction.

### Rule 5: Stop When System Says Stop
If pre_send_check shows 🔴 PAUSED, don't override unless you understand why.

That gate exists to prevent wasting volume.

---

## Expected Timeline

**Day 8:**
- 50 min: preflight → prospect → message → review → approve
- 10 min: dashboard setup

**Days 9–13:**
- 10–15 min/day: monitoring + logging

**Day 14:**
- 30 min: fill template, run diagnosis
- 15 min: make GO/ITERATE/KILL decision

**Total:** ~4 hours over 14 days

---

## Success Looks Like

### Best Case (Day 14)
- Sent: 50 messages
- Replies: 5–10 (10–20%)
- Qualified: 3–5 (30–70% of replies)
- Calls: 1–3 booked
- Pilots: 1–2 closed

### Acceptable Case (Day 14)
- Sent: 50 messages
- Replies: 2–5 (4–10%)
- Qualified: 1–2
- Calls: 0–1 booked
- Pilots: 0 closed (but clear next step)

### Failure Case (Day 14)
- Sent: 50 messages
- Replies: 0–1 (0–2%)
- Qualified: 0
- Calls: 0 booked
- Pilots: 0 closed
- → Pivot to warm channel or different ICP

---

## If Something Goes Wrong

### Error: "No module named 'resilience'"
**Fix:** Add sys.path entry to script (already done, but check)

### Error: "OPENAI_API_KEY not found"
**Fix:** Check .env file, make sure key is there, restart terminal

### Error: "Hunter API rate limit"
**Fix:** Use --demo flag instead for testing

### Error: "pre_send_check says PAUSED"
**Fix:** Read the diagnosis. That's your problem. Fix it before sending.

### Dashboard not updating?
**Fix:** Refresh browser tab, or click the refresh button

---

## Mindset Going In

You have built a system that:

1. **Generates qualified candidates** for outbound experiments
2. **Enforces safety constraints** (won't run broken campaigns)
3. **Provides diagnosis** (tells you what's failing)
4. **Lets you execute** when safe
5. **Captures outcomes** for learning

This is not a growth engine yet. It's an experiment runner.

Your job: **Execute faithfully. Measure honestly. Let the data tell you what to build next.**

The system is complete. The learning happens in the market.

---

## You Are Ready

✅ All components built  
✅ All safety gates in place  
✅ All diagnostics defined  
✅ All guides written  

**Run Day 8 tomorrow.**

**Trust the system.**

**Measure the results.**

The next phase starts with real market signal, not more code.

---

**Print this. Follow it exactly. By Day 15, you'll have a clear verdict on whether this ICP works.**

That's the point.

Go execute. 🚀
