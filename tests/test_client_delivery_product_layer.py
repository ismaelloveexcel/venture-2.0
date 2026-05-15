from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.delivery.artifact_manifest import build_artifact_manifest
from client_runtime.delivery.export_bundle import export_bundle
from client_runtime.delivery.package_builder import build_delivery_package
from client_runtime.onboarding.intake_builder import build_intake_context
from client_runtime.value_layer.value_summary import generate_value_summary


def test_intake_builder_normalizes_execution_intent() -> None:
    raw = {
        "client_id": "acme-demo",
        "campaign_name": "Q2 Outbound",
        "icp_definition": {"industry": "Agencies", "region": "US"},
        "offer_context": {"offer": "Auditbound Pilot", "price": "$2500"},
        "target_source": {"type": "csv", "reference": "clients/acme/prospects.csv"},
        "messaging_constraints": ["no hype", "short"],
        "success_metrics": {"qualified_conversations": 3, "reply_rate": 0.03},
        "reporting_email": "ops@acme.com",
    }

    intake = build_intake_context(raw)

    assert intake["client_id"] == "acme-demo"
    intent = intake["execution_intent"]
    assert intent["targeting_mode"] == "csv"
    assert intent["constraints"] == ["no hype", "short"]
    assert intent["success_definition"]["qualified_conversations"] == 3


def test_value_summary_is_rule_based_and_deterministic() -> None:
    run_report = {
        "run_id": "run-1",
        "outbound": {
            "pipeline_telemetry": {
                "run_health": {
                    "sent": 40,
                    "replies": 3,
                    "qualified": 1,
                    "reply_rate_estimate": 0.075,
                }
            }
        },
    }
    comparison = {
        "trend": "STABLE",
        "notable_changes": ["Qualification rate improved"],
        "breakpoints": [],
    }
    health = {"label": "MEDIUM", "health_score": 68}

    summary = generate_value_summary(run_report, {}, comparison, health)

    assert "summary" in summary
    assert summary["summary"]["performance_overview"].startswith(
        "This run sent 40 messages"
    )
    assert "Qualification rate improved" in summary["summary"]["what_changed"]


def test_delivery_bundle_manifest_export(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-123"
    run_dir.mkdir(parents=True, exist_ok=True)

    bundle = build_delivery_package(
        client_id="acme-demo",
        run_id="run-123",
        run_timestamp="2026-05-14T10:00:00Z",
        engine_version="1.0",
        run_dir=run_dir,
        artifact_paths={
            "dashboard": str(run_dir / "dashboard.html"),
            "health": str(run_dir / "health.json"),
            "comparison": str(run_dir / "comparison.json"),
            "summary": str(run_dir / "value_summary.json"),
        },
        intake_context={"client_id": "acme-demo", "execution_intent": {}},
    )
    manifest = build_artifact_manifest(bundle)

    out_path = run_dir / "delivery_bundle.json"
    export_bundle(manifest, out_path)

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["client_id"] == "acme-demo"
    assert payload["run_id"] == "run-123"
    assert sorted(payload["delivery_items"].keys()) == [
        "comparison",
        "dashboard",
        "health",
        "summary",
    ]
    assert payload["execution_metadata"]["run_timestamp"] == "2026-05-14T10:00:00Z"
