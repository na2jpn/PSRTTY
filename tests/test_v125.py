import time
import unittest
from unittest.mock import patch
from tests.test_ui_v02 import UITests as Fixture


class BufferedReceive125Tests(unittest.TestCase):
    setUpClass = classmethod(Fixture.setUpClass.__func__)
    setUp = Fixture.setUp
    tearDown = Fixture.tearDown

    def send(self, text, start):
        for i, ch in enumerate(text):
            self.window._rx_char((self.window.audio.decode_generation, ch, start + i * .16))

    def cards(self):
        w = self.window
        return [w.cards_layout.itemAt(i).widget().body.text() for i in range(w.cards_layout.count())]

    def test_short_bursts_do_not_join_when_gui_timer_is_delayed(self):
        w = self.window
        w.store.data['ui']['decode_ignore_chars'] = 3
        with patch.object(w, '_consider_auto_extract') as extract:
            self.send('AB', 10)
            self.send('CD', 12)
            self.send('EF\n', 14)
            self.assertEqual(self.cards(), [])
            extract.assert_not_called()

    def test_mark_signal_cannot_keep_buffered_noise_alive(self):
        w = self.window
        w.store.data['ui']['decode_ignore_chars'] = 3
        self.send('AB', time.monotonic() - 3)
        w.audio.decoder.last_signal_time = time.monotonic()
        w._check_rx_idle()
        self.assertEqual(w.rx_buffer, '')
        self.assertEqual(self.cards(), [])

    def test_gap_over_one_character_keeps_valid_message(self):
        w = self.window
        w.store.data['ui']['decode_ignore_chars'] = 3
        self.send('ABCD', 10)
        self.send('E\n', 11.0)  # last character at 10.48; gap exceeds 10 bit times
        self.assertEqual(self.cards(), ['ABCD'])

    def test_continuous_message_and_short_filter_boundary(self):
        w = self.window
        w.store.data['ui']['decode_ignore_chars'] = 3
        self.send('ABC\r\n', 10)
        self.send('CQ JA1ABC\r\n', 20)
        self.assertEqual(self.cards(), ['CQ JA1ABC'])

    def test_buffered_path_does_not_call_live_preview_or_handler(self):
        w = self.window
        with patch.object(w, '_paint_rx_preview') as preview, patch.object(w, '_rx_live_char') as live:
            self.send('CQ\n', 10)
            preview.assert_not_called()
            live.assert_not_called()
        self.assertEqual(self.cards(), ['CQ'])

    def test_old_generation_does_not_split_or_extend_current_buffer(self):
        w = self.window
        self.send('CQ', 10)
        w._rx_char((w.audio.decode_generation - 1, 'X', 20))
        self.assertEqual(w.rx_buffer, 'CQ')
        self.assertEqual(w.rx_last_char_time, 10.16)

    def test_logs_printer_and_extraction_once_per_fragment(self):
        w = self.window
        w.store.data['ui']['decode_ignore_chars'] = 2
        with patch.object(w.printer, 'submit') as printer, patch.object(w, '_consider_auto_extract') as extract:
            self.send('AB', 10)
            self.send('CQ JA1ABC\r\n', 20)
            self.assertEqual(printer.call_count, 2)
            extract.assert_called_once_with('CQ JA1ABC')
            w.transcript.append.assert_any_call('RX AB')
            self.assertEqual(self.cards(), ['CQ JA1ABC'])

    def test_live_mark_wait_policy_is_unchanged(self):
        w = self.window
        w.decode_display.setCurrentIndex(w.decode_display.findData('live'))
        w._rx_char('A')
        card = w.rx_live_card
        w.rx_last_char_time = time.monotonic() - 3
        w.audio.decoder.last_signal_time = time.monotonic()
        w._check_rx_idle()
        self.assertIs(w.rx_live_card, card)
        self.assertFalse(card.finalized)

    def test_stop_and_clear_do_not_leave_buffer_for_next_reception(self):
        w = self.window
        self.send('AB', 10)
        w.decode_enabled.setChecked(False)
        w.decode_enabled.setChecked(True)
        self.send('CD\n', 12)
        self.assertEqual(self.cards(), ['CD'])

    def test_tx_finalization_does_not_auto_extract(self):
        w = self.window
        self.send('CQ JA1ABC', 10)
        with patch.object(w, '_consider_auto_extract') as extract:
            w._finalize_rx_card(extract=False)
            extract.assert_not_called()
        self.assertEqual(self.cards(), ['CQ JA1ABC'])


del Fixture
