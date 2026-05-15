"""Sales acceleration layer."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from client_runtime.file_io import atomic_write_json

from .case_study_builder import build_case_study
from .commercial_snapshot import build_commercial_snapshot
from .pilot_summary import build_pilot_summary
from .proposal_builder import build_proposal_seed


def generate_sales_outputs(
    *,
    run_dir: Path,
    client_id: str,
    executive_outputs: dict[str, Any],
    trend_outputs: dict[str, Any],
    operator_outputs: dict[str, Any],
    roi_projection: dict[str, Any],
    value_summary: dict[str, Any],
    intake_context: dict[str, Any],
) -> dict[str, Any]:
    pilot_summary = build_pilot_summary(
        client_id=client_id,
        executive_outputs=executive_outputs,
        trend_outputs=trend_outputs,
        roi_projection=roi_projection,
    )
    commercial_snapshot = build_commercial_snapshot(
        client_id=client_id,
        executive_outputs=executive_outputs,
        trend_outputs=trend_outputs,
        operator_outputs=operator_outputs,
        roi_projection=roi_projection,
    )
    case_study = build_case_study(
        client_id=client_id,
        executive_outputs=executive_outputs,
        trend_outputs=trend_outputs,
        value_summary=value_summary,
        intake_context=intake_context,
        anonymize=True,
    )
    proposal_seed = build_proposal_seed(
        client_id=client_id,
        executive_outputs=executive_outputs,
        trend_outputs=trend_outputs,
        value_summary=value_summary,
    )

    pilot_path = run_dir / "pilot_summary.json"
    commercial_path = run_dir / "commercial_snapshot.json"
    sales_snapshot_path = run_dir / "sales_snapshot.json"
    case_path = run_dir / "case_study.json"
    proposal_path = run_dir / "proposal_seed.json"

    atomic_write_json(pilot_path, pilot_summary)
    atomic_write_json(commercial_path, commercial_snapshot)
    atomic_write_json(sales_snapshot_path, commercial_snapshot)
    atomic_write_json(case_path, case_study)
    atomic_write_json(proposal_path, proposal_seed)

    return {
        "pilot_summary": pilot_summary,
        "commercial_snapshot": commercial_snapshot,
        "sales_snapshot": commercial_snapshot,
        "case_study": case_study,
        "proposal_seed": proposal_seed,
        "paths": {
            "pilot_summary": str(pilot_path),
            "commercial_snapshot": str(commercial_path),
            "sales_snapshot": str(sales_snapshot_path),
            "case_study": str(case_path),
            "proposal_seed": str(proposal_path),
        },
    }
