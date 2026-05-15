# Launch sign-off — May 18, 2026

One-page operator gate before turning on live sends.

---

## Pre-launch gates (≈ 9:00 AM)

- [ ] `OPERATOR_LAUNCH_READINESS.md` is 100% `[x]` (or you explicitly accept risk with `--skip-checklist` on the executor — not recommended).
- [ ] `python 04-coding/scripts/preflight_safety_check.py --full` shows **no FAIL** rows (WARN/PARTIAL need a conscious decision).
- [ ] Dry-run rehearsal completed: `launch_day_executor.py --outbound-go --dry-run` exited **0** and `run_report.json` looks sane.
- [ ] `launch_monitor.py --live` has been smoke-tested (starts, refreshes, Ctrl+C exits).

---

## Live launch decision (≈ 10:00 AM)

**Before** `python 04-coding/scripts/launch_day_executor.py --outbound-go`:

1. Are you confident in subject + first lines + CTA?
2. Did you see inbox placement on Gmail / Outlook / iCloud (not spam) for a **test** send?
3. Is Calendly live (HTTPS production URL, correct time zone)?
4. Are you ready for a short-term **reply spike** (inbox monitoring)?

**If all YES →** run live at your scheduled window.  
**If any NO →** fix, re-run dry-run, revisit this page.

---

## Live window (scheduled time — hard stop 11:59 PM)

```bash
python 04-coding/scripts/launch_day_executor.py --outbound-go
```

- Watch bounce/complaint ratios in `launch_monitor.py --live`.
- Automatic halt: executor exits **2** if rolling bounce ratio crosses `LAUNCH_BOUNCE_EMERGENCY_RATIO` after a live batch (see `.env`).
- **Kill-switch:**  
  `python 04-coding/scripts/launch_day_executor.py --emergency-pause --pause-reason "bounce_spike"`

---

## Post-launch (May 19–25)

Daily (≈ 2 minutes):

```bash
python 04-coding/scripts/reply_analyzer.py --since-hours 24 --export-csv 07-kpis/replies_daily.csv
```

(Adjust the CSV path if you use `VENTURE_CLIENT_WORKSPACE`.)

Track trends you care about (reply quality, booking language, objections) and feed copy tweaks back into the governed cohort process — not ad-hoc CSV edits.

---

## Sign-off

**Name:** _____________________________  

**Date / time:** _____________________________  

**Status:** GREEN (go) / YELLOW (adjust first) / RED (hold)

**Notes:**

_______________________________________________________________________________

_______________________________________________________________________________
