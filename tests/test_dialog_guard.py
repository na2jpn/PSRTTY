import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QMessageBox, QFileDialog
from tests.dialog_guard import DialogGuard


class DialogGuardTests(unittest.TestCase):
    def test_reports_message_without_waiting_and_restores(self):
        original=QMessageBox.warning
        guard=DialogGuard();guard.start()
        try:
            with patch('sys.stderr'):
                self.assertEqual(QMessageBox.warning(None,'設定','test reason'),QMessageBox.Ok)
                self.assertEqual(QMessageBox.question(None,'確認','continue?'),QMessageBox.No)
                self.assertEqual(QFileDialog.getSaveFileName(None,'保存'),('',''))
            self.assertEqual(len(guard.events),3)
            self.assertIn('test reason',guard.events[0])
            with patch.object(QMessageBox,'warning') as expected:
                QMessageBox.warning(None,'expected','known');expected.assert_called_once()
            self.assertEqual(len(guard.events),3)
        finally:guard.stop()
        self.assertEqual(QMessageBox.warning,original)
