# Launch Day Gates — 2026-05-18
## Operator checklist: one gate at a time, in order

Status key: [ ] = pending  [x] = passed  [!] = blocked

---

## GATE 1 — ICP Lock (DONE)
[x] `launch_execution_state.json` → `landing_icp = locked`, `cohort_id = cohort_001`
[x] `offer.config.json` committed, no further edits during launch window
[x] ICP one-liner: "Founder-led B2B service firms (agencies, consulting, dev shops, recruiters) losing deals to slow lead response"

---

## GATE 2 — Real Prospect Data (BLOCKER — operator action required)

**Current state:** 48 rows, all `source = demo_template`. Pipeline will not send to fake data.

Required before proceeding:
[ ] Replace `06-sales/prospects.csv` with 20–30 real verified rows
[ ] Each row must have:
    - company_name, domain, name, email, role, industry, pain_signal
    - role ∈ { founder, owner, head of sales, managing director }
    - industry ∈ { agency, consulting, dev shop, recruitment }
    - email deliverability verified (Hunter.io or manual check)
    - source ≠ demo_template
[ ] Run: `.venv\Scripts\python.exe 04-coding/scripts/run_daily.py bridge validate`
[ ] Confirm: zero demo_template rows in final CSV

**Sources to use:**
- Apollo.io (free tier) — filter by company size 1–50, industry above
- LinkedIn Sales Navigator free search
- Hunter.io domain search
- Manual research (company website → team page)

---

## GATE 3 — Pre-Send Dry Run (operator runs this)

Run exactly:
```
set VENTURE_CANONICAL_ENTRY=1
.venv\Scripts\python.exe 04-coding/scripts/run_daily.py --generate-prospects --execute-outbound --dry-run --report-path .\run_report.json
```

Pass criteria:
[ ] Exit code 0
[ ] `run_report.json` → `outbound_state = SUCCESS`
[ ] `sent = 0` (dry-run)
[ ] `blocked = 0`
[ ] No exceptions in logs

---

## GATE 4 — SAFE_MODE Reset (operator action — do this AFTER Gate 2 + 3 pass)

Current: `policy.json` → `mode = SAFE_MODE`, `manual_reset_required = true`

To reset:
[ ] Open `04-coding/venture-engine/config/policy.json`
[ ] Set: `"mode": "LIVE"`, `"send_velocity": "normal"`, `"manual_reset_required": false`
[ ] Confirm DNS verified: `RESEND_DOMAIN_VERIFIED=true` already set in `.env`
[ ] Confirm: `AUTO_SEND_EMAILS=true` in `.env` (currently false — flip this only after Gate 3 passes)

---

## GATE 5 — First Live Send (20–30 prospects)

Run:
```
set VENTURE_CANONICAL_ENTRY=1
.venv\Scripts\python.exe 04-coding/scripts/run_daily.py --execute-outbound --report-path .\run_report.json
```

Monitor immediately:
[ ] `sent` count in `run_report.json` increments (target 20–30)
[ ] `blocked = 0` or minimal with clear reason
[ ] No bounce spike in Resend dashboard within 10 min
[ ] No pipeline crash / exception

---

## GATE 6 — Post-Send Validation

[ ] Check Resend dashboard → delivery rate > 80%
[ ] Check `run_report.json` → `outbound_state = SUCCESS`
[ ] Log first reply if any (update `decision-log.md`)
[ ] Record actual sent count in this file

---

## Hard Guardrails (do not touch during launch window)

- NO changes to `venture_pipeline.py`
- NO changes to `event_engine/`
- NO changes to `dashboard.py/html` beyond read-only use
- NO new config keys or schema changes
- Only files allowed: `prospects.csv`, `policy.json`, `.env` (AUTO_SEND flip), this gates file

---

## Done definition

Launch successful when:
- Gate 5 exits with sent ≥ 20
- Gate 6 delivery rate > 80%
- Zero pipeline-level failures
- At least one measurable engagement signal within 48h
