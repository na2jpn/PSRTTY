"""HAMLOG RST setup example stays visible and is shipped in frozen builds."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from psrtty import i18n
from psrtty.paths import resource_path
from tests.test_ui_v02 import UITests as _Fixture


class HamlogFix2Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_example_image_and_red_concrete_instruction_in_eight_languages(self):
        from psrtty.ui.integration_dialog import HamlogSettingsDialog
        from PySide6.QtGui import QColor
        for code in i18n.LANGUAGES:
            with self.subTest(language=code):
                i18n.configure(code);d=HamlogSettingsDialog(self.window.integration,self.window)
                d.show();self.pump(.02)
                self.assertIn('RTTY=5*9',d.rtty_setup_note.text())
                self.assertIn('599',d.rtty_setup_note.text())
                color=d.rtty_setup_note.palette().color(d.rtty_setup_note.foregroundRole())
                self.assertEqual(color,QColor('#c62828'))
                self.assertFalse(d.rtty_setup_image.pixmap().isNull())
                self.assertEqual((d.rtty_setup_image.pixmap().width(),d.rtty_setup_image.pixmap().height()),(432,44))
                self.assertTrue(d.rtty_setup_image.isVisible())
                self.assertLessEqual(d.rtty_setup_image.geometry().right(),d.width())
                self.assertIn('RTTY=5*9',d.rtty_setup_image.accessibleName())
                self.assertIn(d.rtty_setup_note.text(),i18n.tr('guide.8.body'))
                self.assertFalse(hasattr(d,'search_button'))
                d.close();d.deleteLater()
        i18n.configure('ja')

    def test_exact_supplied_asset_and_pyinstaller_resource_path(self):
        root=Path(__file__).resolve().parents[1]
        asset=root/'assets/hamlog_rst599.png'
        self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(),
            'c2271152050805b1873c313316bd1f290d12d2db593c2f73ea32ebdcb0dbf343')
        self.assertIn("('assets/hamlog_rst599.png', 'assets')",(root/'psrtty.spec').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as td,patch('psrtty.paths.sys._MEIPASS',td,create=True):
            self.assertEqual(resource_path('assets/hamlog_rst599.png'),Path(td)/'assets/hamlog_rst599.png')

del _Fixture
