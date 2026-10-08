"""External UI catalogues with an embedded, complete English fallback.

Only display text is translated. Configured callsigns, macros, radio IDs,
received/transmitted text and exported records must never pass through here.
"""
from __future__ import annotations
import json
import logging
import re
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter
from .english_fallback import STRINGS as ENGLISH
from .language_index import ALIASES, GUIDE_KEYS
from .paths import app_root, resource_path

LANGUAGES = ('ja', 'en', 'ru', 'zh', 'ko')
LANGUAGE = 'ja'  # effective display language; requested setting is never rewritten
REQUESTED_LANGUAGE = 'ja'
_strings = dict(ENGLISH)
_issues = []
_seen = set()
_QT_TRANSLATOR = None

class _Markup(HTMLParser):
    def __init__(self):
        super().__init__(); self.stack=[]
    def handle_starttag(self, tag, attrs):
        if tag not in ('br','hr','img','meta','link','input','wbr'):self.stack.append(tag)
    def handle_startendtag(self, tag, attrs):
        if tag not in ('br','hr','img','meta','link','input','wbr'): raise ValueError('invalid self-closing HTML')
    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop()!=tag:raise ValueError('unbalanced HTML')

def _fields(value):
    return sorted((name, spec, conv) for _,name,spec,conv in Formatter().parse(value) if name is not None)

def validate_entry(key, value):
    if not isinstance(value,str):raise ValueError('value must be a string')
    ref=ENGLISH[key]
    if ref.strip() and not value.strip():raise ValueError('empty translation')
    # Guide HTML contains CSS braces only outside the text catalogue.
    if _fields(value)!=_fields(ref):raise ValueError('format placeholders differ')
    if re.search(r'</?(?:h[1-6]|p|li|ol|ul|table|tr|td|th|b|span|code)(?:\s|>)',ref):
        parser=_Markup();parser.feed(value);parser.close()
        if parser.stack:raise ValueError('unclosed HTML')
    return value

def _pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate JSON key: '+str(key))
        result[key]=value
    return result

def load_catalog(language, directory=None):
    """Returns valid entries and diagnostics; never raises for an external file."""
    path=Path(directory or app_root()/'language')/(language+'.json')
    problems=[];valid={}
    try:
        if path.stat().st_size>4*1024*1024:raise ValueError('catalogue exceeds 4 MiB')
        data=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=_pairs)
        if (not isinstance(data,dict) or data.get('format')!=1 or data.get('language')!=language
                or not isinstance(data.get('strings'),dict)):
            raise ValueError('unsupported catalogue structure / language')
    except (OSError,ValueError,UnicodeError) as exc:
        return {},[('file',str(path),str(exc))]
    for key,reference in ENGLISH.items():
        if key not in data['strings']:
            problems.append(('entry',key,'missing'));continue
        try:valid[key]=validate_entry(key,data['strings'][key])
        except ValueError as exc:problems.append(('entry',key,str(exc)))
    return valid,problems

def _record(problem):
    if problem in _seen:return
    _seen.add(problem);_issues.append(problem)
    logging.getLogger('psrtty.language').warning('%s: %s: %s',*problem)
    try:
        path=app_root()/'var'/'language.log';path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists() and path.stat().st_size>1024*1024:
            path.replace(path.with_suffix('.log.1'))
        with path.open('a',encoding='utf-8') as f:f.write(' | '.join(problem)+'\n')
    except OSError:pass  # reporting failure must not prevent startup

def configure(language, directory=None):
    global LANGUAGE, REQUESTED_LANGUAGE, _strings, _issues, _seen
    REQUESTED_LANGUAGE=language
    _issues=[];_seen=set();_strings=dict(ENGLISH)
    english,problems=load_catalog('en',directory)
    _strings.update(english)
    for problem in problems:_record(problem)
    if language not in LANGUAGES:
        LANGUAGE='en';_record(('file',str(language),'unsupported selected language'));return
    selected,problems=load_catalog(language,directory) if language!='en' else (english,[])
    LANGUAGE='en' if any(p[0]=='file' for p in problems) else language
    _strings.update(selected)
    for problem in problems:_record(problem)

def startup_notice():
    if any(p[0]=='file' for p in _issues):return tr('language.load_notice')
    return ''

def diagnostics():return tuple(_issues)

def language_text(key, language):
    # Compatibility for existing document exports / tests, outside active UI.
    data,_=load_catalog(language)
    return data.get(key,ENGLISH.get(key,key))

TEXT={original:ENGLISH[key] for original,key in ALIASES.items()}
TEXT.update(ENGLISH)

def tr(text):
    key=ALIASES.get(text,text)
    if key in _strings:return _strings[key]
    if key in ENGLISH:return ENGLISH[key]
    # Backend diagnostic messages can contain already-formatted placeholders.
    for original,k in ALIASES.items():
        if '{' not in original or original.startswith('<'):continue
        try:
            parts=list(Formatter().parse(original));pattern='';names=[]
            for literal,name,spec,conv in parts:
                pattern+=re.escape(literal)
                if name is not None:pattern+='(.*?)';names.append(name)
            match=re.fullmatch(pattern,text,re.DOTALL)
            if match:
                values=dict(zip(names,match.groups()))
                target=_strings.get(k,ENGLISH[k])
                return ''.join(literal+(values.get(name,'') if name is not None else '')
                               for literal,name,spec,conv in Formatter().parse(target))
        except (ValueError,TypeError):continue
    return text  # technical identifiers and arbitrary external error text

def install_qt_translation():
    global _QT_TRANSLATOR
    from PySide6.QtCore import QTranslator,QLibraryInfo
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance()
    if app is None:return
    if _QT_TRANSLATOR is not None:app.removeTranslator(_QT_TRANSLATOR)
    _QT_TRANSLATOR=QTranslator(app)
    code={'ja':'ja','en':'en','ru':'ru','zh':'zh_CN','ko':'ko'}[LANGUAGE]
    if LANGUAGE=='en':return  # Qt's original strings are English
    loaded=_QT_TRANSLATOR.load('qtbase_'+code,QLibraryInfo.path(QLibraryInfo.TranslationsPath))
    if not loaded:loaded=_QT_TRANSLATOR.load(str(resource_path('assets/qt-translations/qtbase_'+code+'.qm')))
    if loaded:app.installTranslator(_QT_TRANSLATOR)
    else:_record(('qt',code,'Qt catalogue unavailable; standard buttons use English'))

configure('ja')
