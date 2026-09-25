import unittest
import numpy as np
from psrtty.rtty_codec import encode_text_audio
from psrtty.ui.cross_scope import stable_traces,CrossScopeWindow
from psrtty.audio_engine import AudioEngine
from PySide6.QtWidgets import QApplication

class Fix2Tests(unittest.TestCase):
    def test_text_traffic_keeps_short_separate_traces(self):
        audio=encode_text_audio('CQ CQ DE JH1HST JH1HST K 599 599 TU 73')
        counts=[]
        for end in range(4096,len(audio),9600):
            traces=stable_traces(audio[end-4096:end],48000,2125,2295,45.45)
            counts.append(len(traces))
            self.assertLessEqual(len(traces),2)
            for trace in traces:
                self.assertTrue(np.isfinite(trace).all())
                self.assertLessEqual(len(trace),69)
                self.assertGreaterEqual(len(trace),40)
        self.assertGreater(counts.count(2),0)
        self.assertLess(counts.count(0),len(counts)*.1)
    def test_detuning_survives_gating_and_silence_is_empty(self):
        t=np.arange(4096)/48000
        for tone in (2125,2295):
            aligned=stable_traces(.2*np.sin(2*np.pi*tone*t),48000,2125,2295,45.45)
            shifted=stable_traces(.2*np.sin(2*np.pi*(tone+40)*t),48000,2125,2295,45.45)
            self.assertEqual(len(aligned),1);self.assertEqual(len(shifted),1)
            self.assertLess(abs(np.corrcoef(aligned[0].T)[0,1]),.15)
            self.assertGreater(abs(np.corrcoef(shifted[0].T)[0,1]),.25)
        self.assertEqual(stable_traces(np.zeros(4096),48000,2125,2295,45.45),[])
    def test_refresh_rate_and_hidden_cleanup(self):
        app=QApplication.instance() or QApplication([])
        engine=AudioEngine();window=CrossScopeWindow(engine)
        window.show();app.processEvents()
        self.assertEqual(window.timer.interval(),200)
        window.canvas.traces=[np.ones((20,2))]
        window.hide();self.assertEqual(window.canvas.traces,[])
        self.assertFalse(engine.scope_enabled);self.assertFalse(window.timer.isActive())
        window.close()
