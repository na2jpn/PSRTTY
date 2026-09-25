import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, Mock
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.config import ConfigStore
import json

class UI71Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def prepare(self):
        w=self.window;w.radio=Mock();w.radio.status.connected=True;w.current_freq_hz=21090000
        w.qsos=[];w.auto_log.setChecked(True);w.adif.append.return_value=Path('test.adi')
        return w

    def test_text_trigger_macro_manual_boundary_and_once(self):
        w=self.prepare()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            for text in ('TU 73','TU73','tu 73 JH1HST','RRR TU\n73 DE JH1HST'):
                for macro in (True,False):
                    w.q_call.setText('JQ7FIU');w.adif.append.reset_mock()
                    if macro:
                        w.store.macros[8].update(text=text,completes_qso=False);w._send_macro(8)
                    else:w.manual_tx.setText(text);w._send_manual()
                    token=w.active_tx_id;w.adif.append.assert_not_called()
                    w._tx_finished(True,'OK',token);w._tx_finished(True,'OK',token)
                    w.adif.append.assert_called_once();self.assertFalse(w.q_datetime.manual.isChecked())
            for text in ('TU 730','XTU73','TU73ABC','TU','73','CQ TEST'):
                w.adif.append.reset_mock();w.q_call.setText('JQ7FIU')
                w.store.macros[8].update(text=text,completes_qso=True)
                w._send_macro(8);w._tx_finished(True,'OK',w.active_tx_id)
                w.adif.append.assert_not_called()

    def test_empty_call_stop_failure_offline_and_checkbox(self):
        w=self.prepare()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            for condition in ('empty','stop','failed','unchecked'):
                w.adif.append.reset_mock();w.q_call.setText('' if condition=='empty' else 'JQ7FIU')
                w.radio.status.connected=condition!='offline';w.offline_tx.setChecked(True)
                w.auto_log.setChecked(condition!='unchecked')
                w._manual_request('TU73');token=w.active_tx_id
                if condition=='stop':w._stop_tx()
                w._tx_finished(condition!='failed','error' if condition=='failed' else 'OK',token)
                w.adif.append.assert_not_called()
                if condition=='empty':self.assertIn('CALL',w.statusBar().currentMessage())

    def test_clock_blink_midnight_manual_and_no_revision(self):
        w=self.window;clock=w.q_datetime;rev=w.qso_revision
        with patch('psrtty.ui.qso_datetime.datetime') as dt,patch('psrtty.ui.qso_datetime.time.monotonic') as mono:
            dt.now.return_value=datetime(2026,9,24,23,59,59);mono.return_value=clock._blink_start
            clock._tick();self.assertEqual(clock.time.text(),'23:59');self.assertTrue(clock.date.isReadOnly())
            mono.return_value=clock._blink_start+2;clock._tick();self.assertEqual(clock.time.text(),'23 59')
            self.assertEqual(clock.text(),'2026-09-24 23:59')
            dt.now.return_value=datetime(2026,9,25,0,0,1);mono.return_value=clock._blink_start+4
            clock._tick();self.assertEqual(clock.date.text(),'2026-09-25');self.assertEqual(clock.time.text(),'00:00')
            self.assertEqual(w.qso_revision,rev)
            clock.manual.setChecked(True);clock.time.setText('12:34');clock._tick()
            self.assertEqual(clock.time.text(),'12:34');self.assertFalse(clock.time.isReadOnly())
            clock.clear();self.assertEqual(clock.time.text(),'00:00');self.assertFalse(clock.manual.isChecked())

    def test_auto_clock_during_tx_and_actual_completion_timestamp(self):
        w=self.prepare();w.q_call.setText('JQ7FIU')
        with patch.object(w.audio,'send_text',return_value=(True,'OK')),patch('psrtty.ui.main_window.datetime') as dt:
            now=datetime(2026,9,25,0,0,42,tzinfo=timezone.utc);dt.now.return_value=now
            w._manual_request('TU73');revision=w.qso_revision
            w.q_datetime._tick();self.assertEqual(w.qso_revision,revision)
            w._tx_finished(True,'OK',w.active_tx_id)
        self.assertEqual(w.adif.append.call_args.args[0].when_utc,now)

    def test_saved_sq_retained_and_fresh_default_four(self):
        root=Path(self.tmp.name);cfg=root/'sq.json';mac=root/'mac.json'
        with patch('psrtty.config.ensure_runtime_dirs',return_value=self.paths):
            self.assertEqual(ConfigStore(cfg,mac).data['ui']['decode_sq'],4)
            for value in (0,2,7):
                cfg.write_text(json.dumps({'ui':{'decode_sq':value}}))
                self.assertEqual(ConfigStore(cfg,mac).data['ui']['decode_sq'],value)

del _Fixture
