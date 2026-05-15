# LEAD GEN SYSTEM v1.4 — execution contract (audit-loop safe)

Complements **`AGENTS.md`**, **`04-coding/LEAD_GEN_PRODUCT_LAUNCH_PLAN.md`**, and **`04-coding/FOUNDER_STRATEGY_NOTE.md`**. Implementation must follow this document **and** the addendum at the end.

---

## Objective

Harden the current outbound workflow into a deterministic, cohort-tracked, audit-safe lead generation engine that enforces:

- message integrity  
- cohort traceability  
- append-only logging  
- reproducible dry-run/live behavior  
- measurement correctness for pilot conversion decisions  

This is a hardening pass for reliability and revenue signal quality. It is **not** a refactor for flexibility.

---

## 1) Non-negotiable constraints

Must comply with:

- **`AGENTS.md`** restrictions  
- **`run_daily.py`** as sole orchestrator  
- **`venture_pipeline.py`** as existing send/execution layer  
- Existing **`run_report`** flow and schema discipline  

**Hard rules:**

- No new top-level CLI entrypoints  
- No async workers, queues, or background daemons  
- No dashboard/UI work  
- No CRM integration  
- No automated reply classification  
- No parallel truth systems for send/reply state  
- No taxonomy schema mutation in this pass  

---

## 2) Scope (only this)

**Modify existing:**

- `run_daily.py`  
- `venture_pipeline.py`  
- `message_generator_solo.py`  
- `batch_guard.py` (only if needed for version metadata access; **do not** alter Batch 1 contract behavior)  

**Create new:**

- `04-coding/scripts/atomic_io.py` (atomic writes; not named `_io.py` — avoids stdlib `_io` shadowing)  
- `04-coding/scripts/metrics.py`  

**Create/update artifacts:**

- `logs/send_log.csv`  
- `logs/messages/{cohort_id}.txt`  
- `logs/dry_run/{cohort_id}.json`  
- `logs/operator_overrides.csv`  

Do **not** create new executable entrypoints with `__main__`.

---

## 3) Binding data contract (no interpretation)

**Authoritative truth order:**

1. SQLite outbound events and `run_report` outputs (authoritative send truth)  
2. `logs/send_log.csv` (denormalized export for metrics and audit convenience)  
3. `07-kpis/reply_intent_log.csv` (authoritative human intent classification)  
4. Snapshots under `logs/messages` and `logs/dry_run` (immutable audit artifacts)  

**Producer/consumer mapping:**

- `venture_pipeline.py` produces `send_log` rows  
- Operator/manual workflow produces `reply_intent_log` rows  
- `metrics.py` joins `send_log` and `reply_intent_log` using **email + cohort_id**  

**Join + dedupe rules:**

- Join key: **email + cohort_id**  
- Dedupe for reply metrics: **first reply** per email + cohort_id  
- `walkthrough_yes` is treated as a positive intent class for funnel math  
- Unknown/missing intents are tracked separately and excluded from rate denominators where appropriate  

---

## 4) Cohort identity and version tuple

**Implement in `run_daily.py`:**

- `sanitize` helper  
- `generate_cohort_id` using date + segment + message_version + **run_id suffix** to prevent same-day collision  

**Required metadata tuple on every cohort artifact:**

- `cohort_id`  
- `run_id`  
- `message_version`  
- `guard_version` (hash of `batch_guard.py`)  
- `generator_version` (hash of `message_generator_solo.py`)  
- `git_sha` (use `unknown` if unavailable)  

**Propagate tuple to:**

- `send_log` rows  
- dry-run snapshot  
- `run_report` payload extensions (**only** as specified in addendum §1)  

---

## 5) Path and time safety

- All paths **`REPO_ROOT`-anchored** using `pathlib`. Never rely on cwd.  
- Create dirs at startup if missing: `logs`, `logs/messages`, `logs/dry_run`  
- Timestamp standard: **UTC ISO 8601** from a timezone-aware clock  

---

## 6) Atomic write utility

Create `atomic_io.py` with `atomic_write(path, content)`:

- Write temp file in target dir  
- Replace target with `os.replace`  
- Ensure parent directory exists  

Use `atomic_write` for:

- `logs/messages` snapshots  
- `logs/dry_run` snapshots  

---

## 7) Message canonicalization and hashing

**Architecture rule:**

- Keep existing generator/pipeline split  
- Canonical payload is the **final rendered** message used by `venture_pipeline.py` for send  

**Hash rule:** see **addendum §4** (single canonical definition across modes and tests).  

**Normalization rule:**

- Dry-run and live must hash **identical** normalized text representation (same signature inclusion and whitespace normalization policy)  

---

## 8) Dry-run parity

Dry-run must execute the same **generation + validation** path as live (except transport call).

Write `logs/dry_run/{cohort_id}.json` containing:

- cohort metadata tuple  
- generated payloads  
- validation outcomes  
- `message_hash` values  
- planned send count  

If snapshot exists: do not overwrite; skip with notice (strict handling in §12).

**Parity binding:** see **addendum §9**.

---

## 9) Send log contract

**File:** `logs/send_log.csv`  

**Schema (locked):**

- `timestamp_utc`  
- `run_id`  
- `send_attempt_id`  
- `email`  
- `company`  
- `cohort_id`  
- `message_version`  
- `message_hash`  
- `send_status`  

**Allowed `send_status` enum (locked):** `sent`, `blocked`, `failed`, `skipped`, `dry_run`  

**Rules:**

- Create header if file missing  
- Enforce exact header match  
- Append-only  
- Idempotency guard on **`run_id` + `send_attempt_id`**  

**Single writer + ordering:** see **addendum §2–§3**.  

**Append semantics:** see **addendum §7**.  

**Attempt identity:** see **addendum §10**.  

---

## 10) Reply log contract

**File:** `07-kpis/reply_intent_log.csv`  

**Template authority:** `07-kpis/reply_intent_log.template.csv` is schema source.

**Rules:**

- If `reply_intent_log.csv` missing: create from template (operator-safe bootstrap)  
- If exists: header must exactly match template  
- Append-only; no edits/overwrites by code  
- No taxonomy schema changes in this pass  

---

## 11) Delivered and bounce definition (v1 explicit)

- **v1 delivered:** `delivered` = count(`send_status == sent`)  
- **Bounce handling:** do **not** subtract hard bounces in v1 unless a verified bounce source is wired and documented  
- **Metrics API:** no bounce-window parameters in v1 — see **addendum §8**  

---

## 12) Strict mode and blocking semantics

**In `run_daily.py`:**

- `STRICT_MODE=0`: new hardening checks emit warnings only  
- `STRICT_MODE=1`: new hardening checks may block execution  

**Important:** existing safety-critical gates remain **always-on** regardless of `STRICT_MODE`.

**Snapshot failures:** `STRICT_MODE=0` warn and continue; `STRICT_MODE=1` block.  

**Header/schema failures:** `STRICT_MODE=0` warn and continue only where safe; `STRICT_MODE=1` block before sends.  

---

## 13) Manual override audit

If a strict block is overridden, append a row to **`logs/operator_overrides.csv`**.

**Override schema (locked):** `timestamp_utc`, `operator`, `reason`, `strict_mode`, `cohort_id`, `action`, `outcome`  

No silent bypasses.

---

## 14) Metrics library (no CLI)

Create **`metrics.py`** as importable library only.

**Implement:** `safe_div`, `compute_metrics(reply_log_path, send_log_path)`  

**Definitions:** see **addendum §5–§6** and §11 for delivered.

**Sanity checks:**

- `positive_replies <= delivered`  
- `walkthrough_yes <= positive_replies` (logging discipline rule)  
- Invalid states raise explicit exceptions  

**Also output counts for:** `not_now`, `not_a_fit`, `unsubscribe`, `unknown_or_missing_intent`  

---

## 15) Pre-send manual checklist output

Emit reminder before live send:

- Reply log exists (or was bootstrapped from template)  
- Reply header check passed  
- Previous batch reviewed  
- Planned sends within operator capacity  
- Dry-run snapshot generated  
- Cohort metadata tuple confirmed  

---

## 16) Test requirements

Add/update tests for:

- cwd independence via `REPO_ROOT` pathing  
- `cohort_id` uniqueness for same-day reruns  
- Immutable snapshot behavior (write-once)  
- `send_log` header creation and strict schema enforcement  
- Idempotent append on retry  
- `message_hash` consistency from final rendered payload (**per addendum §4**)  
- Dry-run/live generation parity (**per addendum §9**)  
- Strict mode advisory vs blocking  
- Reply log bootstrap from template and header validation  

---

## 17) Validation commands

Run exactly:

```powershell
.venv\Scripts\python -m pytest tests -q
.venv\Scripts\python 04-coding\scripts\validate_repo_contract.py
```

Then scenario checks: missing reply log; malformed reply header; duplicate `run_id` + `send_attempt_id`; existing snapshot; `STRICT_MODE=0` vs `1`.

---

## 18) Explicit non-goals

Do not implement: dashboard/UI; queue/workers; CRM sync; classifier automation; A/B framework; new top-level CLI commands.

---

## 19) End-state definition

Implementation is correct only if each cohort is:

- **Traceable:** cohort tuple across logs/snapshots/report  
- **Reproducible:** same final message hash for same inputs/path (**per addendum §4**)  
- **Measurable:** rates from explicit v1 definitions  
- **Audit-safe:** append-only logs, immutable snapshots, override trail  
- **Operationally bounded:** strict mode and idempotency controls  

---

## Addendum — must-fix closure (bind before implementation)

*Paste this block into any derivative prompt; it is part of v1.4.*

1. **Run report schema binding:** All run report extensions must be implemented only through Pydantic models in `run_report_schema.py`, plus the corresponding writer and tests. No ad-hoc keys may be injected directly into report payload dictionaries.

2. **Single send log writer:** Only one function may append send log rows (for example, a dedicated helper called from `venture_pipeline.py` after authoritative outcome resolution). Neither `run_daily.py` nor any other layer may append independently.

3. **Ordering versus authoritative persistence:** A row may be appended to `logs/send_log.csv` only after the corresponding authoritative outbound outcome has been persisted in the primary system of record for that send path.

4. **Message hash contract:** Use one explicit canonical hash definition across all modes and tests: **hash equals SHA-256 of subject + rendered HTML payload** exactly as used by the current send path in `venture_pipeline.py`. If this definition is changed, all dependent expectations, storage, and tests must be updated in the same change set.

5. **Positive replies definition:** `positive_replies` means count of reply rows classified as **`positive_reply` only**. `walkthrough_yes` is tracked separately and does **not** increment `positive_replies`.

6. **Metrics formulas:** `positive_reply_rate` = `positive_replies / delivered`. `walkthrough_yes_rate` = `walkthrough_yes / delivered`. `conversion_ratio` = `walkthrough_yes / positive_replies`.

7. **CSV append semantics:** CSV append operations are append-mode writes, not atomic replace semantics. Use a single append path with newline control and best-effort flush semantics; deduplication via `run_id` + `send_attempt_id` is the primary duplicate prevention mechanism.

8. **Metrics API stability:** The v1 metrics API must not require bounce window parameters. Delivered is defined in v1 as `send_status == sent`. Bounce-adjusted delivered is deferred to v2 when verified bounce source wiring exists.

9. **Dry-run parity binding:** Dry-run snapshots must be produced from the **same finalized payload object** used to compute `message_hash` in that run mode, so parity checks validate the exact hashed payload representation.

10. **Attempt identity rule:** `send_attempt_id` is generated once per provider attempt and remains stable for retries of that attempt. A new `send_attempt_id` is created only when a new attempt is intentionally started.

11. **Git SHA fallback:** `git_sha` must always be populated; use `unknown` when git metadata is unavailable.

12. **Contract validator note:** If contract checks enforce file/path/import constraints, update those checks in the same change set so validation reflects the new contract-driven paths and helpers.

---

## Appendix B — Phase 1: execution parity (`execute_send`) **[FINAL]**

*Locks the next implementation slice. Does not replace §1–§19; it refines **what Phase 1 means** once v1.4 scaffolding is in place.*

### B.0 Core principle (hard constraint)

Parity is **not** a structural reorganisation of the whole pipeline. It is a refactor of **execution boundary ownership**: one **invariant execution kernel** inside `venture_pipeline.py`, with **transport** as the only axis that differs between dry-run and live.

**Do not:** move orchestration into `run_daily.py`; add parallel orchestration modules; split send truth across multiple writers.

### B.1 True chokepoint (confirmed)

**Primary divergence:** `venture_pipeline.py` → per-prospect loop — specifically the interaction of `AUTO_SEND_EMAILS`, `DRY_RUN`, qualification, `record_outbound`, `send_email` / `send_email_safe`, and `_append_send_log_row`.

### B.2 Required model: `execute_send(...)` inside `venture_pipeline.py`

Introduce a single wrapper (name may be `execute_send` or equivalent; **location is mandatory**):

- It **owns** the execution surface: qualification (existing logic, no gratuitous reorder), lifecycle / persistence hooks, transport, and `send_log` append.
- **Dry-run and live MUST share the same call graph**; they differ **only** in transport (e.g. `send_email_safe(..., dry_run=True)` vs `False`, or an injected transport with no network side effect).

### B.3 Dry-run policy (**Option A required** for true parity)

For Phase 1 to mean **parity**, dry-run **must** still run:

- qualification (unchanged semantics where possible),
- **`record_outbound`** (with a clear **dry** semantic — e.g. status / provider marker agreed with SQLite schema),
- **`send_log`** append with `send_status=dry_run` (or equivalent locked enum),

and use **no-op or stub transport** instead of live Resend.

**Option B** (skip `record_outbound` / `send_log` in dry-run) is explicitly **out of scope** for Phase 1 parity — it preserves weaker guarantees only.

**Implementation note (today vs target):** As of the v1.4 scaffolding pass, `record_outbound` and `_append_send_log_row` live **inside** `send_email` after transport success. Phase 1 work **reconciles** that with this appendix by hoisting or re-threading so the **observable sequence** matches §B.4 without changing money-path safety gates.

### B.4 Order of operations (target invariant)

Inside the execution kernel, **same order** for dry-run and live (transport excepted):

1. Qualify (existing checks).  
2. Persist outbound event (`record_outbound`) — **Option A: also in dry-run**, with dry semantics.  
3. Transport (`send_email_safe` / Resend) — dry = no external send.  
4. **`send_log` append** — after persistence, same ordering as live; `send_status` reflects dry vs sent.  
5. Return structured result to the loop.

### B.5 Testing (mandatory for Phase 1 “done”)

Add a **trace-based** test (not only hash equality):

- Monkeypatch `send_email_safe` (or transport) so dry-run does not hit the network.  
- Assert **identical invocation order** of qualification → persistence → transport → send_log between `dry_run=True` and `dry_run=False` for the same prospect fixture (differing only in transport args / response).  
- Optional: record an `execution_trace` list and `assert trace_dry == trace_live` modulo transport payload.

### B.6 Phase 2 / 3 alignment (do not implement early)

- **Per-row lock (Phase 2):** New `generated-outreach.csv` columns (`message_version`, `generator_version`, `guard_version`, `message_hash`, `cohort_id`) must be **nullable / default empty**; old rows stay valid without backfill.  
- **Cohort message snapshot (Phase 3):** One `logs/messages/{cohort_id}.txt` per cohort, write-once, built from the **exact** subject + body + CTA strings used for `message_hash`, after the batch slice is fixed (not per-prospect spam).

### B.7 Phase 1 success criteria (all required)

1. **Execution identity:** dry-run call graph == live call graph (transport only differs).  
2. **Ordering invariance:** same side-effect order for qualification → persistence → transport → send_log.  
3. **Observable structure:** `send_log` schema unchanged; `record_outbound` semantics documented for dry vs live.  
4. **Test:** trace-based equivalence test passes.

### B.8 Later phases (unchanged intent)

- **Phase 4:** `STRICT_PROSPECT_MODE` (demo vs production validity).  
- **Phase 5:** optional `cohort.py` (or similar) **only after** Phase 1 stabilises — avoids reintroducing fragmentation mid-refactor.

---

**Execute exactly as specified.** No architectural expansion beyond scope.
