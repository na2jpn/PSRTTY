import copy
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QDialogButtonBox
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.macros import NORMAL_TEMPLATE_NAME, TEMPLATE_NAME, CQWW_TEMPLATE_NAME

class UI84Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_template_defaults_cancel_and_save(self):
        before=copy.deepcopy(self.store.data)
        dlg=MacroDialog(self.store)
        for name, sent in [(CQWW_TEMPLATE_NAME,'25'),(TEMPLATE_NAME,'01'),(NORMAL_TEMPLATE_NAME,'')]:
            previous=dlg.sent.text();dlg.template.setCurrentText(name)
            self.assertEqual(dlg.sent.text(),previous)
            dlg._apply_template();self.assertEqual(dlg.sent.text(),sent)
            self.assertTrue(dlg.sent_fixed.isChecked())
        dlg.reject();self.assertEqual(self.store.data,before)
        dlg=MacroDialog(self.store)
        dlg.template.setCurrentText(TEMPLATE_NAME);dlg._apply_template()
        dlg.sent.setText('42');dlg.sent_fixed.setChecked(False);dlg._save()
        reopened=MacroDialog(self.store)
        self.assertEqual(reopened.sent.text(),'42');self.assertFalse(reopened.sent_fixed.isChecked())
        reopened.close()

    def test_main_window_receives_saved_sent(self):
        def save_dialog(dlg):
            dlg.template.setCurrentText(TEMPLATE_NAME);dlg._apply_template();dlg._save()
            return dlg.result()
        with patch.object(MacroDialog,'exec',save_dialog):self.window._edit_macros()
        self.assertEqual(self.window.sent.text(),'01')
        self.assertTrue(self.window.sent_fixed.isChecked())
        self.assertEqual(self.store.data['qso']['sent'],'01')

    def test_japanese_buttons_and_layout(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        from psrtty.ui.backup_dialog import BackupDialog
        for cls in (MacroDialog,SettingsDialog,BackupDialog):
            dlg=cls(self.store, lambda: None) if cls is BackupDialog else cls(self.store)
            box=dlg.findChild(QDialogButtonBox)
            self.assertEqual(box.button(QDialogButtonBox.Save).text(),'保存')
            self.assertEqual(box.button(QDialogButtonBox.Cancel).text(),'キャンセル')
            if cls is MacroDialog:
                dlg.show();self.pump(.03)
                self.assertLess(dlg.sent.geometry().bottom(),box.geometry().top())
                dlg.grab().save('/workspace/scratch/720653aaa76e/psrtty_084_macro_preview.png')
            dlg.close()

del _Fixture
