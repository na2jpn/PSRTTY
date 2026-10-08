import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from psrtty import i18n
from package_release import validate_all, build_distribution
from psrtty.updater import inspect_zip, prepare_update, apply_update, create_manifest

ROOT = Path(__file__).resolve().parents[1]

class Language111Tests(unittest.TestCase):
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
        self.tmp.cleanup()
    def test_complete_and_embedded_english_matches(self):
        self.assertEqual(validate_all(self.catalog), len(i18n.ENGLISH))
        self.assertEqual(json.loads((self.catalog/'en.json').read_text(encoding='utf-8'))['strings'], i18n.ENGLISH)
    def test_initial_japanese_and_saved_languages(self):
        from psrtty.config import DEFAULT_CONFIG
        self.assertEqual(DEFAULT_CONFIG['ui']['language'], 'ja')
        for code in i18n.LANGUAGES:
            i18n.configure(code, self.catalog)
            self.assertEqual(i18n.LANGUAGE, code)
            self.assertFalse(i18n.diagnostics())
            self.assertEqual(i18n.tr('保存'), json.loads((self.catalog/f'{code}.json').read_text(encoding='utf-8'))['strings'][i18n.ALIASES['保存']])
    def test_missing_all_files_operable_english_and_recovery(self):
        shutil.rmtree(self.catalog)
        i18n.configure('ru', self.catalog)
        self.assertEqual(i18n.REQUESTED_LANGUAGE, 'ru')
        self.assertEqual(i18n.LANGUAGE, 'en')
        self.assertEqual(i18n.tr('保存'), 'Save')
        self.assertTrue(i18n.startup_notice())
        self.assertTrue((self.root/'var/language.log').exists())
        shutil.copytree(ROOT/'language', self.catalog)
        i18n.configure('ru', self.catalog)
        self.assertEqual(i18n.LANGUAGE, 'ru')
        self.assertFalse(i18n.startup_notice())
    def test_broken_json_duplicate_and_structure(self):
        for raw in ('{', '{"format":1,"format":1}', '{"format":2,"language":"ko","strings":{}}'):
            (self.catalog/'ko.json').write_text(raw, encoding='utf-8')
            i18n.configure('ko', self.catalog)
            self.assertEqual(i18n.LANGUAGE, 'en')
            self.assertEqual(i18n.REQUESTED_LANGUAGE, 'ko')
    def test_bad_item_only_falls_back_without_dialog(self):
        d=json.loads((self.catalog/'zh.json').read_text(encoding='utf-8'))
        save=i18n.ALIASES['保存']
        field=next(k for k,v in i18n.ENGLISH.items() if '{count}' in v)
        d['strings'][save]=''
        d['strings'][field]='broken {wrong}'
        d['strings']['guide.0.body']='<p>unclosed'
        (self.catalog/'zh.json').write_text(json.dumps(d), encoding='utf-8')
        i18n.configure('zh', self.catalog)
        self.assertEqual(i18n.LANGUAGE,'zh')
        self.assertEqual(i18n.tr(save),'Save')
        self.assertEqual(i18n.tr(field),i18n.ENGLISH[field])
        self.assertEqual(i18n.tr('guide.0.body'),i18n.ENGLISH['guide.0.body'])
        self.assertFalse(i18n.startup_notice())
    def test_missing_english_uses_embedded_for_missing_selected_item(self):
        (self.catalog/'en.json').unlink()
        d=json.loads((self.catalog/'ru.json').read_text(encoding='utf-8'))
        d['strings'].pop(i18n.ALIASES['保存'])
        (self.catalog/'ru.json').write_text(json.dumps(d), encoding='utf-8')
        i18n.configure('ru',self.catalog)
        self.assertEqual(i18n.tr('保存'),'Save')
    def test_external_data_preserved(self):
        i18n.configure('ru',self.catalog)
        for value in ('JH1HST','CQ CQ DE JH1HST K','599 25','IC-705','arbitrary external error'):
            self.assertEqual(i18n.tr(value),value)
    def test_distribution_and_update_replace_language_preserve_user_data(self):
        exe=self.root/'input.exe';exe.write_bytes(b'MZ test executable')
        z=build_distribution(exe,self.root/'release')
        info=inspect_zip(z,'1.09')
        self.assertTrue({f'language/{c}.json' for c in i18n.LANGUAGES} <= info['files'].keys())
        installed=self.root/'installed';installed.mkdir()
        (installed/'psrtty.exe').write_bytes(b'MZ old')
        (installed/'config').mkdir();(installed/'config/psrtty.json').write_bytes(b'saved settings')
        (installed/'logdata').mkdir();(installed/'logdata/test.adi').write_bytes(b'original QSO')
        create_manifest(installed, '1.09')
        prepared=prepare_update(z,installed,'1.09')
        apply_update(prepared,installed,'1.09')
        self.assertEqual((installed/'config/psrtty.json').read_bytes(),b'saved settings')
        self.assertEqual((installed/'logdata/test.adi').read_bytes(),b'original QSO')
        self.assertEqual(validate_all(installed/'language'),len(i18n.ENGLISH))
