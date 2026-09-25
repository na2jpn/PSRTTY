import unittest
from unittest.mock import patch
from tests.test_ui_v02 import UITests as _Fixture
from tests.test_v60 import FakeOutput
from psrtty.adif import ADIFLog

class UI72Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_offline_real_audio_worker_and_adif_macro_manual_stop(self):
        w=self.window
        with patch('psrtty.adif.ensure_runtime_dirs',return_value=self.paths):w.adif=ADIFLog()
        w.qsos=[];w.radio=None;w.offline_tx.setChecked(True);w.auto_log.setChecked(True)
        with patch('psrtty.audio_engine.sd') as sd,patch('psrtty.audio_engine.resolve_device',return_value=None):
            for mode in ('macro','manual','stop'):
                w.q_call.setText('JQ7FIU');stream=FakeOutput();sd.OutputStream.return_value=stream
                if mode=='macro':w._send_macro(3)
                else:w.manual_tx.setText('TU73');w._send_manual()
                self.assertTrue(stream.entered.wait(2))
                self.assertEqual(len(w.adif.load_recent(limit=None)),0 if mode=='macro' else (1 if mode=='manual' else 2))
                if mode=='stop':w._stop_tx()
                stream.release.set();w.audio.wait_tx();self.pump(.05)
                self.assertIsNone(w.active_tx_id)
                records=w.adif.load_recent(limit=None)
                self.assertEqual(len(records),1 if mode=='macro' else 2)
                self.assertEqual(w.latest_box.footer.text(),f'ログ合計 {len(records)}件')
                self.assertIsNone(records[-1].freq_hz)
                self.assertEqual(records[-1].call,'JQ7FIU')
                self.assertFalse(w.q_datetime.manual.isChecked())
        # No invented frequency or band for offline QSOs.
        raw=next(self.paths['logdata'].glob('*.adi')).read_text()
        self.assertNotIn('<FREQ:',raw);self.assertNotIn('<BAND:',raw)

del _Fixture
