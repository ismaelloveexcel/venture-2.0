# Day 8 Execution Scripts (Solo Operator) — UPDATED WITH CRITICAL FIXES

**Three-script execution pack for Day 8–14 automation** (version 2.0: fixes integrated).

---

## 📋 Scripts Overview

### 0. `preflight_check_day8.py` (RUN FIRST) — ✅ NEW
**Purpose:** Validate all keys, paths, and dependencies before execution

**What it does:**
- Checks OPENAI_API_KEY and HUNTER_API_KEY in .env
- Validates Python dependencies (dotenv, httpx, resilience)
- Confirms directories exist (06-sales, 07-kpis)
- Reports clear pass/fail + next steps

**Usage:**
```bash
python 04-coding/scripts/preflight_check_day8.py
```

**Expected output:** `[✅] ALL CHECKS PASSED` or `[❌] SOME CHECKS FAILED` with fix instructions

---

### 1. `prospect_builder.py` — ✅ FIXED (--demo, --input-csv modes)
**Purpose:** Source and validate prospects using rule-based filtering

**What it does:**
- Pulls prospects from Hunter.io API, template data, or your own CSV
- Applies hard rules: READY | REVIEW | REJECT
- Outputs: `06-sales/prospects.csv` with readiness_status

**Rules:**
- READY: valid email + domain + decision-maker role
- REVIEW: missing email but strong domain + role
- REJECT: missing company, domain, role, or non-decision role

**Usage:**
```bash
# Using Hunter API (if HUNTER_API_KEY is set in .env):
python 04-coding/scripts/prospect_builder.py

# Using template data (demo/testing only):
python 04-coding/scripts/prospect_builder.py --demo

# Import your own CSV:
python 04-coding/scripts/prospect_builder.py --input-csv path/to/your-prospects.csv
```

**Output:** `06-sales/prospects.csv` with READY/REVIEW/REJECT classification

**⚠️ For paid execution:** Use `--input-csv` with real prospects (not --demo)

---

### 2. `message_generator_solo.py` — ✅ FIXED (sys.path import)
**Purpose:** Generate and validate messages (3-tier output)

**What it does:**
- Generates messages using ICP prompt from `day8-launch-pack.md`
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

**Output:** `06-sales/generated-outreach.csv` with message, status, and auto_score

**Note:** Reads prospects from `06-sales/prospects.csv` (run prospect_builder first)

---

### 3. `review_queue.py` — ✅ FIXED (approved column instead of separate CSV)
**Purpose:** Ultra-simple review interface (binary decisions only)

**What it does:**
- Displays each PASS message one at a time
- Operator: type 'a' (APPROVE) or 'r' (REJECT)
- Updates `06-sales/generated-outreach.csv` with approval status ("approved" column: yes/no)
- Optional: log call outcomes with `--log-calls` flag

**Usage:**
```bash
# Review and approve messages:
python 04-coding/scripts/review_queue.py

# Log call outcomes (BOOKED | INTERESTED | NOT_NOW | NO_FIT):
python 04-coding/scripts/review_queue.py --log-calls
```

**Output:** 
- Updated `06-sales/generated-outreach.csv` with "approved" column (yes/no)
- Optional `07-kpis/call-log.csv` for call tracking

**🔑 Key change:** Marks messages in the original CSV (no separate file). Integrates directly with venture_pipeline.py.

---

## 🚀 Execution Sequence (Day 8)

### Step 0: Preflight Check (2 minutes) — ✅ REQUIRED FIRST
```bash
python 04-coding/scripts/preflight_check_day8.py
```

**Expected output:** 
```
[✅] ALL CHECKS PASSED - Ready for Day 8 execution!
```

**If it fails:** Fix the issues (usually missing OPENAI_API_KEY in .env) and rerun before proceeding.

---

### Step 1: Build Prospect List (5 minutes)
```bash
# Option A: If you have HUNTER_API_KEY in .env:
python 04-coding/scripts/prospect_builder.py

# Option B: If you don't have Hunter API yet (testing only):
python 04-coding/scripts/prospect_builder.py --demo

# Option C: If you have your own CSV (RECOMMENDED for paid pilots):
python 04-coding/scripts/prospect_builder.py --input-csv 06-sales/my-prospects.csv
```

**Expected output:** 30-50 READY prospects in `06-sales/prospects.csv`

---

### Step 2: Generate Messages (10 minutes)
```bash
python 04-coding/scripts/message_generator_solo.py
```

**Expected output:** Generated messages in `06-sales/generated-outreach.csv` with status (PASS | RETRY | FAIL)

---

### Step 3: Sample Quality Gate (5 minutes) — ✅ NEW CRITICAL STEP
**Before reviewing all messages, spot-check quality:**

1. Open `06-sales/generated-outreach.csv` in a text editor or spreadsheet
2. Look at **first 5 PASS messages**
3. **FOR EACH MESSAGE, ask yourself: "If I received 100+ cold emails today, would I reply to this one?"**
   - Rate each 0 = "No" or 1 = "Yes"
   - You need ≥4/5 scoring as "Yes" to proceed
4. Decision:
   - If **≥4/5 are "Yes"** → Proceed to Step 4 (approval feels solid)
   - If **<4/5 are "Yes"** → **STOP.** Fix messaging or ICP. Don't approve generics.

**Why this threshold:** At 80%+ quality in sample, full batch approval will be defensible. Below 80%, you're entering "approval drift" zone.

**Why this matters:** On Day 14, if reply rate is low, you'll wonder: "Was it bad targeting or bad messaging?" Clear sample gate now = clear diagnosis later.

**Why:** Prevents sending 50 mediocre messages that tank reply rate on Day 9.

---

### Step 4: Review & Approve (20-30 minutes)
```bash
python 04-coding/scripts/review_queue.py
```

**For each message:**
- Read it
- Type **'a'** (approve) or **'r'** (reject)
- Press Enter
- Move to next

**Expected:** 20-30 approved messages (out of 40-50 PASS messages)

**Output:** `06-sales/generated-outreach.csv` now has "approved" column (yes/no)

---

### Step 5: Send (Automated) — Day 9
```bash
# Preview (no emails sent):
python 04-coding/scripts/venture_pipeline.py --dry-run

# Verify no errors, then send:
python 04-coding/scripts/venture_pipeline.py
```

Sends approved messages (20/day cap, configurable in .env)

**🔑 Changed:** No `--send-batch` flag needed. Pipeline reads "approved" column from CSV.

---

### Step 6: Log Call Outcomes (As calls come in) — Days 10-14
```bash
python 04-coding/scripts/review_queue.py --log-calls
```

Enter: prospect name, company, outcome (BOOKED|INTERESTED|NOT_NOW|NO_FIT), notes

---

## ⏱️ Operator Time Budget

| Task | Time | Frequency |
|------|------|-----------|
| Preflight check | 2 min | Day 8 (once) |
| Prospect sourcing | 5 min | Day 8 (once) |
| Message generation | 10 min | Day 8 (once) |
| Sample quality gate | 5 min | Day 8 (once) |
| Message review | 20-30 min | Day 8 (once) |
| Call logging | 5 min/call | Daily (as needed) |
| Daily scorecard | 5 min | Daily |

**Total Day 8:** ~50-60 minutes  
**Daily overhead post-Day 8:** ~10-15 minutes

---

## 🔧 Configuration

All scripts read from `.env` (repo root):
- `OPENAI_API_KEY` — message generation (REQUIRED)
- `HUNTER_API_KEY` — prospect sourcing (optional; use --demo if missing)

**To set keys:**
1. Get OPENAI_API_KEY from openai.com/account
2. Get HUNTER_API_KEY from hunter.io (optional)
3. Add to `.env`:
   ```
   OPENAI_API_KEY=sk-xxx
   HUNTER_API_KEY=xxx
   ```
4. Run preflight check to validate

No additional setup needed.

---

## 📊 Expected Outcomes

**After Day 8 (prospect sourcing + generation + review):**
- Input: 50–100 raw prospects
- After validation: 30–50 READY prospects
- After generation: 30–50 messages (60–70% PASS rate)
- After sample gate: Quality culled to strongest 80%
- After review: 20–30 approved messages

**Quality metrics:**
- Generation pass rate: 60–70% (normal)
- Approval rate: 60–80% (your decision)
- Rejection rate: 20–40% (builds discipline)

**After Day 9 (send first 20):**
- Send cap: 20 messages
- Expected replies: 1–3 (5–15% reply rate, ICP-dependent)
- Expected calls booked: 0–1

---

## 🚫 Anti-Patterns (Do NOT Do)

❌ **Skip preflight check** — won't catch key/import issues early  
❌ **Edit messages in review** — causes scope creep  
❌ **Skip the sample quality gate** — risks sending 50 mediocre messages  
❌ **Add extra validation layers** — defeats simplicity  
❌ **Use template data (--demo) for paid pilots** — contaminate with fake domains  
❌ **Sync to Notion yet** — Phase 2, after signal validation at Day 14  
❌ **Regenerate prospects daily** — validate once per pilot batch  

---

## ⚠️ Troubleshooting

### "OPENAI_API_KEY not found" / ImportError
**Fix:** 
1. Run preflight check: `python preflight_check_day8.py`
2. Add key to `.env`
3. Rerun script

### "ModuleNotFoundError: resilience"
**Fix:** Verify `venture-mcp-server/` directory exists in repo root. Should be at `c:\Users\isuda\Dev\VENTURE 2.0\venture-mcp-server\`.

### "No READY prospects after filtering"
**Fix:** 
- Try `--demo` flag (uses template data for testing)
- Or check your CSV has required fields: company_name, domain, role, email

### "Generated messages are all generic"
**Fix:** Review first 5 messages manually (Step 3). If generic, either:
- Adjust ICP prompt in `day8-launch-pack.md`
- Source better prospects with more specific pain signals

---

## ✅ Validation Checklist (Before Day 9 Send)

- [ ] Preflight check passed (`[✅] ALL CHECKS PASSED`)
- [ ] `06-sales/prospects.csv` has 30+ READY rows
- [ ] `06-sales/generated-outreach.csv` has 60+ PASS messages
- [ ] Sample quality gate reviewed (first 5 messages seem compelling, not generic)
- [ ] 20–30 messages approved via review_queue.py
- [ ] `06-sales/generated-outreach.csv` has "approved" column (yes/no values)

**All checks pass? Ready for Day 9 send.**

---

## 📖 Next Steps

1. **Day 8 (Today):** Run steps 0-4 (50-60 min)
2. **Days 9–14:** Send messages, handle replies, run calls, log outcomes
3. **Day 14 (Evening):** Use [day14-failure-analysis-template.md](../../03-reevaluation/day14-failure-analysis-template.md) to diagnose results
4. **Day 15:** Decide GO / ITERATE / KILL based on template

**⚠️ Important:** Don't skip the Day 14 analysis. It prevents misdiagnosing system failure vs. ICP failure.

See [day14-failure-analysis-template.md](../../03-reevaluation/day14-failure-analysis-template.md) for decision framework.

---

## 🎯 Three Critical Fixes Applied

**FIX #1:** `review_queue.py` now marks approved messages in the CSV (no separate file). Integrates with venture_pipeline.py correctly.

**FIX #2:** `message_generator_solo.py` now imports `resilience` with correct sys.path (matching venture_pipeline.py pattern).

**FIX #3:** `prospect_builder.py` now has `--demo` flag to prevent accidental fake domain emails. Use `--input-csv` for real prospects.

---

**You are fully execution-ready. Deploy today.**
