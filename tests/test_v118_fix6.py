"""Check connection guidance across manufacturers and when changing the selected radio."""
import unittest
from PySide6.QtWidgets import QApplication
from psrtty import i18n
from psrtty.fsk_models import ICOM_FSK,KENWOOD_FSK,YAESU_FSK,AFSK_ONLY,YAESU_AFSK_ONLY
from psrtty.ui.fsk_notice import BLACK,BLUE,RED,USB_ONLY,EXTERNAL,AFSK_REQUIRED,notice_color,notice_html
from psrtty.ui.fsk_help import settings_html,icom_guide_html,kenwood_guide_html,yaesu_guide_html
from psrtty.ui.settings_dialog import SettingsDialog
from tests import test_ui_v02

class GuidanceTests(unittest.TestCase):
    def tearDown(self):i18n.configure('ja')
    def test_all_known_models_have_disjoint_connection_categories(self):
        self.assertEqual(USB_ONLY|EXTERNAL,ICOM_FSK|KENWOOD_FSK|YAESU_FSK)
        self.assertEqual(AFSK_REQUIRED,AFSK_ONLY|YAESU_AFSK_ONLY)
        self.assertFalse(USB_ONLY&EXTERNAL);self.assertFalse((USB_ONLY|EXTERNAL)&AFSK_REQUIRED)
        self.assertIn('FT-891',EXTERNAL);self.assertNotIn('FT-891',USB_ONLY)
        for model in ('IC-7300','IC-705','TS-890S','FT-710'):self.assertEqual(notice_color(model),BLACK)
        for model in ('IC-7100','TS-590SG','FT-950','FT-891'):self.assertEqual(notice_color(model),BLUE)
        for model in ('IC-707','FT-817 / FT-817ND'):self.assertEqual(notice_color(model),RED)
        self.assertEqual(notice_color('その他ICOM'),BLACK)
    def test_all_languages_use_same_guidance_in_output_and_guides(self):
        for lang in i18n.LANGUAGES:
            i18n.configure(lang)
            guides=icom_guide_html()+kenwood_guide_html()+yaesu_guide_html()
            for model in USB_ONLY|EXTERNAL|AFSK_REQUIRED:
                notice=notice_html(model);self.assertIn(notice,settings_html(model))
                if model.startswith('IC-') and model not in ('IC-7300','IC-7100','IC-707'):
                    self.assertIn('style="color:'+notice_color(model)+';" href=',guides)
                else:self.assertIn(notice,guides)
                if model in USB_ONLY|EXTERNAL:self.assertNotIn('<b>',notice)
            usb=settings_html('IC-7300')
            self.assertNotIn(RED,usb);self.assertNotIn('<b>',notice_html('IC-7300'))
            self.assertIn('SCU-17',notice_html('FT-891'))

class NoticeUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=test_ui_v02.UITests.setUp
    tearDown=test_ui_v02.UITests.tearDown
    def test_changing_model_resets_both_notice_text_and_color(self):
        d=SettingsDialog(self.store,self.window)
        for model,color in (('IC-707',RED),('IC-7100',BLUE),('IC-7300',BLACK),('FT-891',BLUE),('FT-710',BLACK)):
            d.rig.setCurrentIndex(d.rig.findData(model))
            self.assertEqual(d.fsk_model_notice.styleSheet(),'color:'+color+';')
            self.assertNotIn('<b>',d.fsk_model_notice.text())
        self.assertEqual(d.fsk_model_notice.text(),i18n.tr('fsk6.usb'));d.reject()
