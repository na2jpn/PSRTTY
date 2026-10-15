"""Global macro colour presets, independent of macros and radio profiles."""
import re
from copy import deepcopy
STANDARD=[{'text':'#2F241B','background':'#F3B35C'} for _ in range(9)]
def color(value):
    return isinstance(value,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',value) is not None
def normalize(value):
    value=value if isinstance(value,dict) else {}
    try:selected=int(value.get('selected',0))
    except (ValueError,TypeError):selected=0
    presets=[];source=value.get('presets',[])
    if not isinstance(source,list):source=[]
    for i in range(3):
        item=source[i] if i<len(source) and isinstance(source[i],dict) else {}
        rows=deepcopy(STANDARD);given=item.get('colors',[])
        if isinstance(given,list):
            for j,row in enumerate(given[:9]):
                if isinstance(row,dict):
                    for key in rows[j]:
                        if color(row.get(key)):rows[j][key]=row[key].upper()
        presets.append({'name':str(item.get('name',''))[:30],'colors':rows})
    return {'selected':selected if selected in range(4) else 0,'presets':presets}
def apply(buttons,settings):
    data=normalize(settings);index=data['selected']
    for b,row in zip(buttons,STANDARD if index==0 else data['presets'][index-1]['colors']):
        if index==0:b.setStyleSheet('');continue
        b.setStyleSheet('QPushButton { background: '+row['background']+'; color: '+row['text']+'; }'
            'QPushButton:hover { border: 2px solid #9c4d08; }'
            'QPushButton:pressed { border: 3px solid #9c4d08; }'
            'QPushButton:disabled { background: #e5ded5; color: #9a9084; border-color: #c8bfb3; }')
