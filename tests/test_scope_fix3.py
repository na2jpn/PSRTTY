import unittest
import numpy as np
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from psrtty.audio_engine import AudioEngine
from psrtty.ui.cross_scope import ScopeAfterglow,CrossScopeWindow,stable_traces
from psrtty.rtty_codec import encode_text_audio

class Fix3Tests(unittest.TestCase):
    def test_axis_retention_replacement_expiry_and_duplicate(self):
        a=ScopeAfterglow();tones=(2125,2295,45.45)
        x=np.ones((5,2));y=x*2
        a.accept(1.,tones,[(0,x)]);a.accept(1.2,tones,[(1,y)])
        shown=a.visible(1.2);self.assertEqual(len(shown),2)
        self.assertAlmostEqual(shown[0][1],1-.2/.7)
        a.accept(1.2,tones,[(0,y)]) # repeated mailbox must not renew MARK
        self.assertEqual(len(a.visible(1.71)),1)
        a.accept(1.75,tones,[(1,x)])
        self.assertEqual(len(a.visible(1.76)),2)
        self.assertEqual(a.visible(2.46),[])
        a.accept(2.,tones,[(0,x)])
        a.accept(2.1,(1500,1670,45.45),[(1,y)])
        self.assertEqual(list(a.latest),[1])
    def test_traffic_both_axes_more_often_with_afterglow(self):
        audio=encode_text_audio('CQ CQ DE JH1HST JH1HST K 599 599 TU 73')
        a=ScopeAfterglow();fresh=held=0
        for end in range(4096,len(audio),9600):
            traces=stable_traces(audio[end-4096:end],48000,2125,2295,45.45,tagged=True)
            now=end/48000;a.accept(now,(2125,2295,45.45),traces)
            visible=a.visible(now);fresh+=len(traces)==2;held+=len(a.latest)==2
            self.assertLessEqual(len(visible),4)
        self.assertGreater(held,fresh)
        self.assertEqual(a.visible(now+.701),[])
    def test_ui_clears_on_tune_hide_and_no_input(self):
        app=QApplication.instance() or QApplication([])
        audio=AudioEngine();w=CrossScopeWindow(audio);w.show()
        with patch('psrtty.ui.cross_scope.time.monotonic',return_value=1.):
            t=np.arange(4096)/48000
            audio.scope_frame=(1.,.2*np.sin(2*np.pi*2125*t),(2125,2295,45.45))
            w.refresh();self.assertTrue(w.canvas.traces)
            audio.scope_frame=(1.1,np.zeros(4096),(1500,1670,45.45))
            w._paint_afterglow();self.assertFalse(w.canvas.traces)
            w.refresh();audio.scope_frame=None;w._paint_afterglow()
            self.assertFalse(w.afterglow.latest)
        w.hide();self.assertFalse(w.fade_timer.isActive())
        self.assertFalse(w.timer.isActive());self.assertFalse(w.canvas.traces)
        w.close()
