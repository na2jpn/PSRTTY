"""Experimental FT-991/A and FTX-1 CAT, USB AFSK only (MAIN / VFO A)."""
from __future__ import annotations
import re
import time
from .civ import CIVController, CIVStatus, serial

YAESU_MODELS = {
    'FT-991 / FT-991A': 'FT-991 / FT-991A（試験用）',
    'FTX-1': 'FTX-1シリーズ（試験用）',
}


class YaesuController(CIVController):
    def __init__(self, model, stopbits=None):
        super().__init__(0)
        if model not in YAESU_MODELS:
            raise ValueError('未対応のYaesu機種です')
        self.model = model
        self.stopbits = int(stopbits or (1 if model == 'FTX-1' else 2))
        if self.stopbits not in (1, 2):
            raise ValueError('ストップビットは1または2です')

    def _query(self, command, prefix, timeout=.4, allow_cancel=False):
        if not self.ser:
            return ''
        self.ser.reset_input_buffer()
        self.ser.write(command.encode('ascii'))
        deadline = time.monotonic() + timeout
        if self._connect_deadline is not None:
            deadline = min(deadline, self._connect_deadline)
        buf = bytearray()
        while time.monotonic() < deadline and (allow_cancel or not self.cancel.is_set()):
            ch = self.ser.read(1)
            if not ch:
                continue
            buf += ch
            if len(buf) > 256:
                buf.clear()
            if ch == b';':
                frame = bytes(buf).decode('ascii', errors='ignore').strip()
                buf.clear()
                if frame == '?;':
                    return ''
                if frame.startswith(prefix) and frame != command:
                    return frame
        return ''

    def _connect(self, port, baud):
        self.disconnect()
        if serial is None:
            self.status.message = 'pyserialがインストールされていません'
            return self.status
        ports = self.available_ports() if str(port).upper() == 'AUTO' else [str(port)]
        speeds = [38400, 4800, 9600, 19200, 115200] if str(baud).upper() == 'AUTO' else [int(baud)]
        for candidate in ports:
            for speed in speeds:
                if self.cancel.is_set() or time.monotonic() >= self._connect_deadline:
                    self.status.message = 'CAT接続を中止しました／タイムアウト。COMと速度を手動指定してください。'
                    return self.status
                try:
                    # Set line states BEFORE opening; Standard COM may be wired to PTT.
                    self.ser = serial.Serial(port=None, baudrate=speed, timeout=.05,
                                             write_timeout=.3, stopbits=self.stopbits,
                                             rtscts=False, dsrdtr=False)
                    self.ser.rts = False
                    self.ser.dtr = False
                    self.ser.port = candidate
                    self.ser.open()
                    identity = self._query('ID;', 'ID')
                    expected = {'ID0840;'} if self.model == 'FTX-1' else {'ID0570;', 'ID0670;'}
                    if identity not in expected:
                        self.disconnect()
                        continue
                    freq = self.read_frequency()
                    if freq and not self.cancel.is_set():
                        self.status = CIVStatus(True, candidate, speed, freq, '接続（試験用）')
                        return self.status
                except Exception:
                    pass
                self.disconnect()
        self.status.message = '選択機種のCAT応答を確認できませんでした。Enhanced COM・CAT速度・ストップビットを確認してください。'
        return self.status

    def read_frequency(self):
        with self._lock:
            try:
                raw = self._query('FA;', 'FA')
                if re.fullmatch(r'FA[0-9]{9};', raw):
                    freq = int(raw[2:-1])
                    if 30_000 <= freq <= 470_000_000:
                        self.status.frequency_hz = freq
                        return freq
            except Exception:
                pass
            return None

    def set_data_mode(self, mode='LSB-D'):
        if mode not in ('LSB-D', 'USB-D'):
            raise ValueError('未対応のDATAモード')
        with self._lock:
            if not self.ser or not self.status.connected or self.cancel.is_set():
                return False
            try:
                digit = '8' if mode == 'LSB-D' else 'C'
                self.ser.write(f'MD0{digit};'.encode('ascii'))
                return self._query('MD0;', 'MD0') == f'MD0{digit};'
            except Exception:
                return False

    def read_transmitting(self):
        with self._lock:
            if not self._control_ready(): return None
            reply = self._query('TX;', 'TX', timeout=.25)
            if reply in ('TX0;', 'TX1;', 'TX2;'): return reply != 'TX0;'
            return None

    def set_frequency(self, hz):
        with self._lock:
            if not self._control_ready() or type(hz) is not int or not 30000 <= hz <= 470000000: return False
            try:
                if self.read_transmitting() is not False: return False
                self.ser.write(f'FA{hz:09d};'.encode('ascii'))
                return self.read_frequency() == hz
            except Exception:
                return False

    def _filter_options(self, mode, narrow):
        # Manufacturer CAT tables: FT-991/A table 4; FTX-1 table 5.
        if self.model == 'FTX-1':
            if mode in ('1','2'):
                widths=[300,400,600,850,1100,1200,1500,1650,1800,1950,2100,2250,2400,2450,2500,2600,2700,2800,2900,3000,3200,3500,4000]
            elif mode in ('3','7','6','9','8','C','E'):
                widths=[50,100,150,200,250,300,350,400,450,500,600,800,1200,1400,1700,2000,2400,3000,3500,4000]
            else: return []
            return [(0,'初期値')]+[(i,f'{v} Hz') for i,v in enumerate(widths,1)]
        if mode in ('1','2'):
            widths=[200,400,600,850,1100,1350,1500,1650,1800] if narrow else [1800,1950,2100,2200,2300,2400,2500,2600,2700,2800,2900,3000,3200]
            start=1 if narrow else 9
        elif mode in ('3','7','6','9','8','C'):
            widths=[50,100,150,200,250,300,350,400,450,500] if narrow else [500,800,1200,1400,1700,2000,2400,3000]
            start=1 if narrow else 10
        else: return []
        return [(0,'初期値')]+[(i,f'{v} Hz') for i,v in enumerate(widths,start)]

    def read_filter(self):
        with self._lock:
            if not self._control_ready(): return None
            try:
                mode=re.fullmatch(r'MD0([0-9A-Z]);',self._query('MD0;','MD0',timeout=.25))
                narrow=re.fullmatch(r'NA0([01]);',self._query('NA0;','NA0',timeout=.25))
                if not mode or not narrow: return None
                mode=mode[1]; narrow=bool(int(narrow[1]))
                prefix='SH00' if self.model=='FTX-1' else 'SH0'
                width=re.fullmatch(prefix+r'(\d{2});',self._query('SH0;','SH0',timeout=.25))
                options=self._filter_options(mode,narrow)
                value=int(width[1]) if width else None
                if value not in dict(options): value=None
                return dict(kind='YAESU',mode=mode,narrow=narrow,value=value,options=options)
            except Exception: return None

    def set_filter(self, value, expected):
        with self._lock:
            if not self._control_ready(): return False
            try:
                if self.read_transmitting() is not False: return False
                current=self.read_filter()
                if not current or not expected or (current['mode'],current['narrow'])!=(expected['mode'],expected['narrow']): return False
                if type(value) is not int or value not in dict(current['options']): return False
                prefix='SH00' if self.model=='FTX-1' else 'SH0'
                self.ser.write(f'{prefix}{value:02d};'.encode('ascii'))
                actual=self.read_filter()
                return bool(actual and actual['mode']==current['mode'] and actual['narrow']==current['narrow'] and actual['value']==value)
            except Exception: return False

    def set_narrow(self, on, expected):
        with self._lock:
            if not self._control_ready(): return False
            try:
                if self.read_transmitting() is not False: return False
                current=self.read_filter()
                if not current or not expected or current['mode']!=expected['mode']: return False
                self.ser.write(f'NA0{int(bool(on))};'.encode('ascii'))
                actual=self.read_filter()
                return bool(actual and actual['mode']==current['mode'] and actual['narrow'] is bool(on))
            except Exception: return False

    def _feature_format(self, name):
        # FTX-1 has level commands instead of FT-991's NB/NR switches.
        if self.model == 'FTX-1' and name in ('NB', 'NR'):
            return ('NL0', 3, 10) if name == 'NB' else ('RL0', 2, 10)
        return {'NB': ('NB0', 1, 1), 'NR': ('NR0', 1, 1),
                'AN': ('BC0', 1, 1), 'MN': ('BP00', 3, 1)}.get(name)

    def read_feature(self, name):
        with self._lock:
            fmt = self._feature_format(name)
            if not self._control_ready() or not fmt: return None
            try:
                prefix, width, maximum = fmt
                reply = self._query(prefix + ';', prefix, timeout=.25)
                match = re.fullmatch(re.escape(prefix) + r'(\d{' + str(width) + r'});', reply)
                if not match or not 0 <= int(match[1]) <= maximum: return None
                value = int(match[1])
                if value:
                    if not hasattr(self, '_feature_levels'): self._feature_levels = {}
                    self._feature_levels[name] = value
                return value != 0
            except Exception:
                return None

    def set_feature(self, name, on):
        with self._lock:
            fmt = self._feature_format(name)
            if not self._control_ready() or not fmt: return False
            try:
                if self.read_transmitting() is not False: return False
                prefix, width, maximum = fmt
                value = getattr(self, '_feature_levels', {}).get(name, 1) if on else 0
                self.ser.write(f'{prefix}{min(value, maximum):0{width}d};'.encode('ascii'))
                return self.read_feature(name) is bool(on)
            except Exception:
                return False

    def set_ptt(self, on):
        with self._lock:
            if not self.ser or not self.status.connected or (on and self.cancel.is_set()):
                return False
            try:
                if on:
                    # The UI/log tracks MAIN/VFO A only. Do not key another TX VFO.
                    if self._query('FT;', 'FT') != 'FT0;':
                        return False
                    if self._query('MD0;', 'MD0') not in ('MD08;', 'MD0C;'):
                        return False
                    if self._query('TX;', 'TX') != 'TX0;':
                        return False
                self.ser.write(b'TX1;' if on else b'TX0;')
                ok = self._query('TX;', 'TX', allow_cancel=not on) == ('TX1;' if on else 'TX0;')
                if on and not ok:
                    self.ser.write(b'TX0;')
                return ok
            except Exception:
                return False
