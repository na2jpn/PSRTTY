import copy
import tempfile
import unittest
from pathlib import Path
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.macros import TEMPLATES, TEMPLATE_NAME, CQWW_TEMPLATE_NAME, NORMAL_TEMPLATE_NAME, expand_macro
from psrtty.parser import parse_exchange
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.adif import ADIFLog, QSORecord

class Macro73Tests(unittest.TestCase):
    def test_templates(self):
        for name, sent in ((TEMPLATE_NAME,'01'),(CQWW_TEMPLATE_NAME,'25')):
            rows=TEMPLATES[name]()
            self.assertEqual([m['key'] for m in rows],[f'F{i}' for i in range(1,10)])
            self.assertEqual(expand_macro(rows[2]['text'],{'HISCALL':'W1AW','SENT':sent}),f'W1AW 599 {sent} {sent}')
            self.assertIn('TU 73',rows[3]['text'])
            rows[2]['text']='custom'
            self.assertNotEqual(TEMPLATES[name]()[2]['text'],'custom')

    def test_exchange_and_adif(self):
        for text, expected in [('599 05 MA 05 MA','05 MA'),('599 04 04 ON ON','04 ON'),('599 01 NWT','01 NWT'),('599 05 PEI','05 PEI'),('599 25 25 K','25'),('599 01 01','01'),('599 25 TU 73','25'),('599 25 JH1HST','25'),('599 44 MA','44'),('599 05 XX','05')]:
            with self.subTest(text=text): self.assertEqual(parse_exchange(text,cqww=True).exchange,expected)
        self.assertEqual(parse_exchange('599 05 MA').exchange,'05')
        with tempfile.TemporaryDirectory() as td:
            log=ADIFLog(Path(td));log.append(QSORecord('W1AW',sent='01',rcvd='05 MA'))
            q=log.load_recent()[0];self.assertEqual((q.sent,q.rcvd),('01','05 MA'))

class UI73Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_selection_apply_save_cancel(self):
        before=copy.deepcopy(self.store.macros);dlg=MacroDialog(self.store)
        try:
            dlg.show();self.pump(.03)
            self.assertGreaterEqual(dlg.table.viewport().height(),dlg.table.rowViewportPosition(8)+dlg.table.rowHeight(8))
            dlg.template.setCurrentText(TEMPLATE_NAME);self.assertIn('平均年齢',dlg.template_help.text())
            dlg.template.setCurrentText(CQWW_TEMPLATE_NAME);self.assertIn('25',dlg.template_help.text())
            self.assertEqual(dlg.table.item(2,2).text(),before[2]['text'])
            dlg._apply_template();dlg.reject()
            self.assertEqual(self.store.macros,before);self.assertNotIn('macro_template',self.store.data)
        finally:dlg.close()
        dlg=MacroDialog(self.store)
        try:
            dlg.template.setCurrentText(CQWW_TEMPLATE_NAME);dlg._apply_template()
            dlg.table.item(8,2).setText('CUSTOM')
            dlg.template.setCurrentText(TEMPLATE_NAME);dlg._save()
            self.assertEqual(self.store.data['macro_template'],CQWW_TEMPLATE_NAME)
            self.assertEqual(self.store.macros[8]['text'],'CUSTOM')
        finally:dlg.close()
        dlg=MacroDialog(self.store)
        try:self.assertEqual(dlg.template.currentText(),CQWW_TEMPLATE_NAME)
        finally:dlg.close()

    def test_receive_auto_and_card(self):
        w=self.window;w.store.data['macro_template']=CQWW_TEMPLATE_NAME
        w.auto_get.setChecked(True);w.q_call.setText('W1AW')
        w._consider_auto_extract('W1AW 599 05 MA 05 MA');self.assertEqual(w.rcvd.text(),'05 MA')
        w._card_selected('W1AW 599 04 ON');self.assertEqual(w.rcvd.text(),'04 ON')
        w.store.data['macro_template']=NORMAL_TEMPLATE_NAME
        w._consider_auto_extract('W1AW 599 05 MA');self.assertEqual(w.rcvd.text(),'05')

del _Fixture
