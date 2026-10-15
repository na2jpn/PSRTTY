"""All QSO logs: verified backup before mutation, rollback on move failure.

Only the ADIF files used by ADIFLog are targeted. Transcripts and previous
backups are retained. A confirmation snapshot prevents deleting new QSOs.
"""
import hashlib
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from .backup import create_log_backup
from .i18n import tr


def snapshot(log_dir):
    result = {}
    for path in sorted(Path(log_dir).glob('*.adi')):
        if path.is_symlink() or not path.is_file():
            raise OSError(tr('v117.delete_changed'))
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def delete_all_qso_logs(log_dir, expected):
    log_dir = Path(log_dir)
    if snapshot(log_dir) != expected:
        raise RuntimeError(tr('v117.delete_changed'))
    if not expected:
        return None
    backup = create_log_backup(log_dir)
    if backup is None:
        raise OSError(tr('v117.backup_failed'))
    with zipfile.ZipFile(backup) as archive:
        if archive.testzip() is not None or any(
            hashlib.sha256(archive.read(name)).hexdigest() != digest
            for name, digest in expected.items()
        ):
            raise OSError(tr('v117.backup_failed'))
    if snapshot(log_dir) != expected:
        raise RuntimeError(tr('v117.delete_changed'))
    staging = Path(tempfile.mkdtemp(prefix='.delete-', dir=log_dir/'backups'))
    moved = []
    try:
        for name in expected:
            os.replace(log_dir/name, staging/name)
            moved.append(name)
    except Exception:
        # Keep staging on rollback failure; it still contains original files.
        for name in reversed(moved):
            os.replace(staging/name, log_dir/name)
        staging.rmdir()
        raise
    # A verified ZIP already protects every byte. Failure to remove the extra
    # staged originals is harmless; don't report the successful deletion failed.
    shutil.rmtree(staging, ignore_errors=True)
    return backup
