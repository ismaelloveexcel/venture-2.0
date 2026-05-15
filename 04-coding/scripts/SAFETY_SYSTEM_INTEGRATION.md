# 🔗 Three-Layer Safety System — Integration Guide

**Status:** ✅ Complete  
**Complexity:** Minimal (no rewrites, pure additions)  
**Time to deploy:** <5 minutes

---

## What You Just Built

Three files that work together to create **self-correcting execution**:

```
execution_state.json
        ↓
   signal_rules_engine.py ← SIGNAL_RULES.md
        ↓
   pre_send_check.py + dashboard_streamlit.py
```

---

## The 3 Files

### 1. **execution_state.json** (State Container)

**What it is:** Single source of truth for system state

**Lives at:** `/execution_state.json` (repo root)

**Contains:**
- Current day (8–14)
- Prospect pipeline metrics
- Message metrics
- Approval rates
- Send rates
- Reply counts
- Call counts
- Pilot counts
- System diagnostics

**Who updates it:** venture_pipeline.py (after each run)

**Who reads it:** dashboard + pre_send_check

### 2. **SIGNAL_RULES.md** (Decision Rules)

**What it is:** Hard-coded thresholds that trigger diagnostics or pauses

**Lives at:** `03-reevaluation/SIGNAL_RULES.md`

**Contains:**
- HARD STOP rules (auto-pause if triggered)
- WARNING rules (red flag, investigate)
- INFO rules (monitoring)
- Thresholds for each metric
- Why each rule exists

**Examples:**
- "If 25+ sends and 0 replies → PAUSE"
- "If reply rate < 3% → WARNING"
- "If approval rate < 20% → PAUSE"

### 3. **signal_rules_engine.py** (Rules Evaluator)

**What it is:** Python module that evaluates rules against state

**Lives at:** `04-coding/scripts/signal_rules_engine.py`

**Does:**
- Loads execution_state.json
- Evaluates all rules in SIGNAL_RULES.md
- Returns: severity + primary diagnosis + all triggered rules
- Used by: dashboard + pre_send_check

**Key functions:**
```python
engine.should_pause_execution()  # True if HARD_STOP triggered
engine.get_primary_diagnosis()   # String for dashboard
engine.evaluate_all()            # Return all triggered rules
```

---

## How It Works Together

### Scenario: Day 10, You're Sending Batch #2

#### Step 1: Run pre-send check (new!)
```bash
python 04-coding/scripts/pre_send_check.py
```

**What happens:**
1. Loads execution_state.json
2. Evaluates signal rules
3. If HARD_STOP triggered → refuse to proceed
4. If WARNING → ask for confirmation
5. If OK → green light

**Example output:**
```
🧭 PRE-SEND SAFETY CHECK
📊 System Health: WARNING
💡 Primary Diagnosis: Low reply rate 0% (ICP misaligned)
   W-1: Review targeting, tighten ICP

⚠️  WARNING: Issues detected
    Use --force to override and send anyway
    Or fix the issue and re-run
```

#### Step 2: If cleared, run pipeline
```bash
python 04-coding/scripts/run_daily.py bridge status
VENTURE_CANONICAL_ENTRY=1 python 04-coding/scripts/run_daily.py --execute
```

**What happens:**
- Sends approved messages
- Tracks sends, replies, calls
- Updates execution_state.json with new metrics

#### Step 3: Dashboard refreshes automatically
```bash
streamlit run 04-coding/scripts/dashboard_streamlit.py
```

**What happens:**
- Reads execution_state.json
- Evaluates signal rules
- Shows issues at top (🔴 = HARD_STOP, 🟡 = WARNING)
- Displays diagnosis + recommended action

---

## Daily Workflow (With Safety System)

### Day 8: Generate & Approve
```
preflight_check → prospect_builder → message_generator → review_queue
(same as before, no changes)
```

### Day 9: First Send
```
Step 1: python pre_send_check.py          (new: clear to send?)
Step 2: python run_daily.py bridge status
Step 3: VENTURE_CANONICAL_ENTRY=1 python run_daily.py --execute --dry-run (preview)
Step 4: VENTURE_CANONICAL_ENTRY=1 python run_daily.py --execute            (actually send)
Step 5: streamlit run dashboard_streamlit  (monitor)
```

### Days 10–13: Daily Check
```
Each morning:
  streamlit run dashboard_streamlit.py
  → check Issues panel (red/yellow/green)
  → if red → don't send (pre_send_check will block anyway)
  → if yellow → review issue, decide yes/no
  → if green → proceed with pre_send_check → send
```

### Day 14: Diagnosis
```
Fill day14-failure-analysis-template.md using actual numbers
Make GO / ITERATE / KILL decision
```

---

## Key Benefits

| Benefit | How | Impact |
|---------|-----|--------|
| **Single truth** | execution_state.json | No CSV drift, dashboard always current |
| **Failure detection** | signal_rules_engine.py | Catches problems automatically |
| **Auto-pause** | pre_send_check.py | Prevents wasting volume on broken campaigns |
| **Operator simplicity** | Dashboard shows diagnosis | No guessing "what went wrong?" |
| **Deterministic** | SIGNAL_RULES.md | Same rules every time, no emotion |

---

## Integration Checklist

- [ ] execution_state.json exists (auto-created)
- [ ] SIGNAL_RULES.md in 03-reevaluation/
- [ ] signal_rules_engine.py in scripts/
- [ ] pre_send_check.py in scripts/
- [ ] dashboard_streamlit.py updated to import signal engine
- [ ] Test pre_send_check: `python scripts/pre_send_check.py`
- [ ] Test dashboard: `streamlit run scripts/dashboard_streamlit.py`
- [ ] run_daily status can run (`python scripts/run_daily.py bridge status`)
- [ ] canonical execute can run (`VENTURE_CANONICAL_ENTRY=1 python scripts/run_daily.py --execute --dry-run`)

---

## Testing the Safety System

### Test 1: Zero-Reply Scenario
```bash
# Manually edit execution_state.json:
# Set sends: 30, replies: 0

# Run dashboard:
streamlit run scripts/dashboard_streamlit.py

# You should see:
# 🔴 EXECUTION PAUSED
# HS-1: Zero replies after 30 sends
```

### Test 2: Low Reply Rate Warning
```bash
# Edit execution_state.json:
# Set sends: 20, replies: 0

# Run pre_send_check:
python scripts/pre_send_check.py

# You should see:
# ⚠️  WARNING: Low reply rate
```

### Test 3: All Clear
```bash
# Edit execution_state.json:
# Set sends: 20, replies: 3 (15% reply rate)

# Run pre_send_check:
python scripts/pre_send_check.py

# You should see:
# ✅ READY TO SEND
```

---

## Where It Fits in the Stack

```
┌─ DAY 8 EXECUTION
│  ├ preflight_check_day8.py (keys, imports)
│  ├ prospect_builder.py (get prospects)
│  ├ message_generator_solo.py (generate)
│  └ review_queue.py (approve)
│
├─ DAYS 9-14 EXECUTION (NEW SAFETY)
│  ├ pre_send_check.py ← NEW (gate before pipeline)
│  ├ venture_pipeline.py (send approved)
│  ├ execution_state.json ← NEW (state container)
│  ├ signal_rules_engine.py ← NEW (evaluate rules)
│  └ dashboard_streamlit.py (monitor with diagnostics)
│
└─ DAY 14 DECISION
   ├ day14-failure-analysis-template.md (diagnose)
   └ SIGNAL_INTERPRETATION_MAP.md (what to fix)
```

---

## Final Status

✅ **Execution system now self-correcting**

- Single source of truth (execution_state.json)
- Hard rules for pause/warn/proceed (SIGNAL_RULES.md)
- Automatic diagnosis (signal_rules_engine.py)
- Kill-switch enforcement (pre_send_check.py)
- Dashboard integration (dashboard_streamlit.py updated)

---

**You can now run Day 8–14 without worrying about:**
- Silent failures (system pauses automatically)
- Missing diagnostics (rules explain what's wrong)
- Wasted volume (kill-switch prevents bad campaigns)
- Operator guessing (rules are deterministic)

Stop building. Start executing. 🚀
