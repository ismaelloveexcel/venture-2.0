# Simple operator guide (non-technical)

**Read this first.** The other launch files are for audit and for technical people. This page is the **short path**.

---

## What the computer already does for you

- Builds the prospect list and draft emails when you run the one command below (no coding).
- Checks subject line and reply wording against fixed rules.
- Writes a **receipt file** after each run (`run_report.json` in the project folder) so nothing is “invisible.”
- Stops the send if something is badly wrong (wrong list, missing approval, etc.).

You do **not** need to understand git, hashes, or “cohort metadata” to run a normal day.

---

## What you still do (on purpose)

- **Choose who is in the list** (or approve the list someone else prepared).
- **Read the drafts** like a human: true facts only, sounds respectful, not spammy.
- **Say yes to send** after a test email to your own inbox looks right (one-time per batch).
- **Reply to people** who write back (scripts in `06-sales/` if you use them).

Those steps stay manual because **judgment** is the product for Batch 1—not full autopilot.

---

## Normal day (least steps)

### 1) Open two files (double-click or Excel)

- **People:** `06-sales/prospects.csv`  
- **Draft emails:** `06-sales/generated-outreach.csv`  

Skim: names, companies, roles. If a row feels wrong, delete it or mark it so someone technical can remove it properly.

### 2) Run one command (copy-paste into PowerShell)

```powershell
cd "C:\Users\isuda\Dev\VENTURE 2.0"
.venv\Scripts\python.exe 04-coding\scripts\run_daily.py --generate-prospects --prospects-demo --execute-outbound --dry-run
```

- **Dry run** = no real emails; refreshes drafts and checks the pipeline. Use this whenever you want to “practice” or re-check.

### 3) When you are ready for real sends (only after someone technical says Resend/domain is ready)

Same command **without** `--dry-run` at the end, **only** after:

- Test email to **your** inbox looked good (`send_outreach_test` flow in `OPERATOR_RUNBOOK.md`—ask technical once if unsure).
- You are happy with the list and drafts.

```powershell
.venv\Scripts\python.exe 04-coding\scripts\run_daily.py --generate-prospects --prospects-demo --execute-outbound
```

**Stop.** If the window prints errors or “BLOCKED,” do not guess—ask technical or read `OPERATOR_RUNBOOK.md` troubleshooting.

### 4) After sends

- Watch your inbox for replies.
- Log replies using the CSV template in `OPERATOR_RUNBOOK.md` (path to `reply_intent_log`).

---

## If something goes wrong

| You see | What to do |
|--------|------------|
| “BLOCKED” or “FAILED” | Pause. Screenshot or copy the message. Ask technical. |
| Weird or rude draft | Do not send. Fix the row or ask technical to fix the template. |
| Someone asks to stop | Stop immediately. Tell technical to add them to suppression. |

---

## Where the “technical” detail lives (only if needed)

| Topic | File |
|-------|------|
| Full send-off checklist + audit tables | `04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` |
| Commands, Resend, approvals | `OPERATOR_RUNBOOK.md` |
| Why we built it this way | `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` |

---

## Honest note

**“Least manual”** here means: **one main command**, **two CSVs to read**, **no repo surgery**. It does **not** yet mean a consumer app with one big green button—that would be more software build. If you want that next, say so and we scope a **single-button** or **desktop shortcut** layer on top of the same command.
