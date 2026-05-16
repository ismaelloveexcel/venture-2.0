#!/usr/bin/env python3
"""
Canonical daily orchestrator (vFINAL.1).

Single user-facing entrypoint: optional prospect build + message generation +
venture_pipeline, dual-namespace report (outbound + optional cis_eval).
Writes one atomic run_report.json.

Semantic / production boundary: `docs/SEMANTIC_CONTRACT.md` §8.1 — this module is the
canonical production-style orchestrator; do not treat `venture_pipeline.py` as
an alternate human entrypoint for governed sends.

End-to-end dry-run (no API keys required when using template + local messages):
  python 04-coding/scripts/run_daily.py --generate-prospects --prospects-demo \\
      --execute-outbound --dry-run
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

# Ensure sibling imports resolve when executed as script
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from fast_test_subset import FAST_TEST_PATHS
from run_report_schema import (
    CisEvalSection,
    CohortMetadataModel,
    FunnelHealthSnapshotModel,
    OrchestratorTelemetryModel,
    OutboundSection,
    OutboundStatus,
    PipelineTelemetry,
    ProspectBatchModel,
    RuntimeGovernanceModel,
    RunReport,
    SystemSection,
)
from runtime_governance import build_runtime_governance
from run_report_writer import resolve_run_report_path, write_run_report_atomic

from atomic_io import atomic_write
from batch_guard import CANONICAL_SUBJECT, CTA_STRING
from metrics import canonical_message_hash
from prospect_gate import sanitize_run_id_fs
from runtime_config import _is_effective_secret, resolve_data_base

REPO_ROOT = _SCRIPTS.parent.parent
REPLY_LOG_TEMPLATE = REPO_ROOT / "07-kpis" / "reply_intent_log.template.csv"
REPLY_LOG_LIVE = REPO_ROOT / "07-kpis" / "reply_intent_log.csv"
SOLO_OPERATOR_RUN_REPORT = REPO_ROOT / "docs" / "solo-operator" / "run_report.json"


def _prospects_csv_path() -> Path:
    return resolve_data_base(REPO_ROOT) / "06-sales" / "prospects.csv"


def _outreach_csv_path() -> Path:
    return resolve_data_base(REPO_ROOT) / "06-sales" / "generated-outreach.csv"


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        return ""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _git_sha_resolved() -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown"


def _sanitize_cohort_token(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "_", (value or "").strip().lower()).strip("_")
    return cleaned or "na"


def _build_cohort_metadata(run_id: str, segment: str) -> CohortMetadataModel:
    guard_v = _sha256_file(_SCRIPTS / "batch_guard.py")
    gen_v = _sha256_file(_SCRIPTS / "message_generator_solo.py")
    git_sha = _git_sha_resolved()
    message_version = (gen_v or guard_v)[:12] or "unknownver"
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    cohort_id = f"{date_part}_{_sanitize_cohort_token(segment)[:24]}_{message_version}_{run_id[:8]}"
    freeze_ts = datetime.now(timezone.utc).isoformat()
    policy_raw = (CANONICAL_SUBJECT + "\n" + CTA_STRING).encode("utf-8")
    subject_cta_fp = hashlib.sha256(policy_raw).hexdigest()[:12]
    return CohortMetadataModel(
        cohort_id=cohort_id,
        run_id=run_id,
        message_version=message_version,
        guard_version=guard_v or "unknown",
        generator_version=gen_v or "unknown",
        git_sha=git_sha,
        freeze_timestamp_utc=freeze_ts,
        subject_cta_fingerprint=subject_cta_fp,
    )


def _publish_cohort_env(cm: CohortMetadataModel) -> None:
    os.environ["VENTURE_COHORT_ID"] = cm.cohort_id
    os.environ["VENTURE_MESSAGE_VERSION"] = cm.message_version
    os.environ["VENTURE_GUARD_VERSION"] = cm.guard_version
    os.environ["VENTURE_GENERATOR_VERSION"] = cm.generator_version
    os.environ["VENTURE_GIT_SHA"] = cm.git_sha


def _ensure_log_directories() -> None:
    for rel in ("logs", "logs/messages", "logs/dry_run"):
        (REPO_ROOT / rel).mkdir(parents=True, exist_ok=True)


def _bootstrap_reply_intent_log(*, strict_mode: bool) -> None:
    if not REPLY_LOG_TEMPLATE.is_file():
        return
    if not REPLY_LOG_LIVE.is_file():
        REPLY_LOG_LIVE.write_text(
            REPLY_LOG_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
        )
        return
    hdr_t = REPLY_LOG_TEMPLATE.read_text(encoding="utf-8").splitlines()[0].strip()
    hdr_l_lines = REPLY_LOG_LIVE.read_text(encoding="utf-8").splitlines()[:1]
    hdr_l = hdr_l_lines[0].strip() if hdr_l_lines else ""
    if hdr_t != hdr_l:
        msg = "reply_intent_log.csv header mismatch vs reply_intent_log.template.csv"
        if strict_mode:
            print(f"[fail] {msg}", file=sys.stderr)
            raise SystemExit(3)
        print(f"[warn] {msg}", file=sys.stderr)


def _ensure_operator_overrides_stub() -> None:
    path = REPO_ROOT / "logs" / "operator_overrides.csv"
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "timestamp_utc,operator,reason,strict_mode,cohort_id,action,outcome\n",
        encoding="utf-8",
    )


def _print_pre_send_checklist() -> None:
    print(
        "\n".join(
            [
                "[checklist] Pre-send (manual):",
                "  - reply_intent_log.csv exists / header OK",
                "  - previous batch reviewed",
                "  - planned sends within operator capacity",
                "  - dry-run snapshot generated when using --dry-run",
                "  - cohort metadata in run_report outbound.cohort_metadata",
            ]
        ),
        flush=True,
    )


def _maybe_write_dry_run_snapshot(
    *,
    dry_run: bool,
    execute_outbound: bool,
    outbound_status: OutboundStatus,
    cohort: CohortMetadataModel | None,
) -> None:
    if not (execute_outbound and dry_run and cohort and outbound_status == "SUCCESS"):
        return
    snap_path = REPO_ROOT / "logs" / "dry_run" / f"{cohort.cohort_id}.json"
    if snap_path.is_file():
        print(f"[cohort] dry_run snapshot exists, skip: {snap_path.name}", flush=True)
        return
    rows: list[dict[str, str | int]] = []
    outreach_csv = _outreach_csv_path()
    if outreach_csv.is_file():
        with outreach_csv.open(newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                if (row.get("status") or "").strip().upper() != "PASS":
                    continue
                if (row.get("approved") or "").strip().lower() != "yes":
                    continue
                msg = (row.get("message") or "").strip()
                if not msg:
                    continue
                from message_generator_solo import (
                    strip_outreach_signature,
                )  # noqa: PLC0415
                from send_guard import materialize_outbound_payload  # noqa: PLC0415

                cold = strip_outreach_signature(msg).strip()
                from_email = (
                    os.environ.get("RESEND_FROM_EMAIL", "") or "outreach@abtmail.co"
                ).strip()
                from_name = (
                    os.environ.get("RESEND_FROM_NAME", "") or "Ismael Sudally"
                ).strip()
                mat = materialize_outbound_payload(
                    {
                        "from": f"{from_name} <{from_email}>",
                        "to": ["dry_run_preview@invalid.local"],
                        "subject": CANONICAL_SUBJECT,
                        "cold_body_text": cold,
                    },
                    send_type="initial_prospect",
                )
                html = str(mat.get("html") or "")
                mh = canonical_message_hash(CANONICAL_SUBJECT, html)
                rows.append(
                    {
                        "email": "",
                        "company_name": (row.get("company_name") or "").strip(),
                        "message_hash": mh,
                    }
                )
    payload = {
        "cohort_metadata": cohort.model_dump(),
        "generated_rows": rows,
        "planned_send_count": len(rows),
    }
    atomic_write(snap_path, json.dumps(payload, indent=2, sort_keys=True))


def _sync_solo_operator_run_report(report_path: Path) -> None:
    """Mirror the canonical run report to the solo-operator dashboard data path."""
    if os.environ.get("VENTURE_SKIP_SOLO_OPERATOR_SYNC", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    try:
        if not report_path.is_file():
            return
        SOLO_OPERATOR_RUN_REPORT.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(
            SOLO_OPERATOR_RUN_REPORT,
            report_path.read_text(encoding="utf-8"),
        )
    except OSError as exc:
        print(
            f"[warn] failed to sync solo operator run report: {exc}",
            file=sys.stderr,
            flush=True,
        )


def _prospect_validation_counts() -> tuple[int, int, int, int]:
    """(ready, review, reject, total_rows) from prospects.csv."""
    prospects_csv = _prospects_csv_path()
    if not prospects_csv.is_file():
        return 0, 0, 0, 0
    ready = review = reject = 0
    with prospects_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            st = (
                (row.get("validation_status") or row.get("readiness_status") or "")
                .strip()
                .upper()
            )
            if st == "READY":
                ready += 1
            elif st == "REVIEW":
                review += 1
            elif st == "REJECT":
                reject += 1
    total = ready + review + reject
    return ready, review, reject, total


def _outreach_pass_fail_approved() -> tuple[int, int, int]:
    """PASS count, FAIL count, rows with status PASS and approved=yes."""
    outreach_csv = _outreach_csv_path()
    if not outreach_csv.is_file():
        return 0, 0, 0
    n_pass = n_fail = n_appr = 0
    with outreach_csv.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            st = (row.get("status") or "").strip().upper()
            if st == "PASS":
                n_pass += 1
                if (row.get("approved") or "").strip().lower() == "yes":
                    n_appr += 1
            elif st == "FAIL":
                n_fail += 1
    return n_pass, n_fail, n_appr


# Env vars commonly required for live prospect + outbound paths (values never printed).
_BRIDGE_SECRET_KEYS: tuple[str, ...] = (
    "APOLLO_API_KEY",
    "HUNTER_API_KEY",
    "OPENAI_API_KEY",
    "RESEND_API_KEY",
)


def _bridge_secrets_status() -> int:
    """Report set/missing/placeholder only — same dotenv rule as prospect_builder."""
    from dotenv import load_dotenv

    env_path = REPO_ROOT / ".env"
    print(
        f"DOTENV_FILE\tpath={env_path}\texists={'yes' if env_path.is_file() else 'no'}"
    )
    load_dotenv(env_path)
    for name in _BRIDGE_SECRET_KEYS:
        raw = os.environ.get(name, "")
        stripped = (raw or "").strip()
        if not stripped:
            print(f"SECRET_STATUS\t{name}\tmissing")
            continue
        if not _is_effective_secret(stripped):
            print(f"SECRET_STATUS\t{name}\tplaceholder")
            continue
        print(f"SECRET_STATUS\t{name}\tset\tchars={len(stripped)}")
    return 0


def _bridge(argv: list[str]) -> int:
    """P5: delegate validate/status without widening the argparse allowlist surface."""
    if not argv:
        print(
            "usage: run_daily.py bridge validate|preflight|status|secrets",
            file=sys.stderr,
        )
        return 2
    sub = argv[0].strip().lower()
    if sub == "validate":
        validate_env = os.environ.copy()
        validate_env.pop("VENTURE_CANONICAL_ENTRY", None)
        validate_env.pop("VENTURE_DEV_MAIN", None)
        c = subprocess.run(
            [sys.executable, str(_SCRIPTS / "validate_repo_contract.py")],
            cwd=str(REPO_ROOT),
            env=validate_env,
        ).returncode
        t = subprocess.run(
            [sys.executable, "-m", "pytest", *FAST_TEST_PATHS, "-q"],
            cwd=str(REPO_ROOT),
            env=validate_env,
        ).returncode
        return 0 if c == 0 and t == 0 else 1
    if sub == "preflight":
        from bridge_preflight import format_preflight_report, run_preflight_checks

        ok_pf, rsn = run_preflight_checks()
        print(format_preflight_report(ok_pf, rsn), end="", flush=True)
        return 0 if ok_pf else 1
    if sub == "status":
        rc = subprocess.run(
            [sys.executable, str(_SCRIPTS / "venture_pipeline.py"), "--status"],
            cwd=str(REPO_ROOT),
            env=os.environ.copy(),
        ).returncode
        gate_path = REPO_ROOT / "07-kpis" / "gate_status.json"
        pause_path = REPO_ROOT / "04-coding" / "state" / "operator_pause_state.json"
        op_log = REPO_ROOT / "07-kpis" / "operator_execution_log.csv"
        if gate_path.is_file():
            try:
                gate = json.loads(gate_path.read_text(encoding="utf-8"))
                print(
                    "GATE_STATUS\t"
                    + f"gate_a={gate.get('gate_a_score_pct')}\t"
                    + f"gate_a_pass={gate.get('gate_a_pass')}\t"
                    + f"gate_b_pass={gate.get('gate_b_pass')}\t"
                    + f"stop_loss={gate.get('stop_loss_triggered')}"
                )
            except Exception:  # noqa: BLE001
                print("GATE_STATUS\tunreadable")
        else:
            print("GATE_STATUS\tmissing")
        if pause_path.is_file():
            try:
                pause = json.loads(pause_path.read_text(encoding="utf-8"))
                print(
                    "PAUSE_STATE\t"
                    + f"paused={pause.get('paused')}\t"
                    + f"reasons={','.join(pause.get('reasons') or [])}"
                )
            except Exception:  # noqa: BLE001
                print("PAUSE_STATE\tunreadable")
        else:
            print("PAUSE_STATE\tmissing")
        if op_log.is_file():
            try:
                with op_log.open(newline="", encoding="utf-8") as fh:
                    rows = list(csv.DictReader(fh))
                if rows:
                    last = rows[-1]
                    date_val = last.get("date") or last.get("\ufeffdate")
                    if not date_val:
                        for k, v in last.items():
                            if "date" in str(k).lower():
                                date_val = v
                                break
                    print(
                        "OPERATOR_LOG_LAST\t"
                        + f"date={date_val}\t"
                        + f"run_id={last.get('run_id')}\t"
                        + f"action={last.get('action_taken')}"
                    )
                else:
                    print("OPERATOR_LOG_LAST\tempty")
            except Exception:  # noqa: BLE001
                print("OPERATOR_LOG_LAST\tunreadable")
        else:
            print("OPERATOR_LOG_LAST\tmissing")
        return rc
    if sub == "secrets":
        return _bridge_secrets_status()
    print(f"run_daily bridge: unknown subcommand {argv[0]!r}", file=sys.stderr)
    return 2


def _telemetry_schema_soft_reasons(parsed: PipelineTelemetry) -> list[str]:
    """Soft guard: orchestrator expects schema_version 1; do not fail the run."""
    if parsed.schema_version != 1:
        return ["unknown_telemetry_schema_version"]
    return []


def _validate_pipeline_telemetry_soft(
    telemetry: object,
) -> tuple[PipelineTelemetry, list[str]]:
    """Validate pipeline telemetry without breaking orchestrator flow."""
    if not isinstance(telemetry, dict):
        return PipelineTelemetry(), ["pipeline_telemetry_invalid"]
    try:
        return PipelineTelemetry.model_validate(telemetry), []
    except ValidationError as exc:
        reasons: list[str] = []
        invalid_fields: set[str] = set()
        for err in exc.errors():
            loc = err.get("loc") or ()
            if loc and isinstance(loc[0], str):
                invalid_fields.add(loc[0])

        sanitized = dict(telemetry)
        if "phase1_structured" in invalid_fields and "phase1_structured" in sanitized:
            sanitized.pop("phase1_structured", None)
            reasons.append("phase1_structured_dropped_invalid")

        other_invalid_fields = invalid_fields - {"phase1_structured"}
        for field in other_invalid_fields:
            sanitized.pop(field, None)
        if other_invalid_fields:
            reasons.append("pipeline_telemetry_invalid")

        try:
            return PipelineTelemetry.model_validate(sanitized), reasons
        except ValidationError:
            if "pipeline_telemetry_invalid" not in reasons:
                reasons.append("pipeline_telemetry_invalid")
            return PipelineTelemetry(), reasons


def _merge_pipeline_telemetry(
    outbound: OutboundSection, telemetry: dict, *, dry_run: bool
) -> OutboundSection:
    """Attach validated telemetry; promote counts into money_path only when run_health is present."""
    parsed, validation_reasons = _validate_pipeline_telemetry_soft(telemetry)
    schema_extra = _telemetry_schema_soft_reasons(parsed)
    extras = schema_extra + validation_reasons
    o = outbound.model_copy(update={"pipeline_telemetry": parsed})
    rh = parsed.run_health
    if not isinstance(rh, dict):
        if extras:
            mp = o.money_path.model_copy(
                update={"reasons": list(o.money_path.reasons) + extras}
            )
            o = o.model_copy(update={"money_path": mp})
        return o
    sent = int(rh.get("sent") or 0)
    blocked = int(rh.get("blocked") or 0)
    attempted = max(0, sent + blocked)
    reasons = ["venture_pipeline_exit_0"]
    if dry_run:
        reasons.append("dry_run")
    else:
        reasons.append("live_pipeline_telemetry")
    reasons.append("pipeline_telemetry")
    reasons.extend(extras)
    return o.model_copy(
        update={
            "money_path": o.money_path.model_copy(
                update={
                    "attempted": attempted,
                    "sent": sent,
                    "blocked": blocked,
                    "reasons": reasons,
                }
            ),
            "money_path_source": "pipeline_telemetry",
        }
    )


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_client_report_artifacts(
    report: RunReport, client_id: str | None = None
) -> dict[str, str]:
    """
    Render client-facing campaign report artifacts from canonical run_report data.

    If client_id is provided, also generates static HTML dashboard in client-scoped directory.
    """
    artifacts: dict[str, str] = {}

    try:
        reporting_dir = REPO_ROOT / "04-coding" / "venture-engine" / "reporting"
        if str(reporting_dir) not in sys.path:
            sys.path.insert(0, str(reporting_dir))
        from report_renderer import build_campaign_report_artifacts  # noqa: PLC0415

        output_dir = (
            resolve_data_base(REPO_ROOT)
            / "04-coding"
            / "reports"
            / "campaign-intelligence"
        )
        artifacts = build_campaign_report_artifacts(
            report,
            repo_root=REPO_ROOT,
            output_dir=output_dir,
        )
    except Exception:
        pass

    # Generate client-scoped deterministic delivery artifacts if client_id provided.
    if client_id:
        try:
            engine_path = REPO_ROOT / "04-coding" / "venture-engine"
            if str(engine_path) not in sys.path:
                sys.path.insert(0, str(engine_path))
            from client_runtime import (
                get_client_router,
                get_previous_run,
            )  # noqa: PLC0415
            from client_runtime.comparison_engine import run_comparison  # noqa: PLC0415
            from client_runtime.dashboard_renderer import (  # noqa: PLC0415
                render_client_dashboard,
            )
            from client_runtime.health_score import compute_health  # noqa: PLC0415

            router = get_client_router(REPO_ROOT)
            run_id = report.run_id

            router.ensure_client_structure(client_id)
            router.ensure_run_directory(client_id, run_id)

            run_report_path = router.get_run_report_path(client_id, run_id)
            projection_path = router.get_projection_path(client_id, run_id)
            comparison_path = router.get_comparison_path(client_id, run_id)
            health_path = router.get_health_path(client_id, run_id)
            dashboard_path = router.get_dashboard_path(client_id, run_id)

            current_report_payload = report.model_dump(mode="json")
            atomic_write(
                run_report_path,
                json.dumps(current_report_payload, indent=2, sort_keys=True),
            )

            current_projection_payload: dict[str, Any] = {}
            projection_src = artifacts.get("projection")
            if projection_src:
                try:
                    psrc = Path(projection_src)
                    if psrc.is_file():
                        current_projection_payload = json.loads(
                            psrc.read_text(encoding="utf-8")
                        )
                except (OSError, json.JSONDecodeError):
                    current_projection_payload = {}
            atomic_write(
                projection_path,
                json.dumps(current_projection_payload, indent=2, sort_keys=True),
            )

            previous_run_dir = get_previous_run(
                client_id,
                run_id,
                repo_root=REPO_ROOT,
            )
            previous_report_payload: dict[str, Any] | None = None
            previous_projection_payload: dict[str, Any] | None = None
            if previous_run_dir is not None:
                prev_report_path = previous_run_dir / "run_report.json"
                prev_projection_path = previous_run_dir / "projection.json"
                try:
                    if prev_report_path.is_file():
                        previous_report_payload = json.loads(
                            prev_report_path.read_text(encoding="utf-8")
                        )
                    if prev_projection_path.is_file():
                        previous_projection_payload = json.loads(
                            prev_projection_path.read_text(encoding="utf-8")
                        )
                except (OSError, json.JSONDecodeError):
                    print(
                        "[warn] previous run artifacts unreadable; treating as baseline",
                        file=sys.stderr,
                        flush=True,
                    )
                    previous_report_payload = None
                    previous_projection_payload = None

            comparison = run_comparison(
                current_report=current_report_payload,
                current_projection=current_projection_payload,
                previous_report=previous_report_payload,
                previous_projection=previous_projection_payload,
            )
            health = compute_health(comparison)

            atomic_write(
                comparison_path,
                json.dumps(comparison, indent=2, sort_keys=True),
            )
            atomic_write(
                health_path,
                json.dumps(health, indent=2, sort_keys=True),
            )

            dashboard_html = render_client_dashboard(
                run_report=current_report_payload,
                projection=current_projection_payload,
                output_path=dashboard_path,
                client_id=client_id,
                comparison=comparison,
                health=health,
            )
            atomic_write(dashboard_path, dashboard_html)

            # POST_DASHBOARD_OPS: deterministic filesystem-only client runtime layer.
            intake_context: dict[str, Any] = {
                "client_id": client_id,
                "execution_intent": {
                    "icp": "",
                    "offer": "",
                    "constraints": [],
                    "targeting_mode": "unknown",
                    "success_definition": {},
                },
            }
            raw_config: dict[str, Any] = {}
            config_path = router.get_client_config_path(client_id)
            if config_path.is_file():
                try:
                    from client_runtime.onboarding.intake_builder import (  # noqa: PLC0415
                        build_intake_context,
                    )

                    raw_config = json.loads(config_path.read_text(encoding="utf-8"))
                    if isinstance(raw_config, dict):
                        intake_context = build_intake_context(raw_config)
                except (OSError, json.JSONDecodeError, ValueError):
                    pass

            from client_runtime.value_layer.value_summary import (  # noqa: PLC0415
                generate_value_summary,
            )

            from client_runtime.delivery.package_builder import (  # noqa: PLC0415
                build_delivery_package,
            )
            from client_runtime.delivery.artifact_manifest import (  # noqa: PLC0415
                build_artifact_manifest,
            )
            from client_runtime.delivery.export_bundle import (  # noqa: PLC0415
                export_bundle,
            )
            from client_runtime.executive import (  # noqa: PLC0415
                generate_executive_outputs,
            )
            from client_runtime.operator import (  # noqa: PLC0415
                generate_operator_outputs,
            )
            from client_runtime.sales import (  # noqa: PLC0415
                generate_sales_outputs,
            )
            from client_runtime.trends import (  # noqa: PLC0415
                generate_trend_outputs,
            )
            from client_runtime.campaigns import (  # noqa: PLC0415
                update_campaign_state,
            )
            from client_runtime.queue import (  # noqa: PLC0415
                update_prospect_queue,
            )
            from client_runtime.replies import (  # noqa: PLC0415
                generate_reply_summary,
            )
            from client_runtime.approval import (  # noqa: PLC0415
                persist_approval_state,
            )
            from client_runtime.patterns import (  # noqa: PLC0415
                update_pattern_memory,
            )

            run_dir = router.get_run_output_dir(client_id, run_id)
            outbound_payload = (
                current_report_payload.get("outbound")
                if isinstance(current_report_payload, dict)
                else {}
            )
            outbound_payload = (
                outbound_payload if isinstance(outbound_payload, dict) else {}
            )
            outbound_status = str(outbound_payload.get("status") or "NOT_EXECUTED")
            campaign_name = str(raw_config.get("campaign_name") or run_id).strip()
            campaign_id = sanitize_run_id_fs(campaign_name)[:80] or run_id

            campaign_outputs = update_campaign_state(
                repo_root=REPO_ROOT,
                client_id=client_id,
                campaign_id=campaign_id,
                run_id=run_id,
                outbound_status=outbound_status,
                run_dir=run_dir,
            )
            queue_outputs = update_prospect_queue(
                run_dir=run_dir,
                run_report=current_report_payload,
            )
            reply_outputs = generate_reply_summary(
                run_dir=run_dir,
                run_report=current_report_payload,
                reply_texts=[],
            )
            approval_outputs = persist_approval_state(
                run_dir=run_dir,
                run_report=current_report_payload,
            )
            pattern_outputs = update_pattern_memory(
                repo_root=REPO_ROOT,
                run_dir=run_dir,
                client_id=client_id,
                run_id=run_id,
                intake_context=intake_context,
                subject_line=CANONICAL_SUBJECT,
                cta_pattern=CTA_STRING,
                run_report=current_report_payload,
                reply_summary=reply_outputs["reply_summary"],
            )
            value_summary = generate_value_summary(
                run_report=current_report_payload,
                projection=current_projection_payload,
                comparison=comparison,
                health=health,
            )
            value_summary_path = run_dir / "value_summary.json"
            atomic_write(
                value_summary_path,
                json.dumps(value_summary, indent=2, sort_keys=True),
            )
            delivery_package = build_delivery_package(
                client_id=client_id,
                run_id=run_id,
                run_timestamp=str(current_report_payload.get("timestamp_utc") or ""),
                engine_version=str(
                    current_report_payload.get("schema_version") or "unknown"
                ),
                run_dir=run_dir,
                artifact_paths={
                    "dashboard": str(dashboard_path),
                    "health": str(health_path),
                    "comparison": str(comparison_path),
                    "summary": str(value_summary_path),
                },
                intake_context=intake_context,
            )
            delivery_manifest = build_artifact_manifest(delivery_package)
            delivery_bundle_path = run_dir / "delivery_bundle.json"
            export_bundle(delivery_manifest, delivery_bundle_path)
            executive_outputs = generate_executive_outputs(
                run_dir=run_dir,
                client_id=client_id,
                run_report=current_report_payload,
                projection=current_projection_payload,
                comparison=comparison,
                health=health,
                value_summary=value_summary,
            )
            trend_outputs = generate_trend_outputs(
                repo_root=REPO_ROOT,
                client_id=client_id,
                run_id=run_id,
                run_dir=run_dir,
            )
            operator_outputs = generate_operator_outputs(
                run_dir=run_dir,
                executive_outputs=executive_outputs,
                trend_outputs=trend_outputs,
                health=health,
                value_summary=value_summary,
            )
            sales_outputs = generate_sales_outputs(
                run_dir=run_dir,
                client_id=client_id,
                executive_outputs=executive_outputs,
                trend_outputs=trend_outputs,
                operator_outputs=operator_outputs,
                roi_projection=executive_outputs.get("roi_projection") or {},
                value_summary=value_summary,
                intake_context=intake_context,
            )

            artifacts["dashboard"] = str(dashboard_path)
            artifacts["comparison"] = str(comparison_path)
            artifacts["health"] = str(health_path)
            artifacts["value_summary"] = str(value_summary_path)
            artifacts["delivery_bundle"] = str(delivery_bundle_path)
            artifacts.update(
                {
                    "executive_summary": executive_outputs["paths"][
                        "executive_summary"
                    ],
                    "executive_brief": executive_outputs["paths"]["executive_brief"],
                    "stakeholder_snapshot": executive_outputs["paths"][
                        "stakeholder_snapshot"
                    ],
                    "roi_projection": executive_outputs["paths"]["roi_projection"],
                    "trend_summary": trend_outputs["paths"]["trend_summary"],
                    "timeline": trend_outputs["paths"]["timeline"],
                    "performance_windows": trend_outputs["paths"][
                        "performance_windows"
                    ],
                    "trend_projection": trend_outputs["paths"]["trend_projection"],
                    "operator_queue": operator_outputs["paths"]["operator_queue"],
                    "operator_tasks": operator_outputs["paths"]["operator_tasks"],
                    "priority_actions": operator_outputs["paths"]["priority_actions"],
                    "workflow_state": operator_outputs["paths"]["workflow_state"],
                    "pilot_summary": sales_outputs["paths"]["pilot_summary"],
                    "commercial_snapshot": sales_outputs["paths"][
                        "commercial_snapshot"
                    ],
                    "sales_snapshot": sales_outputs["paths"]["sales_snapshot"],
                    "case_study": sales_outputs["paths"]["case_study"],
                    "proposal_seed": sales_outputs["paths"]["proposal_seed"],
                    "campaign_state": campaign_outputs["run_path"],
                    "queue": queue_outputs["paths"]["queue"],
                    "queue_metrics": queue_outputs["paths"]["queue_metrics"],
                    "reply_summary": reply_outputs["paths"]["reply_summary"],
                    "approval_queue": approval_outputs["paths"]["approval_queue"],
                    "pattern_memory": pattern_outputs["paths"]["pattern_memory"],
                }
            )
            artifacts["client_run_report"] = str(run_report_path)
            artifacts["client_projection"] = str(projection_path)
            print(f"[dashboard] generated client report: {dashboard_path}", flush=True)
        except Exception as e:
            print(
                f"[warn] Failed to generate client delivery artifacts: {e}",
                file=sys.stderr,
                flush=True,
            )

    return artifacts


def _append_funnel_health_snapshot_row(
    outbound: OutboundSection,
    *,
    run_id: str,
    cohort_cm: CohortMetadataModel | None,
    dry_run: bool,
) -> OutboundSection:
    """Append one funnel snapshot to the report and mirror a row into SQLite (insert-only)."""
    rh: dict[str, Any] = {}
    if outbound.pipeline_telemetry and outbound.pipeline_telemetry.run_health:
        rh = outbound.pipeline_telemetry.run_health  # type: ignore[assignment]
    sent = int(rh.get("sent") or 0)
    blocked = int(rh.get("blocked") or 0)
    qualified = int(
        rh.get("qualified")
        or rh.get("ready")
        or outbound.prospect_batch.approved_pass_rows
        or 0
    )
    generated = int(
        rh.get("generated") or outbound.prospect_batch.message_gen_pass or 0
    )

    model_ver = ""
    mp = (
        REPO_ROOT
        / "04-coding"
        / "venture-engine"
        / "config"
        / "reply_intent.model.json"
    )
    if mp.is_file():
        try:
            model_ver = str(
                json.loads(mp.read_text(encoding="utf-8")).get("schema", "")
            )
        except (OSError, json.JSONDecodeError):
            pass

    approval_user = os.environ.get("VENTURE_APPROVAL_USER", "").strip()
    approval_ts = ""
    lock_path = REPO_ROOT / "06-sales" / "batch.lock"
    if lock_path.is_file():
        try:
            from batch_guard import load_lock  # noqa: PLC0415

            lk = load_lock(lock_path, allow_missing=True)
            approval_ts = str(
                lk.get("test_approved_at") or lk.get("execution_confirmed_at") or ""
            )
            approval_user = approval_user or str(
                lk.get("approved_by") or lk.get("approver") or ""
            )
        except Exception:
            pass

    snap = FunnelHealthSnapshotModel(
        prospect_id=f"run:{run_id}",
        campaign_id=(
            cohort_cm.cohort_id
            if cohort_cm
            else os.environ.get("VENTURE_COHORT_ID", "")
        ).strip(),
        send_timestamp=_utc_iso(),
        reply_intent_model_version=model_ver,
        approval_user=approval_user,
        approval_timestamp=approval_ts,
        sent=sent,
        blocked=blocked,
        qualified=qualified,
    )
    new_list = list(outbound.funnel_health_snapshots) + [snap]
    out = outbound.model_copy(update={"funnel_health_snapshots": new_list})

    try:
        mcp = REPO_ROOT / "venture-mcp-server"
        if str(mcp) not in sys.path:
            sys.path.insert(0, str(mcp))
        from runtime_config import resolve_venture_db_path  # noqa: PLC0415
        from job_queue import get_queue  # noqa: PLC0415

        db_path = str(resolve_venture_db_path(resolve_data_base(REPO_ROOT), REPO_ROOT))
        jq = get_queue(db_path=db_path)
        rr_est = float(rh.get("reply_rate_estimate") or rh.get("reply_rate") or 0.0)
        jq.save_funnel_health_snapshot(
            dry_run=dry_run,
            generated=generated,
            qualified=qualified,
            sent=sent,
            blocked=blocked,
            reply_rate_estimate=rr_est,
            extra=snap.model_dump(mode="json"),
        )
    except Exception:
        pass
    return out


def _load_policy_snapshot() -> dict:
    policy_path = REPO_ROOT / "04-coding" / "venture-engine" / "config" / "policy.json"
    if not policy_path.is_file():
        return {}
    try:
        return json.loads(policy_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"_error": str(exc)}


def _run_prospect_builder_subprocess(
    *,
    run_id: str,
    count: int,
    demo: bool,
) -> tuple[int, list[str]]:
    """Run prospect_builder.py (CLI). Returns (returncode, stderr_tail_lines)."""
    env = os.environ.copy()
    env["VENTURE_RUN_ID"] = run_id
    cmd = [sys.executable, str(_SCRIPTS / "prospect_builder.py")]
    if demo:
        cmd.append("--demo")
    cmd.extend(["--count", str(count)])
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return 1, ["prospect_builder_timeout"]
    except Exception as exc:  # noqa: BLE001
        return 1, [f"prospect_builder_error:{exc}"]

    err_lines: list[str] = []
    if proc.stderr:
        err_lines.extend(proc.stderr.strip().splitlines()[-20:])
    return proc.returncode, err_lines


def _run_message_generator_subprocess(
    *,
    run_id: str,
    dry_run: bool,
    auto_approve: bool,
) -> tuple[int, list[str]]:
    """Run message_generator_solo.py. Sets local stub + auto-approve when orchestrator requests."""
    env = os.environ.copy()
    env["VENTURE_RUN_ID"] = run_id
    if dry_run:
        env["VENTURE_LOCAL_GENERATION"] = "1"
        env["VENTURE_AUTO_APPROVE_OUTREACH"] = "1"
    elif auto_approve:
        env["VENTURE_AUTO_APPROVE_OUTREACH"] = "1"
    cmd = [sys.executable, str(_SCRIPTS / "message_generator_solo.py")]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired:
        return 1, ["message_generator_timeout"]
    except Exception as exc:  # noqa: BLE001
        return 1, [f"message_generator_error:{exc}"]

    err_lines: list[str] = []
    if proc.stderr:
        err_lines.extend(proc.stderr.strip().splitlines()[-20:])
    return proc.returncode, err_lines


def _run_cis_eval(
    *,
    shadow_input: Path,
    baseline_path: Path,
    dashboard_out: Path,
) -> CisEvalSection:
    import shadow_drift_tracker as tracker

    dashboard = tracker.generate_experiment_dashboard(
        shadow_log_path=shadow_input,
        baseline_path=baseline_path,
        output_path=dashboard_out,
    )
    decision = str(dashboard.get("final_decision") or "N/A")
    risk_obj = dashboard.get("risk_components") or {}
    risk = risk_obj.get("risk") if isinstance(risk_obj, dict) else None
    try:
        risk_f = float(risk) if risk is not None else None
    except (TypeError, ValueError):
        risk_f = None
    return CisEvalSection(
        enabled=True,
        metrics=dict(dashboard.get("metrics_point_estimates") or {}),
        bootstrap=dict(dashboard.get("metrics_bootstrap") or {}),
        risk=risk_f,
        decision=decision,
        dashboard_path=str(dashboard_out.resolve()),
    )


def _run_outbound_subprocess(
    *,
    dry_run: bool,
) -> tuple[int, list[str], OutboundStatus, dict]:
    telemetry: dict = {}
    tmp_path: Path | None = None
    cache_dir = REPO_ROOT / ".cache"
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(suffix=".json", dir=str(cache_dir))
        os.close(fd)
        tmp_path = Path(tmp_name)
    except OSError:
        tmp_path = None

    env = os.environ.copy()
    env["VENTURE_DEV_MAIN"] = "1"
    if tmp_path is not None:
        env["VENTURE_PIPELINE_TELEMETRY_JSON"] = str(tmp_path)
    cmd = [sys.executable, str(_SCRIPTS / "venture_pipeline.py")]
    if dry_run:
        cmd.append("--dry-run")
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )
    finally:
        if tmp_path is not None:
            try:
                if tmp_path.is_file():
                    telemetry = json.loads(tmp_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                telemetry = {}
            # Always remove temp file after read so .cache/ does not accumulate per run.
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    err_lines: list[str] = []
    if proc.stderr:
        err_lines.extend(proc.stderr.strip().splitlines()[-20:])
    if proc.returncode != 0:
        return proc.returncode, err_lines, "FAILED", telemetry
    return proc.returncode, err_lines, "SUCCESS", telemetry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Venture OS - canonical daily orchestrator (run_report.json + namespaces)",
    )
    parser.add_argument(
        "--client",
        default=os.environ.get("VENTURE_CLIENT_ID", "").strip() or None,
        help="Client id -> clients/<id>/run_report.json",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Client config JSON (clients/{id}/config.json); extracts client_id and injects into runtime",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=None,
        help="Override run_report.json location",
    )
    parser.add_argument(
        "--cis",
        action="store_true",
        help="Run CIS / shadow evaluation into cis_eval section",
    )
    parser.add_argument(
        "--shadow-input",
        type=Path,
        default=REPO_ROOT / "06-sales" / "shadow_decisions.jsonl",
        help="JSONL input for CIS",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=REPO_ROOT / "06-sales" / "baseline_distributions.json",
        help="Baseline JSON for CIS timestamp / frozen_at",
    )
    parser.add_argument(
        "--cis-dashboard-out",
        type=Path,
        default=REPO_ROOT / "06-sales" / "experiment_dashboard.json",
        help="Where shadow_drift_tracker writes experiment_dashboard.json",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Alias for --execute-outbound",
    )
    parser.add_argument(
        "--execute-outbound",
        action="store_true",
        help="Invoke venture_pipeline.py (requires VENTURE_DEV_MAIN in child; gated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to venture_pipeline when --execute-outbound is set",
    )
    parser.add_argument(
        "--generate-prospects",
        action="store_true",
        help="Run prospect_builder.py before message generation / outbound",
    )
    parser.add_argument(
        "--prospects-demo",
        action="store_true",
        help="Pass --demo to prospect_builder (template-only, no API)",
    )
    parser.add_argument(
        "--prospect-count",
        type=int,
        default=50,
        metavar="N",
        help="Prospect row target for prospect_builder when --generate-prospects",
    )
    parser.add_argument(
        "--auto-approve-generated",
        action="store_true",
        help="Set approved=yes on PASS outreach rows (live risk; off unless set)",
    )
    args = parser.parse_args(argv)

    # Load client config if provided (client boundary layer injection)
    client_config_obj = None
    if args.config:
        try:
            # Import client runtime layer (thin boundary abstraction)
            engine_path = _SCRIPTS.parent / "venture-engine"
            if str(engine_path) not in sys.path:
                sys.path.insert(0, str(engine_path))
            from client_runtime import load_client_config  # noqa: PLC0415

            client_config_obj = load_client_config(args.config)
            # Extract client_id from config; override --client if both provided
            args.client = client_config_obj.client_id
            print(f"[client] loaded config from {args.config}", flush=True)
            print(f"[client] client_id={client_config_obj.client_id}", flush=True)
        except Exception as e:
            print(
                f"[error] Failed to load client config: {e}",
                file=sys.stderr,
                flush=True,
            )
            raise SystemExit(5)

    execute_outbound = bool(args.execute_outbound or args.execute)
    orchestrator_started_at = _utc_iso()

    run_id = os.environ.get("VENTURE_RUN_ID", "").strip() or uuid.uuid4().hex[:16]
    os.environ["VENTURE_RUN_ID"] = run_id

    strict_mode = os.environ.get("VENTURE_STRICT_MODE", "0").strip() == "1"
    _ensure_log_directories()
    _ensure_operator_overrides_stub()
    cohort_cm: CohortMetadataModel | None = None

    report_path = resolve_run_report_path(
        REPO_ROOT,
        client_id=args.client,
        explicit=args.report_path,
    )

    outbound = OutboundSection(
        status="NOT_EXECUTED",
        phases=["resolve_paths", "policy_snapshot"],
        policy_snapshot=_load_policy_snapshot(),
    )
    pbatch = ProspectBatchModel()

    if args.generate_prospects:
        outbound.phases.append("prospect_builder_subprocess")
        rc_pb, err_pb = _run_prospect_builder_subprocess(
            run_id=run_id, count=args.prospect_count, demo=args.prospects_demo
        )
        pbatch.builder_ran = True
        pbatch.builder_exit_code = rc_pb
        if err_pb:
            outbound.errors.extend(err_pb)
        if rc_pb != 0:
            pbatch.reasons.append(f"prospect_builder_exit_{rc_pb}")
        elif rc_pb == 0:
            digest_path = (
                resolve_data_base(REPO_ROOT)
                / "07-kpis"
                / "prospect_generation_digest"
                / f"{sanitize_run_id_fs(run_id)}.json"
            )
            if digest_path.is_file():
                try:
                    pbatch = pbatch.model_copy(
                        update={
                            "prospect_generation_digest": json.loads(
                                digest_path.read_text(encoding="utf-8")
                            )
                        }
                    )
                except (json.JSONDecodeError, OSError):
                    pass

    rdy, rev, rej, tot = _prospect_validation_counts()
    pbatch.ready, pbatch.review, pbatch.reject, pbatch.rows_validated = (
        rdy,
        rev,
        rej,
        tot,
    )

    run_venture = execute_outbound
    if execute_outbound:
        segment = os.environ.get("VENTURE_COHORT_SEGMENT", "default").strip()
        cohort_cm = _build_cohort_metadata(run_id, segment)
        _publish_cohort_env(cohort_cm)
        _bootstrap_reply_intent_log(strict_mode=strict_mode)
        if pbatch.builder_ran and pbatch.builder_exit_code not in (0, None):
            pbatch.reasons.append("skip_venture_pipeline_prospect_builder_failed")
            pbatch.outbound_skipped = True
            run_venture = False
        else:
            outbound.phases.append("message_generator_subprocess")
            rc_mg, err_mg = _run_message_generator_subprocess(
                run_id=run_id,
                dry_run=args.dry_run,
                auto_approve=args.auto_approve_generated,
            )
            pbatch.message_gen_ran = True
            pbatch.message_gen_exit_code = rc_mg
            if err_mg:
                outbound.errors.extend(err_mg)
            n_pass, n_fail, n_appr = _outreach_pass_fail_approved()
            pbatch.message_gen_pass = n_pass
            pbatch.message_gen_fail = n_fail
            pbatch.approved_pass_rows = n_appr

            skip = False
            if tot == 0:
                skip = True
                pbatch.reasons.append("no_prospect_rows_in_csv")
            elif rdy == 0:
                skip = True
                pbatch.reasons.append("zero_ready_prospects")
            elif rc_mg != 0:
                skip = True
                pbatch.reasons.append(f"message_generator_exit_{rc_mg}")
            elif n_appr == 0:
                skip = True
                pbatch.reasons.append("no_approved_pass_rows_for_pipeline")

            if skip:
                pbatch.outbound_skipped = True
                run_venture = False
                outbound = outbound.model_copy(
                    update={
                        "status": "BLOCKED",
                        "dry_run": args.dry_run,
                        "money_path_source": "orchestrator",
                        "prospect_batch": pbatch,
                        "money_path": outbound.money_path.model_copy(
                            update={
                                "attempted": 0,
                                "sent": 0,
                                "blocked": 1,
                                "reasons": list(pbatch.reasons),
                            }
                        ),
                    }
                )

    if run_venture and not args.dry_run:
        from bridge_preflight import format_preflight_report, run_preflight_checks

        ok_pf, rsn = run_preflight_checks()
        print(format_preflight_report(ok_pf, rsn), end="", flush=True)
        if not ok_pf:
            raise SystemExit(17)

    if run_venture:
        if not args.dry_run:
            _print_pre_send_checklist()
        outbound.phases.append("venture_pipeline_subprocess")
        rc, tail_err, st, telemetry = _run_outbound_subprocess(dry_run=args.dry_run)
        outbound.subprocess_return_code = rc
        outbound.status = st
        reasons: list[str] = []
        if st == "SUCCESS":
            reasons.append("venture_pipeline_exit_0")
            if args.dry_run:
                reasons.append("dry_run")
            else:
                reasons.append("live_run_subprocess_complete_telemetry_pending")
            outbound.money_path = outbound.money_path.model_copy(
                update={"attempted": 1, "sent": 0, "blocked": 0, "reasons": reasons}
            )
        else:
            reasons.append("venture_pipeline_nonzero_exit")
            outbound.money_path = outbound.money_path.model_copy(
                update={"attempted": 1, "sent": 0, "blocked": 1, "reasons": reasons}
            )
        if tail_err:
            outbound.errors.extend(tail_err)
        outbound = outbound.model_copy(update={"dry_run": args.dry_run})
        if st == "SUCCESS":
            outbound = outbound.model_copy(update={"money_path_source": "orchestrator"})
            if telemetry:
                outbound = _merge_pipeline_telemetry(
                    outbound, telemetry, dry_run=args.dry_run
                )
        else:
            outbound = outbound.model_copy(update={"money_path_source": "orchestrator"})
            if telemetry:
                parsed, validation_reasons = _validate_pipeline_telemetry_soft(telemetry)
                outbound = outbound.model_copy(update={"pipeline_telemetry": parsed})
                if validation_reasons:
                    outbound.errors.extend(validation_reasons)

    # Impossible-state guard: outbound ran but provenance was never set (future refactor safety).
    if execute_outbound and outbound.money_path_source == "none":
        outbound = outbound.model_copy(update={"money_path_source": "orchestrator"})

    outbound = outbound.model_copy(update={"prospect_batch": pbatch})

    if cohort_cm is not None:
        outbound = outbound.model_copy(update={"cohort_metadata": cohort_cm})
    if execute_outbound and "venture_pipeline_subprocess" in outbound.phases:
        outbound = _append_funnel_health_snapshot_row(
            outbound,
            run_id=run_id,
            cohort_cm=cohort_cm,
            dry_run=args.dry_run,
        )
    _maybe_write_dry_run_snapshot(
        dry_run=args.dry_run,
        execute_outbound=execute_outbound,
        outbound_status=outbound.status,
        cohort=cohort_cm,
    )

    cis_section = CisEvalSection(enabled=False)
    if args.cis:
        outbound.phases.append("cis_eval")
        cis_section = _run_cis_eval(
            shadow_input=args.shadow_input.resolve(),
            baseline_path=args.baseline.resolve(),
            dashboard_out=args.cis_dashboard_out.resolve(),
        )

    # Prospect count for system.record_count: shadow lines if cis else 0
    n_records = 0
    if args.cis and args.shadow_input.is_file():
        n_records = sum(
            1
            for line in args.shadow_input.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    elif args.client:
        pc = REPO_ROOT / "clients" / args.client / "prospects.csv"
        if pc.is_file():
            n_records = max(0, sum(1 for _ in pc.open(encoding="utf-8")) - 1)

    outbound = outbound.model_copy(
        update={
            "orchestrator_telemetry": OrchestratorTelemetryModel(
                started_at_utc=orchestrator_started_at,
                finished_at_utc=_utc_iso(),
                execute_outbound=execute_outbound,
                dry_run=bool(args.dry_run),
                venture_pipeline_subprocess_ran=(
                    "venture_pipeline_subprocess" in outbound.phases
                ),
                subprocess_return_code=outbound.subprocess_return_code,
            )
        }
    )

    report = RunReport(
        run_id=run_id,
        timestamp_utc=_utc_iso(),
        outbound=outbound,
        cis_eval=cis_section,
        system=SystemSection(record_count=n_records, random_seed=42),
    )

    runtime_governance = build_runtime_governance(
        report,
        repo_root=REPO_ROOT,
        client_id=args.client,
    )
    runtime_governance_typed = RuntimeGovernanceModel.model_validate(runtime_governance)
    outbound = outbound.model_copy(
        update={"runtime_governance": runtime_governance_typed}
    )
    report = report.model_copy(update={"outbound": outbound})

    write_run_report_atomic(report_path, report)
    _sync_solo_operator_run_report(report_path)
    report_artifacts = _build_client_report_artifacts(report, client_id=args.client)

    # CLI summary: PIPELINE_STATUS | RECORDS | RISK | OUTBOUND_STATE (tabs, no free text in fields)
    pipeline_status = (
        str(cis_section.decision) if cis_section.enabled else str(outbound.status)
    )
    risk_disp = f"{cis_section.risk:.4f}" if cis_section.risk is not None else "N/A"
    outbound_state = str(outbound.status)
    print(
        "\t".join(
            [
                pipeline_status,
                str(n_records),
                risk_disp,
                outbound_state,
            ]
        ),
        flush=True,
    )
    from operator_ux import print_run_daily_operator_footer

    print_run_daily_operator_footer(
        report_path=report_path,
        data_base=resolve_data_base(REPO_ROOT),
        outbound_status=str(outbound.status),
        run_id=run_id,
        ran_generate=args.generate_prospects,
        ran_outbound=execute_outbound,
        pipeline_rc=outbound.subprocess_return_code,
        dry_run=args.dry_run,
    )
    if report_artifacts.get("html"):
        print(f"[report] campaign_html={report_artifacts['html']}", flush=True)
    if report_artifacts.get("pdf"):
        print(f"[report] campaign_pdf={report_artifacts['pdf']}", flush=True)
    return 0 if outbound.status != "FAILED" else 1


if __name__ == "__main__":
    _raw = sys.argv[1:]
    if _raw and _raw[0] == "bridge":
        raise SystemExit(_bridge(_raw[1:]))
    requires_canonical_entry = "--execute" in _raw and "--dry-run" not in _raw
    if requires_canonical_entry and os.getenv("VENTURE_CANONICAL_ENTRY", "0") != "1":
        raise RuntimeError("Execution must originate from canonical orchestrator")
    raise SystemExit(main())
