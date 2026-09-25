import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QRect
from psrtty.config import ConfigStore, DEFAULT_MACROS
from psrtty.ui.window_state import fitted_rect
from psrtty.updater import MANIFEST, LEGACY_MANIFEST, create_manifest, retire_legacy_manifest, inspect_zip
from package_release import build_distribution

class WindowPlacementTests(unittest.TestCase):
    def test_default_center(self):
        area=QRect(0,0,1920,1040); r=fitted_rect(None,[area])
        self.assertEqual((r.width(),r.height()),(1280,800)); self.assertEqual(r.center(),area.center())
    def test_small_screen_and_decoration(self):
        r=fitted_rect(None,[QRect(0,0,1024,728)],margins=(8,31,8,8))
        self.assertTrue(QRect(8,31,1008,689).contains(r))
    def test_offscreen_centers_on_primary(self):
        area=QRect(0,0,1920,1040)
        r=fitted_rect(dict(x=5000,y=200,w=1280,h=800),[area])
        self.assertEqual(r.center(),area.center())
    def test_secondary_negative_coordinates_preserved(self):
        saved=dict(x=-1700,y=50,w=1280,h=800)
        self.assertEqual(fitted_rect(saved,[QRect(0,0,1920,1040),QRect(-1920,0,1920,1040)]),QRect(-1700,50,1280,800))
    def test_partial_offscreen_clamped(self):
        area=QRect(0,0,1366,728)
        self.assertTrue(area.contains(fitted_rect(dict(x=1300,y=700,w=1280,h=800),[area])))
    def test_reset_ignores_saved_geometry(self):
        area=QRect(0,0,1920,1040)
        self.assertEqual(fitted_rect(dict(x=10,y=10,w=400,h=300,maximized=True),[area],True),fitted_rect(None,[area]))
    def test_bad_saved_state_uses_defaults(self):
        for data in (None, [], dict(x='bad'),dict(x=0,y=0,w=-1,h=2)):
            self.assertEqual(fitted_rect(data,[QRect(0,0,1920,1040)]).width(),1280)

class ReleaseV03Tests(unittest.TestCase):
    def test_zip_only_and_clean_layout_preserves_existing_folder(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); exe=base/'input.exe'; exe.write_bytes(b'MZbuild')
            out=base/'release'; out.mkdir()
            z=build_distribution(exe,out)
            self.assertEqual([x.name for x in out.iterdir()],[f'PSRTTY_{__import__("psrtty").__version__}.zip'])
            with zipfile.ZipFile(z) as archive:
                self.assertEqual(set(archive.namelist()),{f'PSRTTY_{__import__("psrtty").__version__}/'+s for s in ['psrtty.exe',MANIFEST,'config/','logdata/','var/']})
            self.assertEqual(inspect_zip(z,'0.02')['version'],__import__('psrtty').__version__)
            existing=out/'PSRTTY_0.02'; existing.mkdir(); (existing/'mine').write_bytes(b'keep')
            build_distribution(exe,out); self.assertEqual((existing/'mine').read_bytes(),b'keep')
    def test_failed_build_keeps_previous_zip(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); exe=base/'input.exe'; exe.write_bytes(b'MZok'); out=base/'release'
            z=build_distribution(exe,out); before=z.read_bytes(); exe.write_bytes(b'bad')
            with self.assertRaises(ValueError): build_distribution(exe,out)
            self.assertEqual(z.read_bytes(),before); self.assertEqual(len(list(out.iterdir())),1)
    def test_legacy_json_archived_only_after_verified_manual_upgrade(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'psrtty.exe').write_bytes(b'MZold'); old=create_manifest(root,'0.02')
            (root/LEGACY_MANIFEST).write_text(json.dumps(old)); (root/'psrtty.exe').write_bytes(b'MZnew'); create_manifest(root,'0.03')
            retire_legacy_manifest(root,'0.03')
            self.assertFalse((root/LEGACY_MANIFEST).exists())
            backups=list((root/'var/backups').glob('*/'+LEGACY_MANIFEST)); self.assertEqual(len(backups),1)
            self.assertEqual(json.loads(backups[0].read_text()),old)
    def test_legacy_json_preserved_if_new_exe_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'psrtty.exe').write_bytes(b'MZold'); old=create_manifest(root,'0.02')
            (root/LEGACY_MANIFEST).write_text(json.dumps(old)); create_manifest(root,'0.03'); (root/'psrtty.exe').write_bytes(b'MZwrong')
            with self.assertRaises(ValueError): retire_legacy_manifest(root,'0.03')
            self.assertTrue((root/LEGACY_MANIFEST).exists())
    def test_f8_one_time_migration_and_later_free_edit(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); macros=copy.deepcopy(DEFAULT_MACROS); macros[7].update(name='FREE',text='')
            (root/'macros.json').write_text(json.dumps(macros))
            with patch('psrtty.config.ensure_runtime_dirs',return_value={'config':root}):
                store=ConfigStore(); self.assertEqual(store.macros[7]['text'],'KKK')
                store.macros[7].update(name='FREE',text=''); store.save()
                self.assertEqual(ConfigStore().macros[7]['text'],'')
    def test_custom_f8_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); macros=copy.deepcopy(DEFAULT_MACROS); macros[7].update(name='CUSTOM',text='TEST')
            (root/'macros.json').write_text(json.dumps(macros))
            with patch('psrtty.config.ensure_runtime_dirs',return_value={'config':root}):
                self.assertEqual(ConfigStore().macros[7],macros[7])
    def test_v03_to_v04_update_preserves_var_and_rolls_back(self):
        from psrtty.updater import prepare_update, apply_update
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)/'installed'; root.mkdir(); (root/'psrtty.exe').write_bytes(b'MZ03')
            create_manifest(root,'0.03'); (root/'var/user.txt').write_bytes(b'keep')
            release=Path(td)/'payload'; release.mkdir(); (release/'psrtty.exe').write_bytes(b'MZ04'); create_manifest(release,'0.04')
            archive=Path(td)/'next.zip'
            with zipfile.ZipFile(archive,'w') as z:
                for name in ('psrtty.exe',MANIFEST): z.write(release/name,'PSRTTY_0.04/'+name)
            stage=prepare_update(archive,root,'0.03')
            with patch('psrtty.updater.migrate_settings',side_effect=OSError('simulated')):
                with self.assertRaises(RuntimeError): apply_update(stage,root,'0.03')
            self.assertEqual(json.loads((root/MANIFEST).read_text())['version'],'0.03')
            stage=prepare_update(archive,root,'0.03'); backup=apply_update(stage,root,'0.03')
            self.assertEqual(json.loads((root/MANIFEST).read_text())['version'],'0.04')
            self.assertEqual((root/'var/user.txt').read_bytes(),b'keep')
            self.assertEqual((backup/'var/user.txt').read_bytes(),b'keep')
            self.assertFalse((root/LEGACY_MANIFEST).exists())
