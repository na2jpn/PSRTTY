import threading
import unittest
from unittest.mock import Mock, patch
import numpy as np
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from psrtty.audio_engine import AudioEngine
from psrtty.decoder import RTTYDecoder
from psrtty.rtty_codec import encode_text_audio
from tests.test_ui_v02 import UITests as _Fixture

class FakeOutput:
    def __init__(self, fail=None):
        self.calls=[];self.entered=threading.Event();self.release=threading.Event();self.fail=fail
    def op(self,name):
        self.calls.append((name,threading.get_ident()))
        if self.fail==name:raise OSError(name)
    def start(self):self.op('start')
    def write(self,data):
        self.op('write');self.entered.set();self.release.wait(1)
    def stop(self):self.op('stop')
    def abort(self):self.op('abort')
    def close(self):self.op('close')

class Audio60Tests(unittest.TestCase):
    def test_cancel_owned_stream_and_resend(self):
        engine=AudioEngine();gui=threading.get_ident()
        with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.audio_engine.resolve_device',return_value=None):
            for run in range(3):
                stream=FakeOutput();sd.OutputStream.return_value=stream;done=Mock();off=Mock(return_value=True)
                self.assertTrue(engine.send_text('CQ TEST','AUTO',45.45,2125,2295,False,.3,lambda:True,off,done)[0])
                self.assertTrue(stream.entered.wait(1));engine.stop_tx();engine.stop_tx();stream.release.set();engine.wait_tx()
                self.assertFalse(engine._tx_active);self.assertFalse(done.call_args.args[0]);off.assert_called_once()
                self.assertEqual([x[0] for x in stream.calls][-2:],['abort','close'])
                self.assertEqual(len({x[1] for x in stream.calls}),1);self.assertNotEqual(stream.calls[0][1],gui)
            sd.stop.assert_not_called();sd.play.assert_not_called();sd.wait.assert_not_called()
    def test_output_errors_always_attempt_ptt_release(self):
        for failure in ('start','write','stop','abort','close'):
            stream=FakeOutput(failure);stream.release.set();engine=AudioEngine();done=Mock();off=Mock(return_value=True)
            if failure=='abort':
                def write(data):engine.stop_tx()
                stream.write=write
            with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.audio_engine.resolve_device',return_value=None):
                sd.OutputStream.return_value=stream
                engine.send_text('CQ','AUTO',45.45,2125,2295,False,.3,lambda:True,off,done);engine.wait_tx()
            off.assert_called_once();self.assertFalse(engine._tx_active);self.assertFalse(done.call_args.args[0])

class Decoder60Tests(unittest.TestCase):
    def decode(self,audio,sq=2,invert=False):
        out=[];dec=RTTYDecoder(on_char=out.append,invert=invert);dec.sq_level=sq
        for i in range(0,len(audio),731):dec.feed(audio[i:i+731])
        return ''.join(out)
    def test_noise_suppression_and_signal_preservation(self):
        rng=np.random.default_rng(2026);text='CQ DE JH1HST 599 001 TU 73';audio=encode_text_audio(text)
        for level in (0,2,10):self.assertEqual(self.decode(audio,level),text+'\r\n')
        self.assertEqual(self.decode(audio*.0001),text+'\r\n')
        self.assertEqual(self.decode(audio+rng.normal(0,.2,len(audio))),text+'\r\n')
        self.assertEqual(self.decode(encode_text_audio(text,invert=True),invert=True),text+'\r\n')
        noise=rng.normal(0,.2,48000*10)
        self.assertGreater(len(self.decode(noise,0)),0);self.assertEqual(self.decode(noise,2),'')
        f=np.fft.rfftfreq(len(noise),1/48000)
        narrow=np.fft.irfft(np.fft.rfft(noise)*(abs(f-2210)<250))
        self.assertLess(len(self.decode(narrow,10)),len(self.decode(narrow,0)))
    def test_invalid_start_and_stop_never_emit_or_change_shift(self):
        out=[];d=RTTYDecoder(on_char=out.append);d._quality=1
        d._consume_logic(0,1,0);d._consume_logic(1,1,.5*d.bit_time)
        self.assertEqual(d._state,'idle')
        d._consume_logic(0,1,1);d._consume_logic(0,1,1+.5*d.bit_time)
        for i in range(5):d._consume_logic((27>>i)&1,1,1+(1.51+i)*d.bit_time)
        d._consume_logic(0,1,1+6.51*d.bit_time)
        self.assertFalse(d._ita2.figures);self.assertEqual(out,[])

class UI60Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump
    def test_macro_stop_button_offline_and_connected(self):
        w=self.window;w.offline_tx.setChecked(True);w.auto_log.setChecked(True);w.q_call.setText('JQ7FIU')
        w.store.macros[8]['text']='TEST'
        stop=[b for b in w.findChildren(QPushButton) if b.text()=='STOP'][0]
        for connected in (False,True):
            ctl=Mock();ctl.status.connected=connected;ctl.set_ptt.return_value=True;w.radio=ctl
            with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.audio_engine.resolve_device',return_value=None):
                for idx in range(9):
                    stream=FakeOutput();sd.OutputStream.return_value=stream
                    w._send_macro(idx);self.assertTrue(stream.entered.wait(1))
                    stop.click();stream.release.set();w.audio.wait_tx();self.pump(.02)
                    self.assertIsNone(w.active_tx_id);self.assertIsNone(w.pending_auto_log)
                    self.assertFalse(w.auto_cq_active);self.assertFalse(w.q_datetime.manual.isChecked())
                    w.adif.append.assert_not_called()
                sd.stop.assert_not_called()
            if connected:self.assertEqual(ctl.set_ptt.call_args.args,(False,))
        w.radio=None
    def test_sq_header_persistence_and_center_drag(self):
        w=self.window;w.show();self.pump(.05)
        self.assertEqual(w.decode_sq.currentText(),'4')
        self.assertEqual([w.decode_sq.itemText(i) for i in range(11)],['OFF']+list(map(str,range(1,11))))
        w.decode_sq.setCurrentIndex(7)
        self.assertEqual(w.store.data['ui']['decode_sq'],7);self.assertEqual(w.audio.decoder.sq_level,7)
        w.store.save.assert_called();self.assertLess(w.decode_sq.x(),w.decode_enabled.x())
        s=w.spectrum;before=(s.mark_hz,s.space_hz);center=QPoint(int(s._x(sum(before)/2)),6)
        QTest.mouseMove(s,center);self.assertEqual(s.cursor().shape(),Qt.OpenHandCursor)
        QTest.mousePress(s,Qt.LeftButton,pos=center);QTest.mouseMove(s,center+QPoint(35,0));QTest.mouseRelease(s,Qt.LeftButton,pos=center+QPoint(35,0))
        self.assertGreater(s.mark_hz,before[0]);self.assertAlmostEqual(s.space_hz-s.mark_hz,before[1]-before[0])
        self.assertIsNone(s.drag)

del _Fixture
