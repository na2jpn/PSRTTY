"""Bounded, opt-in USB serial print spool. No Qt or radio calls in the worker."""
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
import time
import textwrap

DEFAULT_PRINTER = dict(port='', baud=115200, target='RX', ignore_short=True,
                       min_chars=1, columns=32, line_delay=0.5, ack=False,
                       ack_timeout=10.0, max_jobs=500, timestamps=True)
MAX_TEXT = 8192
MAX_BYTES = 2 * 1024 * 1024


def normalize_settings(values):
    result = dict(DEFAULT_PRINTER)
    if isinstance(values, dict): result.update({k:v for k,v in values.items() if k in result})
    for key, low, high in [('baud',1200,921600),('min_chars',0,300),('columns',16,80),('max_jobs',10,2000)]:
        try: result[key] = max(low, min(high, int(result[key])))
        except (ValueError,TypeError,OverflowError): result[key] = DEFAULT_PRINTER[key]
    for key, low, high in [('line_delay',0.05,5.0),('ack_timeout',1.0,60.0)]:
        try: result[key] = max(low,min(high,float(result[key])))
        except (ValueError,TypeError,OverflowError): result[key] = DEFAULT_PRINTER[key]
    result['port'] = str(result['port'] or '').strip()
    if result['target'] not in ('RX','TX','RXTX'): result['target']='RX'
    for key in ('ack','timestamps','ignore_short'): result[key] = result[key] is True
    return result


def port_key(port):
    value = str(port or '').strip()
    if value.startswith('\\\\.\\'): value=value[4:]
    return value.upper() if value.upper().startswith('COM') else value


@dataclass(frozen=True)
class PrintJob:
    direction: str
    text: str
    when: datetime
    zone: str


def job_lines(job, settings):
    # A control character from received text must never become a printer command.
    body = ''.join(ch if 32 <= ord(ch) <= 126 or ch == '\n' else ' ' if ch in '\r\t' else '?' for ch in job.text)
    header = job.direction
    if settings['timestamps']:
        from .timebase import display_zone
        header = job.when.astimezone(display_zone(job.zone)).strftime('%m-%d %H:%M:%S')+' '+job.zone+' '+header
    lines = textwrap.wrap(header, settings['columns'])
    for line in body.splitlines():
        lines.extend(textwrap.wrap(line,settings['columns'],replace_whitespace=True,drop_whitespace=True) or [''])
    return [(line+'\n').encode('ascii') for line in lines]


class PrinterSpool:
    def __init__(self, settings=None, serial_factory=None):
        self.settings=normalize_settings(settings)
        self.serial_factory=serial_factory
        self.condition=threading.Condition()
        self.jobs=deque(); self.queued_bytes=0; self.active=False
        self.enabled=False; self.closing=False; self.generation=0
        self.problem=''; self.detail=''; self.skipped=0; self.sent=0
        self.thread=threading.Thread(target=self._run,name='PSRTTY-printer',daemon=True)
        self.thread.start()

    def snapshot(self):
        with self.condition:
            return dict(enabled=self.enabled, waiting=len(self.jobs)+int(self.active),
                        problem=self.problem, detail=self.detail, skipped=self.skipped, sent=self.sent)

    def configure(self, settings):
        with self.condition:
            if self.enabled or self.active or self.jobs: return False
            self.settings=normalize_settings(settings); self.generation+=1
            self.problem=''; self.detail=''; self.condition.notify_all(); return True

    def enable(self, value):
        with self.condition:
            if self.closing:return False
            if value and (not self.settings['port'] or self.active):return False
            self.enabled=bool(value)
            if value:
                self.problem='';self.detail=''
            else:
                # OFF is immediate cancellation, not a hidden queue that prints later.
                self.jobs.clear(); self.queued_bytes=0; self.generation+=1
                self.problem=''; self.detail=''
            self.condition.notify_all();return True

    def clear(self):
        with self.condition:
            self.jobs.clear();self.queued_bytes=0;self.generation+=1
            self.condition.notify_all()

    def pause(self, reason, detail=''):
        with self.condition:
            self.enabled=False;self.problem=reason;self.detail=detail;self.generation+=1
            self.condition.notify_all()

    def submit(self, direction, text, when=None, zone='JST', test=False):
        with self.condition:
            if self.closing:return False
            if (test and (self.jobs or self.active)) or not self.settings['port']:return False
            if not test and self.settings['target'] not in (direction,'RXTX'):return False
            text=str(text).strip()
            if not text or (not test and self.settings['ignore_short'] and len(text)<=self.settings['min_chars']):return False
            if self.problem or (not self.enabled and not test):
                if self.problem in ('full','error'):self.skipped+=1
                return False
            size=len(text[:MAX_TEXT+1].encode('utf-8'))
            if len(text)>MAX_TEXT or size+self.queued_bytes>MAX_BYTES or len(self.jobs)+int(self.active)>=self.settings['max_jobs']:
                self.skipped+=1;self.enabled=False;self.problem='full'
                # Preserve accepted jobs, pause them until explicit re-enable or clear.
                self.condition.notify_all();return False
            when=when or datetime.now(timezone.utc)
            if when.tzinfo is None:raise ValueError('Printer timestamps must be timezone-aware')
            self.jobs.append((PrintJob(direction,text,when,zone),size,test));self.queued_bytes+=size
            self.condition.notify_all();return True

    def stop(self):
        with self.condition:
            self.closing=True;self.enabled=False;self.jobs.clear();self.queued_bytes=0
            self.generation+=1;self.condition.notify_all()

    def _cancelled(self,generation):
        with self.condition:return self.closing or generation!=self.generation

    def _wait(self, seconds, generation):
        deadline=time.monotonic()+seconds
        with self.condition:
            while not self.closing and generation==self.generation:
                remaining=deadline-time.monotonic()
                if remaining<=0:return True
                self.condition.wait(min(remaining,.1))
        return False

    def _open(self, settings):
        factory=self.serial_factory
        if factory is None:
            from serial import Serial
            factory=Serial
        # Explicit finite timeouts; opening/writing never runs on the UI thread.
        return factory(port=settings['port'], baudrate=settings['baud'], timeout=.1, write_timeout=.5)

    def _ack(self, device, settings, generation):
        deadline=time.monotonic()+settings['ack_timeout'];buffer=bytearray()
        while time.monotonic()<deadline:
            if self._cancelled(generation):return False
            value=device.read(1)
            if value==b'\n':
                if bytes(buffer).strip()==b'OK':return True
                buffer.clear()
            elif len(buffer)<128:buffer.extend(value)
            else:raise OSError('Invalid ACK response')
        raise TimeoutError('Printer ACK timeout; delivery of the last line is unknown')

    def _run(self):
        device=None; device_generation=None
        try:
            while True:
                with self.condition:
                    if self.closing:break
                    if device is not None and device_generation!=self.generation:
                        try:device.close()
                        except Exception:pass
                        device=None
                    if not self.jobs or (not self.enabled and not self.jobs[0][2]):
                        self.condition.wait(.1);continue
                    job,size,test=self.jobs.popleft();self.queued_bytes-=size;self.active=True
                    settings=dict(self.settings);generation=self.generation
                try:
                    if device is None:
                        device=self._open(settings);device_generation=generation
                        # USB bridge reset/boot settling; cancellable, no UI delay.
                        if not self._wait(1.5,generation):continue
                    complete=True
                    for line in job_lines(job,settings):
                        if self._cancelled(generation):complete=False;break
                        if settings['ack']:device.reset_input_buffer()
                        offset=0
                        while offset<len(line):
                            if self._cancelled(generation):complete=False;break
                            count=device.write(line[offset:])
                            if not count:raise OSError('Printer write made no progress')
                            offset+=count
                        if not complete:break
                        if settings['ack'] and not self._ack(device,settings,generation):complete=False;break
                        if not self._wait(settings['line_delay'],generation):complete=False;break
                    with self.condition:
                        if complete:self.sent+=1
                except Exception as exc:
                    with self.condition:
                        if generation==self.generation:
                            self.enabled=False;self.problem='error';self.detail=str(exc);self.generation+=1
                            self.skipped+=1
                    # Never auto-retry uncertain partial output (would duplicate lines).
                    if device is not None:
                        try:device.close()
                        except Exception:pass
                        device=None
                finally:
                    with self.condition:
                        self.active=False;self.condition.notify_all()
                        idle=not self.enabled and not self.jobs
                    if idle and device is not None:
                        try:device.close()
                        except Exception:pass
                        device=None
        finally:
            if device is not None:
                try:device.close()
                except Exception:pass
