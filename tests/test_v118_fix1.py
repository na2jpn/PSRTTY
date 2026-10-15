import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer,QCoreApplication
from PySide6.QtWidgets import QApplication,QMessageBox,QGroupBox
from psrtty import i18n
from psrtty.ui.questions import ask_question
from psrtty.ui.fsk_help import settings_html
from psrtty.ui.settings_dialog import SettingsDialog
from tests.test_ui_v02 import UITests as Fixture

class LocalizedConfirmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):i18n.configure('ja');i18n.install_qt_translation()
    def check_question(self,yes_key='qt.10',no_key='qt.12'):
        seen=[]
        def inspect():
            box=self.app.activeModalWidget()
            seen.append((box.button(QMessageBox.Yes).text(),box.button(QMessageBox.No).text(),box.defaultButton() is box.button(QMessageBox.No),box.testOption(QMessageBox.Option.DontUseNativeDialog)))
            box.button(QMessageBox.No).click()
        QTimer.singleShot(0,inspect)
        self.assertEqual(ask_question(None,'title','body',yes_key,no_key),QMessageBox.No)
        self.assertEqual(seen,[(i18n.tr(yes_key),i18n.tr(no_key),True,True)])
    def test_real_standard_and_fsk_buttons_in_all_eight_languages(self):
        for code in i18n.LANGUAGES:
            i18n.configure(code);i18n.install_qt_translation()
            self.check_question();self.check_question('fsk.yes','fsk.no');self.check_question('fsk.afsk_yes','fsk.afsk_no')
    def test_messagebox_translation_context(self):
        for code in ('ja','ru','zh','ko','id','th','es'):
            i18n.configure(code);i18n.install_qt_translation()
            self.assertEqual(QCoreApplication.translate('QMessageBox','&Yes'),i18n.tr('qt.10'))
            self.assertEqual(QCoreApplication.translate('QMessageBox','&No'),i18n.tr('qt.12'))
    def test_verified_tables_and_unknown_model_use_generic_text(self):
        for code in i18n.LANGUAGES:
            i18n.configure(code)
            ic=settings_html('IC-7300','DTR','CI-V');self.assertIn('<table',ic);self.assertIn('USB SEND',ic);self.assertNotIn('USB (A) DTR',ic);self.assertIn('USB (A) DTR',settings_html('IC-7300MK2'));self.assertIn('USB (B) DTR',settings_html('IC-7300MK2'))
            yaesu=settings_html('FT-891','RTS','CAT');self.assertIn('10-05 RTTY SHIFT PORT',yaesu);self.assertIn('10-09 RTTY SHIFT FREQ',yaesu);self.assertNotIn('USB (A)',yaesu)
            other=settings_html('UNKNOWN');self.assertIn(i18n.tr('fskhelp.generic'),other);self.assertNotIn('USB SEND',other);self.assertNotIn('10-05',other)
            self.assertIn('Mark',other);self.assertIn('Space',other)

class SettingsFix1UITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    pump=Fixture.pump
    def test_switch_group_is_separate_from_connect(self):
        self.store.data['radio'].update(model='IC-7300',civ_address='94',com_port='COM3')
        dlg=SettingsDialog(self.store,self.window);dlg.show();dlg.tabs.setCurrentIndex(1);self.pump(.05)
        self.assertIsInstance(dlg.fsk_group,QGroupBox);self.assertIs(dlg.fsk_switch.parent(),dlg.fsk_group)
        self.assertGreater(dlg.fsk_group.y(),dlg.connect_button.geometry().bottom()+8)
        with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes) as ask:dlg._switch_fsk();self.assertEqual(ask.call_args.args[-2:],('fsk.yes','fsk.no'))
        self.assertNotIn('USB (A)',dlg.fsk_help.text());dlg.fsk_line.setCurrentText('RTS');self.assertIn('RTS OFF',dlg.fsk_help.text())
        with patch('psrtty.ui.fsk_settings.ask_question',return_value=QMessageBox.Yes) as ask:dlg._switch_fsk();self.assertEqual(ask.call_args.args[-2:],('fsk.afsk_yes','fsk.afsk_no'))
        dlg.reject();dlg.deleteLater()
    def test_polarity_is_displayed_separately_from_port_selection(self):
        self.store.data['radio'].update(model='FT-891',tx_method='fsk',com_port='COM1',cat_baud='38400')
        self.store.data['fsk']['port']='COM2';dlg=SettingsDialog(self.store,self.window)
        self.assertIn('10-05 RTTY SHIFT PORT',dlg.fsk_help.text());self.assertIn('Mark',dlg.fsk_help.text())
        dlg.fsk_line.setCurrentText('RTS');self.assertIn('RTS OFF',dlg.fsk_help.text());self.assertIn('RTS ON',dlg.fsk_help.text())
        dlg.reject();dlg.deleteLater()
