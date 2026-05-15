# Launch day runbook — May 18, 2026 (hard stop 11:59 PM local)

This runbook is the **operator-facing** sequence for go-live. Technical paths live under `04-coding/scripts/` and `AGENTS.md`.

---

## Timeline (suggested)

| Time | Action |
|------|--------|
| 9:00 AM | Open `OPERATOR_LAUNCH_READINESS.md` — confirm every line is `[x]`. |
| 9:30 AM | Start `python 04-coding/scripts/launch_monitor.py --live` in a second terminal (refresh every 10s). |
| 10:00 AM | Rehearsal: `python 04-coding/scripts/launch_day_executor.py --outbound-go --dry-run` — inspect printed summary and `run_report.json`. |
| 10:30 AM | **Decision:** Is the dry-run acceptable (counts, blocks, no surprise errors)? If **no**, fix copy or config and repeat rehearsal. |
| 11:00 AM | **Live:** `python 04-coding/scripts/launch_day_executor.py --outbound-go` — sends begin; watch the monitor for bounce and complaint ratios. |
| Any time | **Kill-switch:** `python 04-coding/scripts/launch_day_executor.py --emergency-pause --pause-reason "…"` — freezes outreach and marks session paused. |
| 11:59 PM | **Hard stop** — no new live sends after this time unless you explicitly change policy and re-arm. |

---

## Emergency procedures

- **Bounce ratio above launch threshold** (default 5% rolling, see `LAUNCH_BOUNCE_EMERGENCY_RATIO` in `.env`): run `--emergency-pause`, then inspect cohort copy, domain reputation, and `run_report.json` / `venture_jobs.db` webhook history.
- **Complaint ratio above threshold** (default 0.3% rolling): pause immediately; review CAN-SPAM posture, footer, and list-unsubscribe.
- **Reply rate far below expectation after 24h:** consider subject and first-line copy; only re-run live sends if policy and locks allow (do not bypass gates).

---

## Post-launch (May 19 onward)

- Run `weekly_optimizer.py` on a schedule you can keep (weekly minimum) to refresh optimizer hints and reply-intent retrain output.
- Review `run_report.json` **outbound.funnel_health_snapshots** for send vs block trends.
- Track business outcomes (replies, meetings, revenue) outside this repo in your CRM or spreadsheet.

---

## Commands (quick reference)

```text
python 04-coding/scripts/preflight_safety_check.py --quick
python 04-coding/scripts/preflight_safety_check.py --full
python 04-coding/scripts/launch_day_executor.py --outbound-go --dry-run
python 04-coding/scripts/launch_day_executor.py --outbound-go
python 04-coding/scripts/launch_day_executor.py --emergency-pause --pause-reason "operator_hold"
python 04-coding/scripts/launch_monitor.py --live
python 04-coding/scripts/reply_analyzer.py --since-hours 24 --export-csv 07-kpis/replies_daily.csv
python 04-coding/scripts/run_daily.py bridge validate
```

Full validation before merge is documented in `AGENTS.md`.
