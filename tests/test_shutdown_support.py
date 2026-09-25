import time
import unittest
from unittest.mock import patch
from tests.test_ui_v02 import UITests as _Fixture
from tests.shutdown_support import close_and_wait


class ShutdownSupportTests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_slow_audio_shutdown_finishes_backup_before_cleanup(self):
        self.pump(.05)
        visited=[]
        def backup(folder):
            self.assertTrue(folder.is_dir())
            visited.append(folder)
            return None
        original=self.window.audio.stop_input
        def slow():
            time.sleep(.3)
            return original()
        with patch.object(self.window.audio,'stop_input',side_effect=slow), patch('psrtty.backup.create_log_backup',side_effect=backup):
            started=time.monotonic();close_and_wait(self.window,self.app)
        self.assertGreaterEqual(time.monotonic()-started,.3)
        self.assertEqual(visited,[self.paths['logdata']])
        self.assertTrue(self.window.exit_backup_done)
        self.assertTrue(self.paths['logdata'].exists())
        self.assertFalse(self.dialog_guard.events)

del _Fixture
