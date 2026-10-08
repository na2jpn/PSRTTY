"""Display smoothing, exact settled thresholds, shared labels, and reset."""
import unittest
from unittest.mock import patch
from psrtty.rx_level import LevelDisplay,level_band,LABELS,COLORS,TEXT_COLORS
from psrtty.i18n import configure
from psrtty.ui.settings_dialog import SettingsDialog
from tests import test_ui_v02 as fixture

class DisplayTests(unittest.TestCase):
    def test_settled_boundaries(self):
        for percent,band in ((0,0),(5,0),(6,1),(29,1),(30,2),(79,2),(80,3),(89,3),(90,4),(100,4)):
            d=LevelDisplay()
            for i in range(150):v=d.update(percent/100,i*.05)
            self.assertEqual(v,percent);self.assertEqual(d.band,band);self.assertEqual(level_band(percent),band)
    def test_fast_rise_slow_fall_and_no_overshoot(self):
        d=LevelDisplay();d.update(0,0);up=d.update(.7,.1)
        self.assertGreater(up,30);self.assertLess(up,70)
        d.update(.7,4);peak=d.percent;d.update(0,4.1)
        self.assertGreater(d.percent,peak*.7);self.assertGreater(d.percent,0)
    def test_boundary_jitter_and_immediate_over(self):
        d=LevelDisplay()
        for i in range(40):d.update(.79,i*.1)
        bands=[d.band]
        for i in range(40):
            d.update(.795 if i%2 else .805,4+i*.02);bands.append(d.band)
        self.assertLessEqual(sum(a!=b for a,b in zip(bands,bands[1:])),1)
        d.update(.95,5);self.assertEqual(d.band,4);self.assertGreaterEqual(d.percent,95)
    def test_reset_discards_previous_envelope(self):
        d=LevelDisplay();d.update(1,1);d.reset()
        self.assertEqual(d.band,0);self.assertEqual(d.percent,0);self.assertIsNone(d.last_time)

class UI109Fix3Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def settle(self,value):
        for i in range(150):
            with patch('psrtty.ui.main_window.time.monotonic',return_value=100+i*.05):self.window._rx_level(value)
    def test_both_meters_share_labels_and_colors_in_both_languages(self):
        for lang in ('ja','en'):
            configure(lang);d=SettingsDialog(self.store,self.window)
            for v,band in ((0,0),(.2,1),(.3,2),(.8,3),(.95,4)):
                self.window.rx_display.reset();self.settle(v);d._refresh_rx_meter()
                self.assertEqual(self.window.rx_level_notice.text(),LABELS[band]);self.assertEqual(d.rx_state.text(),LABELS[band])
                self.assertEqual(d.rx_meter.value(),self.window.level.value())
                for widget in (self.window.level,d.rx_meter):self.assertIn(COLORS[band],widget.styleSheet())
                for widget in (self.window.rx_level_notice,d.rx_state):self.assertIn(TEXT_COLORS[band],widget.styleSheet())
            self.assertIn('30',d.rx_good.text());self.assertIn('79',d.rx_good.text());d.reject()
        configure('ja')
    def test_stale_input_clears_label_and_meter(self):
        self.settle(.95)
        with patch('psrtty.ui.main_window.time.monotonic',return_value=109):self.window._refresh_rx_level_notice()
        self.assertEqual(self.window.level.value(),0);self.assertEqual(self.window.rx_level_notice.text(),'')
    def test_status_is_next_to_main_meter(self):
        self.window.show();self.settle(.5)
        meter=self.window.level.geometry();label=self.window.rx_level_notice.geometry()
        self.assertGreaterEqual(label.left(),meter.right());self.assertLess(abs(label.center().y()-meter.center().y()),10)
