# 📊 Execution Dashboard — User Guide

**Purpose:** One-screen control panel showing you exactly what to do next during Days 8–14

---

## How to Run

### Terminal command:
```bash
streamlit run 04-coding/scripts/dashboard_streamlit.py
```

This opens at: **http://localhost:8501**

Stop it: Press `Ctrl+C`

---

## What You See (7 Sections)

### 1️⃣ SYSTEM STATUS BAR (Top)
**Shows:** Current stage (NOT STARTED / REVIEWING / READY TO SEND)

**Tells you:** Where you are in the process

---

### 2️⃣ NEXT ACTION BOX (Most Important)
**Shows:** Exactly one thing to do next

**Tells you:** No confusion about what to do

Examples:
- "Run preflight check"
- "Review & approve messages" 
- "Ready to send (Day 9)"

---

### 3️⃣ PIPELINE FLOW
**Shows:** Counts at each stage

Example:
```
PROSPECTS    MESSAGES    PASS    APPROVED    CALLS    PILOTS
    50          32       20        18          1         0
```

**Tells you:** Progress through the funnel

---

### 4️⃣ ISSUES PANEL
**Shows:** Anything broken or needs attention

Green (✅): No issues  
Yellow (🟡): Warning (e.g., "only 40 prospects generated")  
Red (❌): Blocker (e.g., "no prospect file found")

---

### 5️⃣ PROGRESS TOWARDS GOAL
**Shows:** How many pilots you have vs. target (5)

**Tells you:** Are you on track by Day 14?

---

### 6️⃣ RECENT ACTIVITY
**Shows:** When each file was last updated

**Tells you:** System is running or stale

---

### 7️⃣ QUICK DIAGNOSTIC
**Shows:** What different outcomes mean

Use when Day 14 results arrive.

---

## Daily Workflow

### Day 8
1. Open dashboard: `streamlit run dashboard_streamlit.py`
2. Follow "NEXT ACTION" box step by step
3. Refresh dashboard after each script completes
4. When "NEXT ACTION" says "Ready to send", move to Day 9

### Days 9–14
1. Open dashboard each morning
2. Check "SYSTEM STATUS" (should stay green)
3. Check "ISSUES" (should be clear)
4. Log any calls in your call-log.csv
5. Refresh dashboard to see updated counts

### Day 14 Evening
1. Check "PROGRESS TOWARDS GOAL" (how many pilots?)
2. Use "QUICK DIAGNOSTIC" to interpret results
3. Decide: GO / ITERATE / KILL (see day14-failure-analysis-template.md)

---

## Tips

### Refresh doesn't work?
- Close and reopen browser tab
- Or click "🔄 Refresh Dashboard" button

### Dashboard says "ERROR"?
- Check that your CSV files exist:
  - `06-sales/prospects.csv`
  - `06-sales/generated-outreach.csv`
  - `07-kpis/call-log.csv` (optional, created after first call)

### Why can't I see my data?
- You may need to refresh your browser (`F5`)
- Or re-run the dashboard

---

## What NOT to Do

❌ Don't open the old HTTP dashboard (different system)  
❌ Don't edit CSVs while dashboard is running (refresh may fail)  
❌ Don't panic if numbers stay low (you need ≥50 sends first)

---

## Keyboard Shortcuts (Streamlit)

- `R`: Hard refresh (clears cache)
- `Ctrl+C`: Stop the dashboard

---

**This is your control panel for Days 8–14. Keep it open, check it daily, follow NEXT ACTION.**
