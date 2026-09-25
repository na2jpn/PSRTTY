from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .timebase import JST, in_zone
from .paths import ensure_runtime_dirs


class TranscriptLogger:
    """Pipe Separator形式（PS形式）の生ログ。"""

    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or ensure_runtime_dirs()["logdata"]
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, now: datetime | None = None) -> Path:
        now = in_zone(now, JST) if now is not None else datetime.now(JST)
        return self.log_dir / f"{now:%Y%m%d}_all.txt"

    def ensure_file(self, now: datetime | None = None) -> Path:
        now = in_zone(now, JST) if now is not None else datetime.now(JST)
        path = self.path_for(now)
        if not path.exists():
            path.write_text("", encoding="utf-8-sig")
        return path

    def append(self, content: str, now: datetime | None = None) -> Path:
        now = in_zone(now, JST) if now is not None else datetime.now(JST)
        path = self.path_for(now)
        line = f"{now:%Y-%m-%d %H:%M:%S} | {content.rstrip()}\r\n"
        first = not path.exists()
        with path.open("a", encoding="utf-8-sig" if first else "utf-8", newline="") as f:
            f.write(line)
        return path
