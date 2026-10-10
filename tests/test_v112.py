import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox
from psrtty import i18n, __version__
from psrtty.config import ConfigStore, DEFAULT_CONFIG
from package_release import validate_all, build_distribution
from psrtty.updater import create_manifest, inspect_zip, MANIFEST
ROOT = Path(__file__).resolve().parents[1]

class Language112Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.catalog = self.root / 'language'
        shutil.copytree(ROOT / 'language', self.catalog)
        self.patch = patch('psrtty.i18n.app_root', return_value=self.root)
        self.patch.start()
    def tearDown(self):
        self.patch.stop()
        i18n.configure('ja')
        i18n.install_qt_translation()
        self.tmp.cleanup()
    def test_version_eight_complete_languages_and_history(self):
        self.assertGreaterEqual(tuple(map(int,__version__.split('.'))), (1,12))
        self.assertEqual(i18n.LANGUAGES, ('ja','en','ru','zh','ko','id','th','es'))
        self.assertEqual(validate_all(self.catalog), len(i18n.ENGLISH))
        for code in i18n.LANGUAGES:
            s=json.loads((self.catalog/f'{code}.json').read_text(encoding='utf-8'))['strings']
            self.assertEqual(set(s),set(i18n.ENGLISH))
            self.assertRegex(s['history.body'].splitlines()[0],r'^2026-\d{2}-\d{2}  Ver'+__version__+r'$')
            self.assertIn('2026-10-09  Ver1.12',s['history.body'])
            self.assertIn('2026-10-08',s['history.body'])
            self.assertIn('Ver1.10',s['history.body'])
    def test_added_language_preferences_survive_restart(self):
        self.assertEqual(DEFAULT_CONFIG['ui']['language'],'ja')
        for code in ('id','th','es'):
            config=self.root/f'{code}.json';macros=self.root/f'{code}-macros.json'
            store=ConfigStore(config,macros);store.data['ui']['language']=code;store.save()
            loaded=ConfigStore(config,macros)
            self.assertEqual(loaded.data['ui']['language'],code)
            i18n.configure(code,self.catalog)
            self.assertEqual(i18n.LANGUAGE,code)
            self.assertFalse(i18n.diagnostics())
    def test_added_file_failure_recovers_without_rewriting_choice(self):
        for code in ('id','th','es'):
            path=self.catalog/f'{code}.json';original=path.read_bytes();path.write_bytes(b'{')
            i18n.configure(code,self.catalog)
            self.assertEqual(i18n.LANGUAGE,'en')
            self.assertEqual(i18n.REQUESTED_LANGUAGE,code)
            self.assertEqual(i18n.tr('保存'),'Save')
            path.write_bytes(original);i18n.configure(code,self.catalog)
            self.assertEqual(i18n.LANGUAGE,code)
            self.assertFalse(i18n.startup_notice())
    def test_added_invalid_item_falls_back_only_for_that_item(self):
        for code in ('id','th','es'):
            path=self.catalog/f'{code}.json';d=json.loads(path.read_text(encoding='utf-8'))
            key=i18n.ALIASES['保存'];d['strings'][key]=''
            path.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
            i18n.configure(code,self.catalog)
            self.assertEqual(i18n.LANGUAGE,code)
            self.assertEqual(i18n.tr(key),'Save')
            self.assertNotEqual(i18n.tr('guide.0.body'),i18n.ENGLISH['guide.0.body'])
            self.assertFalse(i18n.startup_notice())
    def test_native_standard_buttons_without_qtbase_catalogue(self):
        for code,save,cancel in [('id','Simpan','Batal'),('th','บันทึก','ยกเลิก'),('es','Guardar','Cancelar')]:
            i18n.configure(code,self.catalog)
            with patch('PySide6.QtCore.QTranslator.load',return_value=False):
                i18n.install_qt_translation()
            box=QMessageBox();box.setStandardButtons(QMessageBox.Save|QMessageBox.Cancel)
            self.assertEqual(box.button(QMessageBox.Save).text().replace('&',''),save)
            self.assertEqual(box.button(QMessageBox.Cancel).text().replace('&',''),cancel)
            self.assertEqual(QCoreApplication.translate('QFileDialog','&Save'),save)
            self.assertFalse(i18n.diagnostics())
    def test_user_transmission_and_identifiers_are_preserved(self):
        for code in ('id','th','es'):
            i18n.configure(code,self.catalog)
            for text in ('CQ CQ DE JH1HST K','599 05 MA','IC-7760','FT-817ND','{MYCALL}'):
                self.assertEqual(i18n.tr(text),text)
    def test_update_rejects_missing_new_language_but_accepts_111_five(self):
        exe=self.root/'input.exe';exe.write_bytes(b'MZ test executable')
        release=build_distribution(exe,self.root/'release')
        info=inspect_zip(release,'1.11')
        self.assertTrue({f'language/{c}.json' for c in i18n.LANGUAGES} <= info['files'].keys())
        staging=self.root/'staging';staging.mkdir()
        with zipfile.ZipFile(release) as z:z.extractall(staging)
        installation=staging/f'PSRTTY_{__version__}'
        for code in ('id','th','es'):(installation/'language'/f'{code}.json').unlink()
        def archive(version):
            create_manifest(installation,version)
            target=self.root/f'{version}.zip'
            with zipfile.ZipFile(target,'w') as z:
                for p in installation.rglob('*'):
                    if p.is_file():z.write(p,'PSRTTY/'+p.relative_to(installation).as_posix())
            return target
        with self.assertRaisesRegex(ValueError,'8言語'):inspect_zip(archive('1.12'),'1.10')
        self.assertEqual(inspect_zip(archive('1.11'),'1.10')['version'],'1.11')
    def test_distribution_refuses_missing_added_language(self):
        (self.catalog/'th.json').unlink()
        with self.assertRaises(ValueError):validate_all(self.catalog)
