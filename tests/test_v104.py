import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')

import time
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QMessageBox, QMenu
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from psrtty.config import DEFAULT_CONFIG
from psrtty.audio_engine import AudioEngine
from psrtty.rtty_codec import encode_text_audio
from psrtty.sub_decode import SubDecodeWorker, pair_candidates
from psrtty.ui.sub_decode import valid_position
from tests.test_ui_v02 import UITests as _Fixture


class SubDSP104Tests(unittest.TestCase):
    def test_main_decode_is_identical_with_active_sub_worker(self):
        signal=encode_text_audio('CQ TEST JH1HST 599 25 ',sample_rate=48000,baud=45.45,
                                 mark_hz=2125,space_hz=2295,invert=False,amplitude=.35)
        results=[]
        for with_sub in (False,True):
            chars=[];engine=AudioEngine(on_char=chars.append)
            worker=SubDecodeWorker(48000,lambda *_:None)
            if with_sub:
                worker.start();engine.sub_worker=worker
            for start in range(0,len(signal)-959,960):
                block=signal[start:start+960].reshape(-1,1)
                engine._input_callback(block,960,None,None)
            if with_sub:worker.stop()
            results.append(''.join(chars))
        self.assertIn('JH1HST',results[0])
        self.assertEqual(results[0],results[1])

    def test_distinct_pairs_are_ranked_while_main_and_other_are_excluded(self):
        freqs=np.arange(1600.,2901.,5.)
        power=np.full(len(freqs),-75.)
        for tone in (1870,2040,2125,2295,2400,2570):
            power[np.argmin(abs(freqs-tone))]=-24.
        left=pair_candidates(freqs,power,2210,170,0,other=2485)
        right=pair_candidates(freqs,power,2210,170,1,other=1955)
        self.assertTrue(any(abs(c-1955)<6 for c,_ in left))
        self.assertTrue(any(abs(c-2485)<6 for c,_ in right))
        self.assertFalse(valid_position(2210,0,2210,170))

    def test_bounded_sub_queue_drops_only_sub_samples(self):
        worker=SubDecodeWorker(48000,lambda *_:None)
        block=np.zeros(960,dtype=np.float32)
        for _ in range(30):worker.offer(block)
        self.assertGreater(worker.dropped,0)
        self.assertLessEqual(worker.backlog(),8)
        worker.start();worker.stop()


class UI104Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_track_needs_repeated_nearby_pair(self):
        w=self.window
        frequencies=np.arange(1750.,2701.,5.)
        power=np.full(len(frequencies),-80.)
        for tone in (2155,2325):power[np.argmin(abs(frequencies-tone))]=-18.
        w.last_spectrum=(frequencies,power)
        w.auto_track.setChecked(True)
        w.track_pause_until=0
        before=w.spectrum.mark_hz
        w._auto_track_tick();w._auto_track_tick()
        self.assertEqual(w.spectrum.mark_hz,before)
        w._auto_track_tick()
        self.assertEqual(w.spectrum.mark_hz-before,12)

    def test_defaults_warning_and_sub_manual_control(self):
        w=self.window;w.show();self.pump(.03)
        self.assertLess(w.scope_button.geometry().right(),w.sub_button.geometry().left())
        self.assertLess(w.sub_button.geometry().right(),w.center_tuning.geometry().left())
        self.assertEqual(w.sub_button.parent(),w.scope_button.parent())
        self.assertEqual(w.center_tuning.text(),'C同調 ---')
        metrics=w.center_tuning.fontMetrics()
        self.assertEqual(w.center_tuning.width(),
                         metrics.horizontalAdvance('C同調 +24.9 Hz')
                         +metrics.horizontalAdvance('あ')+16)
        self.assertTrue(DEFAULT_CONFIG['ui']['clear_on_frequency'])
        self.assertFalse(w.auto_track.isChecked())
        self.assertIsNone(w.sub_window)
        view=next(m for m in w.menuBar().findChildren(QMenu) if m.title()=='表示')
        self.assertEqual([a.text() for a in view.actions()][-4:],
                         ['コントロール','クロススコープ','','サブデコ'])
        with patch.object(QMessageBox,'exec',return_value=QMessageBox.Cancel):
            w._show_sub()
        self.assertIsNone(w.sub_window)
        with patch.object(QMessageBox,'exec',return_value=QMessageBox.Ok):
            w._show_sub()
        self.pump(.03)
        sub=w.sub_window
        self.assertTrue(sub.isVisible())
        self.assertTrue(w.screen().availableGeometry().contains(sub.geometry()))
        self.assertTrue(all(box.isChecked() for box in sub.checks))
        sub._manual(0,sub.centers[0]-10)
        self.assertFalse(sub.checks[0].isChecked())
        self.assertTrue(sub.checks[1].isChecked())
        sub.close();self.pump(.03)
        self.assertIsNone(w.audio.sub_worker)

    def test_sub_a_label_drag_moves_pair_and_disables_only_a_sweep(self):
        w=self.window;w.show()
        with patch.object(QMessageBox,'exec',return_value=QMessageBox.Ok):
            w._show_sub()
        self.pump(.03)
        sub=w.sub_window;scope=sub.scope
        scope.set_spectrum(np.array([]),np.array([]),2210,1000,170,sub.centers)
        original=sub.centers.copy()
        start=QPoint(round(scope._x(original[0])),12)
        end=QPoint(start.x()+12,start.y())
        QTest.mousePress(scope,Qt.LeftButton,pos=start)
        QTest.mouseMove(scope,end)
        QTest.mouseRelease(scope,Qt.LeftButton,pos=end)
        self.assertGreater(sub.centers[0],original[0]+10)
        self.assertEqual(sub.centers[1],original[1])
        self.assertFalse(sub.checks[0].isChecked())
        self.assertTrue(sub.checks[1].isChecked())
        self.assertEqual(scope.centers,sub.centers)
        sub.close()
