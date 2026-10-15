"""FSK meters must remain available without using AFSK level advice."""
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from tests import test_ui_v02 as fixture
from psrtty import i18n
from psrtty.audio_engine import AudioEngine
from psrtty.config import DEFAULT_CONFIG
from psrtty.civ import CIVController
from psrtty.fsk import SerialKey, start_fsk
from psrtty.fsk_models import ICOM_FSK, YAESU_FSK, KENWOOD_FSK
from psrtty.ui.tx_meters import ALCGauge


class Meter120Tests(unittest.TestCase):
    setUpClass = classmethod(fixture.UITests.setUpClass.__func__)
    setUp = fixture.UITests.setUp
    def tearDown(self):
        # These UI cases simulate an active worker without starting one.
        self.window.audio._tx_active = False
        self.window.active_tx_id = None
        fixture.UITests.tearDown(self)

    def configure(self, model='IC-7300', transmitting=True):
        w = self.window
        w.store.data['radio'].update(model=model, tx_method='fsk')
        w.radio = Mock()
        w.radio.status.connected = True
        w.connecting = False
        w.polling = False
        w.active_tx_id = 19 if transmitting else None
        w.audio._tx_active = transmitting
        w.audio._fsk_mode_confirmed = 'RTTY' if transmitting else None
        w.radio.read_operating_mode.return_value = 'RTTY'
        w.radio.read_swr.return_value = 1.7
        w.radio.read_power.return_value = 25.
        w._ensure_meter_connection()
        return w

    def poll(self):
        w = self.window
        w.alc_last_poll = 0
        def immediate(parent, work, done):
            done(work(), None)
        with patch('psrtty.ui.main_window.BackgroundJob', side_effect=immediate):
            w._poll_main_alc()

    def test_fsk_meters_all_supported_models_without_alc_or_mode_queries_during_tx(self):
        for model in ICOM_FSK | YAESU_FSK | KENWOOD_FSK:
            with self.subTest(model=model):
                w = self.configure(model)
                self.poll()
                self.assertEqual(w.radio_meter_text.text(), 'SWR 1.7\nPWR 25.0')
                w.radio.read_swr.assert_called_once()
                w.radio.read_power.assert_called_once()
                w.radio.read_alc.assert_not_called()
                w.radio.read_operating_mode.assert_not_called()
                self.assertIs(w.alc_gauge.fsk, True)
                self.assertEqual(w.level.format(), 'FSK')

    def test_rx_fsk_badge_requires_recent_readback_and_clears_on_mode_or_connection_change(self):
        w = self.configure(transmitting=False)
        self.poll()
        self.assertIs(w.alc_gauge.fsk, True)
        w._fsk_mode_observed = ('RTTY', time.monotonic() - 3)
        w._paint_radio_meters()
        self.assertIs(w.alc_gauge.fsk, False)
        for mode in ('USB', None):
            w.radio.read_operating_mode.return_value = mode
            self.poll()
            self.assertIs(w.alc_gauge.fsk, False)
        w.radio.read_operating_mode.return_value = 'RTTY-R'
        self.poll()
        self.assertIs(w.alc_gauge.fsk, True)
        w.connection_generation += 1
        w._paint_radio_meters()
        self.assertIs(w.alc_gauge.fsk, False)
        w.radio.status.connected = False
        w._paint_radio_meters()
        self.assertTrue(w.alc_gauge.isHidden())

    def test_tx_badge_requires_worker_confirmation_not_just_profile(self):
        w = self.configure()
        w.audio._fsk_mode_confirmed = None
        self.poll()
        self.assertEqual(w.level.format(), '--')
        self.assertIs(w.alc_gauge.fsk, False)
        w.audio._fsk_mode_confirmed = 'RTTY-R'
        w._paint_main_alc(); w._paint_radio_meters()
        self.assertEqual(w.level.format(), 'FSK')
        self.assertIs(w.alc_gauge.fsk, True)

    def test_fsk_never_displays_audio_warning_even_at_zero_power(self):
        w = self.configure()
        w._meter_tx_started = time.monotonic() - 3
        w.radio.read_power.return_value = 0.
        self.poll()
        self.assertIn('PWR 0.0', w.radio_meter_text.text())
        self.assertTrue(w.audio_check_notice.isHidden())

    def test_meter_switches_and_two_second_hold_remain_effective(self):
        w = self.configure()
        self.poll()
        w._hold_tx_meters()
        w.active_tx_id = None; w.audio._tx_active = False
        w.audio._fsk_mode_confirmed = None
        w.main_meters = {'swr': 1., 'pwr': 0.}
        with patch('psrtty.ui.main_window.time.monotonic', return_value=w._meter_hold_until - .1):
            w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(), 'SWR 1.7\nPWR 25.0')
        with patch('psrtty.ui.main_window.time.monotonic', return_value=w._meter_hold_until + .1):
            w._paint_radio_meters()
        self.assertEqual(w.radio_meter_text.text(), 'SWR --\nPWR 0.0')
        w.store.data['advanced']['show_swr'] = False
        w.radio.reset_mock(); self.poll()
        w.radio.read_swr.assert_not_called()
        self.assertNotIn('SWR', w.radio_meter_text.text())
        w.store.data['advanced']['show_pwr'] = False
        self.poll()
        self.assertTrue(w.radio_meter_text.isHidden())

    def test_stale_completion_from_previous_tx_is_ignored(self):
        w = self.configure()
        jobs = []
        def defer(parent, work, done):
            jobs.append((work, done))
        with patch('psrtty.ui.main_window.BackgroundJob', side_effect=defer):
            w._poll_main_alc()
        work, done = jobs.pop()
        result = work()
        w.active_tx_id = 20
        done(result, None)
        self.assertEqual(w.main_meters, {})

    def test_afsk_and_rx_level_restore_normal_display(self):
        w = self.configure()
        self.poll()
        w.store.data['radio']['tx_method'] = 'afsk'
        w.radio.read_alc.return_value = 2
        self.poll()
        self.assertIsNone(w.alc_gauge.fsk)
        self.assertEqual(w.level_heading.text(), 'ALC')
        self.assertFalse(w.level.isTextVisible())
        w._paint_rx_level()
        self.assertEqual(w.level_heading.text(), 'RX')
        self.assertFalse(w.level.isTextVisible())

    def test_unavailable_meter_values_do_not_create_readings(self):
        w = self.configure()
        w.radio.read_swr.return_value = None
        w.radio.read_power.return_value = None
        self.poll()
        self.assertTrue(w.radio_meter_text.isHidden())
        self.assertIs(w.alc_gauge.fsk, True)

    def test_fsk_hint_and_drawing_in_every_language(self):
        g = ALCGauge()
        try:
            for language in i18n.LANGUAGES:
                i18n.configure(language)
                g.set_fsk(True)
                self.assertEqual(g.toolTip(), i18n.tr('v120.fsk_hint'))
                self.assertNotIn('v120.', g.toolTip())
                self.assertFalse(g.grab().isNull())
            g.set_reading(2, 1, None)
            self.assertIsNone(g.fsk)
        finally:
            i18n.configure('ja')


class Keying120Tests(unittest.TestCase):
    def test_shared_com_key_line_can_change_while_meter_response_waits(self):
        ctl = CIVController(0x94, 'IC-7300')
        ctl.ser = SimpleNamespace(dtr=False, reset_input_buffer=lambda: None, write=lambda value: None)
        ctl.status.connected = True
        entered = threading.Event(); release = threading.Event(); keyed = threading.Event()
        def response(*args, **kwargs):
            entered.set()
            release.wait(2)
            return bytes.fromhex('FE FE E0 94 15 12 00 10 FD')
        radio = dict(DEFAULT_CONFIG['radio'], model='IC-7300', com_port='COM3')
        key = SerialKey(ctl, radio, dict(DEFAULT_CONFIG['fsk']))
        key.open()
        with patch.object(ctl, '_read_response', side_effect=response):
            reader = threading.Thread(target=ctl.read_swr)
            reader.start()
            writer = None
            try:
                self.assertTrue(entered.wait(1))
                def write():
                    key.mark(False)
                    keyed.set()
                writer = threading.Thread(target=write)
                writer.start()
                self.assertTrue(keyed.wait(1), 'Meter wait blocked the FSK output line')
                self.assertTrue(ctl.ser.dtr)
            finally:
                release.set(); reader.join(2)
                if writer: writer.join(2)
                key.close()

    def test_mode_confirmation_is_set_only_after_success_and_cleared_after_tx(self):
        for mode_ok in (True, False):
            engine = AudioEngine()
            ctl = Mock(); ctl.status.connected = True
            ctl.set_fsk_mode.return_value = mode_ok
            radio = dict(DEFAULT_CONFIG['radio'], model='IC-7300', com_port='COM3')
            seen = []
            def ptt():
                seen.append(engine._fsk_mode_confirmed)
                return True
            with patch('psrtty.fsk.SerialKey'), patch('psrtty.fsk.BitClock') as clock:
                clock.return_value.emit.return_value = True
                clock.return_value.code.return_value = True
                ok, _ = start_fsk(engine, ctl, radio, dict(DEFAULT_CONFIG['fsk']),
                                  DEFAULT_CONFIG['advanced'], ptt, lambda: True, Mock(), text='RY')
                self.assertTrue(ok)
                engine._tx_thread.join(2)
                self.assertFalse(engine._tx_thread.is_alive())
            self.assertEqual(seen, ['RTTY'] if mode_ok else [])
            self.assertIsNone(engine._fsk_mode_confirmed)
            self.assertFalse(engine._tx_active)
