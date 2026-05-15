"""Small I/O helpers (atomic file replace for audit artifacts).

Named ``atomic_io`` (not ``_io``) to avoid shadowing Python's stdlib ``_io`` module.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write UTF-8 ``content`` to ``path`` via temp file + os.replace (same volume)."""
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        suffix=path.suffix or ".tmp",
        prefix=path.name + ".",
        dir=str(path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content.encode(encoding))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
