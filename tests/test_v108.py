import ast
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import numpy as np
from psrtty.audio_engine import AudioEngine
from psrtty.secondary_audio import SecondaryOutput, normalize_settings
from psrtty.config import ConfigStore, RIG_MODELS
from psrtty.civ import CIVController, CIVStatus
from psrtty.i18n import configure, tr
from tests import test_ui_v02 as fixture


class Secondary108Tests(unittest.TestCase):
    def test_migration_and_reload_profiles(self):
        with TemporaryDirectory() as folder:
            root=Path(folder); config=root/'config.json'; macros=root/'macros.json'
            config.write_text('{"audio":{"tx_gain":0.25},"profiles":[{"name":"Profile1","audio":{"tx_gain":0.25}},{"name":"P2"}]}',encoding='utf-8')
            store=ConfigStore(config,macros)
            self.assertFalse(store.data['audio']['secondary']['enabled'])
            self.assertEqual(store.data['audio']['tx_gain'],.25)
            expected={'enabled':True,'device':{'backend':'test','id':'2','kind':'output'},'gain':2.0}
            store.data['audio']['secondary']=expected;store.save()
            store.activate_profile(1);self.assertFalse(store.data['audio']['secondary']['enabled'])
            store.activate_profile(0)
            self.assertEqual(ConfigStore(config,macros).data['audio']['secondary'],expected)
        for value in (float('nan'),float('inf'),'bad',None):
            self.assertEqual(normalize_settings({'gain':value})['gain'],1)
        self.assertEqual(normalize_settings({'gain':3})['gain'],2)
        self.assertEqual(normalize_settings({'gain':-1})['gain'],0)

    def test_callback_gain_clipping_end_and_same_device(self):
        class Stop(Exception): pass
        class Abort(Exception): pass
        sd=Mock(CallbackStop=Stop,CallbackAbort=Abort)
        audio=np.array([.25,-.25,.75,-.75],dtype=np.float32)
        report=Mock()
        with patch('psrtty.secondary_audio.resolve_device',return_value=2):
            out=SecondaryOutput(sd,audio,{'enabled':True,'device':2,'gain':2},1,48000,{},report)
        data=np.zeros((6,1),dtype=np.float32)
        with self.assertRaises(Stop):out.callback(data,6,None,False)
        np.testing.assert_allclose(data[:,0],[.5,-.5,1,-1,0,0])
        self.assertTrue(out.done.is_set());out.close();sd.OutputStream.return_value.abort.assert_called_once()
        sd.OutputStream.reset_mock()
        with patch('psrtty.secondary_audio.resolve_device',return_value=1):
            out=SecondaryOutput(sd,audio,{'enabled':True,'device':1},1,48000,{},report)
        sd.OutputStream.assert_not_called();self.assertTrue(out.failed)

    def test_secondary_failure_does_not_change_main_success_or_ptt(self):
        engine=AudioEngine();engine.configure_secondary({'enabled':True,'device':2,'gain':2})
        output=Mock();done=Mock();off=Mock(return_value=True)
        with patch('psrtty.audio_engine.sd') as sd, \
             patch('psrtty.audio_engine.resolve_device',return_value=1), \
             patch('psrtty.secondary_audio.resolve_device',side_effect=ValueError('missing')):
            sd.OutputStream.return_value=output
            engine.send_text('RY',1,45.45,2125,2295,False,.2,lambda:True,off,done)
            engine.wait_tx(3)
        self.assertTrue(done.call_args.args[0]);off.assert_called_once()
        self.assertIn('missing',engine.secondary_notice);output.write.assert_called()
        self.assertLessEqual(float(np.max(abs(output.write.call_args.args[0]))),.20001)

    def test_normal_secondary_drains_and_underflow_reports_once(self):
        class Stop(Exception): pass
        class Abort(Exception): pass
        sd=Mock(CallbackStop=Stop,CallbackAbort=Abort);report=Mock()
        with patch('psrtty.secondary_audio.resolve_device',return_value=2):
            output=SecondaryOutput(sd,np.ones(960,dtype=np.float32),{'enabled':True,'device':2},1,48000,{},report)
        with self.assertRaises(Stop):output.callback(np.zeros((960,1),dtype=np.float32),960,None,False)
        output.close(drain=True)
        sd.OutputStream.return_value.stop.assert_called_once()
        sd.OutputStream.return_value.abort.assert_not_called()
        with patch('psrtty.secondary_audio.resolve_device',return_value=2):
            output=SecondaryOutput(sd,np.ones(960),{'enabled':True,'device':2},1,48000,{},report)
        for _ in range(2):
            with self.assertRaises(Abort):output.callback(np.zeros((960,1)),960,None,'underflow')
        report.assert_called_once();output.close()

    def test_disabled_no_secondary_open_and_stop_cleans_both(self):
        from tests.test_v60 import FakeOutput
        engine=AudioEngine(); primary=FakeOutput(); secondary=Mock();off=Mock(return_value=True)
        with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.audio_engine.resolve_device',return_value=1),patch('psrtty.secondary_audio.resolve_device',return_value=2):
            sd.OutputStream.side_effect=[primary,secondary]
            engine.configure_secondary({'enabled':True,'device':2})
            engine.send_text('RY',1,45.45,2125,2295,False,.2,lambda:True,off)
            self.assertTrue(primary.entered.wait(2));engine.stop_tx();primary.release.set();engine.wait_tx()
        secondary.abort.assert_called_once();secondary.close.assert_called_once();off.assert_called_once()
        self.assertFalse(engine._tx_active)
        with patch('psrtty.secondary_audio.resolve_device') as resolve:
            SecondaryOutput(Mock(),np.zeros(1),{'enabled':False},1,48000,{},Mock())
            resolve.assert_not_called()


class Radio108Tests(unittest.TestCase):
    def test_address_and_selected_receiver_filter_preserves_data(self):
        self.assertEqual(RIG_MODELS['IC-7760'],0xB2)
        ctl=CIVController(0xB2,'IC-7760');ctl.ser=Mock();ctl.status=CIVStatus(connected=True)
        def reply(*payload):return bytes([0xfe,0xfe,0xe0,0xb2,*payload,0xfd])
        for data in (0,1,2,3):
            responses=[reply(4,0,2),reply(0x1a,6,data,2 if data else 0)]
            with patch.object(ctl,'_read_response',side_effect=responses):state=ctl.read_filter()
            self.assertEqual(state['mode'],(0,data));self.assertEqual(state['value'],2)
            with patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'read_filter',side_effect=[state,dict(state,value=3)]),patch.object(ctl,'_read_response',return_value=reply(0xfb)):
                self.assertTrue(ctl.set_filter(3,state))
            payload=(0x1a,6,data,3) if data else (6,0,3)
            self.assertEqual(ctl.ser.write.call_args.args[0],ctl._frame(*payload))


class UI108Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp;tearDown=fixture.UITests.tearDown;pump=fixture.UITests.pump

    def test_secondary_ui_bilingual_save_close_and_red_boundary(self):
        from psrtty.ui.secondary_audio_dialog import SecondaryAudioDialog
        for language in ('ja','en'):
            configure(language);save=Mock()
            with patch.object(AudioEngine,'devices',return_value=[(2,'Monitor')]):
                d=SecondaryAudioDialog({},save,self.window)
            self.assertFalse(d.enabled.isChecked());self.assertFalse(d.gain.isEnabled())
            self.assertEqual(d.gain.value(),100);d.enabled.setChecked(True);d.device.setCurrentIndex(1)
            d.gain.setValue(101);self.assertIn('#d32f2f',d.gain.styleSheet())
            d.gain.setValue(100);self.assertNotIn('#d32f2f',d.gain.styleSheet())
            d.gain.setValue(200);d.save_button.click()
            self.assertEqual(save.call_args.args[0],{'enabled':True,'device':2,'gain':2})
            self.assertEqual(d.close_button.text(),tr('閉じる'))
            d.gain.setValue(0);d.close_button.click();save.assert_called_once()
        configure('ja')

    def test_settings_save_primary_unaffected_profiles_and_thanks(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        from psrtty.ui.special_thanks_dialog import SpecialThanksDialog, CALLSIGNS
        d=SettingsDialog(self.store,self.window)
        self.assertGreaterEqual(d.rig.findText('IC-7760'),0)
        d.show(); d.tabs.setCurrentIndex(3); self.pump(.01)
        self.assertTrue(d.secondary_button.isVisible())
        d.tabs.setCurrentIndex(0); self.assertFalse(d.secondary_button.isVisible())
        gain=self.store.data['audio']['tx_gain'];values={'enabled':True,'device':2,'gain':1.8}
        d._save_secondary_audio(values)
        self.assertEqual(self.store.data['audio']['secondary'],values)
        self.assertEqual(self.window.audio.secondary_settings,values)
        self.assertEqual(self.store.data['audio']['tx_gain'],gain)
        d.working_profiles.append(deepcopy(d.working_profiles[0]))
        with self.assertRaises(ValueError): d._save_secondary_audio(dict(values,gain=.5))
        d.reject();self.assertEqual(self.store.data['audio']['secondary'],values)
        self.assertEqual(CALLSIGNS.count('JH1PGF'),1)
        self.assertEqual(CALLSIGNS[CALLSIGNS.index('JH1DUK')+1],'JH1PGF')
        thanks=SpecialThanksDialog(self.window);self.assertEqual(thanks.media_names.text(),'hamlife.jp');thanks.close()

    def test_runtime_icon_and_identity(self):
        from psrtty.app_identity import application_icon, configure_app_identity, APP_ID
        self.assertFalse(application_icon().isNull())
        self.assertGreaterEqual(len(application_icon().availableSizes()),7)
        for size in (16,24,32,48,64,128,256):
            self.assertFalse(application_icon().pixmap(size,size).isNull())
        with patch('psrtty.app_identity.sys',SimpleNamespace(platform='win32')),patch('psrtty.app_identity.ctypes.windll',create=True) as dll:
            dll.shell32.SetCurrentProcessExplicitAppUserModelID.return_value=0
            self.assertTrue(configure_app_identity())
            dll.shell32.SetCurrentProcessExplicitAppUserModelID.assert_called_once_with(APP_ID)

    def test_new_ui_translated(self):
        from psrtty.i18n import TEXT
        root=Path(__file__).resolve().parents[1]
        for name in ('psrtty/ui/secondary_audio_dialog.py','psrtty/secondary_audio.py'):
            for node in ast.walk(ast.parse((root/name).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and isinstance(node.args[0],ast.Constant):
                    value=node.args[0].value
                    self.assertIn(value,TEXT);self.assertNotEqual(value,TEXT[value])
