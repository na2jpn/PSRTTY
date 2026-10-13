import time,unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from tests.test_ui_v02 import UITests as Fixture
from tests import test_ui_v02 as fixture
from tests.test_hamlib_089 import FakeLibrary
from psrtty.hamlib_radio import HamlibController,HAMLIB_MODELS
from psrtty.radio import create_controller

class LiveReceiveTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    def setUp(self):
        fixture.UITests.setUp(self)
        self.window.decode_display.setCurrentIndex(self.window.decode_display.findData('live'))
    tearDown=Fixture.tearDown
    def test_characters_visible_before_newline_and_same_card_finalizes_once(self):
        w=self.window
        with patch.object(w,'_consider_auto_extract') as extract,patch.object(w.printer,'submit') as printer:
            for ch in 'CQ JA1ABC':w._rx_char(ch)
            card=w.rx_live_card
            self.assertEqual(w.cards_layout.count(),1);self.assertEqual(card.body.text(),'CQ JA1ABC');self.assertFalse(card.finalized)
            extract.assert_not_called();printer.assert_not_called()
            QTest.mouseClick(card,Qt.LeftButton);extract.assert_not_called()
            w._rx_char('\r');w._rx_char('\n')
            self.assertIs(w.cards_layout.itemAt(0).widget(),card);self.assertTrue(card.finalized);self.assertIsNone(w.rx_live_card)
            extract.assert_called_once_with('CQ JA1ABC');printer.assert_called_once()
    def test_short_preview_removed_on_finalize(self):
        w=self.window;w.store.data['ui']['decode_ignore_chars']=2
        w._rx_char('A');self.assertEqual(w.cards_layout.count(),1)
        w._rx_char('\n');self.assertEqual(w.cards_layout.count(),0)
        for ch in 'ABC\n':w._rx_char(ch)
        self.assertEqual(w.cards_layout.count(),1)
    def test_signal_loss_finalizes_and_mark_wait_keeps_preview(self):
        w=self.window;w._rx_char('A');card=w.rx_live_card
        w.rx_last_char_time=time.monotonic()-3;w.audio.decoder.last_signal_time=time.monotonic()
        w._check_rx_idle();self.assertIs(w.rx_live_card,card)
        w.audio.decoder.last_signal_time=0;w._check_rx_idle();self.assertTrue(card.finalized);self.assertIsNone(w.rx_live_card)
    def test_decode_off_removes_preview_and_stale_characters(self):
        w=self.window;w._rx_char('A');generation=w.audio.decode_generation
        w.decode_enabled.setChecked(False);self.assertEqual(w.cards_layout.count(),0)
        w.decode_enabled.setChecked(True);w._rx_char((generation,'B'));self.assertIsNone(w.rx_live_card)
    def test_long_stream_and_tx_boundary_do_not_duplicate(self):
        w=self.window
        for ch in 'A'*302:w._rx_char(ch)
        self.assertEqual(w.cards_layout.count(),2)
        with patch.object(w,'_consider_auto_extract') as extract:w._finalize_rx_card(extract=False);extract.assert_not_called()
        self.assertEqual(w.cards_layout.count(),2);self.assertIsNone(w.rx_live_card)
    def test_ft891_selection_speed_and_localized_note(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        from psrtty import i18n
        from psrtty.radio_support import connection_note
        d=SettingsDialog(self.store,self.window);d.rig.setCurrentIndex(d.rig.findData('FT-891'))
        self.assertTrue(d.cat_note.isHidden())
        self.assertEqual([d.baud.itemData(i) for i in range(1,d.baud.count())],['38400','19200','9600','4800'])
        for code in i18n.LANGUAGES:
            i18n.configure(code);self.assertIn('FT-891',connection_note('FT-891'));self.assertIn('DATA',connection_note('FT-891'))
        i18n.configure('ja');d.close()

class FT891Tests(unittest.TestCase):
    def test_factory_mode_frequency_ptt_and_meter_fallback(self):
        class Library(FakeLibrary):
            def rig_parse_mode(self,name):return {b'PKTLSB':1024,b'PKTUSB':2048,b'LSB':1,b'USB':2}.get(name,0)
            def rig_parse_level(self,name):return {b'ALC':1,b'SWR':2,b'RFPOWER_METER_WATTS':3,b'RFPOWER_METER':4}.get(name,0)
            def rig_get_level(self,handle,vfo,flag,out):
                if flag==3:return -1
                out._obj.f={1:.1,2:1.2,4:.5}[flag];return 0
        values=dict(model='FT-891',ptt='CAT',com_port='COM3',cat_baud=38400)
        ctl=create_controller(values);self.assertIsInstance(ctl,HamlibController);self.assertEqual(HAMLIB_MODELS['FT-891'][0],1036)
        lib=Library()
        with patch('psrtty.hamlib_radio.load_library',return_value=(lib,None)):
            self.assertTrue(ctl.connect('COM3',38400).connected);self.assertIn(('model',1036),lib.events)
            for mode in ('LSB-D','USB-D'):self.assertTrue(ctl.set_data_mode(mode))
            for mode in ('LSB','USB'):self.assertTrue(ctl.set_operating_mode(mode))
            self.assertEqual(ctl.read_frequency(),14085000);self.assertTrue(ctl.set_ptt(True));self.assertTrue(ctl.set_ptt(False))
            self.assertAlmostEqual(ctl.read_alc(),12,places=4);self.assertAlmostEqual(ctl.read_swr(),1.2,places=4);self.assertAlmostEqual(ctl.read_power(),50)
            ctl.disconnect()


del Fixture
