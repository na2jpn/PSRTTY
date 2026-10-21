"""Keep three verified log snapshots and three edit backups per source ADIF.

Only exact application-generated file names are managed. Month-move recovery
directories, unknown files and live ADIF/transcripts are deliberately retained.
"""
from functools import wraps
from pathlib import Path
import re
import threading
import zipfile
from .diagnostics import event

_lock = threading.RLock()


def log_storage_locked(func):
    @wraps(func)
    def run(*args, **kwargs):
        with _lock:
            return func(*args, **kwargs)
    return run


def _linked(path):
    return path.is_symlink() or getattr(path, 'is_junction', lambda: False)()


@log_storage_locked
def prune_log_backups(log_dir):
    log_dir = Path(log_dir)
    folder = log_dir / 'backups'
    if _linked(log_dir) or _linked(folder):
        raise OSError('Linked log backup directory')
    if not folder.exists():
        return 0
    groups = {}
    for path in folder.iterdir():
        name = path.name
        if re.fullmatch(r'PSRTTY_logs_\d{8}_\d{6}_[0-9a-f]{8}\.zip', name):
            key = 'snapshots'
        else:
            match = re.fullmatch(r'(\d{6}\.adi)\.\d{8}_\d{6}_[0-9a-f]{8}\.bak', name)
            if not match:
                continue
            key = match[1]
        if _linked(path) or not path.is_file():
            raise OSError('Invalid log backup: ' + name)
        groups.setdefault(key, []).append(path)
    # Validate all retained generations before deleting anything. A corrupt new
    # snapshot must never cause the older recovery copies to be discarded.
    remove = []
    for key, paths in groups.items():
        paths.sort(key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
        if len(paths) <= 3:
            continue
        for path in paths[:3]:
            if key == 'snapshots':
                with zipfile.ZipFile(path) as archive:
                    if not archive.namelist() or archive.testzip() is not None:
                        raise OSError('Invalid log backup ZIP: ' + path.name)
            else:
                path.read_bytes().decode('utf-8-sig')
        remove.extend(paths[3:])
    for path in remove:
        if _linked(path):
            raise OSError('Linked log backup: ' + path.name)
        path.unlink()
        event('update', 'Removed old log backup ' + path.name)
    return len(remove)


def prune_after_success(log_dir):
    # A cleanup error must not misreport an already committed QSO/backup as
    # failed, which could prompt duplicate writes. Keep recovery data and log it.
    try:
        prune_log_backups(log_dir)
    except Exception as exc:
        event('update', 'Log backup cleanup failed: ' + str(exc))
