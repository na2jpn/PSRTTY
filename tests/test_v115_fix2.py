"""Profiles stay at the right edge of the header, independently of wrapping."""
import copy,unittest,time
from unittest.mock import Mock,patch
from psrtty.ui.control_window import ControlWindow
from tests import test_ui_v02 as fixture
class Header115Fix2Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def test_profiles_right_edge(self):
        w=self.window
        w.store.data['profiles']=[copy.deepcopy(w.store.data['profiles'][0]) for _ in range(5)]
        for i,p in enumerate(w.store.data['profiles']):p['name']='Radio '+str(i+1)
        w._refresh_profile_buttons();w.show()
        for width in (1280,820):
            w.resize(width,800);fixture.UITests.pump(self,.6)
            self.assertLessEqual(abs(w.profile_widget.geometry().right()-w.header_widget.contentsRect().right()),2)
            self.assertLess(w.header_left.geometry().right(),w.profile_widget.geometry().left())
            self.assertLessEqual(w.header_widget.width()+20,w.main_viewport.width())

    def test_rx_labels_stay_close(self):
        w=self.window;w.show()
        for width in (1280,820):
            w.resize(width,800);fixture.UITests.pump(self,.2)
            self.assertLessEqual(w.level.geometry().left()-w.level_heading.geometry().right(),8)
            self.assertLessEqual(w.rx_level_notice.geometry().left()-w.level.geometry().right(),8)
    def test_rx_and_gain_share_right_aligned_group(self):
        w=self.window;w.show()
        from PySide6.QtCore import QPoint
        for width in (1280,820,650):
            w.resize(width,800);fixture.UITests.pump(self,.6)
            group=w.rx_gain_controls
            right=group.mapTo(w.spectrum_box,QPoint(group.width(),0)).x()
            self.assertLessEqual(abs(right-(w.spectrum_box.contentsRect().right()-7)),2)
            self.assertIs(w.spectrum_gain_label.parentWidget(),group)
            self.assertIs(w.spectrum_gain.parentWidget(),group)
            self.assertLessEqual(w.spectrum_gain.geometry().left()-w.spectrum_gain_label.geometry().right(),8)
            self.assertLessEqual(abs(w.spectrum_gain.geometry().center().y()-w.level.geometry().center().y()),2)
            tone_right=w.tone_info.mapTo(w.spectrum_box,QPoint(w.tone_info.width(),0)).x()
            group_left=group.mapTo(w.spectrum_box,QPoint()).x()
            tone_bottom=w.tone_info.mapTo(w.spectrum_box,QPoint(0,w.tone_info.height())).y()
            group_top=group.mapTo(w.spectrum_box,QPoint()).y()
            self.assertTrue(tone_right<group_left or tone_bottom<=group_top)

    def test_meter_polling_and_visibility_during_receive(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True;w.active_tx_id=None;w.connecting=False
        w.radio.read_alc.return_value=0;w.radio.read_swr.return_value=1.1;w.radio.read_power.return_value=0
        w.polling=False;w.alc_last_poll=0;w.alc_busy=False
        def immediate(parent,work,done):done(work(),None)
        with patch('psrtty.ui.main_window.BackgroundJob',side_effect=immediate):w._poll_main_alc()
        w.radio.read_alc.assert_called_once()
        self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.radio_meter_text.text(),'SWR --\nPWR 0.0')
        self.assertEqual(w.level_heading.text(),'RX')
        w.meter_updated-=3;w._paint_radio_meters();self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.alc_gauge.color,"#a59d92")
        w.meter_updated=time.monotonic();w.radio.status.connected=False;w._paint_radio_meters()
        self.assertTrue(w.alc_gauge.isHidden());self.assertTrue(w.radio_meter_text.isHidden())
    def test_control_connection_notice(self):
        w=self.window;d=ControlWindow(w)
        self.assertIn('接続',d.connection_notice.text())
        from psrtty.civ import CIVController
        w.radio=CIVController(0x94);w.radio.status.connected=True;d.refresh_enabled();self.assertIn('取得',d.connection_notice.text())
        d.state_observed=True;d.refresh_enabled();self.assertEqual(d.connection_notice.text(),'')
        w.radio.status.connected=False;d.refresh_enabled();self.assertIn('接続',d.connection_notice.text())
        d.close()
