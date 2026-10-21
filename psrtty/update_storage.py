"""Bounded updater storage. Called only after the installed GUI has started.

Live config and log files are preserved. Log backup retention is handled separately.
"""
from __future__ import annotations
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import time
import zipfile
import zlib
from .diagnostics import event


class StorageBusy(OSError):
    pass


@contextmanager
def storage_lock(root, timeout=0):
    """Cross-process lease, held by the updater through restart confirmation."""
    path=Path(root)/'var'/'update-storage.lock'
    if _linked(path) or _linked(path.parent):raise OSError('Linked storage lock')
    path.parent.mkdir(parents=True,exist_ok=True)
    stream=path.open('a+b');acquired=False;end=time.monotonic()+timeout
    try:
        if path.stat().st_size==0:stream.write(b'0');stream.flush()
        while True:
            stream.seek(0)
            try:
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
                acquired=True;break
            except OSError as exc:
                if time.monotonic()>=end:raise StorageBusy('Updater/storage cleanup is running') from exc
                time.sleep(.1)
        yield
    finally:
        if acquired:
            stream.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(),fcntl.LOCK_UN)
        stream.close()


def _process_stamp(pid):
    try:
        if os.name!='nt':
            raw=Path('/proc')/str(int(pid))/'stat'
            return raw.read_text(encoding='utf-8').rsplit(')',1)[1].split()[19]
        import ctypes
        from ctypes import wintypes
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        api.OpenProcess.restype=wintypes.HANDLE
        api.CloseHandle.argtypes=[wintypes.HANDLE]
        api.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
        handle=api.OpenProcess(0x1000,False,int(pid))
        if not handle:return None
        try:
            fields=[wintypes.FILETIME() for _ in range(4)]
            if not api.GetProcessTimes(handle,*[ctypes.byref(f) for f in fields]):return None
            return str((fields[0].dwHighDateTime<<32)|fields[0].dwLowDateTime)
        finally:api.CloseHandle(handle)
    except (OSError,ValueError,TypeError,IndexError):return None


def owner_marker():
    pid=os.getpid()
    if os.name!='nt':
        # /proc may expose a different PID namespace (containers/test hosts).
        pid=int(Path('/proc/self/stat').read_text(encoding='utf-8').split(' ',1)[0])
    stamp=_process_stamp(pid)
    if stamp is None:raise OSError('Cannot identify update preparation process')
    return {'pid':pid,'start':stamp}


def _prepared_owner_busy(stage):
    try:owner=json.loads((stage/'request.json').read_text(encoding='utf-8')).get('owner',{})
    except (OSError,ValueError):return False
    return bool(owner.get('start') and _process_stamp(owner.get('pid'))==owner['start'])


def _linked(path):
    return path.is_symlink() or (hasattr(path,'is_junction') and path.is_junction())


def _files(directory, kind):
    result=[]
    for base,dirs,names in os.walk(directory,followlinks=False):
        base=Path(base)
        for name in (*dirs,*names):
            if _linked(base/name):raise OSError('Linked updater data: '+str(base/name))
        relative=base.relative_to(directory)
        # Never nest earlier backups/caches into a retained backup again.
        if kind=='backup' and relative.as_posix() in ('logdata','var'):
            dirs[:]=[n for n in dirs if n not in ('backups','updates')]
        if kind=='update' and relative==Path('.'):
            dirs[:]=[n for n in dirs if n!='payload']
        for name in names:
            if kind=='update' and relative==Path('.') and name=='psrtty-updater.exe':continue
            p=base/name
            if not p.is_file():raise OSError('Unexpected updater item: '+str(p))
            result.append(p)
    return sorted(result)


def _legacy_helper_busy(stage):
    # Older helpers lack our lease. Query the process image path, rather than
    # relying on file deletion/rename flags of a mapped Windows executable.
    exe=stage/'psrtty-updater.exe'
    if sys.platform!='win32' or not exe.is_file():return False
    import ctypes
    from ctypes import wintypes as W
    class Entry(ctypes.Structure):
        _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),
                  ('heap',ctypes.c_size_t),('module',W.DWORD),('threads',W.DWORD),
                  ('parent',W.DWORD),('priority',W.LONG),('flags',W.DWORD),('name',W.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=[W.DWORD,W.DWORD];api.CreateToolhelp32Snapshot.restype=W.HANDLE
    for name in ('Process32FirstW','Process32NextW'):
        fn=getattr(api,name);fn.argtypes=[W.HANDLE,ctypes.POINTER(Entry)];fn.restype=W.BOOL
    api.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];api.OpenProcess.restype=W.HANDLE
    api.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
    api.QueryFullProcessImageNameW.restype=W.BOOL
    api.CloseHandle.argtypes=[W.HANDLE]
    snapshot=api.CreateToolhelp32Snapshot(2,0)
    if snapshot==ctypes.c_void_p(-1).value:raise StorageBusy('Cannot inspect running update helpers')
    try:
        entry=Entry();entry.size=ctypes.sizeof(entry)
        more=api.Process32FirstW(snapshot,ctypes.byref(entry))
        while more:
            if entry.name.lower()==exe.name.lower():
                handle=api.OpenProcess(0x1000,False,entry.pid)
                if not handle:raise StorageBusy('Cannot inspect update helper process')
                try:
                    path=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(path))
                    if not api.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(length)):
                        raise StorageBusy('Cannot inspect update helper image')
                    if os.path.normcase(str(Path(path.value).resolve()))==os.path.normcase(str(exe.resolve())):return True
                finally:api.CloseHandle(handle)
            more=api.Process32NextW(snapshot,ctypes.byref(entry))
        return False
    finally:api.CloseHandle(snapshot)


def _owned(path,kind):
    if path.is_dir():
        pattern=r'[0-9a-f]{32}' if kind=='update' else r'(?:\d{8}_\d{6}_[0-9a-f]{8}|legacy_manifest_[0-9a-f]{32})'
    else:pattern=kind+r'_(?:[0-9a-f]{32}|\d{8}_\d{6}_[0-9a-f]{8}|legacy_manifest_[0-9a-f]{32})\.zip'
    return bool(re.fullmatch(pattern,path.name))


def _stamp(path):
    if path.is_dir() and (path/'request.json').is_file():return (path/'request.json').stat().st_mtime
    return path.stat().st_mtime


def _archive(directory,kind):
    target=directory.with_name(kind+'_'+directory.name+'.zip')
    members=_files(directory,kind)
    if target.exists():
        with zipfile.ZipFile(target) as existing:
            if existing.testzip() is not None:raise OSError('Existing retention archive is corrupt')
            for p in members:
                name=p.relative_to(directory).as_posix();crc=0
                with p.open('rb') as stream:
                    for block in iter(lambda:stream.read(1024*1024),b''):crc=zlib.crc32(block,crc)
                info=existing.getinfo(name)
                if info.file_size!=p.stat().st_size or info.CRC!=crc:raise OSError('Retention archive conflict')
        shutil.rmtree(directory)
        return target
    if not members:raise OSError('Empty updater generation: '+str(directory))
    # If migration stopped after publishing the archive, rebuild/verify before
    # deleting the old folder. Both entries count as one logical generation.
    fd,name=tempfile.mkstemp(prefix='.update-storage-',suffix='.tmp',dir=directory.parent.parent)
    os.close(fd);temporary=Path(name);stamp=_stamp(directory)
    try:
        snapshots={p.relative_to(directory).as_posix():(p.stat().st_size,p.stat().st_mtime_ns) for p in members}
        with zipfile.ZipFile(temporary,'w',zipfile.ZIP_DEFLATED,compresslevel=6,allowZip64=True,strict_timestamps=False) as archive:
            for p in members:
                archive.write(p,p.relative_to(directory).as_posix(),compress_type=zipfile.ZIP_STORED if p.suffix.lower()=='.zip' else zipfile.ZIP_DEFLATED)
        with zipfile.ZipFile(temporary) as archive:
            if archive.testzip() is not None:raise OSError('Updater archive CRC failure')
            if {i.filename:i.file_size for i in archive.infolist()}!={n:v[0] for n,v in snapshots.items()}:raise OSError('Updater archive member mismatch')
        for p in members:
            st=p.stat()
            if (st.st_size,st.st_mtime_ns)!=snapshots[p.relative_to(directory).as_posix()]:raise StorageBusy('Updater data changed during archiving')
        with temporary.open('rb+') as stream:os.fsync(stream.fileno())
        os.utime(temporary,(stamp,stamp));os.replace(temporary,target)
        shutil.rmtree(directory)
        event('update','Archived updater generation '+directory.name+' -> '+target.name)
        return target
    finally:temporary.unlink(missing_ok=True)


def _retain(folder,kind,limit):
    if not folder.exists():return {'kept':0,'removed':0}
    if _linked(folder):raise OSError('Linked updater storage: '+str(folder))
    entries=list(folder.iterdir())
    if any(_linked(p) or not (p.is_dir() or p.is_file()) or not _owned(p,kind) for p in entries):
        raise OSError('Unexpected or linked item in '+str(folder)+'; retained for inspection')
    # Preflight every directory before deleting any generation.
    for p in entries:
        if p.is_dir():
            if kind=='update' and (_prepared_owner_busy(p) or _legacy_helper_busy(p)):raise StorageBusy('Prepared/running update is protected')
            _files(p,kind)
    # A folder and its published archive can coexist after an interrupted delete.
    generations={}
    for p in entries:
        key=p.name if p.is_dir() else p.name[len(kind)+1:-4]
        generations.setdefault(key,[]).append(p)
    ordered=sorted(generations.values(),key=lambda group:(max(_stamp(p) for p in group),group[0].name),reverse=True)
    keep=ordered[:limit];removed=0
    # Compact retained generations first. If packing fails, preserve originals
    # and all older generations. No cleanup runs while the updater holds a lease.
    for group in keep:
        directory=next((p for p in group if p.is_dir()),None)
        if directory is not None:_archive(directory,kind)
        else:
            with zipfile.ZipFile(group[0]) as archive:
                if not archive.namelist() or archive.testzip() is not None:raise OSError('Retained archive is invalid')
    for group in ordered[limit:]:
        for p in group:
            if p.is_dir():shutil.rmtree(p)
            else:p.unlink()
            event('update','Removed old updater storage '+str(p));removed+=1
    return {'kept':len(keep),'removed':removed}


def maintain_storage(root):
    """Call after successful normal GUI startup; never on failed update paths."""
    root=Path(root)
    for p in (root/'var',root/'var/updates',root/'var/backups'):
        if _linked(p):raise OSError('Linked updater storage: '+str(p))
    # Do not mistake development folders or arbitrary user directories for installs.
    manifest=root/'var/psrtty-release.json'
    installed=json.loads(manifest.read_text(encoding='utf-8'))
    if installed.get('product')!='PSRTTY' or not (root/'psrtty.exe').is_file():raise OSError('Not an installed PSRTTY folder')
    with storage_lock(root):
        # An interrupted process may leave its unpublished archive in var/.
        for p in (root/'var').glob('.update-storage-*.tmp'):
            if re.fullmatch(r'\.update-storage-[a-z0-9_]{8}\.tmp',p.name) and p.is_file() and not _linked(p):
                p.unlink();event('update','Removed abandoned retention temporary '+p.name)
        result={'updates':_retain(root/'var/updates','update',1),
                'backups':_retain(root/'var/backups','backup',2)}
    from .log_retention import prune_log_backups
    prune_log_backups(root/'logdata')
    event('update','Updater storage retention completed '+str(result))
    return result
