import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QMenu

from psrtty.civ import CIVController
from psrtty.civ import CIVStatus
from psrtty.hamlib_radio import HamlibController, HAMLIB_MODELS
from tests.test_ui_v02 import UITests as _Fixture


class Radio103Tests(unittest.TestCase):
    def test_bundled_hamlib_model_ids_and_modes(self):
        self.assertEqual([HAMLIB_MODELS[m][0] for m in ('FTDX101D','FTDX101MP','FTDX3000')], [1040,1044,1037])
        self.assertEqual(HamlibController('TS-990S').operating_modes(),
            ('LSB-D1','USB-D1','LSB-D2','USB-D2','LSB-D3','USB-D3','LSB','USB'))
        self.assertEqual(HamlibController('TS-590SG').operating_modes()[:2], ('LSB-DATA','USB-DATA'))
        self.assertEqual(HamlibController('FTX-1').operating_modes()[:2], ('DATA-L','DATA-U'))

    def test_icom_plain_mode_disables_data_and_guards_transmit(self):
        ctl=CIVController(0xA4);ctl.ser=Mock();ctl.status.connected=True
        with patch.object(ctl,'read_transmitting',return_value=True):
            self.assertFalse(ctl.set_operating_mode('USB'))
        ctl.ser.write.assert_not_called()
        with patch.object(ctl,'read_transmitting',return_value=False), \
             patch.object(ctl,'_read_response',return_value=bytes.fromhex('fe fe e0 a4 fb fd')):
            self.assertTrue(ctl.set_operating_mode('USB'))
        self.assertEqual([c.args[0] for c in ctl.ser.write.call_args_list],
            [bytes.fromhex('fe fe a4 e0 1a 06 00 01 fd'),bytes.fromhex('fe fe a4 e0 06 01 fd')])

    def test_icom_mode_read_uses_data_flag(self):
        ctl=CIVController(0xA4);ctl.ser=Mock();ctl.status.connected=True
        frames=[bytes.fromhex('fe fe e0 a4 04 01 01 fd'),
                bytes.fromhex('fe fe e0 a4 1a 06 01 01 fd')]
        with patch.object(ctl,'_read_response',side_effect=frames):
            self.assertEqual(ctl.read_operating_mode(),'USB-D')

    def test_ts990_d3_mode_is_sent_and_verified(self):
        ctl=HamlibController('TS-990S');ctl.handle=1;ctl.status.connected=True
        mode={b'LSBD3':43,b'USBD3':40}
        lib=Mock();lib.rig_parse_mode.side_effect=lambda name:mode.get(name,0)
        lib.rig_get_mode.side_effect=lambda handle,vfo,out,width: (setattr(out._obj,'value',40) or 0)
        lib.rig_set_mode.return_value=0
        ctl.lib=lib
        with patch.object(ctl,'read_transmitting',return_value=False):
            self.assertTrue(ctl.set_operating_mode('USB-D3'))
        lib.rig_set_mode.assert_called_once()
        self.assertEqual(lib.rig_set_mode.call_args.args[2],40)


class UI103Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_view_menu_opens_existing_windows_and_mode_is_above_tune(self):
        from psrtty.ui.control_window import ControlWindow
        w=self.window;w.show()
        view=next(menu for menu in w.menuBar().findChildren(QMenu) if menu.title()=='表示')
        labels=[action.text() for action in view.actions()]
        self.assertEqual(labels[-2:],['コントロール','クロススコープ'])
        view.actions()[-2].trigger(); self.pump(.04)
        self.assertIsInstance(w.control_window,ControlWindow)
        self.assertLess(w.control_window.mode_box.geometry().y(),w.control_window.antenna_tune.geometry().y())
        self.assertEqual(set(w.control_window.mode_buttons), {'LSB-D','USB-D','LSB','USB'} if w.store.data['radio']['model']=='IC-705' else set())
        view.actions()[-1].trigger();self.pump(.04)
        self.assertTrue(w.scope_button.isChecked())
        self.assertTrue(w.scope_window.isVisible())

    def test_settings_caption_uses_kenwood_terms(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        dlg=SettingsDialog(self.store)
        dlg.rig.setCurrentIndex(dlg.rig.findData('TS-990S'))
        self.assertIn('LSB-D1',dlg.auto_mode.text())
        dlg.rig.setCurrentIndex(dlg.rig.findData('TS-890S'))
        self.assertIn('LSB-DATA',dlg.auto_mode.text())
        dlg.close()

    def test_mode_button_remains_clickable_during_status_refresh(self):
        w=self.window
        self.store.data['radio']['model']='IC-705'
        w.radio=CIVController(0xA4);w.radio.status=CIVStatus(True,'COM1',19200,14085000)
        w._set_radio_controls();w._show_control()
        dialog=w.control_window
        self.assertEqual(len(dialog.mode_buttons),4)
        for _ in range(4):dialog.refresh_enabled()
        button=dialog.mode_buttons['USB-D']
        self.assertTrue(button.isEnabled())
        dialog.busy=True;dialog.refresh_enabled()
        self.assertTrue(button.isEnabled())
        button.click()
        self.assertEqual(dialog.mode_pending,'USB-D')
        dialog.refresh_enabled()
        self.assertTrue(button.isChecked())
        dialog.busy=False

    def test_tune_does_not_blink_during_poll_or_misclassify_hamlib(self):
        w=self.window;self.store.data['radio']['model']='IC-705'
        w.radio=CIVController(0xA4);w.radio.status=CIVStatus(True,'COM1',19200,14085000)
        w.current_freq_hz=14085000;w._set_radio_controls();w._show_control()
        dialog=w.control_window;dialog.states['TUNER']=1;dialog.refresh_enabled()
        self.assertTrue(dialog.antenna_tune.isEnabled())
        dialog.busy=True;dialog.refresh_enabled()
        self.assertTrue(dialog.antenna_tune.isEnabled())
        dialog.antenna_tune.click()
        self.assertTrue(dialog.tuner_pending)
        dialog.busy=False;dialog.tuner_pending=False
        self.store.data['radio']['model']='FTX-1'
        w.radio=HamlibController('FTX-1');w.radio.status=CIVStatus(True,'COM2',38400,14085000)
        dialog.refresh_enabled()
        self.assertFalse(dialog.antenna_tune.isEnabled())

    def test_test_connection_expires_after_transmission_ends(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        dlg=SettingsDialog(self.store);ctl=Mock();ctl.cancel=Mock();ctl.status.connected=True
        dlg.test_controller=ctl;dlg.tx_testing=True
        callbacks=[]
        with patch('psrtty.ui.settings_dialog.QTimer.singleShot',side_effect=lambda delay,parent,cb:callbacks.append(cb)):
            dlg._expire_test_connection(dlg.test_connection_generation)
            self.assertIs(dlg.test_controller,ctl)
            self.assertEqual(len(callbacks),1)
            dlg.tx_testing=False;callbacks.pop()()
        ctl.disconnect.assert_called_once()
        self.assertIn('［接続］',dlg.test_note.text())
        dlg.close()


del _Fixture
