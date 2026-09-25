"""Cabrillo 3.0 output. Never modifies source ADIF. See CABRILLO_SPEC.md."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import calendar
import os
import re
import string
import tempfile
import textwrap
from . import __version__
from .parser import CQWW_QTH

PROFILES = {'generic':'汎用Cabrillo形式', 'jarl':'JARL World Wide RTTY用Cabrillo形式', 'cqww':'CQ WW RTTY DX用Cabrillo形式'}
CONTESTS = {'jarl':'JARL-WW-RTTY','cqww':'CQ-WW-RTTY'}
HF_BANDS = ['ALL','80M','40M','20M','15M','10M']
BANDS = ['ALL','160M','80M','40M','20M','15M','10M','6M','4M','2M','222','432','902','1.2G','2.3G','3.4G','5.7G','10G']
DEFAULT_LAYOUT = '{FREQ} {MODE} {DATE} {TIME} {MYCALL} {RSTS} {SENT} {HISCALL} {RSTR} {RCVD}'
TOKENS = {'FREQ','MODE','DATE','TIME','MYCALL','HISCALL','RSTS','RSTR','SENT','RCVD','TXID'}
JST = timezone(timedelta(hours=9))


def period(profile, year):
    month = 10 if profile == 'jarl' else 9
    days = [d for d in range(1,calendar.monthrange(year,month)[1]+1) if datetime(year,month,d).weekday()==5]
    day = days[2] if profile=='jarl' else next(d for d in reversed(days) if d+1<=calendar.monthrange(year,month)[1])
    start = datetime(year,month,day,tzinfo=timezone.utc)
    return start, start+timedelta(days=2,seconds=-1)


def ascii_line(value, label):
    value = str(value).strip()
    if any(ord(c)<32 or ord(c)>126 for c in value):
        raise ValueError(f'{label}：半角英数字・記号で入力してください（改行不可）。')
    return value


def call_value(value, label):
    value=ascii_line(value,label).upper()
    if not re.fullmatch(r'[A-Z0-9]+(?:/[A-Z0-9]+)*',value) or not re.search('[A-Z]',value) or not re.search('[0-9]',value):
        raise ValueError(f'{label}：コールサインを入力してください。')
    return value


def needs_qth(call):
    # Explicit portable prefix takes precedence. Complex exceptions can supply DX explicitly.
    parts=call.upper().split('/')
    prefix=parts[0]
    if len(parts)>1 and len(parts[-1])>1 and parts[-1] not in ('P','M','MM','AM','QRP'):
        prefix=parts[-1] if len(parts[-1])<len(parts[0]) else parts[0]
    if re.match(r'(?:KL|AL|NL|WL)[0-9]|(?:KH|AH|NH|WH)[0-9]|(?:KP|NP|WP)[0-9]',prefix):return False
    return bool(re.match(r'(?:[KNW][0-9]|[KNW][A-Z][0-9]|A[A-L][0-9]|V[AEYO][0-9])',prefix))


def cq_exchange(value, call, label):
    parts=ascii_line(value,label).upper().split()
    if not parts or not re.fullmatch(r'\d{1,2}',parts[0]) or not 1<=int(parts[0])<=40:
        raise ValueError(f'{label}：CQゾーン1～40を入力してください。')
    if len(parts)>2:raise ValueError(f'{label}：ゾーンと州・地域略号を入力してください（例：05 MA）。')
    qth=parts[1] if len(parts)==2 else ''
    if not qth:
        if needs_qth(call):raise ValueError(f'{label}：米国・カナダ局の州・地域略号がありません（例：05 MA）。運用地が対象外ならDXを明示してください。')
        qth='DX'
    if qth not in CQWW_QTH and qth!='DX':raise ValueError(f'{label}：州・地域略号「{qth}」を確認してください。')
    return f'{int(parts[0]):02d}',qth


def frequency(freq_hz):
    if not freq_hz or freq_hz<=0:raise ValueError('周波数がありません。')
    if freq_hz<30_000_000:return str(freq_hz//1000)
    for low,high,token in [(50e6,54e6,'50'),(70e6,71e6,'70'),(144e6,148e6,'144'),(222e6,225e6,'222'),(420e6,450e6,'432'),(902e6,928e6,'902'),(1240e6,1300e6,'1.2G'),(2300e6,2450e6,'2.3G'),(3300e6,3500e6,'3.4G'),(5650e6,5850e6,'5.7G'),(10000e6,10500e6,'10G')]:
        if low<=freq_hz<=high:return token
    raise ValueError('Cabrilloの周波数表記に対応していない帯域です。')


def validate_layout(layout):
    fields=[]
    try:
        for literal,name,spec,conversion in string.Formatter().parse(layout):
            if name is not None:
                if name not in TOKENS or spec or conversion:raise ValueError('使用できない置換項目です。')
                fields.append(name)
    except ValueError as exc:raise ValueError(f'汎用QSOの並び：{exc}')
    required=TOKENS-{'TXID'}
    if not required.issubset(fields):raise ValueError('汎用QSOの並び：周波数・モード・日時・両局CALL/RST/交換番号の全項目が必要です。')
    ascii_line(layout,'汎用QSOの並び')
    if any(fields.count(x)>1 for x in fields):raise ValueError('汎用QSOの並び：同じ項目を重複指定しないでください。')


def build_cabrillo(profile, info, entries):
    """entries: [(QSORecord, {'txid': '', 'xqso': False}), ...]."""
    errors=[];warnings=[];lines=['START-OF-LOG: 3.0'];clean={}
    for key,value in info.items():
        if key in ('ADDRESS','SOAPBOX','OFFTIME'):continue
        try:clean[key]=ascii_line(value,key)
        except ValueError as exc:errors.append(str(exc))
    contest=CONTESTS.get(profile,clean.get('CONTEST','').upper())
    if not re.fullmatch('[A-Z0-9-]{1,32}',contest):errors.append('CONTEST：大会識別名を半角英大文字・数字・ハイフンで入力してください。')
    try:mycall=call_value(clean.get('CALLSIGN',''),'自局CALL')
    except ValueError as exc:errors.append(str(exc));mycall=''
    op=clean.get('CATEGORY-OPERATOR','');power=clean.get('CATEGORY-POWER','');band=clean.get('CATEGORY-BAND','');tx=clean.get('CATEGORY-TRANSMITTER','');overlay=clean.get('CATEGORY-OVERLAY','');station=clean.get('CATEGORY-STATION','')
    for key,choices in [('CATEGORY-OPERATOR',['SINGLE-OP','MULTI-OP','CHECKLOG']),('CATEGORY-POWER',['HIGH','LOW','QRP']),('CATEGORY-BAND',HF_BANDS if profile!='generic' else BANDS)]:
        if clean.get(key) not in choices:errors.append(f'{key}：選択してください。')
    if clean.get('CATEGORY-ASSISTED') not in ('','ASSISTED','NON-ASSISTED'):errors.append('CATEGORY-ASSISTED：選択値を確認してください。')
    if op=='MULTI-OP' and not clean.get('OPERATORS'):errors.append('OPERATORS：マルチオペの全運用者を入力してください。')
    if op=='MULTI-OP' and not tx:errors.append('CATEGORY-TRANSMITTER：マルチオペの送信機区分を指定してください。')
    if profile=='jarl':
        if band!='ALL':errors.append('JARL：参加部門はオールバンドです。')
        if op=='MULTI-OP' and power=='QRP':errors.append('JARL：マルチオペQRP部門はありません。')
        if overlay not in ('','YOUTH') or (overlay and op!='SINGLE-OP'):errors.append('JARL：YOUTHはシングルオペのみです。')
        if info.get('JARL-PORTABLE')=='YES' and not clean.get('LOCATION'):errors.append('LOCATION：移動運用地の都道府県を入力してください。')
    if profile=='cqww':
        if not clean.get('LOCATION'):errors.append('LOCATION：米国・カナダは州/地域、その他はDXを入力してください。')
        if op=='MULTI-OP':
            if band!='ALL':errors.append('CQ WW：マルチオペはALLを選択してください。')
            if tx not in ('ONE','TWO','UNLIMITED'):errors.append('CQ WW：送信機区分を選択してください。')
            if power=='QRP' or (tx in ('TWO','UNLIMITED') and power!='HIGH'):errors.append('CQ WW：MULTI-ONEはHIGH/LOW、MULTI-TWO/MULTI-MULTIはHIGHです。')
        if overlay and op!='SINGLE-OP':errors.append('CQ WW：オーバーレイはシングルオペのみです。')
        if overlay=='CLASSIC' and clean.get('CATEGORY-ASSISTED')=='ASSISTED':errors.append('CLASSICはNON-ASSISTEDを選択してください。')
        if overlay in ('YOUTH','ROOKIE'):
            key='BIRTHDATE' if overlay=='YOUTH' else 'LICENSE-DATE'
            try:datetime.strptime(clean.get(key,''),'%Y-%m-%d')
            except ValueError:errors.append(f'{key}：YYYY-MM-DDで入力してください。')
        if station=='DISTRIBUTED' and op!='MULTI-OP':errors.append('DISTRIBUTEDはマルチオペで指定してください。')
    if clean.get('CLAIMED-SCORE') and not re.fullmatch('[0-9]+',clean['CLAIMED-SCORE']):errors.append('CLAIMED-SCORE：整数を入力するか空欄にしてください。')
    if clean.get('EMAIL') and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',clean['EMAIL']):errors.append('EMAIL：メールアドレスを確認してください。')
    if len(clean.get('NAME',''))>75:errors.append('NAME：75文字以内で入力してください。')
    for key in ('NAME','EMAIL','ADDRESS'):
        if not info.get(key,'').strip():warnings.append(f'{key}は未入力です。提出先で必要な場合は入力してください。')
    if profile=='cqww' and info.get('ADDRESS','').strip() and not clean.get('ADDRESS-COUNTRY'):warnings.append('米国外の郵送先にはADDRESS-COUNTRYが必要です。')
    if profile=='generic':
        try:validate_layout(info.get('LAYOUT',DEFAULT_LAYOUT))
        except ValueError as exc:errors.append(str(exc))
        warnings.append('汎用形式：大会固有の交換番号の並び・必須項目を提出先の指定と照合してください。')
    lines += [f'CONTEST: {contest}',f'CALLSIGN: {mycall}',f'CREATED-BY: PSRTTY {__version__}']
    keys=['LOCATION','CATEGORY-OPERATOR','CATEGORY-BAND','CATEGORY-POWER','CATEGORY-ASSISTED','CATEGORY-STATION','CATEGORY-TRANSMITTER','CATEGORY-OVERLAY','CATEGORY-TIME','CLAIMED-SCORE','CLUB','EMAIL','NAME','ADDRESS-CITY','ADDRESS-STATE-PROVINCE','ADDRESS-POSTALCODE','ADDRESS-COUNTRY','GRID-LOCATOR','CERTIFICATE']
    lines.append('CATEGORY-MODE: RTTY')
    for key in keys:
        if clean.get(key):lines.append(f'{key}: {clean[key]}')
    for line in textwrap.wrap(clean.get('OPERATORS',''),width=75,break_long_words=False):lines.append('OPERATORS: '+line)
    address=info.get('ADDRESS','').splitlines()
    if len(address)>6:errors.append('ADDRESS：6行以内で入力してください。')
    for line in address:
        try:
            line=ascii_line(line,'ADDRESS')
            if len(line)>45:raise ValueError('ADDRESS：1行45文字以内で入力してください。')
            if line:lines.append('ADDRESS: '+line)
        except ValueError as exc:errors.append(str(exc))
    for line in info.get('SOAPBOX','').splitlines():
        try:
            line=ascii_line(line,'SOAPBOX')
            lines.extend('SOAPBOX: '+part for part in textwrap.wrap(line,75))
        except ValueError as exc:errors.append(str(exc))
    if profile=='cqww' and overlay in ('YOUTH','ROOKIE'):
        key='BIRTHDATE' if overlay=='YOUTH' else 'LICENSE-DATE'
        lines.append(f'SOAPBOX: {key} {clean.get(key, "")}')
    for line in info.get('OFFTIME','').splitlines():
        try:
            pieces=line.split()
            if len(pieces)!=4:raise ValueError()
            a=datetime.strptime(' '.join(pieces[:2]),'%Y-%m-%d %H%M');b=datetime.strptime(' '.join(pieces[2:]),'%Y-%m-%d %H%M')
            if a>b:raise ValueError()
            lines.append('OFFTIME: '+' '.join(pieces))
        except ValueError:errors.append('OFFTIME：YYYY-MM-DD HHMM YYYY-MM-DD HHMM（UTC）の順で入力してください。')
    if not entries:errors.append('出力するQSOを1件以上選択してください。')
    seen=set()
    for i,(q,extra) in enumerate(entries,1):
        try:
            his=call_value(q.call,'相手CALL');freq=frequency(q.freq_hz)
            if q.when_utc is None or q.when_utc.tzinfo is None:raise ValueError('日時を指定してください。')
            when=q.when_utc.astimezone(timezone.utc)
            if q.station_callsign and q.station_callsign.upper()!=mycall:raise ValueError('記録の自局CALLと提出CALLが異なります。②で対象/自局CALLを確認してください。')
            if profile!='generic' and q.band.upper() not in HF_BANDS:raise ValueError('対象は3.5/7/14/21/28MHzです。')
            for label,value in [('RST-S',q.rst_sent),('RST-R',q.rst_rcvd)]:
                if not re.fullmatch('[1-5][1-9][1-9]',value):raise ValueError(f'{label}は3桁のRSTを入力してください。')
            sent=ascii_line(q.sent,'SENT').upper();rcvd=ascii_line(q.rcvd,'RCVD').upper()
            if not sent or not rcvd:raise ValueError('SENT・RCVDを入力してください。')
            if profile=='cqww':
                sz,sq=cq_exchange(sent,mycall,'SENT');rz,rq=cq_exchange(rcvd,his,'RCVD');sent=f'{sz} {sq:<4}';rcvd=f'{rz} {rq:<4}'
            elif profile=='jarl':
                for label,value in [('SENT',sent),('RCVD',rcvd)]:
                    if not re.fullmatch('[0-9]{1,3}',value):raise ValueError(f'{label}：年齢または01（00/99も可）を数字で入力してください。')
                sent=sent.zfill(2);rcvd=rcvd.zfill(2)
            txid=str(extra.get('txid','')).strip()
            if txid and txid not in ('0','1'):raise ValueError('TX番号は0または1です。')
            if profile=='cqww' and op=='MULTI-OP' and tx in ('ONE','TWO') and not txid:raise ValueError('MULTI-ONE/TWOのTX番号（0/1）を②で入力してください。')
            if profile=='generic':
                values=dict(FREQ=freq,MODE='RY',DATE=when.strftime('%Y-%m-%d'),TIME=when.strftime('%H%M'),MYCALL=mycall,HISCALL=his,RSTS=q.rst_sent,RSTR=q.rst_rcvd,SENT=sent,RCVD=rcvd,TXID=txid)
                validate_layout(info.get('LAYOUT',DEFAULT_LAYOUT));body=info.get('LAYOUT',DEFAULT_LAYOUT).format_map(values).rstrip()
                if '{TXID}' in info.get('LAYOUT','') and not txid:raise ValueError('汎用の並びにTXIDがあるためTX番号を入力してください。')
            else:
                body=f'{freq:>5} RY {when:%Y-%m-%d %H%M} {mycall:<13} {q.rst_sent} {sent:<6} {his:<13} {q.rst_rcvd} {rcvd:<6}'
                if txid:body+=' '+txid
            lines.append(('X-QSO: ' if extra.get('xqso') else 'QSO: ')+body.rstrip())
            duplicate=(his,q.band)
            if duplicate in seen:warnings.append(f'QSO {i} {his}：同一バンドの交信が複数あります（自動削除しません）。')
            seen.add(duplicate)
        except (ValueError,KeyError) as exc:errors.append(f'QSO {i} [{q.call}]：{exc}')
    lines.append('END-OF-LOG:')
    if errors:return '',errors,warnings
    return '\r\n'.join(lines)+'\r\n',[],warnings


def save_cabrillo(path: Path, text: str, protected=()):
    path=Path(path)
    if path.suffix.lower() in ('.adi','.adif','.zip','.bak') or path.name.endswith('_all.txt') or path.resolve() in {Path(p).resolve() for p in protected}:
        raise ValueError('元ログやバックアップへの上書きはできません。.logなど別名で保存してください。')
    data=text.encode('ascii')
    temp=None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.psrtty-cabrillo-',suffix='.tmp',delete=False) as f:
            temp=Path(f.name);f.write(data);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if temp is not None and temp.exists():temp.unlink()
