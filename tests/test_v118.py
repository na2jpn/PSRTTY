import copy
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from psrtty.config import DEFAULT_CONFIG,ConfigStore
from psrtty.fsk import validate,frame,CodeEncoder,BitClock,start_fsk,SerialKey
from psrtty.audio_engine import AudioEngine
from psrtty.live_tx import LiveText
from psrtty.macro_colors import normalize,STANDARD
from psrtty.ui.macro_colors_dialog import MacroColorsDialog
from psrtty.ui.settings_dialog import SettingsDialog
from tests.test_ui_v02 import UITests as Fixture

class FSKTests(unittest.TestCase):
    def settings(self):
        radio=dict(DEFAULT_CONFIG['radio'],model='IC-7300',com_port='COM3')
        return radio,copy.deepcopy(DEFAULT_CONFIG['fsk'])
    def test_profiles_keep_afsk_default_and_isolate_fsk(self):
        with tempfile.TemporaryDirectory() as td:
            store=ConfigStore(Path(td)/'config.json',Path(td)/'macros.json')
            store.data['profiles'].append(copy.deepcopy(store.data['profiles'][0]));store.data['profiles'][1]['name']='Profile2'
            store.activate_profile(1);store.data['radio']['tx_method']='fsk';store.data['fsk']['mode']='RTTY-R';store.save()
            store.activate_profile(0);self.assertEqual(store.data['radio']['tx_method'],'afsk')
            other=ConfigStore(store.config_path,store.macro_path);other.activate_profile(1)
            self.assertEqual(other.data['fsk']['mode'],'RTTY-R');self.assertEqual(other.data['advanced']['data_mode'],'LSB-D')
    def test_conflicts_and_separate_yaesu_port(self):
        r,f=self.settings();self.assertTrue(validate(r,f))
        with self.assertRaises(ValueError):validate(dict(r,ptt='DTR'),f)
        with self.assertRaises(ValueError):validate(dict(r,model='FT-891'),f)
        f['port']='COM4';self.assertFalse(validate(dict(r,model='FT-891',ptt='CAT'),f))
        with self.assertRaises(ValueError):validate(r,f,{'enabled':True,'com_port':'com4'})
        with self.assertRaises(ValueError):validate(dict(r,model='IC-910 / IC-910H'),f)
    def test_frame_and_figures_state(self):
        self.assertEqual(frame(1),[(False,1.),(True,1.),(False,1.),(False,1.),(False,1.),(False,1.),(True,1.5)])
        e=CodeEncoder();self.assertEqual(e.char('3'),[27,1]);self.assertEqual(e.char('4'),[10]);self.assertEqual(e.char('E'),[31,1])
        self.assertEqual(e.char('\n'),[8,2])
    def test_bit_clock_has_no_cumulative_rounding(self):
        clock=[0.];key=Mock();cancel=Mock()
        cancel.is_set.return_value=False
        cancel.wait.side_effect=lambda t:clock.__setitem__(0,clock[0]+t+.0006)
        with patch('psrtty.fsk.time.perf_counter',side_effect=lambda:clock[0]):
            b=BitClock(key,cancel,45.45)
            for _ in range(20):self.assertTrue(b.code(31))
            self.assertAlmostEqual(b.deadline,20*7.5/45.45,places=10)
    def test_timing_overrun_stops(self):
        with patch('psrtty.fsk.time.perf_counter',side_effect=[0.,.1]):
            b=BitClock(Mock(),threading.Event(),45.45)
            with self.assertRaises(RuntimeError):b.emit(True,1.)
    def test_shared_port_not_opened_or_closed(self):
        r,f=self.settings();ser=Mock();ctl=SimpleNamespace(ser=ser,status=SimpleNamespace(connected=True))
        with patch('serial.Serial') as opening:
            key=SerialKey(ctl,r,f);key.open();self.assertFalse(ser.dtr);key.close()
            opening.assert_not_called();ser.close.assert_not_called()
    def run_tx(self,session=None,mode=True,cancel=False):
        r,f=self.settings();engine=AudioEngine();ctl=Mock();ctl.status.connected=True;ctl.set_fsk_mode.return_value=mode
        on=Mock(return_value=True);off=Mock(return_value=True);done=Mock();progress=Mock()
        def code(value):
            if cancel:engine.stop_tx();return False
            return True
        with patch('psrtty.fsk.SerialKey') as key,patch('psrtty.fsk.BitClock') as clock,patch('psrtty.audio_engine.sd') as sd:
            clock.return_value.code.side_effect=code;clock.return_value.emit.return_value=True
            ok,_=start_fsk(engine,ctl,r,f,DEFAULT_CONFIG['advanced'],on,off,done,text='RY',session=session,progress=progress)
            self.assertTrue(ok);engine.wait_tx(2.)
            self.assertFalse(engine._tx_active);self.assertEqual(done.call_count,1);off.assert_called_once();key.return_value.close.assert_called_once();sd.OutputStream.assert_not_called()
        return on,done,progress
    def test_macro_fsk_success_has_no_audio(self):
        on,done,_=self.run_tx();on.assert_called_once();self.assertTrue(done.call_args.args[0])
    def test_mode_failure_never_keys_ptt(self):
        on,done,_=self.run_tx(mode=False);on.assert_not_called();self.assertFalse(done.call_args.args[0])
    def test_cancel_releases_ptt(self):
        _,done,_=self.run_tx(cancel=True);self.assertFalse(done.call_args.args[0])
    def test_live_fsk_progress_and_idle_stop(self):
        session=LiveText('RY',delay=0,hold=True,idle_timeout=0)
        _,done,progress=self.run_tx(session=session)
        self.assertEqual(session.records,['R','Y']);self.assertEqual(progress.call_count,2);self.assertTrue(done.call_args.args[0])
    def test_normalization_drops_invalid_colors(self):
        data=normalize({'selected':99,'presets':[{'colors':[{'text':'bad','background':'#aabbcc'}]}]})
        self.assertEqual(data['selected'],0);self.assertEqual(data['presets'][0]['colors'][0],{'text':STANDARD[0]['text'],'background':'#AABBCC'})

class UI118Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    pump=Fixture.pump
    def test_standard_readonly_custom_save_and_named_selection(self):
        dlg=MacroColorsDialog(self.store,self.window)
        self.assertTrue(all(e.isReadOnly() for row in dlg.edits for e in row.values()))
        dlg.preset.setCurrentIndex(1);dlg.name.setText('CQ');dlg.edits[0]['text'].setText('#112233');dlg.edits[0]['background'].setText('#ABCDEF')
        self.assertIn('CQ',dlg.preset.itemText(1));dlg._save()
        self.assertEqual(self.store.data['ui']['macro_colors']['selected'],1)
        self.window._refresh_macros();self.assertIn('#ABCDEF',self.window.macro_buttons[0].styleSheet());dlg.deleteLater()
    def test_unsaved_no_keeps_edits_and_preset(self):
        dlg=MacroColorsDialog(self.store,self.window);dlg.preset.setCurrentIndex(1);dlg.name.setText('CQ')
        with patch('psrtty.ui.macro_colors_dialog.ask_question',return_value=QMessageBox.No) as question:
            dlg.preset.setCurrentIndex(2);self.assertEqual(dlg.preset.currentIndex(),1);self.assertEqual(dlg.name.text(),'CQ');dlg.reject();self.assertEqual(question.call_count,2)
        with patch('psrtty.ui.macro_colors_dialog.ask_question',return_value=QMessageBox.Yes):dlg.preset.setCurrentIndex(2)
        self.assertEqual(dlg.preset.currentIndex(),2);self.assertEqual(dlg.working['presets'][0]['name'],'');dlg.deleteLater()
    def test_invalid_color_cannot_be_saved(self):
        dlg=MacroColorsDialog(self.store,self.window);dlg.preset.setCurrentIndex(1);dlg.edits[0]['text'].setText('#1')
        with patch.object(QMessageBox,'warning') as warning:dlg._save();warning.assert_called_once()
        self.assertNotIn('macro_colors',self.store.data['ui']);dlg.deleteLater()
    def test_profile_fsk_switch_keeps_afsk_settings(self):
        self.store.data['radio'].update(model='IC-7300',civ_address='94',com_port='COM3')
        dlg=SettingsDialog(self.store,self.window)
        with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes):dlg._switch_fsk()
        self.assertEqual(dlg.working['radio']['tx_method'],'fsk');self.assertEqual(dlg.data_mode.currentText(),'RTTY')
        self.assertIn('FSK',dlg.tabs.tabText(3));self.assertEqual(dlg.fsk_port.currentData(),'RADIO')
        self.assertEqual(dlg.working['advanced']['data_mode'],'LSB-D')
        self.assertEqual(self.store.data['radio']['tx_method'],'afsk')
        with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes):dlg._switch_fsk()
        self.assertEqual(dlg.data_mode.currentText(),'LSB-D');dlg.reject();dlg.deleteLater()
    def test_fsk_cannot_transmit_offline(self):
        w=self.window;w.store.data['radio']['tx_method']='fsk';w.offline_tx.setChecked(True)
        self.assertFalse(w._manual_tx_allowed())
        with patch('psrtty.fsk.start_fsk') as start:self.assertFalse(w._send_text('RY'));start.assert_not_called()

class FSKModeTests(unittest.TestCase):
    def test_icom_command_and_readback_for_both_polarities(self):
        from psrtty.civ import CIVController
        for mode,value in [('RTTY',4),('RTTY-R',8)]:
            ctl=CIVController(0x94,model='IC-7300');ctl.ser=Mock();ctl.status.connected=True
            with patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',side_effect=[bytes.fromhex('FE FE E0 94 04 00 01 FD'),bytes.fromhex('FE FE E0 94 FB FD'),bytes([254,254,224,148,4,value,1,253])]):
                self.assertTrue(ctl.set_fsk_mode(mode))
            self.assertEqual(ctl.ser.write.call_args_list[1].args[0],ctl._frame(6,value))
    def test_icom_unknown_tx_or_bad_mode_never_keys(self):
        from psrtty.civ import CIVController
        ctl=CIVController(0x94,model='IC-7300');ctl.ser=Mock();ctl.status.connected=True
        with patch.object(ctl,'read_transmitting',return_value=None):self.assertFalse(ctl.set_fsk_mode('RTTY'))
        ctl.ser.write.assert_not_called()
        with patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',return_value=bytes.fromhex('FE FE E0 94 FA FD')):self.assertFalse(ctl.set_fsk_mode('RTTY'))
    def test_connect_fsk_skips_usb_audio_routing(self):
        from psrtty.civ import connect_configured,CIVStatus
        ctl=Mock(model='IC-7300');ctl.status=CIVStatus(True);ctl.cancel.is_set.return_value=False;ctl.set_fsk_mode.return_value=True
        connect_configured(ctl,{'model':'IC-7300','tx_method':'fsk','fsk_mode':'RTTY-R','auto_usb_mod_input':True},{'data_mode':'LSB-D'})
        ctl.set_fsk_mode.assert_called_once_with('RTTY-R');ctl.set_data_mode.assert_not_called();ctl.set_usb_mod_input.assert_not_called()
    def test_hamlib_rtty_token_and_readback(self):
        from psrtty.hamlib_radio import HamlibController
        ctl=HamlibController('FT-891');ctl.handle=1;ctl.status.connected=True;ctl.lib=Mock()
        ctl.lib.rig_parse_mode.return_value=32;ctl.lib.rig_set_mode.return_value=0
        def read(handle,vfo,result,width):result._obj.value=32;return 0
        ctl.lib.rig_get_mode.side_effect=read
        with patch.object(ctl,'read_transmitting',return_value=False):self.assertTrue(ctl.set_fsk_mode('RTTY'))
        ctl.lib.rig_parse_mode.assert_called_once_with(b'RTTY')

class FSKMainUI118Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    pump=Fixture.pump
    def test_fsk_main_path_never_calls_audio_sender(self):
        w=self.window;w.store.data['radio'].update(model='IC-7300',tx_method='fsk');ctl=Mock();ctl.status.connected=True;ctl.status.port='COM3';w.radio=ctl
        with patch('psrtty.fsk.start_fsk',return_value=(True,'FSK')) as start,patch.object(w.audio,'send_text') as audio:
            self.assertTrue(w._send_text('RY'));start.assert_called_once();audio.assert_not_called()
        w.active_tx_id=None;w.radio=None
    def test_control_mode_choices_follow_profile_method(self):
        w=self.window;w.store.data['radio'].update(model='IC-7300',tx_method='fsk')
        w._show_control();self.pump(.05)
        self.assertEqual(set(w.control_window.mode_buttons),{'RTTY','RTTY-R'})
        w.store.data['radio']['tx_method']='afsk';w.control_window.refresh_enabled()
        self.assertIn('LSB-D',w.control_window.mode_buttons)
