"""Receive-level guidance without changing audio or decoder settings."""
import unittest
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from psrtty.rx_level import (level_percent,level_color,LowLevelNotice,GRAY,LIGHT_BLUE,GREEN,YELLOW,RED,NOTICE_BLUE)
from psrtty.i18n import configure,TEXT
from psrtty.ui.settings_dialog import SettingsDialog
from tests import test_ui_v02 as fixture

class LevelTests(unittest.TestCase):
    def test_five_bands_and_boundaries(self):
        expected={0:GRAY,5:GRAY,6:LIGHT_BLUE,29:LIGHT_BLUE,30:GREEN,79:GREEN,80:YELLOW,89:YELLOW,90:RED,100:RED}
        for value,color in expected.items():self.assertEqual(level_color(value),color)
    def test_invalid_or_out_of_range_input(self):
        for value in (None,'invalid',float('nan'),float('inf'),-2):self.assertEqual(level_percent(value),0)
        self.assertEqual(level_percent(5),100)
    def test_no_signal_or_no_decoding_never_warns(self):
        hint=LowLevelNotice()
        for now in range(10):hint.level(.15,now);self.assertFalse(hint.visible(now))
        for now in range(10):hint.decoded(now);hint.level(0,now);self.assertFalse(hint.visible(now))
    def test_sustained_low_decode_then_recovery(self):
        h=LowLevelNotice()
        for now in (10,11,12):h.level(.2,now);h.decoded(now);self.assertFalse(h.visible(now))
        h.level(.2,13);h.decoded(13);self.assertTrue(h.visible(13))
        h.level(.5,13.1);self.assertFalse(h.visible(13.1));self.assertIsNone(h.low_since)
    def test_input_or_decoding_loss_and_tx_clear_notice(self):
        for reason in ('input','decode','tx'):
            h=LowLevelNotice();h.low_since=10;h.last_char=13;h.level(.1,13)
            self.assertTrue(h.visible(13))
            if reason=='input':self.assertFalse(h.visible(13.8))
            elif reason=='decode':h.level(.1,15.1);self.assertFalse(h.visible(15.1))
            else:self.assertFalse(h.visible(13,False))
            self.assertIsNone(h.low_since)

class UI109Fix2Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    pump=fixture.UITests.pump

    def test_main_and_settings_share_five_colors(self):
        w=self.window;d=SettingsDialog(self.store,w)
        for value in (0,.059,.06,.39,.4,.7,.71,.89,.9,1.):
            w._rx_level(value);d._refresh_rx_meter()
            from psrtty.rx_level import COLORS
            color=COLORS[w.rx_display.band]
            self.assertIn(color,w.level.styleSheet());self.assertIn(color,d.rx_meter.styleSheet())
        self.assertIn('緑',d.rx_good.text());d.reject()
    def test_status_without_decoded_text(self):
        w=self.window
        for now in range(10):
            with patch('psrtty.ui.main_window.time.monotonic',return_value=now):w._rx_level(.2)
        self.assertEqual(w.rx_level_notice.text(),'Low')
        self.assertFalse(w.rx_level_notice.isHidden())
    def test_decode_disabled_resets_display(self):
        w=self.window;w._rx_level(.95);w.decode_enabled.setChecked(False)
        self.assertEqual(w.level.value(),0);self.assertEqual(w.rx_level_notice.text(),'')
    def test_audio_switch_resets_display(self):
        w=self.window;w._rx_level(.95);w._restart_audio_input()
        self.assertEqual(w.level.value(),0);self.assertEqual(w.rx_level_notice.text(),'')
    def test_guidance_does_not_change_audio_or_display_gain(self):
        w=self.window;original=w.store.data['audio'].copy();gain=w.spectrum.gain_db
        with patch.object(w.audio,'set_rx_gain') as rx,patch.object(w.audio,'configure_decoder') as decoder:
            for value in (.1,.5,.95):w._rx_level(value)
            rx.assert_not_called();decoder.assert_not_called()
        self.assertEqual(w.store.data['audio'],original);self.assertEqual(w.spectrum.gain_db,gain)
    def test_english_short_notice_and_tooltip(self):
        configure('en')
        try:
            self.assertEqual(TEXT['受信レベル低：Audio INを確認'],'Low RX level: check Audio IN')
            d=SettingsDialog(self.store,self.window);self.assertIn('Green',d.rx_good.text());d.reject()
        finally:configure('ja')
    def test_shortcut_guide_remains_open_when_main_activated(self):
        w=self.window;w.show();w._guide_shortcuts();self.pump(.02);g=w.shortcut_window
        self.assertIsNone(g.windowHandle().transientParent());self.assertFalse(g.windowFlags() & Qt.WindowStaysOnTopHint)
        w.raise_();w.activateWindow();QTest.mouseClick(w.manual_tx,Qt.LeftButton);self.pump(.02)
        self.assertIs(QApplication.activeWindow(),w);self.assertTrue(g.isVisible())
        w._guide_shortcuts();self.pump(.02);self.assertIs(QApplication.activeWindow(),g)
