"""Cancellable read-only feeds. GUI consumes a bounded mailbox, never sockets."""
from .diagnostics import trace, event
import json
import queue
import re
import socket
import threading
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from .ry_spots import parse_telnet, parse_jcluster
from .paths import app_root, resource_path

_io_lock=threading.Lock()
_pending_io=set()
_http_next={}


def bounded_io(key,work,stop,timeout,close_late=lambda result:None):
    """DNS is not covered by socket timeouts. Bound caller time and late results."""
    results=queue.Queue(maxsize=1);guard=threading.Lock();active=[True]
    with _io_lock:
        if key in _pending_io:raise TimeoutError('Previous connection is still resolving')
        _pending_io.add(key)
    def run():
        value=None
        try:value=work();error=None
        except Exception as exc:error=exc
        with guard:
            if active[0]:results.put((value,error))
            elif value is not None:close_late(value)
        with _io_lock:_pending_io.discard(key)
    threading.Thread(target=run,daemon=True,name='PSRTTY-FeedIO').start()
    end=time.monotonic()+timeout
    try:
        while not stop.is_set() and time.monotonic()<end:
            try:
                value,error=results.get(timeout=.05)
                if error:raise error
                return value
            except queue.Empty:pass
        raise TimeoutError('Connection stopped' if stop.is_set() else 'Connection timed out')
    finally:
        with guard:
            active[0]=False
            try:value,error=results.get_nowait()
            except queue.Empty:pass
            else:
                if value is not None:close_late(value)


def load_sources(path=None):
    path = path or app_root()/'config/ry_radar_sources.json'
    # User edits live under config and survive software updates.
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf-8') as f:
            f.write(resource_path('psrtty/data/ry_radar_sources.json').read_text(encoding='utf-8'))
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 1: raise ValueError(f'{path.name}: schema')
    for group in ('rbn', 'clusters'):
        if not isinstance(data.get(group), list) or len(data[group]) > 20: raise ValueError(group)
        for index, s in enumerate(data[group]):
            label = f'{group}[{index}]'
            if not isinstance(s, dict) or not isinstance(s.get('name'), str): raise ValueError(label)
            if type(s.get('enabled', True)) is not bool: raise ValueError(label+': enabled')
            if s.get('transport', 'telnet') == 'http':
                if urlparse(s.get('url', '')).scheme != 'https': raise ValueError(label+': https')
                if not 90 <= s.get('interval', 90) <= 86400: raise ValueError(label+': interval')
            else:
                if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}', s.get('host', '')): raise ValueError(label+': host')
                if type(s.get('port')) is not int or not 1 <= s['port'] <= 65535: raise ValueError(label+': port')
                if not isinstance(s.get('commands', []), list) or any(not isinstance(c,str) or '\n' in c or '\r' in c for c in s.get('commands', [])): raise ValueError(label+': commands')
    if not 10 <= data.get('dwell', 60) <= 3600: raise ValueError('dwell')
    old=dict(name='BH4HKZ / Shanghai',host='spots.bh4hkz.com',port=7373,
             commands=['set dx filt'],enabled=True)
    changed=False
    for i,source in enumerate(data['rbn']):
        if source==old:
            data['rbn'][i]=dict(name='RBN / Official',host='telnet.reversebeacon.net',port=7000,commands=[],enabled=True)
            changed=True
    if changed:
        backup=path.with_name(path.name+'.pre-fix4.bak')
        if not backup.exists():
            with backup.open('xb') as f:f.write(path.read_bytes())
        temporary=path.with_name(path.name+'.tmp')
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        temporary.replace(path)
    return data


class TelnetText:
    """Incremental IAC handling, including split negotiations and suboptions."""
    def __init__(self): self.state = 0; self.command = 0

    def feed(self, raw):
        text = bytearray(); reply = bytearray()
        for c in raw:
            if self.state == 0:
                if c == 255: self.state = 1
                else: text.append(c)
            elif self.state == 1:
                if c in (251,252,253,254): self.command = c; self.state = 2
                elif c == 250: self.state = 3
                else:
                    if c == 255: text.append(c)
                    self.state = 0
            elif self.state == 2:
                if self.command in (251,253): reply.extend((255,254 if self.command==251 else 252,c))
                self.state = 0
            elif self.state == 3:
                if c == 255: self.state = 4
            elif self.state == 4: self.state = 0 if c == 240 else 3
        return text.decode('utf-8', 'replace'), bytes(reply)


class RadarFeeds:
    def __init__(self, config, call, connector=socket.create_connection, opener=urlopen):
        if not re.fullmatch(r'[A-Z0-9]+(?:/[A-Z0-9]+)*', call): raise ValueError('callsign')
        self.config = config; self.call = call; self.connector = connector; self.opener = opener
        self.events = queue.Queue(maxsize=2048); self.stop_event = threading.Event()
        self.sockets = set(); self.lock = threading.Lock(); self.threads = []

    def emit(self, kind, *args):
        if kind in ('status','rotation'):event('ry_radar',str((kind,*args)))
        try: self.events.put_nowait((kind, *args))
        except queue.Full: pass

    @trace('ry_radar')
    def start(self):
        if self.threads: return
        jobs = [self._cycle]
        for source in self.config['clusters']:
            if source.get('enabled', True):
                jobs.append(lambda s=source: self._http(s) if s.get('transport')=='http' else self._persistent(s))
        for job in jobs:
            t = threading.Thread(target=job, daemon=True, name='PSRTTY-Radar')
            self.threads.append(t); t.start()

    @trace('ry_radar')
    def stop(self):
        self.stop_event.set()
        with self.lock:
            for sock in tuple(self.sockets):
                try: sock.shutdown(socket.SHUT_RDWR)
                except OSError: pass
                sock.close()
        # Threads have finite socket/HTTP timeouts; GUI never waits for DNS.

    def _cycle(self):
        sources = [s for s in self.config['rbn'] if s.get('enabled', True)]
        for source in sources:self.emit('status',source['name'],'waiting','')
        while sources and not self.stop_event.is_set():
            for index,source in enumerate(sources):
                if self.stop_event.is_set(): return
                self.emit('rotation',source['name'],index+1,len(sources))
                end = time.monotonic()+self.config.get('dwell', 60)
                self._telnet(source, end)
                self.stop_event.wait(max(0, end-time.monotonic()))

    def _persistent(self, source):
        backoff = 5
        while not self.stop_event.is_set():
            self._telnet(source)
            self.stop_event.wait(backoff)
            backoff = min(120, backoff*2)

    def _telnet(self, source, deadline=None):
        sock = None; name = source['name']; failed=False
        self.emit('status', name, 'connecting', '')
        try:
            address=(source['host'], source['port'])
            sock=bounded_io(('tcp',*address),lambda:self.connector(address,timeout=5),
                self.stop_event,5,lambda s:s.close())
            with self.lock:
                if self.stop_event.is_set(): sock.close(); return
                self.sockets.add(sock)
            sock.settimeout(.5)
            parser = TelnetText(); buffer = ''; login = False; commands = False
            opened = time.monotonic()
            self.emit('status', name, 'connected', '')
            while not self.stop_event.is_set() and (deadline is None or time.monotonic()<deadline):
                try: raw = sock.recv(16384)
                except socket.timeout: raw = None
                if raw == b'':
                    if not self.stop_event.is_set():raise ConnectionError('Server closed the connection')
                    break
                if raw:
                    text, reply = parser.feed(raw)
                    if reply: sock.sendall(reply)
                    buffer += text.replace('\r', '\n')
                    if not login and re.search(r'(?:login|call(?:sign)?)[^\n]{0,30}:\s*$', buffer, re.I):
                        sock.sendall((self.call+'\r\n').encode('ascii')); login=True; opened=time.monotonic()
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n',1)
                        spot = parse_telnet(line, name)
                        if spot:
                            self.emit('spot', spot)
                            self.emit('status',name,'receiving','')
                    buffer = buffer[-8192:]
                if not login and time.monotonic()-opened > 2:
                    sock.sendall((self.call+'\r\n').encode('ascii'));login=True;opened=time.monotonic()
                if login and not commands and time.monotonic()-opened > 1:
                    for command in source.get('commands', []): sock.sendall((command+'\r\n').encode('ascii'))
                    commands=True
        except (OSError, ValueError) as e:
            failed=True
            if not self.stop_event.is_set():self.emit('status', name, 'error', str(e))
        finally:
            if sock:
                with self.lock: self.sockets.discard(sock)
                sock.close()
            if not failed:self.emit('status', name, 'waiting' if deadline is not None else 'closed', '')

    def _http(self, source):
        interval = source.get('interval', 90); name = source['name']; delay=interval
        while not self.stop_event.is_set():
            with _io_lock:remaining=max(0,_http_next.get(source['url'],0)-time.monotonic())
            if self.stop_event.wait(remaining):return
            try:
                req=Request(source['url'], headers={'User-Agent':'PSRTTY/1.27', 'Accept':'application/xml,text/xml'})
                with _io_lock:_http_next[source['url']]=time.monotonic()+interval
                def fetch():
                    with self.opener(req,timeout=8) as response:return response.read(2_000_001)
                raw=bounded_io(('http',source['url']),fetch,self.stop_event,8)
                for spot in parse_jcluster(raw, name): self.emit('spot', spot)
                self.emit('status', name, 'connected', ''); delay=interval
            except Exception as e:
                self.emit('status', name, 'error', str(e));delay=min(3600,max(interval,delay*2))
                retry=getattr(e,'headers',{}).get('Retry-After','')
                if retry.isdigit():delay=max(delay,min(int(retry),86400))
            with _io_lock:_http_next[source['url']]=time.monotonic()+delay
            self.stop_event.wait(delay)
