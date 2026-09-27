"""Hamlib 4.7 C API bridge for selected Yaesu/Kenwood transceivers.

The DLL is an external, replaceable file beside the one-file PSRTTY executable.
Never silently fall back to raw CAT when Hamlib cannot open or verify a rig.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path

from .civ import CIVController, CIVStatus
from .paths import app_root

HAMLIB_VERSION = '4.7.2'
HAMLIB_MODELS = {
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
VFO = 1 << 29  # RIG_VFO_CURR in Hamlib 4.7


def library_path():
    return app_root() / 'lib' / 'hamlib' / 'libhamlib-4.dll'


def load_library(path=None):
    path=Path(path or library_path()).resolve()
    if not path.is_file():
        raise FileNotFoundError(f'Hamlib DLLがありません: {path}')
    # Keep the handle: MinGW's dependent DLLs must resolve in the same folder.
    directory=os.add_dll_directory(str(path.parent)) if hasattr(os,'add_dll_directory') else None
    try:
        lib=ctypes.CDLL(str(path))
    except Exception:
        if directory:directory.close()
        raise
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
    return lib,directory


class HamlibController(CIVController):
    def __init__(self, model):
        if model not in HAMLIB_MODELS:raise ValueError('Hamlibの選択機種ではありません。')
        super().__init__(0,model=model)
        self.handle=None;self.lib=None;self.dll_directory=None

    def _configure(self, name, value):
        token=self.lib.rig_token_lookup(self.handle,name.encode('ascii'))
        if token<=0 or self.lib.rig_set_conf(self.handle,token,str(value).encode('ascii'))!=0:
            raise RuntimeError(f'Hamlib設定 {name} を受け付けませんでした。')

    def connect(self,port='AUTO',baud='AUTO',timeout=8.0):
        with self._lock:
            self.disconnect();self.cancel.clear()
            if str(port).upper()=='AUTO' or str(baud).upper()=='AUTO':
                self.status=CIVStatus(message='HamlibではCOMポートとCAT速度を明示して接続テストしてください。')
                return self.status
            try:
                self.lib,self.dll_directory=load_library()
                self.handle=self.lib.rig_init(HAMLIB_MODELS[self.model][0])
                if not self.handle:raise RuntimeError('Hamlibが機種を認識できませんでした。')
                self._configure('rig_pathname',port)
                self._configure('serial_speed',int(baud))
                if self.lib.rig_open(self.handle)!=0:raise RuntimeError('Hamlibが無線機に接続できませんでした。')
                freq=self.read_frequency()
                if not freq:raise RuntimeError('Hamlibから周波数を取得できませんでした。')
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

    def set_narrow(self,*_):return False

    def read_alc(self):return None
