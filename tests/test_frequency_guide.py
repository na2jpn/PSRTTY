import json
import unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from psrtty import i18n
from psrtty.frequency_guide import BANDS, REGIONS, ROWS, SOURCES, REGION_SOURCES, page_html
from psrtty.ui.frequency_guide import FrequencyGuide
from tests import test_ui_v02 as fixture

ROOT = Path(__file__).resolve().parents[1]

class FrequencyGuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
    def tearDown(self):
        i18n.configure('ja')
    def test_all_languages_complete_and_all_five_tabs_render(self):
        for code in i18n.LANGUAGES:
            i18n.configure(code)
            self.assertFalse(i18n.diagnostics())
            catalog = json.loads((ROOT/'language'/f'{code}.json').read_text(encoding='utf-8'))['strings']
            self.assertEqual(set(catalog), set(i18n.ENGLISH))
            self.assertIn(catalog['freq.history'], catalog['history.body'])
            guide = FrequencyGuide()
            try:
                self.assertEqual(guide.tabs.count(), 5)
                self.assertEqual(guide.windowTitle(), catalog['freq.title'])
                for index in range(5):
                    browser = guide.tabs.widget(index)
                    body = browser.toPlainText()
                    self.assertIn(catalog['freq.year'], body)
                    self.assertIn(catalog['freq.japan7'], body)
                    self.assertIn(catalog['freq.sideband'], body)
                    self.assertIn('2026-10-09', body)
                    self.assertTrue(browser.openExternalLinks())
                    self.assertNotIn('freq.', body)
                if code != 'en':
                    self.assertNotEqual(catalog['freq.rules'], i18n.ENGLISH['freq.rules'])
            finally:
                guide.close()
    def test_region_selection_independent_of_display_language_and_japan_only_1200(self):
        for code in ('ja', 'es', 'th'):
            i18n.configure(code)
            guide = FrequencyGuide()
            try:
                self.assertEqual(guide.tabs.currentIndex(), 0)
                guide.tabs.setCurrentIndex(1)
                self.assertIn('1200 MHz', guide.tabs.currentWidget().toPlainText())
                for index in (2, 3, 4):
                    body = guide.tabs.widget(index).toPlainText()
                    self.assertNotIn('1200 MHz', body)
                    self.assertIn('430 MHz', body)
            finally:
                guide.close()
    def test_requested_band_coverage_and_seven_mhz_warning_in_every_region(self):
        for region in REGIONS:
            self.assertEqual(tuple(row[0] for row in ROWS[region]), BANDS + (('1200',) if region == 'japan' else ()))
            seven = next(row for row in ROWS[region] if row[0] == '7')
            self.assertIn('japan7', seven[3])
            self.assertTrue(all(SOURCES[k][1].startswith('https://') for k in REGION_SOURCES[region]))
    def test_frequency_reference_exclusions_and_national_examples(self):
        i18n.configure('ja')
        self.assertIn('7.035', page_html('japan'))
        self.assertIn('7.040 MHz未満', page_html('r1'))
        self.assertIn('14.099～14.101', page_html('r1'))
        self.assertIn('第2地域全体に共通する割当ではありません', page_html('r2'))
        self.assertIn('施行確認ができないため採用していません', page_html('r3'))
        self.assertIn('1294.50～1294.60', page_html('japan'))
    def test_missing_translation_falls_back_while_retaining_usable_guide(self):
        i18n.configure('es')
        old = i18n._strings.pop('freq.japan7')
        try:
            html = page_html('r1')
            self.assertIn('7.041', html)
            self.assertIn('Japan domestic FT8', html)
            self.assertIn(i18n.tr('freq.r1_intro'), html)
        finally:
            i18n._strings['freq.japan7'] = old

class FrequencyGuideMenuTests(unittest.TestCase):
    setUpClass = classmethod(fixture.UITests.setUpClass.__func__)
    setUp = fixture.UITests.setUp
    tearDown = fixture.UITests.tearDown
    def test_menu_order_modeless_reuse_and_close(self):
        window = self.window
        menu = window.top_level_menus[-1]
        labels = [a.text() for a in menu.actions()]
        index = labels.index(i18n.tr('freq.title'))
        self.assertEqual(labels[index-1], i18n.tr('ui.3e9f8e3d03440dc5'))
        menu.actions()[index].trigger()
        guide = window.help_windows['rtty_frequency_guide']
        self.assertFalse(guide.isModal())
        guide.tabs.setCurrentIndex(3)
        guide.close_button.click()
        self.assertFalse(guide.isVisible())
        window._guide_frequencies()
        self.assertIs(window.help_windows['rtty_frequency_guide'], guide)
        self.assertEqual(guide.tabs.currentIndex(), 3)
        self.assertTrue(guide.isVisible())
