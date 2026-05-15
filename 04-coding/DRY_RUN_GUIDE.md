# Dry-run rehearsal guide — before live launch

## What is a dry-run?

- Generates prospects and assembles outbound messages through the normal `run_daily.py` path.
- **Does not** POST to Resend for live delivery when you pass `--dry-run` (no sender reputation risk from real sends).
- Exercises suppression re-checks, MIME assembly, batch locks, and `run_report.json` in a safe mode.

## Prerequisites

1. Run `python 04-coding/scripts/preflight_safety_check.py --quick` and fix any **FAIL** rows (see printed verdict).
2. Prefer `OPERATOR_LAUNCH_READINESS.md` fully checked `[x]` before you treat rehearsal as “launch ready”.
3. Optional: keep `python 04-coding/scripts/launch_monitor.py --live` open in a second terminal.

## Command

```bash
python 04-coding/scripts/launch_day_executor.py --outbound-go --dry-run
```

(Equivalent: `python 04-coding/scripts/run_daily.py --generate-prospects --execute-outbound --dry-run`.)

## What “good” looks like (illustrative)

Your timestamps and counts will differ. Focus on **exit code 0**, **no stderr tracebacks**, and a **dry-run** flag in the report.

```text
[9:32 AM] Launching rehearsal (dry-run, no live Resend POSTs)…
[9:32 AM] Preflight: DB reachable, session not PAUSED
[9:33 AM] Running: python run_daily.py --generate-prospects --execute-outbound --dry-run
… pipeline logs …
[10:15 AM] Rehearsal subprocess exit code: 0
[10:15 AM] Loaded run_report.json
[10:15 AM] outbound.dry_run = true
[10:15 AM] outbound.money_path.sent = 0 (live sends not executed; telemetry may still show attempted/blocked rehearsal counts)
[10:15 AM] outbound.prospect_batch.* populated when prospect_builder ran
[10:15 AM] No Python tracebacks above this line
[10:15 AM] REHEARSAL COMPLETE — review report, then decide on live send timing
```

## Inspect after rehearsal

1. **`run_report.json`** (repo root or `clients/<id>/` if you use `VENTURE_CLIENT_ID`):
   - `outbound.dry_run` should be **true**.
   - `outbound.pipeline_telemetry` and `outbound.prospect_batch` show what the child reported.
   - `outbound.funnel_health_snapshots` may contain rehearsal rows (append-only).
2. **Logs** under `logs/` or `logs/dry_run/` if your run produced artifacts — scan for unexpected `FAILED` or policy skips.
3. **Spot-check** one rendered message (from logs or allowed preview path your operator uses): subject, preview discipline, Calendly link placement, list-unsubscribe footer if enabled.

## If rehearsal fails

- Copy the **full** terminal output (or `venture-pipeline` / `run_daily` stderr tail) into a ticket or chat.
- Common causes: missing API keys for generation, strict prospect CSV gates, batch lock mismatch, or SQLite locked by another process.

## When rehearsal is clean

- Return to `LAUNCH_DAY_2026-05-18_FINAL_RUNBOOK.md` for the live decision and timing.
- Live sends: `python 04-coding/scripts/launch_day_executor.py --outbound-go` (no `--dry-run`) only after checklist + preflight are green.
