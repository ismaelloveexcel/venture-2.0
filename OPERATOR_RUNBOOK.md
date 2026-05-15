# Venture OS — operator runbook (vFINAL.1, P6)

Single-operator workspace: one canonical entrypoint, one atomic report per run.

## Pre-launch execution window (toward 18 May 2026)

Doctrine milestones: `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` (Launch lock **13 May**, dry-run rehearsal **15 May**, live send-off **18 May**).

**Execution clock (baseline + next dates):** `04-coding/state/launch_execution_state.json` — update when you complete launch lock or change cohort/copy materially (re-run baseline per `AGENTS.md`). Field **`landing_icp`**: set to `locked` only after the landing HTML comment is flipped per `docs/SEMANTIC_CONTRACT.md` §8.2 (contract then requires the locked marker in `index.html`).

**Semantic guardrails (anti-drift):** `docs/SEMANTIC_CONTRACT.md` (§§1–8) — category lock, forbidden buyer language, production vs diagnostic CLI (`§8.1`).

**Day-of checklist only:** `04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md` (includes pre-launch ticks §0).

## Production vs diagnostic (semantic)

**Canonical production path:** `run_daily.py` only for orchestrated outbound (see `AGENTS.md`, `docs/SEMANTIC_CONTRACT.md` §8.1).

**`venture_pipeline.py`:** diagnostic / legacy dev — requires `VENTURE_DEV_MAIN=1` for `__main__` (except `--status`). Operators must not default to whichever script is “easier”; if it is not `run_daily.py`, it is not the governed production path.

## Daily path (outbound)

From the repository root:

```text
python 04-coding/scripts/run_daily.py --execute-outbound [--dry-run] [--client <id>] [--report-path <path>]
```

**Full stack in one command (prospects + local stub messages + pipeline dry-run + report):**

```text
python 04-coding/scripts/run_daily.py --generate-prospects --prospects-demo --execute-outbound --dry-run
```

Use `--prospects-demo` for template-only sourcing (no Apollo/Hunter). Omit it when API keys are set. Live sends still require human approval in `generated-outreach.csv` unless you pass `--auto-approve-generated` (not recommended).

- **Dry run (recommended first):** add `--dry-run` so the child pipeline does not send and message generation uses local stub text (no OpenAI).
- **Report:** defaults to repo root or `clients/<id>/run_report.json` when `--client` is set.
- **CIS / shadow (optional):** add `--cis` (same command; see `--help` for shadow input paths).

Do **not** run `venture_pipeline.py` directly in automation unless you set `VENTURE_DEV_MAIN=1` for local debugging. Canonical read-only status command:

```text
python 04-coding/scripts/run_daily.py bridge status
```

## Quick validation (P5 bridge)

Same interpreter, no new allowlisted CLI modules:

```text
python 04-coding/scripts/run_daily.py bridge validate
python 04-coding/scripts/run_daily.py bridge status
```

`bridge validate` runs `validate_repo_contract.py` plus a **fast** pytest subset (not the full `tests/` tree). The file list lives in one place: **`04-coding/scripts/fast_test_subset.py`** (`FAST_TEST_PATHS`; also used by `.pre-commit-config.yaml` pre-push). **CI** runs `pytest tests -q` and the contract script; match that before a risky change.

### Failure surfaces (where problems show up)

| Symptom | First place to check |
|--------|----------------------|
| Non-zero exit from daily run | `run_daily` exit code; `outbound.status` and `outbound.errors` tail in `run_report.json` |
| Contract / allowlist / schema drift | `python 04-coding/scripts/validate_repo_contract.py` |
| Send path or gate regressions | Full `pytest tests -q`; money-path tests under `tests/test_money_path_*.py` |
| Child pipeline gated | stderr message from `venture_pipeline.py`; use `run_daily` or `VENTURE_DEV_MAIN=1` for dev only |
| CIS / shadow math or inputs | `cis_eval` section and `experiment_dashboard.json`; not mixed with outbound send path |
| Exit code `9` from `venture_pipeline.py` (child of `run_daily --execute-outbound`) | Outbound eligibility HALT: missing `DATA_BASE/07-kpis/prospect_audit_log.csv`, audit header mismatch, or `DATA_BASE/logs/send_skipped_log.csv` header drift (see below) |

### Outbound eligibility (audit join)

When `prospects.csv` includes `validation_status` (prospect_builder / gate-era schema), the pipeline **does not** put a row on the send path unless:

1. The prospect row is `READY` (same rule as before), **and**
2. The latest audit row for `(VENTURE_RUN_ID or BATCH_RUN_ID, prospect_gate.normalize_email(email))` in `07-kpis/prospect_audit_log.csv` has `classification=ELIGIBLE`.

- **Skip audit:** non-ready rows, run_id mismatches, or non-ELIGIBLE audit rows append one line each to `DATA_BASE/logs/send_skipped_log.csv` (fixed header; a header mismatch on an existing file stops the run with exit `9`).
- **Fail-safe:** if the audit file cannot be read into a usable index (empty body after a valid header, or parse failure), every pending prospect is skipped with reason `audit_log_unreadable_or_empty_index` (no sends).
- **No eligible left:** if the filter removes everyone, the pipeline prints one JSON line to stdout: `{"event":"PIPELINE_NO_ELIGIBLE_PROSPECTS",...}` (still exits `0` if nothing else fails). `run_report.json` will show `outbound.status` from the orchestrator (`FAILED` if the child exited non-zero; otherwise merge telemetry as today).

### Prospect generation integrity (upstream)

- **`prospect_builder`** verifies in-memory **eligible ↔ audit `ELIGIBLE` parity** before appending the audit log, normalizes **emails** to `prospect_gate.normalize_email` before writing `prospects.csv`, and verifies a **CSV round-trip** after write (exit `2` / `3` on invariant or round-trip failure).
- **`STRICT_PROSPECT_MODE=1`:** unchanged — forensic summary + console; **always exit `0`**.
- **`VENTURE_STRICT_PROSPECT_AUDIT=1`:** after a successful write, if forensic checks (including parity) are not clean, **`prospect_builder` exits `11`** (halt).
- **Observability:** each successful builder run writes `DATA_BASE/07-kpis/prospect_generation_digest/<run_id_fs>.json`; **`run_daily`** merges it into `run_report.json` → `outbound.prospect_batch.prospect_generation_digest` when `--generate-prospects` succeeds.
- **HTTP dashboard:** `/add-prospect` no longer appends to `prospects.csv` (use `run_daily` / `prospect_builder`).

### Exit codes & quick actions

| Component | Code | What to do next |
|-----------|------|------------------|
| `run_daily.py` | `0` | OK — read machine tab line + human footer (artifact paths). |
| `run_daily.py` | `1` | `outbound.status == FAILED` — open `run_report.json`, tail `outbound.errors`, check pipeline child exit in footer. |
| `prospect_builder.py` | `1` | Sourcing or audit append schema error — fix env/API/`--demo` or `prospect_audit_log.csv` header. |
| `prospect_builder.py` | `2` | Eligible vs audit ELIGIBLE mismatch — do not hand-edit; fix gate/data and re-run. |
| `prospect_builder.py` | `3` | CSV round-trip failed — disk/schema; inspect strict summary if `STRICT_PROSPECT_MODE=1`. |
| `prospect_builder.py` | `11` | `VENTURE_STRICT_PROSPECT_AUDIT=1` forensic fail — open `07-kpis/strict_mode_summary/*.json`. |
| `venture_pipeline.py` (child) | `5` | Integrity monitor blocked live send — reasons printed; review freeze / `job_queue`. |
| `venture_pipeline.py` (child) | `6` | Outreach frozen — clear freeze after investigation. |
| `venture_pipeline.py` (child) | `7` | Batch 1 guard / preflight / lock — open printed preflight log path. |
| `venture_pipeline.py` (child) | `8` | Batch aborted mid-run — read `batch_abort_reason` in log output. |
| `venture_pipeline.py` (child) | `9` | Outbound eligibility HALT — fix audit file or `send_skipped_log.csv` header (see outbound eligibility above). |

**Operator CLI UX:** `run_daily` and `prospect_builder` print a short footer with absolute paths when stdout is a TTY. Set **`NO_COLOR=1`** to disable ANSI highlights. **`04-coding/scripts/operator_ux.py`** holds shared hints and `SKIP_REASON_*` text used by the local dashboard API.

## Prospect review workflow (strict → dry → small live)

Use this flow to produce a reviewable prospect batch before any live sends, then validate dry-run audit artifacts, and finally run a small capped live cohort.

### Preconditions

1. From repository root:

```text
cd "c:\Users\isuda\Dev\VENTURE 2.0"
```

2. Ensure the pipeline child can send when you intend to test “send path” behavior:
- `RESEND_API_KEY` and `RESEND_FROM_EMAIL` are set (in `.env` or environment) for any run where you expect `logs/send_log.csv` and cohort message snapshot plumbing to populate.

### Step 1: Generate a review batch (strict forensic mode; no outbound sends)

Goal: `06-sales/prospects.csv` contains **only ELIGIBLE** prospects (`validation_status=READY`). Full batch truth (including REVIEW/REJECT/DROP) is in `DATA_BASE/07-kpis/prospect_audit_log.csv` (see `04-coding/PROSPECT_SYSTEM_V2_2_7_IMPLEMENTATION_PLAN.md`).

1. Enable strict **forensic** checks (does **not** fail the build; always exit `0`; writes `07-kpis/strict_mode_summary/{run_id_fs}.json`):

```powershell
$env:STRICT_PROSPECT_MODE = "1"
```

2. Generate prospects:

```powershell
# Template-only demo sourcing (no Apollo/Hunter required):
python 04-coding/scripts/run_daily.py --generate-prospects --prospects-demo --prospect-count 25 --report-path .\run_report.json

# Or real sourcing when API keys are configured:
# python 04-coding/scripts/run_daily.py --generate-prospects --prospect-count 25 --report-path .\run_report.json
```

3. Pass criteria:
- Command exits with code `0`.
- In `06-sales/prospects.csv`, every row’s `validation_status` is `READY` (file may be header-only if no one passed the gate).
- Console shows `STRICT_MODE: OK` or `STRICT_MODE: VIOLATIONS DETECTED`; inspect strict summary JSON if needed.

4. Disable strict mode after review batch generation:

```powershell
Remove-Item Env:STRICT_PROSPECT_MODE -ErrorAction SilentlyContinue
```

### Step 2: One dry-run cohort (execute outbound + audit artifacts)

Goal: validate cohort metadata + snapshot plumbing + merged CSV version/hash fields produced by the outbound path, without sending.

```powershell
$env:VENTURE_RUN_ID = "op_dry_$(Get-Date -Format 'yyyyMMdd_HHmm')"
python 04-coding/scripts/run_daily.py --execute-outbound --dry-run --report-path .\run_report.json
```

Pass criteria:
- `run_report.json` shows `outbound.dry_run == true` and `outbound.cohort_metadata` is present.
- `logs/messages/` contains a new `*.txt` cohort message snapshot (write-once per cohort stem).
- `06-sales/generated-outreach.csv` includes populated fields for rows that reached the send-path metadata: `message_version`, `generator_version`, `guard_version`, `message_hash`, and `cohort_id`.
- `logs/send_log.csv` contains new entries with `send_status = dry_run` for simulated sends (where the send path was exercised).

### Step 3: Small capped live cohort (monitor replies)

Goal: allow the first real send only after dry-run audit artifacts look correct, and keep initial blast radius small.

1. Prepare a small set of pending prospect rows in `06-sales/prospects.csv` (only rows you intend to send).
2. Run full test/contract preflight:

```powershell
python -m pytest tests\test_money_path_gates.py tests\test_money_path_safety.py -q
python 04-coding/scripts/validate_repo_contract.py
```

3. Live run:

```powershell
$env:VENTURE_RUN_ID = "op_live_$(Get-Date -Format 'yyyyMMdd_HHmm')"
python 04-coding/scripts/run_daily.py --execute-outbound --report-path .\run_report.json
```

Pass criteria:
- Command exits with code `0`.
- `run_report.json` indicates a non-dry run on the money path.
- `logs/send_log.csv` records entries with `send_status = sent`.
- After the cohort window, inspect `logs/reply_intent_log.csv` for new classifications, using the frozen taxonomy from your repo contracts/runbook.

## Optional local hooks (P4)

```text
pip install pre-commit
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Hooks call the repo contract validator and the same fast pytest subset as `bridge validate` on pre-push.

## Daily auto-run (least manual mode)

Register a Windows scheduled task (dry-run by default):

```text
powershell -ExecutionPolicy Bypass -File 04-coding/scripts/register_operator_daily_task.ps1 -Time 08:30
```

Run immediately once (manual trigger):

```text
Start-ScheduledTask -TaskName VentureOperatorDailyDryRun
```

List current task:

```text
Get-ScheduledTask -TaskName VentureOperatorDailyDryRun
```

Health check:

```text
powershell -ExecutionPolicy Bypass -File 04-coding/scripts/check_operator_task_health.ps1
```

Gate status refresh:

```text
python 04-coding/scripts/calculate_gate_scores.py
```

Live scheduling is opt-in and requires explicit acknowledgment:

```text
powershell -ExecutionPolicy Bypass -File 04-coding/scripts/register_operator_daily_task.ps1 -TaskName VentureOperatorDailyLive -Time 09:00 -Live -ConfirmLive I_UNDERSTAND_LIVE_SENDS
```

Client legal/commercial operating terms: `04-coding/CLIENT_OPERATING_ADDENDUM.md`.

## Phase tracking (P3–P6)

Machine-readable state: `04-coding/.venture_phase_state.json`. Advance after a phase passes:

```text
python 04-coding/scripts/advance_venture_phase.py P3
```

Gate helper (Windows): `04-coding/scripts/run_phase_gate.ps1`. Canonical procedure: `04-coding/VENTURE_OS_P3_P6_AUTONOMOUS_EXECUTION_PLAN.md`.

## Committed launch (live send-off)

**`18/05/2026` = live send-off** — Monday **18 May 2026**: first **real** outbound sends (no `--dry-run`). **Doctrine:** `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md` (v1.12 canonical). **Day-of:** `04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md`. **Delta archive (optional):** `04-coding/LEAD_GEN_LAUNCH_V1_12_MERGE_FRAGMENT.md`.

## Where to read next

- **Non-technical operator (start here):** `04-coding/OPERATOR_SIMPLE_GUIDE.md` — one command, two spreadsheets, when to ask for help  
- **Founder “where are we?” (goals vs drift):** `04-coding/FOUNDER_WHERE_WE_ARE.md`
- **Launch doctrine (v1.12 canonical):** `04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md`
- **18 May day-of (operator-only):** `04-coding/LAUNCH_DAY_2026-05-18_EXECUTION_SHEET.md`
- **v1.12 delta archive (optional / history):** `04-coding/LEAD_GEN_LAUNCH_V1_12_MERGE_FRAGMENT.md`
- **Agent contract:** `AGENTS.md`
- **System one-pager:** `04-coding/VENTURE_OS_SYSTEM_ONE_PAGE.md`
- **Scripts index:** `04-coding/scripts/README.md`
- **Live 14-day protocol:** `04-coding/OPERATOR_EXECUTION_SHEET_V1.md`
- **Local report viewer (offline):** open `04-coding/reports/local_run_report_viewer.html` in a browser and load a `run_report.json` file (viewer is display-only, not a validator).
