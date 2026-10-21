import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from psrtty.log_retention import prune_log_backups
from psrtty.backup import create_log_backup


class LogRetention128Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folder = self.root/'backups'
        self.folder.mkdir()

    def snapshot(self, i):
        p = self.folder/f'PSRTTY_logs_20261021_0000{i:02d}_abcdef01.zip'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('202610.adi', '<EOH><CALL:6>JH1HST<EOR>')
        return p

    def bak(self, month, i):
        p = self.folder/f'{month}.adi.20261021_0000{i:02d}_abcdef01.bak'
        p.write_text('<EOH><CALL:6>JH1HST<EOR>', encoding='utf-8')
        return p

    def test_existing_copies_per_month_and_live_files(self):
        live = self.root/'202610.adi'; live.write_bytes(b'QSO original')
        txt = self.root/'20261021_all.txt'; txt.write_bytes(b'RX original')
        unknown = self.folder/'my-copy.zip'; unknown.write_bytes(b'private')
        move = self.folder/'month_move_abcdef'; move.mkdir(); (move/'202610.adi').write_bytes(b'recovery')
        for i in range(8):
            self.snapshot(i); self.bak('202609',i); self.bak('202610',i)
        self.assertEqual(prune_log_backups(self.root),15)
        self.assertEqual(len(list(self.folder.glob('PSRTTY_logs_*.zip'))),3)
        self.assertEqual(len(list(self.folder.glob('202609*.bak'))),3)
        self.assertEqual(len(list(self.folder.glob('202610*.bak'))),3)
        self.assertEqual(live.read_bytes(),b'QSO original')
        self.assertEqual(txt.read_bytes(),b'RX original')
        self.assertEqual(unknown.read_bytes(),b'private')
        self.assertEqual((move/'202610.adi').read_bytes(),b'recovery')
        self.assertEqual(prune_log_backups(self.root),0)

    def test_corrupt_new_zip_preserves_all(self):
        files=[self.snapshot(i) for i in range(5)]
        files[-1].write_bytes(b'corrupt')
        with self.assertRaises(zipfile.BadZipFile):prune_log_backups(self.root)
        self.assertTrue(all(p.exists() for p in files))

    def test_corrupt_new_bak_preserves_all(self):
        files=[self.bak('202610',i) for i in range(5)]
        files[-1].write_bytes(b'\xff')
        with self.assertRaises(UnicodeDecodeError):prune_log_backups(self.root)
        self.assertTrue(all(p.exists() for p in files))

    def test_creation_keeps_three_and_failed_creation_keeps_older(self):
        (self.root/'202610.adi').write_bytes(b'<EOH>')
        for i in range(5):self.snapshot(i)
        p=create_log_backup(self.root)
        self.assertTrue(p.exists())
        self.assertEqual(len(list(self.folder.glob('*.zip'))),3)
        before={p.name:p.read_bytes() for p in self.folder.iterdir()}
        with patch('psrtty.backup.os.replace',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):create_log_backup(self.root)
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.folder.iterdir()})

    def test_cleanup_error_does_not_report_backup_failure(self):
        (self.root/'202610.adi').write_bytes(b'<EOH>')
        with patch('psrtty.log_retention.prune_log_backups',side_effect=OSError('denied')):
            self.assertTrue(create_log_backup(self.root).exists())

    def test_linked_backup_directory_preserved(self):
        other=self.root/'other';other.mkdir()
        self.folder.rmdir()
        try:self.folder.symlink_to(other,target_is_directory=True)
        except OSError:self.skipTest('symlinks unavailable')
        with self.assertRaises(OSError):prune_log_backups(self.root)
        self.assertTrue(other.exists())

    def test_newest_mtime_wins_over_random_uuid_name(self):
        paths=[self.snapshot(i) for i in range(4)]
        for i,p in enumerate(paths):os.utime(p,ns=(100+i,100+i))
        newest=paths[0]
        os.utime(newest,ns=(1000,1000))
        prune_log_backups(self.root)
        self.assertTrue(newest.exists())
        self.assertFalse(paths[1].exists())
