# Venture OS — P3–P6 execution plan (one-go + per-phase sub-agent review)

This plan matches **`VENTURE_OS_VFINAL_1_EXECUTION_PLAN.md` §7** (P3–P6 rows) and adds **how to run it end-to-end** with a **mandatory review gate after each phase** so work stays bounded and CI-safe.

---

## Phase map (what P3–P6 are)

| Phase | Goal | Primary outputs | CI must stay green |
|-------|------|-----------------|-------------------|
| **P3** | Honest **outbound telemetry** in `run_report` after pipeline runs (and optional **read-only dashboard** that only reads `run_report.json`) | Extend `run_report_schema` / `run_daily` (or minimal `venture_pipeline` hook) so `outbound.money_path` reflects real attempted/sent/blocked when available; optional `04-coding/scripts/run_report_dashboard/` static HTML or `python -m http.server` one-file viewer | `pytest tests`, `validate_repo_contract.py` |
| **P4** | **Pre-commit** repo-wide (fast subset + full optional) | `.pre-commit-config.yaml` + docs in `AGENTS.md`; hooks: `ruff`/`ruff format` (if adopted), or at minimum `validate_repo_contract.py` + targeted pytest | Same + `pre-commit run --all-files` in CI (optional job) |
| **P5** | **Shrink `contract_cli_allowlist.json`** only after behavior absorbed by **`run_daily`** subcommands or dev-only entry | Smaller allowlist; fewer `ArgumentParser(` surfaces; no removal until parity tests exist | Validator + contract tests |
| **P6** | **Operator surface**: one-page runbook + **`04-coding/scripts/README.md`** daily path points to **`run_daily.py`** | `OPERATOR_RUNBOOK.md` (or `07-kpis/`), README delta, links from root `README.md` | Docs-only; run `pytest` to catch broken references if any |

**Optional insert (UI-first):** If you prefer, ship **read-only dashboard** as **P3a** before telemetry **P3b**; same review gates apply per slice.

---

## Machine-readable phase state

**File:** `04-coding/.venture_phase_state.json` (committed; update after each `PHASE_PASS`).

| Field | Meaning |
|-------|---------|
| `schema_version` | State file format (currently `1`). |
| `current_phase` | Active work target (`P3` … `P6`, or `DONE`). |
| `completed` | Phases finished and reviewed (e.g. `P1`, `P2`, …). |
| `last_review_commit` | Optional git SHA when reviewer signed off. |
| `last_run_id` | Optional correlation to `run_report.json` / CI. |

**Deterministic gate (no LLM):** `04-coding/scripts/run_phase_gate.ps1`  
Optional: `-ExpectCurrentPhase P3` ensures `current_phase` matches before running `pytest` + `validate_repo_contract.py`.

**After `PHASE_PASS: Pn`:** advance state (human or CI):

```powershell
.venv\Scripts\python 04-coding\scripts\advance_venture_phase.py P3
```

CI validates presence/shape of `.venture_phase_state.json` via `validate_repo_contract.py` (`_check_venture_phase_state`).

---

## Autonomous pattern: parent + reviewer after **each** phase

### Roles

| Role | Responsibility |
|------|----------------|
| **Parent agent** | Implements exactly one phase (P3, then P4, …). Stops after commit-sized chunk. Does not start next phase until review passes. |
| **Phase reviewer** | See **Canonical reviewer rule** below — never edits files. |

### Hard rules for autonomy

1. **One phase per parent invocation slice** — no “while I’m here I’ll also do P5.”
2. **Reviewer runs immediately after** each phase’s implementation push (separate Task — see canonical rule).
3. **Promotion rule:** next phase starts only when review outputs **`PHASE_PASS: Pn`** as the **first line** of the reviewer output.
4. **Rollback rule:** if the first line is **`PHASE_FAIL: Pn`** (optionally `+ reason` on the same line or line 2), parent fixes only Pn scope until pass.

---

## Canonical reviewer rule (single deterministic contract)

> The reviewer is **always** a **read-only** prompt run with **no write permission**: open a **new Cursor Task** (or Cloud Agent) in **Ask / read-only** mode only, with the repository state fixed at the **current commit SHA** (reviewer must record that SHA in its output). **No file edits** in the reviewer turn. The reviewer output **must** start with **exactly one** of:
>
> * `PHASE_PASS: Pn`
> * `PHASE_FAIL: Pn` — and a short reason (same line or immediately below)

Do **not** substitute ad-hoc “second chat” or ambiguous `subagent_type` labels unless they obey the rule above.

---

## Phase reviewer prompt (paste as the **entire** prompt in the read-only Task)

```text
You are the Venture OS PHASE REVIEWER (read-only).

Context: Phase Pn just completed. Repo: VENTURE 2.0.

Verify ALL of the following. **First line of your reply must be exactly** `PHASE_PASS: Pn` **or** `PHASE_FAIL: Pn` (optional reason after a space or on line 2).

Record `git rev-parse HEAD` as `review_commit_sha` in line 3 or in your bullet list.

Checks:
1. AGENTS.md + venture-os.mdc: no new user-facing CLI outside run_daily without allowlist update.
2. run_report_schema.py remains the only Pydantic source for RunReport top-level keys; validate_repo_contract still aligned (no duplicate field lists).
3. Resend endpoint isolation: the outbound `POST` URL (host `api.resend.com`, path `/emails`) must appear only in `send_guard.py` — do not weaken `validate_repo_contract`.
4. CIS: shadow_drift_tracker must not import outbound modules.
5. Suggest running: pytest tests -q && python 04-coding/scripts/validate_repo_contract.py (if you cannot run, say UNVERIFIED and why).

Then: bullet list of risks, file list touched, and any MUST_FIX before PHASE_PASS.
```

Replace `Pn` with **P3**, **P4**, **P5**, or **P6** when invoking.

---

## “One go” — two ways to run it

### Option A — Single Cursor chat (recommended)

1. Open one **Agent** chat.
2. Paste the **master driver prompt** below once.
3. The parent agent executes **P3 → review → P4 → review → …**. For each review, open a **separate Cursor Task** in **read-only / Ask** mode only; paste the **Phase reviewer prompt** from this doc (Canonical reviewer rule).
4. You only intervene if a phase returns **`PHASE_FAIL`**.

**Master driver prompt (copy-paste):**

```text
Execute Venture OS phases P3 through P6 sequentially from 04-coding/VENTURE_OS_P3_P6_AUTONOMOUS_EXECUTION_PLAN.md.

For each phase P3, P4, P5, P6:
1. Implement ONLY that phase per the doc. Minimal diffs. Tests first when touching money path or schema.
2. Run: 04-coding/scripts/run_phase_gate.ps1 (from repo root), or: pytest tests -q && python 04-coding/scripts/validate_repo_contract.py
3. Open a NEW read-only Cursor Task; paste the full "Phase reviewer prompt" with Pn replaced. First line of reviewer output MUST be PHASE_PASS: Pn or PHASE_FAIL: Pn. No writes in that Task.
4. On PHASE_PASS: run advance_venture_phase.py Pn and commit .venture_phase_state.json if policy requires.
5. If PHASE_FAIL, fix within the same phase only, re-run gate, re-run reviewer until PHASE_PASS.
6. Only then proceed to the next phase.

Do not skip reviews. Do not merge P4 into P3 scope. P5: do not shrink allowlist until run_daily parity exists for removed CLI.
```

### Option B — Headless / scripted (partial automation)

There is **no stable generic “sub-agent” API** in plain Git; “review after each phase” belongs in **Cursor Cloud Agents**, **CI**, or a **wrapper script** that:

1. Runs a phase tag / branch job.
2. Posts a GitHub comment checklist (human or bot).
3. Blocks merge without check.

**Implemented:** `04-coding/scripts/run_phase_gate.ps1` (optional `-ExpectCurrentPhase Pn`). **Review** remains LLM/human in a read-only Task per canonical rule above.

---

## Per-phase deliverables and exit criteria

### P3 — Telemetry (+ optional dashboard)

| Deliverable | Exit criterion |
|-------------|------------------|
| Telemetry contract | `run_report.outbound.money_path` (or nested typed fields) documents attempted/sent/blocked with stable reason strings when subprocess provides data (or explicit `telemetry_pending`). |
| Parser / merge | `run_daily` merges subprocess artifact or parsed stdout JSON **without** second schema source of truth. |
| Dashboard (optional) | Static page loads `run_report.json` via `file://` or local server; **no** outbound/CIS computation. |
| Review | `PHASE_PASS: P3` |

### P4 — Pre-commit

| Deliverable | Exit criterion |
|-------------|------------------|
| Config | `.pre-commit-config.yaml` at repo root; documented install `pre-commit install`. |
| Hooks | At least: `validate_repo_contract.py` + `pytest tests/test_money_path_safety.py tests/test_run_report_contract.py` (fast) OR full `pytest tests` if acceptable speed. |
| CI (optional) | Workflow job `pre-commit run --all-files` on PR. |
| Review | `PHASE_PASS: P4` |

### P5 — Allowlist shrink

| Deliverable | Exit criterion |
|-------------|------------------|
| Parity | Each removed CLI file has behavior reachable via `run_daily` **or** is moved to `devtools/` with explicit validator exemption list (documented). |
| Validator | `contract_cli_allowlist.json` updated; `validate_repo_contract.py` still passes. |
| Review | `PHASE_PASS: P5` |

### P6 — Runbook + README

| Deliverable | Exit criterion |
|-------------|------------------|
| Runbook | One file, ≤2 screens: install, three daily commands, failure codes, where `run_report.json` lives, `VENTURE_DEV_MAIN` note. |
| README | `04-coding/scripts/README.md` “daily path” = `run_daily.py`; link to runbook. |
| Review | `PHASE_PASS: P6` |

---

## Single command block (local, after all phases implemented)

```powershell
cd "c:\Users\isuda\Dev\VENTURE 2.0"
.venv\Scripts\python -m pip install -r requirements.txt -r requirements-dev.txt -q
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python 04-coding\scripts\validate_repo_contract.py
pre-commit run --all-files   # after P4 exists
```

---

## Future: CI as orchestrator authority (optional)

Add a workflow job that runs the same commands as **`run_phase_gate.ps1`** (pytest + `validate_repo_contract.py`) on every PR so **GitHub**, not a Cursor session, is the always-on gate. Phase alignment (`-ExpectCurrentPhase`) can stay manual or be keyed off a branch naming convention (`feature/p4-precommit`).

---

## Autonomy limits (honest)

- **Sub-agent review** in Cursor is **as autonomous as your agent session**; it is not a separate OS process unless you use **Cursor Cloud** / **API** with an orchestration runner.
- **True lights-out** across days needs **CI + branch protection** (required checks) so bad phases never land on `main`.

---

## Ordering dependency (do not violate)

```
P3 (telemetry/UI) → P4 (hooks assume stable paths) → P5 (CLI shrink last) → P6 (docs reflect final CLI)
```

**P5 last among code phases** avoids documenting CLIs you are about to delete.

---

## File this plan references

- `04-coding/VENTURE_OS_VFINAL_1_EXECUTION_PLAN.md` — source of P3–P6 definitions  
- `AGENTS.md` — operator + agent contract  
- `.cursor/rules/venture-os.mdc` — edit-time guardrails  

When P3–P6 are complete, update **§7** in `VENTURE_OS_VFINAL_1_EXECUTION_PLAN.md` to mark rows done and point here for the autonomous procedure.
