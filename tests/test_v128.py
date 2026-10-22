"""Regression tests for 1.28 lifecycle, logging, migration and mode linkage."""
import copy
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from psrtty import diagnostics as diag,i18n
from psrtty.club_database import migrate_clubs,load_clubs
from psrtty.civ import CIVController,CIVStatus
from tests.test_ui_v02 import UITests as _Fixture

class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.old=diag._directory;diag.configure(self.root/'var/diagnostics')
    def tearDown(self):diag._directory=self.old;self.tmp.cleanup()
    def test_rotation_three_total_and_preserves_latest(self):
        with patch.object(diag,'MAX_BYTES',200):
            for n in range(20):diag.event('app',str(n)+'x'*80)
        files=list((self.root/'var/diagnostics').glob('app.log*'))
        self.assertEqual(len(files),3);self.assertTrue(all(p.stat().st_size<=200 for p in files))
        self.assertIn('19xxx',(self.root/'var/diagnostics/app.log').read_text(encoding='utf-8'))
    def test_global_cap_retains_each_latest(self):
        d=self.root/'var/diagnostics'
        with patch.object(diag,'MAX_BYTES',200),patch.object(diag,'MAX_TOTAL_BYTES',1800):
            for c in diag.CATEGORIES:
                for n in range(5):diag.event(c,'x'*70)
        self.assertLessEqual(sum(p.stat().st_size for p in d.iterdir()),1800)
        self.assertTrue(all((d/(c+'.log')).exists() for c in diag.CATEGORIES))
    def test_last_existing_archive_survives_even_over_cap(self):
        d=self.root/'var/diagnostics';last=d/'radio.log.2';last.write_bytes(b'x'*400)
        with patch.object(diag,'MAX_TOTAL_BYTES',50):diag.configure(d)
        self.assertTrue(last.exists())
    def test_never_deletes_qso_transcripts_backups_or_unknown_files(self):
        names=['logdata/20261021_all.txt','logdata/all.adi','var/backups/test.zip','var/diagnostics/notes.log.2']
        for n in names:
            p=self.root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'keep')
        with patch.object(diag,'MAX_TOTAL_BYTES',1):
            for _ in range(10):diag.event('app','x'*500)
        self.assertTrue(all((self.root/n).read_bytes()==b'keep' for n in names))
    def test_traceback_and_threads_are_readable_utf8(self):
        def run():
            try:raise RuntimeError('試験エラー')
            except RuntimeError as e:diag.event('ry_skimmer','DLL stage',error=e)
        t=threading.Thread(target=run);t.start();t.join()
        s=(self.root/'var/diagnostics/ry_skimmer.log').read_text(encoding='utf-8')
        self.assertIn('Traceback',s);self.assertIn('試験エラー',s)
    def test_logging_failure_does_not_interrupt_operation(self):
        with patch.object(Path,'mkdir',side_effect=PermissionError):diag.event('tx','PTT OFF')
    def test_language_errors_use_settings_category(self):
        i18n.configure('ja',self.root/'missing')
        self.assertIn('Language',(self.root/'var/diagnostics/settings.log').read_text(encoding='utf-8'));i18n.configure('ja')

class MigrationTests(unittest.TestCase):
    def test_migration_preserves_active_and_conflicting_edits(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'club_db.csv').write_text('number,name\n001,Original\n', encoding='utf-8');(r/'config').mkdir()
            (r/'config/club_db.csv').write_text('number,name\n002,Other\n', encoding='utf-8');migrate_clubs(r)
            self.assertFalse((r/'club_db.csv').exists());self.assertEqual(load_clubs(r)[0],[('001','Original')])
            b=list((r/'config').glob('club_db.csv.pre-128-*'));self.assertEqual(len(b),1);self.assertIn('Other',b[0].read_text(encoding='utf-8'))
            before=(r/'config/club_db.csv').read_bytes();migrate_clubs(r);self.assertEqual(before,(r/'config/club_db.csv').read_bytes())
    def test_failed_copy_retains_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);p=r/'club_db.csv';p.write_bytes(b'custom')
            with patch('psrtty.club_database.os.replace',side_effect=PermissionError):
                with self.assertRaises(PermissionError):migrate_clubs(r)
            self.assertEqual(p.read_bytes(),b'custom')
    def test_new_manifest_rejects_loose_root_file(self):
        from psrtty.updater import create_manifest
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);(r/'psrtty.exe').write_bytes(b'MZfake');(r/'club_db.csv').write_text('bad root', encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'root'):create_manifest(r,'1.28')
    def test_distribution_uses_folders_and_omits_club_payload(self):
        from package_release import build_distribution
        from psrtty.updater import inspect_zip
        import zipfile
        with tempfile.TemporaryDirectory() as td:
            r=Path(td);exe=r/'test.exe';exe.write_bytes(b'MZfake');archive=build_distribution(exe,r/'out');info=inspect_zip(archive,'1.27')
            with zipfile.ZipFile(archive) as z:
                root=info['prefix'];loose=[x.filename[len(root):] for x in z.infolist() if not x.is_dir() and '/' not in x.filename[len(root):]]
                self.assertEqual(loose,['psrtty.exe']);self.assertFalse(any('club_db' in n for n in z.namelist()))
                self.assertIn(root+'lib/iq/psrtty-extio32.exe',z.namelist())
            # Prove exclusions are unused by the runtime in a fresh interpreter.
            import ast,subprocess,sys
            spec=ast.parse(Path('psrtty.spec').read_text(encoding='utf-8'))
            excluded=next(ast.literal_eval(k.value) for node in ast.walk(spec) if isinstance(node,ast.Call) for k in node.keywords if k.arg=='excludes')
            code="""import sys,json,importlib.abc
blocked=json.loads(sys.argv[1])
class Block(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if any(name==x or name.startswith(x+'.') for x in blocked):raise ModuleNotFoundError(name)
sys.meta_path.insert(0,Block())
from psrtty.ui.main_window import MainWindow
from psrtty.ry_skimmer import SkimmerEngine
import numpy as np
SkimmerEngine().feed(np.zeros(10000,dtype=np.complex64),48000,14090000)
"""
            subprocess.run([sys.executable,'-c',code,__import__('json').dumps(excluded)],check=True,timeout=30)

class ModeCommandTests(unittest.TestCase):
    def ctl(self):
        c=CIVController(0x94,model='IC-7300');c.ser=Mock();c.status=CIVStatus(connected=True);return c
    def test_link_omits_filter_and_never_keys(self):
        c=self.ctl();ack=bytes.fromhex('FE FE E0 94 FB FD')
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_operating_mode',side_effect=['LSB','LSB-D']),patch.object(c,'_read_response',return_value=ack),patch.object(c,'set_ptt') as ptt:
            self.assertTrue(c.set_linked_mode('LSB-D'))
        self.assertEqual([x.args[0] for x in c.ser.write.call_args_list],[c._frame(0x26,0,0,1)]);ptt.assert_not_called()
    def test_same_mode_no_write_and_tx_blocks(self):
        c=self.ctl()
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_operating_mode',return_value='USB-D'):self.assertTrue(c.set_linked_mode('USB-D'))
        c.ser.write.assert_not_called()
        with patch.object(c,'read_transmitting',return_value=True):self.assertFalse(c.set_linked_mode('LSB-D'))
        c.ser.write.assert_not_called()
    def test_legacy_echoes_destination_filter_not_fil1(self):
        c=self.ctl();ack=bytes.fromhex('FE FE E0 94 FB FD');nak=bytes.fromhex('FE FE E0 94 FA FD');f=bytes.fromhex('FE FE E0 94 04 00 03 FD')
        with patch.object(c,'read_transmitting',return_value=False),patch.object(c,'read_operating_mode',side_effect=['USB-D','LSB-D']),patch.object(c,'_read_response',side_effect=[nak,ack,f,ack]):self.assertTrue(c.set_linked_mode('LSB-D'))
        self.assertEqual(c.ser.write.call_args_list[-1].args[0],c._frame(0x1A,6,1,3))

class UI128Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__);setUp=_Fixture.setUp;tearDown=_Fixture.tearDown;pump=_Fixture.pump
    def skimmer(self):
        from psrtty.ui.ry_windows import SkimmerWindow
        self.window.ry_skimmer_window=SkimmerWindow(self.window);self.window.ry_skimmer_window.timer.stop();return self.window.ry_skimmer_window
    def setup(self):
        from psrtty.ui.ry_windows import SkimmerSetup
        d=SkimmerSetup(self.window);d.choose('extio');return d
    def test_shared_checkbox_persistence_and_save_failure(self):
        from psrtty.ui.ry_windows import RadarWindow
        s=self.skimmer();r=RadarWindow(self.window);self.window.ry_radar_window=r;r.timer.stop()
        self.assertTrue(s.mode_link.isChecked());self.assertTrue(r.mode_link.isChecked());r.mode_link.setChecked(False);self.assertFalse(s.mode_link.isChecked())
        self.store.save.side_effect=OSError('disk full');s.mode_link.setChecked(True)
        self.assertFalse(s.mode_link.isChecked());self.assertFalse(r.mode_link.isChecked());self.store.save.side_effect=None
    def test_invalid_dll_keeps_setup_open_red(self):
        d=self.setup();d.show();d.dll.setText('missing.dll');d.accept_options()
        self.assertTrue(d.isVisible());self.assertIsNone(d.options);self.assertIn('#c62828',d.note.styleSheet())
    def test_save_failure_retains_settings_and_reports_cause(self):
        d=self.setup();before=copy.deepcopy(self.store.data['ui'].get('ry_skimmer_inputs',{}));d.dll.setText(__file__);self.store.save.side_effect=PermissionError('denied')
        with patch('psrtty.ry_iq.pe_bits',return_value=64):d.accept_options()
        self.assertIsNone(d.options);self.assertIn('denied',d.note.text());self.assertEqual(self.store.data['ui']['ry_skimmer_inputs'],before);self.store.save.side_effect=None
    def test_save_success_closes_setup(self):
        d=self.setup();d.dll.setText(__file__);d.show()
        with patch('psrtty.ry_iq.pe_bits',return_value=32):d.accept_options()
        self.assertEqual(d.result(),1);self.assertFalse(d.isVisible());self.assertEqual(d.options['method'],'extio')
    def test_configure_reveals_and_schedules_start(self):
        s=self.skimmer();d=Mock();d.exec.return_value=1;d.options={'method':'extio'}
        with patch('psrtty.ui.ry_windows.SkimmerSetup',return_value=d),patch.object(s,'reveal') as reveal,patch.object(s,'start_input') as start:
            s.configure();self.pump(.03);reveal.assert_called_once();start.assert_called_once()
    def test_constructor_failure_red_and_retryable(self):
        s=self.skimmer();s.options=dict(method='extio',dll='x',center=14.09,span=20000,reverse=False)
        with patch('psrtty.ry_skimmer.SkimmerWorker',side_effect=RuntimeError('DSP failed')):s.start_input()
        self.assertIn('DSP failed',s.status.text());self.assertIn('#c62828',s.status.styleSheet());self.assertTrue(s.start.isEnabled())
    def test_async_error_persists_and_iq_timeout_cleans_up(self):
        s=self.skimmer();s.options=dict(method='extio',dll='x',center=14.09,span=20000,reverse=False);source=Mock();source.start.side_effect=OSError('native DLL failed')
        with patch('psrtty.ry_iq.ExtIOInput',return_value=source):s.start_input();self.pump(.1)
        self.assertIn('native DLL failed',s.status.text());self.assertIsNone(s.input);text=s.status.text();s.refresh();self.assertEqual(text,s.status.text())
        source.start.side_effect=None
        with patch('psrtty.ry_iq.ExtIOInput',return_value=source):s.start_input();self.pump(.1)
        self.assertFalse(s.first_iq);self.assertIn(i18n.tr('ry.wait_iq'),s.status.text());s.last_data=time.monotonic()-16;s.refresh()
        self.assertIsNone(s.input);self.assertTrue(s.failure);self.assertIn('#c62828',s.status.styleSheet())
    def test_first_samples_required_for_receiving(self):
        s=self.skimmer();s.worker=Mock(samples=4096,error=None,dropped=0);s.worker.engine.channels=[];s.refresh()
        self.assertTrue(s.first_iq);self.assertIn(i18n.tr('ry.receiving'),s.status.text());s.worker=None
    def test_mode_queue_follows_profile_and_can_be_off(self):
        from psrtty.ui.control_window import ControlWindow
        w=self.window
        with patch.object(w.rit_service,'ready',return_value=True),patch.object(ControlWindow,'ready',return_value=True),patch.object(ControlWindow,'tick'):
            for method,mode in [('afsk','USB-D'),('afsk','LSB'),('fsk','RTTY-R')]:
                w.store.data['radio']['tx_method']=method;w.store.data['advanced']['data_mode']=mode;w.store.data['fsk']['mode']=mode;w._ry_tune(7078000)
                self.assertEqual(w.control_window.pending,7078000);self.assertEqual(w.control_window.mode_pending,mode)
            w.store.data['ui']['ry_mode_link']=False;w._ry_tune(7079000);self.assertIsNone(w.control_window.mode_pending)
    def test_eight_languages_controls_history(self):
        from psrtty.ui.ry_windows import RadarWindow
        for code in i18n.LANGUAGES:
            i18n.configure(code);r=RadarWindow(self.window);self.assertNotIn('ry.',r.mode_link.text());self.assertTrue(r.mode_link.toolTip());r.close()
            self.assertTrue(i18n.tr('history.body').startswith('2026-10-23  Ver1.29'))
        i18n.configure('ja')

del _Fixture
