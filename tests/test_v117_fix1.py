import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QComboBox
from psrtty.i18n import tr
from psrtty.windows_volume import VolumeState
from psrtty.ui.windows_volume import WindowsVolumeWidget
from psrtty.manual_radio import MANUAL_MODEL
from tests.test_ui_v02 import UITests as Fixture


class WindowsVolumeFix1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_first_session_becomes_available_without_writing_volume(self):
        combo = QComboBox(); combo.addItem('device', {'id': 'chosen'})
        with patch('psrtty.ui.windows_volume.WindowsVolume') as factory:
            backend = factory.return_value
            backend.read.side_effect = RuntimeError('no session before TX')
            widget = WindowsVolumeWidget(combo, 'output')
            self.addCleanup(widget.close)
            self.assertIn(tr('v117.unavailable'), widget.label.text())
            self.assertEqual(widget.meter.format(), tr('v117.unavailable'))
            self.assertFalse(widget.slider.isEnabled())
            self.assertFalse(widget.mute.isEnabled())
            self.assertNotIn('0%', widget.label.text())
            self.assertTrue(widget.slider.styleSheet())
            backend.read.side_effect = None; backend.read.return_value = VolumeState(69, False)
            widget.refresh()
            self.assertTrue(widget.slider.isEnabled())
            self.assertEqual(widget.slider.value(), 69)
            self.assertEqual(widget.slider.styleSheet(), '')
            self.assertEqual(widget.meter.value(), 69)
            backend.set_percent.assert_not_called(); backend.set_mute.assert_not_called()
            # Actual zero is valid, unlike an unavailable session.
            backend.read.return_value = VolumeState(0, True); widget.refresh()
            self.assertTrue(widget.slider.isEnabled()); self.assertTrue(widget.mute.isChecked())
            self.assertIn('0%', widget.label.text())
            # Loss of the session restores the unknown state without a stale mute indication.
            backend.read.side_effect = RuntimeError('session gone'); widget.refresh()
            self.assertFalse(widget.slider.isEnabled()); self.assertFalse(widget.mute.isChecked())
            self.assertEqual(widget.meter.format(), tr('v117.unavailable'))
            backend.set_percent.assert_not_called(); backend.set_mute.assert_not_called()


class RadioOrderFix1Tests(Fixture):
    def test_manual_entry_follows_placeholder_and_selection_survives(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        self.store.data['radio']['model'] = 'FT-710'
        dialog = SettingsDialog(self.store, self.window); self.addCleanup(dialog.close)
        self.assertEqual(dialog.rig.itemData(0), '')
        self.assertEqual(dialog.rig.itemData(1), MANUAL_MODEL)
        self.assertEqual(dialog.rig.currentData(), 'FT-710')
        self.assertEqual(sum(dialog.rig.itemData(i) == MANUAL_MODEL for i in range(dialog.rig.count())), 1)
