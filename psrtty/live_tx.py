"""Cancellable streaming ITA2 with an editable, age-gated pending tail."""
from __future__ import annotations
import threading
import time
import queue
import sys
import numpy as np
from .rtty_codec import LTRS_ENCODE, FIGS_ENCODE
from .audio_devices import resolve_device
from .i18n import tr


class LiveText:
    """Only the uncommitted tail may be edited. Epochs discard stale replay events."""
    def __init__(self, text='', delay=.5, hold=True):
        self.lock = threading.RLock()
        self.text = text
        self.delay = delay
        self.hold = hold
        self.times = [time.monotonic()] * len(text)
        self.position = 0
        self.epoch = 0
        self.records = []

    def update(self, text):
        with self.lock:
            if text[:self.position] != self.text[:self.position]: return False
            common = self.position
            while common < min(len(text), len(self.text)) and text[common] == self.text[common]: common += 1
            self.times = self.times[:common] + [time.monotonic()] * (len(text)-common)
            self.text = text
            return True

    def replay(self):
        with self.lock:
            self.position = 0
            self.epoch += 1
            self.times = [0.] * len(self.text)
            return self.epoch

    def next_char(self, now=None):
        with self.lock:
            if self.position == len(self.text): return None
            now = time.monotonic() if now is None else now
            if now < self.times[self.position] + self.delay: return None
            index = self.position
            self.position += 1
            return self.epoch, index, self.text[index]


class ToneEncoder:
    def __init__(self, rate, baud, mark, space, invert):
        self.rate, self.baud, self.mark, self.space, self.invert = rate, baud, mark, space, invert
        self.phase = 0.
        self.error = 0.
        self.figures = False
    def tone(self, mark, units):
        exact = self.rate/self.baud*units+self.error
        n = max(1, round(exact)); self.error = exact-n
        step = 2*np.pi*(self.mark if bool(mark)^self.invert else self.space)/self.rate
        result = np.sin(self.phase + step*np.arange(n)).astype(np.float32)
        self.phase = (self.phase + step*n) % (2*np.pi)
        return result
    def code(self, code):
        return np.concatenate([self.tone(False,1)] + [self.tone(bool(code>>i&1),1) for i in range(5)] + [self.tone(True,1.5)])
    def char(self, ch):
        ch = ch.upper()
        codes = []
        if ch == '\n': codes = [LTRS_ENCODE['\r'], LTRS_ENCODE['\n']]
        elif ch in LTRS_ENCODE:
            if self.figures and ch not in ' \r': codes.append(31); self.figures=False
            codes.append(LTRS_ENCODE[ch])
        elif ch in FIGS_ENCODE:
            if not self.figures: codes.append(27); self.figures=True
            codes.append(FIGS_ENCODE[ch])
        else: codes = [LTRS_ENCODE[' ']]
        return np.concatenate([self.code(c) for c in codes])


class MonitorSink:
    """A separate device clock; slow/failed monitoring never blocks primary TX."""
    def __init__(self, stream, cancel, gain, report):
        self.stream, self.cancel, self.gain, self.report = stream, cancel, gain, report
        self.blocks=queue.Queue(25);self.failed=False;self.closed=threading.Event();self.drained=False
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def offer(self, audio):
        if self.failed:return
        try:self.blocks.put_nowait(audio)
        except queue.Full:
            self.failed=True;self.report(tr('ui.292e6223635779d3'))
    def run(self):
        try:
            while not self.cancel.is_set() and not self.failed and not self.closed.is_set():
                try: block=self.blocks.get(timeout=.05)
                except queue.Empty:continue
                if block is None:
                    self.stream.stop();self.drained=True;break
                self.stream.write(np.clip(block*self.gain,-1,1).reshape(-1,1))
        except Exception as exc:
            self.failed=True;self.report(str(exc))
        finally:
            try:
                if not self.drained:self.stream.abort()
            finally:self.stream.close()
    def close(self, drain=False):
        if drain and not self.failed and not self.cancel.is_set():
            try:self.blocks.put(None,timeout=1.)
            except queue.Full:self.closed.set()
        else:self.closed.set()
        self.thread.join(3.)
        if self.thread.is_alive():
            self.closed.set()
            try:self.stream.abort()
            except Exception:pass
            self.thread.join(1.)


def start_live(engine, sd, session, output_device, advanced, amplitude, ptt_on, ptt_off, finished, progress, offline=False):
    if sd is None:return False,tr('ui.a1cea5a40ed3af98')
    if engine._tx_active:return False,tr('ui.1270a65b09bcaf38')
    engine._tx_active=True;engine._tx_cancel.clear();engine.set_tx_gain(amplitude)
    engine.secondary_notice=''
    secondary=dict(engine.secondary_settings)
    def worker():
        primary=None;monitor=None;success=False;message=tr('ui.63e1879b6cfd6a0e');primary_gain=lambda:engine.tx_gain
        def open_stream(selection):
            if selection=='UNSET':raise ValueError(tr('ui.6213305916949e4c'))
            chosen=resolve_device(sd,selection,'output')
            stream=sd.OutputStream(samplerate=engine.sample_rate,device=chosen,channels=1,dtype='float32',blocksize=960,latency='low',
                **({'extra_settings':sd.WasapiSettings(auto_convert=True)} if sys.platform=='win32' else {}))
            try:stream.start()
            except Exception:stream.close();raise
            return stream,chosen
        try:
            # Resolve outputs before keying; disconnected operation never touches PTT.
            primary_error=None
            try:primary,chosen=open_stream(output_device)
            except Exception as exc:
                primary_error=exc
                if not offline or not secondary.get('enabled'):raise
            if secondary.get('enabled'):
                try:
                    secondary_stream,secondary_chosen=open_stream(secondary.get('device','UNSET'))
                    if primary is None:
                        primary=secondary_stream;chosen=secondary_chosen;primary_gain=lambda:secondary.get('gain',1.)
                        engine.secondary_notice=str(primary_error)
                    elif secondary_chosen==chosen:
                        secondary_stream.abort();secondary_stream.close()
                    else:monitor=MonitorSink(secondary_stream,engine._tx_cancel,secondary.get('gain',1.),lambda m:setattr(engine,'secondary_notice',m))
                except Exception as exc:
                    engine.secondary_notice=str(exc)
                    if primary is None:raise
            if engine._tx_cancel.is_set():return
            if not offline and (not ptt_on or ptt_on() is not True):raise RuntimeError(tr('ui.5eef7dde3c3c7e95'))
            if engine._tx_cancel.wait(.12):return
            encoder=ToneEncoder(engine.sample_rate,advanced['rtty_baud'],advanced['mark_hz'],advanced['space_hz'],advanced['invert'])
            def emit(audio):
                for offset in range(0,len(audio),960):
                    if engine._tx_cancel.is_set():return False
                    block=audio[offset:offset+960]
                    primary.write(np.clip(block*primary_gain(),-1,1).reshape(-1,1))
                    if monitor:monitor.offer(block.copy())
                return not engine._tx_cancel.is_set()
            if not emit(np.concatenate([encoder.tone(True,3),encoder.code(31)])):return
            epoch=session.epoch
            while not engine._tx_cancel.is_set():
                with session.lock:
                    current_epoch=session.epoch
                if current_epoch!=epoch:
                    epoch=current_epoch;encoder.figures=False
                    if not emit(encoder.code(31)):return
                item=session.next_char()
                if item:
                    item_epoch,index,ch=item
                    if not emit(encoder.char(ch)):return
                    session.records.append(ch)
                    progress(item_epoch,index+1,ch)
                else:
                    with session.lock:complete=session.position==len(session.text)
                    if complete and not session.hold:
                        if not emit(encoder.char('\n')):return
                        primary.stop();success=True;message=tr('ui.fe0cbba02e8d4de7');break
                    if not emit(encoder.tone(True,advanced['rtty_baud']*960/engine.sample_rate)):return
        except Exception as exc:message=tr('ui.f8732c961aef978d')+str(exc)
        finally:
            if primary:
                try:
                    if not success:primary.abort()
                except Exception as exc:success=False;message=tr('ui.611bb70023f686e8')+str(exc)
            if monitor:monitor.close(drain=success)
            try:
                if not offline and ptt_off and ptt_off() is False:success=False;message=tr('ui.240e5b329beabdee')
            except Exception as exc:success=False;message=tr('ui.386d70631d3ddd57')+str(exc)
            if primary:
                try:primary.close()
                except Exception as exc:success=False;message=str(exc)
            engine._tx_active=False
            finished(success,message)
    engine._tx_thread=threading.Thread(target=worker,daemon=True);engine._tx_thread.start()
    return True,tr('ui.18e846a7e87b6ef5')
