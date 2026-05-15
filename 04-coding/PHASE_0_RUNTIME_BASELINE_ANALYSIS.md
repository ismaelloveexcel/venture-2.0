# Venture OS — Phase 0 Runtime Baseline Analysis

## Scope lock (Phase 0 only)

This document is a Phase 0 baseline artifact for runtime understanding and consolidation planning.

- In scope: system truth mapping, governance mapping, invariant cataloging, observability/integrity gap analysis.
- Out of scope: runtime behavior changes, schema mutations, queue/state rewrites, telemetry framework replacement.

---

## Source-of-truth set used for this baseline

- `/home/runner/work/venture-2.0/venture-2.0/README.md`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/venture-implementation-notes.md`
- `/home/runner/work/venture-2.0/venture-2.0/AGENTS.md`
- `/home/runner/work/venture-2.0/venture-2.0/docs/SEMANTIC_CONTRACT.md`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/VENTURE_OS_VFINAL_1_EXECUTION_PLAN.md`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/scripts/run_daily.py`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/scripts/run_report_schema.py`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/scripts/runtime_governance.py`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/scripts/system_integrity_monitor.py`
- `/home/runner/work/venture-2.0/venture-2.0/04-coding/scripts/replay_audit.py`
- `/home/runner/work/venture-2.0/venture-2.0/venture-mcp-server/job_queue.py`

---

## Canonical runtime flow (validated)

The operational spine is already implemented and should be preserved:

1. `run_daily.py` is the canonical orchestrator for production-style runs.
2. `run_daily.py` executes `message_generator_solo.py` and then `venture_pipeline.py` for outbound execution paths.
3. `venture_pipeline.py` persists state via SQLite `venture_jobs.db` through `JobQueue`.
4. Runtime artifacts are written to atomic `run_report.json` using `run_report_schema.py`.
5. Dashboard/readers consume report and governance projections as read-only surfaces.

This confirms Venture OS is an operating runtime, not a greenfield architecture target.

---

## Governance map (implemented primitives)

### Execution control

- Canonical execution path enforced through `run_daily.py`.
- Legacy script execution is dev-gated (`VENTURE_DEV_MAIN`) per operating contract.
- Canonical-entry guard exists for execute mode.

### Data contract governance

- `run_report_schema.py` is the schema source of truth.
- `run_report_writer` performs atomic write semantics.
- CI contract validation checks schema integration and execution constraints.

### Queue/state governance

- `job_queue.py` provisions and migrates core tables including:
  - `opportunities`
  - `lifecycle_events`
  - `lifecycle_snapshots`
  - `block_logs` (with `severity`)
  - `reply_intent_training_data`
  - `funnel_health_snapshots`
- Outbound idempotency protections exist via dedupe/behavioral constraints.

### Replay/integrity governance

- `replay_audit.py` recomputes lifecycle-derived state and evidence against stored state.
- `state_engine_version` drift warnings are emitted to protect replay trust.
- `system_integrity_monitor.py` computes threshold-based block decisions for safety.

### Runtime explainability governance

- `runtime_governance.py` derives deterministic governance payloads from run report telemetry and history.
- Governance output is appended to report structure, preserving additive compatibility.

---

## Deterministic invariant catalog (Phase 0 baseline)

1. **Single production orchestrator invariant**  
   Human production-style runs go through `run_daily.py`.

2. **Single atomic report invariant**  
   Each run emits one atomic `run_report.json`.

3. **Schema authority invariant**  
   Run report structure is defined in `run_report_schema.py`.

4. **Dual-namespace invariant**  
   `outbound` and optional `cis_eval` are sibling namespaces, not one merged lifecycle.

5. **Lifecycle replay invariant**  
   Stored opportunity state must be reconstructable from lifecycle events/snapshots.

6. **Replay version integrity invariant**  
   `state_engine_version` drift is observable and auditable.

7. **Severity-governed block invariant**  
   Block events use severity semantics (`HARD`/`SOFT`/`INFO`), with freeze behavior on hard blocks.

8. **Idempotent side-effect invariant**  
   Outbound behavior is constrained to prevent duplicate side effects.

9. **Append-only telemetry compatibility invariant**  
   New telemetry should be additive and backward-compatible with existing artifacts.

---

## Observability and integrity gap analysis

### Confirmed strengths

- Core governance primitives already exist in runtime.
- Replay and drift checks already exist.
- Queue-level event/state model is present.
- Atomic reporting contract exists.

### Phase 0 gaps (no mutation yet)

1. **Contract fragmentation gap**  
   Contracts are distributed across schema, queue, and runtime modules without a single contract registry.

2. **Version lineage gap**  
   Full cross-surface version lineage is not uniformly embedded in every run artifact.

3. **Operator diagnostic cohesion gap**  
   Operator-relevant diagnostics are spread across multiple artifacts and commands.

4. **Evidence bundle gap**  
   There is no single immutable per-run evidence bundle path standard for all runtime artifacts.

5. **Telemetry consistency gap**  
   Telemetry is present but shape/placement consistency remains partially implicit across surfaces.

---

## Recommended additions (captured for later phases)

## 1) Runtime Contract Registry

Target location:

- `/home/runner/work/venture-2.0/venture-2.0/04-coding/contracts/`

Proposed modules:

- `report_contracts.py`
- `telemetry_contracts.py`
- `integrity_contracts.py`
- `governance_contracts.py`
- `replay_contracts.py`
- `version_matrix.py`

Goal: central compatibility layer for CI validation, schema evolution, and replay/version drift controls.

## 2) Runtime Version Lineage

Standard lineage tuple to embed in run-level artifacts:

- `runtime_version`
- `schema_version`
- `governance_version`
- `telemetry_version`
- `integrity_version`
- `git_sha`
- `replay_engine_version`

Goal: deterministic replay/debug compatibility across time.

## 3) Operator Cognitive Budget Rule

Formal governance rule to add to docs/contracts:

- No feature should require continuous monitoring.
- No feature should create noisy alert pressure.
- No feature should create ambiguous operational states.
- No feature should require deep forensic work for normal operation.

Goal: runtime must reduce operator cognitive load over time.

## 4) Execution Evidence Artifacts

Proposed run evidence layout:

- `artifacts/runs/<run_id>/`

Bundle intent:

- telemetry snapshot
- integrity snapshot
- governance snapshot
- queue-state snapshot
- replay metadata
- failure summaries
- execution lineage
- final report bundle

Goal: immutable operational evidence for auditability and debugging.

---

## Primary architectural risk to control

**Accidental observability overengineering** is the largest architectural risk.

Guardrails:

- Keep event set minimal and high-signal.
- Keep traces append-only and deterministic.
- Avoid nested telemetry stacks and framework churn.
- Treat telemetry as a flight recorder, not a product layer.

---

## Phase 0 execution deliverables (this cycle)

- Runtime flow map (completed in this document)
- Governance primitive map (completed in this document)
- Invariant catalog (completed in this document)
- Observability/integrity gap list (completed in this document)
- Deferred implementation targets for Phases 1+ (captured, not implemented)

No runtime mutations are authorized by this Phase 0 baseline.
