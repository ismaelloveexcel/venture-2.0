# Venture OS — automation scripts

These are the **main runtime** for Venture OS: Python entrypoints for outreach generation, sending, trust/integrity gates, and weekly optimization. Everything here serves **one operator’s** workflow (SQLite state beside these files), not a multi-tenant product.

**Framing:** See [repository README](../../README.md) (“What this is / is not”) and [venture-implementation-notes.md](../venture-implementation-notes.md).
---

## 🚀 Day 8–14 Solo Operator Execution (NEW)

**See [DAY8_EXECUTION_GUIDE.md](DAY8_EXECUTION_GUIDE.md) for complete Day 8–14 workflow.**

Three-script execution pack for non-technical operators:

| Script | Purpose | Input | Output |
|--------|---------|-------|--------|
| `prospect_builder.py` | Source + validate prospects (rule-based filtering) | API or template data | `prospects.csv` (READY/REVIEW/REJECT) |
| `message_generator_solo.py` | Generate + validate messages (3-tier: PASS/RETRY/FAIL) | Prospects + ICP prompt | `generated-outreach.csv` (PASS messages only) |
| `review_queue.py` | Ultra-simple approval interface (binary APPROVE/REJECT) | Generated messages | `approved-messages.csv` + call logger |

**Execution sequence:**
```bash
python prospect_builder.py          # 5 min
python message_generator_solo.py    # 10 min
python review_queue.py              # 20-30 min (approve/reject)
# Then: venture_pipeline.py --dry-run && venture_pipeline.py (send)
```

**Operator overhead:** 30-40 min setup (Day 8), then ~10 min daily

See [DAY8_EXECUTION_GUIDE.md](DAY8_EXECUTION_GUIDE.md) for full details.

---
## Primary commands

### Runtime

| Script | Purpose |
|--------|---------|
| `venture_pipeline.py` | End-to-end: enrich, draft, gates (qualification, quality, capacity, reply-intent, compliance, **policy gatekeeper**), send, lifecycle events, funnel snapshot |
| `weekly_optimizer.py` | Weekly run: trust aggregates, settle stale `reply_intent_training_data` (`pending` → `no_reply`), emit retrain hints into `venture-engine/config/` |

### Operations & Monitoring

| Script | Purpose |
|--------|---------|
| `ops_daily.ps1` | Windows daily health: `--status`, exit 1 if compliance `BLOCKED` or DLQ over `VENTURE_OPS_DLQ_THRESHOLD` (default 0 = any row) |
| `ops_weekly.ps1` | Windows weekly: `replay_audit.py` + `dlq_replay.py` dry-run; appends to `logs/ops-weekly.log` |
| `autopilot_health_guard.ps1` | Autonomous anomaly detection: runs snapshot + policy engine, detects DLQ spikes / failures / data integrity issues, auto-escalates to SAFE_MODE if critical |
| `ops_autopilot_daily.ps1` | One-pass daily operator run: executes `ops_daily` + `autopilot_health_guard`, computes GO/HOLD verdict, and can auto-run `venture_pipeline.py` when safe (`VENTURE_AUTOPILOT_RUN_PIPELINE_ON_GO=true`) |
| `operator_verdict.py` | Deterministic daily GO/HOLD engine from state + policy + KPI trend; returns JSON used by `ops_autopilot_daily.ps1` |

### Autonomous Control Plane

| Script | Purpose |
|--------|---------|
| `system_state_snapshot.py` | Pure read-only probe: DLQ count, send volume, reply rate, failure rate, cooldown violations, orphaned events. Outputs JSON snapshot. |
| `policy_engine.py` | Deterministic policy decision engine: consumes snapshot, evaluates against rules, selects mode (NORMAL / CONSERVATIVE / RESTRICTED / SAFE_MODE), persists to `policy.json` (recommended input for the operator; pipeline enforces the fields below). |

### Testing & Diagnostics

| Script | Purpose |
|--------|---------|
| `replay_audit.py` | Replay lifecycle state from SQLite; flag `state_engine_version` drift vs `lifecycle_engine.STATE_ENGINE_VERSION` |
| `integration_test.py` | Resilience + job queue + lifecycle replay + gatekeeper smoke tests |
| `batch1_release_gate.py` | Read-only Batch 1 release gate: compile checks, Resend chokepoint scan, send-type blocking, internal test allowlist, lock lifecycle registration |
| `credibility_candidate_generator.py` | Motion-first Credibility Launch candidate generator: converts structured YC/job/funding exports into pre-scored Signal Lab rows with `linkedin_quality=unknown` |

---

## Autonomous Control Plane (Days 6–10)

Snapshot + policy engine + health guard **produce** `policy.json`. **`venture_pipeline.py` enforces a subset of that file at send time** (see below). Modes like CONSERVATIVE / RESTRICTED matter because the engine **writes** matching `followup_depth`, `cooldown_multiplier`, and `send_velocity` into the same JSON the pipeline reads — not because the pipeline branches on mode name alone.

```
system_state_snapshot.py
        ↓ (read-only observation)
policy_engine.py
        ↓ (deterministic decision)
policy.json (persisted)
        ↓
autopilot_health_guard.ps1
        ↓ (monitor + escalate)
venture_pipeline.py (reads policy.json)
        ↓
outbound_events (if gates allow)
```

### How it works

1. **system_state_snapshot.py** — reads DLQ, send volume, reply rates, orphan events → outputs JSON
2. **policy_engine.py** — consumes snapshot, selects policy fields + mode → persists to `policy.json`
3. **autopilot_health_guard.ps1** — watches for anomalies (DLQ spike, failures, data integrity) → can invoke snapshot / policy engine
4. **venture_pipeline.py** — loads `policy.json` (or `VENTURE_POLICY_JSON` for tests) and:
   - **Blocks all prospect sends** if `mode == SAFE_MODE` or `send_velocity == "paused"` (gatekeeper before Resend).
   - **Caps automated follow-ups per prospect per run** using `followup_depth` (`0` = skip follow-up phase).
   - **Scales outbound cooldown days** for `gate_outbound_send` using `cooldown_multiplier`, with an extra factor when `send_velocity` is `"slow"`.
        - **Upgrades message quality** with one rewrite pass if initial copy fails the premium quality rubric.

### Policy modes (what the engine *writes* into `policy.json`)

| Mode | Trigger (policy_engine) | Typical persisted fields |
|------|-------------------------|---------------------------|
| **NORMAL** | Healthy system | `followup_depth` 2, multiplier 1.0, velocity normal |
| **CONSERVATIVE** | Minor risk | `followup_depth` 1, multiplier 1.2, velocity normal |
| **RESTRICTED** | Elevated risk | `followup_depth` 0, multiplier 1.5, velocity slow |
| **SAFE_MODE** | Critical | **Sends blocked** by gatekeeper; manual reset |

### Auto-reset behavior

- **SAFE_MODE**: manual reset only (operator must run `policy_engine.py --reset-safe-mode`)
- **Other modes**: auto-clear if system returns to baseline on next evaluation

---

Run from this directory (or repo root with adjusted paths). Example:

```powershell
cd 04-coding/scripts
uv run --with httpx --with python-dotenv python venture_pipeline.py --dry-run
uv run python system_state_snapshot.py
uv run python policy_engine.py
uv run python weekly_optimizer.py
uv run python replay_audit.py
uv run python integration_test.py
```

### Windows scheduling (Task Scheduler)

Use **repo-root `.venv`** (or another fixed interpreter) in the task action so runs do not depend on Store `python`.

- **Daily:** `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\VENTURE 2.0\04-coding\scripts\ops_daily.ps1"`
- **Daily (recommended single task):** `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\path\to\VENTURE 2.0\04-coding\scripts\ops_autopilot_daily.ps1"`
- **Weekly:** same pattern with `ops_weekly.ps1`
- **Pipeline:** run `venture_pipeline.py` in a separate task; stagger times so daily health does not overlap a long pipeline window if both are heavy on the same machine.

Suggested cadence for confidence-first operation:

- 08:00 daily: `ops_autopilot_daily.ps1`
- 08:15 daily: `venture_pipeline.py` run task (skip this if autopilot is allowed to auto-run pipeline)
- Sunday 09:00: `ops_weekly.ps1`

### One-command daily startup (manual operator path)

If you want a deterministic manual start with zero ambiguity, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\04-coding\scripts\run_pipeline.ps1 -Mode dry-run
```

Before moving from dry-run/test approval into live Batch 1, run the release gate:

```powershell
.\.venv\Scripts\python.exe .\04-coding\scripts\batch1_release_gate.py
```

Treat a non-zero exit as a hard stop. Fix only the failed invariant, rerun the gate, then continue.

`run_pipeline.ps1` now executes in this order:

1. Batch 1 pre-send gate (`live` blocks on failure; `dry-run` reports and continues)
2. `venture_pipeline.py --status`
3. `venture_pipeline.py --dry-run` (or live with `-Mode live`)

Use the mandatory daily scorecard template after each run: `03-reevaluation/daily-scorecard-template.md`.

`ops_autopilot_daily.ps1` now emits a single verdict line:

- `verdict=GO` means controls are healthy enough to execute pipeline runs.
- `verdict=HOLD` means operator action is required before sending (policy block, control failure, or no outbound momentum).

Optional autonomous mode:

- `VENTURE_AUTOPILOT_RUN_PIPELINE_ON_GO=true` (default) runs pipeline automatically when verdict is GO.
- Set `VENTURE_AUTOPILOT_RUN_PIPELINE_ON_GO=false` if you prefer separate scheduler control.
- `VENTURE_ENFORCE_ACTIVITY_HOLD=true` enables strict HOLD when there is zero recent outbound activity and revenue is below target (default is false to avoid bootstrap deadlock).

Dashboard: with `VENTURE_ALLOW_INSECURE_WEBHOOKS=true`, startup **refuses** unless `DASHBOARD_BIND` is loopback (`127.0.0.1`, `localhost`, or `::1`).

## Database

Default SQLite path: **`venture_jobs.db` at the repository root** (same as `venture_pipeline.py` and `dashboard.py`). Schema is created/migrated by `venture-mcp-server/job_queue.py` on first use.

Notable tables for operations:

- `block_logs` — `block_type`, **`severity`** (`HARD` freezes outreach; `SOFT` / `INFO` do not)
- `reply_intent_training_data` — training rows for reply-intent model calibration
- `funnel_health_snapshots` — one row per pipeline run summary
- `opportunities` / `lifecycle_events` — replayable state; **`state_engine_version`** per opportunity

## Configuration

- **Runtime**: `runtime_config.py` (loads `.env` from repo root)
- **Reply-intent model**: `../venture-engine/config/reply_intent.model.json`
- **Retrain hints** (weekly output): `../venture-engine/config/reply_intent_retrain_hint.json`, merged into `optimizer_output.json`

See root **`README.md`**, **`../venture-implementation-notes.md`**, and **`../venture-engine/README.md`** for runtime summary, contracts, and env vars (`REPLY_INTENT_*`, integrity thresholds, caps).
