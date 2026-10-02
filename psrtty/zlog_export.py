"""ADIF mappings verified against zLog ZLOG3040 (3.0.4.0), UzLogQSO.pas.

Never put a compound exchange in the numeric CQZ field. STATE is retained
for other ADIF readers; zLog's importer currently ignores it. COMMENT keeps
both original exchanges for manual reconciliation after import.
"""
import re
from .adif import _field
from .i18n import tr

PROFILES = ('standard', 'zlog', 'zlog_jarl', 'zlog_cqww')


def extra_fields(qso, profile):
    if profile not in PROFILES:
        raise ValueError(tr('ADIF出力形式が不正です。'))
    if profile == 'standard':
        return ''
    for value in (qso.call, qso.sent, qso.rcvd, qso.station_callsign):
        if any(char in value for char in '\r\n<>'):
            raise ValueError(tr('zLog出力のCALL・交換番号に改行や < > は使用できません。'))
    fields = []
    if profile == 'zlog_jarl':
        if not re.fullmatch(r'[0-9]{1,2}', qso.rcvd):
            raise ValueError(tr('{call}: JARL WW RTTYの受信番号は年齢の1～2桁で指定してください。').format(call=qso.call))
        fields.append(_field('AGE', str(int(qso.rcvd))))
        fields.append(_field('CONTEST_ID', 'JARL-WW-RTTY'))
    elif profile == 'zlog_cqww':
        match = re.fullmatch(r'([0-9]{1,2})(?:\s+([A-Za-z]{2}))?', qso.rcvd.strip())
        if not match or not 1 <= int(match[1]) <= 40:
            raise ValueError(tr('{call}: CQ WW RTTYの受信番号は01～40、または「05 MA」のように指定してください。').format(call=qso.call))
        fields.append(_field('CQZ', str(int(match[1]))))
        if match[2]: fields.append(_field('STATE', match[2].upper()))
        fields.append(_field('CONTEST_ID', 'CQ-WW-RTTY'))
    # zLog imports COMMENT as its note. Keep literal leading zeroes here, since
    # numeric STX/SRX (and CQZ/AGE) do not preserve their display formatting.
    memo = f'PSRTTY SENT={qso.sent} RCVD={qso.rcvd} MYCALL={qso.station_callsign}'
    fields.append(_field('COMMENT', memo))
    return ' '.join(fields) + ' '
