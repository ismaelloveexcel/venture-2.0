# VENTURE OS vFINAL.1 — Final execution plan (implementation + operations)

This document is the **locked operational spec** after audit feedback: **one orchestrator**, **two logical namespaces (outbound + optional CIS)**, **one atomic `run_report.json` per run**, **CI contract validation**, **Cursor behavioral rules only** (no fake MCP enforcement).

---

## 1. Core system truth (non-negotiable)

### Three runtime surfaces

| Surface | Role |
|---------|------|
| **`run_report.json`** | Single machine source of truth: `outbound`, optional `cis_eval`, `system`. **Atomic full write per `run_id`** (no partial multi-process append). |
| **CLI stdout** | **One parseable line**, tab-separated: `PIPELINE_STATUS \t RECORDS \t RISK \t OUTBOUND_STATE` (`RISK` may be `N/A`). |
| **Dashboard** | **Read-only** presentation of `run_report.json` + static assets; **no business logic**. |

### Architectural rule

- **One orchestrator:** `04-coding/scripts/run_daily.py`
- **Two internal namespaces** in one report — **not** one linear merged pipeline.
- **Forbidden mental model:** CIS steps feeding outbound or a single universal step list.

---

## 2. Report lifecycle

### Path resolution (mandatory)

- **`--client <id>`** or **`VENTURE_CLIENT_ID`** → `clients/<id>/run_report.json`
- **`--report-path <path>`** → explicit file
- Else → **`<repo_root>/run_report.json`**

Configured in **`run_daily.py`** via **`run_report_writer.resolve_run_report_path`**.

### Write semantics

- **Atomic replace:** write temp in same directory → `os.replace` to final path.
- **Schema:** **`04-coding/scripts/run_report_schema.py`** (Pydantic) — **only** definition; writer + CI import this module.

### CIS side artifact

- **`06-sales/experiment_dashboard.json`** remains the CIS tracker output when `--cis` is used; **`run_report.cis_eval`** holds a summary + paths for orchestration; dashboard UI should **read report first**, optionally link to dashboard JSON.

---

## 3. Orchestrator contract (`run_daily.py`)

### Responsibilities

| Namespace | Behavior |
|-----------|----------|
| **outbound** | Load policy snapshot; optional **`--execute-outbound`** runs `venture_pipeline.py` as subprocess with **`VENTURE_DEV_MAIN=1`**; honor **`--dry-run`**. |
| **cis_eval** | Runs only if **`--cis`**; calls **`shadow_drift_tracker.generate_experiment_dashboard`**; fills `cis_eval` section. |
| **Final** | Atomic **`run_report.json`** + tab-separated status line. |

### Library modules (not user CLIs without dev gate)

- **`venture_pipeline.py`**, **`send_guard.py`**, **`job_queue.py`** — outbound stack.
- **`shadow_drift_tracker.py`** — CIS; **must not** import outbound modules (enforced in **`validate_repo_contract.py`**).

### `VENTURE_DEV_MAIN` gate

- **`venture_pipeline.py`**, **`run_pipeline.py`**, **`shadow_drift_tracker.py`**: direct `python file.py` exits **2** unless **`VENTURE_DEV_MAIN=1`**.
- **`run_daily.py`** sets **`VENTURE_DEV_MAIN=1`** only on the **child** process for `venture_pipeline` when **`--execute-outbound`** is used.

---

## 4. Enforcement split (realistic)

| Layer | What it does |
|-------|----------------|
| **`.cursor/rules/venture-os.mdc`** | Short behavioral rules for edits under `04-coding/scripts/` — **does not** execute policy. |
| **`AGENTS.md` (repo root)** | Human + agent “start here” contract; validation commands. |
| **`validate_repo_contract.py`** | **Real** checks: argparse allowlist, `__main__` gates, CIS import isolation, schema import + **RunReport.model_fields key set** (must match contract; no duplicate field list in validator), **&lt;5s**. |
| **GitHub Actions** | `pytest tests` + `validate_repo_contract.py` on **Python 3.11**. |

### CLI allowlist

- **`04-coding/scripts/contract_cli_allowlist.json`** — files allowed to contain **`ArgumentParser(`**. Shrink over time by moving capability into **`run_daily`** or libraries.

---

## 5. CI pipeline (locked)

1. `pip install -r requirements.txt -r requirements-dev.txt`
2. `pytest tests -q`
3. `python 04-coding/scripts/validate_repo_contract.py`

Workflow: **`.github/workflows/venture-os-ci.yml`**

---

## 6. Pre-commit (optional, recommended)

```bash
.venv\Scripts\python -m pytest tests\test_money_path_safety.py -q
.venv\Scripts\python 04-coding\scripts\validate_repo_contract.py
```

Purpose: catch CI failures before push.

---

## 7. Implementation order (completed vs next)

### Done in this rollout

1. **`run_report_schema.py`** — Pydantic `RunReport` v1.0  
2. **`run_report_writer.py`** — resolve path + atomic write + parse  
3. **`run_daily.py`** — orchestrator stub: policy snapshot, optional CIS, optional outbound subprocess, report + CLI line  
4. **`validate_repo_contract.py`** + **`contract_cli_allowlist.json`**  
5. **`VENTURE_DEV_MAIN`** gates on **`venture_pipeline.py`**, **`shadow_drift_tracker.py`**, **`run_pipeline.py`**  
6. **Tests:** `tests/test_run_report_contract.py`, `tests/test_money_path_safety.py`, **`tests/conftest.py`**; CIS contract test updated for **`run_daily --help`**  
7. **`.github/workflows/venture-os-ci.yml`**, **`requirements-dev.txt`**, **`.cursor/rules/venture-os.mdc`**, **`AGENTS.md`**

### Next (normal product work — not blocking vFINAL.1 shell)

| Priority | Item |
|----------|------|
| P1 | **Money-path pytest** — **done (baseline):** `tests/test_money_path_gates.py` (policy gate before `_resend_request`, missing Resend creds short-circuit, `send_guard` blocks + dry_run never calls `httpx.post`). **Still to add later:** httpx transport mocks for live-path branches, suppression/cooldown matrix on real DB fixtures. |
| P2 (core) | **Done:** CI enforces Resend outbound `POST` URL text (host `api.resend.com`, path `/emails`) appears **only** in `send_guard.py` via `_check_resend_emails_endpoint_isolation` (validator excludes its own file from the scan). **E2E:** `tests/test_run_daily_e2e_trace.py` — `run_daily --execute-outbound --dry-run` writes atomic `run_report.json` with `run_id`, `outbound.dry_run`, phases, subprocess exit. **Next P2 UI:** dashboard read-only viewer. |
| P3 | **`venture_pipeline` telemetry**: structured line or small JSON fragment merged into **`outbound.money_path`** after subprocess (honest sent/blocked counts). |
| P4 | **Pre-commit config** repo-wide. |
| P5 | **Shrink allowlist** by moving CLIs into **`run_daily`** subcommands or dev-only modules. |
| P6 | **Operator runbook** one-pager + update **`04-coding/scripts/README.md`** “daily path” to **`run_daily`**. |

**Autonomous execution (one-go + read-only reviewer after each phase):** **`04-coding/VENTURE_OS_P3_P6_AUTONOMOUS_EXECUTION_PLAN.md`** (canonical reviewer I/O, **`04-coding/.venture_phase_state.json`**, **`run_phase_gate.ps1`**, **`advance_venture_phase.py`**).

---

## 8. System guarantee (honest)

### You get

- Single **canonical** orchestrator for daily coordinated runs.
- **Gated** direct execution of legacy pipeline CLIs.
- **CI-enforced** argparse allowlist + CIS isolation + schema import.
- **Atomic** `run_report.json` contract.

### You do not get

- Runtime enforcement from Cursor rules alone.
- Perfect cross-environment determinism for all timestamps.
- Send counts from subprocess **until** pipeline emits machine-readable telemetry (noted above).

---

## 9. One-line definition

> Venture OS is a **single-orchestrator**, **dual-namespace** execution system (**outbound + optional CIS**) producing one **schema-validated, atomic `run_report.json` per run**, enforced by **CI-level contract validation** and guided by **lightweight Cursor behavioral rules**.

---

## 10. Daily operator commands (reference)

```powershell
cd "c:\Users\isuda\Dev\VENTURE 2.0"
# Report only (no outbound subprocess, no CIS)
.venv\Scripts\python 04-coding\scripts\run_daily.py --report-path .\run_report.json

# CIS evaluation into report + experiment_dashboard.json
.venv\Scripts\python 04-coding\scripts\run_daily.py --cis --report-path .\run_report.json

# Outbound via venture_pipeline (dry-run)
.venv\Scripts\python 04-coding\scripts\run_daily.py --execute-outbound --dry-run --report-path .\run_report.json
```

Validation:

```powershell
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python 04-coding\scripts\validate_repo_contract.py
```
