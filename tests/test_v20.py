from psrtty.timebase import JST
import copy
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF, QLockFile
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QGroupBox, QDialog, QMessageBox
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.adif import ADIFLog, QSORecord, _field, record_spans
from psrtty.ui.qso_log_dialog import QSOLogDialog, QSOEditDialog
from psrtty.ui.formatting import frequency_text, band_text
from psrtty.single_instance import ActivationServer, request_activation, endpoint
from psrtty.audio_engine import AudioEngine
from psrtty.config import ConfigStore


class ADIF20Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.log=ADIFLog(self.root)
    def tearDown(self): self.tmp.cleanup()
    def record(self,call='JH1HST'):
        return QSORecord(call=call,freq_hz=21090700,when_utc=datetime(2026,9,24,8,45,30,tzinfo=timezone.utc),sent='001',rcvd='25')
    def test_edit_one_of_over_200_preserves_unknown_fields_and_backup_bytes(self):
        for _ in range(205): path=self.log.append(self.record())
        raw=path.read_bytes(); raw=b'\xef\xbb\xbf'+raw.replace(b'<EOR>',(_field('COMMENT','日本語 <EOR> <CALL:3>ABC')+' <EOR>').encode(),1)
        path.write_bytes(raw)
        records=self.log.load_recent(limit=None); self.assertEqual(len(records),205)
        first=records[0]; new=replace(first,call='JQ7FIU',sent='ABC',rcvd='',freq_hz=14080123)
        backup=self.log.modify(first,new)
        self.assertEqual(backup.read_bytes(),raw)
        result=path.read_bytes(); self.assertTrue(result.startswith(b'\xef\xbb\xbf'))
        self.assertIn('日本語 <EOR> <CALL:3>ABC'.encode(),result)
        allq=self.log.load_recent(limit=None); self.assertEqual(len(allq),205)
        self.assertEqual((allq[0].call,allq[0].band,allq[0].sent,allq[0].rcvd),('JQ7FIU','20m','ABC',''))
        self.assertTrue(all(q.call=='JH1HST' for q in allq[1:]))
        first_chunk=record_spans(result.decode('utf-8-sig'))[0][2]
        fields={n:v for _,_,n,v in first_chunk}; self.assertNotIn('STX',fields); self.assertNotIn('SRX',fields)
    def test_delete_exact_duplicate_only_and_stale_edit_rejected(self):
        self.log.append(self.record()); path=self.log.append(self.record())
        a,b=self.log.load_recent(limit=None); original=path.read_bytes()
        self.log.modify(b,None); self.assertEqual(len(self.log.load_recent(limit=None)),1)
        with self.assertRaisesRegex(RuntimeError,'変更'): self.log.modify(a,None)
        self.assertEqual(len(list((self.root/'backups').glob('*.bak'))),1)
        self.assertEqual(next((self.root/'backups').glob('*.bak')).read_bytes(),original)
    def test_failed_replace_preserves_original_and_backup(self):
        path=self.log.append(self.record()); raw=path.read_bytes(); q=self.log.load_recent()[0]
        with patch('psrtty.adif.os.replace',side_effect=OSError('disk')):
            with self.assertRaises(OSError): self.log.modify(q,None)
        self.assertEqual(path.read_bytes(),raw)
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.assertEqual(next((self.root/'backups').glob('*')).read_bytes(),raw)
    def test_multiple_days_and_edit_date_not_moving_or_dropping_records(self):
        self.log.append(self.record('JH1HST'),datetime(2026,9,23))
        self.log.append(self.record('JQ7FIU'),datetime(2026,9,24))
        records=self.log.load_recent(limit=None); self.assertEqual(len(records),2)
        newdate=datetime(2026,8,1,1,2,3,tzinfo=timezone.utc)
        self.log.modify(records[1],replace(records[1],when_utc=newdate))
        updated=self.log.load_recent(limit=None)
        self.assertEqual(updated[0].when_utc,newdate); self.assertEqual(len(updated),2)
    def test_foreign_path_and_incomplete_adif_rejected(self):
        q=self.record(); q.source_path=str(self.root.parent/'elsewhere.adi')
        with self.assertRaises(ValueError): self.log.modify(q,None)
        with self.assertRaises(ValueError): record_spans('<CALL:100>SHORT')
    def test_unreadable_old_file_does_not_hide_good_logs_or_get_rewritten(self):
        self.log.append(self.record()); bad=self.root/'20000101.adi'; bad.write_bytes(b'<CALL:999>broken')
        self.assertEqual(len(self.log.load_recent(limit=None)),1)
        self.assertIn('20000101.adi',self.log.read_errors[0])
        self.assertEqual(bad.read_bytes(),b'<CALL:999>broken')

    def test_frequency_and_band_display(self):
        self.assertEqual(frequency_text(21090700),'21.090.700 MHz')
        self.assertEqual(frequency_text(10235000000),'10235.000.000 MHz')
        self.assertEqual(band_text(self.record()),'15m / 21MHz')
        self.assertEqual(replace(self.record(),freq_hz=10235000000).band,'3cm')


class UI20Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp; tearDown=_Fixture.tearDown; pump=_Fixture.pump
    def test_shift_reset_click_persist_and_tx_tones_preserved(self):
        w=self.window; before=copy.deepcopy(self.store.data['advanced'])
        w._spectrum_click(1900); w.shift_edit.setText('250'); w._shift_changed()
        self.assertEqual((w.spectrum.mark_hz,w.spectrum.space_hz),(1900,2150))
        w._reset_position(); self.assertEqual((w.spectrum.mark_hz,w.spectrum.space_hz),(2125,2375))
        w._reset_170(); self.assertEqual((w.spectrum.mark_hz,w.spectrum.space_hz),(2125,2295))
        w.shift_edit.setText('nan'); w._shift_changed(); self.assertEqual(w.shift_edit.text(),'170')
        w.shift_edit.setText('999999'); w._shift_changed(); self.assertEqual(w.shift_edit.text(),'170')
        self.assertEqual(self.store.data['advanced'],before)
        self.assertEqual(self.store.data['ui']['rx_tones'],[2125,2295])
        w._set_tones(2300,2100); w._spectrum_click(2200)
        self.assertEqual((w.spectrum.mark_hz,w.spectrum.space_hz),(2200,2000))
    def test_drag_either_line_preserves_spacing_without_initial_jump(self):
        w=self.window; w.show(); self.pump(.03); spec=w.spectrum
        for which in ('mark_hz','space_hz'):
            w._set_tones(2125,2295); self.store.save.reset_mock()
            x=round(spec._x(getattr(spec,which))); width=spec.width()
            QTest.mousePress(spec,Qt.LeftButton,pos=QPoint(x,40))
            self.assertEqual(spec.mark_hz,2125)
            QTest.mouseMove(spec,QPoint(x+40,40))
            self.assertAlmostEqual(spec.mark_hz,2125+40/width*1000)
            self.assertAlmostEqual(spec.space_hz-spec.mark_hz,170)
            self.store.save.assert_not_called()
            QTest.mouseRelease(spec,Qt.LeftButton,pos=QPoint(x+40,40)); self.store.save.assert_called_once()
    def test_autotune_uses_current_shift_and_updates_width(self):
        w=self.window; w._set_tones(2000,2250)
        freq=np.arange(1500,2700,10); power=np.full(freq.shape,-100.)
        power[freq==2020]=-5; power[freq==2280]=-6
        w.last_spectrum=(freq,power); w._auto_tune()
        self.assertEqual((w.spectrum.mark_hz,w.spectrum.space_hz),(2020,2280))
        self.assertEqual(w.shift_edit.text(),'260')
    def test_display_gain_does_not_change_decoder_or_audio_gain(self):
        w=self.window; spec=w.spectrum
        with patch.object(w.audio,'configure_decoder') as decoder,patch.object(w.audio,'set_rx_gain') as gain:
            w.spectrum_gain.setValue(20); self.assertEqual(spec.gain_db,20)
            decoder.assert_not_called(); gain.assert_not_called()
        f=np.array([2000,2100]); spec.set_data(f,np.array([-50.,-60.]))
        spec.set_data(f,np.array([-30.,-40.])); np.testing.assert_allclose(spec.power,[-43,-53])
    def test_log_dialog_edits_deletes_and_refreshes_main(self):
        w=self.window; log=ADIFLog(self.paths['logdata']); w.adif=log
        q=QSORecord('JH1HST',freq_hz=21090700,when_utc=datetime(2026,9,24,8,45,tzinfo=timezone.utc)); log.append(q)
        d=QSOLogDialog(log,w); d.changed.connect(w._reload_qsos)
        self.assertEqual(d.table.item(0,2).text(),'15m / 21MHz'); self.assertTrue(d.table.item(0,0).text())
        self.assertFalse(d.delete_button.isEnabled()); d.table.selectRow(0)
        original=d.selected(); self.assertTrue(d.apply_change(original,replace(original,call='JQ7FIU')))
        self.assertEqual(w.qsos[0].call,'JQ7FIU'); self.assertEqual(w.latest_table.item(0,2).text(),'JQ7FIU')
        d.table.selectRow(0)
        with patch('psrtty.ui.qso_log_dialog.QMessageBox.question',return_value=QMessageBox.No): d.delete_selected()
        self.assertEqual(len(log.load_recent()),1)
        with patch('psrtty.ui.qso_log_dialog.QMessageBox.question',return_value=QMessageBox.Yes): d.delete_selected()
        self.assertEqual(w.qsos,[]); self.assertEqual(d.table.rowCount(),0); d.close()
    def test_edit_validates_date_frequency_and_converts_jst_to_utc(self):
        q=QSORecord('JH1HST',freq_hz=21090700,when_utc=datetime.now(timezone.utc))
        d=QSOEditDialog(q); d.fields['when'].setText('2026-02-30 12:00')
        with patch('psrtty.ui.qso_log_dialog.QMessageBox.warning'):
            d.save(); self.assertIsNone(d.result_record)
        d.fields['when'].setText('2026-09-24 17:45'); d.fields['freq'].setText('10235.000001'); d.save()
        self.assertEqual(d.result_record.freq_hz,10235000001)
        self.assertEqual(d.result_record.when_utc,datetime(2026,9,24,17,45,tzinfo=JST).astimezone(timezone.utc))
    def test_control_wheel_reverse_and_circular_wrap(self):
        w=self.window; w._show_control(); d=w.control_window; d.timer.stop(); d.dial.setEnabled(True)
        output=[]; d.dial.steps.connect(output.append)
        def wheel(y):
            d.dial.wheelEvent(QWheelEvent(QPointF(86,36),QPointF(86,36),QPoint(),QPoint(0,y),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False))
        wheel(-120); wheel(120); self.assertEqual(output,[1,-1])
        d.reverse.setChecked(True); wheel(120); self.assertEqual(output,[1,-1,1]); self.assertTrue(self.store.data['ui']['wheel_reverse'])
        self.assertEqual([d.step.itemData(i) for i in range(d.step.count())],[1,10,100,1000,10000])
        self.assertTrue(any(g.title()=='NOTCH' for g in d.findChildren(QGroupBox)))
        output.clear()
        QTest.mousePress(d.dial,Qt.LeftButton,pos=QPoint(90,136))
        QTest.mouseMove(d.dial,QPoint(82,136)); QTest.mouseMove(d.dial,QPoint(60,130))
        QTest.mouseRelease(d.dial,Qt.LeftButton,pos=QPoint(60,130))
        self.assertTrue(output); self.assertTrue(all(0<n<4 for n in output))
    def test_guide_tabs_readable_and_reused(self):
        w=self.window; w._guide_initial(); guide=w.help_windows['初期設定ガイド']
        self.assertEqual(guide.tabs.count(),7); self.assertIn('Cabrillo出力', [guide.tabs.tabText(i) for i in range(guide.tabs.count())]); self.assertGreaterEqual(guide.tabs.widget(0).font().pointSize(),11)
        self.assertIn('表示感度',guide.tabs.widget(2).toPlainText())
        w._guide_initial(); self.assertIs(guide,w.help_windows['初期設定ガイド'])
    def test_activation_message_restores_window_and_acknowledges(self):
        w=self.window; w.showMinimized(); server=ActivationServer(self.paths['root'],w)
        client=Mock(); client.canReadLine.return_value=True; client.readLine.return_value=b'ACTIVATE\n'
        server.receive(client)
        self.assertFalse(w.isMinimized()); client.write.assert_called_once_with(b'OK\n')
        client.disconnectFromServer.assert_called_once(); server.server.close()

    def test_activation_ipc_and_lock_are_per_installation(self):
        w=self.window; root=self.paths['root']; lock=QLockFile(str(root/'var'/'psrtty.lock'))
        other=QLockFile(str(root/'var'/'psrtty.lock')); server=None; worker=None
        try:
            self.assertTrue(lock.tryLock(0)); self.assertFalse(other.tryLock(0))
            server=ActivationServer(root,w)
            if not server.listening:
                self.skipTest('この環境ではOSがローカルソケット作成を拒否します。Windows実機確認対象。')
            w.showMinimized()
            script=("import sys; from pathlib import Path; "
                    "from PySide6.QtCore import QCoreApplication; "
                    "from psrtty.single_instance import request_activation; "
                    "app=QCoreApplication([]); sys.exit(0 if request_activation(Path(sys.argv[1])) else 1)")
            worker=subprocess.Popen([sys.executable,'-c',script,str(root)],
                cwd=str(Path(__file__).resolve().parents[1]),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            deadline=time.monotonic()+8
            # Keep the GUI dispatching until the real second process exits.
            # Never join/wait on it while the GUI must deliver its reply.
            while worker.poll() is None and time.monotonic()<deadline: self.pump(.02)
            self.assertIsNotNone(worker.poll(),'呼び戻し用の子プロセスが終了しませんでした')
            stdout,stderr=worker.communicate(timeout=1)
            self.assertEqual(worker.returncode,0,(stdout+stderr).decode(errors='replace'))
            self.assertFalse(w.isMinimized())
            self.assertNotEqual(endpoint(root),endpoint(root/'other'))
        finally:
            if worker is not None:
                if worker.poll() is None: worker.kill()
                worker.communicate(timeout=3)
            if server is not None:
                for client in list(server.clients): client.abort()
                server.server.close()
            other.unlock(); lock.unlock()
        # Verify cleanup before TemporaryDirectory's Windows deletion runs.
        self.assertFalse((root/'var'/'psrtty.lock').exists())


del _Fixture

class FFT20Tests(unittest.TestCase):
    def test_fixed_fft_scale_tracks_input_amplitude(self):
        spectra=[]; engine=AudioEngine(on_spectrum=lambda f,p:spectra.append(p))
        n=np.arange(4096); signal=np.sin(2*np.pi*187.5*n/48000).astype(np.float32)
        engine._input_callback((signal*.1)[:,None],4096,None,None)
        engine._last_fft=0
        engine._input_callback((signal*.01)[:,None],4096,None,None)
        self.assertEqual(len(spectra),2)
        self.assertAlmostEqual(float(max(spectra[0])-max(spectra[1])),20,places=2)


class ActivationReply20Tests(unittest.TestCase):
    def client(self, chunks):
        from PySide6.QtNetwork import QLocalSocket
        client=Mock(); client.waitForConnected.return_value=True
        client.state.return_value=QLocalSocket.ConnectedState
        client.readAll.side_effect=chunks
        return client

    def test_already_buffered_reply_does_not_wait_again(self):
        client=self.client([b'OK\n'])
        with patch('psrtty.single_instance.QLocalSocket',return_value=client):
            self.assertTrue(request_activation(Path('.')))
        client.waitForReadyRead.assert_not_called(); client.abort.assert_called_once()

    def test_fragmented_reply_is_collected(self):
        client=self.client([b'O',b'K',b'\n'])
        with patch('psrtty.single_instance.QLocalSocket',return_value=client):
            self.assertTrue(request_activation(Path('.')))
        self.assertEqual(client.waitForReadyRead.call_count,2); client.abort.assert_called_once()

    def test_connection_failure_always_releases_client(self):
        client=self.client([]); client.waitForConnected.return_value=False
        with patch('psrtty.single_instance.QLocalSocket',return_value=client):
            self.assertFalse(request_activation(Path('.')))
        client.abort.assert_called_once()
