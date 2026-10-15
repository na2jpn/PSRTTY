import os
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QComboBox
from psrtty.windows_volume import WindowsVolume, VolumeState, VolumeUnavailable, volume_error
from psrtty.ui.windows_volume import WindowsVolumeWidget
from psrtty.i18n import tr


def output_with_sessions(sessions):
    backend=WindowsVolume.__new__(WindowsVolume)
    backend.kind='output'; backend._interfaces=(object,object); backend._empty_volume=None
    backend.control=Mock()
    enumerator=backend.control.GetSessionEnumerator.return_value
    enumerator.GetCount.return_value=len(sessions)
    enumerator.GetSession.side_effect=lambda i:sessions[i]
    return backend


def session(pid, state, percent=20, mute=False):
    ctl=Mock();ctl.QueryInterface.return_value=ctl
    ctl.GetProcessId.return_value=pid;ctl.GetState.return_value=state
    ctl.GetMasterVolume.return_value=percent/100;ctl.GetMute.return_value=mute
    return ctl


class VolumeFix2Tests(unittest.TestCase):
    def test_before_first_tx_uses_empty_current_process_session_no_stream_or_writes(self):
        backend=output_with_sessions([])
        volume=backend.control.GetSimpleAudioVolume.return_value
        volume.GetMasterVolume.return_value=.2;volume.GetMute.return_value=True
        with patch('psrtty.audio_engine.sd') as audio_api:
            self.assertEqual(backend.read(),VolumeState(20,True))
            self.assertEqual(backend.read(),VolumeState(20,True))
            audio_api.OutputStream.assert_not_called()
        backend.control.GetSimpleAudioVolume.assert_called_once_with(None,0)
        volume.SetMasterVolume.assert_not_called();volume.SetMute.assert_not_called()

    def test_other_apps_are_untouched_and_our_active_session_takes_over(self):
        other=session(os.getpid()+1,1,88)
        backend=output_with_sessions([other])
        empty=backend.control.GetSimpleAudioVolume.return_value
        empty.GetMasterVolume.return_value=.2;empty.GetMute.return_value=False
        self.assertEqual(backend.read().percent,20)
        backend.set_percent(35);empty.SetMasterVolume.assert_called_once_with(.35,None)
        other.SetMasterVolume.assert_not_called();other.SetMute.assert_not_called()
        ours=session(os.getpid(),1,35)
        enumerator=backend.control.GetSessionEnumerator.return_value
        enumerator.GetCount.return_value=1;enumerator.GetSession.side_effect=lambda i:ours
        self.assertEqual(backend.read().percent,35)
        backend.set_mute(False);ours.SetMute.assert_called_once_with(False,None)

    def test_mismatched_sessions_do_not_fall_back_or_modify(self):
        a,b=session(os.getpid(),1,20),session(os.getpid(),0,30)
        backend=output_with_sessions([a,b])
        with self.assertRaises(VolumeUnavailable) as caught:backend.read()
        self.assertEqual(caught.exception.reason,'mixed')
        backend.control.GetSimpleAudioVolume.assert_not_called()
        a.SetMasterVolume.assert_not_called();b.SetMasterVolume.assert_not_called()

    def test_empty_session_failure_and_hresult_classification(self):
        backend=output_with_sessions([])
        backend.control.GetSimpleAudioVolume.side_effect=OSError('not initialized')
        with self.assertRaises(VolumeUnavailable) as caught:backend.read()
        self.assertEqual(caught.exception.reason,'not_ready')
        for code,reason in [(0x88890001,'not_ready'),(0x88890004,'device'),(0x88890010,'service')]:
            error=RuntimeError('COM');error.hresult=code-2**32
            self.assertEqual(volume_error(error).reason,reason)
        self.assertEqual(volume_error(OSError('failure'),'write').reason,'write')


class VolumeUIFix2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_reason_changes_and_clears_after_recovery_without_volume_writes(self):
        combo=QComboBox();combo.addItem('chosen',{'id':'chosen'})
        with patch('psrtty.ui.windows_volume.WindowsVolume') as factory:
            backend=factory.return_value
            backend.read.side_effect=VolumeUnavailable('device')
            widget=WindowsVolumeWidget(combo,'output');self.addCleanup(widget.close)
            self.assertEqual(widget.reason.text(),tr('v117fix2.device'))
            self.assertEqual(widget.meter.format(),tr('v117.unavailable'))
            self.assertFalse(widget.slider.isEnabled())
            backend.read.side_effect=VolumeUnavailable('service');widget.refresh()
            self.assertEqual(widget.reason.text(),tr('v117fix2.service'))
            backend.read.side_effect=None;backend.read.return_value=VolumeState(0,False);widget.refresh()
            self.assertEqual(widget.reason.text(),'');self.assertTrue(widget.slider.isEnabled())
            self.assertIn('0%',widget.label.text())
            backend.set_percent.assert_not_called();backend.set_mute.assert_not_called()

    def test_write_failure_is_visible_not_silently_refreshed_away(self):
        combo=QComboBox();combo.addItem('chosen',{'id':'chosen'})
        with patch('psrtty.ui.windows_volume.WindowsVolume') as factory:
            backend=factory.return_value;backend.read.return_value=VolumeState(20,False)
            widget=WindowsVolumeWidget(combo,'input');self.addCleanup(widget.close)
            backend.set_percent.side_effect=OSError('denied')
            widget.slider.setValue(30)
            self.assertEqual(widget.reason.text(),tr('v117fix2.write'))
            self.assertFalse(widget.slider.isEnabled())

    def test_no_test_transmission_instruction_in_any_language(self):
        from psrtty.i18n import LANGUAGES,load_catalog
        for code in LANGUAGES:
            strings,issues=load_catalog(code)
            self.assertFalse(issues,code)
            for reason in ('platform','dependency','selection','device','not_ready','service','mixed','read','write'):
                self.assertTrue(strings['v117fix2.'+reason])
            self.assertNotIn('perform a test transmission',strings['v117.session_note'])

    def test_periodic_reads_only_run_while_visible(self):
        combo=QComboBox();combo.addItem('chosen',{'id':'chosen'})
        with patch('psrtty.ui.windows_volume.WindowsVolume') as factory:
            factory.return_value.read.return_value=VolumeState(20,False)
            widget=WindowsVolumeWidget(combo,'output');self.addCleanup(widget.close)
            self.assertFalse(widget.timer.isActive())
            widget.show();self.app.processEvents();self.assertTrue(widget.timer.isActive())
            widget.hide();self.assertFalse(widget.timer.isActive());self.assertIsNone(widget.backend)
