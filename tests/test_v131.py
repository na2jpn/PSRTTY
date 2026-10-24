import io
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from scipy.signal import hilbert
from psrtty.ry_skimmer import SkimmerEngine,SkimmerWorker
from tests.test_v130 import UI130Tests as _Fixture

class DSP131Tests(unittest.TestCase):
    def test_fixed_monitor_frequency_and_rf_tone_survive_moving_source_center(self):
        target=21090000;rate=240000;spectra=[]
        e=SkimmerEngine(on_spectrum=lambda *a:spectra.append(a));e.set_monitor_center(target)
        for actual in (target,target+30000,target-50000):
            t=np.arange(120000)/rate
            iq=np.exp(2j*np.pi*(target+3000-actual)*t).astype(np.complex64)
            for i in range(0,len(iq),24000):e.feed(iq[i:i+24000],rate,actual)
            self.assertTrue(e.coverage);f,db,c,span=spectra[-1]
            self.assertEqual(c,target);self.assertAlmostEqual(f[np.argmax(db)],target+3000,delta=10)
        e.feed(iq[:1000],rate,target+200000);self.assertFalse(e.coverage)

    def test_fixed_monitor_decodes_calls_from_offset_source_iq(self):
        from psrtty.live_tx import ToneEncoder
        rate=96000;target=14090000;actual=target+20000;out=[]
        encoder=ToneEncoder(rate,45.45,2210,2040,False)
        text=('CQ DE JA1ABC JA1ABC 599 001 ')*3
        audio=np.concatenate([encoder.tone(True,8),encoder.code(31),*[encoder.char(c) for c in text],encoder.tone(True,20)])
        iq=(hilbert(audio)*np.exp(2j*np.pi*(3000-2125-(actual-target))*np.arange(len(audio))/rate)).astype(np.complex64)
        e=SkimmerEngine(on_text=lambda *a:out.append(a));e.set_monitor_center(target)
        for i in range(0,len(iq),8192):e.feed(iq[i:i+8192],rate,actual)
        self.assertIn('JA1ABC',{r[1] for r in out})
        for row in out:self.assertAlmostEqual(row[0],target+3085,delta=12)

    def test_twofold_clock_discrepancy_warns_without_changing_sample_rate(self):
        with patch('psrtty.ry_skimmer.time.monotonic',return_value=100) as clock:
            w=SkimmerWorker();w.offer(np.zeros(6000),6000,14090000)
            clock.return_value=106
            # Isolate sample-count clock from intentional queue-overload policy.
            with w.stats_lock:w.received=72000;w.last_arrival=106
            s=w.snapshot()
            self.assertTrue(s['rate_warning']);self.assertEqual(s['rate'],6000)
            self.assertEqual(s['measured_sps'],12000);self.assertEqual(s['rate_ratio'],2)
            clock.return_value=112
            with w.stats_lock:w.received=72000;w.last_arrival=112
            s=w.snapshot();self.assertFalse(s['rate_warning'])

class UI131Tests(_Fixture):
    # Reuse fixture only; inherited regression methods are suppressed below.
    def test_large_center_buttons_adjust_both_directions_and_allow_direct_entry(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        from psrtty.ui.ry_windows import SkimmerSetup
        d=SkimmerSetup(self.window);d.choose('extio');d.show();self.pump(.02)
        self.assertGreater(d.center.lineEdit().width(),80)
        d.center.setValue(10.08);QTest.mouseClick(d.center_plus,Qt.LeftButton);self.assertAlmostEqual(d.center.value(),10.081)
        QTest.mouseClick(d.center_minus,Qt.LeftButton);self.assertAlmostEqual(d.center.value(),10.08)
        d.center.lineEdit().setText('21.090000 MHz');d.center.interpretText();self.assertEqual(d.center.value(),21.09)
        self.assertGreaterEqual(d.center_plus.height(),30);d.close()

    def test_large_band_change_waits_for_stability_and_does_not_repeat(self):
        s=self.skimmer();s.options=dict(method='extio',center=14.09,span=20000);s.input=Mock(actual_center=14090000,rate=1920000);s.worker=Mock()
        with patch.object(self.window,'_connected',return_value=True),patch('psrtty.ui.ry_windows.time.monotonic',return_value=10) as clock:
            self.window.current_freq_hz=21090000;s.follow_frequency();s.input.set_center.assert_not_called()
            clock.return_value=10.7;s.follow_frequency();s.input.set_center.assert_called_once_with(21090000)
            clock.return_value=11;s.follow_frequency();self.assertEqual(s.input.set_center.call_count,1)
            s.input.actual_center=21090000;clock.return_value=12;s.follow_frequency();self.assertEqual(s.input.set_center.call_count,1)
        s.input=None;s.worker=None

    def test_following_physical_vfo_within_iq_band_sends_no_retunes(self):
        s=self.skimmer();s.options=dict(method='extio',center=21.09,span=20000);s.input=Mock(actual_center=21090000,rate=1920000);s.worker=Mock()
        with patch.object(self.window,'_connected',return_value=True):
            for hz in range(21090000,21120000,1000):self.window.current_freq_hz=hz;s.follow_frequency()
        s.input.set_center.assert_not_called();self.assertEqual(s.last_monitor,21119000);s.input=None;s.worker=None

    def test_off_keeps_monitor_fixed_when_vendor_center_changes(self):
        s=self.skimmer();s.options=dict(method='extio',center=21.09,span=20000,follow=False);s.load_follow();s.worker=Mock();s.input=Mock(actual_center=21090000,rate=1920000)
        for hz in (21100000,21110000,21120000):
            self.window.current_freq_hz=hz;s.input.actual_center=hz;s.follow_frequency();s.show_frequency_state(dict(center=hz,rate=1920000))
            self.assertEqual(s.last_monitor,21090000);self.assertFalse(s.frequency_note.text())
        s.input.set_center.assert_not_called();s.input=None;s.worker=None

    def test_outside_fixed_input_band_is_visible_then_recovers(self):
        s=self.skimmer();s.options=dict(method='extio',center=14.09,span=20000);s.last_monitor=14090000
        s.show_frequency_state(dict(center=21090000,rate=1920000));self.assertTrue(s.canvas.message)
        s.show_frequency_state(dict(center=14090000,rate=1920000));self.assertFalse(s.canvas.message)

# UI130 is already discovered in test_v130; do not run inherited tests twice.
for name in dir(_Fixture):
    if name.startswith('test_') and name not in UI131Tests.__dict__:setattr(UI131Tests,name,None)
del _Fixture

class Documentation131Tests(unittest.TestCase):
    def test_fixed_document_names_and_no_old_version_files(self):
        root=Path(__file__).resolve().parents[1]
        self.assertTrue((root/'README.md').exists())
        for p in root.glob('*'):
            if p.suffix.lower() in ('.txt','.md','.html'):self.assertIn(p.name,('README.md','CHANGELOG.md','requirements.txt'))
        for name in ('DEVELOPMENT.md','TESTING.md','UPDATE.md','RADIOS.md','FORMATS.md'):
            self.assertTrue((root/'docs'/name).is_file())
        self.assertFalse((root/'docs/history').exists());self.assertFalse((root/'docs/validation').exists())
