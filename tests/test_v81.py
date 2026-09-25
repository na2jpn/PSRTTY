import time
import unittest
import numpy as np
from unittest.mock import patch
from psrtty.audio_engine import AudioEngine
from psrtty.ui.cross_scope import scope_points
from tests.test_ui_v02 import UITests as _Fixture

class ScopeDSPTests(unittest.TestCase):
    def test_axes_silence(self):
        t=np.arange(4096)/48000
        for tone,axis in [(2125,0),(2295,1)]:
            xy=scope_points(.2*np.sin(2*np.pi*tone*t),48000,2125,2295,45.45)
            energy=np.mean(xy*xy,axis=0)
            self.assertGreater(energy[axis],5*energy[1-axis])
        self.assertEqual(len(scope_points(np.zeros(4096),48000,2125,2295,45.45)),0)
    def test_ellipse_phase_and_detuning(self):
        t=np.arange(4096)/48000
        def covariance(tone, mark=2125, space=2295):
            xy=scope_points(.2*np.sin(2*np.pi*tone*t),48000,mark,space,45.45)
            return np.corrcoef(xy.T)[0,1], np.linalg.eigvalsh(np.cov(xy.T))
        for tone in (2125,2295):
            corr, eigen=covariance(tone)
            self.assertLess(abs(corr),.08)
            self.assertGreater(eigen[0]/eigen[1],.0002)
            self.assertLess(eigen[0]/eigen[1],.006)
            shifted,_=covariance(tone+40)
            self.assertGreater(abs(shifted),.25)
        corr,_=covariance(2295,2295,2125)
        self.assertLess(abs(corr),.08)

    def test_decode_unchanged(self):
        a=AudioEngine();seen=[];a.decoder.feed=lambda x:seen.append(x.copy())
        samples=np.random.default_rng(81).normal(0,.1,(4096,1)).astype('float32')
        a._input_callback(samples,4096,None,None)
        self.assertIsNone(a.scope_frame)
        a.scope_enabled=True;a._last_fft=0;a._input_callback(samples,4096,None,None)
        np.testing.assert_array_equal(seen[0],seen[1]);self.assertIsNotNone(a.scope_frame)
        a.configure_decoder(45.45,1500,1670,False);self.assertIsNone(a.scope_frame)

class ScopeUITests(_Fixture):
    def test_toggle(self):
        w=self.window;w.show();self.pump(.03);width=w.spectrum.width()
        with patch.object(w,'disconnect_radio') as disconnect:
            w.scope_button.click();self.pump(.03);d=w.scope_window
            self.assertTrue(d.isVisible());self.assertTrue(w.audio.scope_enabled)
            self.assertEqual(w.spectrum.width(),width)
            w.audio.scope_frame=(time.monotonic()-1,np.ones(4096),(2125,2295,45.45))
            d.refresh();self.assertEqual(len(d.canvas.points),0)
            d.close();self.pump(.03)
            self.assertFalse(w.scope_button.isChecked());self.assertFalse(w.audio.scope_enabled)
            self.assertFalse(d.timer.isActive())
            w.scope_button.click();self.assertIs(w.scope_window,d)
            w.scope_button.click();self.assertFalse(d.isVisible())
            disconnect.assert_not_called()
del _Fixture
