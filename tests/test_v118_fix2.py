import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QFormLayout
from psrtty import i18n
from psrtty.ui.guide import GuideWindow
from psrtty.ui.audio_usb_help import ProfileAudioNotice
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.ui.special_thanks_dialog import CALLSIGNS
from tests.test_ui_v02 import UITests as Fixture

class GuideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def tearDown(self):i18n.configure('ja')
    def test_fsk_tab_and_notice_in_all_languages(self):
        for code in i18n.LANGUAGES:
            i18n.configure(code)
            g=GuideWindow();n=ProfileAudioNotice()
            index=g.tabs.count()-1
            self.assertEqual(g.tabs.tabText(index),i18n.tr('guide.fsk.title'))
            text=g.tabs.widget(index).toPlainText()
            for role in ('AFSK','FSK','Audio IN','Audio OUT','DTR','RTS','PTT','Mark','Space','RY','STOP'):
                self.assertIn(role,text)
            self.assertIn(i18n.tr('fsk.notice'),n.browser.toPlainText())
            self.assertEqual(len(i18n.diagnostics()),0)
            g.close();n.close()
    def test_thanks_once_in_call_area_order(self):
        for name in ('JM3LGF','JP1PPB'):self.assertEqual(CALLSIGNS.count(name),1)
        for before,after in (('JN1ATL','JP1PPB'),('JP1PPB','JG2AJK'),('JF3RRP','JM3LGF'),('JM3LGF','JP3GMO')):
            self.assertEqual(CALLSIGNS.index(after),CALLSIGNS.index(before)+1)

class SettingsTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    def test_notice_counts_only_afsk_profiles_including_legacy(self):
        d=SettingsDialog(self.store,self.window)
        for methods,expected in ((['afsk'],False),(['afsk','fsk'],False),(['afsk','fsk','fsk'],False),(['fsk','fsk'],False),(['afsk','afsk'],True),(['afsk','afsk','fsk'],True),([None,None,'fsk'],True)):
            d.working_profiles=[{'radio':{} if method is None else {'tx_method':method}} for method in methods]
            self.assertEqual(d._needs_profile_audio_notice(),expected,methods)
        d.reject()
    def test_fsk_test_controls_above_help(self):
        d=SettingsDialog(self.store,self.window)
        d.working['radio']['tx_method']='fsk';d._rebuild_inner_tabs()
        form=d.fsk_help.parentWidget().layout()
        help_row=form.getWidgetPosition(d.fsk_help)[0]
        # Connect/test are inside the row layout just above the test note.
        rows=[]
        for row in range(form.rowCount()):
            item=form.itemAt(row,QFormLayout.SpanningRole)
            if item and item.layout():
                layout=item.layout()
                if any(layout.itemAt(i).widget() is d.test_tx_button for i in range(layout.count())):rows.append(row)
        self.assertEqual(len(rows),1);self.assertLess(rows[0],help_row)
        d.reject()
