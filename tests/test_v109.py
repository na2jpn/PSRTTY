import ast
import copy
import time
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from psrtty.live_tx import LiveText,ToneEncoder,start_live
from psrtty.decoder import RTTYDecoder
from psrtty.rtty_codec import encode_ita2_codes,encode_text_audio,ITA2Decoder
from psrtty.audio_engine import AudioEngine
from psrtty.config import DEFAULT_CONFIG,RIG_MODELS,ConfigStore
from psrtty.radio_support import ICOM_EXTERNAL_PTT,ICOM_EXTERNAL_AUDIO
from psrtty.external_ptt import ExternalPTT
from psrtty.tx_keying import keying_callbacks
from psrtty.i18n import configure,TEXT
from psrtty.civ import CIVController,CIVStatus

class LiveTests(unittest.TestCase):
    def test_age_edit_commit_and_replay(self):
        s=LiveText('ABC');s.times=[10.,10.,10.]
        self.assertIsNone(s.next_char(10.49));self.assertEqual(s.next_char(10.5),(0,0,'A'))
        self.assertFalse(s.update('XBC'));self.assertTrue(s.update('AZ'))
        self.assertEqual(s.position,1);s.replay();self.assertEqual(s.next_char(100),(1,0,'A'))
    def test_streaming_digits_across_idle_and_newline(self):
        enc=ToneEncoder(48000,45.45,2125,2295,False)
        audio=np.concatenate([enc.tone(True,3),enc.code(31),enc.char('5'),enc.tone(True,45.45*2),enc.char('9'),enc.char('A'),enc.char('\n'),enc.tone(True,3)])
        out=[];dec=RTTYDecoder(on_char=out.append)
        for n in range(0,len(audio),960):dec.feed(audio[n:n+960])
        self.assertEqual(''.join(out),'59A\r\n');self.assertGreater(dec.last_signal_time,0)
    def test_three_idle_forms_keep_characters(self):
        for idle in (None,31,0):
            enc=ToneEncoder(48000,45.45,2125,2295,False)
            chunks=[enc.tone(True,3),enc.code(31),enc.char('C'),enc.char('Q')]
            chunks += [enc.tone(True,45.45*2)] if idle is None else [enc.code(idle) for _ in range(13)]
            chunks += [enc.char(c) for c in ' TEST 599\n'];chunks.append(enc.tone(True,3))
            out=[];d=RTTYDecoder(on_char=out.append);d.feed(np.concatenate(chunks))
            self.assertEqual(''.join(out),'CQ TEST 599\r\n')
    def test_standalone_tx_recovers_peer_figures(self):
        out=[];d=RTTYDecoder(on_char=out.append);d._ita2.figures=True
        d.feed(encode_text_audio('CQ'));self.assertEqual(''.join(out),'CQ\r\n')
    def test_silence_not_activity(self):
        d=RTTYDecoder();d.feed(np.zeros(48000,dtype=np.float32));self.assertEqual(d.last_signal_time,0)
    def run_worker(self,hold=False,offline=False,secondary=False,fail_primary=False,key_ok=True):
        engine=AudioEngine();engine.configure_secondary({'enabled':secondary,'device':2,'gain':1.})
        session=LiveText('CQ 599',0,hold);done=Mock();on=Mock(return_value=key_ok);off=Mock(return_value=True)
        output=Mock()
        def write(data):time.sleep(len(data)/48000*.01)
        output.write.side_effect=write
        sd=Mock();sd.OutputStream.return_value=output
        def resolve(_sd,device,kind):
            if fail_primary and device==1:raise ValueError('missing primary')
            return device
        with patch('psrtty.live_tx.resolve_device',side_effect=resolve):
            ok,msg=start_live(engine,sd,session,1,DEFAULT_CONFIG['advanced'],.3,on,off,done,Mock(),offline)
            self.assertTrue(ok)
            if hold:
                time.sleep(.2);engine.stop_tx()
            engine.wait_tx(4.)
        self.assertFalse(engine._tx_active);self.assertTrue(done.called)
        return done,on,off,output,session
    def test_finite_tx_drains_and_unkeys(self):
        done,on,off,output,s=self.run_worker();self.assertTrue(done.call_args.args[0]);off.assert_called_once();output.stop.assert_called_once();self.assertEqual(''.join(s.records),'CQ 599')
    def test_stop_aborts_and_unkeys(self):
        done,on,off,output,s=self.run_worker(hold=True);self.assertFalse(done.call_args.args[0]);off.assert_called_once();output.abort.assert_called()
    def test_offline_secondary_fallback_never_ptt(self):
        done,on,off,output,s=self.run_worker(offline=True,secondary=True,fail_primary=True)
        self.assertTrue(done.call_args.args[0]);on.assert_not_called();off.assert_not_called()
    def test_dual_outputs_same_audio_and_finite_drain(self):
        engine=AudioEngine();engine.configure_secondary({'enabled':True,'device':2,'gain':.5})
        session=LiveText('CQ 599',0,False);done=Mock();streams={1:Mock(),2:Mock()};blocks={1:[],2:[]}
        for device in (1,2):
            def capture(data,k=device):
                blocks[k].append(data.copy())
                if k==1:time.sleep(.001)
            streams[device].write.side_effect=capture
        sd=Mock();sd.OutputStream.side_effect=lambda **kw:streams[kw['device']]
        with patch('psrtty.live_tx.resolve_device',side_effect=lambda sd,d,k:d):
            ok,_=start_live(engine,sd,session,1,DEFAULT_CONFIG['advanced'],.25,Mock(return_value=True),Mock(return_value=True),done,Mock())
            self.assertTrue(ok);engine.wait_tx(4.)
        self.assertTrue(done.call_args.args[0]);self.assertTrue(blocks[1]);self.assertTrue(blocks[2])
        np.testing.assert_allclose(np.concatenate(blocks[2]),np.concatenate(blocks[1])*2)
        for stream in streams.values():stream.stop.assert_called_once();stream.close.assert_called_once();stream.abort.assert_not_called()
    def test_failed_key_has_no_audio(self):
        done,on,off,output,s=self.run_worker(key_ok=False);self.assertFalse(done.call_args.args[0]);output.write.assert_not_called();off.assert_called_once()

class RadioTests(unittest.TestCase):
    def test_external_only_keying_and_release(self):
        ctl=Mock();config={'enabled':True,'role':'ptt'};seq=Mock(config=config);seq.before_ptt.return_value=True
        on,off=keying_callbacks(ctl,'外部接続',seq,lambda:True)
        self.assertTrue(on());self.assertTrue(ctl.external_transmitting);self.assertTrue(off());self.assertFalse(ctl.external_transmitting)
        ctl.set_ptt.assert_not_called();seq.after_ptt.assert_called_once()
    def test_external_role_mismatch_rejected(self):
        with self.assertRaises(ValueError):keying_callbacks(Mock(),'外部接続',Mock(config={'enabled':False}),lambda:True)
        with self.assertRaises(ValueError):keying_callbacks(Mock(),'CI-V',Mock(config={'enabled':True,'role':'ptt'}),lambda:True)
    def test_prekey_preserved(self):
        ctl=Mock();ctl.set_ptt.return_value=True;seq=Mock(config={'enabled':True,'role':'prekey'});seq.before_ptt.return_value=True
        on,off=keying_callbacks(ctl,'CI-V',seq,lambda:True);self.assertTrue(on());self.assertTrue(off());self.assertEqual(ctl.set_ptt.call_args_list[0].args,(True,));seq.after_ptt.assert_called_once()
    def test_roster_and_addresses(self):
        self.assertEqual(RIG_MODELS['IC-729'],0x3a);self.assertEqual(RIG_MODELS['IC-756PROII'],0x64)
        self.assertEqual(RIG_MODELS['IC-7760'],0xb2);self.assertEqual(len(ICOM_EXTERNAL_PTT),29)
        from psrtty.hamlib_radio import HAMLIB_MODELS
        self.assertEqual(HAMLIB_MODELS['FT-857 / FT-857D'][0],1022)
    def test_old_four_byte_frequency(self):
        ctl=CIVController(4,model='IC-735');ctl.ser=Mock();ctl.status=CIVStatus(True)
        with patch.object(ctl,'_read_response',return_value=bytes.fromhex('FE FE E0 04 03 00 00 07 00 FD')):
            self.assertEqual(ctl.read_frequency(),70000)
        ctl.external_transmitting=False
        with patch.object(ctl,'_read_response',return_value=bytes.fromhex('FE FE E0 04 FB FD')):
            self.assertTrue(ctl.set_frequency(7100000))
            frame=ctl.ser.write.call_args.args[0];self.assertEqual(frame[4],5);self.assertEqual(len(frame[5:-1]),4)
    def test_no_civ_ptt_for_group3(self):
        for model in ICOM_EXTERNAL_PTT:
            ctl=CIVController(RIG_MODELS[model],model=model);ctl.ser=Mock();ctl.status=CIVStatus(True)
            self.assertFalse(ctl.set_ptt(True));ctl.ser.write.assert_not_called()
    def test_added_strings_have_english(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('ui/direct_tx.py','ui/shortcut_guide.py','radio_support.py','tx_keying.py','live_tx.py'):
            for node in ast.walk(ast.parse((root/'psrtty'/name).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args and isinstance(node.args[0],ast.Constant):
                    s=node.args[0].value
                    if any('\u3000'<=c<='\u9fff' for c in s):self.assertTrue(s in TEXT,s)

from tests import test_ui_v02 as fixture
from PySide6.QtGui import QTextCursor
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from psrtty.ui.settings_dialog import SettingsDialog

class UI109Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    pump=fixture.UITests.pump
    def test_direct_buttons_pending_color_and_two_lines(self):
        w=self.window;w._open_direct();d=w.direct_window
        d.auto.setChecked(False);d.editor.setPlainText('CQ\nTEST\nTHIRD')
        self.assertEqual(d.last_text,'CQ\nTEST')
        c=QTextCursor(d.editor.document());c.setPosition(1)
        self.assertEqual(c.charFormat().foreground().color().name(),'#8899af')
        d.session=LiveText(d.last_text,0);d.progress(0,2,'Q')
        c.setPosition(1);self.assertEqual(c.charFormat().foreground().color().name(),'#000000')
        d.finished()
    def test_focus_only_from_main_then_f11_f12(self):
        w=self.window;w._open_direct();d=w.direct_window
        with patch('psrtty.ui.main_window.QApplication.activeWindow',return_value=w),patch.object(d,'focus_input') as focus,patch.object(d,'toggle') as toggle,patch.object(d,'replay') as replay:
            w._direct_key(11);w._direct_key(12);self.assertEqual(focus.call_count,2);toggle.assert_not_called();replay.assert_not_called()
        with patch('psrtty.ui.main_window.QApplication.activeWindow',return_value=d),patch.object(d,'toggle') as toggle,patch.object(d,'replay') as replay:
            w._direct_key(11);w._direct_key(12);toggle.assert_called_once();replay.assert_called_once()
        d.close()
        with patch.object(d,'focus_input') as focus:w._direct_key(12);focus.assert_not_called()
    def test_toggle_alias_and_no_repeat(self):
        w=self.window
        keys={s.key().toString():s for s in w.shortcuts}
        for key in ('Ctrl+F12','Shift+F12','F11','F12'):
            self.assertFalse(keys[key].autoRepeat());self.assertEqual(keys[key].context(),Qt.ApplicationShortcut)
        keys['Ctrl+F12'].activated.emit();self.assertTrue(w.direct_window.isVisible())
        keys['Shift+F12'].activated.emit();self.assertFalse(w.direct_window.isVisible())
    def test_clear_stops_and_close_stops(self):
        w=self.window;w._open_direct();d=w.direct_window;d.auto.setChecked(False);d.editor.setPlainText('CQ')
        with patch.object(w,'_stop_tx') as stop:
            d.clear();self.assertEqual(d.last_text,'');stop.assert_called_once()
            d.close();self.assertEqual(stop.call_count,2)
    def test_main_1tx_switch_and_clear(self):
        w=self.window;self.assertEqual(w.send_button.text(),'1TX')
        w.active_tx_id=1;w._set_radio_controls();self.assertEqual(w.send_button.text(),'STOP')
        with patch.object(w,'_stop_tx') as stop:w._manual_button();stop.assert_called_once()
        w.active_tx_id=None;w.manual_tx.setText('CQ')
        with patch.object(w,'_stop_tx') as stop:w._clear_manual();stop.assert_called_once();self.assertEqual(w.manual_tx.text(),'')
    def test_signal_idle_retains_then_loss_finalizes(self):
        w=self.window;w.rx_buffer='CQ';w.rx_last_char_time=time.monotonic()-3;w.audio.decoder.last_signal_time=time.monotonic()
        with patch.object(w,'_finalize_rx_card') as final:
            w._check_rx_idle();final.assert_not_called()
            w.audio.decoder.last_signal_time=0;w._check_rx_idle();final.assert_called_once()
    def test_nonmodal_bilingual_guide(self):
        w=self.window;configure('en');w._guide_shortcuts()
        self.assertEqual(w.shortcut_window.windowTitle(),'Keyboard shortcut guide');self.assertFalse(w.shortcut_window.isModal())
        w._open_direct();self.assertEqual(w.direct_window.windowTitle(),'Direct TX');self.assertEqual(w.direct_window.clear_button.text(),'Clear')
        configure('ja')
    def test_group3_settings_note_role_and_saved_enum(self):
        d=SettingsDialog(self.store,self.window)
        d.rig.setCurrentIndex(d.rig.findData('IC-729'))
        self.assertIn('外部接続',d.port_note.text());self.assertIn('#075aa6',d.port_note.styleSheet())
        self.assertFalse(d.auto_mode.isChecked());self.assertEqual(d._radio_values()['ptt'],'外部接続')
        d.external_role.setCurrentIndex(d.external_role.findData('ptt'))
        self.assertEqual(d._external_values()['role'],'ptt');d.reject()
    def test_committed_prefix_cannot_be_edited(self):
        w=self.window;w._open_direct();d=w.direct_window;d.auto.setChecked(False);d.editor.setPlainText('CQ TEST')
        d.session=LiveText(d.last_text,0);d.session.position=3;w.active_tx_id=42
        d.editor.setPlainText('XX TEST');self.assertEqual(d.last_text,'CQ TEST')
        w.active_tx_id=None;d.finished()
    def test_live_history_uses_actual_characters(self):
        w=self.window;s=LiveText('CQ TEST',0);s.records=['C','Q'];w.live_session=s;w.active_tx_id=42
        with patch.object(w,'_add_card') as card,patch.object(w.printer,'submit') as printed:
            w._tx_finished(False,'stop',42)
            w.transcript.append.assert_any_call('TX CQ');card.assert_called_once_with('CQ','TX');printed.assert_not_called()
    def test_existing_profiles_add_role_without_losing_ports(self):
        import tempfile,json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'config.json';path.write_text(json.dumps({'external':{'enabled':True,'com_port':'COM9','line':'DTR','delay_seconds':.7}}),encoding='utf-8')
            store=ConfigStore(path,Path(td)/'macros.json')
            self.assertEqual(store.data['external']['role'],'prekey');self.assertEqual(store.data['external']['com_port'],'COM9')
