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
PORT_SETTLE_SECONDS = .15

def release_connection(controller):
    """Dispose the dedicated FSK port before the CAT connection is closed."""
    session = vars(controller).get('_fsk_key_session')
    controller._fsk_key_session = None
    if session:
        device, signature, idle = session
        try:
            for line, value in idle.items():
                try:setattr(device, line, value)
                except Exception:pass
        finally:
            try:device.close()
            except Exception:pass

def wait_receive(controller, cancel):
    """After our port initialization, require a confirmed RX state, never force RX."""
    for attempt in range(5):
        if cancel.is_set() or not controller.status.connected:
            raise RuntimeError(tr('v122.cancelled'))
        if controller.read_transmitting() is False:
            return
        if attempt < 4 and cancel.wait(.1):
            raise RuntimeError(tr('v122.cancelled'))
    raise RuntimeError(tr('v122.receive_failed'))

def borrow_for_ptt_test(controller, config):
    """Use the held interface for a separate PTT-line test without reopening it."""
    session=vars(controller).get('_fsk_key_session')
    if not session or not controller.status.connected:
        return None
    device,signature,idle=session
    if str(config.get('com_port','')).casefold()!=signature[0]:
        return None
    line=str(config.get('line','')).lower()
    if (not config.get('enabled') or config.get('role')!='ptt'
        or config.get('line')==signature[1] or line not in idle
        or idle[line]!=bool(config.get('reversed',False))):
        raise ValueError(tr('fsk.conflict'))
    return device

def prepare_connection(controller, radio, options, external=None):
    """Open a dedicated keying port once, during connection, with inactive PTT."""
    key = SerialKey(controller, radio, options, external)
    with controller._lock:
        if controller.read_transmitting() is not False:
            raise RuntimeError(tr('v122.receive_failed'))
        try:
            key.open()
            if key.opened_new and controller.cancel.wait(PORT_SETTLE_SECONDS):
                raise RuntimeError(tr('v122.cancelled'))
            wait_receive(controller, controller.cancel)
        except Exception:
            release_connection(controller)
            key.ser=None
            raise
        finally:
            key.close()

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
        self.opened_new=False
        self.persistent='_fsk_key_session' in vars(controller)
    def open(self):
        if self.persistent:
            with self.controller._lock:
                if not self.controller.status.connected or self.controller.cancel.is_set():
                    raise RuntimeError(tr('v122.cancelled'))
                return self._open()
        return self._open()
    def _open(self):
        self.opened_new=False
        if self.shared:
            self.ser=getattr(self.controller,'ser',None)
            if self.ser is None or not self.controller.status.connected:
                raise ValueError(tr('fsk.connected'))
        else:
            import serial
            idle={'rts':False,'dtr':False}
            idle[self.options['line'].lower()]=bool(self.options.get('invert'))
            if self.external.get('enabled') and str(self.external.get('com_port','')).casefold()==str(self.options['port']).casefold():
                idle[self.external['line'].lower()]=bool(self.external.get('reversed',False))
            signature=(str(self.options['port']).casefold(),self.options['line'],tuple(sorted(idle.items())))
            session=vars(self.controller).get('_fsk_key_session') if self.persistent else None
            if session and session[1]==signature and getattr(session[0],'is_open',True) is not False:
                self.ser=session[0]
                self.mark(True)
                return
            if session:release_connection(self.controller)
            # Set inactive levels before opening: do not key RTS/PTT on open.
            self.ser=serial.Serial(port=None,baudrate=9600,timeout=.05,write_timeout=.3,rtscts=False,dsrdtr=False)
            for line,value in idle.items():setattr(self.ser,line,value)
            self.ser.port=self.options['port']
            try:
                self.ser.open()
                for line,value in idle.items():setattr(self.ser,line,value)
            except Exception:
                self.ser.close();self.ser=None
                raise
            self.opened_new=True
            if self.persistent:self.controller._fsk_key_session=(self.ser,signature,idle)
        self.mark(True)
    def mark(self, mark):
        # Default: idle Mark=inactive, Space=active. Polarity is selectable.
        setattr(self.ser,self.options['line'].lower(),bool(not mark)^bool(self.options.get('invert')))
    def close(self):
        if self.ser is None:return
        try:self.mark(True)
        finally:
            if not self.shared and not self.persistent:self.ser.close()
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
        success=False;message=tr('ui.63e1879b6cfd6a0e');timer=False;ptt_attempted=False
        stage='mode'
        trace=[]
        controller.fsk_start_diagnostic={'events':trace}
        try:
            # Mode must be confirmed before any PTT, even if auto-mode is OFF.
            trace.append('mode_before_port')
            if engine._tx_cancel.is_set():return
            from .hamlib_radio import HamlibController
            confirmed=(controller.set_fsk_mode(options.get('mode','RTTY'),cancel_event=engine._tx_cancel)
                       if isinstance(controller,HamlibController) else controller.set_fsk_mode(options.get('mode','RTTY')))
            if not confirmed:
                if engine._tx_cancel.is_set():return
                detail=getattr(controller,'fsk_mode_error','')
                raise RuntimeError(detail if isinstance(detail,str) and detail else tr('fsk.mode_failed'))
            if engine._tx_cancel.is_set():return
            stage='port'
            trace.append('port_prepare')
            key.open()
            if share_ptt:sequencer.borrowed_serial=key.ser
            if key.opened_new is True:
                stage='receive'
                trace.append('receive_after_port')
                if engine._tx_cancel.wait(PORT_SETTLE_SECONDS):return
                wait_receive(controller,engine._tx_cancel)
            if engine._tx_cancel.is_set():return
            engine._fsk_mode_confirmed=options.get('mode','RTTY')
            stage='ptt'
            trace.append('ptt_on')
            ptt_attempted=True
            if not ptt_on or ptt_on() is not True:raise RuntimeError(tr('ui.5eef7dde3c3c7e95'))
            stage='keying'
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
        except Exception as exc:
            controller.fsk_start_diagnostic.update(stage=stage,error=str(exc))
            message=tr('ui.f8732c961aef978d')+tr('v122.stage_'+stage)+': '+str(exc)
        finally:
            try:
                if ptt_attempted and ptt_off and ptt_off() is False:success=False;message=tr('ui.240e5b329beabdee')
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
