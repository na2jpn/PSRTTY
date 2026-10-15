"""Yaesu FSK classification, guarded TX, model instructions and per-profile UI."""
import unittest
from copy import deepcopy
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication,QMessageBox
from psrtty.ui.fsk_notice import notice_color,notice_key
from psrtty import i18n
from psrtty.config import DEFAULT_CONFIG
from psrtty.hamlib_radio import HAMLIB_MODELS,HamlibController
from psrtty.fsk_models import YAESU_FSK,YAESU_USB,YAESU_EXTERNAL,YAESU_AFSK_ONLY,modes_for
from psrtty.fsk_manuals import YAESU_MANUALS
from psrtty.fsk import validate,start_fsk
from psrtty.audio_engine import AudioEngine
from psrtty.ui.fsk_help import settings_html,yaesu_guide_html
from psrtty.ui.settings_dialog import SettingsDialog
from tests import test_ui_v02

class YaesuFSKTests(unittest.TestCase):
    def tearDown(self):i18n.configure('ja')
    def test_every_selected_yaesu_classified_and_source_linked(self):
        selected={m for m in HAMLIB_MODELS if m.startswith(('FT-','FTDX','FTX-'))}
        self.assertEqual(selected,YAESU_FSK|YAESU_AFSK_ONLY)
        self.assertEqual(selected,set(YAESU_MANUALS))
        self.assertEqual(len(YAESU_USB),8);self.assertEqual(len(YAESU_EXTERNAL),2)
        self.assertFalse(YAESU_FSK&YAESU_AFSK_ONLY)
        for model in selected:
            r=dict(DEFAULT_CONFIG['radio'],model=model,com_port='COM3',ptt='CAT')
            f=dict(DEFAULT_CONFIG['fsk'],port='COM4')
            if model in YAESU_FSK:
                for mode in modes_for(model):self.assertFalse(validate(r,dict(f,mode=mode)))
                for port in ('com3','RADIO','','AUTO'):
                    with self.assertRaises(ValueError):validate(r,dict(f,port=port))
            else:
                self.assertFalse(modes_for(model))
                with self.assertRaisesRegex(ValueError,'AFSK'):validate(r,f)
    def test_hamlib_rtty_mode_and_actual_readback_all_supported_models(self):
        for model in YAESU_FSK:
            for mode in modes_for(model):
                ctl=HamlibController(model);ctl.handle=1;ctl.status.connected=True;ctl.lib=Mock()
                val=32 if mode=='RTTY' else 64
                ctl.lib.rig_parse_mode.side_effect=lambda t:32 if t==b'RTTY' else 64 if t==b'RTTYR' else 0
                ctl.lib.rig_set_mode.return_value=0
                def read(h,v,result,width):result._obj.value=val;return 0
                ctl.lib.rig_get_mode.side_effect=read
                with patch.object(ctl,'read_transmitting',return_value=False):
                    self.assertTrue(ctl.set_fsk_mode(mode));self.assertEqual(ctl.read_operating_mode(),mode)
                    ctl.lib.rig_get_mode.side_effect=None;ctl.lib.rig_get_mode.return_value=-1
                    self.assertFalse(ctl.set_fsk_mode(mode))
    def test_all_supported_models_send_no_audio_and_unsupported_models_never_start(self):
        for model in YAESU_FSK|YAESU_AFSK_ONLY:
            r=dict(DEFAULT_CONFIG['radio'],model=model,com_port='COM3',ptt='CAT')
            f=dict(DEFAULT_CONFIG['fsk'],port='COM4');engine=AudioEngine()
            ctl=Mock();ctl.status.connected=True;ctl.set_fsk_mode.return_value=True
            on=Mock(return_value=True);off=Mock(return_value=True);done=Mock()
            key_device=Mock()
            def checked_key(controller,radio,options,external=None):
                validate(radio,options,external);return key_device
            with patch('psrtty.fsk.SerialKey',side_effect=checked_key) as key,patch('psrtty.fsk.BitClock'),patch('psrtty.audio_engine.sd') as sd:
                ok,_=start_fsk(engine,ctl,r,f,DEFAULT_CONFIG['advanced'],on,off,done,text='RY')
                self.assertEqual(ok,model in YAESU_FSK)
                if ok:
                    engine.wait_tx(2);self.assertFalse(engine._tx_active);self.assertTrue(done.call_args.args[0])
                    on.assert_called_once();off.assert_called_once();key_device.close.assert_called_once()
                else:on.assert_not_called();key_device.open.assert_not_called()
                sd.OutputStream.assert_not_called()
    def test_model_specific_instructions_in_all_eight_languages(self):
        for lang in i18n.LANGUAGES:
            i18n.configure(lang);guide=yaesu_guide_html()
            for model in YAESU_FSK|YAESU_AFSK_ONLY:
                html=settings_html(model,ptt='CAT');self.assertIn(model,guide)
                self.assertIn(YAESU_MANUALS[model].replace('&','&amp;'),html)
                self.assertNotIn('fsk5.',html);self.assertIn('color:'+notice_color(model),html)
                if model in YAESU_AFSK_ONLY:
                    self.assertIn(i18n.tr('fsk3.afsk_only'),html);self.assertNotIn('<table',html)
                else:self.assertIn('170 Hz',html);self.assertIn('2125 Hz',html)
                if model in YAESU_EXTERNAL:self.assertIn('4 FSK IN / 2 GND',html);self.assertIn('SCU-17',html)
            for model,menu in (('FT-891','07-12 PC KEYING'),('FT-991 / FT-991A','060 PC KEYING'),('FTDX3000','065 PC KEYING'),('FT-710','RADIO SETTING → MODE RTTY → RPTT SELECT')):
                for line,ptt in (('DTR','RTS'),('RTS','DTR')):
                    html=settings_html(model,line=line,ptt='CAT')
                    self.assertIn(menu+'</td><td align="left" style="padding:5px;">'+ptt,html)
            self.assertIn('FT-991A 096',settings_html('FT-991 / FT-991A'))
            self.assertIn(i18n.tr('fsk5.pair'),settings_html('FT-710'))
            # Supported features do not carry discouraging provisional labels.
            if lang=='ja':
                for model in YAESU_FSK:
                    self.assertNotIn('未確認',settings_html(model));self.assertNotIn('試験機能',settings_html(model))

class YaesuSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=test_ui_v02.UITests.setUp
    tearDown=test_ui_v02.UITests.tearDown
    def test_supported_switch_preserves_afsk_and_unsupported_stays_afsk(self):
        for model in YAESU_FSK|YAESU_AFSK_ONLY:
            self.store.data['radio'].update(model=model,ptt='CAT',tx_method='afsk')
            d=SettingsDialog(self.store,self.window);audio=deepcopy(d.working['audio']);advanced=deepcopy(d.working['advanced'])
            if model in YAESU_FSK:
                with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes):d._switch_fsk()
                self.assertEqual(d.working['radio']['tx_method'],'fsk');self.assertEqual(d.fsk_port.findData('RADIO'),-1)
                self.assertEqual(d.data_mode.count(),2);self.assertEqual(d.working['audio'],audio);self.assertEqual(d.working['advanced'],advanced)
            else:
                with patch('psrtty.ui.fsk_settings.QMessageBox.information') as notice:d._switch_fsk()
                notice.assert_called_once();self.assertIn('AFSK',notice.call_args.args[2])
                self.assertEqual(d.working['radio']['tx_method'],'afsk')
            d.reject()
