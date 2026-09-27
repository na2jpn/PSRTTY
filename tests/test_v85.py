import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.parser import parse_exchange
from psrtty.macros import TEMPLATES, NORMAL_TEMPLATE_NAME, SHORT_TEMPLATE_NAME
from psrtty.ui.macro_dialog import MacroDialog
from psrtty.adif import QSORecord, ADIFLog
from psrtty.tuning import estimate_center, CenterTuning, tuning_display


class Logic85Tests(unittest.TestCase):
    def test_sender(self):
        for text, call in [('JA4HEU TU UA0KLKW','UA0KLKW'),('BA5AB TU UA0OK CQ','UA0OK'),
                           ('JF3DCH 599 18 18',''),('CQ DE JH1HST K',''),
                           ('JH1HST DE W1AW K','W1AW'),('CQ W1AW W1AW K','W1AW'),
                           ('W1AW W2BB','')]:
            with self.subTest(text=text): self.assertEqual(parse_exchange(text,'JH1HST').callsign,call)
        self.assertEqual(parse_exchange('JF3DCH 599 -18 18').exchange,'18')
        self.assertEqual(parse_exchange('599 K').exchange,'')

    def test_band_only_adif(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'202609.adi';p.write_text('<CALL:5>JA1AA<BAND:3>15m<EOR>')
            self.assertEqual(ADIFLog(Path(td)).load_recent()[0].band,'15m')

    def test_meter_tones_noise_and_boundaries(self):
        from psrtty.rtty_codec import encode_text_audio
        sr=48000;t=np.arange(8192)/sr
        for off in (-24,-15,-10,-5,0,5,10,15,24):
            x=encode_text_audio('CQ TEST JH1HST',mark_hz=2125+off,space_hz=2295+off)[16000:24192]
            value=estimate_center(x,sr,2125,2295)
            self.assertIsNotNone(value);self.assertAlmostEqual(value,off,delta=.15)
        for x in [np.zeros(8192),np.random.default_rng(5).normal(0,.1,8192),np.sin(2*np.pi*2125*t),np.sin(2*np.pi*2155*t)+np.sin(2*np.pi*2325*t)]:
            self.assertIsNone(estimate_center(x,sr,2125,2295))
        colors=['#0055dd','#006400','#80b918','#e0bd00','#f28c00','#e34234','#000000']
        for v,c in zip([0,5,9,11,15,20,25],colors):
            self.assertEqual(tuning_display(v)[1],c);self.assertEqual(tuning_display(-v)[1],c)
        self.assertEqual(tuning_display(-.01)[0],'C同調 0.0 Hz')
        meter=CenterTuning();frame=(10,t,(2125,2295,45.45))
        self.assertIsNone(meter.update(frame,sr,now=11))


class UI85Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_cq_sender_and_exchange(self):
        w=self.window; w.auto_get.setChecked(True);w.my_call.setText('JH1HST')
        self.assertTrue(w.cq_only.isChecked())
        w._consider_auto_extract('JA4HEU TU UA0KLKW');self.assertEqual(w.q_call.text(),'')
        w._consider_auto_extract('BA5AB TU UA0OK CQ');self.assertEqual(w.q_call.text(),'UA0OK')
        w._consider_auto_extract('JF3DCH 599 18 18');self.assertEqual(w.q_call.text(),'UA0OK');self.assertEqual(w.rcvd.text(),'18')
        w.auto_get.setChecked(False);w._card_selected('JH1HST DE W1AW 599 05 MA')
        self.assertEqual(w.q_call.text(),'W1AW');self.assertEqual(w.rcvd.text(),'05')
        w._card_selected('JF3DCH 599 19 19');self.assertEqual(w.q_call.text(),'W1AW');self.assertEqual(w.rcvd.text(),'19')
        w.q_call.clear();w.auto_get.setChecked(True);w.cq_only.setChecked(False)
        w._consider_auto_extract('JA4HEU TU UA0KLKW');self.assertEqual(w.q_call.text(),'UA0KLKW')

    def test_frequency_clear_uppercase_and_history(self):
        w=self.window;w.qsos=[QSORecord('W1AW',freq_hz=21080000),QSORecord('W1AW',freq_hz=28080000)]
        w.current_freq_hz=14080000;w.q_call.setText('w1aw');w.rcvd.setText('18');w.sent.setText('25')
        self.assertEqual(w.q_call.text(),'W1AW');self.assertIn('21MHz 28MHz',w.worked_label.text())
        self.assertNotIn('＊＊＊',w.worked_label.text());w.clear_on_frequency.setChecked(True)
        for delta in (5,10,15,19):
            w._radio_observed(14080000+delta);self.assertEqual(w.q_call.text(),'W1AW')
        w._radio_observed(14080020);self.assertEqual(w.q_call.text(),'');self.assertEqual(w.rcvd.text(),'');self.assertEqual(w.sent.text(),'25')
        w._radio_observed(21080000);w.q_call.setText('W1AW');self.assertIn('＊＊＊',w.worked_label.text())
        w.q_call.setText('JX1XXX');self.assertEqual(w.worked_label.text(),'初めての局です')

    def test_short_template(self):
        names=list(TEMPLATES);self.assertEqual(names.index(SHORT_TEMPLATE_NAME),names.index(NORMAL_TEMPLATE_NAME)+1)
        dlg=MacroDialog(self.store)
        try:
            dlg.template.setCurrentText(SHORT_TEMPLATE_NAME);dlg._apply_template()
            self.assertEqual(dlg.table.item(2,2).text(),'{HISCALL} DE {MYCALL} UR {RSTS} K')
            self.assertEqual(dlg.sent.text(),'');self.assertTrue(dlg.sent_fixed.isChecked())
        finally: dlg.close()

    def test_settings_disconnect_only_valid_save(self):
        w=self.window
        with patch.object(w,'disconnect_radio') as disconnect:
            w._settings();disconnect.assert_not_called();w.settings_window.reject();disconnect.assert_not_called()
            w._settings();dlg=w.settings_window
            dlg.rig.setCurrentText('IC-7300')
            with patch('psrtty.ui.settings_dialog.validate_radio',side_effect=ValueError('invalid')),patch('psrtty.ui.settings_dialog.QMessageBox.warning'):
                dlg._save();disconnect.assert_not_called()
            dlg._save();disconnect.assert_called_once()


del _Fixture

class Tuner85Tests(unittest.TestCase):
    def test_icom_command_and_gates(self):
        from unittest.mock import Mock
        from psrtty.civ import CIVController
        ctl=CIVController(0x94,model='IC-7300');ctl.ser=Mock();ctl.status.connected=True
        with patch.object(ctl,'read_tuner',return_value=0),patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',return_value=b'\xfe\xfe\xe0\x94\xfb\xfd'):
            self.assertTrue(ctl.start_tuner())
            ctl.ser.write.assert_called_with(b'\xfe\xfe\x94\xe0\x1c\x01\x02\xfd')
        ctl.ser.reset_mock()
        ctl.model='IC-7100'
        with patch.object(ctl,'read_tuner',return_value=None),patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',return_value=b'\xfe\xfe\xe0\x94\xfb\xfd'):
            self.assertTrue(ctl.start_tuner())

    def test_yaesu_model_commands_and_external_gate(self):
        from unittest.mock import Mock
        from psrtty.yaesu import YaesuController
        for model,command in [('FT-991 / FT-991A',b'AC002;'),('FTX-1',b'AC003;')]:
            ctl=YaesuController(model);ctl.ser=Mock();ctl.status.connected=True
            with patch.object(ctl,'read_tuner',return_value=0),patch.object(ctl,'read_transmitting',return_value=False):
                self.assertTrue(ctl.start_tuner());ctl.ser.write.assert_called_with(command)
            with patch.object(ctl,'_query',return_value='AC103;'):
                self.assertIsNone(ctl.read_tuner())
            ctl.ser.reset_mock()
            with patch.object(ctl,'read_tuner',return_value=0),patch.object(ctl,'read_transmitting',return_value=True):
                self.assertFalse(ctl.start_tuner());ctl.ser.write.assert_not_called()
