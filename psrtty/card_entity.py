"""Display-only, local DXCC information; ambiguous operating sites stay blank."""
import json
from functools import lru_cache
from .jarl_score import locate
from .paths import resource_path
from . import i18n


@lru_cache(maxsize=1)
def names():
    try:
        return json.loads(resource_path('psrtty/data/entity_names.json').read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError):
        return {}


def entity_name(call):
    from .parser import CALL_RE
    if not call or not CALL_RE.fullmatch(call):return ''
    try:row=locate(call)
    except (OSError, UnicodeError, ValueError, KeyError):return ''
    if not row or row['entity'] in ('MM','AM'):return ''
    return names().get(row['entity'],{}).get(i18n.LANGUAGE,row.get('name',''))
