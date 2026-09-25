from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """Return the writable application root.

    Frozen builds keep config/logdata/var beside psrtty.exe. Source runs keep
    them beside psrtty.py.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", app_root()))
    return base / relative


def ensure_runtime_dirs() -> dict[str, Path]:
    root = app_root()
    paths = {
        "root": root,
        "config": root / "config",
        "logdata": root / "logdata",
        "var": root / "var",
    }
    for key in ("config", "logdata", "var"):
        paths[key].mkdir(parents=True, exist_ok=True)
    return paths
