import unittest
from unittest.mock import Mock,patch
from copy import deepcopy
from PySide6.QtWidgets import QApplication,QMessageBox
from psrtty.ui.fsk_notice import notice_color,notice_key
from psrtty import i18n
from psrtty.config import RIG_MODELS,DEFAULT_CONFIG
from psrtty.fsk_models import ICOM_FSK,USB_KEYING,USB_AB,ACC13,ACC8,AFSK_ONLY,NO_REVERSE,modes_for
from psrtty.fsk_manuals import MANUALS
from psrtty.fsk import validate,start_fsk
from psrtty.civ import CIVController
from psrtty.radio_support import LEGACY_MODE
from psrtty.audio_engine import AudioEngine
from psrtty.external_ptt import ExternalPTT
from psrtty.tx_keying import keying_callbacks
from psrtty.ui.fsk_help import settings_html,icom_guide_html
from psrtty.ui.settings_dialog import SettingsDialog
from tests.test_ui_v02 import UITests as Fixture

class CapabilityTests(unittest.TestCase):
    def tearDown(self):i18n.configure('ja')
    def test_all_selected_icom_models_classified_with_sources(self):
        self.assertEqual(set(RIG_MODELS)-{'その他ICOM'},ICOM_FSK|AFSK_ONLY)
        self.assertFalse(ICOM_FSK&AFSK_ONLY)
        self.assertEqual(set(MANUALS),ICOM_FSK|AFSK_ONLY)
        self.assertEqual(len(ICOM_FSK),32);self.assertEqual(len(USB_KEYING),8)
    def test_all_supported_routes_and_invalid_routes(self):
        for model in ICOM_FSK:
            r=dict(DEFAULT_CONFIG['radio'],model=model,com_port='CAT1')
            f=dict(DEFAULT_CONFIG['fsk'],port='FSK2')
            self.assertFalse(validate(r,f),model)
            f['port']='RADIO'
            if model in USB_KEYING:self.assertTrue(validate(r,f),model)
            else:
                with self.assertRaises(ValueError,msg=model):validate(r,f)
        for model in AFSK_ONLY|{'その他ICOM'}:
            with self.assertRaises(ValueError,msg=model):validate({'model':model},{'port':'FSK2','line':'DTR','mode':'RTTY'})
    def test_icom_mode_command_forms_and_readback(self):
        for model in ICOM_FSK:
            for mode in modes_for(model):
                code=4 if mode=='RTTY' else 8;address=RIG_MODELS[model]
                ctl=CIVController(address,model=model);ctl.ser=Mock();ctl.status.connected=True
                reply=bytes([254,254,224,address,4,code,253])
                with patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',side_effect=[bytes([254,254,224,address,4,0,1,253]),bytes([254,254,224,address,251,253]),reply]):
                    self.assertTrue(ctl.set_fsk_mode(mode),(model,mode))
                payload=(6,code)
                self.assertEqual(ctl.ser.write.call_args_list[1].args[0],ctl._frame(*payload),(model,mode))
        for model in AFSK_ONLY|NO_REVERSE:
            ctl=CIVController(RIG_MODELS[model],model=model);ctl.ser=Mock();ctl.status.connected=True
            self.assertFalse(ctl.set_fsk_mode('RTTY-R'));ctl.ser.write.assert_not_called()
    def test_annotations_and_guide_cover_every_model_in_all_languages(self):
        for language in i18n.LANGUAGES:
            i18n.configure(language);guide=icom_guide_html()
            for model in ICOM_FSK|AFSK_ONLY:
                html=settings_html(model)
                self.assertIn('color:'+notice_color(model),html);self.assertIn(MANUALS[model].replace('&','&amp;'),html)
                self.assertIn(model,guide)
                if model in AFSK_ONLY:self.assertIn(i18n.tr('fsk3.afsk_only'),html);self.assertNotIn('<table',html)
                if model in USB_AB:
                    prefix='USB1' if model=='IC-7610' else 'USB'
                    self.assertIn(prefix+' (A)',html);self.assertIn(prefix+' (B)',html)
                if model in ACC13|ACC8:self.assertNotIn('USB (A)',html);self.assertIn('ACC',html)
            self.assertIn('USB1',settings_html('IC-7851'));self.assertNotIn('USB (A)',settings_html('IC-7851'))

class SharedPTTTests(unittest.TestCase):
    def config(self):
        return ({'model':'IC-706','com_port':'CAT1','ptt':'外部接続'},
                {'port':'FSK2','line':'DTR','invert':False,'mode':'RTTY'},
                {'enabled':True,'com_port':'FSK2','line':'RTS','role':'ptt','reversed':False,'delay_seconds':.1})
    def test_shared_interface_single_open_and_cleanup_on_success_and_failure(self):
        for mode_ok in (True,False):
            r,f,e=self.config();ctl=Mock();ctl.status.connected=True;ctl.set_fsk_mode.return_value=mode_ok
            engine=AudioEngine();seq=ExternalPTT(e,'CAT1',engine._tx_cancel)
            on,off=keying_callbacks(ctl,'外部接続',seq,lambda:True);device=Mock();done=[]
            # No audio or FSK timing dependency: this test checks resource ownership and PTT.
            with patch('serial.Serial',return_value=device) as serial,patch('psrtty.fsk.BitClock'):
                ok,_=start_fsk(engine,ctl,r,f,DEFAULT_CONFIG['advanced'],on,off,lambda *x:done.append(x),text='RY',external=e,sequencer=seq)
                self.assertTrue(ok);engine._tx_thread.join(2);self.assertFalse(engine._tx_thread.is_alive())
                self.assertEqual(serial.call_count,1);device.open.assert_called_once();device.close.assert_called_once()
                self.assertFalse(device.rts);self.assertFalse(device.dtr);self.assertFalse(ctl.external_transmitting)
                self.assertEqual(done[0][0],mode_ok)
    def test_reject_same_line_cat_port_and_prekey_sharing(self):
        r,f,e=self.config();self.assertFalse(validate(r,f,e))
        for changes in ({'line':'DTR'},{'role':'prekey'}):
            with self.assertRaises(ValueError):validate(r,f,dict(e,**changes))
        with self.assertRaises(ValueError):validate(r,dict(f,port='CAT1'),e)
        engine=AudioEngine();ctl=Mock();ctl.status.connected=True
        ok,_=start_fsk(engine,ctl,r,f,DEFAULT_CONFIG['advanced'],Mock(),Mock(),Mock(),external=e)
        self.assertFalse(ok);self.assertFalse(engine._tx_active)

class SettingsTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    def test_switch_additional_icom_and_warn_nonfsk_without_changing_mode(self):
        for model in ('IC-705','IC-7100','IC-7300MK2','IC-761'):
            self.store.data['radio'].update(model=model,tx_method='afsk')
            d=SettingsDialog(self.store,self.window)
            with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes):d._switch_fsk()
            self.assertEqual(d.working['radio']['tx_method'],'fsk')
            self.assertEqual(d.fsk_port.findData('RADIO')>=0,model in USB_KEYING)
            self.assertEqual(tuple(d.data_mode.itemText(i) for i in range(d.data_mode.count())),modes_for(model))
            d.reject();d.deleteLater()
        self.store.data['radio'].update(model='IC-910 / IC-910H',tx_method='afsk')
        d=SettingsDialog(self.store,self.window)
        with patch('psrtty.ui.fsk_settings.QMessageBox.information') as warning:d._switch_fsk()
        warning.assert_called_once();self.assertEqual(d.working['radio']['tx_method'],'afsk');d.reject()
