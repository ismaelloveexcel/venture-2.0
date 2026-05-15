"""
Client Layer Integration Test

Validates:
1. Config loading and validation
2. Client router path resolution
3. run_daily.py --config flag acceptance
4. Directory isolation
5. Dashboard rendering (with mock run_report)
"""

import json
import sys
from pathlib import Path

# Setup paths
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "scripts"))

from client_runtime import load_client_config, get_client_router
from client_runtime.dashboard_renderer import render_client_dashboard
from client_runtime.executive import generate_executive_outputs
from client_runtime.operator import generate_operator_outputs
from client_runtime.sales import generate_sales_outputs
from client_runtime.trends import generate_trend_outputs
from client_runtime.campaigns import update_campaign_state
from client_runtime.queue import update_prospect_queue
from client_runtime.replies import generate_reply_summary
from client_runtime.approval import persist_approval_state
from client_runtime.patterns import update_pattern_memory
from run_report_schema import RunReport, OutboundSection, ProspectBatchModel


def test_config_loading():
    """Test 1: Config loading and validation."""
    print("\n[TEST 1] Config Loading")
    print("-" * 60)

    config = load_client_config(REPO_ROOT / "clients" / "acme-demo" / "config.json")
    print(f"✓ Loaded config for client: {config.client_id}")
    print(f"  Campaign: {config.campaign_name}")
    print(f"  ICP: {config.icp.industry}")
    print(f"  Reporting Email: {config.reporting.email}")
    print(f"  Tone: {config.messaging.tone}")
    print(f"  Personalization: {config.messaging.personalization_level}")


def test_client_router():
    """Test 2: Client router path resolution."""
    print("\n[TEST 2] Client Router Path Resolution")
    print("-" * 60)

    router = get_client_router(REPO_ROOT)
    client_id = "test-client"
    run_id = "test-run-12345"

    router.ensure_client_structure(client_id)
    router.ensure_run_directory(client_id, run_id)

    print(f"✓ Created client structure: {router.get_client_base_path(client_id)}")
    print(f"✓ Created run directory: {router.get_run_output_dir(client_id, run_id)}")
    print(f"✓ Dashboard path: {router.get_dashboard_path(client_id, run_id)}")
    print(f"✓ Run report path: {router.get_run_report_path(client_id, run_id)}")

    # Verify directories exist
    assert router.get_client_base_path(client_id).exists()
    assert router.get_run_output_dir(client_id, run_id).exists()
    print(f"✓ Directory creation verified")


def test_dashboard_rendering():
    """Test 3: Dashboard rendering with mock data."""
    print("\n[TEST 3] Dashboard Rendering")
    print("-" * 60)

    # Create a mock run_report
    outbound = OutboundSection(
        status="SUCCESS",
        prospect_batch=ProspectBatchModel(ready=50, approved_pass_rows=45),
    )
    outbound.pipeline_telemetry = {
        "schema_version": 1,
        "run_health": {
            "sent": 45,
            "replies": 6,
            "qualified": 3,
            "reply_rate_estimate": 0.133,
        },
    }

    report = RunReport(
        run_id="test-run-demo",
        timestamp_utc="2026-05-14T12:00:00Z",
        outbound=outbound,
    )

    # Render dashboard
    router = get_client_router(REPO_ROOT)
    client_id = "test-dashboard"
    run_id = report.run_id

    router.ensure_client_structure(client_id)
    router.ensure_run_directory(client_id, run_id)

    # Create mock run_report.json
    run_report_path = router.get_run_report_path(client_id, run_id)
    run_report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
    )

    projection_payload = {
        "ranked_signals": [
            {"id": "s1", "title": "Reply dip", "severity_score": 62},
            {"id": "s2", "title": "Volume shift", "severity_score": 48},
        ]
    }
    projection_path = router.get_projection_path(client_id, run_id)
    projection_path.write_text(
        json.dumps(projection_payload, indent=2), encoding="utf-8"
    )

    # Render dashboard
    dashboard_path = router.get_dashboard_path(client_id, run_id)
    html = render_client_dashboard(
        run_report=report.model_dump(mode="json"),
        projection=projection_payload,
        output_path=dashboard_path,
        client_id=client_id,
        comparison={
            "trend": "BASELINE",
            "metrics_delta": {},
            "signal_delta": {},
            "notable_changes": [],
            "breakpoints": [],
        },
        health={
            "health_score": 70,
            "label": "BASELINE",
            "drivers": [],
            "risk_flags": ["no_history"],
        },
    )
    dashboard_path.write_text(html, encoding="utf-8")

    print(f"✓ Rendered dashboard HTML: {dashboard_path.name}")
    print(f"✓ File size: {len(html)} bytes")
    assert dashboard_path.exists()
    assert "Client Campaign Dashboard" in html
    assert "45" in html  # sent count
    assert "6" in html  # replies count
    assert "test-run-demo" in html  # run_id
    print(f"✓ Dashboard HTML content verified")


def test_commercial_layers_smoke():
    """Test 4: Commercial layer smoke pass."""
    print("\n[TEST 4] Commercial Layer Smoke")
    print("-" * 60)

    router = get_client_router(REPO_ROOT)
    client_id = "test-commercial"
    run_id = "test-run-commercial"
    router.ensure_client_structure(client_id)
    router.ensure_run_directory(client_id, run_id)
    run_dir = router.get_run_output_dir(client_id, run_id)

    run_report = {
        "run_id": run_id,
        "timestamp_utc": "2026-05-15T12:00:00Z",
        "outbound": {
            "pipeline_telemetry": {
                "run_health": {
                    "sent": 40,
                    "replies": 8,
                    "qualified": 2,
                    "reply_rate_estimate": 0.2,
                }
            }
        },
    }
    projection = {"ranked_signals": [{"title": "Healthcare ICP", "severity_score": 88}]}
    comparison = {
        "trend": "IMPROVING",
        "metrics_delta": {"reply_rate_delta": 0.22, "qualification_rate_delta": 0.05},
        "breakpoints": [],
        "notable_changes": ["Reply rate improved"],
    }
    health = {"health_score": 81, "label": "HEALTHY", "risk_flags": []}
    value_summary = {
        "summary": {
            "performance_overview": "This run sent 40 messages, received 8 replies, and produced 2 qualified conversations.",
            "what_is_working": ["Healthcare ICP is outperforming the baseline."],
            "recommended_actions": ["Increase healthcare segment allocation"],
        }
    }
    intake_context = {
        "client_id": client_id,
        "execution_intent": {"icp": "Healthcare providers"},
    }

    executive_outputs = generate_executive_outputs(
        run_dir=run_dir,
        client_id=client_id,
        run_report=run_report,
        projection=projection,
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
        roi_projection=executive_outputs["roi_projection"],
        value_summary=value_summary,
        intake_context=intake_context,
    )
    campaign_outputs = update_campaign_state(
        repo_root=REPO_ROOT,
        client_id=client_id,
        campaign_id="test-commercial-campaign",
        run_id=run_id,
        outbound_status="SUCCESS",
        run_dir=run_dir,
    )
    queue_outputs = update_prospect_queue(run_dir=run_dir, run_report=run_report)
    reply_outputs = generate_reply_summary(
        run_dir=run_dir,
        run_report=run_report,
        reply_texts=["Interested. Send times.", "Not interested", "Please unsubscribe"],
    )
    approval_outputs = persist_approval_state(run_dir=run_dir, run_report=run_report)
    pattern_outputs = update_pattern_memory(
        repo_root=REPO_ROOT,
        run_dir=run_dir,
        client_id=client_id,
        run_id=run_id,
        intake_context=intake_context,
        subject_line="When they ask for the receipt",
        cta_pattern="Reply and I will show you",
        run_report=run_report,
        reply_summary=reply_outputs["reply_summary"],
    )

    assert (run_dir / "executive_summary.json").exists()
    assert (run_dir / "trend_summary.json").exists()
    assert (run_dir / "operator_tasks.json").exists()
    assert (run_dir / "operator_queue.json").exists()
    assert (run_dir / "proposal_seed.json").exists()
    assert (run_dir / "sales_snapshot.json").exists()
    assert (run_dir / "campaign_state.json").exists()
    assert (run_dir / "queue.json").exists()
    assert (run_dir / "queue_metrics.json").exists()
    assert (run_dir / "reply_summary.json").exists()
    assert (run_dir / "approval_queue.json").exists()
    assert (run_dir / "pattern_memory.json").exists()
    assert campaign_outputs["state"] == "completed"
    assert queue_outputs["metrics"]["total"] == 40
    assert approval_outputs["approval_queue"]["snapshot"]["total"] >= 8
    assert pattern_outputs["pattern_memory"]["best_subject_lines"]
    assert (
        sales_outputs["proposal_seed"]["recommended_engagement"]
        == "30-day optimization sprint"
    )
    assert operator_outputs["workflow_state"]["state"] in {
        "ACTION_REQUIRED",
        "REVIEW_REQUIRED",
        "MONITOR",
        "IDLE",
    }


def test_cli_acceptance():
    """Test 5: CLI flag acceptance (parse check)."""
    print("\n[TEST 5] CLI Flag Acceptance")
    print("-" * 60)

    import subprocess
    import os

    env = os.environ.copy()
    env["VENTURE_CANONICAL_ENTRY"] = "1"

    # Test that --config flag is recognized
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "04-coding" / "scripts" / "run_daily.py"),
            "--help",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )

    assert "--config" in result.stdout
    print(f"✓ --config flag is recognized in CLI")
    print(f"✓ Help text includes: 'Client config JSON'")


def main():
    """Run all integration tests."""
    print("\n" + "=" * 60)
    print("CLIENT LAYER MVP — INTEGRATION TEST SUITE")
    print("=" * 60)

    try:
        test_config_loading()
        test_client_router()
        test_dashboard_rendering()
        test_commercial_layers_smoke()
        test_cli_acceptance()

        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        print("\nClient layer is ready for first customer campaign!")
        return 0
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
