import copy
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch
from psrtty.config import DEFAULT_CONFIG
from psrtty.radio import create_controller, validate_radio
from psrtty.civ import connect_configured, CIVStatus
from psrtty.hamlib_radio import HAMLIB_MODELS
from psrtty.manual_radio import MANUAL_MODEL
from psrtty.tx_keying import keying_callbacks
from psrtty.log_delete import snapshot, delete_all_qso_logs
from psrtty.windows_volume import WindowsVolume, VolumeState
from tests.test_ui_v02 import UITests as Fixture


class LogDelete117Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'202610.adi').write_bytes(b'<CALL:3>ABC <EOR>\r\n')
        (self.root/'202609.adi').write_bytes(b'<CALL:3>DEF <EOR>\r\n')
        (self.root/'20261015_all.txt').write_text('transcript')
        (self.root/'backups').mkdir();(self.root/'backups/old.bak').write_text('old')

    def test_verified_backup_and_retained_transcript(self):
        expected=snapshot(self.root)
        contents={name:(self.root/name).read_bytes() for name in expected}
        backup=delete_all_qso_logs(self.root,expected)
        self.assertEqual(snapshot(self.root),{})
        with zipfile.ZipFile(backup) as z:
            for name,body in contents.items():self.assertEqual(z.read(name),body)
        self.assertEqual((self.root/'backups/old.bak').read_text(),'old')
        self.assertTrue((self.root/'20261015_all.txt').exists())

    def test_backup_failure_never_deletes(self):
        before=snapshot(self.root)
        with patch('psrtty.log_delete.create_log_backup',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):delete_all_qso_logs(self.root,before)
        self.assertEqual(snapshot(self.root),before)

    def test_stale_confirmation_never_deletes_new_qso(self):
        before=snapshot(self.root)
        with (self.root/'202610.adi').open('ab') as f:f.write(b'NEW')
        after=snapshot(self.root)
        with self.assertRaises(RuntimeError):delete_all_qso_logs(self.root,before)
        self.assertEqual(snapshot(self.root),after)

    def test_second_move_failure_restores_all_files(self):
        before=snapshot(self.root);real=os.replace
        def move(a,b):
            if Path(a).parent==self.root and Path(a).name=='202610.adi':raise OSError('blocked')
            return real(a,b)
        with patch('psrtty.log_delete.os.replace',side_effect=move):
            with self.assertRaises(OSError):delete_all_qso_logs(self.root,before)
        self.assertEqual(snapshot(self.root),before)


class Radio117Tests(unittest.TestCase):
    def test_new_rig_ids_and_external_ptt_for_every_family(self):
        self.assertEqual(HAMLIB_MODELS['FT-950'][0],1028)
        self.assertEqual(HAMLIB_MODELS['FT-450'][0],1027)
        for model in HAMLIB_MODELS:
            values=dict(DEFAULT_CONFIG['radio'],model=model,ptt='外部接続',com_port='COM5',cat_baud=19200)
            validate_radio(values)
            ctl=Mock();ctl.status=CIVStatus(True,'COM5',19200,14080000);ctl.connect.return_value=ctl.status;ctl.cancel.is_set.return_value=False
            connect_configured(ctl,dict(values,auto_data_mode=False),{})
            ctl.connect.assert_called_once_with('COM5',19200)

    def test_manual_has_no_cat_and_external_callbacks_never_use_cat(self):
        ctl=create_controller(dict(DEFAULT_CONFIG['radio'],model=MANUAL_MODEL,ptt='外部接続'))
        self.assertTrue(connect_configured(ctl,{},{}).connected)
        self.assertIsNone(ctl.read_frequency())
        seq=Mock();seq.config={'enabled':True,'role':'ptt'};seq.before_ptt.return_value=True
        with patch.object(ctl,'set_ptt') as cat:
            on,off=keying_callbacks(ctl,'外部接続',seq,lambda:True)
            self.assertTrue(on());self.assertTrue(ctl.read_transmitting())
            off();self.assertFalse(ctl.read_transmitting());cat.assert_not_called()
        seq.after_ptt.assert_called_once()

    def test_sessions_target_our_pid_and_skip_expired_or_other_apps(self):
        obj=WindowsVolume.__new__(WindowsVolume);obj.kind='output';obj._interfaces=(object,object)
        sessions=[]
        for pid,state in [(os.getpid(),1),(os.getpid()+1,1),(os.getpid(),2)]:
            v=Mock();v.GetProcessId.return_value=pid;v.GetState.return_value=state;v.QueryInterface.return_value=v
            sessions.append(v)
        enum=Mock();enum.GetCount.return_value=3;enum.GetSession.side_effect=sessions
        obj.control=Mock();obj.control.GetSessionEnumerator.return_value=enum
        self.assertEqual(obj._sessions(),[sessions[0]])

    def test_read_does_not_write_and_volume_set_does_not_unmute(self):
        obj=WindowsVolume.__new__(WindowsVolume);obj.kind='input';obj.control=Mock()
        obj.control.GetMasterVolumeLevelScalar.return_value=.2;obj.control.GetMute.return_value=True
        self.assertEqual(obj.read(),VolumeState(20,True))
        obj.control.SetMasterVolumeLevelScalar.assert_not_called();obj.control.SetMute.assert_not_called()
        obj.set_percent(40);obj.control.SetMasterVolumeLevelScalar.assert_called_once_with(.4,None)
        obj.control.SetMute.assert_not_called()

    def test_volume_binds_exact_endpoint_not_default_device(self):
        import types
        api=types.ModuleType('pycaw.pycaw')
        api.AudioUtilities=Mock()
        for name in ('IAudioEndpointVolume','IAudioSessionManager2','IAudioSessionControl2','ISimpleAudioVolume'):
            setattr(api,name,type(name,(),{'_iid_':name}))
        selection={'backend':'wasapi','id':'chosen-id','kind':'output','name':'USB Audio CODEC'}
        with patch.dict('sys.modules',{'comtypes':types.SimpleNamespace(CLSCTX_ALL=23),'pycaw':types.ModuleType('pycaw'),'pycaw.pycaw':api}),patch('psrtty.windows_volume.sys.platform','win32'),patch('psrtty.audio_devices.resolve_device',return_value=7) as resolve,patch('psrtty.audio_devices.wasapi_endpoint',return_value=('chosen-id',True)):
            obj=WindowsVolume(selection,'output')
        resolve.assert_called_once()
        self.assertEqual(resolve.call_args.args[1],selection)
        api.AudioUtilities.GetDeviceEnumerator.return_value.GetDevice.assert_called_once_with('chosen-id')
        api.AudioUtilities.GetSpeakers.assert_not_called()


class UI117Tests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown

    def test_all_models_offer_external_and_manual_round_trip(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        d=SettingsDialog(self.store,self.window)
        for index in range(d.rig.count()):
            if d.rig.itemData(index):
                d.rig.setCurrentIndex(index)
                self.assertGreaterEqual(d.ptt.findData('外部接続'),0,d.rig.currentText())
        d.rig.setCurrentIndex(d.rig.findData(MANUAL_MODEL))
        self.assertFalse(d.com.isEnabled());self.assertFalse(d.auto_mode.isEnabled())
        d.external_enabled.setChecked(True);d.external_role.setCurrentIndex(d.external_role.findData('ptt'))
        d.external_port.addItem('COM9','COM9');d.external_port.setCurrentIndex(d.external_port.findData('COM9'))
        d._save();self.assertEqual(self.store.data['radio']['model'],MANUAL_MODEL)
        self.assertEqual(self.store.data['radio']['ptt'],'外部接続')

    def test_external_test_release_timeout_and_dialog_close(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        d=SettingsDialog(self.store,self.window)
        d.external_enabled.setChecked(True);d.external_role.setCurrentIndex(1)
        d.external_port.addItem('COM9','COM9');d.external_port.setCurrentIndex(d.external_port.findData('COM9'))
        with patch('psrtty.ui.settings_dialog.ExternalPTT') as factory:
            for stop in (d._stop_external_test, d.external_test_timer.timeout.emit, d.reject):
                d._start_external_test();self.assertIsNotNone(d._external_test)
                stop();self.assertIsNone(d._external_test)
            self.assertEqual(factory.return_value.after_ptt.call_count,3)

    def test_volume_widget_reads_without_writes_and_handles_failure(self):
        from PySide6.QtWidgets import QComboBox
        from psrtty.ui.windows_volume import WindowsVolumeWidget
        combo=QComboBox();combo.addItem('device',{'id':'chosen'})
        with patch('psrtty.ui.windows_volume.WindowsVolume') as factory:
            backend=factory.return_value;backend.read.return_value=VolumeState(20,True)
            widget=WindowsVolumeWidget(combo,'output');self.assertEqual(widget.slider.value(),20)
            backend.set_percent.assert_not_called();backend.set_mute.assert_not_called()
            widget.slider.setValue(30);backend.set_percent.assert_called_once_with(30)
            backend.read.side_effect=OSError('unplugged');widget.refresh()
            self.assertFalse(widget.slider.isEnabled());widget.close()

    def test_delete_button_resets_on_each_open(self):
        from psrtty.ui.qso_log_dialog import QSOLogDialog
        dialog=QSOLogDialog(self.window.adif,self.window)
        self.assertFalse(dialog.delete_all_button.isEnabled())
        dialog.delete_all_enable.setChecked(True);self.assertTrue(dialog.delete_all_button.isEnabled())
        dialog.show();self.assertFalse(dialog.delete_all_enable.isChecked());dialog.close()

    def test_delete_confirmation_requires_consent_and_final_yes(self):
        from PySide6.QtWidgets import QCheckBox, QDialog, QMessageBox
        from psrtty.ui.qso_log_dialog import QSOLogDialog
        from psrtty.adif import QSORecord, ADIFLog
        from psrtty.i18n import tr
        adif=ADIFLog(self.paths['logdata'])
        adif.append(QSORecord('JH1HST'))
        dialog=QSOLogDialog(adif,self.window)
        def confirmation(consent):
            def run(box):
                box.findChild(QCheckBox).setChecked(consent)
                return QDialog.Accepted
            return run
        with patch.object(QDialog,'exec',confirmation(False)),patch.object(QMessageBox,'question') as question:
            dialog.delete_all_enable.setChecked(True);dialog.delete_all();question.assert_not_called()
        for answer in (QMessageBox.No,QMessageBox.Yes):
            with patch.object(QDialog,'exec',confirmation(True)),patch.object(QMessageBox,'question',return_value=answer) as question,patch.object(QMessageBox,'information'):
                dialog.delete_all_enable.setChecked(True);dialog.delete_all()
                self.assertEqual(question.call_args.args[-1],QMessageBox.No)
            self.assertEqual(len(adif.load_recent(limit=None)),1 if answer==QMessageBox.No else 0)
            self.assertFalse(dialog.delete_all_enable.isChecked())
        dialog.close()

    def test_manual_mode_does_not_poll_disconnect_or_reuse_frequency(self):
        w=self.window;w.radio=create_controller(dict(DEFAULT_CONFIG['radio'],model=MANUAL_MODEL,ptt='外部接続'))
        w.radio.connect();w.connecting=False
        with patch('psrtty.ui.main_window.BackgroundJob') as worker:
            w._poll_radio();worker.assert_not_called()
        self.assertTrue(w._manual_tx_allowed())
