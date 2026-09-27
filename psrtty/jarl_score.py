"""JARL WW RTTY preliminary score. Entity hints are confirmed in the UI."""
from __future__ import annotations

import json
import re
from functools import lru_cache

from .paths import resource_path

CONTINENTS = ('AF', 'AN', 'AS', 'EU', 'NA', 'OC', 'SA')
MAINLAND = {'JA': 'JA', 'K': 'W', 'VE': 'VE', 'VK': 'VK'}


@lru_cache(maxsize=1)
def database():
    return json.loads(resource_path('psrtty/data/contest_prefixes.json').read_text(encoding='utf-8'))


def locate(call, overrides=None):
    call = call.strip().upper()
    if overrides and call in overrides:
        row = dict(overrides[call])
        if (row.get('continent') not in CONTINENTS or
            not re.fullmatch(r'[A-Za-z0-9/]{1,12}', row.get('entity', '')) or
            not re.fullmatch(r'[A-Za-z0-9/]{1,12}', row.get('multiplier', ''))):
            raise ValueError(f'{call}：手動指定のエンティティ・大陸・マルチを確認してください。')
        return row
    if not re.fullmatch(r'[A-Z0-9]+(?:/[A-Z0-9]+)*',call): return None
    if call.endswith('/MM'): return {'entity':'MM','continent':'','multiplier':''}
    if call.endswith('/AM') or call.startswith('JD1') or '/JD1' in call: return None
    db=database()
    if call in db['exact']: row=dict(db['exact'][call])
    else:
        base=call
        if '/' in call:
            left,right=call.split('/',1)
            if '/' in right or right not in ('P','QRP') and not right.isdigit():return None
            base=left
        row=next((dict(db['prefixes'][base[:n]]) for n in range(len(base),0,-1)
                  if base[:n] in db['prefixes']),None)
    if row and row['entity'] in MAINLAND:
        if '/' in call:
            part=call.rsplit('/',1)[-1]
            area=part if part.isdigit() else '0'
        else:
            before=re.search(r'(\d+)(?=[A-Z]+$)',call)
            area=before[1][-1] if before else ''
        if not area: return None
        row['multiplier']=MAINLAND[row['entity']]+area[-1]
    elif row:
        row['multiplier']=row['entity']
    return row


def calculate(entries, own_continent, overrides=None):
    """Return points, multipliers, total and per-QSO evidence, without modifying logs."""
    if own_continent not in CONTINENTS:raise ValueError('自局の運用大陸を指定してください。')
    points=0;mults=set();duplicates=set();details=[];unknown=[]
    for q, extra in entries:
        call=q.call.strip().upper();band=q.band.upper()
        if extra.get('xqso'):
            details.append((call,band,0,'X-QSO'));continue
        key=(call,band)
        if key in duplicates:
            details.append((call,band,0,'同一バンドの重複'));continue
        duplicates.add(key)
        place=locate(call,overrides)
        if not place:
            unknown.append(call)
            details.append((call,band,None,'運用地を指定してください'));continue
        value=2 if place['entity']=='MM' or place['continent']==own_continent else 3
        points+=value
        if place.get('multiplier'):mults.add((band,place['multiplier']))
        details.append((call,band,value,place.get('multiplier','マルチなし')))
    return dict(points=points,multipliers=len(mults),total=points*len(mults),
                details=details,unknown=sorted(set(unknown)))
