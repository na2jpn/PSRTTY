import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from psrtty import __version__
from psrtty.config import ConfigStore, DEFAULT_CONFIG
from psrtty.macros import normal_qso_template, jarl_ww_template, expand_macro, NORMAL_TEMPLATE_NAME, TEMPLATE_NAME
from psrtty.audio_engine import AudioEngine
from psrtty.civ import CIVController
from psrtty.updater import inspect_zip, create_manifest, prepare_update, apply_update, MANIFEST, helper_main, restart_application
from package_release import build_distribution
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.ui.number_edit import NumberEdit
from psrtty.ui.update_dialog import UpdateDialog
from PySide6.QtWidgets import QLineEdit, QGroupBox, QTextBrowser, QLabel, QMessageBox, QMenu
from PySide6.QtCore import QTimer


class Config05Tests(unittest.TestCase):
    def test_fresh_defaults_and_existing_settings_macros_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); cfg=root/'settings.json'; macros=root/'macros.json'
            st=ConfigStore(cfg,macros)
            self.assertEqual(st.data['audio']['input_device'],'UNSET')
            self.assertEqual(st.macros,normal_qso_template())
            old=copy.deepcopy(DEFAULT_CONFIG); old['audio']['input_device']='AUTO'; old.pop('station')
            cfg.write_text(json.dumps(old)); rows=jarl_ww_template(); rows[0]['text']='MY CUSTOM CQ'
            macros.write_text(json.dumps(rows))
            st=ConfigStore(cfg,macros); self.assertEqual(st.macros,rows)
            self.assertEqual(st.data['audio']['input_device'],'AUTO'); self.assertEqual(st.data['station']['qth'],'')
    def test_normal_template_variables_empty_and_no_recursive_expansion(self):
        rows=normal_qso_template(); self.assertEqual(len(rows),9)
        self.assertFalse(any('{SENT}' in row['text'] for row in rows))
        self.assertNotIn('TEST',rows[0]['text']); self.assertEqual(rows[7]['text'],'KKK')
        vals=dict(MYQTH='SOKA',MYJCCJCG='1318',MYTXT='NAME TARO\nRIG TEST',MYCALL='JX1XXX',HISCALL='')
        result=expand_macro(rows[6]['text'],vals)
        self.assertIn('QTH SOKA 1318',result); self.assertIn('NAME TARO\nRIG TEST',result)
        self.assertEqual(expand_macro('{MYQTH} {MYJCCJCG}',{'MYQTH':'','MYJCCJCG':'1318'}),'1318')
        self.assertEqual(expand_macro('{MYTXT}',{'MYTXT':'LITERAL {MYCALL}','MYCALL':'JX1XXX'}),'LITERAL {MYCALL}')
    def test_unset_input_never_opens_device(self):
        engine=AudioEngine()
        with patch('psrtty.audio_engine.sd') as sd:
            self.assertFalse(engine.start_input('UNSET')[0]); sd.InputStream.assert_not_called()


class UI05Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump
    def test_number_fields_commit_and_clamp_without_spin_buttons(self):
        w=self.window
        for widget,default in ((w.cq_count,10),(w.cq_interval,7)):
            self.assertIsInstance(widget,QLineEdit)
            for text,expected in [('100',99),('0',1),('-2',1),('abc',default),('',default),('2.5',default),('９８',98)]:
                widget.setText(text); self.assertEqual(widget.text(),text)
                widget.editingFinished.emit(); self.assertEqual(widget.text(),str(expected))
    def test_cq_start_commits_even_without_focus_change(self):
        w=self.window; w.radio=CIVController(0xA4); w.radio.status.connected=True
        w.cq_count.setText('999'); w.cq_interval.setText('bad')
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w._start_auto_cq()
        self.assertEqual(w.auto_cq_remaining,99); self.assertEqual(w.cq_interval.text(),'7')
        self.assertEqual(self.store.data['auto_cq']['count'],99)
    def test_basic_fields_save_and_preview_and_cancel(self):
        w=self.window; w._settings(); dlg=w.settings_window
        self.assertEqual(dlg.tabs.tabText(0),'基本設定')
        dlg.my_call.setText('jx1xxx'); dlg.my_qth.setText('SOKA'); dlg.my_jcc_jcg.setText('1318')
        dlg.my_text.setPlainText('NAME TARO\nRIG TEST'); dlg._save()
        self.assertEqual(w.my_call.text(),'JX1XXX')
        self.assertIn('QTH SOKA 1318',w.macro_buttons[6].toolTip())
        self.assertIn('NAME TARO',w.macro_buttons[6].toolTip())
        w._settings(); w.settings_window.my_qth.setText('CHANGED'); w.settings_window.reject()
        self.assertEqual(self.store.data['station']['qth'],'SOKA')
    def test_main_call_edit_while_settings_open_is_preserved(self):
        w=self.window; w.my_call.setText('JX1XXX'); w._settings()
        self.assertEqual(w.settings_window.my_call.text(),'JX1XXX')
        w.my_call.setText('JX2XXX'); w.settings_window._save()
        self.assertEqual(w.my_call.text(),'JX2XXX'); self.assertEqual(self.store.data['station_callsign'],'JX2XXX')
    def test_both_templates_editable_and_cancel_preserves(self):
        dlg=MacroDialog(self.store)
        self.assertEqual(dlg.template.currentText(),NORMAL_TEMPLATE_NAME)
        for name,expected in ((TEMPLATE_NAME,jarl_ww_template()),(NORMAL_TEMPLATE_NAME,normal_qso_template())):
            dlg.template.setCurrentText(name); dlg._apply_template()
            self.assertEqual(dlg.table.item(0,2).text(),expected[0]['text'])
        dlg.table.item(3,2).setText('EDIT {MYTXT}'); dlg._save()
        self.assertEqual(self.store.macros[3]['text'],'EDIT {MYTXT}')
    def test_audio_start_without_radio_and_disconnect_does_not_stop_input(self):
        w=self.window; self.store.data['audio']['input_device']='AUTO'
        with patch.object(w.audio,'start_input',return_value=(True,'OK')) as start, patch.object(w.audio,'stop_input') as stop:
            self.pump(.1); start.assert_called_once_with('AUTO')
            self.assertEqual(w.audio_status.text(),'Audio IN: 入力中')
            stop.reset_mock(); w.disconnect_radio(); stop.assert_not_called()
            self.store.data['audio']['input_device']='UNSET'; w._restart_audio_input(); self.pump(.1)
            self.assertEqual(w.audio_status.text(),'Audio IN: 未設定'); self.assertEqual(start.call_count,1)
    def test_audio_failure_does_not_change_selection_or_enable_tx(self):
        w=self.window; selected={'backend':'wasapi','id':'missing','kind':'input','name':'USB'}
        self.store.data['audio']['input_device']=selected
        with patch.object(w.audio,'start_input',return_value=(False,'missing device')) as start:
            self.pump(.1); start.assert_called_once_with(selected)
        self.assertEqual(w.audio_status.toolTip(),'missing device'); self.assertFalse(w.send_button.isEnabled())
        self.assertEqual(self.store.data['audio']['input_device'],selected)
    def test_audio_open_is_async_and_latest_selection_wins(self):
        w=self.window; self.pump(.1); calls=[]
        def slow(selection): calls.append(selection); time.sleep(.08); return True,'OK'
        ticks=[]; timer=QTimer(); timer.setInterval(5); timer.timeout.connect(lambda:ticks.append(1)); timer.start()
        with patch.object(w.audio,'start_input',side_effect=slow), patch.object(w.audio,'stop_input'):
            self.store.data['audio']['input_device']='FIRST'; start=time.monotonic(); w._restart_audio_input()
            self.assertLess(time.monotonic()-start,.05)
            self.store.data['audio']['input_device']='SECOND'; w._restart_audio_input(); self.pump(.3)
        timer.stop(); self.assertEqual(calls,['FIRST','SECOND']); self.assertGreater(len(ticks),10)
    def test_offline_audio_only_and_auto_cq_always_requires_radio(self):
        w=self.window; self.assertFalse(w.offline_tx.isChecked()); self.assertFalse(isinstance(w.offline_tx.parentWidget(),QGroupBox))
        w.offline_tx.setChecked(True); self.assertTrue(w.send_button.isEnabled()); self.assertFalse(w.auto_cq_button.isEnabled())
        self.assertTrue(all(s.isEnabled() for s in w.shortcuts[:9]))
        with patch.object(w.audio,'send_text',return_value=(True,'OK')) as send:
            w._start_auto_cq(); send.assert_not_called()
            w._send_macro(0); args=send.call_args.args
            self.assertTrue(args[7]()); self.assertTrue(args[8]())
            args[9](True,'OK'); self.pump(.05); self.assertIsNone(w.active_tx_id)
            w.manual_tx.setText('MANUAL'); w._send_manual(); self.assertEqual(send.call_args.args[0],'MANUAL')
            with patch.object(w.audio,'stop_tx') as stop:
                w.offline_tx.setChecked(False); stop.assert_called_once()
        self.assertFalse(w.send_button.isEnabled())
    def test_connected_ptt_still_used_with_test_checkbox_on(self):
        w=self.window; w.offline_tx.setChecked(True); ctl=w.radio=CIVController(0xA4); ctl.status.connected=True
        with patch.object(ctl,'set_ptt',return_value=True) as ptt, patch.object(w.audio,'send_text',return_value=(True,'OK')) as send:
            w._send_macro(0); args=send.call_args.args
            self.assertTrue(args[7]()); self.assertTrue(args[8]()); self.assertEqual([c.args for c in ptt.call_args_list],[(True,),(False,)])
    def test_test_transmission_does_not_auto_log(self):
        w=self.window; w.offline_tx.setChecked(True); w.auto_log.setChecked(True); w.q_call.setText('JX1XXX'); w.rcvd.setText('01')
        with patch.object(w.audio,'send_text',return_value=(True,'OK')), patch.object(w,'_add_qso') as add:
            w._manual_request('TU TEST',macro=True); w._tx_finished(True,'OK'); add.assert_not_called()
    def test_empty_sent_survives_qso_and_does_not_increment(self):
        w=self.window; w.qsos=[]; w.adif.append.return_value=Path('log.adi'); w.sent.setText(''); w.sent_fixed.setChecked(False)
        w.q_call.setText('JX1XXX'); w._add_qso(); self.assertEqual(w.sent.text(),''); self.assertEqual(w.qsos[0].sent,'')
    def test_guide_order_update_menu_and_dialog(self):
        w=self.window; w._guide_initial(); tabs=w.help_windows['初期設定ガイド'].tabs
        text=tabs.widget(0).toPlainText()
        self.assertIn('基本設定',text); self.assertIn('初期設定は通常交信',text)
        self.assertLess(text.index('基本設定'),text.index('COMポート'))
        self.assertLess(text.index('テンプレート'),text.index('Auto CQ'))
        self.assertIn('SENT',tabs.widget(4).toPlainText())
        # Retrieve parent-owned menus directly. QAction.menu() wrappers can
        # become invalid after temporary QAction wrappers are released in PySide6.
        menu_bar = w.menuBar()
        menu_objects = menu_bar.findChildren(QMenu)
        menus = {menu.title(): menu for menu in menu_objects}
        self.assertIn(w.update_action,menus['ヘルプ'].actions()); self.assertNotIn(w.update_action,menus['ファイル'].actions())
        dlg=UpdateDialog(w); text=dlg.findChild(QLabel).text(); self.assertIn(__version__,text); self.assertIn('自動で再起動',text)


del _Fixture


class Update05Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.root=self.base/'installed'; self.root.mkdir()
        for n in ('config','logdata','var'): (self.root/n).mkdir()
        (self.root/'psrtty.exe').write_bytes(b'MZ old payload'); create_manifest(self.root,__version__)
        self.exe=self.base/'new.exe'; self.exe.write_bytes(b'MZ different payload')
        self.archive=build_distribution(self.exe,self.base/'release')
    def tearDown(self): self.tmp.cleanup()
    def test_same_version_different_content_repairs_preserves_and_identical_rejects(self):
        (self.root/'config/keep.txt').write_text('settings'); (self.root/'logdata/keep.txt').write_text('log')
        self.assertTrue(inspect_zip(self.archive,__version__,self.root)['repair'])
        stage=prepare_update(self.archive,self.root,__version__); backup=apply_update(stage,self.root,__version__)
        self.assertEqual((backup/'psrtty.exe').read_bytes(),b'MZ old payload')
        self.assertEqual((self.root/'config/keep.txt').read_text(),'settings'); self.assertEqual((self.root/'logdata/keep.txt').read_text(),'log')
        with self.assertRaisesRegex(ValueError,'同じ内容'): inspect_zip(self.archive,__version__,self.root)
        with self.assertRaises(ValueError): inspect_zip(self.archive,'0.99',self.root)
    def test_same_version_failure_rolls_back(self):
        original=(self.root/MANIFEST).read_bytes(); stage=prepare_update(self.archive,self.root,__version__)
        with patch('psrtty.updater.migrate_settings',side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError): apply_update(stage,self.root,__version__)
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZ old payload'); self.assertEqual((self.root/MANIFEST).read_bytes(),original)
    def test_restart_command_and_environment(self):
        with patch('psrtty.updater.subprocess.Popen') as popen, patch('psrtty.updater.sys.platform','linux'):
            restart_application(self.root)
        args,kwargs=popen.call_args; self.assertEqual(args[0],[str(self.root/'psrtty.exe')]); self.assertEqual(kwargs['cwd'],self.root)
        self.assertEqual(kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'],'1')
    def test_helper_unlocks_before_restart_and_failure_never_restarts(self):
        stage=prepare_update(self.archive,self.root,__version__); events=[]
        lock=Mock(); lock.tryLock.return_value=True; lock.unlock.side_effect=lambda:events.append('unlock')
        for failed in (False,True):
            events.clear()
            with patch('psrtty.updater.wait_for_parent'), patch('PySide6.QtCore.QLockFile',return_value=lock), \
                 patch('psrtty.updater.apply_update',side_effect=RuntimeError('failed') if failed else None,return_value=self.root/'var/backups/test'), \
                 patch('psrtty.updater.restart_application',side_effect=lambda root:events.append('restart')) as restart, \
                 patch('psrtty.updater.confirm_restart',return_value={'version':__version__}), \
                 patch('ctypes.windll',SimpleNamespace(user32=Mock()),create=True):
                code=helper_main([str(stage),str(self.root),'123'])
            self.assertEqual(events,['unlock'] if failed else ['unlock','restart']); self.assertEqual(code,1 if failed else 0)
    def test_restart_failure_reports_successful_update_without_rollback(self):
        stage=prepare_update(self.archive,self.root,__version__)
        lock=Mock(); lock.tryLock.return_value=True
        with patch('psrtty.updater.wait_for_parent'), patch('PySide6.QtCore.QLockFile',return_value=lock), \
             patch('psrtty.updater.restart_application',side_effect=OSError('launch failed')), \
             patch('ctypes.windll',SimpleNamespace(user32=Mock()),create=True):
            code=helper_main([str(stage),str(self.root),'123'])
        self.assertEqual(code,2); self.assertEqual((self.root/'psrtty.exe').read_bytes(),self.exe.read_bytes())
        self.assertEqual(json.loads((stage/'result.json').read_text())['status'],'succeeded')
        self.assertTrue((stage/'restart-error.txt').exists())
