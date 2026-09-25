import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, Mock
import numpy as np
from psrtty.adif import ADIFLog, QSORecord
from psrtty.decoder import RTTYDecoder
from psrtty.rtty_codec import encode_text_audio
from tests.test_ui_v02 import UITests as _Fixture

class Decoder70Tests(unittest.TestCase):
    def test_low_sq_passes_decodable_signal_with_out_of_band_energy(self):
        text='CQ DE JH1HST 599 TU 73'
        audio=encode_text_audio(text)
        audio=audio+1.3*np.sin(2*np.pi*8000*np.arange(len(audio))/48000)
        def decode(level):
            out=[];d=RTTYDecoder(on_char=out.append);d.sq_level=level
            for i in range(0,len(audio),997):d.feed(audio[i:i+997])
            return ''.join(out)
        for level in (0,1,2):self.assertEqual(decode(level),text+'\r\n')
        self.assertEqual(decode(6),'') # approximately the previous default threshold

class UI70Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def connected(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True
        w.current_freq_hz=21168490;w.auto_log.setChecked(True);w.auto_get.setChecked(True)
        w.q_call.setText('JQ7FIU');w.rcvd.setText('11');w.qsos=[]
        w.adif.append.return_value=Path('test.adi')
        return w

    def test_auto_log_survives_rx_during_tx_and_rejects_queued_rx(self):
        w=self.connected()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w.rx_buffer='JQ7FIU 459 99'
            w._send_macro(3);token=w.active_tx_id
            generation=w.audio.decode_generation
            for c in 'JQ7FIU 459 99\r':w._rx_char((generation,c))
            w._consider_auto_extract('JQ7FIU 459 99')
            self.assertEqual(w.rcvd.text(),'11');self.assertEqual(w.rst_r.text(),'599')
            w._tx_finished(True,'OK',token)
            for c in 'JQ7FIU 459 99\r':w._rx_char((generation,c))
            w._tx_finished(True,'OK',token)
        w.adif.append.assert_called_once()
        self.assertEqual(w.adif.append.call_args.args[0].rcvd,'11')
        self.assertEqual(w.q_call.text(),'');self.assertEqual(w.rx_buffer,'')
        self.assertEqual(w.latest_box.footer.text(),'ログ合計 1件')

    def test_manual_edit_is_explained_and_legacy_flag_not_required(self):
        w=self.connected()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w._send_macro(3);w.rcvd.setText('22');w._tx_finished(True,'OK',w.active_tx_id)
            w.adif.append.assert_not_called()
            self.assertIn('編集',w.statusBar().currentMessage())
            self.assertEqual(w.q_call.text(),'JQ7FIU')
            w.store.macros[3]['completes_qso']=False
            w._send_macro(3)
            w._tx_finished(True,'OK',w.active_tx_id)
            w.adif.append.assert_called_once()

    def test_record_number_and_total_across_days_reload_delete(self):
        w=self.window
        with patch('psrtty.adif.ensure_runtime_dirs',return_value=self.paths):log=ADIFLog()
        first=datetime(2026,9,24,tzinfo=timezone.utc);second=datetime(2026,9,25,tzinfo=timezone.utc)
        for i in range(205):
            # Deliberately backdate the final entry: record order must win.
            log.append(QSORecord(call=f'TEST{i}',when_utc=first if i==204 else second),now_local=first if i<200 else second)
        w.adif=log;w._reload_qsos();w.latest_panel.resize(1200,100);w._refresh_latest_qsos()
        self.assertEqual(len(w.qsos),205)
        self.assertEqual(w.latest_box.footer.text(),'ログ合計 205件')
        self.assertEqual([t.item(r,0).text() for r in (0,1) for t in (w.latest_table,w.latest_right)],['205','204','203','202'])
        self.assertEqual(w.latest_table.item(0,2).text(),'TEST204')
        log.modify(w.qsos[-1],None);w._reload_qsos()
        self.assertEqual(w.latest_box.footer.text(),'ログ合計 204件')
        self.assertEqual(w.latest_table.item(0,2).text(),'TEST203')
        w.latest_panel.resize(400,100);w._refresh_latest_qsos()
        self.assertTrue(w.latest_right.isHidden());self.assertEqual(w.latest_table.item(1,0).text(),'203')
        w.show();self.pump(.04)
        for width in (850,1200):
            w.resize(width,850);self.pump(.03)
            self.assertTrue(w.latest_box.rect().contains(w.latest_box.footer.geometry()))
            self.assertGreater(w.latest_box.footer.y(),w.latest_panel.geometry().bottom())

del _Fixture
