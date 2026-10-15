"""ITA2 FSK on serial control lines; never opens an audio output."""
from copy import deepcopy
import math
import threading
import time
import sys
from .i18n import tr
from .rtty_codec import LTRS_ENCODE, FIGS_ENCODE

from .fsk_models import ICOM_FSK, KENWOOD_FSK, YAESU_FSK, USB_KEYING, modes_for, warning_key
SUPPORTED = tuple(sorted(ICOM_FSK | KENWOOD_FSK | YAESU_FSK))
DEFAULT_FSK = {'port': 'RADIO', 'line': 'DTR', 'invert': False, 'mode': 'RTTY'}

def enabled(config):
    return config.get('radio', {}).get('tx_method', 'afsk') == 'fsk'

def validate(radio, options, external=None):
    if radio.get('model') not in SUPPORTED:
        raise ValueError(tr(warning_key(radio.get('model'))))
    if options.get('line') not in ('DTR','RTS') or options.get('mode') not in modes_for(radio.get('model')):
        raise ValueError(tr('fsk.invalid'))
    port=str(options.get('port','')).strip()
    if not port or port.upper() in ('AUTO','UNSET'):
        raise ValueError(tr('fsk.port_note'))
    shared=port=='RADIO' or port.casefold()==str(radio.get('com_port','')).casefold()
    if shared and radio['model'] not in USB_KEYING:
        raise ValueError(tr('fsk3.separate'))
    if shared and radio.get('ptt')==options['line']:
        raise ValueError(tr('fsk.conflict'))
    ext=external or {}
    # A dedicated keying interface can carry FSK + PTT on different signal lines.
    if ext.get('enabled') and str(ext.get('com_port','')).casefold()==port.casefold():
        if shared or ext.get('role')!='ptt' or ext.get('line') not in ('DTR','RTS') or ext.get('line')==options['line']:
            raise ValueError(tr('fsk.conflict'))
    return shared

class SerialKey:
    def __init__(self, controller, radio, options, external=None):
        self.shared=validate(radio,options,external)
        self.controller=controller
        self.options=deepcopy(options)
        self.external=dict(external or {})
        self.ser=None
    def open(self):
        if self.shared:
            self.ser=getattr(self.controller,'ser',None)
            if self.ser is None or not self.controller.status.connected:
                raise ValueError(tr('fsk.connected'))
        else:
            import serial
            # Set inactive levels before opening: do not key RTS/PTT on open.
            self.ser=serial.Serial(port=None,baudrate=9600,timeout=.05,write_timeout=.3,rtscts=False,dsrdtr=False)
            self.ser.rts=False;self.ser.dtr=False
            if self.external.get('enabled') and str(self.external.get('com_port','')).casefold()==str(self.options['port']).casefold():
                setattr(self.ser,self.external['line'].lower(),bool(self.external.get('reversed',False)))
            self.ser.port=self.options['port']
            self.ser.open()
        self.mark(True)
    def mark(self, mark):
        # Default: idle Mark=inactive, Space=active. Polarity is selectable.
        setattr(self.ser,self.options['line'].lower(),bool(not mark)^bool(self.options.get('invert')))
    def close(self):
        if self.ser is None:return
        try:self.mark(True)
        finally:
            if not self.shared:self.ser.close()
            self.ser=None

class CodeEncoder:
    def __init__(self):self.figures=False
    def char(self,ch):
        ch=ch.upper();codes=[]
        if ch=='\n':return [8,2]
        if ch in LTRS_ENCODE:
            if self.figures and ch not in ' \r':codes.append(31);self.figures=False
            codes.append(LTRS_ENCODE[ch])
        elif ch in FIGS_ENCODE:
            if not self.figures:codes.append(27);self.figures=True
            codes.append(FIGS_ENCODE[ch])
        else:codes=[4]
        return codes

def frame(code):
    return [(False,1.)]+[(bool(code>>i&1),1.) for i in range(5)]+[(True,1.5)]

class BitClock:
    def __init__(self,key,cancel,baud):
        self.key=key;self.cancel=cancel;self.bit=1./baud;self.deadline=time.perf_counter()
    def emit(self,mark,units):
        if self.cancel.is_set():return False
        if time.perf_counter()-self.deadline > self.bit:
            raise RuntimeError(tr('fsk.timing'))
        self.key.mark(mark);self.deadline+=self.bit*units
        while not self.cancel.is_set():
            remaining=self.deadline-time.perf_counter()
            if remaining<=0:return True
            if remaining>.001:self.cancel.wait(max(0,remaining-.0005))
        return False
    def code(self,code):
        return all(self.emit(mark,units) for mark,units in frame(code))

def start_fsk(engine,controller,radio,options,advanced,ptt_on,ptt_off,finished,
              text=None,session=None,progress=None,external=None,sequencer=None):
    if engine._tx_active:return False,tr('ui.1270a65b09bcaf38')
    try:
        key=SerialKey(controller,radio,options,external)
        share_ptt=(external or {}).get('enabled') and str((external or {}).get('com_port','')).casefold()==str(options.get('port','')).casefold()
        if share_ptt and sequencer is None:raise ValueError(tr('fsk.conflict'))
        baud=float(advanced['rtty_baud'])
        if not math.isfinite(baud) or not 30<=baud<=300:raise ValueError(tr('fsk.invalid'))
        if not controller.status.connected:raise ValueError(tr('fsk.connected'))
    except Exception as exc:return False,str(exc)
    engine._fsk_mode_confirmed=None
    engine._tx_active=True;engine._tx_cancel.clear();engine.secondary_notice=''
    def worker():
        success=False;message=tr('ui.63e1879b6cfd6a0e');timer=False
        try:
            key.open()
            if share_ptt:sequencer.borrowed_serial=key.ser
            # Mode must be confirmed before any PTT, even if auto-mode is OFF.
            if engine._tx_cancel.is_set():return
            if not controller.set_fsk_mode(options.get('mode','RTTY')):
                raise RuntimeError(tr('fsk.mode_failed'))
            engine._fsk_mode_confirmed=options.get('mode','RTTY')
            if not ptt_on or ptt_on() is not True:raise RuntimeError(tr('ui.5eef7dde3c3c7e95'))
            if engine._tx_cancel.wait(.12):return
            if sys.platform=='win32':
                import ctypes
                timer=ctypes.windll.winmm.timeBeginPeriod(1)==0
            clock=BitClock(key,engine._tx_cancel,baud);encoder=CodeEncoder()
            if not clock.emit(True,3) or not clock.code(31):return
            if session is None:
                for ch in (text or '')+'\r\n':
                    for code in encoder.char(ch):
                        if not clock.code(code):return
                if not clock.emit(True,2):return
            else:
                epoch=session.epoch
                while not engine._tx_cancel.is_set():
                    with session.lock:current=session.epoch
                    if epoch!=current:
                        epoch=current;encoder.figures=False
                        if not clock.code(31):return
                    item=session.next_char()
                    if item:
                        e,index,ch=item
                        for code in encoder.char(ch):
                            if not clock.code(code):return
                        session.records.append(ch)
                        if progress:progress(e,index+1,ch)
                    else:
                        with session.lock:complete=session.position==len(session.text)
                        auto_stop=session.idle_expired()
                        if auto_stop or (complete and not session.hold):break
                        encoder.figures=False
                        if not clock.code(31):return
                if engine._tx_cancel.is_set():return
            success=True;message=tr('ui.fe0cbba02e8d4de7')
        except Exception as exc:message=tr('ui.f8732c961aef978d')+str(exc)
        finally:
            try:
                if ptt_off and ptt_off() is False:success=False;message=tr('ui.240e5b329beabdee')
            except Exception as exc:success=False;message=str(exc)
            try:key.close()
            except Exception as exc:success=False;message=str(exc)
            if timer:
                import ctypes
                ctypes.windll.winmm.timeEndPeriod(1)
            engine._fsk_mode_confirmed=None
            engine._tx_active=False
            finished(success,message)
    engine._tx_thread=threading.Thread(target=worker,daemon=True);engine._tx_thread.start()
    return True,tr('ui.18e846a7e87b6ef5')
