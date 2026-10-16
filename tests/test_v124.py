"""Missing-frequency entry is part of the QSO transaction, before all writes."""
from copy import deepcopy
import unittest
from unittest.mock import Mock,patch

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QDialog,QDialogButtonBox
from psrtty import i18n
from psrtty.adif import QSORecord,adif_record
from psrtty.hamlog_csv import hamlog_row
from psrtty.udp_adif import payload
from psrtty.ui.qso_frequency_dialog import QSOFrequencyDialog,parse_mhz,request_qso_frequency
from tests.test_ui_v02 import UITests as Fixture


class Frequency124Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):i18n.configure('ja')

    def test_decimal_comma_and_fullwidth_values_have_exact_hz(self):
        for text,hz in (('7.045',7045000),('14.085',14085000),('50.303',50303000),
                        ('144.123456',144123456),('1295.5',1295500000),('0.1357',135700),
                        ('7,045',7045000),(' ７．０４５ ',7045000),('7.0450000',7045000)):
            self.assertEqual(parse_mhz(text),hz,text)

    def test_invalid_or_sub_hz_frequency_is_rejected(self):
        for text in ('','NaN','inf','-7.045','0','1e1','7.045 Hz','7,045.2','7.0450001',
                     '15000','999999999999999999999999999999999999'):
            with self.subTest(text=text),self.assertRaises(ValueError):parse_mhz(text)

    def test_dialog_rejects_invalid_input_then_accepts_valid_entry(self):
        i18n.configure('ja');dialog=QSOFrequencyDialog('JA1ABC')
        self.assertIn('JA1ABC',dialog.call_label.text())
        self.assertIn('周波数を指定してください',dialog.explanation.text())
        self.assertEqual(dialog.buttons.button(QDialogButtonBox.Save).text(),'登録')
        dialog.frequency.setText('0');dialog.accept()
        self.assertIsNone(dialog.frequency_hz);self.assertTrue(dialog.error.text())
        dialog.frequency.setText('14.085');dialog.accept()
        self.assertEqual(dialog.result(),QDialog.Accepted);self.assertEqual(dialog.frequency_hz,14085000)
        dialog.deleteLater()

    def test_real_modal_prompt_register_and_cancel(self):
        for accept in (True,False):
            def finish():
                dialog=QApplication.activeModalWidget()
                self.assertIsInstance(dialog,QSOFrequencyDialog)
                dialog.frequency.setText('50.303')
                dialog.accept() if accept else dialog.reject()
            QTimer.singleShot(0,finish)
            self.assertEqual(request_qso_frequency('JA1ABC'),50303000 if accept else None)
            self.app.processEvents()

    def test_eight_language_dialogs_and_valid_band_mapping(self):
        for language in i18n.LANGUAGES:
            i18n.configure(language);dialog=QSOFrequencyDialog('JA1ABC')
            for suffix in ('title','explanation','call','frequency','examples','register','invalid'):
                self.assertNotEqual(i18n.tr('v124.'+suffix),'v124.'+suffix)
            self.assertIn('JA1ABC',dialog.call_label.text());self.assertIn('7.045',dialog.examples.text())
            dialog.deleteLater()
        for text,band in (('7.045','40m'),('14.085','20m'),('50.303','6m'),('1295.5','23cm')):
            self.assertEqual(QSORecord('JA1ABC',freq_hz=parse_mhz(text)).band,band)


class Logging124Tests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown

    def values(self):
        w=self.window;w.qsos=[];w.q_call.setText('JA1ABC');w.his_call.setText('JA1ABC')
        w.sent_fixed.setChecked(False);w.sent.setText('009');w.rcvd.setText('015')
        w.q_datetime.setText('2026-10-16 23:10');w.adif.append.reset_mock();w.store.save.reset_mock()
        return w

    def test_known_frequency_never_prompts(self):
        w=self.values();w.current_freq_hz=14085000
        with patch('psrtty.ui.main_window.request_qso_frequency') as prompt,patch.object(w.integration,'record') as record:
            w._add_qso();prompt.assert_not_called()
            self.assertEqual(w.qsos[0].freq_hz,14085000);self.assertEqual(w.sent.text(),'010')
            self.assertIs(record.call_args.args[0],w.qsos[0])

    def test_input_frequency_and_band_go_to_adif_hamlog_and_udp(self):
        w=self.values();w.current_freq_hz=None;w.last_known_freq_hz=None
        with patch('psrtty.ui.main_window.request_qso_frequency',return_value=7045000) as prompt,patch.object(w.integration,'record') as record:
            w._add_qso();prompt.assert_called_once_with('JA1ABC',w)
            q=w.qsos[0];self.assertIs(w.adif.append.call_args.args[0],q);self.assertIs(record.call_args.args[0],q)
            self.assertEqual(q.freq_hz,7045000);self.assertEqual(q.band,'40m')
            self.assertIn('<FREQ:5>7.045',adif_record(q));self.assertIn('<BAND:3>40m',adif_record(q))
            self.assertIn(b'<FREQ:5>7.045',payload(q));self.assertIn(b'<BAND:3>40m',payload(q))
            self.assertEqual(hamlog_row(q)[5],'7.045')
            self.assertIsNone(w.current_freq_hz);self.assertIsNone(w.last_known_freq_hz)

    def test_cancel_preserves_all_qso_fields_and_has_no_side_effects(self):
        w=self.values();data=deepcopy(w.store.data);stamp=w.q_datetime.text()
        with patch('psrtty.ui.main_window.request_qso_frequency',return_value=None),patch.object(w.integration,'record') as record:
            w._add_qso();w.adif.append.assert_not_called();record.assert_not_called();w.store.save.assert_not_called()
        self.assertEqual(w.store.data,data);self.assertEqual(w.q_call.text(),'JA1ABC');self.assertEqual(w.sent.text(),'009')
        self.assertEqual(w.rcvd.text(),'015');self.assertEqual(w.q_datetime.text(),stamp);self.assertFalse(w.qsos)

    def test_external_manual_mode_requires_entry_despite_old_radio_frequency(self):
        w=self.values();w.store.data['radio']['model']='EXTERNAL-MANUAL'
        w.current_freq_hz=14085000;w.last_known_freq_hz=14085000
        with patch('psrtty.ui.main_window.request_qso_frequency',return_value=50303000) as prompt,patch.object(w.integration,'record'):
            w._add_qso();prompt.assert_called_once();self.assertEqual(w.qsos[0].freq_hz,50303000)

    def test_last_known_frequency_is_used_under_existing_disconnected_rule(self):
        w=self.values();w.current_freq_hz=None;w.last_known_freq_hz=21085000
        with patch('psrtty.ui.main_window.request_qso_frequency') as prompt,patch.object(w.integration,'record'):
            w._add_qso();prompt.assert_not_called();self.assertEqual(w.qsos[0].freq_hz,21085000)

    def test_modal_reentry_cannot_duplicate_log_or_increment(self):
        w=self.values()
        def answer(*args):w._add_qso();return 14085000
        with patch('psrtty.ui.main_window.request_qso_frequency',side_effect=answer),patch.object(w.integration,'record') as record:
            w._add_qso();w.adif.append.assert_called_once();record.assert_called_once()
        self.assertEqual(len(w.qsos),1);self.assertEqual(w.sent.text(),'010');self.assertFalse(w._adding_qso)

    def test_adif_failure_after_entry_does_not_transfer_or_increment(self):
        w=self.values();w.adif.append.side_effect=OSError('disk full')
        with patch('psrtty.ui.main_window.request_qso_frequency',return_value=14085000),patch.object(w.integration,'record') as record,patch('psrtty.ui.main_window.QMessageBox.warning'):
            w._add_qso();record.assert_not_called()
        self.assertFalse(w.qsos);self.assertEqual(w.sent.text(),'009');self.assertEqual(w.q_call.text(),'JA1ABC')

    def test_auto_logging_asks_once_after_success_and_respects_cancel(self):
        for frequency in (None,14085000):
            w=self.values();w.adif.append.reset_mock();w.auto_log.setChecked(True);w.active_tx_id=124
            w.pending_auto_log=(w._macro_values(),w.qso_revision,w.current_freq_hz)
            with patch('psrtty.ui.main_window.request_qso_frequency',return_value=frequency) as prompt,patch.object(w.integration,'record') as record:
                w._tx_finished(True,'OK',124);prompt.assert_called_once_with('JA1ABC',w)
                self.assertEqual(w.adif.append.call_count,int(frequency is not None));self.assertEqual(record.call_count,int(frequency is not None))
                self.assertEqual(w.sent.text(),'009' if frequency is None else '010')

    def test_closing_during_entry_aborts_before_save(self):
        w=self.values()
        def answer(*args):w.closing=True;return 14085000
        try:
            with patch('psrtty.ui.main_window.request_qso_frequency',side_effect=answer),patch.object(w.integration,'record') as record:
                w._add_qso();w.adif.append.assert_not_called();record.assert_not_called()
        finally:w.closing=False


del Fixture
