import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from copy import deepcopy
from psrtty.alc_display import classify,signature,calibration_onset
from psrtty.i18n import configure,tr
from psrtty.config import ConfigStore
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.ui.guide import GuideWindow
from tests import test_ui_v02 as fixture

class ALC110Tests(unittest.TestCase):
    def test_shared_good_criteria(self):
        self.assertEqual(classify(0,46,50),(True,'#208341'))
        for value,gain,onset in ((0,35,None),(2,46,50),(0,50,50),(0,44,50)):
            self.assertFalse(classify(value,gain,onset)[0])
        self.assertEqual(classify(10,35,None)[1],'#c0392b')
        self.assertEqual(classify(2,35,None)[1],'#c98722')
    def test_calibration_invalidated_by_radio_or_output(self):
        radio={'model':'IC-705','com_port':'COM5'}
        audio={'output_device':'dev','alc_calibration':{'onset':50,'signature':signature(radio,'dev')}}
        self.assertEqual(calibration_onset(audio,radio),50)
        self.assertIsNone(calibration_onset(audio,{**radio,'com_port':'COM6'}))
        audio['output_device']='other';self.assertIsNone(calibration_onset(audio,radio))
    def test_calibration_and_languages_persist(self):
        with tempfile.TemporaryDirectory() as tmp:
            for lang in ('ja','en','ru','zh','ko'):
                s=ConfigStore(Path(tmp)/'config.json',Path(tmp)/'macro.json');s.data['ui']['language']=lang
                s.data['audio']['alc_calibration']={'onset':50,'signature':signature(s.data['radio'],s.data['audio']['output_device'])}
                s.save();loaded=ConfigStore(Path(tmp)/'config.json',Path(tmp)/'macro.json')
                self.assertEqual(loaded.data['ui']['language'],lang)
                self.assertEqual(calibration_onset(loaded.data['audio'],loaded.data['radio']),50)
    def test_native_short_labels_and_technical_names(self):
        try:
            for lang in ('ru','zh','ko'):
                configure(lang);self.assertNotEqual(tr('保存'),'Save');self.assertNotEqual(tr('無線機確認'),'Check rig')
                self.assertEqual(tr('Good'),'Good');self.assertEqual(tr('Audio IN'),'Audio IN')
        finally:configure('ja')

class UI110Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def test_tx_blocks_rx_updates_but_does_not_change_spectrum(self):
        w=self.window;gain=w.spectrum.gain_db;w.active_tx_id=1;w.main_alc=12;w._paint_main_alc()
        for x in (.1,.5,.99):w._rx_level(x)
        self.assertEqual(w.level.value(),12);self.assertEqual(w.level_heading.text(),'ALC');self.assertEqual(w.spectrum.gain_db,gain)
        w.active_tx_id=None;w._tx_finished(False,'stopped')
        self.assertEqual(w.level_heading.text(),'RX');self.assertEqual(w.level.maximum(),100)
    def test_unknown_alc_is_gray_and_check_rig(self):
        w=self.window;w.active_tx_id=1;w.main_alc=None;w._paint_main_alc()
        self.assertIn('#a59d92',w.level.styleSheet());self.assertEqual(w.rx_level_notice.text(),'無線機確認')
    def test_main_and_audio_out_use_same_good_and_color(self):
        w=self.window;au=w.store.data['audio'];au['tx_gain']=.46
        au['alc_calibration']={'onset':50,'signature':signature(w.store.data['radio'],au['output_device'])}
        d=SettingsDialog(self.store,w);d.alc_onset=50;d.tx_gain.setValue(46)
        w.active_tx_id=1
        for value in (0,2,10):
            w.main_alc=value;w._paint_main_alc();d._show_alc(value)
            good,color=classify(value,46,50)
            self.assertIn(color,w.level.styleSheet());self.assertIn(color,d.alc_meter.styleSheet())
            self.assertEqual(w.rx_level_notice.text()=='Good',good)
        w.active_tx_id=None;d.reject()
    def test_three_native_guides_open(self):
        try:
            for lang in ('ru','zh','ko'):
                configure(lang);g=GuideWindow(self.window)
                self.assertGreater(g.tabs.count(),1);text=g.tabs.widget(0).toPlainText()
                self.assertIn('ALC',text);self.assertIn('Good',text);self.assertTrue(any('F11' in g.tabs.widget(i).toPlainText() for i in range(g.tabs.count())));g.close()
        finally:configure('ja')
    def test_language_menu_has_supported_choices(self):
        self.assertEqual({a.data() for a in self.window.language_group.actions()},set(__import__('psrtty.i18n',fromlist=['LANGUAGES']).LANGUAGES))

    def test_async_alc_callback_rejects_old_tx(self):
        w=self.window;w.active_tx_id=1;callbacks=[]
        with patch.object(w,'radio',SimpleNamespace(read_alc=lambda:99)),patch.object(w,'polling',False),patch.object(w,'_connected',return_value=True),patch('psrtty.ui.main_window.BackgroundJob',side_effect=lambda parent,work,done:callbacks.append(done)),patch('psrtty.ui.main_window.time.monotonic',return_value=100):
            w._poll_main_alc()
        self.assertEqual(len(callbacks),1);w.active_tx_id=2;callbacks[0](99,None)
        self.assertIsNone(w.main_alc);self.assertFalse(w.alc_busy)
    def test_audio_in_does_not_show_tx_alc(self):
        w=self.window;w.rx_display.percent=20;w.rx_display.band=1;w.active_tx_id=1;w.main_alc=110;w._paint_main_alc()
        d=SettingsDialog(self.store,w);d._refresh_rx_meter()
        self.assertEqual(d.rx_meter.value(),20);self.assertEqual(d.rx_state.text(),'Low');w.active_tx_id=None;d.reject()
