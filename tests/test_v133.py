"""MAX wire contract from nextzlog/zmax 69b6acc; independent queues and UI.

The local TCP peer models MAX's approval gate, not the actual MAX executable.
"""
import copy
import csv
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QLabel, QDialogButtonBox
from psrtty import i18n
from psrtty.config import ConfigStore
from psrtty.zserver_link import ZServerLink, MAX_OPTIONS, DEFAULT_OPTIONS, serialize
from psrtty.ui.integration_dialog import ZLogSettingsDialog, IntegrationController
from tests.test_v114 import FakeZServer, qso, wait_for
from tests import test_ui_v02 as fixture


class ApprovalServer(FakeZServer):
    """CP932/CRLF; queue requests until approved, then PUTQSO and readback.

    Mirrors hub.receive/decide, protocol.qso_ids and wire field ordering.
    Responds in fragments and sends an unrelated chat notification first.
    """
    def __init__(self):
        self.approved=threading.Event()
        super().__init__()

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
                    if line.startswith('#ZLOG# PCNAME '):continue
                    while not self.approved.wait(.05):
                        if self.stop.is_set():return
                    if line.startswith('#ZLOG# PUTQSO '):
                        fields=next(csv.reader([line[14:]],delimiter='~'))
                        self.records[int(fields[24])//100]=serialize(fields);self.relay.append(line)
                        if self.drop:self.drop=False;return
                    elif line=='#ZLOG# GETQSOIDS':
                        ids=[next(csv.reader([v],delimiter='~'))[24] for v in self.records.values()]
                        answer='#ZLOG# PUTMESSAGE 接続を許可しました\r\n'
                        if ids:answer+='#ZLOG# QSOIDS '+' '.join(ids)+' \r\n'
                        answer+='#ZLOG# ENDQSOIDS\r\n'
                        data=answer.encode('cp932');s.sendall(data[:3]);s.sendall(data[3:])
                    elif line.startswith('#ZLOG# GETLOGQSOID '):
                        record=self.records.get(int(line[18:])//100)
                        answer=('#ZLOG# PUTLOGEX '+record+'\r\n' if record else '')+'#ZLOG# RENEW \r\n'
                        s.sendall(answer.encode('cp932'))
        except (OSError,ValueError):pass
        finally:s.close()


class MaxTCP133Tests(unittest.TestCase):
    def setUp(self):
        try:self.server=ApprovalServer()
        except PermissionError:self.skipTest('local TCP unavailable')
        self.addCleanup(self.server.close)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.link=ZServerLink(Path(self.tmp.name)/'max.json',name='zLog MAX',defaults=MAX_OPTIONS,approval_wait=60)
        self.addCleanup(self.link.close)
        self.options=dict(MAX_OPTIONS,enabled=True,port=self.server.port,operator='JH1HST')

    def test_approval_after_five_seconds_then_registration_and_readback(self):
        self.link.configure(self.options);self.link.enqueue(qso())
        wait_for(lambda:self.link.snapshot()[0]=='zmax.waiting')
        # Real elapsed time: the former five-second handshake must not reconnect.
        time.sleep(5.2)
        self.assertEqual(self.link.snapshot()[0],'zmax.waiting')
        self.assertEqual(self.server.records,{})
        self.server.approved.set();wait_for(lambda:self.link.snapshot()[3]==1)
        self.assertEqual(sum('PCNAME ' in c for c in self.server.commands),1)
        fields=next(csv.reader([next(iter(self.server.records.values()))],delimiter='~'))
        self.assertEqual(fields[2:7],['JA1ABC','25','05 MA','599','599'])
        self.assertEqual(fields[8:10],['4','4']);self.assertEqual(fields[16],'JH1HST')
        self.assertEqual(fields[25],'14085.0');self.assertEqual(fields[27],'PSRTTY-MAX')
        self.assertEqual(json.loads(self.link.path.read_text(encoding='utf-8'))['entries'],[])

    def test_disconnect_after_registration_and_restart_never_resends_confirmed_id(self):
        self.server.approved.set();self.server.drop=True
        self.link.configure(self.options);self.link.enqueue(qso())
        wait_for(lambda:len(self.server.records)==1)
        self.link.close()
        restored=ZServerLink(self.link.path,defaults=MAX_OPTIONS,approval_wait=60)
        self.addCleanup(restored.close);restored.configure(self.options)
        wait_for(lambda:restored.snapshot()[3]==1)
        self.assertEqual(len(self.server.relay),1)

    def test_disable_during_approval_wait_retains_outbox_and_stops_connection(self):
        self.link.configure(self.options);self.link.enqueue(qso())
        wait_for(lambda:self.link.snapshot()[0]=='zmax.waiting')
        self.link.configure(dict(self.options,enabled=False))
        wait_for(lambda:self.link.snapshot()[0]=='zlink.disabled')
        self.assertEqual(self.link.snapshot()[2],1);self.assertEqual(self.server.records,{})
        start=time.monotonic();self.link.close();self.assertLess(time.monotonic()-start,1)
        self.assertFalse(self.link.thread.is_alive())

    def test_approval_timeout_has_actionable_status_and_retains_pending(self):
        # Exercise the timeout branch without a 60-second test delay.
        with patch('psrtty.zserver_link.ZConnection.ids',side_effect=TimeoutError):
            self.link.configure(self.options);self.link.enqueue(qso())
            wait_for(lambda:self.link.snapshot()[0]=='zmax.approval_timeout')
            self.assertEqual(self.link.snapshot()[2],1)
            self.assertEqual(self.server.records,{})
            self.link.close()


class Config133Tests(unittest.TestCase):
    def test_existing_reiwa_settings_preserved_and_max_independent_default_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=ConfigStore(root/'s.json',root/'m.json')
            s.data['zlog']=dict(DEFAULT_OPTIONS,host='192.0.2.10',port=2323,pc_name='OLD')
            old=copy.deepcopy(s.data['zlog']);s.save()
            s=ConfigStore(root/'s.json',root/'m.json');self.assertEqual(s.data['zlog'],old)
            self.assertEqual(s.data['zlog_max'],MAX_OPTIONS)
            s.data['zlog_max']=dict(MAX_OPTIONS,host='192.0.2.11',port=2324,time_basis='JST');s.save()
            s=ConfigStore(root/'s.json',root/'m.json')
            self.assertEqual(s.data['zlog_max']['time_basis'],'JST');self.assertEqual(s.data['zlog'],old)

    def test_pending_queues_do_not_mix_and_corrupt_max_does_not_damage_reiwa(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=ZServerLink(root/'zserver-outbox.json')
            old.options=dict(DEFAULT_OPTIONS,enabled=True);old.enqueue(qso());saved=old.path.read_bytes()
            new=ZServerLink(root/'zlog-max-outbox.json',defaults=MAX_OPTIONS)
            new.options=dict(MAX_OPTIONS,enabled=True);new.enqueue(qso())
            self.assertEqual(new.entries[0]['fields'][27],'PSRTTY-MAX')
            self.assertEqual(old.path.read_bytes(),saved)
            new.path.write_text('broken',encoding='utf-8')
            self.assertTrue(ZServerLink(new.path,defaults=MAX_OPTIONS).load_error)
            self.assertEqual(ZServerLink(old.path).entries,old.entries)


class UI133Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp;tearDown=fixture.UITests.tearDown;pump=fixture.UITests.pump

    def test_menu_order_and_separate_settings_dialogs(self):
        # Use the QMenu wrappers retained by MainWindow. Re-fetching every menu
        # through temporary QAction.menu() wrappers can expose deleted objects
        # on Windows/PySide6; do not mask this with RuntimeError/skip handling.
        menu=next(m for m in self.window.top_level_menus
                  if m.title()==i18n.tr('ui.e73b7be6f0d5c286'))
        self.assertIn(menu.menuAction(),self.window.menuBar().actions())
        texts=[a.text() for a in menu.actions()]
        self.assertEqual(texts[texts.index(i18n.tr('zmax.title'))-1],i18n.tr('ui.17cea206eaeefd06'))
        c=self.window.integration;c.zlog_settings();c.zmax_settings()
        self.assertIsNot(c.zlog_dialog,c.zmax_dialog)
        self.assertEqual(c.zmax_dialog.pc_name.text(),'PSRTTY-MAX')
        self.assertEqual(c.zlink.path.name,'zserver-outbox.json')
        self.assertEqual(c.zmax_link.path.name,'zlog-max-outbox.json')

    def test_eight_languages_blue_notice_guide_and_buttons_at_small_size(self):
        try:
            for code in i18n.LANGUAGES:
                i18n.configure(code)
                d=ZLogSettingsDialog(self.window,target='zlog_max');d.resize(680,530);d.show();self.pump(.02)
                self.assertEqual(d.trial_notice.text(),i18n.tr('zmax.trial'))
                self.assertIn('#1565c0',d.trial_notice.styleSheet())
                self.assertIn('zLog MAX',i18n.tr('guide.8.body'))
                self.assertFalse(d.enabled.isChecked())
                self.assertGreater(d.scroll.verticalScrollBar().maximum(),0)
                buttons=d.findChild(QDialogButtonBox)
                self.assertLessEqual(buttons.geometry().bottom(),d.height())
                d.reject()
            i18n.configure('ja')
            self.assertEqual(i18n.tr('zmax.trial'),'現在試験対応中です、フィードバックをお願いします。')
            self.assertFalse(hasattr(ZLogSettingsDialog(self.window),'trial_notice'))
        finally:i18n.configure('ja')

    def test_save_cancel_rollback_and_prevent_same_endpoint_double_registration(self):
        d=ZLogSettingsDialog(self.window,target='zlog_max');before=copy.deepcopy(self.store.data)
        d.host.setText('changed');d.reject();self.assertEqual(self.store.data,before)
        with patch.object(self.store,'save',side_effect=OSError('full')),patch('psrtty.ui.integration_dialog.QMessageBox.warning'),patch.object(d.link,'configure') as configure:
            self.assertFalse(d.apply());configure.assert_not_called()
        self.assertEqual(self.store.data,before)
        self.store.data['zlog']['enabled']=True;d.host.setText('localhost');d.enabled.setChecked(True)
        with patch('psrtty.ui.integration_dialog.QMessageBox.warning') as warning:
            self.assertFalse(d.apply());self.assertEqual(warning.call_args.args[2],i18n.tr('zmax.duplicate_target'))
        d.enabled.setChecked(False);self.assertTrue(d.apply());self.assertTrue(self.store.data['zlog']['enabled'])

    def test_qso_max_transfer_only_after_adif_success_and_failure_does_not_block_reiwa(self):
        w=self.window;w.q_call.setText('JA1ABC');w.current_freq_hz=14085000
        with patch.object(w.integration.zmax_link,'enqueue') as max_send,patch.object(w.integration.zlink,'enqueue') as old_send:
            w._add_qso();max_send.assert_called_once();old_send.assert_called_once()
        w.q_call.setText('JA1XYZ')
        with patch.object(w.adif,'append',side_effect=OSError('full')),patch('psrtty.ui.main_window.QMessageBox.warning'),patch.object(w.integration.zmax_link,'enqueue') as send:
            w._add_qso();send.assert_not_called()
        with patch.object(w.integration.zlink,'enqueue',side_effect=OSError('full')),patch.object(w.integration.zmax_link,'enqueue') as send,patch('psrtty.ui.integration_dialog.QMessageBox.warning'):
            w.integration.record(qso());send.assert_called_once()

    def test_both_workers_closed_and_startup_conflict_does_not_connect_max(self):
        self.store.data['zlog']=dict(DEFAULT_OPTIONS,enabled=True)
        self.store.data['zlog_max']=dict(MAX_OPTIONS,enabled=True)
        with patch.object(ZServerLink,'configure') as configure:
            c=IntegrationController(self.window)
            self.assertEqual(configure.call_count,1)
            self.assertEqual(c.zmax_link.snapshot()[0],'zmax.duplicate_target');c.close()
        with patch.object(self.window.integration.zlink,'close') as old,patch.object(self.window.integration.zmax_link,'close') as new:
            self.window.integration.close();old.assert_called_once();new.assert_called_once()
