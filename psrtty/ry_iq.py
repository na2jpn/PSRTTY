"""Receive-only IQ inputs. ExtIO runs outside the GUI process (32/64-bit)."""
import ctypes as C
from collections import deque
from .diagnostics import event
import os
from pathlib import Path
import struct
import subprocess
import threading
import numpy as np
from .paths import app_root


def pe_bits(path):
    with open(path, 'rb') as f:
        if f.read(2) != b'MZ': raise ValueError('DLL: MZ')
        f.seek(60); offset = struct.unpack('<I', f.read(4))[0]
        f.seek(offset)
        if f.read(4) != b'PE\0\0': raise ValueError('DLL: PE')
        machine = struct.unpack('<H', f.read(2))[0]
    if machine not in (0x14c,0x8664): raise ValueError('DLL: x86/x64')
    return 32 if machine == 0x14c else 64


class ExtIOInput:
    def __init__(self, path, center, on_samples, on_error):
        self.path=Path(path).resolve(); self.center=int(center)
        self.on_samples=on_samples; self.on_error=on_error
        self.process=None; self.stopped=threading.Event(); self.thread=None
        self.stderr_thread=None;self.stderr_tail=deque(maxlen=24)

    def start(self):
        if self.stopped.is_set():return
        event('ry_skimmer','ExtIO DLL validation '+str(self.path))
        bits=pe_bits(self.path)
        event('ry_skimmer','ExtIO DLL architecture '+str(bits)+' bit')
        bridge=app_root()/f'lib/iq/psrtty-extio{bits}.exe'
        if not bridge.is_file(): raise FileNotFoundError('ExtIO bridge missing: '+str(bridge))
        event('ry_skimmer','Bridge process startup '+str(bridge))
        self.process=subprocess.Popen([str(bridge),str(self.path),str(self.center)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),cwd=self.path.parent)
        self.stderr_thread=threading.Thread(target=self._stderr,daemon=True,name='PSRTTY-ExtIO-stderr');self.stderr_thread.start()
        event('ry_skimmer','Bridge process created pid='+str(self.process.pid)+'; waiting for hardware / IQ')
        self.thread=threading.Thread(target=self._read,daemon=True,name='PSRTTY-ExtIO');self.thread.start()
        if self.stopped.is_set():self.stop()

    def _stderr(self):
        try:
            while True:
                raw=self.process.stderr.readline(4096)
                if not raw:break
                line=raw.decode('utf-8','replace').strip()
                if line:
                    self.stderr_tail.append(line);event('ry_skimmer','ExtIO '+line)
        except (OSError,ValueError) as exc:
            if not self.stopped.is_set():event('ry_skimmer','ExtIO stderr failed',error=exc)

    def _read_exact(self, n):
        result=bytearray()
        while len(result)<n:
            part=self.process.stdout.read(n-len(result))
            if not part: raise EOFError('ExtIO')
            result.extend(part)
        return result

    def _read(self):
        expected=None
        try:
            while not self.stopped.is_set():
                magic,count,rate,center,position=struct.unpack('<4sIIdq',self._read_exact(28))
                if magic!=b'RYIQ' or not 0<count<=1_048_576 or not 6000<=rate<=8_000_000 or not np.isfinite(center):
                    raise ValueError('ExtIO packet')
                data=np.frombuffer(self._read_exact(count*8),dtype='<f4').reshape(-1,2)
                if expected is None:event('ry_skimmer','ExtIO IQ receive started rate='+str(rate)+' center='+str(center))
                self.on_samples(data[:,0]+1j*data[:,1],rate,center,expected is not None and expected!=position)
                expected=position+count
        except Exception as exc:
            if not self.stopped.is_set():
                try:self.process.wait(timeout=.3)
                except subprocess.TimeoutExpired:pass
                if self.stderr_thread:self.stderr_thread.join(timeout=.3)
                detail='\n'.join(self.stderr_tail)
                # Also support direct reader use without a launched stderr thread.
                if self.stderr_thread is None and self.process.poll() is not None:
                    detail=self.process.stderr.read(8192).decode('utf-8','replace')
                message=(detail+'\n' if detail else '')+str(exc)+' (exit='+str(self.process.poll())+')'
                event('ry_skimmer','ExtIO IQ input failed',error=exc)
                self.on_error(message)

    def stop(self):
        self.stopped.set()
        if self.process and self.process.poll() is None:
            try: self.process.stdin.close();self.process.wait(timeout=.3)
            except (OSError,subprocess.TimeoutExpired):
                self.process.kill()
                try:self.process.wait(timeout=.3)
                except subprocess.TimeoutExpired:pass
        event('ry_skimmer','ExtIO stopped')


class RTLInput:
    def __init__(self, path, serial, center, on_samples, on_error, direct=0):
        self.path=path;self.serial=serial;self.center=int(center)
        self.on_samples=on_samples;self.on_error=on_error;self.direct=direct
        self.handle=C.c_void_p();self.lib=None;self.thread=None;self.stopped=threading.Event()
        self.lifecycle=threading.Lock()
        self.rate=240000

    def _library(self):
        path=str(Path(self.path).resolve())
        if os.name=='nt': self._dll_dir=os.add_dll_directory(str(Path(path).parent))
        event('ry_skimmer','RTL-SDR DLL load '+path)
        lib=C.CDLL(path)
        signatures={'rtlsdr_get_device_count':(C.c_uint,[]),
            'rtlsdr_get_device_usb_strings':(C.c_int,[C.c_uint,C.c_char_p,C.c_char_p,C.c_char_p]),
            'rtlsdr_open':(C.c_int,[C.POINTER(C.c_void_p),C.c_uint]),
            'rtlsdr_close':(C.c_int,[C.c_void_p]),
            'rtlsdr_set_sample_rate':(C.c_int,[C.c_void_p,C.c_uint]),
            'rtlsdr_set_center_freq':(C.c_int,[C.c_void_p,C.c_uint]),
            'rtlsdr_set_tuner_gain_mode':(C.c_int,[C.c_void_p,C.c_int]),
            'rtlsdr_set_direct_sampling':(C.c_int,[C.c_void_p,C.c_int]),
            'rtlsdr_reset_buffer':(C.c_int,[C.c_void_p]),
            'rtlsdr_read_async':(C.c_int,[C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint]),
            'rtlsdr_cancel_async':(C.c_int,[C.c_void_p])}
        for name,(ret,args) in signatures.items():
            fn=getattr(lib,name);fn.restype=ret;fn.argtypes=args
        return lib

    def devices(self):
        if self.lib is None:self.lib=self._library()
        rows=[]
        for index in range(min(256,self.lib.rtlsdr_get_device_count())):
            m,p,s=(C.create_string_buffer(256) for _ in range(3))
            if self.lib.rtlsdr_get_device_usb_strings(index,m,p,s)==0:
                rows.append((index,s.value.decode('ascii','replace'),p.value.decode('ascii','replace')))
        return rows

    def start(self):
        if self.stopped.is_set():return
        event('ry_skimmer','RTL-SDR device open serial='+str(self.serial))
        rows=self.devices();found=[r for r in rows if r[1]==self.serial]
        if len(found)!=1:raise ValueError('RTL-SDR: serial / device')
        if self.lib.rtlsdr_open(C.byref(self.handle),found[0][0])<0:raise OSError('rtlsdr_open')
        try:
            # V4 requires tuner mode (0); V3 HF direct-sampling is opt-in.
            if self.lib.rtlsdr_set_direct_sampling(self.handle,self.direct)<0:raise OSError('direct sampling')
            for name,value in [('rtlsdr_set_sample_rate',self.rate),('rtlsdr_set_center_freq',self.center),('rtlsdr_set_tuner_gain_mode',0)]:
                if getattr(self.lib,name)(self.handle,value)<0:raise OSError(name)
            if self.lib.rtlsdr_reset_buffer(self.handle)<0:raise OSError('reset_buffer')
        except Exception:
            self.lib.rtlsdr_close(self.handle);self.handle=C.c_void_p();raise
        event('ry_skimmer','RTL-SDR IQ input configured rate='+str(self.rate)+' center='+str(self.center))
        self.callback=C.CFUNCTYPE(None,C.POINTER(C.c_ubyte),C.c_uint,C.c_void_p)(self._callback)
        self.thread=threading.Thread(target=self._run,daemon=True,name='PSRTTY-RTL');self.thread.start()
        if self.stopped.is_set():self.stop()

    def _callback(self,buf,n,context):
        if self.stopped.is_set():
            self.lib.rtlsdr_cancel_async(self.handle);return
        a=np.ctypeslib.as_array(buf,shape=(n,)).astype(np.float32)
        if n%2:return
        a=(a.reshape(-1,2)-127.5)/128.
        self.on_samples(a[:,0]+1j*a[:,1],self.rate,self.center)

    def _run(self):
        try:
            if self.stopped.is_set():return
            result=self.lib.rtlsdr_read_async(self.handle,self.callback,None,0,16384)
            if not self.stopped.is_set():self.on_error('RTL-SDR read_async: '+str(result))
        except Exception as exc:
            event('ry_skimmer','RTL-SDR read failed',error=exc)
            if not self.stopped.is_set():self.on_error(str(exc))
        finally:
            with self.lifecycle:
                self.lib.rtlsdr_close(self.handle);self.handle=C.c_void_p()

    def stop(self):
        self.stopped.set()
        with self.lifecycle:
            if self.lib and self.thread and self.handle:self.lib.rtlsdr_cancel_async(self.handle)
        if self.thread:self.thread.join(timeout=.3)
