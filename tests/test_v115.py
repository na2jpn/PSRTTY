"""1.15 migration, audio, offline Auto CQ and meter regressions."""
import copy,json,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QMessageBox
from psrtty.config import ConfigStore
from psrtty.tx_level import gain_to_level,level_to_gain
from psrtty.radio_meters import ICOM_TABLES,interpolate,valid_reading
from psrtty.civ import CIVController
from psrtty.ui.settings_dialog import SettingsDialog
from psrtty.ui.tx_meters import ALCGauge
from tests import test_ui_v02 as fixture

class Model115Tests(unittest.TestCase):
    def test_curve(self):
        v=[level_to_gain(x) for x in range(101)]
        self.assertEqual(v[0],0);self.assertAlmostEqual(v[-1],.9)
        self.assertTrue(all(a<b for a,b in zip(v,v[1:])))
        self.assertLess(v[2]-v[1],.001)
        for x in range(101):self.assertEqual(gain_to_level(v[x]),x)
    def test_legacy_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'settings.json';p.write_text(json.dumps({'audio':{'input_device':'AUTO','output_device':'AUTO','tx_gain':.04123}}),encoding='utf-8')
            with patch('psrtty.config.ensure_runtime_dirs',return_value={'config':Path(d)}):
                s=ConfigStore(p,Path(d)/'macros.json');s.save();s=ConfigStore(p,Path(d)/'macros.json')
            self.assertEqual(s.data['audio']['input_device'],'AUTO');self.assertEqual(s.data['audio']['output_device'],'AUTO')
            self.assertEqual(s.data['audio']['tx_gain'],.04123);self.assertTrue(s.data['advanced']['show_swr'])
    def test_unselected_output_never_resolves_to_default(self):
        from psrtty.audio_devices import resolve_device
        backend=Mock()
        with self.assertRaises(ValueError): resolve_device(backend,'UNSET','output')
        backend.query_devices.assert_not_called();backend.query_hostapis.assert_not_called()

    def test_meter_validation(self):
        self.assertEqual(interpolate(48,ICOM_TABLES['IC-7100']['swr']),1.5)
        self.assertEqual(interpolate(24,ICOM_TABLES['IC-7100']['swr']),1.25)
        self.assertEqual(interpolate(43,ICOM_TABLES['IC-705']['pwr']),1)
        for v in [None,float('nan'),float('inf'),-1,True,'2']:self.assertIsNone(valid_reading(v))
        self.assertIsNone(interpolate(256,ICOM_TABLES['IC-7100']['swr']))
    def test_civ_reply_validation(self):
        ctl=CIVController(0x88);ctl.model='IC-7100';ctl.ser=Mock()
        with patch.object(ctl,'_control_ready',return_value=True),patch.object(ctl,'_read_response') as reply:
            reply.return_value=b'\xfe\xfe\xe0\x88\x15\x12\x00\x48\xfd';self.assertEqual(ctl.read_swr(),1.5)
            reply.return_value=b'\xfe\xfe\xe0\x88\x15\x11\x00\x48\xfd';self.assertIsNone(ctl.read_swr())
            reply.return_value=b'\xfe\xfe\xe0\x88\x15\x12\x00\xfa\xfd';self.assertIsNone(ctl.read_swr())

class UI115Tests(fixture.UITests):
    def test_new_audio_and_legacy_choice(self):
        d=SettingsDialog(self.store,self.window)
        self.assertEqual(d.audio_in.currentData(),'UNSET');self.assertEqual(d.audio_out.currentData(),'UNSET');self.assertEqual(d.audio_out.findData('AUTO'),-1);d.reject()
        self.store.data['audio']['output_device']='AUTO';d=SettingsDialog(self.store,self.window)
        self.assertEqual(d.audio_out.currentData(),'AUTO');self.assertIn('旧設定',d.audio_out.currentText())
        d.audio_out.addItem('radio',{'id':'radio','backend':'test','kind':'output'});d.audio_out.setCurrentIndex(d.audio_out.count()-1)
        self.assertEqual(d.audio_out.findData('AUTO'),-1);d.reject()
    def test_gain_preserved_and_zero_mutes(self):
        self.store.data['audio']['tx_gain']=.04123;d=SettingsDialog(self.store,self.window)
        d._save();self.assertEqual(self.store.data['audio']['tx_gain'],.04123)
        d=SettingsDialog(self.store,self.window);d.tx_gain.setValue(0)
        self.assertEqual(d._tx_gain_value(),0);self.assertEqual(self.window.audio.tx_gain,0)
        d._save();self.assertEqual(self.store.data['audio']['tx_gain'],0)
    def test_new_profile_resets_audio(self):
        self.store.data['audio']['input_device']='AUTO';self.store.data['audio']['output_device']='AUTO'
        d=SettingsDialog(self.store,self.window);d._add_profile()
        self.assertEqual(d.audio_in.currentData(),'UNSET');self.assertEqual(d.audio_out.currentData(),'UNSET')
        self.assertEqual(d.working_profiles[0]['audio']['output_device'],'AUTO');d.reject()
    def test_input_save_reapplies_same_device(self):
        d=SettingsDialog(self.store,self.window)
        with patch.object(self.window,'_restart_audio_input') as restart:d._save_audio_in();restart.assert_called_once()
        d.reject()
    def test_offline_cq_and_permission_removal(self):
        w=self.window;w.offline_tx.setChecked(True);self.assertTrue(w.auto_cq_button.isEnabled())
        with patch.object(w,'_send_text',return_value=True) as send:
            w._start_auto_cq();self.assertTrue(w.auto_cq_active);send.assert_called_once()
            w.offline_tx.setChecked(False);self.assertFalse(w.auto_cq_active)
    def test_meter_visibility_and_stale_data(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True;w.connecting=False;w.active_tx_id=1
        w.meter_updated=time.monotonic();w.main_meters={'alc':0,'swr':1.1,'pwr':10};w._paint_radio_meters()
        self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.radio_meter_text.text(),'SWR 1.1\nPWR 10.0')
        w.store.data['advanced']['show_swr']=False;w._paint_radio_meters();self.assertEqual(w.radio_meter_text.text(),'PWR 10.0')
        w.main_meters={'alc':None,'swr':float('nan'),'pwr':None};w._paint_radio_meters();self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.radio_meter_text.text(),'PWR --')
        w.main_meters={'alc':2,'swr':1.1,'pwr':10};w.meter_updated-=3;w._paint_radio_meters();self.assertFalse(w.alc_gauge.isHidden());self.assertEqual(w.alc_gauge.color,"#a59d92");w.active_tx_id=None
    def test_onset_colors(self):
        g=ALCGauge();g.set_reading(0,30,None);self.assertEqual(g.position,0)
        g.set_reading(0,30,40);self.assertEqual(g.color,'#70cde5');self.assertLess(g.position,.35)
        g.set_reading(2,40,40);self.assertEqual(g.color,'#208341')
        g.set_reading(3,40,40);self.assertEqual(g.color,'#e88919')
    def test_plain_center_tuning(self):
        w=self.window;w._refresh_center_tuning();self.assertIn('border:none',w.center_tuning.styleSheet());self.assertIn('font-weight:normal',w.center_tuning.styleSheet());self.assertFalse(w.center_tuning.font().bold())
    def test_current_profile_and_one_notice(self):
        other=copy.deepcopy(self.store.data['profiles'][0]);other['name']='Profile2';self.store.data['profiles'].append(other);self.store.data['active_profile']=1
        d=SettingsDialog(self.store,self.window);self.assertEqual(d.profile_index,1)
        with patch('psrtty.ui.settings_dialog.QDialog.exec',return_value=0) as notice:
            d.show();self.pump(.03);notice.assert_called_once();d.hide();d.show();self.pump(.03);notice.assert_called_once()
        d.reject()
