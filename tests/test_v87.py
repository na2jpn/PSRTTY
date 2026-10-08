import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QPushButton

from psrtty.civ import CIVController
from psrtty.audio_engine import AudioEngine
from psrtty.ui.settings_dialog import SettingsDialog
from tests.test_ui_v02 import UITests as _Fixture


class CIV87Tests(unittest.TestCase):
    def test_alc_bcd_and_unsupported_reply(self):
        ctl=CIVController(0x94, model='IC-7300')
        ctl.ser=Mock(); ctl.status.connected=True
        with patch.object(ctl, '_read_response', return_value=b'\xfe\xfe\xe0\x94\x15\x13\x01\x20\xfd'):
            self.assertEqual(ctl.read_alc(),120)
            ctl.ser.write.assert_called_with(b'\xfe\xfe\x94\xe0\x15\x13\xfd')
        with patch.object(ctl, '_read_response', return_value=b'\xfe\xfe\xe0\x94\xfa\xfd'):
            self.assertIsNone(ctl.read_alc())

    def test_external_tuner_command_without_state_reply(self):
        ctl=CIVController(0x88, model='IC-7100')
        ctl.ser=Mock();ctl.status.connected=True
        with patch.object(ctl,'read_tuner',return_value=None),patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',return_value=b'\xfe\xfe\xe0\x88\xfb\xfd'):
            self.assertTrue(ctl.start_tuner())
        with patch.object(ctl,'read_tuner',return_value=2),patch.object(ctl,'read_transmitting',return_value=False):
            self.assertFalse(ctl.start_tuner())


class UI87Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_provisional_rx_gain_and_quiet_meter(self):
        from psrtty.config import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG['audio']['rx_gain'], .5)
        dlg=SettingsDialog(self.store,self.window);dlg.show()
        dlg.rx_gain.setValue(100)
        preset=next(b for b in dlg.findChildren(QPushButton) if b.text()=='暫定50%')
        preset.click()
        self.assertEqual(dlg.rx_gain.value(),50)
        self.window.level.setValue(6);self.window.rx_display.band=1;dlg._refresh_rx_meter()
        self.assertEqual(dlg.rx_state.text(),'Low')
        self.assertIn('#73cbe8',dlg.rx_meter.styleSheet())
        dlg.reject()

    def test_rx_live_preview_and_cancel_restore(self):
        dlg=SettingsDialog(self.store,self.window);dlg.show()
        old=self.store.data['audio']['rx_gain']
        dlg.rx_gain.setValue(170)
        self.assertEqual(self.window.audio.rx_gain,1.7)
        self.assertEqual(self.store.data['audio']['rx_gain'],old)
        dlg.reject()
        self.assertEqual(self.window.audio.rx_gain,old)

    def test_individual_save_and_timed_tx_toggle(self):
        dlg=SettingsDialog(self.store,self.window);dlg.show()
        dlg.rx_gain.setValue(130);dlg._save_audio_in()
        self.assertEqual(self.store.data['audio']['rx_gain'],1.3)
        ctl=Mock();ctl.status.connected=True;ctl.set_ptt.return_value=True
        dlg.test_controller=ctl;dlg.verified_values=dlg._radio_values()
        dlg.test_tx_button.setEnabled(True)
        with patch.object(self.window.audio,'send_text',return_value=(True,'送信開始')),patch.object(self.window.audio,'stop_tx') as stop:
            dlg._toggle_test_tx()
            self.assertTrue(dlg.tx_testing)
            self.assertIn('10秒',dlg.test_count_label.text())
            self.assertFalse(dlg.save_out_button.isEnabled())
            dlg.test_deadline=time.monotonic()-1
            dlg._tick_test_tx();stop.assert_called_once()
            dlg.tx_test_finished.emit(False,'送信中止')
            self.assertFalse(dlg.tx_testing)
            self.assertTrue(dlg.save_out_button.isEnabled())
        dlg.reject()
        self.assertEqual(self.store.data['audio']['rx_gain'],1.3)

    def test_green_alc_requires_observed_onset(self):
        dlg=SettingsDialog(self.store,self.window)
        dlg.tx_gain.setValue(40);dlg._show_alc(0)
        self.assertNotIn('緑：',dlg.alc_note.text())
        dlg.alc_onset=45;dlg._show_alc(0)
        self.assertIn('緑：',dlg.alc_note.text())
        dlg._show_alc(None)
        self.assertIn('無線機本体',dlg.alc_note.text())
        dlg.reject()

    def test_radio_change_invalidates_tx_test(self):
        dlg=SettingsDialog(self.store,self.window);dlg.show()
        dlg.rig.setCurrentText('IC-7300')
        dlg.verified_values=dlg._radio_values()
        dlg.test_tx_button.setEnabled(True)
        dlg.rig.setCurrentText('IC-7100')
        self.assertFalse(dlg.test_tx_button.isEnabled())
        self.assertIn('再実行',dlg.tx_test_note.text())
        dlg.reject()

    def test_operational_connection_allows_tx_test_without_disconnect(self):
        self.store.data['radio']['model']='IC-7300'
        ctl=Mock();ctl.status.connected=True;ctl.set_ptt.return_value=True
        self.window.radio=ctl
        dlg=SettingsDialog(self.store,self.window);dlg.show()
        self.assertTrue(dlg.test_tx_button.isEnabled())
        self.assertTrue(dlg.test_uses_main)
        with patch.object(self.window.audio,'send_text',return_value=(True,'送信開始')) as send,patch.object(self.window.audio,'stop_tx'):
            dlg.test_tx_button.click()
            self.assertTrue(dlg.tx_testing)
            send.assert_called_once()
            dlg.tx_test_finished.emit(False,'送信中止')
        dlg.reject()
        ctl.disconnect.assert_not_called()
        self.assertIs(self.window.radio,ctl)


class Audio87Tests(unittest.TestCase):
    def test_transmit_gain_is_sampled_for_each_block(self):
        chunks=[]; engine=AudioEngine()
        class Output:
            def __init__(self,**kwargs): pass
            def start(self): pass
            def write(self,chunk):
                chunks.append(float(abs(chunk).max()))
                if len(chunks)==1: engine.set_tx_gain(.10)
            def stop(self): pass
            def close(self): pass
        fake=Mock(OutputStream=Output)
        fake.WasapiSettings=Mock()
        # Keep the fake transport independent of Windows endpoint discovery,
        # while exercising the Windows WASAPI output-stream branch.
        with patch('psrtty.audio_engine.sd',fake), \
             patch('psrtty.audio_engine.resolve_device',return_value=None), \
             patch('psrtty.audio_engine.sys',SimpleNamespace(platform='win32')):
            ok,_=engine.send_text('RYRYRY','AUTO',45.45,2125,2295,False,.60,
                                  lambda:True,lambda:True)
            self.assertTrue(ok)
            engine.wait_tx(3)
        self.assertGreater(len(chunks),2)
        self.assertGreater(chunks[0],.5)
        self.assertLess(max(chunks[1:]),.11)
