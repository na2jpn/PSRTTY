"""Replaceable UTF-8 JARL club list, with nonfatal per-row validation."""
import csv
import re
import json
from .paths import app_root, resource_path


def load_clubs(root=None):
    root = app_root() if root is None else root
    external = root / 'club_db.csv'
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
        meta_path = root / 'club_db_meta.json' if path == external else resource_path('psrtty/data/club_db_meta.json')
        meta = json.loads(meta_path.read_text(encoding='utf-8-sig'))
        # A date from another list must never describe a user-edited CSV.
        import hashlib
        date = meta.get('checked_at', '') if hashlib.sha256(path.read_bytes()).hexdigest() == meta.get('sha256') else ''
    except (OSError, UnicodeError, ValueError, AttributeError):
        date = ''
    return rows, date, problem
