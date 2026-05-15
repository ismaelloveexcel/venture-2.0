# Venture OS (VENTURE 2.0)

## What this is

**Venture OS** is one founder’s **personal operating workspace**: folders and scripts for moving from raw ideas to shipped experiments, outbound, and KPIs. The technical center of gravity is **`04-coding/scripts/`** — a Python pipeline that generates outreach, runs **guardrails** (qualification, quality, caps, integrity, optional reply-intent), sends via configured providers, and persists **replayable state** in SQLite (**`venture_jobs.db` at the repo root**) with **block severity**, **funnel snapshots**, and **lifecycle events**.

Supporting pieces: JSON **contracts** (`04-coding/venture-engine/config/`), a small **MCP server** (`venture-mcp-server/`) for IDE automation, and templates for ideas, evaluation, design QA, and sales copy elsewhere in the repo.

## What this is not

- **Not** a multi-tenant commercial product, **not** a “vertical BD SaaS,” and **not** tied to any external company brand you might see in old research files.
- **Not** a replacement for your CRM or data vendors — it **composes** APIs (e.g. Hunter, OpenAI, Resend, Airtable/Notion) around **your** offer and rules.
- The **thing you sell** (offer, niche, pricing) lives in config and `06-sales/`; **Venture OS** is the **system that runs** the venture, not the customer-facing product name unless you choose to use it that way.

If anything in the repo conflicts with this page, **trust this README first**, then `04-coding/venture-implementation-notes.md`.

**Canonical daily orchestrator (vFINAL.1):** `04-coding/scripts/run_daily.py` → atomic `run_report.json`. One-shot dry-run (prospects → local messages → pipeline dry-run → report): `python 04-coding/scripts/run_daily.py --generate-prospects --prospects-demo --execute-outbound --dry-run`. Operator steps: **`OPERATOR_RUNBOOK.md`**. Agent/CI contract: **`AGENTS.md`**, **`04-coding/VENTURE_OS_VFINAL_1_EXECUTION_PLAN.md`**, one-page model **`04-coding/VENTURE_OS_SYSTEM_ONE_PAGE.md`**.

## Independent Agent Review (No Assumptions)

For external/independent review, follow **`docs/INDEPENDENT_AGENT_REVIEW.md`** exactly.

It defines:

- strict source-of-truth hierarchy,
- mandatory validation command sequence,
- required evidence capture,
- forbidden assumptions,
- required review output format.

## Current build target (state as of May 2026)

The current productization focus is **not** new execution logic. The focus is a deterministic **interpretation layer** over existing execution truth:

- Keep `run_daily.py` as the only orchestration entrypoint.
- Keep `venture_pipeline.py` as the only governed execution path.
- Keep `run_report_schema.py` as the run-level data contract.
- Build client-facing artifacts from those existing outputs.

Implemented output layer:

- `04-coding/venture-engine/reporting/report_renderer.py` renders campaign intelligence artifacts.
- `04-coding/venture-engine/reporting/templates/weekly_report.html` is display-only (no scoring logic in template).
- Artifacts are generated in `04-coding/reports/campaign-intelligence/`:
	- `campaign-report-<run_id>.html`
	- `campaign-report-<run_id>.json` (artifact manifest)
	- `campaign-report-<run_id>.projection.json` (projection memory for cross-run comparison)

Insight calibration status:

- Deterministic trend + delta interpretation across runs.
- Deterministic severity/confidence scoring and ranked signals (Primary vs Secondary).
- Projection metadata includes `insight_metadata` with calibration/scoring model identifiers for replayability.

---

Structured workspace for idea → evaluation → build → design QA → sales → KPIs, with an automated **outreach pipeline** and **replayable lifecycle state**.

## Quick map

| Area | Path |
|------|------|
| Pipeline & scripts | `04-coding/scripts/` — see [scripts README](04-coding/scripts/README.md) |
| Engine contracts (JSON) | `04-coding/venture-engine/` — see [venture-engine README](04-coding/venture-engine/README.md) |
| Reporting & insight projection | `04-coding/venture-engine/reporting/` |
| Job queue, lifecycle, blocks | `venture-mcp-server/` — see [MCP server README](venture-mcp-server/README.md) |
| Copilot / agent defaults | `.github/copilot-instructions.md`, `.github/agents/` |
| Implementation notes (runtime) | `04-coding/venture-implementation-notes.md` |
| Environment template | `.env.example` |

## Operational hardening (runtime)

The pipeline and SQLite-backed `JobQueue` implement:

- **Block severity** (`HARD` / `SOFT` / `INFO`) on `block_logs` — `HARD` triggers outreach freeze.
- **Reply-intent feedback** — rows in `reply_intent_training_data` (`features_json`, `predicted_prob`, `actual_outcome`: `pending` → `replied` | `no_reply` | `not_sent`).
- **Low-volume bypass** — `REPLY_INTENT_VOLUME_THRESHOLD` (trailing 7d send count); below threshold, reply-intent pre-send filter is skipped.
- **Funnel snapshots** — `funnel_health_snapshots` after each pipeline run (`generated`, `qualified`, `sent`, `blocked`, `reply_rate_estimate`, `payload_json`).
- **Replay lock** — `opportunities.state_engine_version` aligned with `STATE_ENGINE_VERSION` in `venture-mcp-server/lifecycle_engine.py`; `replay_audit.py` reports drift.

Weekly maintenance: `04-coding/scripts/weekly_optimizer.py` settles stale reply-intent labels and writes `venture-engine/config/reply_intent_retrain_hint.json`.

## Repository

Initialize or clone as usual; copy `.env.example` → `.env`. Do not commit `.env` or local `venture_jobs.db`.

If this folder had no Git remote yet, create one on your host, then:

```text
git remote add origin <your-repo-url>
git push -u origin main
```

(Use `master` instead of `main` if that is your default branch.)
