import unittest
from unittest.mock import Mock
from psrtty.radio import create_controller
from psrtty.config import RIG_MODELS
from tests.test_v75 import UI75Tests as _Fixture

MODELS={'IC-7200':0x76,'IC-7410':0x80,'IC-7600':0x7A,'IC-9100':0x7C}

class Radio77Tests(unittest.TestCase):
    def test_model_commands_with_custom_address_and_no_ack(self):
        for model,address in MODELS.items():
            self.assertEqual(RIG_MODELS[model],address)
            ctl=create_controller({'model':model,'civ_address':'55'})
            ctl.ser=Mock();ctl.status.connected=True
            ctl._read_response=Mock(return_value=bytes.fromhex('FE FE E0 55 FB FD'))
            self.assertTrue(ctl.set_data_mode('USB-D'))
            sub='04' if model=='IC-7200' else '06'
            self.assertEqual([c.args[0] for c in ctl.ser.write.call_args_list],
                [bytes.fromhex('FE FE 55 E0 06 01 FD'),bytes.fromhex(f'FE FE 55 E0 1A {sub} 01 01 FD')])
            self.assertTrue(ctl.set_ptt(True));self.assertTrue(ctl.set_ptt(False))
            self.assertEqual(ctl.ser.write.call_args_list[-2].args[0],bytes.fromhex('FE FE 55 E0 1C 00 01 FD'))
            self.assertEqual(ctl.ser.write.call_args_list[-1].args[0],bytes.fromhex('FE FE 55 E0 1C 00 00 FD'))
            ctl.ser.write.reset_mock();self.assertIsNone(ctl.read_filter());ctl.ser.write.assert_not_called()
            ctl._read_response.return_value=b''
            self.assertFalse(ctl.set_ptt(True));self.assertFalse(ctl.set_data_mode('LSB-D'))

class UI77Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump
    dialog=_Fixture.dialog

    def test_period_labels_stay_adjacent_when_window_widens(self):
        d=self.dialog([],0);d.show();self.pump(.03)
        for width in (1080,1500):
            d.resize(width,720);self.pump(.03)
            self.assertLess(d.start.x()-d.start_label.geometry().right(),20)
            self.assertLess(d.end.x()-d.end_label.geometry().right(),20)
            self.assertLess(d.end_label.x()-d.start.geometry().right(),40)

del _Fixture
