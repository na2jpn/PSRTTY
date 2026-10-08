"""Hamlib 4.7 C API bridge for selected Yaesu/Kenwood transceivers.

The DLL is an external, replaceable file beside the one-file PSRTTY executable.
Never silently fall back to raw CAT when Hamlib cannot open or verify a rig.
"""
from __future__ import annotations
from .i18n import tr

import ctypes
import ctypes.util
import os
import sys
from pathlib import Path

from .civ import CIVController, CIVStatus
from .paths import app_root

HAMLIB_VERSION = '4.7.2'
HAMLIB_MODELS = {
    'FT-817 / FT-817ND': (1020, 'Yaesu FT-817 / FT-817ND'),
    'FT-818ND': (1041, 'Yaesu FT-818ND'),
    'FT-857 / FT-857D': (1022, 'Yaesu FT-857 / FT-857D'),
    'FT-991 / FT-991A': (1035, 'Yaesu FT-991 / FT-991A'),
    'FTX-1': (1051, 'Yaesu FTX-1 Field / Optima'),
    'FT-710': (1049, 'Yaesu FT-710'),
    'FTDX10': (1042, 'Yaesu FTDX10'),
    'FTDX101D': (1040, 'Yaesu FTDX101D'),
    'FTDX101MP': (1044, 'Yaesu FTDX101MP'),
    'FTDX3000': (1037, 'Yaesu FTDX3000'),
    'TS-590SG': (2037, 'Kenwood TS-590SG'),
    'TS-890S': (2041, 'Kenwood TS-890S'),
    'TS-990S': (2039, 'Kenwood TS-990S'),
}
class LevelValue(ctypes.Union):
    _fields_ = [('i', ctypes.c_int), ('f', ctypes.c_float), ('s', ctypes.c_char_p)]


VFO = 1 << 29  # RIG_VFO_CURR in Hamlib 4.7


def _library_filename() -> str:
    if sys.platform == 'win32':
        return 'libhamlib-4.dll'
    if sys.platform == 'darwin':
        return 'libhamlib-4.dylib'
    return 'libhamlib-4.so'


def library_path():
    return app_root() / 'lib' / 'hamlib' / _library_filename()


def _library_candidates(path=None):
    # Windows keeps its original explicit, bundled DLL loading policy.
    if sys.platform == 'win32':
        yield Path(path or library_path()).resolve()
        return
    if path is not None:
        yield path
        return
    yield library_path()
    for name in ('hamlib-4', 'hamlib'):
        found = ctypes.util.find_library(name)
        if found:
            yield found
    if sys.platform == 'win32':
        yield 'libhamlib-4.dll'
    elif sys.platform == 'darwin':
        yield 'libhamlib-4.dylib'


def load_library(path=None):
    if sys.platform == 'win32' and not Path(path or library_path()).resolve().is_file():
        raise FileNotFoundError(tr('ui.c094d50df160d30e').format(path=Path(path or library_path()).resolve()))
    directory = None
    lib = None
    last_error = None
    for candidate in _library_candidates(path):
        try:
            if isinstance(candidate, (str, os.PathLike)):
                candidate_path = Path(candidate)
                if candidate_path.is_file():
                    load_target = candidate_path.resolve()
                elif candidate_path.parent != Path('.') and candidate_path.suffix:
                    continue
                else:
                    load_target = candidate
            else:
                load_target = candidate
            if isinstance(load_target, Path):
                # Keep the handle: MinGW's dependent DLLs must resolve in the same folder.
                if sys.platform == 'win32' and hasattr(os, 'add_dll_directory'):
                    directory = os.add_dll_directory(str(load_target.parent))
                lib = ctypes.CDLL(str(load_target))
            else:
                lib = ctypes.CDLL(load_target)
            break
        except Exception as exc:
            last_error = exc
            if directory:
                directory.close()
                directory = None
            lib = None
    if lib is None:
        raise FileNotFoundError(tr('ui.088c2a06f0368f17').format(error=last_error))
    signatures={
        'rig_init':(ctypes.c_void_p,[ctypes.c_int]),
        'rig_cleanup':(ctypes.c_int,[ctypes.c_void_p]),
        'rig_open':(ctypes.c_int,[ctypes.c_void_p]),
        'rig_close':(ctypes.c_int,[ctypes.c_void_p]),
        'rig_token_lookup':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_char_p]),
        'rig_set_conf':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_int,ctypes.c_char_p]),
        'rig_get_freq':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_double)]),
        'rig_set_freq':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_uint,ctypes.c_double]),
        'rig_get_ptt':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_int)]),
        'rig_set_ptt':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int]),
        'rig_parse_mode':(ctypes.c_uint64,[ctypes.c_char_p]),
        'rig_get_mode':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_uint,ctypes.POINTER(ctypes.c_uint64),ctypes.POINTER(ctypes.c_long)]),
        'rig_set_mode':(ctypes.c_int,[ctypes.c_void_p,ctypes.c_uint,ctypes.c_uint64,ctypes.c_long]),
    }
    for name,(restype,argtypes) in signatures.items():
        function=getattr(lib,name);function.restype=restype;function.argtypes=argtypes
    for name, (restype, argtypes) in {
        'rig_parse_level': (ctypes.c_uint64, [ctypes.c_char_p]),
        'rig_get_level': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.POINTER(LevelValue)]),
        'rig_set_level': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, LevelValue]),
        'rig_parse_func': (ctypes.c_uint64, [ctypes.c_char_p]),
        'rig_get_func': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.POINTER(ctypes.c_int)]),
        'rig_set_func': (ctypes.c_int, [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint64, ctypes.c_int]),
    }.items():
        function = getattr(lib, name, None)
        if function is not None:
            function.restype, function.argtypes = restype, argtypes
    return lib,directory


class HamlibController(CIVController):
    def __init__(self, model):
        if model not in HAMLIB_MODELS:raise ValueError(tr('ui.0e1b2eddb0064736'))
        super().__init__(0,model=model)
        self.handle=None;self.lib=None;self.dll_directory=None

    def _configure(self, name, value):
        token=self.lib.rig_token_lookup(self.handle,name.encode('ascii'))
        if token<=0 or self.lib.rig_set_conf(self.handle,token,str(value).encode('ascii'))!=0:
            raise RuntimeError(tr('ui.3b63f1d8c2e309c9').format(name=name))

    def connect(self,port='AUTO',baud='AUTO',timeout=8.0):
        with self._lock:
            self.disconnect();self.cancel.clear()
            if str(port).upper()=='AUTO' or str(baud).upper()=='AUTO':
                self.status=CIVStatus(message=tr('ui.8a80fb6572bef5af'))
                return self.status
            try:
                self.lib,self.dll_directory=load_library()
                self.handle=self.lib.rig_init(HAMLIB_MODELS[self.model][0])
                if not self.handle:raise RuntimeError(tr('ui.7e5e540d968b10d3'))
                self._configure('rig_pathname',port)
                self._configure('serial_speed',int(baud))
                if self.model in ('FT-817 / FT-817ND','FT-818ND','FT-857 / FT-857D'):
                    self._configure('stop_bits',2)
                    self._configure('serial_handshake','None')
                if self.lib.rig_open(self.handle)!=0:raise RuntimeError(tr('ui.ed1d3a7ce55eadc9'))
                freq=self.read_frequency()
                if not freq:raise RuntimeError(tr('ui.a634f8b30c1ea3a3'))
                self.status=CIVStatus(True,str(port),int(baud),freq,'Hamlib接続')
            except Exception as exc:
                self.disconnect();self.status.message=str(exc)
            return self.status

    def disconnect(self):
        with self._lock:
            if self.handle and self.lib:
                try:self.lib.rig_close(self.handle)
                except Exception:pass
                try:self.lib.rig_cleanup(self.handle)
                except Exception:pass
            self.handle=None;self.lib=None
            if self.dll_directory:
                self.dll_directory.close();self.dll_directory=None
            self.status=CIVStatus()

    def read_frequency(self):
        with self._lock:
            if not self.handle:return None
            value=ctypes.c_double()
            if self.lib.rig_get_freq(self.handle,VFO,ctypes.byref(value))!=0:return None
            hz=round(value.value)
            if not 30_000<=hz<=500_000_000:return None
            self.status.frequency_hz=hz
            return hz

    def set_frequency(self,hz):
        with self._lock:
            if not self.handle or self.cancel.is_set() or type(hz) is not int or not 30_000<=hz<=500_000_000:return False
            if self.read_transmitting() is not False:return False
            return self.lib.rig_set_freq(self.handle,VFO,float(hz))==0 and self.read_frequency()==hz

    def read_transmitting(self):
        with self._lock:
            if not self.handle:return None
            state=ctypes.c_int()
            if self.lib.rig_get_ptt(self.handle,VFO,ctypes.byref(state))!=0:return None
            return state.value!=0

    def set_ptt(self,on):
        with self._lock:
            if not self.handle or not self.status.connected or (on and self.cancel.is_set()):return False
            if on and self.read_transmitting() is not False:return False
            ok=self.lib.rig_set_ptt(self.handle,VFO,int(bool(on)))==0
            if on and not ok:self.lib.rig_set_ptt(self.handle,VFO,0)
            return ok

    def set_data_mode(self,mode='LSB-D'):
        if mode not in ('LSB-D','USB-D'):return False
        with self._lock:
            if not self.handle or not self.status.connected:return False
            token=(b'LSBD1' if mode=='LSB-D' else b'USBD1') if self.model=='TS-990S' else (b'PKTLSB' if mode=='LSB-D' else b'PKTUSB')
            value=self.lib.rig_parse_mode(token)
            if not value:return False
            if self.lib.rig_set_mode(self.handle,VFO,value,-1)!=0:return False
            actual=ctypes.c_uint64();width=ctypes.c_long()
            return self.lib.rig_get_mode(self.handle,VFO,ctypes.byref(actual),ctypes.byref(width))==0 and actual.value==value

    def operating_modes(self):
        if self.model == 'TS-990S':
            return ('LSB-D1','USB-D1','LSB-D2','USB-D2','LSB-D3','USB-D3','LSB','USB')
        if self.model.startswith('TS-'):
            return ('LSB-DATA','USB-DATA','LSB','USB')
        if self.model == 'FTX-1':
            return ('DATA-L','DATA-U','LSB','USB')
        return ('DATA-LSB','DATA-USB','LSB','USB')

    def _mode_token(self, mode):
        if self.model == 'TS-990S':
            return mode.replace('-', '') if mode in self.operating_modes() else None
        if mode in ('LSB','USB'): return mode
        if mode in ('LSB-DATA','DATA-LSB','DATA-L'): return 'PKTLSB'
        if mode in ('USB-DATA','DATA-USB','DATA-U'): return 'PKTUSB'
        return None

    def read_operating_mode(self):
        with self._lock:
            if not self.handle or not self.status.connected:return None
            actual=ctypes.c_uint64(); width=ctypes.c_long()
            if self.lib.rig_get_mode(self.handle,VFO,ctypes.byref(actual),ctypes.byref(width))!=0:return None
            for mode in self.operating_modes():
                token=self._mode_token(mode)
                if token and self.lib.rig_parse_mode(token.encode('ascii'))==actual.value:return mode
            return None

    def set_operating_mode(self,mode):
        if mode not in self.operating_modes():return False
        with self._lock:
            if not self.handle or not self.status.connected or self.cancel.is_set():return False
            if self.read_transmitting() is not False:return False
            token=self._mode_token(mode)
            value=self.lib.rig_parse_mode(token.encode('ascii'))
            if not value or self.lib.rig_set_mode(self.handle,VFO,value,-1)!=0:return False
            return self.read_operating_mode()==mode

    def _control_ready(self):
        return bool(self.handle and self.lib and self.status.connected and not self.cancel.is_set())

    def read_feature(self, name):
        if self.model in ('FT-817 / FT-817ND','FT-818ND','FT-857 / FT-857D'):return None
        with self._lock:
            if not self._control_ready() or name not in ('NB', 'NR'):
                return None
            try:
                flag = self.lib.rig_parse_func(name.encode('ascii'))
                value = ctypes.c_int()
                if not flag or self.lib.rig_get_func(self.handle, VFO, flag, ctypes.byref(value)) != 0:
                    return None
                return bool(value.value)
            except (AttributeError, OSError):
                return None

    def set_feature(self, name, on):
        with self._lock:
            if self.read_feature(name) is None or self.read_transmitting() is not False:
                return False
            try:
                flag = self.lib.rig_parse_func(name.encode('ascii'))
                return self.lib.rig_set_func(self.handle, VFO, flag, int(bool(on))) == 0 and self.read_feature(name) is bool(on)
            except (AttributeError, OSError):
                return False

    def read_filter(self):
        with self._lock:
            if not self._control_ready() or self.model in ('TS-890S', 'TS-990S', 'FT-817 / FT-817ND', 'FT-818ND', 'FT-857 / FT-857D'):
                return None
            mode = ctypes.c_uint64(); width = ctypes.c_long()
            if self.lib.rig_get_mode(self.handle, VFO, ctypes.byref(mode), ctypes.byref(width)) != 0 or width.value <= 0:
                return None
            data_modes = [self.lib.rig_parse_mode(m) for m in (b'PKTLSB', b'PKTUSB', b'RTTY', b'RTTYR')]
            ssb_modes = [self.lib.rig_parse_mode(m) for m in (b'LSB', b'USB')]
            if self.model == 'TS-590SG':
                if mode.value not in data_modes[:2] + ssb_modes:
                    return None
                # set_mode changes SH but get_mode returns SH-SL inconsistently.
                # Read both supported cutoff levels; preserve SL when setting SH.
                try:
                    high_flag = self.lib.rig_parse_level(b'SLOPE_HIGH')
                    low_flag = self.lib.rig_parse_level(b'SLOPE_LOW')
                    high = LevelValue(); low = LevelValue()
                    if (not high_flag or not low_flag
                        or self.lib.rig_get_level(self.handle, VFO, high_flag, ctypes.byref(high)) != 0
                        or self.lib.rig_get_level(self.handle, VFO, low_flag, ctypes.byref(low)) != 0
                        or high.i < 1000 or low.i < 0 or low.i >= high.i):
                        return None
                except (AttributeError, OSError):
                    return None
                highs = [1000,1200,1400,1600,1800,2000,2200,2400,2600,2800,3000,3400,4000,5000]
                return dict(kind='HAMLIB_SLOPE', mode=mode.value, value=high.i-low.i, low=low.i,
                            options=[(v-low.i, f'{v-low.i} Hz') for v in highs if v > low.i], narrow=None)
            if mode.value in data_modes:
                widths = [50,100,150,200,250,300,350,400,450,500,600,800,1200,1400,1700,2000,2400,3000,3200,3500,4000]
                if self.model in ('FT-991 / FT-991A', 'FTDX3000'):
                    widths = [v for v in widths if v != 600 and v <= (2400 if self.model == 'FTDX3000' else 3000)]
            elif mode.value in ssb_modes:
                if self.model in ('FT-991 / FT-991A', 'FTDX3000'):
                    widths = [200,400,600,850,1100,1350,1500,1650,1800,1950,2100,2200,2300,2400,2500,2600,2700,2800,2900,3000,3200]
                    if self.model == 'FTDX3000': widths += [3400,3600,3800,4000]
                else:
                    widths = [300,400,600,850,1100,1200,1500,1650,1800,1950,2100,2200,2300,2400,2500,2600,2700,2800,2900,3000,3200,3500,4000]
                    if self.model == 'FTX-1':
                        widths = [v for v in widths if v not in (2200,2300)] + [2250,2450]
            else:
                return None
            widths = sorted(set(widths + [width.value]))
            return dict(kind='HAMLIB', mode=mode.value, value=width.value,
                        options=[(v, f'{v} Hz') for v in widths], narrow=None)

    def set_filter(self, value, expected):
        with self._lock:
            if type(value) is not int or not expected or self.read_transmitting() is not False:
                return False
            current = self.read_filter()
            if not current or current['mode'] != expected.get('mode') or value not in dict(current['options']):
                return False
            if current['kind'] == 'HAMLIB_SLOPE':
                if current['low'] != expected.get('low'):
                    return False
                level = self.lib.rig_parse_level(b'SLOPE_HIGH')
                if self.lib.rig_set_level(self.handle, VFO, level, LevelValue(i=value + current['low'])) != 0:
                    return False
            elif self.lib.rig_set_mode(self.handle, VFO, current['mode'], value) != 0:
                return False
            actual = self.read_filter()
            return bool(actual and actual['mode'] == current['mode'] and actual['value'] == value)

    def set_narrow(self,*_):return False

    def read_alc(self):return None
