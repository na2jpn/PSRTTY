"""One-way Turbo HAMLOG link, public WM_COPYDATA API (5.27c+).

Target: HAMLOG 5.48. No database DLL, keystroke automation or reverse log sync.
All native calls run on the same worker thread as the temporary reply window.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import sys
import threading
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .hamlog_csv import hamlog_row
from .i18n import tr

TARGET_VERSION = '5.48'
API_VERSION = '5.27c'
WM_COPYDATA = 0x004A
THW_ENTER = 0x10000
THW_SAVEBOX_OFF = 0x80000
THW_APPLIHWND = 0x100000
THW_SHUUSEI_WIN = 0x200000


def wire_command(command, reply=False):
    # Ask HAMLOG to confirm if it would target an existing-record edit window.
    # Normal input-window transfer does not prompt. A pending prompt times out
    # and aborts the remaining transfer, including automatic Save.
    return command | (THW_APPLIHWND if reply else THW_SHUUSEI_WIN)


class LinkError(RuntimeError):
    pass


def input_fields(text):
    lines = text.replace('\r\n', '\n').split('\n')
    if lines and lines[0] == '':
        lines.pop(0)  # API 115 has an initial empty line.
    if len(lines) < 14:
        raise LinkError(tr('ui.9b060b211e88fc24'))
    return tuple(value.strip() for value in lines[:14])


class Win32Transport:
    """A bounded, synchronous native request with a reentrant reply WNDPROC."""
    def __enter__(self):
        if sys.platform != 'win32':
            raise LinkError(tr('ui.c4452bd5d152c4d4'))
        from ctypes import wintypes as w
        self.u = ctypes.WinDLL('user32', use_last_error=True)
        self.k = ctypes.WinDLL('kernel32', use_last_error=True)
        self.hwnd = None
        self.atom = None
        self.reply = None
        self.awaiting = False
        self.WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        class WNDCLASS(ctypes.Structure):
            _fields_ = [('style', w.UINT), ('lpfnWndProc', self.WNDPROC),
                        ('cbClsExtra', ctypes.c_int), ('cbWndExtra', ctypes.c_int),
                        ('hInstance', w.HINSTANCE), ('hIcon', w.HICON), ('hCursor', w.HANDLE),
                        ('hbrBackground', w.HBRUSH), ('lpszMenuName', w.LPCWSTR), ('lpszClassName', w.LPCWSTR)]
        class COPYDATA(ctypes.Structure):
            _fields_ = [('dwData', ctypes.c_size_t), ('cbData', w.DWORD), ('lpData', ctypes.c_void_p)]
        self.COPYDATA = COPYDATA
        signatures = {
            'FindWindowW': (w.HWND, [w.LPCWSTR, w.LPCWSTR]),
            'FindWindowExW': (w.HWND, [w.HWND, w.HWND, w.LPCWSTR, w.LPCWSTR]),
            'RegisterClassW': (w.ATOM, [ctypes.POINTER(WNDCLASS)]),
            'CreateWindowExW': (w.HWND, [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, ctypes.c_void_p]),
            'DefWindowProcW': (ctypes.c_ssize_t, [w.HWND, w.UINT, w.WPARAM, w.LPARAM]),
            'SendMessageTimeoutW': (ctypes.c_ssize_t, [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, ctypes.POINTER(ctypes.c_size_t)]),
            'DestroyWindow': (w.BOOL, [w.HWND]),
            'UnregisterClassW': (w.BOOL, [w.LPCWSTR, w.HINSTANCE]),
            'GetWindowTextW': (ctypes.c_int, [w.HWND, w.LPWSTR, ctypes.c_int]),
            'IsWindow': (w.BOOL, [w.HWND]),
        }
        for name, (restype, argtypes) in signatures.items():
            fn = getattr(self.u, name); fn.restype = restype; fn.argtypes = argtypes
        self.k.GetModuleHandleW.restype = w.HMODULE
        self.k.GetModuleHandleW.argtypes = [w.LPCWSTR]
        self.target = self.u.FindWindowW('TThwin', None)
        if not self.target:
            raise LinkError(tr('ui.4f0d7bced676d235'))
        if self.u.FindWindowExW(None, self.target, 'TThwin', None):
            raise LinkError(tr('ui.1cf4657143247f68'))
        title = ctypes.create_unicode_buffer(512)
        self.u.GetWindowTextW(self.target, title, len(title))
        self.title = title.value or 'Turbo HAMLOG'
        def window_proc(hwnd, message, sender, data):
            if message == WM_COPYDATA and self.awaiting and sender == self.target and data:
                try:
                    cds = ctypes.cast(data, ctypes.POINTER(COPYDATA)).contents
                    if cds.dwData not in (0, 1) or cds.cbData > 65536:
                        return 0
                    if cds.cbData and cds.lpData:
                        raw = ctypes.string_at(cds.lpData, cds.cbData).split(b'\0', 1)[0]
                        self.reply = raw.decode('cp932', errors='strict')
                    elif cds.dwData == 0:
                        self.reply = ''
                    else:
                        return 0
                    return 1
                except (ValueError, UnicodeError):
                    return 0
            return self.u.DefWindowProcW(hwnd, message, sender, data)
        self.callback = self.WNDPROC(window_proc)
        self.class_name = 'PSRTTY_HAMLOG_' + uuid.uuid4().hex
        self.instance = self.k.GetModuleHandleW(None)
        wc = WNDCLASS(lpfnWndProc=self.callback, hInstance=self.instance, lpszClassName=self.class_name)
        self.atom = self.u.RegisterClassW(ctypes.byref(wc))
        if not self.atom:
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = self.u.CreateWindowExW(0, self.class_name, '', 0, 0, 0, 0, 0, None, None, self.instance, None)
        if not self.hwnd:
            error = ctypes.WinError(ctypes.get_last_error()); self.__exit__(None, None, None); raise error
        return self

    def request(self, command, text=None, reply=False):
        if not self.u.IsWindow(self.target):
            raise LinkError(tr('ui.b22d344db84c32c7'))
        payload = None if text is None else ctypes.create_string_buffer(text.encode('cp932') + b'\0')
        cds = self.COPYDATA(wire_command(command, reply),
                            0 if payload is None else len(payload.raw) - 1,
                            None if payload is None else ctypes.cast(payload, ctypes.c_void_p))
        result = ctypes.c_size_t()
        self.reply = None; self.awaiting = reply
        try:
            # Do not set SMTO_BLOCK: HAMLOG must synchronously send our reply.
            ok = self.u.SendMessageTimeoutW(self.target, WM_COPYDATA, self.hwnd,
                    ctypes.addressof(cds), 0x2 | 0x20, 2000, ctypes.byref(result))
        finally:
            self.awaiting = False
        if not ok or not result.value or (reply and self.reply is None):
            raise LinkError(tr('ui.58c6548694ca7ec6'))
        return self.reply if reply else result.value

    def __exit__(self, *_):
        if self.hwnd:
            self.u.DestroyWindow(self.hwnd); self.hwnd = None
        if self.atom:
            self.u.UnregisterClassW(self.class_name, self.instance); self.atom = None


class HamlogLink:
    def __init__(self, journal: Path, transport_factory=Win32Transport):
        self.journal = Path(journal)
        self.transport_factory = transport_factory
        self.lock = threading.Lock()
        self.lookup_owner = None

    def _journal(self, key, state):
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        with self.journal.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'key': key, 'state': state}) + '\n')
            stream.flush(); os.fsync(stream.fileno())

    def check(self):
        with self.lock, self.transport_factory() as api:
            input_fields(api.request(115, reply=True))
            return api.title

    def lookup(self, call):
        call = call.strip().upper()
        if not re.fullmatch(r'[A-Z0-9/]{3,24}', call):
            raise LinkError(tr('ui.c90813e1e925bfc5'))
        with self.lock, self.transport_factory() as api:
            before = input_fields(api.request(115, reply=True))
            if before[0]:
                raise LinkError(tr('ui.71ef020415e1cb94'))
            # Enter invokes HAMLOG's own call lookup; no direct database access.
            api.request(1 | THW_ENTER, call)
            after = input_fields(api.request(115, reply=True))
            if after[0].upper() != call:
                raise LinkError(tr('ui.a0ff1dcc26cac607'))
            self.lookup_owner = (api.target, after)
            return {'call': call, 'name': after[10], 'qth': after[11], 'title': api.title}

    def transfer(self, qso, auto_save=False):
        try:
            row = hamlog_row(qso)
        except ValueError as exc:
            raise LinkError(tr('ui.c5ba582ace4bbb6c')) from exc
        key = hashlib.sha256(json.dumps([row, qso.when_utc.isoformat()], ensure_ascii=False).encode('utf-8')).hexdigest()
        with self.lock:
            if self.journal.exists():
                for line in self.journal.read_text(encoding='utf-8').splitlines():
                    try:
                        if json.loads(line)['key'] == key:
                            raise LinkError(tr('ui.23219d1da1afd4ba'))
                    except (json.JSONDecodeError, KeyError) as exc:
                        raise LinkError(tr('ui.9faa18d06e02f378')) from exc
            with self.transport_factory() as api:
                before = input_fields(api.request(115, reply=True))
                owned = self.lookup_owner == (api.target, before) and before[0].upper() == row[0]
                if before[0] and not owned:
                    raise LinkError(tr('ui.71ef020415e1cb94'))
                self._journal(key, 'attempted')  # durable before the first mutation
                self.lookup_owner = None
                # Preserve HAMLOG's own QSL/code/name/QTH defaults and lookup result.
                for index in (1,2,3,4,5,6,7,13,14):
                    api.request(index, row[index - 1])
                after = input_fields(api.request(115, reply=True))
                try:
                    date_ok = any(after[1] == datetime.strptime(row[1], '%y/%m/%d').strftime(fmt) for fmt in ('%y/%m/%d', '%Y/%m/%d'))
                    time_ok = after[2].upper() == row[2]
                    freq_ok = Decimal(after[5]) == Decimal(row[5])
                except (ValueError, InvalidOperation):
                    date_ok = time_ok = freq_ok = False
                if (not (date_ok and time_ok and freq_ok) or after[0].upper() != row[0] or after[3:5] != tuple(row[3:5])
                        or after[6].upper() != 'RTTY' or after[12:14] != tuple(row[12:14])):
                    raise LinkError(tr('ui.fcde825f19a91068'))
                if auto_save:
                    api.request(18 | THW_SAVEBOX_OFF)
                    if api.request(101, reply=True).strip():
                        raise LinkError(tr('ui.b1769edc3bac554f'))
                self._journal(key, 'save_requested' if auto_save else 'input_transferred')
                return tr('ui.b05c93fe60062bb6') if auto_save else tr('ui.445bcd18f8c28b41')
