import unittest
from unittest.mock import Mock
from PySide6.QtWidgets import QFormLayout, QPushButton
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.adif import QSORecord
from psrtty.ui.formatting import band_mhz
from psrtty.ui.settings_dialog import SettingsDialog


class UI102Tests(unittest.TestCase):
    setUpClass = classmethod(_Fixture.setUpClass.__func__)
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    pump = _Fixture.pump

    def test_frequency_retained_only_after_radio_observation(self):
        w = self.window
        w.qsos = []
        w.q_call.setText('JA1AAA')
        w._add_qso()
        first = w.adif.append.call_args.args[0]
        self.assertIsNone(first.freq_hz)
        w.radio = Mock()
        w.radio.status.connected = True
        w._radio_observed(21085000)
        w.disconnect_radio()
        self.assertIn('21.085.000', w.freq_label.text())
        self.assertIn('#888888', w.freq_label.styleSheet())
        w.q_call.setText('JA1BBB')
        w._add_qso()
        second = w.adif.append.call_args.args[0]
        self.assertEqual(second.freq_hz, 21085000)
        self.assertEqual(band_mhz(second), '21')
        self.assertEqual(w.latest_table.horizontalHeaderItem(2).text(), 'BAND')
        self.assertEqual(w.latest_table.item(0, 2).text(), '21')
        self.pump(.05)

    def test_connected_without_new_frequency_does_not_use_old_one(self):
        w = self.window
        w.last_known_freq_hz = 14085000
        w.radio = Mock()
        w.radio.status.connected = True
        w.q_call.setText('JA1CCC')
        w._add_qso()
        self.assertIsNone(w.adif.append.call_args.args[0].freq_hz)

    def test_latest_two_columns_with_wide_windows_font(self):
        w = self.window
        font = w.latest_table.font()
        font.setPointSize(20)
        w.latest_table.setFont(font)
        w.latest_panel.resize(1200, 100)
        w._refresh_latest_qsos()
        self.assertFalse(w.latest_right.isHidden())
        self.assertLessEqual(w.latest_table.horizontalHeader().length(), w.latest_table.width())
        w.latest_panel.resize(450, 100)
        w._refresh_latest_qsos()
        self.assertTrue(w.latest_right.isHidden())

    def test_audio_out_status_shares_refresh_button_row(self):
        dlg = SettingsDialog(self.store, self.window)
        dlg.show()
        self.assertTrue(dlg.audio_out_status.isHidden())
        self.assertEqual(dlg.audio_out_status.objectName(), '')
        dlg.audio_out.addItem('以前の機器（未接続／無効）',
                              {'backend': 'old', 'id': 'missing', 'kind': 'output', 'name': '以前の機器'})
        dlg.audio_out.setCurrentIndex(dlg.audio_out.count() - 1)
        self.assertFalse(dlg.audio_out_status.isHidden())
        self.assertIn('現在は使えません', dlg.audio_out_status.text())
        refresh = next(b for b in dlg.findChildren(QPushButton)
                       if b.text() == '音声デバイスを再検出')
        form = dlg.audio_out.parentWidget().layout()
        self.assertIsInstance(form, QFormLayout)
        self.assertTrue(any((row := form.itemAt(i, QFormLayout.FieldRole)) and row.layout()
                            and row.layout().indexOf(refresh) >= 0
                            and row.layout().indexOf(dlg.audio_out_status) >= 0
                            for i in range(form.rowCount())))
        dlg.reject()


del _Fixture
