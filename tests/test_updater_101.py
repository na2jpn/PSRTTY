import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from package_release import package_release
from psrtty.updater import (MANIFEST, VERSIONUP, HAMLIB_REQUIRED,
                            apply_update, create_manifest, inspect_zip, prepare_update)


def make_release(base, version, extra=False):
    root=base/f'PSRTTY_{version}';root.mkdir()
    (root/'psrtty.exe').write_bytes(b'MZ release '+version.encode())
    for name in HAMLIB_REQUIRED:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(b'file '+name.encode())
    if extra:
        target=root/'support/new-data.bin';target.parent.mkdir();target.write_bytes(b'future data')
    return root,package_release(root)


class BundledUpdateTest(unittest.TestCase):
    def test_manual_copy_preserves_user_data_and_future_update_adds_file(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);old=base/'existing';old.mkdir()
            (old/'config').mkdir();(old/'config/psrtty.json').write_bytes(b'saved settings')
            (old/'logdata').mkdir();(old/'logdata/202609.adi').write_bytes(b'saved QSOs')
            (old/'psrtty.exe').write_bytes(b'MZ old')
            create_manifest(old,'0.88')
            with patch('package_release.__version__','1.02'):
                release_root,release=make_release(base,'1.02')
            info=inspect_zip(release,'0.88')
            self.assertEqual(info['version'],'1.02')
            with zipfile.ZipFile(release) as z:
                top = {name[len('PSRTTY_1.02/'):].split('/')[0]
                       for name in z.namelist() if name.startswith('PSRTTY_1.02/')}
                self.assertEqual(top, {'psrtty.exe', 'config', 'logdata',
                                       'var', 'lib', 'docs', 'DISTRIBUTION_TERMS.txt'})
                self.assertFalse(any(n.endswith(('psrtty.json','.adi')) for n in z.namelist()))
                for name in info['files']:
                    (old/name).parent.mkdir(parents=True,exist_ok=True)
                    (old/name).write_bytes(z.read('PSRTTY_1.02/'+name))
                (old/MANIFEST).write_bytes(z.read('PSRTTY_1.02/'+MANIFEST))
            self.assertEqual((old/'config/psrtty.json').read_bytes(),b'saved settings')
            self.assertEqual((old/'logdata/202609.adi').read_bytes(),b'saved QSOs')
            with zipfile.ZipFile(release) as z:
                instructions=json.loads(z.read('PSRTTY_1.02/'+VERSIONUP))
            self.assertEqual(set(instructions['install']),set(info['files'])-{VERSIONUP})
            self.assertEqual((old/MANIFEST).read_bytes(),(release_root/MANIFEST).read_bytes())
            future_root,future=make_release(base,'1.03',extra=True)
            stage=prepare_update(future,old,'1.02')
            with patch('psrtty.updater.migrate_settings',side_effect=RuntimeError('migration')):
                with self.assertRaises(RuntimeError):apply_update(stage,old,'1.02')
            self.assertFalse((old/'support/new-data.bin').exists())
            stage=prepare_update(future,old,'1.02')
            apply_update(stage,old,'1.02')
            self.assertEqual((old/'support/new-data.bin').read_bytes(),b'future data')
            self.assertEqual((old/'config/psrtty.json').read_bytes(),b'saved settings')
            self.assertEqual((old/'logdata/202609.adi').read_bytes(),b'saved QSOs')
            self.assertEqual((old/MANIFEST).read_bytes(),(future_root/MANIFEST).read_bytes())

    def test_versionup_tamper_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);root,release=make_release(base,'1.03',extra=True)
            altered=base/'altered.zip'
            with zipfile.ZipFile(release) as source,zipfile.ZipFile(altered,'w') as dest:
                for name in source.namelist():
                    data=source.read(name)
                    if name.endswith(VERSIONUP):
                        instructions=json.loads(data);instructions['install'].append('config/psrtty.json')
                        data=json.dumps(instructions).encode()
                    dest.writestr(name,data)
            with self.assertRaises(ValueError):inspect_zip(altered,'1.01')


if __name__=='__main__':unittest.main()
