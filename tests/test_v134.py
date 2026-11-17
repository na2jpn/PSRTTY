"""Offline license access and signing failures before release packaging."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from psrtty import i18n
from psrtty.ui.about_dialog import AboutDialog
from psrtty.ui.license_dialog import LicenseDialog, license_document
from build_support.windows_signing import sign_executables
from tests import test_ui_v02 as fixture

ROOT = Path(__file__).resolve().parents[1]


class License134Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self):
        i18n.configure('ja')

    def test_offline_documents_and_localized_summary_in_all_languages(self):
        for code in i18n.LANGUAGES:
            with self.subTest(code=code):
                i18n.configure(code)
                d = LicenseDialog(document='LICENSING.md')
                self.assertEqual(d.windowTitle(), i18n.tr('license.title'))
                self.assertEqual(d.tabs.currentWidget(), d.documents['LICENSING.md'])
                self.assertIn('GPL-3.0-or-later', d.summary.toPlainText())
                self.assertIn('Hiroshi Tanaka', d.summary.toPlainText())
                for name, view in d.documents.items():
                    path = ROOT / (('docs/' if name.endswith('.txt') else '') + name)
                    self.assertEqual(view.toPlainText(), path.read_text(encoding='utf-8-sig'))
                    self.assertTrue(view.isReadOnly())
                d.close()

    def test_frozen_fallback_and_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); frozen = root/'embedded';(frozen/'licenses').mkdir(parents=True)
            (frozen/'licenses/LICENSE.md').write_text('GNU GPL 日本語', encoding='utf-8-sig')
            with patch('psrtty.ui.license_dialog.app_root', return_value=root), \
                 patch('psrtty.ui.license_dialog.resource_path', side_effect=lambda name:frozen/name):
                self.assertEqual(license_document('LICENSE.md'), 'GNU GPL 日本語')
                self.assertEqual(license_document('LICENSING.md'),
                                 i18n.tr('about.license_missing').format(name='LICENSING.md'))
                with self.assertRaises(ValueError):
                    license_document('../other.txt')

    def test_about_buttons_open_the_correct_document(self):
        d = AboutDialog()
        with patch('psrtty.ui.about_dialog.LicenseDialog') as dialog:
            d.license_button.click();dialog.assert_called_with(d, document='LICENSE.md')
            dialog.return_value.exec.assert_called_once()
            d.policy_button.click();dialog.assert_called_with(d, document='LICENSING.md')
        d.close()

    def test_current_history_is_only_the_requested_signing_entry(self):
        expected = 'Windows版の実行ファイルに、コードサイニング証明書によるデジタル署名を追加しました。'
        for code in i18n.LANGUAGES:
            s = json.loads((ROOT/f'language/{code}.json').read_text(encoding='utf-8'))['strings']
            lines = s['history.body'].split('\n\n', 1)[0].splitlines()
            self.assertEqual(lines[0], '2026-11-18  Ver1.34')
            self.assertEqual(len(lines), 2)
            if code == 'ja':
                self.assertEqual(lines[1], '・'+expected)
        self.assertEqual((ROOT/'CHANGELOG.md').read_text(encoding='utf-8').split('\n\n')[0],
                         '2026-11-18  Ver1.34\n・'+expected)


class Help134Tests(unittest.TestCase):
    setUpClass = classmethod(fixture.UITests.setUpClass.__func__)
    setUp = fixture.UITests.setUp
    tearDown = fixture.UITests.tearDown

    def test_license_is_accessible_directly_from_help(self):
        menu = self.window.top_level_menus[-1]
        action = next(a for a in menu.actions() if a.text() == i18n.tr('license.title'))
        with patch('psrtty.ui.main_window.LicenseDialog') as dialog:
            action.trigger();dialog.assert_called_once_with(self.window)
            dialog.return_value.exec.assert_called_once()


class Signing134Tests(unittest.TestCase):
    def test_sign_then_verify_every_executable_with_spaced_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = [Path(tmp)/name for name in ('app with spaces.exe','bridge.exe')]
            for path in files:path.write_bytes(b'MZ')
            with patch('build_support.windows_signing.find_signtool', return_value='Sign Tool.exe'), \
                 patch('build_support.windows_signing.subprocess.run') as run:
                sign_executables(files, 'AA '*20, machine_store=True)
            calls = run.call_args_list
            self.assertEqual(len(calls),4)
            for index,path in enumerate(files):
                sign = calls[index*2].args[0]
                self.assertEqual(sign[:4], ['Sign Tool.exe','sign','/sha1','AA'*20])
                self.assertIn('/sm',sign);self.assertEqual(sign[-1],str(path.resolve()))
                self.assertEqual(sign[sign.index('/fd')+1], 'SHA256')
                self.assertEqual(sign[sign.index('/td')+1], 'SHA256')
                self.assertEqual(calls[index*2+1].args[0],
                    ['Sign Tool.exe','verify','/pa','/all','/tw','/v',str(path.resolve())])
                self.assertEqual(calls[index*2].kwargs, {'check':True})

    def test_sign_or_verification_failure_never_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = [Path(tmp)/name for name in ('app.exe','bridge.exe')]
            for path in files:path.write_bytes(b'MZ')
            for stage in (0,1):
                with self.subTest(stage=stage), \
                     patch('build_support.windows_signing.find_signtool', return_value='signtool'), \
                     patch('build_support.windows_signing.subprocess.run',
                           side_effect=[None]*stage+[subprocess.CalledProcessError(2, 'signtool')]) as run:
                    with self.assertRaises(subprocess.CalledProcessError):
                        sign_executables(files, 'a'*40)
                    self.assertEqual(run.call_count, stage+1)

    def test_invalid_certificate_or_missing_file_does_not_invoke_signer(self):
        with patch('build_support.windows_signing.subprocess.run') as run:
            with self.assertRaises(ValueError):sign_executables([], '')
            with self.assertRaises(FileNotFoundError):sign_executables(['not-present.exe'],'a'*40)
            run.assert_not_called()
