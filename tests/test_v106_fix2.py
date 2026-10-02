"""Language regression tests: displayed text and persisted identities are separate."""
import copy
import re
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import (QApplication, QWidget, QComboBox, QTabWidget,
                               QLabel, QTextBrowser)
from psrtty import i18n
from psrtty.config import ConfigStore
from psrtty.macros import TEMPLATES, TEMPLATE_HELP, CQWW_TEMPLATE_NAME, NORMAL_TEMPLATE_NAME
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.ui.guide import GuideWindow, PAGES
from psrtty.ui.history_dialog import HistoryDialog
from psrtty.ui.about_dialog import AboutDialog
from psrtty.ui.update_dialog import UpdateDialog
from psrtty.ui.cabrillo_dialog import CabrilloDialog
from psrtty.update_history import HISTORY_TEXT
from psrtty.update_history_en import HISTORY_TEXT_EN
from psrtty.adif import ADIFLog

JAPANESE = re.compile('[ぁ-龥]')


class Language106Fix2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        i18n.configure('en')
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name)
        self.store = ConfigStore(path/'config.json', path/'macros.json')
        self.windows = []

    def tearDown(self):
        for window in self.windows:
            window.close()
            window.deleteLater()
        self.app.processEvents()
        i18n.configure('ja')
        self.temp.cleanup()

    def keep(self, window):
        self.windows.append(window)
        return window

    def assert_english(self, window):
        for widget in [window] + window.findChildren(QWidget):
            values = []
            for name in ('text', 'toolTip', 'placeholderText', 'windowTitle', 'toPlainText', 'suffix', 'format'):
                method = getattr(widget, name, None)
                if callable(method):
                    try: values.append(method())
                    except TypeError: pass
            if isinstance(widget, QComboBox):
                values.extend(widget.itemText(i) for i in range(widget.count()))
            if isinstance(widget, QTabWidget):
                values.extend(widget.tabText(i) for i in range(widget.count()))
            for value in values:
                if isinstance(value, str):
                    self.assertIsNone(JAPANESE.search(value), (type(widget).__name__, value))

    def test_help_all_tabs_history_about_update_are_english(self):
        guide = self.keep(GuideWindow())
        self.assertEqual(guide.tabs.count(), len(PAGES))
        for window in [guide, self.keep(HistoryDialog()), self.keep(AboutDialog()), self.keep(UpdateDialog())]:
            self.assert_english(window)
        self.assertEqual(HISTORY_TEXT.count('\n・'), HISTORY_TEXT_EN.count('\n・'))
        self.assertEqual(re.findall(r'Ver[0-9.]+', HISTORY_TEXT), re.findall(r'Ver[0-9.]+', HISTORY_TEXT_EN))
        i18n.configure('ja')
        japanese = self.keep(GuideWindow())
        self.assertEqual(japanese.tabs.tabText(1), 'コントロール')
        self.assertIn('最初の設定', japanese.tabs.widget(0).toPlainText())
        self.assertIn('作者からの案内', '\n'.join(w.text() for w in self.keep(AboutDialog()).findChildren(QLabel)))

    def test_english_template_selection_apply_save_reload_and_japanese_reopen(self):
        original = copy.deepcopy(self.store.macros)
        dlg = self.keep(MacroDialog(self.store))
        for key in TEMPLATES:
            dlg.template.setCurrentIndex(dlg.template.findData(key))
            self.assert_english(dlg)
        self.assertEqual(dlg.macros, original)  # Selection alone cannot change macros.
        dlg._apply_template()
        self.assertEqual(dlg.applied_template, CQWW_TEMPLATE_NAME)
        self.assertEqual(dlg.sent.text(), '25')
        self.assertIn('actual operating location', dlg.template_help.text())
        self.assertIn('Japan is Zone 25.', dlg.template_help.text())
        dlg.sent.setText('14')
        dlg.table.item(8, 2).setText('CUSTOM {MYCALL}')
        dlg._save()
        path = Path(self.temp.name)
        store = ConfigStore(path/'config.json', path/'macros.json')
        self.assertEqual(store.data['macro_template'], CQWW_TEMPLATE_NAME)
        self.assertEqual(store.data['qso']['sent'], '14')
        self.assertEqual(store.macros[8]['text'], 'CUSTOM {MYCALL}')
        self.assertEqual(store.macros[0]['text'], TEMPLATES[CQWW_TEMPLATE_NAME]()[0]['text'])
        i18n.configure('ja')
        reopened = self.keep(MacroDialog(store))
        self.assertEqual(reopened.template.currentText(), CQWW_TEMPLATE_NAME)
        self.assertIn('実際の運用地のCQ Zoneを確認し、送信番号に設定してください。日本は25です。', reopened.template_help.text())

    def test_cancel_and_custom_macro_text_are_preserved(self):
        self.store.macros[8]['name'] = '任意名称'
        self.store.macros[8]['text'] = 'CUSTOM {SENT}'
        before = copy.deepcopy(self.store.data), copy.deepcopy(self.store.macros)
        dlg = self.keep(MacroDialog(self.store))
        self.assertEqual(dlg.table.item(8, 1).text(), '任意名称')
        dlg.template.setCurrentIndex(dlg.template.findData(CQWW_TEMPLATE_NAME))
        dlg._apply_template(); dlg.reject()
        self.assertEqual((self.store.data, self.store.macros), before)

    def test_settings_tabs_dynamic_labels_and_saved_radio_identity(self):
        with patch('psrtty.ui.settings_dialog.AudioEngine.devices', return_value=[]), \
             patch('psrtty.ui.settings_dialog.CIVController.port_choices', return_value=[]):
            dlg = self.keep(SettingsDialog(self.store))
            self.assert_english(dlg)
            for model in ('IC-705', 'FTX-1', 'その他ICOM'):
                dlg.rig.setCurrentIndex(dlg.rig.findData(model))
                self.assert_english(dlg)
                self.assertEqual(dlg._radio_values()['model'], model)
            for value in (None, 0, 10):
                dlg._show_alc(value)
                self.assert_english(dlg)
            dlg.rig.setCurrentIndex(dlg.rig.findData('IC-705'))
            dlg.my_call.setText('JH1HST'); dlg._save()
        self.assertEqual(self.store.data['radio']['model'], 'IC-705')
        self.assertEqual(self.store.data['station_callsign'], 'JH1HST')

    def test_cq_region_identity_survives_translation(self):
        adif = ADIFLog(Path(self.temp.name)/'log')
        dlg = self.keep(CabrilloDialog(adif, self.store))
        self.assertEqual([dlg.cq_region.itemText(i) for i in range(3)], ['Japan','US / Canada','Other'])
        self.assertEqual([dlg.cq_region.itemData(i) for i in range(3)], ['日本','米国・カナダ','その他'])
        for index, location in [(0, 'DX'), (1, ''), (2, 'DX')]:
            dlg.cq_region.setCurrentIndex(index); dlg.cq_call.setText('JH1HST')
            dlg._cq_prepare_period()
            self.assertEqual(dlg.value('LOCATION'), location)
        for index in range(dlg.pages.count()):
            dlg._set_page(index)
            self.assertIsNone(JAPANESE.search(dlg.heading.text()))

    def test_translation_placeholders_and_japanese_identity(self):
        formatter = string.Formatter()
        for japanese, english in i18n.TEXT.items():
            expected = {x[1] for x in formatter.parse(japanese) if x[1] is not None}
            actual = {x[1] for x in formatter.parse(english) if x[1] is not None}
            self.assertEqual(expected, actual, japanese)
        i18n.configure('ja')
        for text in i18n.TEXT:
            self.assertEqual(i18n.tr(text), text)

    def test_radio_and_external_validation_messages(self):
        from psrtty.radio import validate_radio
        from psrtty.external_ptt import validate_external
        with self.assertRaises(ValueError) as caught:
            validate_radio(self.store.data['radio'])
        self.assertIsNone(JAPANESE.search(str(caught.exception)))
        external = dict(self.store.data['external'], enabled=True, com_port='')
        with self.assertRaises(ValueError) as caught:
            validate_external(external, self.store.data['radio'])
        self.assertIsNone(JAPANESE.search(str(caught.exception)))
