"""Write delivery bundle manifest to filesystem."""

from __future__ import annotations

from pathlib import Path

from client_runtime.file_io import atomic_write_json


def export_bundle(bundle_payload: dict[str, Any], output_path: Path) -> Path:
    return atomic_write_json(output_path, bundle_payload)
