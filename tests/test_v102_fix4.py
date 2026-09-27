import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from package_release import build_distribution
from psrtty.updater import (HAMLIB_REQUIRED, MANIFEST, apply_update,
                            create_manifest, inspect_zip, prepare_update,
                            retire_compatibility_terms)


class Legacy101UpgradeTests(unittest.TestCase):
    def test_release_passes_actual_101_requirement_and_cleans_root_copy(self):
        # The shipped 1.01 EXE requests the root-level filename; its source
        # canonical was subsequently changed to request the docs/ filename.
        legacy_required = (HAMLIB_REQUIRED - {'docs/DISTRIBUTION_TERMS.txt'}) | {'DISTRIBUTION_TERMS.txt'}
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            exe = base / 'psrtty.exe'
            exe.write_bytes(b'MZ future 1.02 executable')
            release = build_distribution(exe, base / 'release')
            with patch('psrtty.updater.HAMLIB_REQUIRED', legacy_required):
                self.assertEqual(inspect_zip(release, '1.01')['version'], '1.03')
            with zipfile.ZipFile(release) as z:
                names = set(z.namelist())
                for filename in ('DISTRIBUTION_TERMS.txt', 'docs/DISTRIBUTION_TERMS.txt'):
                    self.assertIn('PSRTTY_1.03/' + filename, names)
                self.assertEqual(z.read('PSRTTY_1.03/DISTRIBUTION_TERMS.txt'),
                                 z.read('PSRTTY_1.03/docs/DISTRIBUTION_TERMS.txt'))
            old = base / 'installed'
            old.mkdir()
            (old / 'psrtty.exe').write_bytes(b'MZ old 1.01')
            (old / 'config').mkdir()
            (old / 'config' / 'saved.json').write_text('settings')
            (old / 'logdata').mkdir()
            (old / 'logdata' / 'saved.adi').write_text('qsos')
            create_manifest(old, '1.01')
            with patch('psrtty.updater.HAMLIB_REQUIRED', legacy_required):
                stage = prepare_update(release, old, '1.01')
                apply_update(stage, old, '1.01')
            retire_compatibility_terms(old)
            self.assertFalse((old / 'DISTRIBUTION_TERMS.txt').exists())
            self.assertTrue((old / 'docs' / 'DISTRIBUTION_TERMS.txt').is_file())
            self.assertEqual((old / 'config' / 'saved.json').read_text(), 'settings')
            self.assertEqual((old / 'logdata' / 'saved.adi').read_text(), 'qsos')
            self.assertEqual(json.loads((old / MANIFEST).read_text())['version'], '1.03')

    def test_unrelated_root_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / 'docs').mkdir()
            (root / 'DISTRIBUTION_TERMS.txt').write_text('personal')
            (root / 'docs' / 'DISTRIBUTION_TERMS.txt').write_text('release')
            retire_compatibility_terms(root)
            self.assertEqual((root / 'DISTRIBUTION_TERMS.txt').read_text(), 'personal')


if __name__ == '__main__':
    unittest.main()
