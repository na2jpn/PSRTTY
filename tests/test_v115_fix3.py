import unittest,time
from unittest.mock import Mock,patch
from tests import test_ui_v02 as fixture
from psrtty.ui.settings_dialog import SettingsDialog
class MeterFix3Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def connect_meter(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True;w.connecting=False
        w.main_meters={'alc':2,'swr':1.7,'pwr':4.61111};w.meter_updated=time.monotonic()
        w.active_tx_id=123;w._paint_radio_meters();return w
    def test_hold_then_receive_defaults_and_resume(self):
        w=self.connect_meter();self.assertEqual(w.radio_meter_text.text(),'SWR 1.7\nPWR 4.6')
        w._hold_tx_meters();w.active_tx_id=None;w.audio._tx_active=False
        w.main_meters={'alc':0,'swr':1,'pwr':0};w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'SWR 1.7\nPWR 4.6');self.assertFalse(w.alc_gauge.isHidden())
        w._meter_hold_until=time.monotonic()-1;w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'SWR --\nPWR 0.0')
        w.active_tx_id=124;w.main_meters={'alc':3,'swr':1.2,'pwr':89.99};w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'SWR 1.2\nPWR 90.0')
    def test_hold_rejects_expired_values_and_honors_switches(self):
        w=self.connect_meter();w._meter_last_tx={k:(v,time.monotonic()-3) for k,(v,t) in w._meter_last_tx.items()}
        w._hold_tx_meters();w.active_tx_id=None;w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'SWR --\nPWR 0.0')
        w.store.data['advanced']['show_swr']=False;w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(),'PWR 0.0')
        w.store.data['advanced']['show_pwr']=False;w._paint_radio_meters();self.assertTrue(w.radio_meter_text.isHidden())
    def test_connection_change_discards_capability_and_hold(self):
        w=self.connect_meter();w._hold_tx_meters();w.active_tx_id=None
        w.connection_generation+=1;w._paint_radio_meters()
        self.assertTrue(w.alc_gauge.isHidden());self.assertTrue(w.radio_meter_text.isHidden())
        self.assertEqual(w._meter_hold_values,{})
    def test_temporary_read_failure_keeps_frame_and_recent_value(self):
        w=self.connect_meter();w.active_tx_id=None;w.alc_busy=False;w.alc_last_poll=0;w.polling=False
        for method in ('read_alc','read_swr','read_power'):getattr(w.radio,method).return_value=None
        w._meter_samples={'alc':(2,time.monotonic()),'swr':(1.7,time.monotonic()),'pwr':(4.6,time.monotonic())}
        def immediate(parent,work,done):done(work(),None)
        with patch('psrtty.ui.main_window.BackgroundJob',side_effect=immediate):w._poll_main_alc()
        self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.alc_gauge.color,'#208341')
        w._meter_samples={k:(v,time.monotonic()-3) for k,(v,t) in w._meter_samples.items()};w.alc_last_poll=0
        with patch('psrtty.ui.main_window.BackgroundJob',side_effect=immediate):w._poll_main_alc()
        self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.alc_gauge.color,'#a59d92')
        self.assertEqual(w.radio_meter_text.text(),'SWR --\nPWR 0.0')
        w.radio.status.connected=False;w._paint_radio_meters()
        self.assertTrue(w.alc_gauge.isHidden());self.assertTrue(w.radio_meter_text.isHidden())
    def test_profile_notice_uses_plain_dialog_without_message_box(self):
        d=SettingsDialog(self.store,self.window);d.show()
        with patch('psrtty.ui.settings_dialog.QMessageBox.information') as native,patch('psrtty.ui.settings_dialog.QDialog.exec',return_value=0) as plain:
            d._show_profile_notice();native.assert_not_called();plain.assert_called_once()
        d.reject()
