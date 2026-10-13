import unittest,time
from unittest.mock import Mock,patch
from tests import test_ui_v02 as fixture
from psrtty.ui.tx_meters import ALCGauge,swr_color
from psrtty.ui.audio_usb_help import ProfileAudioNotice
from psrtty.ui.guide import GuideWindow
from psrtty.ui.special_thanks_dialog import CALLSIGNS
from psrtty import i18n
class Fix4Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def meter(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True;w.connecting=False;w.active_tx_id=9
        w.main_meters={'alc':0,'swr':2.2,'pwr':0};w.meter_updated=time.monotonic();w._paint_radio_meters();return w
    def test_cyan_tx_cue_is_not_receive_headroom(self):
        g=ALCGauge()
        for onset in (None,40):
            g.set_reading(0,30,onset,True);self.assertAlmostEqual(g.position,.35*.85);self.assertEqual(g.color,'#70cde5')
            g.set_reading(0,30,onset,False);self.assertEqual(g.position,0)
        g.set_reading(2,40,40,True);self.assertEqual(g.color,'#208341');self.assertEqual(g.position,.35)
        g.set_reading(3,40,40,True);self.assertEqual(g.color,'#e88919')
    def test_swr_boundaries(self):
        for value,color in ((None,None),(1.799,None),(1.8,'#df7900'),(2.199,'#df7900'),(2.2,'#d94324'),(2.799,'#d94324'),(2.8,'#d00000')):
            self.assertEqual(swr_color(value),color)
    def test_two_second_hold_keeps_color_then_resets(self):
        w=self.meter();base=time.monotonic()
        with patch('psrtty.ui.main_window.time.monotonic',return_value=base):w._hold_tx_meters()
        self.assertAlmostEqual(w._meter_hold_until,base+2)
        w.active_tx_id=None;w.audio._tx_active=False;w.main_meters={'alc':0,'swr':1,'pwr':0}
        with patch('psrtty.ui.main_window.time.monotonic',return_value=base+1.5):w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'SWR 2.2\nPWR 0.0');self.assertIn('#d94324',w.radio_meter_text.swr_label.styleSheet())
        self.assertEqual(w.radio_meter_text.pwr_label.styleSheet(),'')
        with patch('psrtty.ui.main_window.time.monotonic',return_value=base+2):w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'SWR --\nPWR 0.0');self.assertEqual(w.radio_meter_text.swr_label.styleSheet(),'')
    def test_zero_warning_requires_current_valid_tx_reading(self):
        w=self.meter();base=time.monotonic();w._meter_tx_started=base;w.polling=False;w.alc_busy=False
        w.radio.read_alc.return_value=0;w.radio.read_swr.return_value=1.1;w.radio.read_power.return_value=0
        def immediate(parent,work,done):done(work(),None)
        def poll(at):
            w.alc_last_poll=0
            with patch('psrtty.ui.main_window.time.monotonic',return_value=base+at),patch('psrtty.ui.main_window.BackgroundJob',side_effect=immediate):w._poll_main_alc()
        poll(.5);self.assertTrue(w.audio_check_notice.isHidden())
        poll(1.1);self.assertFalse(w.audio_check_notice.isHidden());self.assertIn('Audio',w.audio_check_notice.text())
        w.radio.read_power.return_value=None;poll(1.2);self.assertTrue(w.audio_check_notice.isHidden())
        w.radio.read_power.return_value=0;poll(1.3);self.assertFalse(w.audio_check_notice.isHidden())
        w.radio.read_power.return_value=.01;poll(1.4);self.assertTrue(w.audio_check_notice.isHidden())
        w.radio.read_power.return_value=0;poll(1.5);w.active_tx_id=None;w._paint_radio_meters();self.assertTrue(w.audio_check_notice.isHidden())
    def test_warning_stale_or_disconnected_is_hidden(self):
        w=self.meter();now=time.monotonic();w._meter_tx_started=now-2;w._pwr_warning_read=(0,now-1,w.active_tx_id)
        w._paint_radio_meters();self.assertTrue(w.audio_check_notice.isHidden())
        w._pwr_warning_read=(0,now,w.active_tx_id);w.radio.status.connected=False;w._paint_radio_meters();self.assertTrue(w.audio_check_notice.isHidden())
    def test_thanks_order_and_unique_entries(self):
        wanted=('JG2AJK','JA3LVJ','JF3RRP','JP3GMO','JK4JMO','JQ7FIU');start=CALLSIGNS.index('JG2AJK')
        self.assertEqual(CALLSIGNS[start:start+len(wanted)],wanted)
        for name in wanted:self.assertEqual(CALLSIGNS.count(name),1)
    def test_illustration_in_notice_and_audio_guide_all_languages(self):
        from PySide6.QtGui import QTextDocument
        from PySide6.QtCore import QUrl
        from psrtty.paths import resource_path
        for code in ('ja','en','ru','zh','ko','id','th','es'):
            i18n.configure(code)
            n=ProfileAudioNotice(self.window);g=GuideWindow(self.window);b=g.tabs.widget(0)
            for browser in (n.browser,b):
                self.assertIn(i18n.tr('v115fix4.usb_check'),browser.toPlainText())
                img=browser.document().resource(QTextDocument.ImageResource,QUrl.fromLocalFile(str(resource_path('assets/audio_usb_examples.png'))))
                self.assertIsNotNone(img);self.assertFalse(img.isNull())
            n.close();g.close()
        i18n.configure('ja')
