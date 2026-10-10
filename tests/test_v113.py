"""Direct TX continuation, real worker idle deadlines and help/About controls."""
import json
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import numpy as np
from PySide6.QtGui import QColor, QFont, QFontInfo, QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from psrtty import i18n, __version__
from psrtty.live_tx import LiveText, start_live
from psrtty.audio_engine import AudioEngine
from psrtty.config import DEFAULT_CONFIG
from psrtty.decoder import RTTYDecoder
from psrtty.ui.about_dialog import AboutDialog, about_html
from tests import test_ui_v02 as fixture

ROOT=Path(__file__).resolve().parents[1]

class Idle113Tests(unittest.TestCase):
    def test_input_at_16_seconds_survives_2_second_deadline(self):
        s=LiveText('A',.5,True);s.times=[0.]
        self.assertEqual(s.next_char(.5),(0,0,'A'))
        self.assertFalse(s.idle_expired(1.))  # audio finished at t=1
        with patch('psrtty.live_tx.time.monotonic',return_value=2.6):
            self.assertTrue(s.update('AB'))  # append after 1.6 s idle
        self.assertIsNone(s.next_char(3.))
        self.assertFalse(s.idle_expired(3.))  # old deadline is t=3
        self.assertEqual(s.next_char(3.1),(0,1,'B'))
        self.assertFalse(s.idle_expired(3.3))  # B finished; fresh deadline
        self.assertFalse(s.idle_expired(5.29))
        self.assertTrue(s.idle_expired(5.31))

    def test_correction_changes_only_uncommitted_tail(self):
        s=LiveText('AB',.5);s.times=[0.,0.]
        self.assertEqual(s.next_char(.5),(0,0,'A'))
        with patch('psrtty.live_tx.time.monotonic',return_value=.6):
            self.assertTrue(s.update('AC'))
        self.assertIsNone(s.next_char(1.09))
        self.assertEqual(s.next_char(1.1),(0,1,'C'))
        self.assertFalse(s.update('XC'))

    def run_audio(self, append=False, offline=False, position=0, text='VVV', delay=.5):
        # Drive monotonic time from audio samples, with no wall-clock sleeps.
        # This exercises the actual threaded encoder, output drain and PTT path.
        clock=[0.];blocks=[];sent_at=[];added=[False]
        engine=AudioEngine();s=LiveText(text,delay,True);s.position=position;s.times=[0.]*len(text)
        output=Mock();sd=Mock();sd.OutputStream.return_value=output
        def write(data):
            blocks.append(data.copy());clock[0]+=len(data)/engine.sample_rate
            if append and len(sent_at)==3 and not added[0] and clock[0]>=sent_at[-1]+1.6:
                added[0]=True;self.assertTrue(s.update(text+'VVV'))
        output.write.side_effect=write
        progress=Mock(side_effect=lambda *args: sent_at.append(clock[0]))
        done=Mock();on=Mock(return_value=True);off=Mock(return_value=True)
        with patch('psrtty.live_tx.time.monotonic',side_effect=lambda:clock[0]),patch('psrtty.live_tx.resolve_device',return_value=1):
            ok,_=start_live(engine,sd,s,1,DEFAULT_CONFIG['advanced'],.3,on,off,done,progress,offline)
            self.assertTrue(ok)
            engine._tx_thread.join(5.)
            if engine._tx_thread.is_alive():
                engine._tx_cancel.set();engine._tx_thread.join(1.)
                self.fail('audio worker did not auto-stop')
        self.assertTrue(done.call_args.args[0]);self.assertFalse(engine._tx_active)
        output.stop.assert_called_once();output.abort.assert_not_called();output.close.assert_called_once()
        if offline:on.assert_not_called();off.assert_not_called()
        else:on.assert_called_once();off.assert_called_once()
        self.assertGreaterEqual(clock[0]-sent_at[-1],2.)
        self.assertLess(clock[0]-sent_at[-1],2.2)
        decoded=[];RTTYDecoder(on_char=decoded.append).feed(np.concatenate(blocks).reshape(-1))
        self.assertEqual(''.join(decoded),''.join(s.records))
        return s,sent_at

    def test_worker_auto_stops_drains_and_releases_ptt(self):
        s,_=self.run_audio();self.assertEqual(''.join(s.records),'VVV')

    def test_worker_append_at_16_seconds_sends_after_grace_then_stops(self):
        s,t=self.run_audio(append=True)
        self.assertEqual(''.join(s.records),'VVVVVV')
        self.assertGreaterEqual(t[3]-t[2],2.1)

    def test_offline_audio_also_auto_stops_without_ptt(self):
        s,_=self.run_audio(offline=True);self.assertEqual(''.join(s.records),'VVV')

    def test_worker_resumes_new_tail_only(self):
        s,_=self.run_audio(text='VVVVVV',position=3)
        self.assertEqual(''.join(s.records),'VVV')

class UI113Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    pump=fixture.UITests.pump

    def direct(self):
        self.window._open_direct();d=self.window.direct_window
        d.auto.setChecked(False);return d

    def mark_sent(self,d,text,count):
        d.editor.setPlainText(text);d.session=LiveText(text,0);d.session.position=count
        d.progress(0,count,text[count-1]);d.finished();d.editor.moveCursor(QTextCursor.End)

    def fmt(self,d,pos):
        c=QTextCursor(d.editor.document());c.setPosition(pos);c.movePosition(QTextCursor.NextCharacter,QTextCursor.KeepAnchor)
        return c.charFormat()

    def test_black_bold_pending_normal_and_one_point_larger(self):
        d=self.direct();self.mark_sent(d,'VVVABC',3)
        self.assertEqual(self.fmt(d,0).foreground().color(),QColor('black'))
        self.assertEqual(self.fmt(d,0).fontWeight(),QFont.Bold)
        self.assertEqual(self.fmt(d,3).fontWeight(),QFont.Normal)
        self.assertEqual(self.fmt(d,3).foreground().color().name(),'#8899af')
        self.assertAlmostEqual(d.editor.font().pointSizeF(),QFontInfo(d.font()).pointSizeF()+1)

    def test_stop_then_append_keeps_sent_position_and_replay_resets(self):
        d=self.direct();self.mark_sent(d,'VVV',3)
        QTest.keyClicks(d.editor,'VVV');self.assertEqual(d.last_text,'VVVVVV');self.assertEqual(d.sent,3)
        with patch.object(self.window,'_send_text',return_value=True) as send:
            d.start();s=send.call_args.kwargs['live_session'];self.assertEqual(s.position,3)
            self.assertEqual([s.next_char(1e12)[2] for _ in range(3)],['V']*3)
            self.assertIsNone(s.next_char(1e12))
            d.finished();d.replay();s=send.call_args.kwargs['live_session']
            self.assertEqual(s.position,0);self.assertEqual(d.sent,0)
            self.assertEqual(self.fmt(d,0).fontWeight(),QFont.Normal)
            self.assertEqual([s.next_char(1e12)[2] for _ in range(6)],['V']*6)
            d.finished()

    def test_sent_prefix_protected_after_stop_but_pending_can_change(self):
        d=self.direct();self.mark_sent(d,'VVVAB',3)
        d.editor.setPlainText('XXXAB');self.assertEqual(d.last_text,'VVVAB');self.assertEqual(d.sent,3)
        d.editor.setPlainText('VVVAC');self.assertEqual(d.last_text,'VVVAC');self.assertEqual(d.sent,3)

    def test_close_reopen_keeps_text_offset_and_bold(self):
        d=self.direct();self.mark_sent(d,'VVV',3)
        with patch.object(self.window,'_stop_tx') as stop:d.close();stop.assert_called_once()
        self.window._open_direct();self.assertIs(self.window.direct_window,d)
        self.assertEqual(d.last_text,'VVV');self.assertEqual(d.sent,3)
        self.assertEqual(self.fmt(d,0).fontWeight(),QFont.Bold)
        QTest.keyClicks(d.editor,'A');self.assertEqual(d.sent,3)
        self.assertEqual(self.fmt(d,3).fontWeight(),QFont.Normal)

    def test_input_after_idle_stop_claim_is_retained_and_resumed(self):
        d=self.direct();d.auto.setChecked(True);d.editor.setPlainText('VVV');d.timer.stop()
        s=LiveText('VVV',0);s.position=3;s.closing=True;d.session=s;self.window.active_tx_id=42
        d.progress(0,3,'V');d.editor.moveCursor(QTextCursor.End);QTest.keyClicks(d.editor,'A')
        self.window.active_tx_id=None;d.finished(True)
        self.assertEqual(d.last_text,'VVVA');self.assertEqual(d.sent,3);self.assertTrue(d.timer.isActive())
        d.timer.stop()

    def test_closed_window_and_failed_tx_do_not_restart(self):
        d=self.direct();d.auto.setChecked(True);d.editor.setPlainText('VVVA');d.timer.stop()
        s=LiveText('VVVA');s.closing=True;d.session=s;d.sent=3
        d.finished(False);self.assertFalse(d.timer.isActive())
        d.session=s;d.close();d.finished(True);self.assertFalse(d.timer.isActive())

    def test_help_separator_and_official_button_all_languages(self):
        actions=self.window.top_level_menus[-1].actions();index=actions.index(self.window.update_action)
        self.assertTrue(actions[index-1].isSeparator());self.assertTrue(actions[index+1].isSeparator())
        for code in i18n.LANGUAGES:
            i18n.configure(code);dialog=AboutDialog(self.window)
            self.assertIn(f'PSRTTY {__version__}',about_html())
            self.assertEqual(dialog.website_button.text(),i18n.tr('about.website'))
            with patch('psrtty.ui.about_dialog.QDesktopServices.openUrl',return_value=True) as opened:
                dialog.website_button.click();self.assertEqual(opened.call_args.args[0].toString(),'https://2jp.org/ps/psrtty/?')
            dialog.close()
        i18n.configure('ja')

    def test_version_and_localized_history(self):
        self.assertEqual(__version__,'1.14')
        for code in i18n.LANGUAGES:
            s=json.loads((ROOT/f'language/{code}.json').read_text(encoding='utf-8'))['strings']
            self.assertTrue(s['history.body'].startswith('2026-10-10  Ver1.14'))
            self.assertIn('2026-10-09  Ver1.12',s['history.body'])
            self.assertIn('0.5' if code not in ('ru','id','es') else '0,5',s['guide.9.body'])
