import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import Qt

from tests.test_v75 import UI75Tests as _Fixture, qso, info
from psrtty.adif import ADIFLog, export_adif
from psrtty.cabrillo import build_cabrillo
from psrtty.ui.adif_export_dialog import ADIFExportDialog


class Output88Tests(unittest.TestCase):
    def test_adif_selected_records_and_source_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            log = ADIFLog(Path(directory) / 'source')
            record = qso()
            source = log.append(record)
            original = source.read_bytes()
            output = Path(directory) / 'chosen.adi'
            with self.assertRaises(ValueError):
                export_adif(source, [record], [source])
            export_adif(output, [record], [source])
            self.assertEqual(source.read_bytes(), original)
            parsed = ADIFLog(Path(directory)).load_recent(output)
            self.assertEqual(len(parsed), 1)
            self.assertEqual(parsed[0].sent, '25')
            self.assertEqual(parsed[0].rcvd, '05 MA')
            self.assertIn(b'PROGRAMVERSION', output.read_bytes())

    def test_cqww_converter_headers_and_mixed_calls(self):
        entries = [(qso(), {}), (qso(station_callsign='JA1OTHER', call='K1AAA', rcvd='05 MA'), {})]
        body, errors, warnings = build_cabrillo('cqww', info(**{'MY-CQ-ZONE': '25', 'CQ-REGION': 'JA'}), entries)
        self.assertFalse(errors)
        self.assertIn('CLAIMED-SCORE: \r\n', body)
        self.assertIn('OPERATORS: \r\n', body)
        self.assertIn('LOCATION: DX\r\n', body)
        self.assertEqual(body.count('QSO: '), 2)
        self.assertTrue(any('JA1OTHER' in warning for warning in warnings))
        self.assertTrue(build_cabrillo('cqww', info(NAME='日本語'), entries)[1])


class Wizard88Tests(unittest.TestCase):
    setUpClass = classmethod(_Fixture.setUpClass.__func__)
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown
    pump = _Fixture.pump
    dialog = _Fixture.dialog

    def test_adif_wizard_requires_band_and_qso(self):
        self.store.data['station_callsign'] = 'JH1HST'
        adif = Mock(); adif.load_recent.return_value = [qso(), qso(call='JA1BBB', freq_hz=21085000)]
        adif.read_errors = []
        dialog = ADIFExportDialog(adif, self.store, self.window)
        self.addCleanup(dialog.close)
        dialog.start.setDateTime(dialog.start.dateTime().fromString('2026-09-26 00:00', 'yyyy-MM-dd HH:mm'))
        dialog.end.setDateTime(dialog.end.dateTime().fromString('2026-09-27 23:59', 'yyyy-MM-dd HH:mm'))
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 1, dialog.message.text())
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 1)
        dialog.band_checks['20m'].setChecked(True)
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 2)
        dialog.table.item(0, 0).setCheckState(Qt.Unchecked)
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 2)
        dialog.table.item(0, 0).setCheckState(Qt.Checked)
        dialog.go_next(); self.assertIn('1件', dialog.summary.text())
        target = Path(self.tmp.name) / 'selected.adi'
        with patch('psrtty.ui.adif_export_dialog.QFileDialog.getSaveFileName', return_value=(str(target), '')):
            dialog.go_next()
        self.assertEqual(len(ADIFLog(target.parent).load_recent(target)), 1)

    def test_cqww_warning_and_navigation(self):
        dialog = self.dialog([qso(station_callsign='JA1OTHER')])
        self.assertEqual(dialog.pages.currentIndex(), 1)
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 3)
        self.assertIn('JA1OTHER', dialog.cq_warning.text())
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 2, dialog.error.text())
        dialog.go_next(); self.assertEqual(dialog.pages.currentIndex(), 4, dialog.error.text())
        self.assertIn('JA1OTHER', dialog.warnings.toPlainText())
        dialog.go_back(); self.assertEqual(dialog.pages.currentIndex(), 2)


del _Fixture
