from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "04-coding" / "venture-engine"))

from client_runtime.sales import generate_sales_outputs


def test_generate_sales_outputs(tmp_path: Path) -> None:
    run_dir = tmp_path / "clients" / "acme-demo" / "runs" / "run-1"
    run_dir.mkdir(parents=True)

    executive_outputs = {
        "executive_summary": {
            "campaign_status": "IMPROVING",
            "business_impact": "Reply efficiency improved 22%",
            "primary_risk": "Qualified lead velocity below target",
            "top_opportunity": "Healthcare ICP outperforming baseline",
            "recommended_action": "Increase healthcare segment allocation",
            "confidence": 82,
        },
        "roi_projection": {
            "projected_replies_30d": 48,
            "projected_qualified_30d": 9,
            "trajectory": "POSITIVE",
            "confidence": "MEDIUM",
        },
    }
    trend_outputs = {
        "trend_projection": {"projected_state": "IMPROVING", "risk_probability": "LOW"},
        "trend_summary": {"trend_projection": {"projected_state": "IMPROVING"}},
    }
    operator_outputs = {
        "workflow_state": {"next_action": "Review healthcare messaging"}
    }
    value_summary = {
        "summary": {
            "performance_overview": "This run sent 40 messages, received 8 replies, and produced 2 qualified conversations."
        }
    }
    intake_context = {
        "client_id": "acme-demo",
        "execution_intent": {
            "icp": "Healthcare providers",
            "offer": "Optimization sprint",
        },
    }

    outputs = generate_sales_outputs(
        run_dir=run_dir,
        client_id="acme-demo",
        executive_outputs=executive_outputs,
        trend_outputs=trend_outputs,
        operator_outputs=operator_outputs,
        roi_projection=executive_outputs["roi_projection"],
        value_summary=value_summary,
        intake_context=intake_context,
    )

    pilot_path = run_dir / "pilot_summary.json"
    commercial_path = run_dir / "commercial_snapshot.json"
    sales_snapshot_path = run_dir / "sales_snapshot.json"
    case_path = run_dir / "case_study.json"
    proposal_path = run_dir / "proposal_seed.json"

    assert pilot_path.is_file()
    assert commercial_path.is_file()
    assert sales_snapshot_path.is_file()
    assert case_path.is_file()
    assert proposal_path.is_file()

    case_study = json.loads(case_path.read_text(encoding="utf-8"))
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    snapshot = json.loads(commercial_path.read_text(encoding="utf-8"))

    assert proposal["client"] == "acme-demo"
    assert proposal["recommended_engagement"] == "30-day optimization sprint"
    assert case_study["anonymized"] is True
    assert case_study["industry"] in {"Healthcare", "Confidential"}
    assert snapshot["priority_action"] == "Review healthcare messaging"
    assert outputs["paths"]["sales_snapshot"].endswith("sales_snapshot.json")
    assert outputs["pilot_summary"]["trajectory"] == "IMPROVING"
