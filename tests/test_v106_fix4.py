import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from psrtty.config import ConfigStore
from psrtty.i18n import configure, tr
from psrtty.ui.about_dialog import AboutDialog
from psrtty.ui.special_thanks_dialog import CALLSIGNS
from tests import test_ui_v02 as fixture

class Fix4Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    pump=fixture.UITests.pump

    def test_filter_boundary_streaming_and_independent_outputs(self):
        w=self.window
        self.assertEqual(w.decode_ignore.currentData(),0)
        with patch.object(w.printer,'submit') as printer,patch.object(w,'_consider_auto_extract') as extract:
            w._rx_char('A');w._rx_char('\n')
            self.assertEqual(w.cards_layout.count(),1)
            w.decode_ignore.setCurrentIndex(1)
            w._rx_char('B');w._rx_char('\n')
            self.assertEqual(w.cards_layout.count(),1)
            self.assertEqual(extract.call_count,1)
            w._rx_char('C');w._rx_char('Q');w._rx_char('\n')
            self.assertEqual(w.cards_layout.count(),2)
            self.assertEqual(extract.call_count,2)
            self.assertEqual(printer.call_count,3)
            w.transcript.append.assert_any_call('RX B')
            w.decode_ignore.setCurrentIndex(2)
            w.rx_buffer='  CQ  ';w._finalize_rx_card()
            self.assertEqual(w.cards_layout.count(),2)
            w.rx_buffer='599';w._finalize_rx_card()
            self.assertEqual(w.cards_layout.count(),3)
            w._add_card('K','TX');self.assertEqual(w.cards_layout.count(),4)
        w.show();self.pump(.03)
        self.assertLess(w.decode_sq.x(),w.decode_ignore.x())
        self.assertLess(w.decode_sq.x(),w.decode_enabled.x())
        self.assertLess(w.decode_enabled.x(),w.decode_ignore.x())

    def test_filter_save_failure_rolls_back(self):
        w=self.window;w.store.save.side_effect=OSError('disk full')
        w.decode_ignore.setCurrentIndex(2)
        self.assertEqual(w.decode_ignore.currentData(),0)
        self.assertEqual(w.store.data['ui']['decode_ignore_chars'],0)
        w.store.save.side_effect=None

    def test_printer_status_toggle_error_and_menu_order_bilingual(self):
        w=self.window
        with patch.object(w,'_printer_port_problem',return_value=''):
            w.printer.configure(dict(port='COM9'))
            for language in ('ja','en'):
                configure(language)
                w._refresh_printer_status();self.assertTrue(w.printer_status.isHidden())
                self.assertEqual(w.printer_enable_action.text(),tr('プリンター出力を有効にする'))
                w._printer_enable(True)
                self.assertFalse(w.printer_status.isHidden())
                self.assertEqual(w.printer_enable_action.text(),tr('プリンター出力を無効にする'))
                self.assertIn('Printer enabled' if language=='en' else 'プリンターが有効',w.printer_status.text())
                w.printer.pause('error','Disconnected');w._refresh_printer_status()
                self.assertFalse(w.printer_status.isHidden())
                self.assertIn('Printer stopped' if language=='en' else 'プリンター停止',w.printer_status.text())
                w._printer_enable(False);self.assertTrue(w.printer_status.isHidden())
                self.assertEqual(w.printer.snapshot()['problem'],'')
        configure('ja')
        actions=w.printer_menu.actions();i=actions.index(w.printer_test_action)
        self.assertTrue(actions[i-1].isSeparator())
        self.assertEqual(actions[i-2].text(),'プリンター設定…')
        self.assertEqual(sum(a.isSeparator() for a in actions),1)

    def test_thanks_text_order_reuse_and_parent_close_bilingual(self):
        for language in ('ja','en'):
            configure(language);about=AboutDialog(self.window)
            about.show();about.thanks_button.click();self.pump(.01)
            d=about.thanks_window
            self.assertTrue(d.isVisible());self.assertEqual(d.windowTitle(),tr('スペシャルサンクス'))
            names=d.names.text().splitlines()
            self.assertEqual(names[0],'JS1YCP '+tr('秋葉原無線部'))
            self.assertEqual(names[1],'JA1YML '+tr('草加アマチュア無線クラブ'))
            self.assertEqual(names[3:],list(CALLSIGNS))
            self.assertEqual(d.message.text(),tr('ご意見やアイディアをだされた方、試験や開発に協力いただいた方々へ感謝いたします。'))
            d.close();about.thanks_button.click();self.assertIs(about.thanks_window,d)
            about.reject();self.assertFalse(d.isVisible())
        configure('ja')

class ConfigFix4Tests(unittest.TestCase):
    def test_saved_filter_reload_and_legacy_default(self):
        import json
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'config.json'
            store=ConfigStore(path,Path(td)/'macros.json');self.assertEqual(store.data['ui']['decode_ignore_chars'],0)
            store.data['ui']['decode_ignore_chars']=3;store.save()
            self.assertEqual(ConfigStore(path,Path(td)/'macros.json').data['ui']['decode_ignore_chars'],3)
            data=json.loads(path.read_text(encoding='utf-8'))
            data['ui']['decode_ignore_chars']='bad';path.write_text(json.dumps(data))
            self.assertEqual(ConfigStore(path,Path(td)/'macros.json').data['ui']['decode_ignore_chars'],0)
