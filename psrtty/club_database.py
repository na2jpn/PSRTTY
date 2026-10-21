"""Replaceable UTF-8 JARL club list, with nonfatal per-row validation."""
from .diagnostics import trace, event
import csv
import re
import json
import os
import shutil
import hashlib
import tempfile
from pathlib import Path
from .paths import app_root, resource_path


def migrate_clubs(root):
    """Copy and verify before unlinking legacy root files; preserve both on conflict."""
    root=Path(root);target=root/'config';target.mkdir(parents=True,exist_ok=True)
    for name in ('club_db.csv','club_db_meta.json'):
        old=root/name;new=target/name
        if not old.is_file() or old.is_symlink():continue
        raw=old.read_bytes()
        if new.exists() and new.read_bytes()!=raw:
            saved=target/(name+'.pre-128-'+hashlib.sha256(new.read_bytes()).hexdigest()[:12])
            if not saved.exists():shutil.copy2(new,saved)
        fd,temp=tempfile.mkstemp(prefix='.club-',dir=target)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            if Path(temp).read_bytes()!=raw:raise OSError('club migration verification')
            os.replace(temp,new)
            if new.read_bytes()!=raw:raise OSError('club migration verification')
            old.unlink()
            event('settings','Migrated '+name+' to config/')
        finally:Path(temp).unlink(missing_ok=True)
    for name in ('club_db.csv','club_db_meta.json'):
        new=target/name
        if not new.exists():
            source=resource_path('psrtty/data/'+name)
            if source.is_file():
                # Exclusive creation never overwrites user data.
                with new.open('xb') as stream:stream.write(source.read_bytes())


@trace('settings')
def load_clubs(root=None):
    root = app_root() if root is None else Path(root)
    try:migrate_clubs(root)
    except OSError as exc:event('settings','Club migration failed; original retained',error=exc)
    external = root / 'config' / 'club_db.csv'
    if (root/'club_db.csv').is_file():external=root/'club_db.csv'
    path = external if external.exists() else resource_path('psrtty/data/club_db.csv')
    rows = []; seen = set(); problem = False
    try:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not {'number', 'name'} <= set(reader.fieldnames or []):
                return [], '', True
            for row in reader:
                number = (row.get('number') or '').strip()
                name = (row.get('name') or '').strip()
                if not re.fullmatch(r'[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*', number) or not name or number in seen:
                    problem = True; continue
                seen.add(number); rows.append((number, name))
    except (OSError, UnicodeError, csv.Error):
        return [], '', True
    try:
        meta_path = external.with_name('club_db_meta.json') if path == external else resource_path('psrtty/data/club_db_meta.json')
        meta = json.loads(meta_path.read_text(encoding='utf-8-sig'))
        # A date from another list must never describe a user-edited CSV.
        import hashlib
        date = meta.get('checked_at', '') if hashlib.sha256(path.read_bytes()).hexdigest() == meta.get('sha256') else ''
    except (OSError, UnicodeError, ValueError, AttributeError):
        date = ''
    return rows, date, problem
