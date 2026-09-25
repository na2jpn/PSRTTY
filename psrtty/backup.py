"""Log-only snapshots and an actual startup write probe."""
from datetime import datetime
from pathlib import Path
import os
import tempfile
import uuid
import zipfile


def check_log_writable(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    probe = None
    try:
        with tempfile.NamedTemporaryFile(dir=log_dir, prefix='.psrtty-write-', delete=False) as f:
            probe = Path(f.name)
            f.write(b'PSRTTY write check\n')
            f.flush()
            os.fsync(f.fileno())
    finally:
        if probe is not None:
            probe.unlink()


def create_log_backup(log_dir: Path) -> Path | None:
    # No recursive traversal: never include backups, locks, config or temp files.
    sources = sorted(p for p in log_dir.iterdir()
                     if p.is_file() and (p.suffix.lower() == '.adi' or p.name.endswith('_all.txt')))
    if not sources:
        return None
    directory = log_dir / 'backups'
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f'PSRTTY_logs_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}.zip'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=directory, suffix='.tmp', delete=False) as f:
            temporary = Path(f.name)
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            for source in sources:
                archive.write(source, source.name)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise OSError('バックアップZIPの検証に失敗しました。')
        with temporary.open('rb+') as f:
            os.fsync(f.fileno())
        os.replace(temporary, target)
        return target
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
