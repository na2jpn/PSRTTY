import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, Mock
from PySide6.QtWidgets import QMessageBox
from PySide6.QtGui import QCloseEvent
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.adif import ADIFLog, QSORecord
from psrtty.logging_store import TranscriptLogger
from psrtty.backup import check_log_writable, create_log_backup
from psrtty.ui.backup_dialog import BackupDialog


class Storage74Tests(unittest.TestCase):
    def test_month_daily_rollover_and_probe(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'logdata';check_log_writable(root)
            self.assertEqual(list(root.iterdir()),[])
            adif=ADIFLog(root);raw=TranscriptLogger(root)
            self.assertEqual(adif.path_for(datetime(2026,9,25)).name,'202609.adi')
            self.assertEqual(adif.path_for(datetime(2026,10,1)).name,'202610.adi')
            self.assertEqual(raw.path_for(datetime(2026,9,25)).name,'20260925_all.txt')
            adif.append(QSORecord('JH1HST'),datetime(2026,9,25))
            adif.append(QSORecord('JQ7FIU'),datetime(2026,9,26))
            self.assertEqual(len(adif.load_recent()),2)
            self.assertEqual(len(list(root.glob('*.adi'))),1)
            with patch('psrtty.backup.os.fsync',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):check_log_writable(root)
            self.assertEqual(list(root.glob('.psrtty-write-*')),[])

    def test_backup_contents_unique_and_failure(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);self.assertIsNone(create_log_backup(root))
            (root/'202609.adi').write_bytes(b'adif')
            (root/'20260925_all.txt').write_bytes(b'raw')
            (root/'config.json').write_bytes(b'ignore')
            a=create_log_backup(root);b=create_log_backup(root);self.assertNotEqual(a,b)
            with zipfile.ZipFile(a) as z:
                self.assertEqual(set(z.namelist()),{'202609.adi','20260925_all.txt'})
                self.assertEqual(z.read('202609.adi'),b'adif')
            with patch('psrtty.backup.os.replace',side_effect=OSError('no space')):
                with self.assertRaises(OSError):create_log_backup(root)
            self.assertEqual(len(list((root/'backups').glob('*.zip'))),2)
            self.assertEqual(list((root/'backups').glob('*.tmp')),[])
            self.assertEqual((root/'202609.adi').read_bytes(),b'adif')


class UI74Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_startup_failure_never_constructs_mainwindow(self):
        from psrtty import app
        with patch.object(app,'QApplication',return_value=self.app), patch.object(app,'app_root',return_value=Path(self.tmp.name)), patch.object(app,'check_log_writable',side_effect=PermissionError('read only')), patch.object(app,'MainWindow') as main, patch.object(app.QMessageBox,'critical') as message:
            self.assertEqual(app.run(),1);main.assert_not_called()
            self.assertIn('read only',message.call_args.args[2])

    def test_count_success_failure_manual_and_exit_once(self):
        w=self.window;w.store.data['backup'].update(on_exit=True,every_enabled=True,every_count=2,pending_qsos=0)
        w.adif.append.return_value=Path('202609.adi')
        with patch('psrtty.backup.create_log_backup',return_value=Path('saved.zip')) as backup, patch.object(QMessageBox,'information'), patch.object(QMessageBox,'warning'):
            w.q_call.setText('JH1HST');w._add_qso();backup.assert_not_called()
            w.q_call.setText('JQ7FIU');w._add_qso();self.assertEqual(backup.call_count,1)
            self.assertEqual(w.store.data['backup']['pending_qsos'],0)
            w.adif.append.side_effect=OSError('disk full');w.q_call.setText('W1AW');w._add_qso()
            self.assertEqual(w.store.data['backup']['pending_qsos'],0)
            w.store.data['backup']['pending_qsos']=2
            backup.side_effect=OSError('disk full');self.assertFalse(w._backup_logs())
            self.assertEqual(w.store.data['backup']['pending_qsos'],2)
            backup.side_effect=None;w._backup_logs(manual=True)
            self.assertEqual(w.store.data['backup']['pending_qsos'],0)
            backup.reset_mock()
            w.closing=True;w.audio_input_busy=False;w.audio._tx_active=False
            w.closeEvent(QCloseEvent());w.closeEvent(QCloseEvent())
            backup.assert_called_once()

    def test_settings_cancel_failure_and_menu_dates(self):
        d=BackupDialog(self.store,Mock())
        try:
            d.on_exit.setChecked(False);d.every.setChecked(True);d.count.setValue(7)
            self.store.save.side_effect=OSError('denied')
            with patch.object(QMessageBox,'warning'):d._save()
            self.assertTrue(self.store.data['backup']['on_exit'])
            self.assertNotEqual(d.result(),1)
            self.store.save.side_effect=None;d._save()
            self.assertEqual(self.store.data['backup']['every_count'],7)
            self.assertFalse(self.store.data['backup']['on_exit'])
        finally:
            self.store.save.side_effect=None
            d.close()
        with patch('psrtty.ui.main_window.datetime') as dt:
            dt.now.return_value=datetime(2026,10,1);self.window._refresh_log_menu()
            self.assertEqual('今月のADIFを開く（UTC基準）',self.window.adif_action.text())
            self.assertEqual('今日の生ログTXTを開く（JST基準）',self.window.transcript_action.text())

del _Fixture
