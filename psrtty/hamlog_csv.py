"""Turbo HAMLOG V5: 15 fields, CP932, no header, explicit JST times."""
import csv
import io
import os
import tempfile
from datetime import timezone
from pathlib import Path
from .timebase import JST


FIELDS = ('Call', 'Date', 'Time', 'RSTs', 'RSTr', 'Freq', 'Mode', 'Code',
          'GL', 'QSL', 'Name', 'QTH', 'Remarks1', 'Remarks2', 'DX')


def hamlog_row(qso, include_station=True):
    if qso.when_utc is None or not qso.call.strip() or not qso.freq_hz:
        raise ValueError('HAMLOG出力にはCALL・日時・周波数が必要です。')
    when = qso.when_utc
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    when = when.astimezone(JST)
    # Retain exchanges as text; do not infer a JCC/JCG from contest numbers.
    remarks = ' '.join(f'{key}:{value}' for key, value in (('SENT', qso.sent), ('RCVD', qso.rcvd)) if value)
    station = f'MYCALL:{qso.station_callsign}' if include_station and qso.station_callsign else ''
    row = [qso.call.upper(), when.strftime('%y/%m/%d'), when.strftime('%H:%MJ'),
           qso.rst_sent, qso.rst_rcvd, qso.freq_mhz, 'RTTY', '', '', '', '', '', remarks, station, '']
    for label, value in zip(FIELDS, row):
        if '\r' in value or '\n' in value:
            raise ValueError(f'{qso.call}: {label}に改行があります。')
        try:
            encoded = value.encode('cp932')
        except UnicodeEncodeError as exc:
            raise ValueError(f'{qso.call}: {label}にHAMLOGで扱えない文字があります。') from exc
        if label.startswith('Remarks') and len(encoded) > 56:
            raise ValueError(f'{qso.call}: {label}が56バイトを超えています。元ログで内容を確認してください。')
    return row


def export_hamlog(path, records, protected=(), include_station=True):
    path = Path(path)
    if path.suffix.lower() != '.csv':
        raise ValueError('CSVファイル（.csv）を選んでください。')
    if path.resolve() in {Path(p).resolve() for p in protected if p}:
        raise ValueError('元のログには上書きできません。')
    if not records:
        raise ValueError('交信を1件以上選択してください。')
    stream = io.StringIO(newline='')
    writer = csv.writer(stream, quoting=csv.QUOTE_ALL, lineterminator='\r\n')
    writer.writerows(hamlog_row(qso, include_station) for qso in records)
    content = stream.getvalue().encode('cp932')
    temp = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.psrtty-hamlog-', suffix='.tmp', delete=False) as output:
            temp = Path(output.name); output.write(content); output.flush(); os.fsync(output.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
