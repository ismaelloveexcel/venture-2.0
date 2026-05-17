# Dashboard 1-Day Execution Checklist (Scope-Locked)

Date: 2026-05-17
Mode: Option A (Revenue / Operator Loop Only)
Window: One execution day

## Objective
Increase operator decision speed and revenue visibility through dashboard-only improvements.

## Hard Scope Lock
Allowed:
- Dashboard UI/UX flow improvements
- Dashboard API additions needed only for operator visibility and speed
- Runtime projection endpoint for operator decisions
- Small test updates directly tied to dashboard behavior

Forbidden in this window:
- Event engine expansion
- New backend abstractions/framework layers
- Contract/governance architecture additions
- Refactors outside dashboard money path
- "While I'm here" structural cleanups

## Success Criteria (must all be true)
- Operator can identify today's top revenue risk in less than 15 seconds
- Operator can trigger safe rehearsal and live action with explicit guardrails
- Dashboard shows projected shortfall/surplus toward monthly target
- Zero regressions in canonical validation path

## Execution Plan (Time-Boxed)

1. Baseline and freeze (30 min)
- Capture current dashboard screenshots and current operator click path
- Log current time-to-decision and time-to-action baseline
- Freeze non-dashboard files for this window

2. Runtime projection endpoint (90 min)
- Add/verify endpoint returning:
  - current MRR run-rate estimate
  - gap to monthly target
  - required daily sends/conversions based on current funnel
  - confidence band (simple low/base/high)
- Keep logic simple and deterministic for operator trust

3. Dashboard decision strip upgrade (90 min)
- Add a single "Today Focus" strip at top with:
  - highest risk
  - next best action
  - projected gap
- Ensure one-click path to rehearse/live actions

4. Operator action flow hardening (60 min)
- Keep Observe/Rehearse/Execute Live split explicit
- Maintain live confirmation guard before send actions
- Add concise, visible outcome messages after actions

5. Validation and smoke checks (60 min)
- Run:
  - .venv\Scripts\python.exe 04-coding/scripts/validate_repo_contract.py
  - .venv\Scripts\python.exe 04-coding/scripts/run_daily.py bridge validate
- Dashboard smoke:
  - load dashboard
  - verify top strip values render
  - verify rehearse and live confirm flow

6. Closeout and handoff (30 min)
- Record before/after operator path and timing
- Summarize only revenue-loop deltas
- Explicitly state deferred backend items (not worked)

## Scope Creep Guardrails (must enforce continuously)
- If a change touches non-dashboard architecture, stop and defer
- If a task takes you into event engine internals, stop and defer
- If a fix requires broad refactor, create defer note and continue dashboard path
- No new files outside dashboard scope unless required for dashboard endpoint/tests

## Defer List (intentionally frozen today)
- event_engine feature extension
- additional governance/contract hardening
- venture_pipeline structural cleanups not required by dashboard flow
- any new subsystem or framework addition

## End-of-Day Done Definition
- Checklist steps complete
- Success criteria all met
- No forbidden-scope changes committed
- One concise operator-facing summary produced
