"""Real input-rate, sample accounting, tuning and template regressions."""
import io
import json
from pathlib import Path
import struct
import time
import unittest
from unittest.mock import Mock,patch
import numpy as np
from scipy.signal import lfilter
from psrtty import i18n
from psrtty.ry_skimmer import FIRDecimator,SkimmerWorker,SkimmerEngine
from psrtty.ry_iq import ExtIOInput,pe_bits
from psrtty.macros import (jarl_contest_one_template,jarl_ww_template,TEMPLATES,
    TEMPLATE_NAME,JARL_ONE_NAME,LEGACY_JARL_NAME)
from tests.test_ui_v02 import UITests as _Fixture

ROOT=Path(__file__).resolve().parents[1]

class Stream130Tests(unittest.TestCase):
    def test_fft_and_small_block_filter_paths_have_same_phase_and_history(self):
        rng=np.random.default_rng(130)
        x=(rng.normal(size=65333)+1j*rng.normal(size=65333)).astype(np.complex64)
        for factor in (16,20,40):
            d=FIRDecimator(factor);ends=[0,512,4511,17655,18001,65000,len(x)]
            out=np.concatenate([d.feed(x[a:b]) for a,b in zip(ends,ends[1:])])
            np.testing.assert_allclose(out,lfilter(d.taps,[1],x)[::factor],atol=4e-7)

    def test_buffer_is_duration_bounded_not_eight_packets(self):
        for rate in (48000,1920000):
            w=SkimmerWorker(buffer_seconds=.05)
            for _ in range(10):w.offer(np.zeros(32),rate,14090000)
            self.assertEqual(w.dropped,0)
            while w.queued_seconds+512/rate<=.05:w.offer(np.zeros(512),rate,14090000)
            before=w.queued_seconds;w.offer(np.zeros(512),rate,14090000)
            self.assertEqual(w.lost_samples,512);self.assertEqual(w.queued_seconds,before)
            while not w.queue.empty():w._take(0)
            w.offer(np.zeros(512),rate,14090000);self.assertTrue(w._take(0)[3])

    def test_upstream_sample_gaps_and_local_overflow_count_separately(self):
        w=SkimmerWorker(buffer_seconds=.01)
        w.offer(np.zeros(480),48000,14090000,960)
        w.offer(np.zeros(480),48000,14090000)
        stats=w.snapshot()
        self.assertEqual(stats['lost_samples'],1440);self.assertEqual(stats['received'],960)
        self.assertAlmostEqual(stats['loss_percent'],75.)
        self.assertEqual(stats['queue_ms'],10.)

    def test_batches_preserve_center_and_gap_boundaries(self):
        w=SkimmerWorker(batch_seconds=.05);got=[]
        w.engine.feed=lambda data,rate,center,gap:got.append((len(data),center,gap))
        for n,c,g in [(512,14090000,False),(512,14090000,False),(512,14090000,True),(512,21090000,False)]:w.offer(np.zeros(n),1920000,c,g)
        w.start()
        deadline=time.monotonic()+2
        while w.samples<2048 and time.monotonic()<deadline:time.sleep(.01)
        w.stop()
        self.assertEqual(got,[(1024,14090000,False),(512,14090000,True),(512,21090000,False)])

    def test_gap_resets_and_then_spectrum_recovers(self):
        frames=[];e=SkimmerEngine(on_spectrum=lambda *a:frames.append(a))
        block=np.zeros(38400,dtype=np.complex64)
        e.feed(block,1920000,14090000,True)
        for _ in range(30):e.feed(block,1920000,14090000)
        self.assertTrue(frames)

    def test_real_time_1920000_512_two_station_decode_without_loss(self):
        from psrtty.skimmer_selftest import check_high_rate
        report=check_high_rate(seconds=21,decode=True)
        self.assertEqual(report['lost_samples'],0)
        self.assertEqual(report['calls'],['JA1ABC','JA2XYZ'])
        self.assertEqual(report['samples'],report['processed'])
        self.assertGreater(report['spectra'],10)

    def test_extio_command_changes_hardware_request_not_readback_label(self):
        src=ExtIOInput('test.dll',14090000,Mock(),Mock())
        src.process=Mock(stdin=io.BytesIO());src.process.poll.return_value=None
        src.actual_center=14090000;src.set_center(21090000)
        self.assertEqual(src.process.stdin.getvalue(),b'CENTER 21090000\n')
        self.assertEqual(src.actual_center,14090000)

    def test_new_bridges_match_pe_architecture(self):
        for bits in (32,64):self.assertEqual(pe_bits(ROOT/f'lib/iq/psrtty-extio{bits}.exe'),bits)

class Macro130Tests(unittest.TestCase):
    def test_both_templates_exact_and_independent(self):
        rows=jarl_contest_one_template()
        self.assertEqual([m['text'] for m in rows],[
            'CQ TEST {MYCALL} {MYCALL} K','{MYCALL} {MYCALL} {MYCALL}',
            '{HISCALL} 599 {SENT}-{SENT} {SENT} {HISCALL}','TU QRZ DE {MYCALL} CQ',
            'AGN AGN','NR NR?','{HISCALL} 599-{SENT}-{SENT}','QRZ DE {MYCALL}',''])
        self.assertEqual(rows[3]['name'],'TU 73')
        self.assertIn('DE {MYCALL} K',jarl_ww_template()[2]['text'])
        self.assertLess(list(TEMPLATES).index(JARL_ONE_NAME),list(TEMPLATES).index(TEMPLATE_NAME))
        rows[0]['text']='CUSTOM';self.assertNotEqual(jarl_contest_one_template()[0]['text'],'CUSTOM')

class UI130Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def skimmer(self):
        from psrtty.ui.ry_windows import SkimmerWindow
        s=SkimmerWindow(self.window);self.window.ry_skimmer_window=s;s.timer.stop();return s

    def test_frequency_defaults_saved_per_input_and_off_uses_manual_center(self):
        s=self.skimmer();w=self.window
        for method,checked in [('extio',True),('rtl',False)]:
            s.options=dict(method=method,center=14.09);s.load_follow()
            self.assertEqual(s.follow.isChecked(),checked)
        s.input=Mock();s.follow.setChecked(True)
        with patch.object(w,'_connected',return_value=True):
            w.current_freq_hz=21090000;s.last_requested=None;s.follow_frequency()
            s.input.set_center.assert_called_with(21090000)
            s.input.set_center.reset_mock();s.follow_frequency();s.input.set_center.assert_not_called()
            s.follow.setChecked(False);s.input.set_center.assert_called_once_with(14090000)
        self.assertFalse(w.store.data['ui']['ry_skimmer_inputs']['rtl']['follow'])
        s.input=None

    def test_no_retune_disconnected_or_while_icom_transmitting(self):
        s=self.skimmer();s.options={'method':'extio'};s.input=Mock();w=self.window
        with patch.object(w,'_connected',return_value=False):s.follow_frequency()
        with patch.object(w,'_connected',return_value=True):
            w.current_freq_hz=21090000;w.active_tx_id=1;s.follow_frequency();w.active_tx_id=None
        s.input.set_center.assert_not_called();s.input=None

    def test_readback_mismatch_is_visible_and_never_relabels_canvas(self):
        s=self.skimmer();s.last_requested=21090000;s.request_time=time.monotonic()-3
        s.canvas.range=(21224800,21244800)
        with patch('psrtty.ui.ry_windows.event') as record:
            s.show_frequency_state({'center':21234800});s.show_frequency_state({'center':21234800})
            self.assertEqual(record.call_count,1)
        self.assertIn('21.234800',s.frequency_note.text());self.assertIn('21.090000',s.frequency_note.text())
        self.assertEqual(s.canvas.range,(21224800,21244800))
        s.show_frequency_state({'center':21090000});self.assertFalse(s.frequency_note.text())

    def test_localized_graph_and_adjacent_controls_wrap_at_small_width(self):
        for code in i18n.LANGUAGES:
            i18n.configure(code);s=self.skimmer();s.show();s.resize(600,500);self.pump(.02)
            self.assertNotIn('ry.',s.follow.text());self.assertEqual(s.tabs.count(),2)
            s.health.feed(dict(input_sps=1920000,queue_ms=0,loss_percent=0,interval=.25,incoming=.25,processed_time=.25,lost_time=0))
            self.assertIn('1.92',s.health.metrics.text());self.assertEqual(s.health.history[-1][1],[1.,0.,0.,0.])
            self.assertLessEqual(s.toolbar.itemAt(s.toolbar.indexOf(s.follow)).geometry().right(),s.width())
            s.health.grab();s.close()
        i18n.configure('ja')

    def test_off_selection_during_tx_defers_icom_tune_until_rx(self):
        s=self.skimmer();s.options=dict(method='extio',center=14.09);s.input=Mock()
        self.window.active_tx_id=1;s.follow.setChecked(False)
        s.input.set_center.assert_not_called();self.assertEqual(s.deferred_center,14090000)
        self.window.active_tx_id=None;s.follow_frequency()
        s.input.set_center.assert_called_once_with(14090000);s.input=None

    def test_new_center_removes_old_band_spots(self):
        from psrtty.ry_spots import Spot
        s=self.skimmer();s.display_center=14090000;s.rows={1:Spot('JA1ABC',14090085,time.time())}
        s.spectrum(np.array([21090000]),np.array([0]),21090000,20000);s.refresh()
        self.assertFalse(s.rows);self.assertEqual(s.canvas.band,21)

    def test_legacy_template_name_resolves_without_rewriting_custom_rows(self):
        from psrtty.ui.macro_dialog import MacroDialog
        self.store.data['macro_template']=LEGACY_JARL_NAME;self.store.macros[0]['text']='MY CUSTOM CQ'
        d=MacroDialog(self.store,self.window)
        self.assertEqual(d.template.currentData(),TEMPLATE_NAME)
        self.assertEqual(d.table.item(0,2).text(),'MY CUSTOM CQ')
        d.template.setCurrentIndex(d.template.findData(JARL_ONE_NAME));d._apply_template()
        self.assertEqual(d.sent.text(),'01');self.assertTrue(d.sent_fixed.isChecked())
        self.assertEqual(d.table.item(3,2).text(),'TU QRZ DE {MYCALL} CQ');d.close()

del _Fixture
