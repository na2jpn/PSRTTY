"""Kenwood FSK routes, Hamlib readback, cleanup and translated profile UI."""
import unittest
from copy import deepcopy
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from psrtty.ui.fsk_notice import notice_color,notice_key
from psrtty import i18n
from psrtty.config import DEFAULT_CONFIG
from psrtty.hamlib_radio import HAMLIB_MODELS,HamlibController
from psrtty.fsk_models import KENWOOD_FSK,modes_for
from psrtty.fsk_manuals import KENWOOD_MANUALS
from psrtty.fsk import validate,start_fsk
from psrtty.audio_engine import AudioEngine
from psrtty.ui.fsk_help import settings_html,kenwood_guide_html
from psrtty.ui.settings_dialog import SettingsDialog
from tests import test_ui_v02

class KenwoodFSKTests(unittest.TestCase):
    def tearDown(self):i18n.configure('ja')
    def test_every_selected_kenwood_has_modes_sources_and_dedicated_route(self):
        self.assertEqual({m for m in HAMLIB_MODELS if m.startswith('TS-')},KENWOOD_FSK)
        self.assertEqual(set(KENWOOD_MANUALS),KENWOOD_FSK)
        for model in KENWOOD_FSK:
            r=dict(DEFAULT_CONFIG['radio'],model=model,com_port='COM3',ptt='CAT')
            for mode in modes_for(model):
                f=dict(DEFAULT_CONFIG['fsk'],mode=mode,port='COM4')
                self.assertFalse(validate(r,f))
                for port in ('RADIO','com3','','AUTO'):
                    with self.assertRaises(ValueError):validate(r,dict(f,port=port))
    def test_hamlib_mode_readback_and_failure_never_claim_success(self):
        for model in KENWOOD_FSK:
            for mode in modes_for(model):
                ctl=HamlibController(model);ctl.handle=1;ctl.status.connected=True;ctl.lib=Mock()
                token=b'RTTY' if mode=='RTTY' else b'RTTYR'
                value=32 if mode=='RTTY' else 64
                ctl.lib.rig_parse_mode.side_effect=lambda v:32 if v==b'RTTY' else 64 if v==b'RTTYR' else 0
                ctl.lib.rig_set_mode.return_value=0
                def read(h,v,result,width):result._obj.value=value;return 0
                ctl.lib.rig_get_mode.side_effect=read
                with patch.object(ctl,'read_transmitting',return_value=False):
                    self.assertTrue(ctl.set_fsk_mode(mode));self.assertEqual(ctl.read_operating_mode(),mode)
                    self.assertIn(unittest.mock.call(token),ctl.lib.rig_parse_mode.call_args_list)
                    ctl.lib.rig_get_mode.side_effect=None;ctl.lib.rig_get_mode.return_value=-1
                    self.assertFalse(ctl.set_fsk_mode(mode))
                with patch.object(ctl,'read_transmitting',return_value=True):
                    ctl.lib.rig_set_mode.reset_mock();self.assertFalse(ctl.set_fsk_mode(mode));ctl.lib.rig_set_mode.assert_not_called()
    def test_all_three_send_without_audio_and_release_on_mode_failure(self):
        for model in KENWOOD_FSK:
            for mode_ok in (True,False):
                r=dict(DEFAULT_CONFIG['radio'],model=model,com_port='COM3',ptt='CAT')
                f=dict(DEFAULT_CONFIG['fsk'],port='COM4')
                engine=AudioEngine();ctl=Mock();ctl.status.connected=True;ctl.set_fsk_mode.return_value=mode_ok
                on=Mock(return_value=True);off=Mock(return_value=True);done=Mock()
                with patch('psrtty.fsk.SerialKey') as key,patch('psrtty.fsk.BitClock'),patch('psrtty.audio_engine.sd') as sd:
                    ok,_=start_fsk(engine,ctl,r,f,DEFAULT_CONFIG['advanced'],on,off,done,text='RY')
                    self.assertTrue(ok);engine.wait_tx(2)
                    self.assertFalse(engine._tx_active);self.assertEqual(done.call_args.args[0],mode_ok)
                    self.assertEqual(on.call_count,int(mode_ok));self.assertEqual(off.call_count,int(mode_ok));key.return_value.close.assert_called_once()
                    sd.OutputStream.assert_not_called()
    def test_eight_language_model_guides_and_selected_usb_signal(self):
        for language in i18n.LANGUAGES:
            i18n.configure(language);guide=kenwood_guide_html()
            for model in KENWOOD_FSK:
                html=settings_html(model,ptt='CAT')
                self.assertIn(model,guide);self.assertIn('color:'+notice_color(model),html)
                self.assertIn(KENWOOD_MANUALS[model],html)
                self.assertIn(i18n.tr('fsk4.modes'),html);self.assertIn(i18n.tr('fsk4.polarity'),html)
                self.assertIn('170 Hz',html);self.assertIn('2125 Hz',html)
                self.assertNotIn('fsk4.',html);self.assertNotIn('SCU-17',html)
                if model!='TS-890S':
                    self.assertIn('ACC2: 2 RTTY / 4 GND',html)
                    self.assertNotIn('Advanced 19',html)
            for line,number in (('DTR','20'),('RTS','19')):
                html=settings_html('TS-890S',line=line,ptt='CAT')
                self.assertIn('Advanced '+number+' (Enhanced '+line+')</td><td align="left" style="padding:5px;">RTTY Keying',html)

class KenwoodSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=test_ui_v02.UITests.setUp
    tearDown=test_ui_v02.UITests.tearDown
    def test_switch_builds_dedicated_output_and_preserves_afsk_settings(self):
        for model in KENWOOD_FSK:
            self.store.data['radio'].update(model=model,tx_method='afsk',ptt='CAT')
            self.store.data['audio']['output_device']='saved-audio'
            self.store.data['advanced']['data_mode']='USB-D'
            d=SettingsDialog(self.store,self.window)
            before=deepcopy(d.working['audio']);advanced=deepcopy(d.working['advanced'])
            self.assertIn(i18n.tr(notice_key(model)),d.fsk_model_notice.text())
            with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes):d._switch_fsk()
            self.assertEqual(d.working['radio']['tx_method'],'fsk');self.assertEqual(d.fsk_port.findData('RADIO'),-1)
            self.assertEqual(d.working['fsk']['port'],'');self.assertEqual(d.data_mode.count(),2)
            self.assertEqual(d.working['audio'],before);self.assertEqual(d.working['advanced'],advanced)
            with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes):d._switch_fsk()
            self.assertEqual(d.working['radio']['tx_method'],'afsk');self.assertEqual(d.working['audio'],before)
            self.assertEqual(d.working['advanced'],advanced);d.reject()
