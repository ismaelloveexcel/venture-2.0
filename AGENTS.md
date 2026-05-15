# VENTURE OS — Agent operating contract (vFINAL.1)

## Launch-period execution mode (Cursor / agents)

**Canonical behavioral prompt:** `04-coding/CURSOR_AGENT_PRIMARY_EXECUTION_PROMPT.md` — session start protocol (read `AGENTS.md` + doctrine before edits), phase stops, escalation, doctrine vs speed, perception vs backend truth, evidence over theatre, no silent workarounds. Use during work toward the **2026-05-18** live send-off; it supplements (does not replace) technical invariants below.

**Pre-launch clock (milestones + last baseline):** `04-coding/state/launch_execution_state.json` — update when launch-lock or rehearsal milestones complete or after material cohort/copy changes (re-run `AGENTS.md` validation).

**Semantic contract (drift prevention):** `docs/SEMANTIC_CONTRACT.md` (§§1–8: category lock, naming, cross-surface rules, ICP latch §8.2) — naming, forbidden buyer interpretations, production vs diagnostic CLI, landing ICP latch (`VENTURE_ENFORCE_LANDING_ICP` or `landing_icp: locked` in execution state).

**Independent review protocol (mandatory for external/autonomous reviewers):** `docs/INDEPENDENT_AGENT_REVIEW.md` — source-of-truth hierarchy, required command sequence, evidence checklist, and forbidden assumptions.

## Resend / operator identity (Auditbound)

- **Brand domain (DNS verify only):** `auditbound.io` — add in Resend if needed for account/brand verification; cold **From** does not use this domain unless you choose to.
- **Sending domain:** `abtmail.co` — `RESEND_FROM_EMAIL` must use this domain after Resend verification (e.g. `outreach@abtmail.co`).
- **Operator / digest inbox:** `isudally@outlook.com` — set `DIGEST_TO_EMAIL` in `.env` (see `.env.example`).
- Canonical env keys live in **`.env.example`**; copy to **`.env`** locally (never commit `.env`).

## System rules

- **One canonical user CLI:** `04-coding/scripts/run_daily.py` (optional `--generate-prospects` / `--prospects-demo`; with `--execute-outbound` it runs `message_generator_solo.py` then `venture_pipeline.py`; `--dry-run` uses local stub messages + auto-approve for pipeline handoff only in that mode)
- **One atomic report per run:** `run_report.json` (path from `--client`, `VENTURE_CLIENT_ID`, `--report-path`, or repo root)
- **Two namespaces in that report:** `outbound` (money path) and optional `cis_eval` (shadow / CIS analytics)

## Truth flow

```text
run_daily.py → outbound (+ optional cis_eval) → run_report.json → dashboard / viewers (read-only)
```

## Do not

- Write `prospects.csv` / `PROSPECTS_FILE` from ad-hoc scripts (CI enforces this in `validate_repo_contract.py`); canonical generation is **`prospect_gate.write_eligible_prospects_csv`** via **`prospect_builder.py`** / **`run_daily.py --generate-prospects`**. Post-send status sync is **`venture_pipeline.sync_prospect_status_to_source_csv`** only.
- Add new top-level CLI entrypoints under `04-coding/scripts/` without updating `contract_cli_allowlist.json` and team review (goal: shrink allowlist over time).
- Change outbound send behavior without going through `send_guard.py` / existing gates.
- Import outbound modules from `shadow_drift_tracker.py` (CIS isolation).
- Duplicate `run_report` field definitions outside `run_report_schema.py`.

## Legacy CLIs (gated)

- `venture_pipeline.py`, `run_pipeline.py`, `shadow_drift_tracker.py` `__main__` blocks require **`VENTURE_DEV_MAIN=1`** (local debugging), except **`venture_pipeline.py --status`** (read-only, no env). Production-style runs use **`run_daily.py`** (it sets the env var for the pipeline child when needed).

## Validation (required before merge)

```powershell
cd "c:\Users\isuda\Dev\VENTURE 2.0"
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python 04-coding\scripts\validate_repo_contract.py
```

Fast local check (subset + contract): `python 04-coding/scripts/run_daily.py bridge validate`. The pytest file list is **`04-coding/scripts/fast_test_subset.py`** (`FAST_TEST_PATHS`); keep it in sync with `.pre-commit-config.yaml`. Optional hooks: repo root `.pre-commit-config.yaml`. Human operator flow: **`OPERATOR_RUNBOOK.md`**. **`run_daily` / `prospect_builder`** print a short operator footer (artifact paths) when stdout is a TTY; set **`NO_COLOR=1`** to disable ANSI.

Money-path gate tests live in **`tests/test_money_path_gates.py`** (P1 baseline).

P2 chokepoint: Resend POST URL text must exist only in **`send_guard.py`** (CI: `validate_repo_contract`). Orchestrator trace: **`tests/test_run_daily_e2e_trace.py`**.

Phase orchestration (P3–P6): **`04-coding/.venture_phase_state.json`**, gate script **`04-coding/scripts/run_phase_gate.ps1`**, advance helper **`04-coding/scripts/advance_venture_phase.py`**. Procedure: **`04-coding/VENTURE_OS_P3_P6_AUTONOMOUS_EXECUTION_PLAN.md`** (canonical read-only reviewer rule inside).

**Whole-system one-pager (diagram + invariants):** **`04-coding/VENTURE_OS_SYSTEM_ONE_PAGE.md`**.

## Schema source of truth

- **`04-coding/scripts/run_report_schema.py`** — Pydantic models consumed by writer, validator import check, and tests.
