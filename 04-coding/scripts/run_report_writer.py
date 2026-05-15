"""Atomic full-json writer for run_report.json (vFINAL.1)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from run_report_schema import RunReport


def resolve_run_report_path(
    repo_root: Path,
    *,
    client_id: str | None,
    explicit: Path | None = None,
) -> Path:
    if explicit is not None:
        return explicit.resolve()
    cid = client_id or os.environ.get("VENTURE_CLIENT_ID", "").strip()
    if cid:
        p = repo_root / "clients" / cid / "run_report.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p.resolve()
    return (repo_root / "run_report.json").resolve()


def write_run_report_atomic(path: Path, report: RunReport) -> None:
    """Write complete JSON once; replace atomically (same volume)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json", exclude_none=False)
    text = json.dumps(payload, indent=2, sort_keys=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=".json",
        prefix="run_report_",
        dir=str(path.parent),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def parse_run_report(path: Path) -> RunReport:
    return RunReport.model_validate_json(path.read_text(encoding="utf-8"))
