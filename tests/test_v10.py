from psrtty.timebase import JST
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGroupBox
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.civ import CIVController, CIVStatus, decode_bcd_frequency
from psrtty.yaesu import YaesuController
from psrtty.macros import normal_qso_template, jarl_ww_template
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.updater import confirm_restart, report_startup

class Protocol10Tests(unittest.TestCase):
    def test_icom_frequency_bcd_and_ack_required(self):
        c=CIVController(0x94); c.ser=Mock(); c.status.connected=True
        ack=bytes.fromhex('FE FE E0 94 FB FD')
        with patch.object(c,'read_transmitting',return_value=False), patch.object(c,'_read_response',return_value=ack):
            for hz,nbytes in [(14080120,5),(10450100120,6)]:
                self.assertTrue(c.set_frequency(hz)); frame=c.ser.write.call_args.args[0]
                self.assertEqual(frame[:5],bytes.fromhex('FE FE 94 E0 05'))
                self.assertEqual(len(frame[5:-1]),nbytes); self.assertEqual(decode_bcd_frequency(frame[5:-1]),hz)
        with patch.object(c,'read_transmitting',return_value=True):
            c.ser.reset_mock(); self.assertFalse(c.set_frequency(14080000)); c.ser.write.assert_not_called()
        with patch.object(c,'read_transmitting',return_value=False), patch.object(c,'_read_response',return_value=b''):
            self.assertFalse(c.set_frequency(14080000))
        c.cancel.set(); c.ser.reset_mock(); self.assertFalse(c.set_feature('NR',True)); c.ser.write.assert_not_called()
    def test_icom_features_validate_subcommand_and_unknown(self):
        c=CIVController(0x94); c.ser=Mock(); c.status.connected=True
        for name,sub in [('NB',0x22),('NR',0x40),('AN',0x41),('MN',0x48)]:
            with patch.object(c,'_read_response',return_value=bytes([254,254,224,148,22,sub,1,253])):
                self.assertIs(c.read_feature(name),True)
            with patch.object(c,'_read_response',return_value=bytes.fromhex('FE FE E0 94 FA FD')):
                self.assertIsNone(c.read_feature(name))
            with patch.object(c,'read_transmitting',return_value=False), patch.object(c,'_read_response',return_value=bytes.fromhex('FE FE E0 94 FB FD')):
                self.assertTrue(c.set_feature(name,False)); self.assertEqual(c.ser.write.call_args.args[0][4:-1],bytes([22,sub,0]))
    def test_cat_models_use_distinct_nb_nr_commands_and_restore_level(self):
        for model in ('FT-991 / FT-991A','FTX-1'):
            c=YaesuController(model); c.ser=Mock(); c.status.connected=True
            replies={'NB0':'NB01;','NR0':'NR01;','NL0':'NL0007;','RL0':'RL006;','BC0':'BC01;','BP00':'BP00001;'}
            with patch.object(c,'_query',side_effect=lambda cmd,prefix,**kw:replies[prefix]), patch.object(c,'read_transmitting',return_value=False):
                for name in ('NB','NR','AN','MN'): self.assertIs(c.read_feature(name),True); self.assertTrue(c.set_feature(name,True))
            sent=[x.args[0] for x in c.ser.write.call_args_list]
            self.assertIn(b'NL0007;' if model=='FTX-1' else b'NB01;',sent)
            self.assertIn(b'RL006;' if model=='FTX-1' else b'NR01;',sent)
            self.assertIn(b'BP00001;',sent)
            with patch.object(c,'_query',return_value='?;'): self.assertIsNone(c.read_feature('NB'))
    def test_cat_frequency_serialization_and_tx_guard(self):
        c=YaesuController('FTX-1'); c.ser=Mock(); c.status.connected=True
        with patch.object(c,'read_transmitting',return_value=False), patch.object(c,'read_frequency',return_value=14080010):
            self.assertTrue(c.set_frequency(14080010)); c.ser.write.assert_called_once_with(b'FA014080010;')
        with patch.object(c,'read_transmitting',return_value=None):
            c.ser.reset_mock(); self.assertFalse(c.set_feature('AN',True)); c.ser.write.assert_not_called()

class UI10Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp; tearDown=_Fixture.tearDown; pump=_Fixture.pump
    def connected(self):
        w=self.window; w.radio=CIVController(0x94); w.radio.status.connected=True
        self.store.data['radio'].update(model='IC-7300',civ_address='94'); w.current_freq_hz=14080000
        w._set_radio_controls(); return w
    def test_completion_records_date_only_after_success_auto_off(self):
        w=self.connected(); w.q_call.setText('JX1XXX'); w.rcvd.clear()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w._send_macro(3); self.assertFalse(w.q_datetime.manual.isChecked()); token=w.active_tx_id
            w._tx_finished(True,'OK',token); self.assertRegex(w.q_datetime.text(),r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$')
        w.adif.append.assert_not_called()
    def test_autolog_clears_date_once_and_preserves_utc(self):
        w=self.connected(); w.qsos=[]; w.q_call.setText('JX1XXX'); w.auto_log.setChecked(True)
        w.adif.append.return_value=Path('test.adi')
        w.q_datetime.setText('2026-09-24 17:14')
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w._send_macro(3); token=w.active_tx_id; w._tx_finished(True,'OK',token); w._tx_finished(True,'OK',token)
        w.adif.append.assert_called_once(); self.assertFalse(w.q_datetime.manual.isChecked()); self.assertEqual(w.q_call.text(),'')
        q=w.qsos[0]; self.assertEqual(q.when_utc,datetime(2026,9,24,17,14,tzinfo=JST).astimezone(timezone.utc))
        self.assertEqual(w.latest_table.item(0,1).text(),'2026-09-24 17:14'); self.assertEqual(w.latest_table.horizontalHeaderItem(1).text(),'日時（JST）')
    def test_stop_failure_offline_and_intervening_edit_never_stamp(self):
        w=self.connected(); w.q_call.setText('JX1XXX'); w.auto_log.setChecked(True)
        with patch.object(w.audio,'send_text',return_value=(True,'OK')), patch.object(w,'_add_qso') as add:
            w._send_macro(3); w._tx_finished(False,'error'); self.assertFalse(w.q_datetime.manual.isChecked())
            w._send_macro(3); w._stop_tx(); w._tx_finished(True,'OK'); self.assertFalse(w.q_datetime.manual.isChecked())
            w._send_macro(3); w.rcvd.setText('A'); w.rcvd.clear(); w._tx_finished(True,'OK'); self.assertFalse(w.q_datetime.manual.isChecked())
            add.assert_not_called()
    def test_log_validation_and_failed_save_keep_date(self):
        w=self.window; w.q_call.setText('JX1XXX'); w.q_datetime.setText('2026-02-30 17:14')
        with patch('psrtty.ui.main_window.QMessageBox.warning'):
            w._add_qso(); w.adif.append.assert_not_called(); self.assertEqual(w.q_datetime.text(),'2026-02-30 17:14')
            w.q_datetime.setText('2026-09-24 17:14'); w.adif.append.side_effect=OSError('disk')
            w._add_qso(); self.assertEqual(w.q_datetime.text(),'2026-09-24 17:14')
    def test_templates_completion_checkbox_and_custom_preservation(self):
        for template in (normal_qso_template(),jarl_ww_template()):
            self.assertEqual([i for i,m in enumerate(template) if m['completes_qso']],[3]); self.assertIn('TU 73',template[3]['text'])
        self.store.macros[0]['text']='CUSTOM TU'; self.store.macros[0]['completes_qso']=False
        d=MacroDialog(self.store); d.table.item(0,3).setCheckState(Qt.Checked); d._save()
        self.assertEqual(self.store.macros[0]['text'],'CUSTOM TU'); self.assertTrue(self.store.macros[0]['completes_qso'])
        w=self.connected(); w.q_call.setText('JX1XXX')
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w._send_macro(0); w._tx_finished(True,'OK'); self.assertTrue(w.q_datetime.text())
    def test_control_single_instance_recall_and_step(self):
        w=self.window; w.show(); w._show_control(); d=w.control_window; d.timer.stop()
        self.assertEqual(d.step.currentData(),10); self.assertFalse(d.dial.isEnabled()); d.step.setCurrentIndex(d.step.findData(1000))
        d.move(90000,90000); d.showMinimized(); w._show_control(); self.pump(.02)
        self.assertIs(w.control_window,d); self.assertEqual(d.step.currentData(),1000); self.assertFalse(d.isMinimized())
        self.assertTrue(w.screen().availableGeometry().intersects(d.frameGeometry()))
        self.assertTrue(any(b.title()=='デコード' for b in w.findChildren(QGroupBox)))
    def test_control_coalesces_latest_and_unknown_not_off(self):
        w=self.connected(); w._show_control(); d=w.control_window; d.timer.stop(); ctl=w.radio
        gate=threading.Event(); calls=[]; freq=[14080000]
        def tune(hz): calls.append(hz); gate.wait(.4); freq[0]=hz; return True
        with patch.object(ctl,'set_frequency',side_effect=tune),patch.object(ctl,'read_frequency',side_effect=lambda:freq[0]),patch.object(ctl,'read_feature',return_value=None):
            d.request_frequency(14080010); d.tick()
            for _ in range(50): d.nudge(1)
            self.assertEqual(d.pending,14080510); self.assertTrue(d.busy)
            gate.set(); self.pump(.05); d.tick(); self.pump(.07)
            self.assertEqual(calls,[14080010,14080510]); self.assertEqual(w.current_freq_hz,14080510)
            d.last_poll=0; d.tick(); self.pump(.05)
        self.assertEqual(d.buttons['NB'].text(),'NB —'); self.assertFalse(d.buttons['NB'].isEnabled())
        d.states={'NB':True,'NR':False,'AN':False,'MN':True}; d.refresh_enabled()
        self.assertEqual(d.buttons['NB'].text(),'NB ON'); d.notch.setCurrentIndex(1); self.assertEqual(d.buttons['NOTCH'].text(),'ON')
        w.active_tx_id=42; d.refresh_enabled(); d.request_frequency(14090000); self.assertIsNone(d.pending); self.assertFalse(d.dial.isEnabled())
    def test_wheel_drag_and_direct_frequency(self):
        w=self.connected(); w._show_control(); d=w.control_window; d.timer.stop()
        QTest.mousePress(d.dial,Qt.LeftButton,pos=QPoint(86,36)); QTest.mouseMove(d.dial,QPoint(136,86)); QTest.mouseRelease(d.dial,Qt.LeftButton,pos=QPoint(136,86))
        self.assertEqual(d.pending,14080060)
        event=QWheelEvent(QPointF(80,80),QPointF(80,80),QPoint(),QPoint(0,120),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        d.dial.wheelEvent(event); self.assertEqual(d.pending,14080050)
        d.entry.setText('14.080123'); d.apply_frequency(); self.assertEqual(d.pending,14080123)
        d.entry.setText('NaN'); d.apply_frequency(); self.assertEqual(d.pending,14080123)
    def test_test_connection_then_real_connection(self):
        w=self.window; w._settings(); d=w.settings_window; d.rig.setCurrentText('IC-7300')
        status=CIVStatus(True,'COM8',19200,14080000,'OK')
        with patch('psrtty.ui.settings_dialog.QMessageBox.information'),patch('psrtty.ui.settings_dialog.connect_configured',return_value=status):
            d._test_radio(); self.assertFalse(d.connect_button.isEnabled()); self.pump(.1)
        self.assertIn('［接続］',d.test_note.text()); self.assertFalse(w._connected())
        with patch.object(w,'connect_radio') as connect:
            d.connect_button.click(); self.pump(.06); connect.assert_called_once()
        self.assertEqual(self.store.data['radio']['model'],'IC-7300')

del _Fixture

class Restart10Tests(unittest.TestCase):
    def test_nonce_handshake_ignores_stale_receipt_and_detects_exit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'var').mkdir(); token='a'*32
            with patch.dict(os.environ,{'PSRTTY_RESTART_TOKEN':token}): report_startup(root)
            p=Mock(psrtty_restart_token=token); p.poll.return_value=None
            self.assertEqual(confirm_restart(root,p,.1)['token'],token)
            p.psrtty_restart_token='b'*32; p.poll.return_value=1
            with self.assertRaisesRegex(RuntimeError,'画面表示前'): confirm_restart(root,p,.1)
            p.poll.return_value=None
            with self.assertRaises(TimeoutError): confirm_restart(root,p,0)
