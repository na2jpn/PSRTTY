"""Regression: repeated FSK transmission must preserve the selected RX filter."""
import unittest
from unittest.mock import Mock, patch

from psrtty.civ import CIVController
from psrtty.fsk_models import ICOM_FSK, modes_for
from psrtty.config import RIG_MODELS
from psrtty.fsk_models import YAESU_FSK, KENWOOD_FSK
from psrtty.hamlib_radio import HamlibController, VFO


class Filter119Tests(unittest.TestCase):
    def controller(self, model='IC-7300'):
        ctl = CIVController(RIG_MODELS[model], model=model)
        ctl.ser = Mock()
        ctl.status.connected = True
        return ctl

    def reply(self, ctl, *payload):
        return bytes([254, 254, 224, ctl.address, *payload, 253])

    def test_all_icom_fsk_modes_keep_every_filter_across_repeated_starts(self):
        for model in ICOM_FSK:
            for mode in modes_for(model):
                for selected_filter in (1, 2, 3):
                    with self.subTest(model=model, mode=mode, filter=selected_filter):
                        ctl = self.controller(model)
                        code = 4 if mode == 'RTTY' else 8
                        reply = self.reply(ctl, 4, code, selected_filter)
                        with patch.object(ctl, 'read_transmitting', return_value=False), patch.object(ctl, '_read_response', return_value=reply):
                            self.assertTrue(ctl.set_fsk_mode(mode))
                            self.assertTrue(ctl.set_fsk_mode(mode))
                        self.assertEqual([c.args[0] for c in ctl.ser.write.call_args_list], [ctl._frame(4)] * 2)

    def test_mode_change_omits_filter_and_requires_readback(self):
        for actual, expected in ((8, True), (4, False)):
            ctl = self.controller()
            replies = [self.reply(ctl, 4, 4, 2), self.reply(ctl, 251), self.reply(ctl, 4, actual, 3)]
            with patch.object(ctl, 'read_transmitting', return_value=False), patch.object(ctl, '_read_response', side_effect=replies):
                self.assertEqual(ctl.set_fsk_mode('RTTY-R'), expected)
            self.assertEqual([c.args[0] for c in ctl.ser.write.call_args_list], [ctl._frame(4), ctl._frame(6, 8), ctl._frame(4)])

    def test_unreadable_current_mode_never_writes_mode(self):
        for reply in (b'', bytes.fromhex('FE FE E0 94 FA FD')):
            ctl = self.controller()
            with patch.object(ctl, 'read_transmitting', return_value=False), patch.object(ctl, '_read_response', return_value=reply):
                self.assertFalse(ctl.set_fsk_mode('RTTY'))
            self.assertEqual(ctl.ser.write.call_args_list[0].args[0], ctl._frame(4))
            self.assertEqual(ctl.ser.write.call_count, 1)

    def test_hamlib_all_fsk_models_preserve_filters_without_mode_write(self):
        for model in YAESU_FSK | KENWOOD_FSK:
            for mode, code in (('RTTY', 32), ('RTTY-R', 64)):
                for bandwidth in (250, 500, 2400):
                    with self.subTest(model=model, mode=mode, bandwidth=bandwidth):
                        ctl = HamlibController(model)
                        ctl.handle = 1
                        ctl.status.connected = True
                        ctl.lib = Mock()
                        ctl.lib.rig_parse_mode.return_value = code
                        def read(handle, vfo, actual, width):
                            actual._obj.value = code
                            width._obj.value = bandwidth
                            return 0
                        ctl.lib.rig_get_mode.side_effect = read
                        with patch.object(ctl, 'read_transmitting', return_value=False):
                            self.assertTrue(ctl.set_fsk_mode(mode))
                            self.assertTrue(ctl.set_fsk_mode(mode))
                        ctl.lib.rig_set_mode.assert_not_called()

    def test_hamlib_change_retains_no_change_width_and_verifies_mode(self):
        for final_mode, expected in ((32, True), (64, False)):
            ctl = HamlibController('FT-891')
            ctl.handle = 1
            ctl.status.connected = True
            ctl.lib = Mock()
            ctl.lib.rig_parse_mode.return_value = 32
            ctl.lib.rig_set_mode.return_value = 0
            readings = iter((64,) + (final_mode,) * 5)
            def read(handle, vfo, actual, width):
                actual._obj.value = next(readings)
                width._obj.value = 500
                return 0
            ctl.lib.rig_get_mode.side_effect = read
            with patch.object(ctl, 'read_transmitting', return_value=False):
                self.assertEqual(ctl.set_fsk_mode('RTTY'), expected)
            ctl.lib.rig_set_mode.assert_called_once_with(1, VFO, 32, -1)

    def test_hamlib_unknown_current_mode_never_writes(self):
        ctl = HamlibController('FT-891')
        ctl.handle = 1
        ctl.status.connected = True
        ctl.lib = Mock()
        ctl.lib.rig_parse_mode.return_value = 32
        ctl.lib.rig_get_mode.return_value = -1
        with patch.object(ctl, 'read_transmitting', return_value=False):
            self.assertFalse(ctl.set_fsk_mode('RTTY'))
        ctl.lib.rig_set_mode.assert_not_called()


if __name__ == '__main__':
    unittest.main()
