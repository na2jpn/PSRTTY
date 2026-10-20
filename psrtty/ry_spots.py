"""RTTY-only observations and a bounded, source-independent band cache."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
import xml.etree.ElementTree as ET

BANDS = ((1.8, 1.8, 2.0), (3.5, 3.5, 4.0), (5, 5.0, 5.5), (7, 7, 7.3),
         (10, 10.1, 10.15), (14, 14, 14.35), (18, 18.068, 18.168),
         (21, 21, 21.45), (24, 24.89, 24.99), (28, 28, 29.7),
         (50, 50, 54), (70, 70, 70.5), (144, 144, 148),
         (220, 220, 225), (430, 420, 450), (1200, 1240, 1300))


def band_for(hz):
    if hz is None: return None
    return next((b for b, lo, hi in BANDS if lo*1e6 <= hz < hi*1e6), None)


def short_frequency(hz):
    """Band heading supplies the MHz; never use this string for tuning."""
    return '.'+f'{hz/1e6:.6f}'.split('.', 1)[1].rstrip('0').ljust(3, '0')


def age_color(age):
    for end, color in ((180, '#cf2424'), (360, '#d44831'), (720, '#ad557b'),
                       (1440, '#aa6a2c'), (1800, '#727272')):
        if age < end: return color
    return None


@dataclass(frozen=True)
class Spot:
    call: str
    hz: int
    stamp: float
    source: str = ''
    reporter: str = ''
    comment: str = ''
    text: str = ''

    @property
    def band(self): return band_for(self.hz)


class SpotCache:
    def __init__(self): self.rows = {}

    def put(self, spot, now):
        from .parser import CALL_RE
        if (spot.band is None or not CALL_RE.fullmatch(spot.call) or
                not 0 <= now-spot.stamp < 1800): return False
        key = spot.call, spot.band
        old = self.rows.get(key)
        # Re-polling the same report or receiving an older one cannot renew it.
        if old and spot.stamp <= old.stamp: return False
        self.rows[key] = spot
        self.expire(now)
        if len(self.rows) > 5000:
            del self.rows[min(self.rows, key=lambda k: self.rows[k].stamp)]
        return True

    def expire(self, now):
        for key, spot in list(self.rows.items()):
            if now-spot.stamp >= 1800: del self.rows[key]


def parse_telnet(line, source, now=None):
    now = now or datetime.now(timezone.utc)
    m = re.search(r'DX de\s+(\S+):\s*(\d+(?:\.\d+)?)\s+(\S+)\s+(.*?)\s+(\d{4})Z\b', line)
    if not m: return None
    reporter, freq, call, comment, clock = m.groups()
    # A frequency inside a digital segment is not evidence of RTTY.
    if not re.search(r'\bRTTY\b', comment, re.I): return None
    if re.search(r'\b(?:FT8|FT4|CW|PSK\d*)\b', comment, re.I): return None
    try:
        stamp = now.replace(hour=int(clock[:2]), minute=int(clock[2:]), second=0, microsecond=0)
        if stamp-now > timedelta(minutes=2): stamp -= timedelta(days=1)
        hz = int(Decimal(freq)*1000)
    except (ValueError, InvalidOperation): return None
    return Spot(call.upper(), hz, stamp.timestamp(), source, reporter, comment)


def parse_jcluster(raw, source='J-Cluster'):
    if len(raw) > 2_000_000: raise ValueError('XML > 2 MB')
    if b'<!ENTITY' in raw.upper(): raise ValueError('XML ENTITY')
    encoding = re.search(br'encoding=[\'\"]([^\'\"]+)', raw[:160], re.I)
    codec = (encoding[1].decode('ascii') if encoding else 'utf-8-sig').lower()
    if codec in ('shift_jis', 'shift-jis', 'sjis'): codec = 'cp932'
    if codec not in ('cp932', 'utf-8', 'utf8', 'utf-8-sig'): raise ValueError(codec)
    root = ET.fromstring(raw.decode(codec))
    if root.tag != 'List': raise ValueError('XML: List')
    rows = []
    for row in root.findall('Spot')[:1000]:
        def value(path): return (row.findtext(path) or '').strip()
        if value('Mode').upper() != 'RTTY': continue
        try:
            zone = re.fullmatch(r'([+-])(\d{1,2}):(\d{2})', value('TimeZone') or '+9:00')
            if not zone: continue
            minutes = (int(zone[2])*60+int(zone[3])) * (1 if zone[1]=='+' else -1)
            stamp = datetime.fromisoformat(value('Date').replace('/', '-')+'T'+value('Time'))
            stamp = stamp.replace(tzinfo=timezone(timedelta(minutes=minutes))).timestamp()
            hz = int(Decimal(value('Freq').replace(',', ''))*1000)
            message = row.find('Message')
            rows.append(Spot(value('SpotStation/CallSign').upper(), hz, stamp, source,
                             value('ReportStation/CallSign'),
                             ''.join(message.itertext()) if message is not None else ''))
        except (ValueError, InvalidOperation, OverflowError): continue
    return rows
