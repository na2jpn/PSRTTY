"""RTTY wire decoding and real TCP Z-Link framing/reconnect/outbox tests."""
import copy
import csv
import json
import socket
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
from PySide6.QtWidgets import QLabel
from psrtty import i18n
from psrtty.adif import QSORecord
from psrtty.config import ConfigStore, DEFAULT_CONFIG
from psrtty.live_tx import ToneEncoder, LiveText, start_live
from psrtty.audio_engine import AudioEngine
from psrtty.decoder import RTTYDecoder
from psrtty.zserver_link import (ZServerLink, ZConnection, DEFAULT_OPTIONS, LinkError,
                                qso_fields, serialize, same_record)
from psrtty.ui.integration_dialog import ZLogSettingsDialog
from tests import test_ui_v02 as fixture


def qso():
    return QSORecord('JA1ABC',sent='25',rcvd='05 MA',freq_hz=14085000,
                     when_utc=datetime(2026,10,10,1,2,3,tzinfo=timezone.utc))


def wait_for(condition, timeout=4):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if condition():return
        time.sleep(.01)
    raise AssertionError('condition not reached')


class FakeZServer:
    """Normal TCP subset from UCliForm: PUTQSO, IDs, GETLOGQSOID, relay."""
    def __init__(self, drop=False):
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0));self.sock.listen();self.sock.settimeout(.1)
        self.port=self.sock.getsockname()[1];self.stop=threading.Event();self.records={}
        self.commands=[];self.relay=[];self.drop=drop;self.clients=[];self.threads=[]
        self.thread=threading.Thread(target=self.accept,daemon=True);self.thread.start()
    def accept(self):
        while not self.stop.is_set():
            try:s,_=self.sock.accept()
            except socket.timeout:continue
            except OSError:return
            self.clients.append(s);t=threading.Thread(target=self.client,args=(s,),daemon=True)
            self.threads.append(t);t.start()
    def client(self,s):
        buf=bytearray();s.settimeout(.1)
        try:
            while not self.stop.is_set():
                try:data=s.recv(4096)
                except socket.timeout:continue
                if not data:return
                buf.extend(data)
                while b'\r\n' in buf:
                    raw,_,tail=buf.partition(b'\r\n');buf=bytearray(tail)
                    line=raw.decode('cp932');self.commands.append(line)
                    if line.startswith('#ZLOG# PUTQSO '):
                        payload=line[14:];fields=next(csv.reader([payload],delimiter='~'))
                        ident=int(fields[24]);self.records[ident//100]=payload;self.relay.append(line)
                        if self.drop:self.drop=False;s.close();return
                    elif line=='#ZLOG# GETQSOIDS':
                        ids=[next(csv.reader([v],delimiter='~'))[24] for v in self.records.values()]
                        answer=('#ZLOG# QSOIDS '+' '.join(ids)+'\r\n' if ids else '')+'#ZLOG# ENDQSOIDS\r\n'
                        b=answer.encode('cp932');s.sendall(b[:4]);s.sendall(b[4:])
                    elif line.startswith('#ZLOG# GETLOGQSOID '):
                        ident=int(line[18:]);value=self.records.get(ident//100)
                        answer=('#ZLOG# PUTLOGEX '+value+'\r\n' if value else '')+'#ZLOG# RENEW\r\n'
                        s.sendall(answer.encode('cp932'))
        except (OSError,ValueError):pass
        finally:s.close()
    def close(self):
        self.stop.set();self.sock.close()
        for s in self.clients:
            try:s.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(1)
        for t in self.threads:t.join(1)


class Protocol114Tests(unittest.TestCase):
    def test_wire_fields_match_zlog_with_cqww_state(self):
        f=qso_fields(qso(),DEFAULT_OPTIONS,1500012300)
        self.assertEqual(len(f),31);self.assertEqual(f[0],'ZLOGQSODATA:')
        self.assertEqual(f[2:7],['JA1ABC','25','05 MA','599','599'])
        self.assertEqual(f[8:10],['4','4']);self.assertEqual(f[24],'1500012300')
        self.assertEqual(f[25],'14085.0');self.assertEqual(f[27],'PSRTTY')
        delta=timedelta(days=float(f[1]));self.assertLess(abs(((datetime(1899,12,30)+delta)-datetime(2026,10,10,1,2,3)).total_seconds()),.001)
        self.assertTrue(same_record(f,serialize(f)))

    def test_jst_and_decimal_comma(self):
        utc=qso_fields(qso(),DEFAULT_OPTIONS,12300)
        jst=qso_fields(qso(),dict(DEFAULT_OPTIONS,time_basis='JST',decimal=','),12300)
        self.assertAlmostEqual(float(jst[1].replace(',','.'))-float(utc[1]),9/24)
        self.assertEqual(jst[25],'14085,0');self.assertTrue(same_record(jst,serialize(jst)))

    def test_quote_separator_and_non_ascii_roundtrip(self):
        q=qso();q.rcvd='05~MA';o=dict(DEFAULT_OPTIONS,operator='試験')
        f=qso_fields(q,o,12300);self.assertEqual(next(csv.reader([serialize(f)],delimiter='~')),f)
        self.assertIn('試験',serialize(f))

    def test_unknown_band_unencodable_and_oversize_rejected(self):
        q=qso();q.freq_hz=None
        with self.assertRaises(LinkError):qso_fields(q,DEFAULT_OPTIONS,12300)
        q=qso();q.rcvd='ไทย'
        with self.assertRaises(LinkError):qso_fields(q,DEFAULT_OPTIONS,12300)
        q.rcvd='A'*300
        with self.assertRaises(LinkError) as exc:qso_fields(q,DEFAULT_OPTIONS,12300)
        self.assertEqual(exc.exception.key,'zlink.too_long')

    def test_outbox_persists_and_setting_change_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'outbox.json';link=ZServerLink(p)
            link.options=dict(DEFAULT_OPTIONS,enabled=True);link.enqueue(qso());saved=p.read_bytes()
            restored=ZServerLink(p);self.assertEqual(restored.entries,link.entries)
            with self.assertRaises(LinkError):restored.check_options(dict(DEFAULT_OPTIONS,host='other'))
            self.assertEqual(p.read_bytes(),saved)
            disabled=restored.check_options(dict(DEFAULT_OPTIONS,enabled=False));self.assertFalse(disabled['enabled'])

    def test_corrupt_outbox_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'outbox.json';p.write_text('broken',encoding='utf-8');link=ZServerLink(p)
            link.options=dict(DEFAULT_OPTIONS,enabled=True)
            with self.assertRaises(LinkError):link.enqueue(qso())
            self.assertEqual(p.read_text(),'broken')

    def test_disk_failure_does_not_claim_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=ZServerLink(Path(tmp)/'outbox.json');link.options=dict(DEFAULT_OPTIONS,enabled=True)
            with patch.object(link,'_save',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):link.enqueue(qso())
            self.assertEqual(link.entries,[])

    def test_existing_id_collision_allocates_new_before_send(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=ZServerLink(Path(tmp)/'outbox.json');link.options=dict(DEFAULT_OPTIONS,enabled=True);link.enqueue(qso())
            old=int(link.entries[0]['fields'][24]);wire=Mock()
            wire.ids.side_effect=[{old//100:old},{}]*8
            with self.assertRaises(LinkError):link._deliver(wire)
            new=int(link.entries[0]['fields'][24]);self.assertNotEqual(old,new)
            self.assertTrue(link.entries[0]['attempted']);self.assertEqual(wire.send.call_count,1)

    def test_attempted_id_mismatch_is_held_without_resend(self):
        with tempfile.TemporaryDirectory() as tmp:
            link=ZServerLink(Path(tmp)/'outbox.json');link.options=dict(DEFAULT_OPTIONS,enabled=True);link.enqueue(qso())
            e=link.entries[0];e['attempted']=True;n=int(e['fields'][24]);other=e['fields'].copy();other[2]='JA9ZZZ'
            wire=Mock();wire.ids.return_value={n//100:n};wire.record.return_value=serialize(other)
            with self.assertRaises(LinkError) as exc:link._deliver(wire)
            self.assertEqual(exc.exception.key,'zlink.id_collision');wire.send.assert_not_called()
            self.assertEqual(len(link.entries),1)


class TCP114Tests(unittest.TestCase):
    def setUp(self):
        try:self.server=FakeZServer()
        except PermissionError:self.skipTest('local TCP unavailable')
        self.addCleanup(self.server.close);self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.link=ZServerLink(Path(self.tmp.name)/'queue.json');self.addCleanup(self.link.close)
        self.options=dict(DEFAULT_OPTIONS,enabled=True,port=self.server.port)

    def test_real_tcp_split_frames_server_registration_and_relay(self):
        self.link.configure(self.options);self.link.enqueue(qso())
        wait_for(lambda:self.link.snapshot()[3]==1)
        self.assertEqual(len(self.server.records),1);self.assertEqual(len(self.server.relay),1)
        self.assertEqual(self.link.snapshot()[2],0)
        self.assertEqual(json.loads(self.link.path.read_text())['entries'],[])
        self.assertTrue(any('PCNAME PSRTTY' in x for x in self.server.commands))

    def test_disconnect_after_putqso_then_readback_no_duplicate(self):
        self.server.drop=True;self.link.configure(self.options);self.link.enqueue(qso())
        wait_for(lambda:self.link.snapshot()[3]==1,timeout=8)
        self.assertGreaterEqual(sum('PCNAME ' in x for x in self.server.commands),2)
        self.assertEqual(len(self.server.relay),1);self.assertEqual(len(self.server.records),1)

    def test_restart_with_saved_attempted_record_confirms_without_resend(self):
        self.link.options=self.options;self.link.enqueue(qso());e=self.link.entries[0]
        e['attempted']=True;self.link._save();self.server.records[int(e['fields'][24])//100]=serialize(e['fields'])
        restored=ZServerLink(self.link.path);self.addCleanup(restored.close);restored.configure(self.options)
        wait_for(lambda:restored.snapshot()[3]==1);self.assertEqual(self.server.relay,[])


class Config114Tests(unittest.TestCase):
    def test_timeout_and_connection_options_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for seconds in range(1,10):
                store=ConfigStore(root/'settings.json',root/'macros.json')
                store.data['ui']['direct_idle_seconds']=seconds
                store.data['zlog']=dict(DEFAULT_OPTIONS,host='192.0.2.10',port=2323,time_basis='JST',decimal=',')
                store.save();restored=ConfigStore(root/'settings.json',root/'macros.json')
                self.assertEqual(restored.data['ui']['direct_idle_seconds'],seconds)
                self.assertEqual(restored.data['zlog']['host'],'192.0.2.10')
                self.assertEqual(restored.data['zlog']['time_basis'],'JST')
                self.assertEqual(restored.data['zlog']['decimal'],',')

    def test_invalid_saved_values_fall_back_without_enabling_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);store=ConfigStore(root/'settings.json',root/'macros.json')
            store.data['ui']['direct_idle_seconds']=99;store.data['zlog']={'enabled':True,'port':0}
            store.save();restored=ConfigStore(root/'settings.json',root/'macros.json')
            self.assertEqual(restored.data['ui']['direct_idle_seconds'],2)
            self.assertFalse(restored.data['zlog']['enabled'])


class Idle114Tests(unittest.TestCase):
    def test_digits_after_idle_ltrs_decode_as_digits(self):
        e=ToneEncoder(48000,45.45,2125,2295,False);chunks=[e.tone(True,3),e.code(31)]
        for ch in '599':chunks.append(e.char(ch))
        for _ in range(7):chunks.append(e.idle())
        for ch in '05':chunks.append(e.char(ch))
        chunks.append(e.tone(True,3));received=[]
        RTTYDecoder(on_char=received.append).feed(np.concatenate(chunks))
        self.assertEqual(''.join(received),'59905')

    def test_idle_has_both_tones_normal_and_reverse(self):
        for reverse in (False,True):
            e=ToneEncoder(48000,45.45,2125,2295,reverse);e.figures=True;wave=e.idle()
            self.assertFalse(e.figures)
            fft=np.abs(np.fft.rfft(wave));freq=np.fft.rfftfreq(len(wave),1/48000)
            for tone in (2125,2295):self.assertGreater(fft[np.abs(freq-tone)<15].max(),20)

    def test_each_timeout_pending_grace_and_idle_no_progress(self):
        for seconds in range(1,10):
            s=LiveText('',idle_timeout=seconds);self.assertFalse(s.idle_expired(10))
            self.assertFalse(s.idle_expired(10+seconds-.01));self.assertTrue(s.idle_expired(10+seconds))
            s=LiveText('',idle_timeout=seconds)
            s.idle_expired(10)
            with patch('psrtty.live_tx.time.monotonic',return_value=10+seconds-.4):s.update('A')
            self.assertFalse(s.idle_expired(10+seconds));self.assertIsNone(s.next_char(10+seconds))
            self.assertEqual(s.next_char(10+seconds+.11)[2],'A')
            self.assertEqual(s.records,[])


class UI114Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp;tearDown=fixture.UITests.tearDown;pump=fixture.UITests.pump
    def test_timeout_default_choices_session_and_saved_setting(self):
        self.window._open_direct();d=self.window.direct_window;d.auto.setChecked(False)
        self.assertEqual([d.idle_timeout.itemData(i) for i in range(9)],list(range(1,10)))
        self.assertEqual(d.idle_timeout.currentData(),2);d.idle_timeout.setCurrentIndex(8)
        self.assertEqual(self.store.data['ui']['direct_idle_seconds'],9)
        d.session=LiveText('');d.idle_timeout.setCurrentIndex(0);self.assertEqual(d.session.idle_timeout,1)
        d.session=None
        with patch.object(self.window,'_send_text',return_value=True) as send:
            d.editor.setPlainText('A');d.start();self.assertEqual(send.call_args.kwargs['live_session'].idle_timeout,1);d.finished()

    def test_zlog_settings_all_languages_and_cancel_does_not_change(self):
        before=copy.deepcopy(self.store.data['zlog'])
        try:
            for code in i18n.LANGUAGES:
                i18n.configure(code);d=ZLogSettingsDialog(self.window)
                self.assertEqual(d.host.text(),'127.0.0.1');self.assertEqual(d.port.value(),23)
                self.assertEqual(d.time_basis.currentData(),'UTC');self.assertFalse(d.enabled.isChecked())
                self.assertTrue(any('Z-Server' in label.text() for label in d.findChildren(QLabel)))
                self.assertNotIn('リアルタイム連動ではありません',i18n.tr('guide.8.body'))
                d.host.setText('different');d.reject();self.assertEqual(self.store.data['zlog'],before)
        finally:i18n.configure('ja')

    def test_qso_dispatches_zserver_after_adif_success_even_hamlog_off(self):
        w=self.window;w.q_call.setText('JA1ABC');w.current_freq_hz=14085000
        with patch.object(w.integration.zlink,'enqueue') as enqueue:
            w._add_qso();enqueue.assert_called_once();self.assertEqual(enqueue.call_args.args[0].call,'JA1ABC')
        with patch.object(w.integration.zlink,'enqueue') as enqueue,patch.object(w.adif,'append',side_effect=OSError('full')),patch('psrtty.ui.main_window.QMessageBox.warning'):
            w.q_call.setText('JA1XYZ');w._add_qso();enqueue.assert_not_called()

    def test_zlog_save_failure_rolls_back_without_connecting(self):
        d=ZLogSettingsDialog(self.window);previous=copy.deepcopy(self.store.data['zlog']);d.host.setText('localhost')
        with patch.object(self.store,'save',side_effect=OSError('full')),patch('psrtty.ui.integration_dialog.QMessageBox.warning'),patch.object(self.window.integration.zlink,'configure') as configure:
            self.assertFalse(d.apply());configure.assert_not_called()
        self.assertEqual(self.store.data['zlog'],previous);d.close()
