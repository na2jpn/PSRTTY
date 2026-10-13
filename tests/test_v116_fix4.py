import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from psrtty.civ import CIVController,CIVStatus,connect_configured
from psrtty.config import ConfigStore,DEFAULT_CONFIG
from psrtty.radio_support import USB_MOD_INPUT
from tests.test_ui_v02 import UITests as Fixture

class UsbInputTests(unittest.TestCase):
    def controller(self,model='IC-9700'):
        c=CIVController(0xA2,model=model);c.ser=Mock();c.status.connected=True;return c
    def test_exact_command_per_model_and_mode_readback(self):
        for model,(off,on,value) in USB_MOD_INPUT.items():
            for mode in ('LSB','USB','LSB-D','USB-D'):
                c=self.controller(model);menu=on if mode.endswith('-D') else off
                prefix=bytes.fromhex('FE FE E0 A2 1A 05')+menu
                with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_operating_mode',return_value=mode),patch.object(c,'_read_response',side_effect=[prefix+b'\x00\xfd',bytes.fromhex('FE FE E0 A2 FB FD'),prefix+bytes([value,0xFD])]):
                    self.assertTrue(c.set_usb_mod_input())
                self.assertEqual([x.args[0] for x in c.ser.write.call_args_list],[c._frame(0x1A,5,*menu),c._frame(0x1A,5,*menu,value),c._frame(0x1A,5,*menu)])
    def test_already_usb_only_reads(self):
        c=self.controller();menu=USB_MOD_INPUT[c.model][1]
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_operating_mode',return_value='LSB-D'),patch.object(c,'_read_response',return_value=bytes.fromhex('FE FE E0 A2 1A 05')+menu+b'\x03\xfd'):
            self.assertTrue(c.set_usb_mod_input())
        self.assertEqual(c.ser.write.call_count,1)
    def test_bad_readback_nak_and_wrong_menu_fail_closed(self):
        prefix=bytes.fromhex('FE FE E0 A2 1A 05 01 16')
        for replies in ([prefix+b'\x01\xfd',bytes.fromhex('FE FE E0 A2 FA FD')],[prefix+b'\x01\xfd',bytes.fromhex('FE FE E0 A2 FB FD'),prefix+b'\x01\xfd'],[bytes.fromhex('FE FE E0 A2 1A 05 01 15 03 FD')],[bytes.fromhex('FE FE A2 E0 1A 05 01 16 03 FD')]):
            c=self.controller()
            with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_operating_mode',return_value='LSB-D'),patch.object(c,'_read_response',side_effect=replies):self.assertFalse(c.set_usb_mod_input())
    def test_tx_unknown_mode_cancel_and_unsupported_never_write(self):
        for model,tx,mode,cancel in [('IC-9700',True,'LSB-D',False),('IC-9700',None,'LSB-D',False),('IC-9700',False,None,False),('IC-9700',False,'LSB-D',True),('FT-891',False,'LSB-D',False)]:
            c=self.controller(model)
            if cancel:c.cancel.set()
            with patch.object(c,'read_transmitting',return_value=tx),patch.object(c,'read_operating_mode',return_value=mode):self.assertFalse(c.set_usb_mod_input())
            c.ser.write.assert_not_called()
    def test_connection_shared_off_and_failure(self):
        c=Mock(model='IC-9700');c.status=CIVStatus(True);c.cancel.is_set.return_value=False;c.set_usb_mod_input.return_value=True
        connect_configured(c,{'auto_data_mode':False,'auto_usb_mod_input':True},{'data_mode':'USB-D'});c.set_usb_mod_input.assert_called_once_with();c.set_data_mode.assert_not_called()
        c.reset_mock();c.status=CIVStatus(True);connect_configured(c,{'auto_usb_mod_input':False},{'data_mode':'LSB-D'});c.set_usb_mod_input.assert_not_called()
        c.status=CIVStatus(True);c.set_usb_mod_input.return_value=False
        def disconnect():c.status=CIVStatus()
        c.disconnect.side_effect=disconnect
        status=connect_configured(c,{'auto_data_mode':False,'auto_usb_mod_input':True},{})
        self.assertFalse(status.connected);self.assertTrue(status.message)
    def test_migration_fresh_legacy_profiles_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'settings.json';m=Path(t)/'macros.json'
            s=ConfigStore(p,m);self.assertTrue(s.data['radio']['auto_usb_mod_input']);s.save();self.assertTrue(ConfigStore(p,m).data['radio']['auto_usb_mod_input'])
            raw=copy.deepcopy(DEFAULT_CONFIG);raw['radio'].pop('auto_usb_mod_input');raw['profiles'][0]['radio'].pop('auto_usb_mod_input');raw['profiles'].append(copy.deepcopy(raw['profiles'][0]));raw['profiles'][1]['radio']['auto_usb_mod_input']=True
            p.write_text(json.dumps(raw),encoding='utf-8');s=ConfigStore(p,m);self.assertFalse(s.data['radio']['auto_usb_mod_input']);self.assertTrue(s.data['profiles'][1]['radio']['auto_usb_mod_input']);s.activate_profile(1);self.assertTrue(s.data['radio']['auto_usb_mod_input'])
            raw.pop('profiles');p.write_text(json.dumps(raw),encoding='utf-8');self.assertFalse(ConfigStore(p,m).data['radio']['auto_usb_mod_input'])

class UsbInputUI(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    def test_visibility_order_default_and_copy(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        d=SettingsDialog(self.store,self.window)
        for model in ('IC-9700','IC-7300','IC-705'):
            d.rig.setCurrentIndex(d.rig.findData(model));self.assertFalse(d.auto_usb_input.isHidden());self.assertFalse(d.usb_input_note.isHidden());self.assertTrue(d.auto_usb_input.isChecked())
        self.assertGreater(d.specific_form.getWidgetPosition(d.auto_usb_input)[0],d.specific_form.getWidgetPosition(d.auto_mode)[0]);self.assertIn('#777777',d.usb_input_note.styleSheet())
        for model in ('FT-891','IC-7760','IC-735'):
            d.rig.setCurrentIndex(d.rig.findData(model));self.assertTrue(d.auto_usb_input.isHidden());self.assertTrue(d.usb_input_note.isHidden())
        d.rig.setCurrentIndex(d.rig.findData('IC-9700'));d.auto_usb_input.setChecked(False);d._add_profile();self.assertFalse(d.auto_usb_input.isChecked());d.close()
    def test_all_eight_languages_have_usb_port_explanation(self):
        from psrtty import i18n
        from psrtty.ui.settings_dialog import SettingsDialog
        for code in i18n.LANGUAGES:
            i18n.configure(code);d=SettingsDialog(self.store,self.window)
            self.assertEqual(d.auto_usb_input.text(),i18n.tr('v116.usb_mod_auto'));self.assertIn('SSB',d.usb_input_note.text());self.assertIn('ACC',d.usb_input_note.text());d.close()
        i18n.configure('ja')

del Fixture
