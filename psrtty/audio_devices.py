"""Active WASAPI endpoints, stable Windows IDs, no silent device substitution."""
from __future__ import annotations
from collections import Counter
import ctypes
import hashlib
import sys


def wasapi_endpoint(sd, index):
    """Borrow PortAudio's IMMDevice; GetId memory is owned by COM task allocator.

    Keep this small adapter isolated: sounddevice._libname is private, but loads
    the SAME initialized PortAudio DLL used for playback, not another instance.
    """
    dll = ctypes.CDLL(sd._libname)
    get_device = dll.PaWasapi_GetIMMDevice
    get_device.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
    get_device.restype = ctypes.c_int
    ptr = ctypes.c_void_p()
    if get_device(index, ctypes.byref(ptr)) < 0 or not ptr.value:
        raise RuntimeError('音声デバイスの識別情報を取得できません')
    table = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    get_state = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))(table[6])
    state = ctypes.c_ulong()
    if get_state(ptr, ctypes.byref(state)) < 0:
        raise RuntimeError('音声デバイスの状態を確認できません')
    get_id = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(table[5])
    identifier = ctypes.c_void_p()
    if get_id(ptr, ctypes.byref(identifier)) < 0 or not identifier.value:
        raise RuntimeError('音声デバイスIDを取得できません')
    try:
        key = ctypes.wstring_at(identifier)
    finally:
        ole = ctypes.OleDLL('ole32')
        ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
        ole.CoTaskMemFree.restype = None
        ole.CoTaskMemFree(identifier)
    # IMMDevice pointer is borrowed from PortAudio: do not Release it.
    return key, state.value == 1


def enumerate_devices(sd, kind):
    if sd is None:
        return []
    devices, apis = sd.query_devices(), sd.query_hostapis()
    result, seen = [], set()
    for i, dev in enumerate(devices):
        if not dev.get(f'max_{kind}_channels', 0):
            continue
        name = str(dev['name'])
        api = apis[dev['hostapi']]['name']
        if sys.platform == 'win32':
            if api != 'Windows WASAPI':
                continue
            key, active = wasapi_endpoint(sd, i)
            if not active or (kind, key) in seen:
                continue
            seen.add((kind, key))
            choice = dict(backend='wasapi', id=key, kind=kind, name=name)
        else:
            choice = dict(backend=api, id=name, kind=kind, name=name)
        result.append(dict(index=i, name=name, choice=choice))
    counts = Counter(row['name'] for row in result)
    for row in result:
        row['label'] = row['name']
        if counts[row['name']] > 1:
            tag = hashlib.sha256(row['choice']['id'].encode()).hexdigest()[:6]
            row['label'] += f' [{tag}]'
    return result


def resolve_device(sd, selection, kind):
    if selection in (None, '', 'AUTO'):
        if sys.platform != 'win32':
            return None
        apis = sd.query_hostapis()
        for api in apis:
            if api['name'] == 'Windows WASAPI':
                index = api[f'default_{kind}_device']
                if index >= 0 and wasapi_endpoint(sd, index)[1]:
                    return index
        raise ValueError('有効な既定の音声デバイスがありません')
    if not isinstance(selection, dict):
        # Old numeric IDs cannot identify a device after USB/driver changes.
        if sys.platform == 'win32':
            raise ValueError('旧版の音声設定です。Audio設定でデバイスを選び直してください。')
        return int(selection)
    for row in enumerate_devices(sd, kind):
        item = row['choice']
        if all(item.get(k) == selection.get(k) for k in ('backend', 'id', 'kind')):
            return row['index']
    raise ValueError(f"音声デバイスが未接続または無効です: {selection.get('name', '')}")
