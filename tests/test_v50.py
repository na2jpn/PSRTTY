import gc
import unittest
from PySide6.QtWidgets import QMenu
from tests.test_ui_v02 import UITests as _Fixture

class UI50Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_header_control_remains_accessible_after_resize(self):
        w=self.window;w.show();self.pump(.05)
        for width in (1130,800):
            w.resize(width,835);self.pump(.05)
            check=w.decode_enabled;box=w.decode_group
            self.assertIs(check.parentWidget(),box.header_control)
            self.assertEqual(box.header_control.y(),0)
            self.assertLessEqual(check.geometry().right(),box.width()-1)
            self.assertGreaterEqual(w.cards_scroll.y(),box.header_control.geometry().bottom())
        check.click();self.assertFalse(w.audio.decode_enabled)
        check.click();self.assertTrue(w.audio.decode_enabled)

    def test_center_tracks_tones_and_shift_in_both_polarities(self):
        w=self.window
        for mark,space,center in ((2125,2295,'2210'),(2146,2316,'2231'),(1500,1671,'1585.5'),(2295,2125,'2210')):
            w._set_tones(mark,space)
            self.assertIn(f'Center {center} Hz',w.tone_label.text())
            self.assertEqual((w.spectrum.mark_hz+w.spectrum.space_hz)/2,float(center))
        w.spectrum.resize(800,110)
        pic=w.spectrum.grab().toImage()
        x=int(w.spectrum._x(2210))
        pixel=pic.pixelColor(x,5)
        self.assertEqual(pixel.red(),pixel.green())
        self.assertGreater(pixel.red(),50)
        self.assertEqual(pic.pixelColor(x,17).name(),'#171717')

    def test_parent_owned_menus_survive_collection(self):
        bar=self.window.menuBar();menus=bar.findChildren(QMenu)
        gc.collect()
        self.assertIn('ヘルプ',[m.title() for m in menus])
        self.assertIn('QSOログ',[a.text() for m in menus for a in m.actions()])

del _Fixture
