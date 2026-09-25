from psrtty.timebase import JST
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
import numpy as np
from PySide6.QtWidgets import QLabel, QMenu
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.civ import CIVController
from psrtty.yaesu import YaesuController
from psrtty.audio_engine import AudioEngine
from psrtty.adif import QSORecord
from psrtty.ui.main_window import ReceiveCard

class Protocol30Tests(unittest.TestCase):
    def test_icom_filter_preserves_mode_data_and_reads_actual(self):
        c=CIVController(0x94); c.ser=Mock(); c.status.connected=True
        def reply(f): return bytes([254,254,224,148,38,0,0,1,f,253])
        with patch.object(c,'_read_response',return_value=reply(1)):
            state=c.read_filter(); self.assertEqual(state['mode'],(0,1))
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'_read_response',side_effect=[reply(1),bytes.fromhex('FE FE E0 94 FB FD'),reply(3)]):
            self.assertTrue(c.set_filter(3,state))
        self.assertIn(bytes.fromhex('FE FE 94 E0 26 00 00 01 03 FD'),[call.args[0] for call in c.ser.write.call_args_list])
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_filter',return_value=dict(state,mode=(1,1))):
            c.ser.reset_mock(); self.assertFalse(c.set_filter(2,state)); c.ser.write.assert_not_called()
        with patch.object(c,'read_transmitting',return_value=None):
            c.ser.reset_mock(); self.assertFalse(c.set_filter(2,state)); c.ser.write.assert_not_called()
        with patch.object(c,'_read_response',return_value=b''):
            self.assertIsNone(c.read_filter())
    def test_icom_rejected_ack_and_failed_readback_are_not_success(self):
        c=CIVController(0x94);c.ser=Mock();c.status.connected=True
        state=dict(kind='ICOM',mode=(0,1),value=1,options=[(1,'FIL1'),(2,'FIL2')],narrow=None)
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_filter',return_value=state),patch.object(c,'_read_response',return_value=bytes.fromhex('FE FE E0 94 FA FD')):
            self.assertFalse(c.set_filter(2,state))
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_filter',return_value=state),patch.object(c,'_read_response',return_value=bytes.fromhex('FE FE E0 94 FB FD')):
            self.assertFalse(c.set_filter(2,state)) # ACK alone is not readback

    def test_cat_distinct_width_formats_readback_and_narrow(self):
        for model in ('FT-991 / FT-991A','FTX-1'):
            c=YaesuController(model); c.ser=Mock(); c.status.connected=True
            prefix='SH00' if model=='FTX-1' else 'SH0'
            values={'mode':'8','width':12,'narrow':0}
            def query(cmd,pre,**kw):
                return {'MD0;':'MD0'+values['mode']+';','NA0;':f"NA0{values['narrow']};",'SH0;':f"{prefix}{values['width']:02d};"}[cmd]
            def write(cmd):
                cmd=cmd.decode()
                if cmd.startswith(prefix): values['width']=int(cmd[len(prefix):-1])
                elif cmd.startswith('NA0'): values['narrow']=int(cmd[3:-1])
            c.ser.write.side_effect=write
            with patch.object(c,'_query',side_effect=query),patch.object(c,'read_transmitting',return_value=False):
                state=c.read_filter(); self.assertEqual(state['value'],12)
                self.assertTrue(c.set_filter(10,state)); c.ser.write.assert_called_with((prefix+'10;').encode())
                self.assertTrue(c.set_narrow(True,state)); self.assertTrue(c.read_filter()['narrow'])
                self.assertFalse(c.set_filter(10,state)) # stale NARROW
                state=c.read_filter(); values['mode']='2'
                self.assertFalse(c.set_filter(10,state)) # stale mode
            with patch.object(c,'read_transmitting',return_value=True):
                c.ser.reset_mock(); self.assertFalse(c.set_filter(10,state)); self.assertFalse(c.set_narrow(False,state)); c.ser.write.assert_not_called()
    def test_cat_width_candidates_follow_model_mode_and_narrow(self):
        c=YaesuController('FT-991 / FT-991A')
        self.assertEqual(dict(c._filter_options('8',False))[12],'1200 Hz')
        self.assertEqual(dict(c._filter_options('8',True))[6],'300 Hz')
        self.assertNotIn(12,dict(c._filter_options('8',True)))
        c=YaesuController('FTX-1')
        self.assertEqual(dict(c._filter_options('8',False))[12],'800 Hz')
        self.assertEqual(c._filter_options('B',True),[])
    def test_audio_pause_skips_decoder_but_keeps_meter_and_fft(self):
        meter=Mock(); spectrum=Mock(); e=AudioEngine(on_level=meter,on_spectrum=spectrum)
        with patch.object(e.decoder,'feed') as feed,patch.object(e.decoder,'reset') as reset:
            e.set_decode_enabled(False); generation=e.decode_generation
            e._input_callback(np.ones((4096,1),dtype=np.float32)*.01,4096,None,None)
            feed.assert_not_called(); meter.assert_called_once(); spectrum.assert_called_once(); reset.assert_called_once()
            e.set_decode_enabled(True); self.assertGreater(e.decode_generation,generation)
            e._input_callback(np.zeros((960,1),dtype=np.float32),960,None,None); feed.assert_called_once()

class UI30Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp; tearDown=_Fixture.tearDown; pump=_Fixture.pump
    def test_decode_pause_discards_queued_old_characters_keeps_cards_tx(self):
        w=self.window; old=w.audio.decode_generation
        w._add_card('OLD','RX'); w._rx_char('A')
        w.decode_enabled.setChecked(False)
        w._rx_char((old,'B')); w._finalize_rx_card()
        self.assertEqual(w.rx_buffer,''); self.assertEqual(w.cards_layout.count(),1)
        w._add_card('TEST','TX'); self.assertEqual(w.cards_layout.count(),2)
        w.decode_enabled.setChecked(True); w._rx_char((old,'C')); self.assertEqual(w.rx_buffer,'')
        w._rx_char((w.audio.decode_generation,'D')); w._finalize_rx_card()
        self.assertEqual(w.cards_layout.count(),3); self.assertEqual(w.cards_layout.itemAt(2).widget().text_value,'D')
    def test_three_consecutive_failures_and_recovery_reset(self):
        w=self.window; w.current_freq_hz=21090000
        with patch.object(w,'disconnect_radio') as disconnect:
            w._radio_observed(None); w._radio_observed(None); disconnect.assert_not_called()
            w._radio_observed(21090010); self.assertEqual(w.poll_failures,0)
            for _ in range(3): w._radio_observed(None)
            disconnect.assert_called_once()
            self.assertIn('3回連続',w.statusBar().currentMessage()); self.assertIn('3回連続',w.rig_status.toolTip())
    def test_stale_poll_does_not_affect_new_connection(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True
        completions=[]
        with patch('psrtty.ui.main_window.BackgroundJob',side_effect=lambda parent,work,done:completions.append(done)):
            w._poll_radio()
        w.connection_generation+=1
        completions[0](None,None)
        self.assertEqual(w.poll_failures,0)

    def test_separate_date_time_and_partial_rejected(self):
        w=self.window;w.q_call.setText('JH1HST');w.q_datetime.setText('2026-09-24 ')
        with patch('psrtty.ui.main_window.QMessageBox.warning') as warning:
            w._add_qso(); warning.assert_called_once();w.adif.append.assert_not_called()
        w.q_time.setText('17:14');w._add_qso()
        self.assertFalse(w.q_datetime.manual.isChecked()); self.assertTrue(w.q_datetime.text())
        q=w.adif.append.call_args.args[0]
        self.assertEqual(q.when_utc.astimezone(JST).strftime('%Y-%m-%d %H:%M'),'2026-09-24 17:14')
    def test_latest_two_columns_order_and_narrow_fallback(self):
        w=self.window;w.store.data['ui']['latest_qso_count']=6
        w.qsos=[QSORecord(call=f'JH{i}HST',when_utc=datetime.now(timezone.utc)) for i in range(6)]
        w.latest_panel.resize(1200,100);w._refresh_latest_qsos()
        self.assertFalse(w.latest_right.isHidden());self.assertEqual(w.latest_table.rowCount(),3)
        self.assertEqual([t.item(r,2).text() for r in (0,1) for t in (w.latest_table,w.latest_right)],['JH5HST','JH4HST','JH3HST','JH2HST'])
        self.assertLessEqual(w.latest_table.horizontalHeader().length(),w.latest_table.width())
        w.latest_panel.resize(450,100);w._refresh_latest_qsos();self.assertEqual(w.latest_table.columnCount(),7);self.assertEqual(w.latest_table.rowCount(),6)
    def test_compact_cards_plain_text_and_menu(self):
        card=ReceiveCard('21:18:24','<b>literal</b>','RX');card.resize(700,35)
        labels=card.findChildren(QLabel)
        self.assertEqual([x.text() for x in labels],['21:18:24','RX','|','<b>literal</b>'])
        self.assertEqual(labels[1].objectName(),'cardRX'); card.deleteLater()
        w=self.window
        actions=[a.text() for menu in w.menuBar().findChildren(QMenu) for a in menu.actions()]
        self.assertNotIn('FT8環境からの設定方法',actions)
    def test_filter_ui_tracks_actual_and_switches_manufacturer(self):
        w=self.window;w._show_control();d=w.control_window;d.timer.stop()
        d.states['FILTER']=dict(kind='ICOM',mode=(0,1),value=2,options=[(i,f'FIL{i}') for i in (1,2,3)],narrow=None)
        d.refresh_filter(True);self.assertTrue(d.filter_buttons[1].isChecked())
        d.band_profile='FTX-1'; d.states['FILTER']=dict(kind='YAESU',mode='8',value=10,options=[(10,'500 Hz'),(12,'800 Hz')],narrow=True)
        d.refresh_filter(True);self.assertEqual(d.width.currentText(),'500 Hz');self.assertTrue(d.narrow.isChecked())
        d.refresh_filter(False);self.assertFalse(d.width.isEnabled());self.assertFalse(d.narrow.isChecked())

del _Fixture
