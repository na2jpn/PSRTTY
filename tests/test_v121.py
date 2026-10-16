"""Hamlib FSK retries, filter preservation, cancellation and diagnostics."""
import copy
import threading
import unittest
from unittest.mock import Mock, patch

from psrtty import i18n
from psrtty.audio_engine import AudioEngine
from psrtty.civ import CIVStatus, connect_configured
from psrtty.config import DEFAULT_CONFIG
from psrtty.fsk import start_fsk
from psrtty.fsk_models import YAESU_FSK, KENWOOD_FSK
from psrtty.hamlib_radio import HamlibController, VFO


class Mode121Tests(unittest.TestCase):
    def setUp(self):
        i18n.configure('ja')
        self.interval = patch('psrtty.hamlib_radio.FSK_VERIFY_INTERVAL', 0.)
        self.interval.start(); self.addCleanup(self.interval.stop)
        self.addCleanup(i18n.configure, 'ja')

    def controller(self, readings, model='FT-991 / FT-991A', set_code=0):
        ctl = HamlibController(model)
        ctl.handle = 1; ctl.status = CIVStatus(True, 'COM3')
        ctl.lib = Mock()
        ctl.lib.rig_parse_mode.side_effect = lambda token: {b'RTTY': 16, b'RTTYR': 256, b'USB': 4}.get(token, 0)
        ctl.lib.rig_set_mode.return_value = set_code
        replies = iter(readings)
        last = [(-5, 0)]
        def read(handle, vfo, actual, width):
            last[0] = next(replies, last[0])
            code, mode = last[0]
            actual._obj.value = mode; width._obj.value = 500
            return code
        ctl.lib.rig_get_mode.side_effect = read
        ptt = patch.object(ctl, 'read_transmitting', return_value=False)
        ptt.start(); self.addCleanup(ptt.stop)
        return ctl

    def test_every_hamlib_fsk_model_recovers_current_read_without_reapplying_mode(self):
        for model in YAESU_FSK | KENWOOD_FSK:
            for mode, value in (('RTTY', 16), ('RTTY-R', 256)):
                with self.subTest(model=model, mode=mode):
                    ctl = self.controller([(-5, 0), (-5, 0), (0, value)], model)
                    self.assertTrue(ctl.set_fsk_mode(mode))
                    self.assertEqual(ctl.lib.rig_get_mode.call_count, 3)
                    ctl.lib.rig_set_mode.assert_not_called()
                    self.assertEqual(ctl.fsk_mode_error, '')

    def test_mode_change_set_once_waits_through_stale_and_failed_readbacks(self):
        ctl = self.controller([(0, 4), (0, 4), (-5, 0), (0, 16)])
        self.assertTrue(ctl.set_fsk_mode('RTTY'))
        ctl.lib.rig_set_mode.assert_called_once_with(1, VFO, 16, -1)
        self.assertEqual(ctl.lib.rig_get_mode.call_count, 4)

    def test_fifth_readback_can_succeed(self):
        ctl = self.controller([(0, 4)] * 5 + [(0, 16)])
        self.assertTrue(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.lib.rig_get_mode.call_count, 6)
        ctl.lib.rig_set_mode.assert_called_once()

    def test_current_mode_read_failure_is_bounded_and_does_not_set_mode(self):
        ctl = self.controller([(-5, 0)])
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.lib.rig_get_mode.call_count, 5)
        ctl.lib.rig_set_mode.assert_not_called()
        self.assertEqual(ctl.fsk_mode_diagnostic, dict(reason='read', requested='RTTY', attempts=5, code=-5))
        self.assertIn('-5', ctl.fsk_mode_error)
        self.assertIn('5回', ctl.fsk_mode_error)

    def test_write_failure_and_post_write_read_failure_are_distinct(self):
        for set_code, readings, reason in ((-8, [(0, 4)], 'set'), (0, [(0, 4), (-5, 0)], 'verify_read')):
            ctl = self.controller(readings, set_code=set_code)
            self.assertFalse(ctl.set_fsk_mode('RTTY'))
            self.assertEqual(ctl.fsk_mode_diagnostic['reason'], reason)
            ctl.lib.rig_set_mode.assert_called_once()

    def test_mismatch_reports_observed_mode_and_raw_value(self):
        ctl = self.controller([(0, 4)])
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.fsk_mode_diagnostic['reason'], 'mismatch')
        self.assertIn('USB (0x4)', ctl.fsk_mode_error)
        self.assertIn('RTTY', ctl.fsk_mode_error)
        self.assertEqual(ctl.lib.rig_get_mode.call_count, 6)
        ctl.lib.rig_set_mode.assert_called_once()

    def test_unknown_tx_state_retries_but_confirmed_tx_is_never_changed(self):
        ctl = self.controller([(0, 16)])
        ctl.read_transmitting.side_effect = [None, None, False]
        self.assertTrue(ctl.set_fsk_mode('RTTY'))
        ctl.read_transmitting.side_effect = None
        ctl.read_transmitting.return_value = None
        ctl.lib.reset_mock()
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.fsk_mode_diagnostic['reason'], 'ptt_read')
        self.assertEqual(ctl.read_transmitting.call_count, 8)
        ctl.lib.rig_get_mode.assert_not_called()
        ctl.read_transmitting.return_value = True
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.fsk_mode_diagnostic['reason'], 'transmitting')
        ctl.lib.rig_set_mode.assert_not_called()

    def test_deadline_prevents_another_read_and_does_not_start_tx(self):
        ctl = self.controller([(-5, 0)])
        ticks = iter((0., 0., 3.))
        with patch('psrtty.hamlib_radio.time.monotonic', side_effect=lambda: next(ticks, 3.)):
            self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertLessEqual(ctl.lib.rig_get_mode.call_count, 1)
        ctl.lib.rig_set_mode.assert_not_called()

    def test_cancel_before_start_and_after_read_never_authorizes_transmit(self):
        for during_read in (False, True):
            ctl = self.controller([(0, 16)])
            stop = threading.Event()
            if during_read:
                def read(handle, vfo, actual, width):
                    actual._obj.value = 16; stop.set(); return 0
                ctl.lib.rig_get_mode.side_effect = read
            else:
                stop.set()
            self.assertFalse(ctl.set_fsk_mode('RTTY', cancel_event=stop))
            self.assertEqual(ctl.fsk_mode_diagnostic['reason'], 'cancelled')
            ctl.lib.rig_set_mode.assert_not_called()

    def test_reconnected_controller_during_read_is_rejected(self):
        ctl = self.controller([(0, 16)])
        def read(handle, vfo, actual, width):
            actual._obj.value = 16; ctl.handle = 2; return 0
        ctl.lib.rig_get_mode.side_effect = read
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.fsk_mode_diagnostic['reason'], 'not_ready')

    def test_new_success_clears_previous_failure(self):
        ctl = self.controller([(-5, 0)])
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        def read(handle, vfo, actual, width):
            actual._obj.value = 16; return 0
        ctl.lib.rig_get_mode.side_effect = read
        self.assertTrue(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.fsk_mode_error, '')
        self.assertEqual(ctl.fsk_mode_diagnostic, {})

    def test_errors_are_localized_and_format_in_every_language(self):
        keys = ['invalid','cancelled','not_ready','transmitting','ptt_read','read','set','verify_read','mismatch','exception','timeout']
        for language in i18n.LANGUAGES:
            i18n.configure(language)
            for key in keys:
                text = i18n.tr('v121.' + key).format(mode='RTTY', attempts=5, code=-5, observed='USB (0x4)', stage=i18n.tr('v121.stage_read'), error='I/O')
                self.assertNotIn('v121.', text)
                self.assertIn('Hamlib', text)
            ctl = self.controller([(0, 4)])
            self.assertFalse(ctl.set_fsk_mode('RTTY'))
            self.assertIn('USB (0x4)', ctl.fsk_mode_error)

    def test_connection_failure_keeps_diagnostic_after_disconnect(self):
        ctl = self.controller([(-5, 0)])
        ctl.connect = Mock(return_value=ctl.status)
        settings = dict(DEFAULT_CONFIG['radio'], model=ctl.model, tx_method='fsk')
        status = connect_configured(ctl, settings, DEFAULT_CONFIG['advanced'])
        self.assertFalse(status.connected)
        self.assertIn('-5', status.message)
        self.assertIn('5回', status.message)

    def test_driver_exception_identifies_stage(self):
        ctl = self.controller([(0, 16)])
        ctl.lib.rig_get_mode.side_effect = OSError('read failed')
        self.assertFalse(ctl.set_fsk_mode('RTTY'))
        self.assertEqual(ctl.fsk_mode_diagnostic['stage'], 'read')
        self.assertIn('read failed', ctl.fsk_mode_error)

    def test_worker_stop_interrupts_wait_and_never_keys_ptt(self):
        ctl = self.controller([(0, 4)])
        waiting = threading.Event()
        original = ctl.lib.rig_get_mode.side_effect
        def read(*args):
            result = original(*args)
            if ctl.lib.rig_get_mode.call_count >= 2: waiting.set()
            return result
        ctl.lib.rig_get_mode.side_effect = read
        engine = AudioEngine(); on = Mock(return_value=True); off = Mock(return_value=True); done = Mock()
        radio = dict(DEFAULT_CONFIG['radio'], model=ctl.model, com_port='COM3', ptt='CAT')
        options = dict(DEFAULT_CONFIG['fsk'], port='COM4')
        with patch('psrtty.hamlib_radio.FSK_VERIFY_INTERVAL', .5), patch('psrtty.fsk.SerialKey'), patch('psrtty.fsk.BitClock') as clock:
            ok, _ = start_fsk(engine, ctl, radio, options, DEFAULT_CONFIG['advanced'], on, off, done, text='RY')
            self.assertTrue(ok)
            try:
                self.assertTrue(waiting.wait(1))
                engine.stop_tx()
                engine._tx_thread.join(1)
                self.assertFalse(engine._tx_thread.is_alive())
                on.assert_not_called(); clock.assert_not_called()
                self.assertFalse(engine._tx_active)
                self.assertIsNone(engine._fsk_mode_confirmed)
            finally:
                engine.stop_tx(); engine._tx_thread.join(2)

    def test_worker_reports_diagnostic_and_no_ptt_on_failure(self):
        ctl = self.controller([(-5, 0)])
        engine = AudioEngine(); on = Mock(return_value=True); done = Mock()
        radio = dict(DEFAULT_CONFIG['radio'], model=ctl.model, com_port='COM3', ptt='CAT')
        with patch('psrtty.fsk.SerialKey'), patch('psrtty.fsk.BitClock') as clock:
            self.assertTrue(start_fsk(engine, ctl, radio, dict(DEFAULT_CONFIG['fsk'], port='COM4'), DEFAULT_CONFIG['advanced'], on, lambda: True, done, text='RY')[0])
            engine._tx_thread.join(2)
            self.assertFalse(engine._tx_thread.is_alive())
            on.assert_not_called(); clock.assert_not_called()
            self.assertFalse(done.call_args.args[0])
            self.assertIn('-5', done.call_args.args[1])


if __name__ == '__main__':
    unittest.main()
