from __future__ import annotations

import re
from dataclasses import dataclass, asdict, field
import hashlib
import os
import tempfile
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from pathlib import Path

from .timebase import UTC, in_zone
from .paths import ensure_runtime_dirs


@dataclass
class QSORecord:
    call: str
    rst_sent: str = "599"
    rst_rcvd: str = "599"
    sent: str = ""
    rcvd: str = ""
    station_callsign: str = ""
    freq_hz: int | None = None
    when_utc: datetime | None = None

    source_path: str = field(default='', repr=False, compare=False)
    source_index: int = field(default=-1, repr=False, compare=False)
    source_hash: str = field(default='', repr=False, compare=False)

    @property
    def band(self) -> str:
        return band_from_hz(self.freq_hz)

    @property
    def freq_mhz(self) -> str:
        if not self.freq_hz:
            return ""
        return f"{self.freq_hz / 1_000_000:.6f}".rstrip("0").rstrip(".")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["band"] = self.band
        d["freq_mhz"] = self.freq_mhz
        return d


BANDS = [
    (135_000, 138_000, "2190m"),
    (472_000, 479_000, "630m"),
    (1_800_000, 2_000_000, "160m"),
    (3_500_000, 4_000_000, "80m"),
    (7_000_000, 7_300_000, "40m"),
    (10_100_000, 10_150_000, "30m"),
    (14_000_000, 14_350_000, "20m"),
    (18_068_000, 18_168_000, "17m"),
    (21_000_000, 21_450_000, "15m"),
    (24_890_000, 24_990_000, "12m"),
    (28_000_000, 29_700_000, "10m"),
    (50_000_000, 54_000_000, "6m"),
    (144_000_000, 148_000_000, "2m"),
    (430_000_000, 450_000_000, "70cm"),
    (1_240_000_000, 1_300_000_000, "23cm"),
    (2_300_000_000, 2_450_000_000, "13cm"),
    (5_650_000_000, 5_850_000_000, "6cm"),
    (10_000_000_000, 10_500_000_000, "3cm"),
]


def band_from_hz(freq_hz: int | None) -> str:
    if not freq_hz:
        return ""
    for low, high, name in BANDS:
        if low <= freq_hz <= high:
            return name
    return ""


def _field(name: str, value: str) -> str:
    value = str(value)
    return f"<{name}:{len(value)}>{value}"


class ADIFLog:
    def __init__(self, log_dir: Path | None = None):
        self.log_dir = log_dir or ensure_runtime_dirs()["logdata"]
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def path_for(self, now_local: datetime | None = None) -> Path:
        now_local = in_zone(now_local, UTC) if now_local is not None else datetime.now(UTC)
        return self.log_dir / f"{now_local:%Y%m}.adi"

    def ensure_file(self, now_local: datetime | None = None) -> Path:
        path = self.path_for(now_local)
        if not path.exists() or path.stat().st_size == 0:
            header = (
                _field("ADIF_VER", "3.1.7") + " "
                + _field("PROGRAMID", "PSRTTY") + " "
                + _field("PROGRAMVERSION", "0.84") + " <EOH>\r\n"
            )
            path.write_text(header, encoding="utf-8")
        return path

    def append(self, qso: QSORecord, now_local: datetime | None = None) -> Path:
        when = qso.when_utc or (in_zone(now_local, UTC) if now_local is not None else datetime.now(UTC))
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        when = when.astimezone(timezone.utc)
        path = self.ensure_file(when)

        parts = [
            _field("CALL", qso.call.upper()),
            _field("QSO_DATE", when.strftime("%Y%m%d")),
            _field("TIME_ON", when.strftime("%H%M%S")),
            _field("MODE", "RTTY"),
            _field("RST_SENT", qso.rst_sent),
            _field("RST_RCVD", qso.rst_rcvd),
        ]
        if qso.band:
            parts.append(_field("BAND", qso.band))
        if qso.freq_mhz:
            parts.append(_field("FREQ", qso.freq_mhz))
        if qso.sent:
            parts.append(_field("STX_STRING", qso.sent))
            if qso.sent.isdigit():
                parts.append(_field("STX", str(int(qso.sent))))
        if qso.rcvd:
            parts.append(_field("SRX_STRING", qso.rcvd))
            if qso.rcvd.isdigit():
                parts.append(_field("SRX", str(int(qso.rcvd))))
        if qso.station_callsign:
            parts.append(_field("STATION_CALLSIGN", qso.station_callsign.upper()))
        record = " ".join(parts) + " <EOR>\r\n"
        with path.open("a", encoding="utf-8", newline="") as f:
            f.write(record)
        return path

    def load_recent(self, path: Path | None = None, limit: int | None = 50, *, record_order: bool = False) -> list[QSORecord]:
        paths = [Path(path)] if path is not None else sorted(self.log_dir.glob('*.adi'))
        out=[]; self.read_errors=[]
        for path in paths:
            if not path.exists(): continue
            try:
                raw=path.read_bytes(); digest=hashlib.sha256(raw).hexdigest()
                text=raw.decode('utf-8-sig'); spans=record_spans(text)
            except (OSError,UnicodeError,ValueError) as exc:
                self.read_errors.append(f'{path.name}: {exc}'); continue
            for index,(start,end,tokens) in enumerate(spans):
                fields={name:value for _,_,name,value in tokens}
                if not fields.get('CALL'): continue
                try: freq=int(Decimal(fields['FREQ'])*1000000) if fields.get('FREQ') else None
                except (ValueError,ArithmeticError): freq=None
                when=None
                try:
                    when=datetime.strptime(fields['QSO_DATE']+fields['TIME_ON'][:6].ljust(6,'0'),'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
                except (KeyError,ValueError): pass
                out.append(QSORecord(call=fields['CALL'],rst_sent=fields.get('RST_SENT','599'),rst_rcvd=fields.get('RST_RCVD','599'),
                    sent=fields.get('STX_STRING',fields.get('STX','')),rcvd=fields.get('SRX_STRING',fields.get('SRX','')),
                    station_callsign=fields.get('STATION_CALLSIGN',''),freq_hz=freq,when_utc=when,
                    source_path=str(path.resolve()),source_index=index,source_hash=digest))
        if not record_order:
            out.sort(key=lambda q:q.when_utc or datetime.min.replace(tzinfo=timezone.utc))
        return out[-limit:] if limit is not None else out

    def modify(self, original: QSORecord, replacement: QSORecord | None) -> Path:
        """Update one record; preserve all other bytes/unknown fields and back up first."""
        from PySide6.QtCore import QLockFile
        path=Path(original.source_path).resolve()
        if path.parent!=self.log_dir.resolve() or path.suffix.lower()!='.adi':
            raise ValueError('ログの保存先を確認できません。一覧を開き直してください。')
        lock=QLockFile(str(path)+'.lock')
        if not lock.tryLock(0): raise RuntimeError('ログを使用中です。しばらくして再試行してください。')
        try:
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=original.source_hash:
                raise RuntimeError('ログが変更されています。一覧を更新してから再操作してください。')
            bom=raw.startswith(b'\xef\xbb\xbf'); text=raw.decode('utf-8-sig')
            records=record_spans(text)
            if not 0<=original.source_index<len(records): raise ValueError('対象QSOが見つかりません。')
            start,end,tokens=records[original.source_index]
            if replacement is None: edited=text[:start]+text[end:]
            else:
                q=replacement
                if not q.call.strip() or q.when_utc is None: raise ValueError('CALLと日時を入力してください。')
                when=q.when_utc.astimezone(timezone.utc)
                updates={'CALL':q.call.strip().upper(),'QSO_DATE':when.strftime('%Y%m%d'),'TIME_ON':when.strftime('%H%M%S'),
                    'RST_SENT':q.rst_sent,'RST_RCVD':q.rst_rcvd,'FREQ':q.freq_mhz,'BAND':q.band,
                    'STX_STRING':q.sent,'SRX_STRING':q.rcvd,
                    'STX':str(int(q.sent)) if q.sent.isdigit() else '',
                    'SRX':str(int(q.rcvd)) if q.rcvd.isdigit() else ''}
                # An unchanged frequency must not remove a BAND-only imported record.
                if q.freq_hz==original.freq_hz: updates.pop('FREQ'); updates.pop('BAND')
                pieces=[]; cursor=start; used=set()
                for a,b,name,value in tokens:
                    if name not in updates: continue
                    pieces.append(text[cursor:a])
                    if name not in used and updates[name]: pieces.append(_field(name,updates[name]))
                    used.add(name); cursor=b
                pieces.append(text[cursor:end-5])
                pieces.extend(' '+_field(k,v) for k,v in updates.items() if k not in used and v)
                pieces.append('<EOR>')
                edited=text[:start]+''.join(pieces)+text[end:]
            if replacement is not None and re.fullmatch(r'\d{6}\.adi',path.name) and self.path_for(when).resolve()!=path:
                return self._move_month(path, raw, text[:start]+text[end:], ''.join(pieces), when)
            data=(b'\xef\xbb\xbf' if bom else b'')+edited.encode('utf-8')
            backup_dir=self.log_dir/'backups'; backup_dir.mkdir(exist_ok=True)
            backup=backup_dir/(path.name+'.'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]+'.bak')
            with backup.open('xb') as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            temp=None
            try:
                with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name,suffix='.tmp',delete=False) as stream:
                    temp=Path(stream.name); stream.write(data); stream.flush(); os.fsync(stream.fileno())
                if path.read_bytes()!=raw: raise RuntimeError('保存直前にログが変更されました。一覧を更新してください。')
                os.replace(temp,path)
            finally:
                if temp and temp.exists(): temp.unlink()
            return backup
        finally: lock.unlock()


    def _move_month(self, source, original, remaining, record, when):
        """Keep edited records in their UTC bucket; retain both originals first."""
        from PySide6.QtCore import QLockFile
        target=self.path_for(when).resolve()
        lock=QLockFile(str(target)+'.lock')
        if not lock.tryLock(0): raise RuntimeError('移動先ログを使用中です。再試行してください。')
        try:
            before=target.read_bytes() if target.exists() else None
            if before is not None:
                before.decode('utf-8-sig')  # Never append to an unreadable file.
            directory=self.log_dir/'backups';directory.mkdir(exist_ok=True)
            backup=directory/('month_move_'+uuid.uuid4().hex)
            backup.mkdir()
            for name, data in ((source.name,original),(target.name,before)):
                if data is not None:
                    with (backup/name).open('xb') as stream:
                        stream.write(data);stream.flush();os.fsync(stream.fileno())
            prefix=before if before is not None else b'<ADIF_VER:5>3.1.7 <EOH>\r\n'
            outgoing=prefix+b'\r\n'+record.encode('utf-8')+b'\r\n'
            incoming=(b'\xef\xbb\xbf' if original.startswith(b'\xef\xbb\xbf') else b'')+remaining.encode('utf-8')
            def write_atomic(path, data):
                temp=None
                try:
                    with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.'+path.name,suffix='.tmp',delete=False) as f:
                        temp=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
                    os.replace(temp,path)
                finally:
                    if temp and temp.exists():temp.unlink()
            if source.read_bytes()!=original or (target.read_bytes() if target.exists() else None)!=before:
                raise RuntimeError('ログが変更されています。一覧を更新してください。')
            write_atomic(target,outgoing)
            try:write_atomic(source,incoming)
            except Exception:
                # Restore destination if removing the source record fails.
                if before is None:target.unlink()
                else:write_atomic(target,before)
                raise
            return backup
        finally:lock.unlock()


def record_spans(text):
    """Length-aware ADIF tokenizer; tag-like text inside field values is not a tag."""
    tag=re.compile(r'<([A-Za-z0-9_]+)(?::(\d+)(?::[^>]*)?)?>')
    pos=0; start=0; tokens=[]; records=[]
    while True:
        match=tag.search(text,pos)
        if match is None: break
        name=match[1].upper(); pos=match.end()
        if match[2] is not None:
            end=pos+int(match[2])
            if end>len(text): raise ValueError('ADIFフィールドが途中で切れています。')
            tokens.append((match.start(),end,name,text[pos:end])); pos=end
        elif name=='EOH': start=pos; tokens=[]
        elif name=='EOR':
            records.append((start,pos,tokens)); start=pos; tokens=[]
    return records
