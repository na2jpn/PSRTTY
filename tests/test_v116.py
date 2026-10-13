import copy,threading,unittest,json
from unittest.mock import Mock,patch
from pathlib import Path
from psrtty.civ import CIVController,CIVStatus,connect_configured
from psrtty.hamlib_radio import HamlibController
from psrtty.yaesu import YaesuController
from psrtty.config import ConfigStore,DEFAULT_CONFIG
from tests.test_hamlib_089 import FakeLibrary
from tests.test_v04 import FakeCAT
from tests import test_ui_v02 as fixture

class Mode116Tests(unittest.TestCase):
    def test_connect_dispatch_and_auto_off(self):
        for mode in ('LSB-D','USB-D','LSB','USB'):
            ctl=Mock();ctl.cancel.is_set.return_value=False;ctl.status=CIVStatus(True,'COM3',9600,144100000,'OK');ctl.connect.return_value=ctl.status
            ctl.set_operating_mode.return_value=True;ctl.set_data_mode.return_value=True
            self.assertTrue(connect_configured(ctl,{'auto_data_mode':True},{'data_mode':mode}).connected)
            expected=ctl.set_operating_mode if mode in ('LSB','USB') else ctl.set_data_mode
            other=ctl.set_data_mode if mode in ('LSB','USB') else ctl.set_operating_mode
            expected.assert_called_once_with(mode);other.assert_not_called()
        ctl.reset_mock();connect_configured(ctl,{'auto_data_mode':False},{'data_mode':'USB'})
        ctl.set_operating_mode.assert_not_called();ctl.set_data_mode.assert_not_called()
    def test_failed_plain_mode_disconnects(self):
        ctl=Mock();ctl.status=CIVStatus(True);ctl.connect.return_value=ctl.status;ctl.cancel.is_set.return_value=False;ctl.set_operating_mode.return_value=False
        connect_configured(ctl,{}, {'data_mode':'LSB'});ctl.disconnect.assert_called_once()
    def test_icom_plain_turns_data_off(self):
        for model in ('IC-9700','IC-7760'):
            for mode,digit in (('LSB',0),('USB',1)):
                ctl=CIVController(0xA2,model=model);ctl.ser=Mock();ctl.status.connected=True
                with patch.object(ctl,'read_transmitting',return_value=False),patch.object(ctl,'_read_response',return_value=bytes.fromhex('FE FE E0 A2 FB FD')):
                    self.assertTrue(ctl.set_operating_mode(mode))
                commands=[x.args[0][4:-1] for x in ctl.ser.write.call_args_list]
                self.assertEqual(commands,[bytes([0x1A,0x06,0,0 if model=='IC-7760' else 1]),bytes([6,digit])])
    def test_hamlib_plain_modes_and_tx_guard(self):
        class Library(FakeLibrary):
            def rig_parse_mode(self,name):return {b'LSB':1,b'USB':2,b'LSBD1':4,b'USBD1':8}.get(name,0)
        for model in ('FT-710','TS-990S'):
            lib=Library();ctl=HamlibController(model)
            with patch('psrtty.hamlib_radio.load_library',return_value=(lib,None)):
                for mode in ('LSB','USB'):
                    self.assertTrue(connect_configured(ctl,{'com_port':'COM3','ptt':'CAT','cat_baud':38400},{'data_mode':mode}).connected)
                    self.assertEqual(ctl.read_operating_mode(),mode)
                lib.ptt=1;self.assertFalse(ctl.set_operating_mode('LSB'));ctl.disconnect()
    def test_legacy_cat_plain_modes(self):
        fake=FakeCAT();ctl=YaesuController('FTX-1')
        with patch('psrtty.yaesu.serial') as serial:
            serial.Serial.return_value=fake
            for mode,digit in (('LSB','1'),('USB','2')):
                self.assertTrue(connect_configured(ctl,{'com_port':'COM3','ptt':'CAT','cat_baud':38400},{'data_mode':mode}).connected)
                self.assertEqual(fake.mode,digit)
            ctl.disconnect()

class UI116Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def test_saved_modes_and_caption_for_all_families(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        d=SettingsDialog(self.store,self.window)
        self.assertEqual([d.data_mode.itemText(i) for i in range(d.data_mode.count())],['LSB-D','USB-D','LSB','USB'])
        for model in ('IC-9700','FT-710','TS-990S','FTX-1'):
            d.rig.setCurrentIndex(d.rig.findData(model))
            for mode in ('LSB','USB'):
                d.data_mode.setCurrentText(mode);self.assertIn(mode,d.auto_mode.text());self.assertNotIn('DATA',d.auto_mode.text());self.assertNotIn(mode+'-D',d.auto_mode.text())
        d.close()
    def test_frequency_interval_and_pending_request(self):
        w=self.window;self.assertEqual(w.poll_timer.interval(),500)
        w.radio=Mock();w.radio.status.connected=True;w.connecting=False;w.polling=False
        with patch('psrtty.ui.main_window.BackgroundJob') as job:
            w._poll_radio();w._poll_radio();self.assertEqual(job.call_count,1)
        self.assertTrue(w.polling)
    def test_profile_round_trip_preserves_plain_modes(self):
        # Store serialization keeps the four mode values without migration loss.
        store=ConfigStore(Path(self.tmp.name)/'settings.json',Path(self.tmp.name)/'macros.json')
        for mode in ('LSB-D','USB-D','LSB','USB'):
            store.data['advanced']['data_mode']=mode;store.save()
            fresh=ConfigStore(store.config_path,store.macro_path);self.assertEqual(fresh.data['advanced']['data_mode'],mode)
        self.assertEqual(DEFAULT_CONFIG['advanced']['data_mode'],'LSB-D')
