"""Bounded diagnostics only; QSO, transcripts and backups are never managed here."""
from __future__ import annotations
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
import sys
import threading
import traceback
from .paths import app_root

CATEGORIES = ('app','radio','audio','tx','decode','ry_skimmer','ry_radar',
              'integration','printer','settings','update')
MAX_BYTES = 500_000
MAX_TOTAL_BYTES = 12_000_000
_lock = threading.RLock()
_directory = None

def configure(directory=None):
    global _directory
    with _lock:
        _directory = Path(directory) if directory is not None else app_root()/'var'/'diagnostics'
        try:
            _directory.mkdir(parents=True,exist_ok=True)
            _prune(_directory)
        except OSError:
            pass

def _prune(directory):
    # Only our exact names. Never walk backups, transcripts, ADIF or user files.
    files=[]
    for category in CATEGORIES:
        for suffix in ('','.1','.2'):
            path=directory/(category+'.log'+suffix)
            if path.is_file() and not path.is_symlink(): files.append(path)
    total=sum(p.stat().st_size for p in files)
    for path in sorted((p for p in files if p.name.endswith(('.1','.2'))),key=lambda p:p.stat().st_mtime):
        if total<=MAX_TOTAL_BYTES: break
        # Retain at least one existing file, including a lone archived generation.
        base=path.name.split('.log')[0]+'.log'
        if sum((directory/(base+s)).is_file() for s in ('','.1','.2'))<=1: continue
        size=path.stat().st_size;path.unlink();total-=size

def event(category, message, *, error=None):
    if category not in CATEGORIES: raise ValueError(category)
    try:
        text=str(message)
        if error is not None:
            if isinstance(error,BaseException):
                text+='\n'+''.join(traceback.format_exception(type(error),error,error.__traceback__))
            else: text+=': '+str(error)
        # Bound native stderr and exception strings. Never store sample arrays.
        text=text[:16000].replace('\x00','?')
        record=(datetime.now(timezone.utc).isoformat(timespec='seconds')+' '+
                ('ERROR ' if error is not None else 'INFO ')+text+'\n').encode('utf-8')
        with _lock:
            directory=_directory or app_root()/'var'/'diagnostics'
            directory.mkdir(parents=True,exist_ok=True)
            path=directory/(category+'.log')
            if path.exists() and path.stat().st_size+len(record)>MAX_BYTES:
                second=directory/(category+'.log.2');first=directory/(category+'.log.1')
                second.unlink(missing_ok=True)
                if first.exists(): first.replace(second)
                path.replace(first)
            with path.open('ab') as stream: stream.write(record)
            _prune(directory)
    except (OSError,ValueError):
        pass  # diagnostics must never interrupt radio/PTT or prevent startup

def trace(category):
    """Trace selected low-rate operations, deliberately omitting arguments/text."""
    def decorate(function):
        @wraps(function)
        def wrapped(*args,**kwargs):
            name=function.__module__+'.'+function.__qualname__
            event(category,name+' begin')
            try: result=function(*args,**kwargs)
            except Exception as exc:
                event(category,name+' failed',error=exc);raise
            detail=''
            if isinstance(result,bool): detail=' result='+str(result)
            elif isinstance(result,tuple) and result and isinstance(result[0],bool): detail=' result='+str(result[0])+(' '+str(result[1]) if len(result)>1 else '')
            elif hasattr(result,'connected'): detail=' connected='+str(result.connected)+' '+str(getattr(result,'message',''))
            event(category,name+' end'+detail)
            return result
        return wrapped
    return decorate

def install_exception_hooks():
    old=sys.excepthook
    def report(kind,value,tb):
        event('app','unhandled GUI/main exception',error=value)
        old(kind,value,tb)
    sys.excepthook=report
    previous=threading.excepthook
    def thread_report(args):
        event('app','unhandled thread '+str(args.thread.name),error=args.exc_value)
        previous(args)
    threading.excepthook=thread_report
