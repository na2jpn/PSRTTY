"""One-way Z-Link client; durable outbox, server readback, no log downloads.

Protocol based on jr8ppg/zLog 6e309daf and jr8ppg/zServer cd48d5d2.
A successful delivery means Z-Server contains the record, not that a particular
zLog window is open. Its contest and time basis must be configured by the user.
"""
from __future__ import annotations
import csv
import io
import json
import os
import secrets
import select
import socket
import tempfile
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from pathlib import Path

DEFAULT_OPTIONS = {'enabled': False, 'host': '127.0.0.1', 'port': 23,
                   'pc_name': 'PSRTTY', 'operator': '', 'tx': 15, 'time_basis': 'UTC', 'decimal': '.'}
BANDS = ('160m', '80m', '40m', '30m', '20m', '17m', '15m', '12m',
         '10m', '6m', '2m', '70cm', '23cm', '13cm', '6cm', '3cm')

class LinkError(Exception):
    def __init__(self, key, detail=''):
        self.key, self.detail = key, str(detail)
        super().__init__(key + (': ' + self.detail if self.detail else ''))


def options_checked(options):
    if not isinstance(options,dict):raise LinkError('zlink.bad_options')
    result = dict(DEFAULT_OPTIONS, **options)
    result['enabled'] = result['enabled'] is True
    result['host'] = str(result['host']).strip()
    result['pc_name'] = str(result['pc_name']).strip()
    result['operator'] = str(result['operator']).strip().upper()
    try:
        result['port'] = int(result['port']); result['tx'] = int(result['tx'])
        if not result['host'] or not 1 <= result['port'] <= 65535 or not 0 <= result['tx'] <= 15:
            raise ValueError()
        if not result['pc_name'] or len(result['pc_name']) > 20 or len(result['operator']) > 20:
            raise ValueError()
        for value in (result['host'], result['pc_name'], result['operator']):
            if any(ch in value for ch in '\r\n\x00~'):
                raise ValueError()
            value.encode('cp932')
        if result['time_basis'] not in ('UTC', 'JST') or result['decimal'] not in ('.', ','):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise LinkError('zlink.bad_options') from None
    return result


def _text(value):
    value = str(value)
    if any(ch in value for ch in '\r\n\x00'):
        raise LinkError('zlink.bad_qso')
    try:
        value.encode('cp932')
    except UnicodeError:
        raise LinkError('zlink.bad_qso') from None
    return value


def serialize(fields):
    buf = io.StringIO(newline='')
    csv.writer(buf, delimiter='~', lineterminator='', quoting=csv.QUOTE_MINIMAL).writerow(fields)
    payload = buf.getvalue()
    # zLog CommProcess truncates the entire command (without #ZLOG#) to 255.
    # CP932 is used by Delphi's AnsiString transport on Japanese Windows.
    if len(('PUTQSO ' + payload).encode('cp932')) > 255:
        raise LinkError('zlink.too_long')
    return payload


def qso_fields(qso, options, qso_id):
    options = options_checked(options)
    if qso.when_utc is None or qso.band not in BANDS or not qso.call.strip():
        raise LinkError('zlink.bad_qso')
    when = qso.when_utc
    if when.tzinfo is None: when = when.replace(tzinfo=timezone.utc)
    zone = timezone.utc if options['time_basis'] == 'UTC' else timezone(timedelta(hours=9))
    local = when.astimezone(zone).replace(tzinfo=None)
    date = (local - datetime(1899, 12, 30)).total_seconds() / 86400
    try:
        rst_s, rst_r = int(qso.rst_sent), int(qso.rst_rcvd)
        if not 111 <= rst_s <= 599 or not 111 <= rst_r <= 599: raise ValueError()
    except (ValueError, TypeError):
        raise LinkError('zlink.bad_qso') from None
    fields = ['ZLOGQSODATA:', format(date, '.10f'), _text(qso.call.upper()),
              _text(qso.sent), _text(qso.rcvd), str(rst_s), str(rst_r),
              str(int(qso.sent)) if qso.sent.isdecimal() and len(qso.sent) <= 8 else '0',
              '4', str(BANDS.index(qso.band)), '3', '', '', '0', '0', '0',
              _text(options['operator']), '', '0', '0', '0', str(options['tx']),
              '0', '0', str(qso_id),
              format(qso.freq_hz / 1000, '.1f') if qso.freq_hz else '',
              '0', _text(options['pc_name']), '0', '0', '0']
    if options['decimal'] == ',':
        fields[1] = fields[1].replace('.', ','); fields[25] = fields[25].replace('.', ',')
    serialize(fields)
    return fields


def same_record(expected, received):
    try:
        actual = next(csv.reader([received], delimiter='~'))
        if len(actual) < 31 or actual[0] != 'ZLOGQSODATA:': return False
        if abs(float(actual[1].replace(',', '.')) - float(expected[1].replace(',', '.'))) > 1 / 86400: return False
        for index in (2, 3, 4, 5, 6, 8, 9, 27):
            if actual[index] != expected[index]: return False
        return abs(float((actual[25] or '0').replace(',', '.')) - float((expected[25] or '0').replace(',', '.'))) < .11
    except (ValueError, IndexError, csv.Error):
        return False


class ZConnection:
    """CRLF framing, bounded reads; normal TCP Z-Server mode (no TLS login)."""
    def __init__(self, sock, cancelled):
        self.sock, self.cancelled, self.buffer = sock, cancelled, bytearray()
        self.sock.settimeout(.25)

    def send(self, command):
        if self.cancelled.is_set(): raise InterruptedError()
        self.sock.sendall(('#ZLOG# ' + command + '\r\n').encode('cp932'))

    def line(self, deadline):
        while not self.cancelled.is_set():
            if b'\r\n' in self.buffer:
                raw, _, tail = self.buffer.partition(b'\r\n'); self.buffer = bytearray(tail)
                return raw.decode('cp932', errors='replace')
            if time.monotonic() >= deadline: raise TimeoutError('Z-Server response timeout')
            try: data = self.sock.recv(4096)
            except socket.timeout: continue
            if not data: raise ConnectionError('Z-Server disconnected')
            self.buffer.extend(data)
            if len(self.buffer) > 65536: raise LinkError('zlink.protocol')
            if b'Login:' in self.buffer or b'Password:' in self.buffer:
                raise LinkError('zlink.normal_tcp')
        raise InterruptedError()

    def ids(self):
        self.send('GETQSOIDS')
        found = {}; deadline = time.monotonic() + 5
        while True:
            line = self.line(deadline)
            if line == '#ZLOG# ENDQSOIDS': return found
            if line.startswith('#ZLOG# QSOIDS '):
                for value in line[14:].split():
                    try: number = int(value)
                    except ValueError: raise LinkError('zlink.protocol') from None
                    found[number // 100] = number

    def record(self, number):
        self.send('GETLOGQSOID ' + str(number))
        result = None; deadline = time.monotonic() + 5
        while True:
            line = self.line(deadline)
            if line == '#ZLOG# RENEW': return result
            if line.startswith('#ZLOG# PUTLOGEX '): result = line[16:]

    def drain(self):
        while select.select([self.sock], [], [], 0)[0]:
            data = self.sock.recv(4096)
            if not data: raise ConnectionError('Z-Server disconnected')
            self.buffer.extend(data)
            if len(self.buffer) > 65536: raise LinkError('zlink.protocol')
        while b'\r\n' in self.buffer:
            _, _, tail = self.buffer.partition(b'\r\n'); self.buffer = bytearray(tail)


class ZServerLink:
    def __init__(self, path):
        self.path = Path(path); self.lock = threading.RLock()
        self.options = dict(DEFAULT_OPTIONS); self.entries = []
        self.state = 'zlink.disabled'; self.detail = ''; self.load_error = None
        self.cancelled = threading.Event(); self.wake = threading.Event()
        self.thread = None; self.sock = None; self.generation = 0; self.confirmed = 0
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                self.entries = data['entries']
                if data.get('schema') != 1 or not isinstance(self.entries, list): raise ValueError()
                for entry in self.entries:
                    fields=entry['fields']
                    if not isinstance(fields,list) or len(fields)!=31 or not all(isinstance(v,str) for v in fields):raise ValueError()
                    if fields[0]!='ZLOGQSODATA:' or fields[8]!='4' or not 0<=int(fields[9])<len(BANDS):raise ValueError()
                    number=int(fields[24])
                    if not 0<number<1600000000 or number%100 or not isinstance(entry['attempted'],bool):raise ValueError()
                    float(fields[1].replace(',','.'))
                    options_checked(entry['target']); serialize(entry['fields'])
            except Exception as exc:
                self.entries = []; self.load_error = str(exc)
                self.state = 'zlink.storage'; self.detail = str(exc)

    def snapshot(self):
        with self.lock: return self.state, self.detail, len(self.entries), self.confirmed

    def _status(self, state, detail=''):
        with self.lock: self.state, self.detail = state, str(detail)

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=self.path.name + '.', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
                json.dump({'schema': 1, 'entries': self.entries}, f, ensure_ascii=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name): os.unlink(name)

    @staticmethod
    def target(options):
        return {key: options[key] for key in ('host', 'port', 'pc_name', 'operator', 'tx', 'time_basis', 'decimal')}

    def check_options(self, options):
        checked = options_checked(options)
        with self.lock:
            if self.entries and any(e['target'] != self.target(checked) for e in self.entries):
                raise LinkError('zlink.pending_settings')
        return checked

    def configure(self, options):
        checked = self.check_options(options)
        with self.lock:
            if checked != self.options: self.generation += 1
            self.options = checked
        if self.load_error: return
        if checked['enabled'] and (self.thread is None or not self.thread.is_alive()):
            self.cancelled.clear()
            self.thread = threading.Thread(target=self._worker, name='PSRTTY-ZLink', daemon=True)
            self.thread.start()
        if not checked['enabled']:
            self._disconnect(); self._status('zlink.disabled')
        self.wake.set()

    def enqueue(self, qso):
        with self.lock:
            if not self.options['enabled']: return
            if self.load_error: raise LinkError('zlink.storage', self.load_error)
            number = self._new_id(self.options['tx'], {int(e['fields'][24]) // 100 for e in self.entries})
            entry = {'fields': qso_fields(qso, self.options, number),
                     'target': self.target(self.options), 'attempted': False}
            self.entries.append(entry)
            try: self._save()
            except Exception:
                self.entries.pop(); raise
        self.wake.set()

    @staticmethod
    def _new_id(tx, used):
        for _ in range(10000):
            number = tx * 100000000 + secrets.randbelow(9999) * 10000 + secrets.randbelow(100) * 100
            if number > 0 and number // 100 not in used: return number
        raise LinkError('zlink.id_collision')

    def _deliver(self, connection):
        ids = connection.ids()
        with self.lock:
            if not self.entries: return
            entry = self.entries[0]
            number = int(entry['fields'][24])
            existing = ids.get(number // 100)
        if existing is not None:
            if entry['attempted']:
                if not same_record(entry['fields'], connection.record(existing) or ''):
                    raise LinkError('zlink.id_collision')
                self._ack(entry); return
            with self.lock:
                new_id = self._new_id(entry['target']['tx'], set(ids) | {int(e['fields'][24]) // 100 for e in self.entries})
                entry['fields'][24] = str(new_id); self._save(); number = new_id
        with self.lock:
            entry['attempted'] = True; self._save()
        connection.send('PUTQSO ' + serialize(entry['fields']))
        # PUTQSO posts a GUI message in Z-Server. It has no explicit ACK.
        # Read back the server's ID and record after its message queue runs.
        for _ in range(8):
            if self.cancelled.wait(.15): raise InterruptedError()
            ids = connection.ids()
            existing = ids.get(number // 100)
            if existing is not None:
                if not same_record(entry['fields'], connection.record(existing) or ''):
                    raise LinkError('zlink.id_collision')
                self._ack(entry); return
        raise LinkError('zlink.unconfirmed')

    def _ack(self, entry):
        with self.lock:
            self.entries.remove(entry)
            try: self._save()
            except Exception:
                self.entries.insert(0, entry); raise
            self.confirmed += 1

    def _worker(self):
        connection = None; connected_generation = -1; last_check = 0
        try:
            while not self.cancelled.is_set():
                with self.lock: options = dict(self.options); generation = self.generation
                if not options['enabled']:
                    self._disconnect(); connection = None; self._status('zlink.disabled')
                    self.wake.wait(.5); self.wake.clear(); continue
                try:
                    if connection is None or generation != connected_generation:
                        self._disconnect(); connection = None; self._status('zlink.connecting')
                        sock = socket.create_connection((options['host'], options['port']), timeout=3)
                        self.sock = sock
                        connection = ZConnection(sock, self.cancelled)
                        connection.send('PCNAME ' + options['pc_name'])
                        connection.send('OPERATOR ' + options['operator'])
                        # Do not advertise a second active radio on the same band.
                        connection.ids(); connected_generation = generation; last_check = time.monotonic()
                        self._status('zlink.connected')
                    with self.lock:
                        if not self.options['enabled'] or generation != self.generation:continue
                        pending = bool(self.entries)
                    if pending:
                        self._deliver(connection); self._status('zlink.connected')
                    else:
                        connection.drain()
                        if time.monotonic() - last_check >= 15:
                            connection.ids(); last_check = time.monotonic()
                        self.wake.wait(.25); self.wake.clear()
                except InterruptedError: break
                except Exception as exc:
                    self._disconnect(); connection = None
                    with self.lock:enabled=self.options['enabled']
                    self._status((exc.key if isinstance(exc, LinkError) else 'zlink.error') if enabled else 'zlink.disabled',
                                 (exc.detail if isinstance(exc, LinkError) else str(exc)) if enabled else '')
                    self.wake.wait(5); self.wake.clear()
        finally: self._disconnect()

    def _disconnect(self):
        sock, self.sock = self.sock, None
        if sock:
            try: sock.shutdown(socket.SHUT_RDWR)
            except OSError: pass
            sock.close()

    def close(self):
        self.cancelled.set(); self.wake.set(); self._disconnect()
        if self.thread and self.thread is not threading.current_thread(): self.thread.join(.8)
