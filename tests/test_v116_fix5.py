import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from psrtty.config import ConfigStore
from psrtty import i18n
from tests.test_ui_v02 import UITests as Fixture


class DisplayModeTests(unittest.TestCase):
    setUpClass = classmethod(Fixture.setUpClass.__func__)
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown
    pump = Fixture.pump

    def mode(self, value):
        w = self.window
        w.decode_display.setCurrentIndex(w.decode_display.findData(value))

    def test_default_buffered_filter_boundary_and_independent_outputs(self):
        w = self.window
        self.assertEqual(w.decode_display.currentData(), 'buffered')
        w.decode_ignore.setCurrentIndex(3)
        with patch.object(w.printer, 'submit') as printer, patch.object(w, '_consider_auto_extract') as extract:
            for ch in 'ABC': w._rx_char(ch)
            self.assertEqual(w.cards_layout.count(), 0)
            w._rx_char('\n')
            self.assertEqual(w.cards_layout.count(), 0)
            extract.assert_not_called()
            for ch in 'ABCD': w._rx_char(ch)
            self.assertEqual(w.cards_layout.count(), 0)
            w._rx_char('\n')
            self.assertEqual(w.cards_layout.count(), 1)
            self.assertEqual(w.cards_layout.itemAt(0).widget().body.text(), 'ABCD')
            extract.assert_called_once_with('ABCD')
            self.assertEqual(printer.call_count, 2)
            w.transcript.append.assert_any_call('RX ABC')

    def test_switch_both_directions_mid_receive_no_loss_or_duplicate(self):
        w = self.window
        with patch.object(w.printer, 'submit') as printer, patch.object(w, '_consider_auto_extract') as extract:
            for ch in 'CQ ': w._rx_char(ch)
            self.mode('live')
            self.assertEqual(w.rx_live_card.body.text(), 'CQ')
            for ch in 'JA1': w._rx_char(ch)
            self.mode('buffered')
            self.assertIsNone(w.rx_live_card)
            self.assertEqual(w.cards_layout.count(), 0)
            self.assertEqual(w.rx_buffer, 'CQ JA1')
            for ch in 'ABC': w._rx_char(ch)
            self.mode('live')
            card = w.rx_live_card
            self.assertEqual(card.body.text(), 'CQ JA1ABC')
            self.assertFalse(card.finalized)
            extract.assert_not_called(); printer.assert_not_called()
            w._rx_char('\n')
            self.assertEqual(w.cards_layout.count(), 1)
            self.assertIs(w.cards_layout.itemAt(0).widget(), card)
            self.assertTrue(card.finalized)
            extract.assert_called_once_with('CQ JA1ABC'); printer.assert_called_once()

    def test_live_short_message_removed_on_finalization_and_decode_off(self):
        w = self.window
        self.mode('live'); w.decode_ignore.setCurrentIndex(2)
        for ch in 'AB': w._rx_char(ch)
        self.assertEqual(w.cards_layout.count(), 1)
        w._rx_char('\n'); self.assertEqual(w.cards_layout.count(), 0)
        w._rx_char('C'); self.mode('buffered')
        w.decode_enabled.setChecked(False)
        self.assertEqual(w.rx_buffer, '')
        self.mode('live'); self.assertIsNone(w.rx_live_card)
        w.decode_enabled.setChecked(True); w._rx_char('D')
        self.assertEqual(w.rx_live_card.body.text(), 'D')

    def test_failed_save_preserves_preview_buffer_and_mode(self):
        w = self.window
        self.mode('live'); w._rx_char('A'); card = w.rx_live_card
        w.store.save.side_effect = OSError('disk full')
        self.mode('buffered')
        self.assertEqual(w.decode_display.currentData(), 'live')
        self.assertEqual(w.store.data['ui']['decode_display_mode'], 'live')
        self.assertIs(w.rx_live_card, card); self.assertEqual(w.rx_buffer, 'A')
        w.store.save.side_effect = None

    def test_header_order_and_full_ignore_caption(self):
        w = self.window; w.show(); self.pump(.03)
        widgets = (w.decode_enabled, w.decode_display, w.decode_label, w.decode_ignore, w.decode_ignore_label)
        for left, right in zip(widgets, widgets[1:]):
            self.assertLess(left.geometry().right(), right.geometry().left())
        self.assertEqual(w.decode_ignore_label.text(), '文字以下は無視')
        self.assertTrue(w.decode_display.toolTip())

    def test_all_catalogues_have_mode_and_filter_explanation(self):
        root = Path(__file__).resolve().parents[1] / 'language'
        for code in i18n.LANGUAGES:
            s = json.loads((root / f'{code}.json').read_text(encoding='utf-8'))['strings']
            for key in ('v116.rx_live', 'v116.rx_buffered', 'v116.rx_display_tip', 'v116.rx_display_guide', 'ui.061c37bfacafe1e5'):
                self.assertTrue(s[key], (code, key))
            for key in ('guide.2.body', 'guide.7.body', 'guide.9.body'):
                self.assertIn(s['v116.rx_display_guide'], s[key])


class DisplayConfigTests(unittest.TestCase):
    def test_new_legacy_invalid_and_saved_live(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'config.json'; macros = Path(td) / 'macros.json'
            store = ConfigStore(path, macros)
            self.assertEqual(store.data['ui']['decode_display_mode'], 'buffered')
            store.data['ui']['decode_display_mode'] = 'live'; store.save()
            self.assertEqual(ConfigStore(path, macros).data['ui']['decode_display_mode'], 'live')
            saved = json.loads(path.read_text(encoding='utf-8'))
            del saved['ui']['decode_display_mode']
            path.write_text(json.dumps(saved), encoding='utf-8')
            self.assertEqual(ConfigStore(path, macros).data['ui']['decode_display_mode'], 'buffered')
            for invalid in ('bad', None, [], 1):
                saved['ui']['decode_display_mode'] = invalid
                path.write_text(json.dumps(saved), encoding='utf-8')
                self.assertEqual(ConfigStore(path, macros).data['ui']['decode_display_mode'], 'buffered')


del Fixture
