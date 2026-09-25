import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import copy
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from tests.dialog_guard import DialogGuard
from tests.shutdown_support import close_and_wait
from psrtty.config import DEFAULT_CONFIG, DEFAULT_MACROS
from psrtty.civ import CIVController, CIVStatus
from psrtty.ui.main_window import MainWindow
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.ui.settings_dialog import SettingsDialog

class UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.dialog_guard=DialogGuard()
        self.dialog_guard.start()
        self.addCleanup(self.dialog_guard.stop)
        self.tmp=tempfile.TemporaryDirectory(); root=Path(self.tmp.name)
        self.paths={'root':root, **{name:root/name for name in ('config','logdata','var')}}
        for p in self.paths.values(): p.mkdir(exist_ok=True)
        self.store=Mock(data=copy.deepcopy(DEFAULT_CONFIG), macros=copy.deepcopy(DEFAULT_MACROS))
        self.patches=[patch('psrtty.ui.main_window.ensure_runtime_dirs',return_value=self.paths),
            patch('psrtty.ui.main_window.ConfigStore',return_value=self.store),
            patch('psrtty.ui.main_window.TranscriptLogger'),patch('psrtty.ui.main_window.ADIFLog'),
            patch('psrtty.ui.settings_dialog.AudioEngine.devices',return_value=[]),
            patch('psrtty.ui.settings_dialog.CIVController.available_ports',return_value=[]),
            patch('psrtty.ui.settings_dialog.CIVController.port_choices',return_value=[])]
        for p in self.patches: p.start()
        self.window=MainWindow()
    def tearDown(self):
        close_and_wait(self.window, self.app)
        for p in reversed(self.patches): p.stop()
        self.tmp.cleanup()
        self.assertEqual(self.dialog_guard.events, [], "予期しないダイアログ（応答待ちを抑止）:\n" + "\n".join(self.dialog_guard.events))
    def pump(self,seconds):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            self.app.processEvents(); time.sleep(.005)
    def test_nine_buttons_shortcuts_and_unconnected_guards(self):
        w=self.window
        self.assertEqual(len(w.macro_buttons),9)
        self.assertEqual([s.key().toString() for s in w.shortcuts[:9]],[f'F{i}' for i in range(1,10)])
        self.assertTrue(all(not b.isEnabled() for b in w.macro_buttons))
        self.assertFalse(w.send_button.isEnabled())
        with patch.object(w.audio,'send_text') as send:
            w._send_macro(0); w._send_text('TEST'); self.assertFalse(w._ptt_on()); send.assert_not_called()
    def test_macro_apply_edit_and_cancel(self):
        dlg=MacroDialog(self.store); dlg._apply_template()
        self.assertEqual(dlg.table.rowCount(),9); self.assertEqual(dlg.table.item(7,2).text(),'KKK')
        dlg.table.item(8,2).setText('EDITABLE'); dlg._save()
        self.assertEqual(self.store.macros[8]['text'],'EDITABLE')
        before=copy.deepcopy(self.store.macros); dlg=MacroDialog(self.store); dlg._apply_template(); dlg.reject()
        self.assertEqual(self.store.macros,before)
    def test_rig_unselected_manual_address_and_tabs(self):
        dlg=SettingsDialog(self.store)
        self.assertEqual(dlg.rig.currentText(),'選択してください'); self.assertEqual(dlg.civ_addr.currentText(),'')
        self.assertEqual([dlg.tabs.tabText(i) for i in range(4)],['基本設定','無線機','Audio','高度な設定'])
        dlg.rig.setCurrentText('IC-705'); self.assertEqual(dlg.civ_addr.currentText(),'A4')
        dlg.civ_addr.setCurrentText('90'); dlg._save(); self.assertEqual(self.store.data['radio']['civ_address'],'90')
    def test_unselected_settings_can_save_audio(self):
        dlg=SettingsDialog(self.store); dlg.tx_gain.setValue(20); dlg._save()
        self.assertEqual(self.store.data['radio']['model'],''); self.assertEqual(self.store.data['audio']['tx_gain'],.2)
    def test_help_and_settings_nonmodal(self):
        w=self.window; w.show(); w._guide_initial(); w._guide_ft8(); w._guide_tuning(); w._settings(); self.pump(.05)
        self.assertEqual(len(w.help_windows),3)
        self.assertTrue(all(x.windowModality()==Qt.NonModal and x.isVisible() for x in w.help_windows.values()))
        self.assertFalse(w.settings_window.isModal()); self.assertIsNone(self.app.activeModalWidget())
        w.my_call.setText('JH1HST'); self.assertEqual(w.my_call.text(),'JH1HST')
    def test_connect_failure_ui_keeps_ticking(self):
        w=self.window; self.store.data['radio'].update(model='IC-705',civ_address='A4')
        def slow(ctl,*args): time.sleep(.18); return CIVStatus(False,message='timeout')
        ticks=[]; timer=QTimer(); timer.setInterval(5); timer.timeout.connect(lambda:ticks.append(1)); timer.start()
        with patch('psrtty.ui.main_window.connect_configured',side_effect=slow):
            start=time.monotonic(); w.connect_radio(); self.assertLess(time.monotonic()-start,.1)
            self.assertTrue(w.connecting); self.pump(.3)
        timer.stop(); self.assertGreater(len(ticks),10); self.assertFalse(w.connecting)
        self.assertTrue(w.connect_action.isEnabled()); self.assertFalse(w.send_button.isEnabled())
    def test_success_and_disconnect(self):
        w=self.window; self.store.data['radio'].update(model='IC-705',civ_address='A4')
        def success(ctl,*args): ctl.status=CIVStatus(True,'COM1',19200,14085000); return ctl.status
        with patch('psrtty.ui.main_window.connect_configured',side_effect=success), patch.object(w.audio,'start_input',return_value=(True,'OK')):
            w.connect_radio(); self.pump(.1)
        self.assertTrue(w.send_button.isEnabled()); w.disconnect_radio(); self.assertFalse(w.send_button.isEnabled()); self.pump(.1)
    def test_cancel_ignores_late_success(self):
        w=self.window; self.store.data['radio'].update(model='IC-705',civ_address='A4')
        def slow(ctl,*args): time.sleep(.1); return CIVStatus(True,'COM1',19200,14085000)
        with patch('psrtty.ui.main_window.connect_configured',side_effect=slow), patch.object(w.audio,'start_input') as start:
            w.connect_radio(); w.disconnect_radio(); self.pump(.2); start.assert_not_called()
        self.assertFalse(w.send_button.isEnabled())
    def test_function_key_f9_invokes_macro(self):
        w=self.window; w.show(); w.activateWindow(); w.radio=CIVController(0xA4); w.radio.status.connected=True; w._set_radio_controls(); self.pump(.05)
        with patch.object(w,'_send_macro') as send:
            QTest.keyClick(w,Qt.Key_F9); self.pump(.05); send.assert_called_once_with(8)
    def test_autolog_only_after_successful_tu_and_unchanged_qso(self):
        w=self.window; w.radio=CIVController(0xA4); w.radio.status.connected=True
        from psrtty.macros import jarl_ww_template
        self.store.macros=jarl_ww_template(); w.auto_log.setChecked(True); w.q_call.setText('JX1XXX'); w.his_call.setText('JX1XXX'); w.rcvd.setText('01')
        with patch.object(w.audio,'send_text',return_value=(True,'OK')), patch.object(w,'_add_qso') as add:
            w._send_macro(2); w._tx_finished(True,'OK'); add.assert_not_called()
            w._send_macro(3); add.assert_not_called(); w._tx_finished(False,'failure'); add.assert_not_called()
            w._send_macro(3); w._tx_finished(True,'OK'); add.assert_called_once()
            add.reset_mock(); w._send_macro(3); w.rcvd.setText('02'); w._tx_finished(True,'OK'); add.assert_not_called()
    def test_gui_watchdog_restores_controls(self):
        w=self.window; self.store.data['radio'].update(model='IC-705',civ_address='A4')
        real_single=QTimer.singleShot
        def short_timeout(ms,*args): return real_single(40 if ms==10000 else ms,*args)
        def stalled(ctl,*args):
            time.sleep(.2)
            ctl.disconnect()
            return ctl.status
        with patch('psrtty.ui.main_window.QTimer.singleShot',side_effect=short_timeout), patch('psrtty.ui.main_window.connect_configured',side_effect=stalled):
            w.connect_radio(); self.pump(.1)
            self.assertFalse(w.connecting); self.assertTrue(w.connect_action.isEnabled()); self.assertFalse(w.send_button.isEnabled())
            self.pump(.2)
    def test_settings_connection_test_is_async(self):
        dlg=SettingsDialog(self.store); dlg.rig.setCurrentText('IC-705'); dlg.show()
        def slow(ctl,*args): time.sleep(.1); return CIVStatus(False,message='failed')
        with patch('psrtty.ui.settings_dialog.connect_configured',side_effect=slow), patch.object(QMessageBox,'warning') as warning:
            start=time.monotonic(); dlg._test_radio(); self.assertLess(time.monotonic()-start,.1)
            self.assertFalse(dlg.test_button.isEnabled()); self.pump(.2)
            self.assertTrue(dlg.test_button.isEnabled()); warning.assert_called_once()
        dlg.close()
    def test_v03_six_macro_rows_and_rx_position(self):
        w=self.window; w.show(); self.pump(.05)
        expected=[(0,0,1,1),(0,1,1,1),(1,0,1,2),(2,0,1,2),(4,0,1,1),(4,1,1,1),(5,0,1,1),(5,1,1,1),(6,0,1,2)]
        self.assertEqual([w.macro_layout.getItemPosition(w.macro_layout.indexOf(b)) for b in w.macro_buttons],expected)
        from PySide6.QtWidgets import QPushButton
        auto=next(b for b in w.findChildren(QPushButton) if b.text()=='AUTO TUNE')
        self.assertEqual(w.level.parentWidget(),auto.parentWidget())
        self.assertLess(w.level.geometry().bottom(),auto.geometry().top())
        self.assertEqual(self.store.macros[7]['text'],'KKK')
    def test_v03_window_save_and_reset_help(self):
        w=self.window; w.show(); self.pump(.05); w.resize(700,500); self.pump(.05)
        w._guide_flags(); self.assertFalse(w.help_windows['起動コマンドフラグについて'].isModal())
        w.close(); self.assertEqual(self.store.data['ui']['window']['w'],700)
    def test_v03_reset_ignores_maximized_and_restores_bounds(self):
        from psrtty.ui.window_state import restore_window
        w=self.window; w.show(); self.pump(.05)
        saved=dict(x=9999,y=9999,w=500,h=400,maximized=True)
        restore_window(w,saved,True); self.pump(.05)
        self.assertFalse(w.isMaximized()); self.assertTrue(w.screen().availableGeometry().contains(w.frameGeometry()))
        restore_window(w,saved); self.pump(.05); self.assertTrue(w.isMaximized())
