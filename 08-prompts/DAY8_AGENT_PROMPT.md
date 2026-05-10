# 🤖 DAY 8 AGENT EXECUTION PROMPT

Run this exactly as written. This is a deterministic 60-minute execution with gates.

---

## AGENT INSTRUCTIONS

You are executing the solo founder's Day 8 campaign launch.

**Your role:** Verify system readiness, execute scripts in sequence, validate outputs, report completion status.

**Time budget:** 60 minutes total

**Constraints:** 
- No editing of code or config files
- No skipping preflight checks
- No skipping sample quality gate (Step 3)
- All commands run from repo root

---

## EXECUTION SEQUENCE

### Phase 1: Validation (10 minutes)

**STEP 1: Verify Environment**

Run:
```bash
python 04-coding/scripts/preflight_check_day8.py
```

**Success criteria:**
- All checks pass (✅ OPENAI_API_KEY, ✅ HUNTER_API_KEY, ✅ Dependencies, ✅ Directories)
- Output: "✅ READY TO EXECUTE"

**Failure handling:**
- If any check fails: STOP, report error, don't proceed
- Common fix: Check .env file for missing API keys
- If Hunter API key missing: OK (will use template fallback)

**Agent action:** Report pass/fail status before proceeding

---

### Phase 2: Generate Assets (20 minutes)

**STEP 2: Build Prospect List**

Run:
```bash
python 04-coding/scripts/prospect_builder.py
```

**What you'll see:**
```
Use Hunter API? (y/n):
```

**Decision:**
- If you have HUNTER_API_KEY configured: type `y` (fetches real prospects)
- If no key: type `n` (uses template demo data)

**Success criteria:**
- Script completes without error
- Creates file: `06-sales/prospects.csv`
- File contains 50 rows with columns: name, company, role, email, domain, readiness_status

**Agent action:** Verify file exists and has 50+ rows

---

**STEP 3: Generate Messages**

Run:
```bash
python 04-coding/scripts/message_generator_solo.py
```

**What happens:**
- Reads from `06-sales/prospects.csv`
- Generates personalized message for each prospect
- Validates each (word count, CTA presence, personalization)
- Outputs status: PASS, RETRY, or FAIL

**Success criteria:**
- Script completes
- Creates file: `06-sales/generated-outreach.csv`
- File contains 30–50 rows
- At least 20 rows marked as PASS status

**Agent action:** Report total generated, PASS/RETRY/FAIL breakdown

---

### Phase 3: Quality Gate (5 minutes) ⚠️ CRITICAL GATE

**STEP 4: Sample Review (Manual, Non-Automatable)**

**OPERATOR ACTION REQUIRED** (agent cannot automate this)

Open file: `06-sales/generated-outreach.csv`

Select: First 5 rows marked `status: PASS`

For each message, score: 0 (wouldn't reply) or 1 (would reply)

Decision rule:
- If ≥4/5 messages score "1" → GO to Step 5
- If <4/5 messages score "1" → STOP, report quality issue

**Agent responsibility:** Prompt operator to review, wait for confirmation before proceeding

**Report:** "Sample quality gate: X/5 messages scored 'would reply' — GO / NO-GO"

---

### Phase 4: Approve Messages (30 minutes)

**STEP 5: Binary Review & Approval**

Run:
```bash
python 04-coding/scripts/review_queue.py
```

**What happens:**
- Shows each PASS message one by one
- Operator inputs: `a` (approve) or `r` (reject)
- No editing allowed, binary only
- Updates `06-sales/generated-outreach.csv` with `approved: yes/no` column

**Target:** Approve 20–30 messages

**Success criteria:**
- Script completes
- `06-sales/generated-outreach.csv` updated with `approved` column
- At least 20 rows marked `approved: yes`
- Zero rows marked `approved: yes` have blank messages

**Agent action:** 
- Monitor completion
- Report final count: "20–30 messages approved"
- Flag if approval count <15 (too few to reach 50 sends)

---

### Phase 5: Verify & Close (5 minutes)

**STEP 6: Final Verification**

Check all outputs:

```bash
# Check prospect count
wc -l 06-sales/prospects.csv

# Check message count
wc -l 06-sales/generated-outreach.csv

# Check approved count (if needed)
grep "approved.*yes" 06-sales/generated-outreach.csv | wc -l
```

**Success criteria:**
- prospects.csv: ≥50 rows
- generated-outreach.csv: ≥20 rows with `approved: yes`
- No errors in any file

**Agent action:** Verify all files exist and report summary

---

## SUMMARY REPORT (Agent Output)

After completion, generate this report:

```
═══════════════════════════════════════════════════════════
DAY 8 EXECUTION REPORT
═══════════════════════════════════════════════════════════

⏱️  TIME ELAPSED: [X minutes]

✅ PREFLIGHT CHECK: PASSED
   - OPENAI_API_KEY: [Found/Missing]
   - HUNTER_API_KEY: [Found/Missing]
   - Dependencies: [All present]

✅ PROSPECT GENERATION: PASSED
   - Prospects generated: 50
   - File location: 06-sales/prospects.csv

✅ MESSAGE GENERATION: PASSED
   - Messages generated: [X total]
   - Status breakdown: [Y PASS, Z RETRY, W FAIL]
   - File location: 06-sales/generated-outreach.csv

✅ SAMPLE QUALITY GATE: PASSED (or FAILED)
   - Sample score: X/5 messages would reply
   - Decision: GO to approval

✅ MESSAGE APPROVAL: PASSED
   - Messages approved: [20–30]
   - Approval rate: [X%]
   - File updated: 06-sales/generated-outreach.csv

✅ FINAL VERIFICATION: PASSED
   - prospects.csv: 50 rows ✓
   - generated-outreach.csv: [X] approved rows ✓
   - No errors ✓

═══════════════════════════════════════════════════════════
STATUS: ✅ DAY 8 COMPLETE — READY FOR DAY 9 SEND
═══════════════════════════════════════════════════════════

NEXT STEPS (Day 9):
1. Run: python pre_send_check.py
2. Run: python venture_pipeline.py
3. Monitor: streamlit run dashboard_streamlit.py

Key metrics to track Days 9–14:
- Sends: Target 50 by Day 13
- Replies: Target 5–10 by Day 14
- Calls: Target 1–3 by Day 14
```

---

## ABORT CONDITIONS

Stop execution immediately if:

- ❌ Preflight check fails
- ❌ Prospect file doesn't contain 50 rows
- ❌ Fewer than 20 PASS messages generated
- ❌ Sample quality gate fails (≥4/5 threshold not met)
- ❌ Fewer than 15 messages approved in Step 5

If any abort condition triggered: Report reason and halt. Do not proceed to Day 9 launch.

---

## SUCCESS DEFINITION

Day 8 is complete when:

```
✅ 50 prospects generated
✅ 20–30 messages approved
✅ All files verified
✅ Sample quality gate passed
✅ Zero errors in logs
```

All five conditions must be TRUE.

---

## NOTES FOR AGENT

1. **You cannot automate Step 4 (sample quality gate).** Operator must manually review first 5 messages and score them. Wait for input before proceeding.

2. **No modifications to code.** If there's an error, report it and stop. Don't try to fix the script.

3. **Times are estimates.** If execution takes 90 minutes instead of 60, that's OK. Report actual time.

4. **Template data is acceptable.** If Hunter API is missing, using template prospects is fine for Day 8 testing.

5. **Report every step completion** before proceeding to next step.

---

Good luck. Execute faithfully. 🚀
