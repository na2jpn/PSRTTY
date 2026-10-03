import threading
import unittest
from unittest.mock import patch, Mock
import numpy as np
from psrtty.audio_engine import AudioEngine
from tests import test_ui_v02 as fixture

class Output:
    def __init__(self,device,failure=None,entered=None,release=None,**kwargs):
        self.device=device;self.failure=failure;self.entered=entered;self.release=release
        self.calls=[];self.data=[];self.threads=[]
    def op(self,name):
        self.calls.append(name);self.threads.append(threading.get_ident())
        if self.failure==name:raise OSError(name)
    def start(self):self.op('start')
    def write(self,data):
        self.op('write');self.data.append(data.copy())
        if self.entered:self.entered.set()
        if self.release:self.release.wait(2)
    def stop(self):self.op('stop')
    def abort(self):self.op('abort')
    def close(self):self.op('close')

class OfflineAudioTests(unittest.TestCase):
    def send(self,engine,done,on=None,off=None,allow=True):
        return engine.send_text('RY',1,45.45,2125,2295,False,.2,on,off,done,allow_secondary_only=allow)
    def test_all_availability_combinations_and_independent_volume_no_ptt(self):
        for primary,secondary in ((True,True),(True,False),(False,True),(False,False)):
            with self.subTest(primary=primary,secondary=secondary):
                engine=AudioEngine();engine.configure_secondary({'enabled':True,'device':2,'gain':1.5})
                done,on,off=Mock(),Mock(),Mock();streams=[]
                def resolve(sd,device,kind):
                    if not (primary if device==1 else secondary):raise ValueError('missing')
                    return device
                def output(**kwargs):
                    result=Output(**kwargs);streams.append(result);return result
                with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.offline_audio.resolve_device',side_effect=resolve),patch('psrtty.audio_engine.encode_text_audio',return_value=np.ones(1920,dtype=np.float32)*.5):
                    sd.OutputStream.side_effect=output
                    self.assertTrue(self.send(engine,done,on,off)[0]);engine.wait_tx(3)
                self.assertFalse(engine._tx_active);self.assertEqual(done.call_args.args[0],primary or secondary)
                on.assert_not_called();off.assert_not_called()
                self.assertEqual(len(streams),int(primary)+int(secondary))
                for stream in streams:
                    self.assertEqual(len(set(stream.threads)),1);self.assertIn('close',stream.calls)
                    np.testing.assert_allclose(stream.data[0],.1 if stream.device==1 else .75)
    def test_open_start_write_failure_still_uses_other_output(self):
        for failure in ('open','start','write','close'):
            engine=AudioEngine();engine.configure_secondary({'enabled':True,'device':2});done=Mock();streams=[]
            def output(**kwargs):
                if kwargs['device']==1 and failure=='open':raise OSError('open')
                stream=Output(failure=failure if kwargs['device']==1 else None,**kwargs);streams.append(stream);return stream
            with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.offline_audio.resolve_device',side_effect=lambda sd,d,k:d):
                sd.OutputStream.side_effect=output
                self.send(engine,done);engine.wait_tx(3)
            self.assertTrue(done.call_args.args[0]);self.assertIn(failure,engine.secondary_notice)
            self.assertTrue(any(s.device==2 and 'stop' in s.calls for s in streams))
    def test_stop_aborts_both_on_own_threads(self):
        engine=AudioEngine();engine.configure_secondary({'enabled':True,'device':2});done=Mock()
        entered=[threading.Event(),threading.Event()];release=threading.Event();streams=[]
        def output(**kwargs):
            stream=Output(entered=entered[kwargs['device']-1],release=release,**kwargs);streams.append(stream);return stream
        with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.offline_audio.resolve_device',side_effect=lambda sd,d,k:d):
            sd.OutputStream.side_effect=output;self.send(engine,done)
            self.assertTrue(all(e.wait(2) for e in entered));engine.stop_tx();release.set();engine.wait_tx(3)
        self.assertFalse(done.call_args.args[0]);self.assertFalse(engine._tx_active)
        for stream in streams:
            self.assertIn('abort',stream.calls);self.assertEqual(stream.calls[-1],'close');self.assertEqual(len(set(stream.threads)),1)
    def test_connected_and_disabled_do_not_fallback(self):
        import ast
        from pathlib import Path
        from psrtty.i18n import TEXT
        source=Path(__file__).resolve().parents[1]/'psrtty/offline_audio.py'
        for node in ast.walk(ast.parse(source.read_text(encoding='utf-8'))):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr':
                self.assertIn(node.args[0].value,TEXT)
        for enabled,allow in ((True,False),(False,True)):
            engine=AudioEngine();engine.configure_secondary({'enabled':enabled,'device':2})
            with patch('psrtty.audio_engine.resolve_device',side_effect=ValueError('primary missing')),patch('psrtty.offline_audio.start_offline_dual') as fallback:
                self.assertFalse(self.send(engine,Mock(),allow=allow)[0]);fallback.assert_not_called()
    def test_duplicate_resolved_device_opens_once(self):
        engine=AudioEngine();engine.configure_secondary({'enabled':True,'device':2});done=Mock()
        with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.offline_audio.resolve_device',return_value=3):
            sd.OutputStream.side_effect=Output;self.send(engine,done);engine.wait_tx(3);sd.OutputStream.assert_called_once()
        self.assertTrue(done.call_args.args[0])

class UI108Fix2Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp;tearDown=fixture.UITests.tearDown;pump=fixture.UITests.pump
    def test_offline_permission_reaches_worker_and_blocks_when_off(self):
        w=self.window;w.radio=None;w.offline_tx.setChecked(True)
        with patch.object(w.audio,'send_text',return_value=(False,'test')) as send:
            w._send_text('RY');self.assertTrue(send.call_args.kwargs['allow_secondary_only'])
            send.reset_mock();w.offline_tx.setChecked(False);w._send_text('RY');send.assert_not_called()
    def test_real_main_path_secondary_only(self):
        w=self.window;w.radio=None;w.offline_tx.setChecked(True);w.audio.configure_secondary({'enabled':True,'device':2})
        def resolve(sd,device,kind):
            if device!=2:raise ValueError('primary missing')
            return 2
        with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.offline_audio.resolve_device',side_effect=resolve):
            sd.OutputStream.side_effect=Output
            self.assertTrue(w._send_text('RY'));w.audio.wait_tx(3);self.pump(.02)
            self.assertIsNone(w.active_tx_id);self.assertFalse(w.audio._tx_active)
            self.assertEqual(sd.OutputStream.call_args.kwargs['device'],2)
