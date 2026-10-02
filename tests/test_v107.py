import ast
import copy
import json
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from psrtty.adif import QSORecord, export_adif
from psrtty.config import ConfigStore
from psrtty.hamlog_link import HamlogLink, LinkError, THW_ENTER, THW_SAVEBOX_OFF, input_fields
from psrtty.hamlib_radio import HAMLIB_MODELS, HamlibController
from psrtty.civ import CIVStatus
from psrtty.i18n import configure, tr, TEXT
from tests import test_ui_v02 as fixture
from tests.test_v106 import RadioLibrary


def qso():
    return QSORecord('JA1ABC', '579', '589', '001', '007', 'JH1HST', 14085000,
                     datetime(2026, 10, 2, 16, 1, 5, tzinfo=timezone.utc))


class FakeHamlog:
    title = 'Turbo HAMLOG/Win Ver5.48'
    target = 17
    def __init__(self):
        self.fields = [''] * 14
        self.commands = []
        self.saved = []
        self.fail_on = None
        self.mismatch = False
        self.stuck_save = False
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def request(self, command, text=None, reply=False):
        self.commands.append((command, text, reply))
        if command == self.fail_on: raise LinkError('timeout')
        if command == 115:
            result = list(self.fields)
            if self.mismatch and result[0]: result[5] = '7.040'
            return '\r\n' + '\r\n'.join(result) + '\r\n'
        if command == 101: return self.fields[0]
        if command == (18 | THW_SAVEBOX_OFF):
            if not self.stuck_save:
                self.saved.append(list(self.fields)); self.fields = [''] * 14
        elif command == (1 | THW_ENTER):
            self.fields[0] = text; self.fields[10:12] = ['太郎', '東京都']
        elif 1 <= command <= 14:
            self.fields[command - 1] = text
        else: raise AssertionError(command)
        return 999


class Hamlog107Tests(unittest.TestCase):
    def setUp(self):
        configure('en'); self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.api = FakeHamlog()
        self.link = HamlogLink(Path(self.tmp.name)/'journal.jsonl', lambda: self.api)
    def tearDown(self): configure('ja')
    def test_transfer_only_explicit_jst_rst_exchanges_and_no_save(self):
        self.link.transfer(qso())
        self.assertEqual(self.api.fields[:7], ['JA1ABC','26/10/03','01:01J','579','589','14.085','RTTY'])
        self.assertEqual(self.api.fields[12:14], ['SENT:001 RCVD:007','MYCALL:JH1HST'])
        self.assertEqual(self.api.saved, [])
        self.assertEqual(json.loads(self.link.journal.read_text(encoding='utf-8').splitlines()[-1])['state'], 'input_transferred')
    def test_auto_save_only_after_full_readback(self):
        self.link.transfer(qso(), True)
        self.assertEqual(len(self.api.saved), 1)
        commands = [c[0] for c in self.api.commands]
        self.assertEqual(commands[-3:], [115, 18 | THW_SAVEBOX_OFF, 101])
    def test_busy_draft_is_not_changed_or_marked_attempted(self):
        self.api.fields[0] = 'JA9XYZ'; before = list(self.api.fields)
        with self.assertRaises(LinkError): self.link.transfer(qso(), True)
        self.assertEqual(self.api.fields, before); self.assertFalse(self.link.journal.exists())
    def test_lookup_retains_unicode_and_allows_same_unedited_draft(self):
        result = self.link.lookup('ja1abc')
        self.assertEqual((result['name'], result['qth']), ('太郎', '東京都'))
        self.link.transfer(qso(), True)
        self.assertEqual(self.api.saved[0][10:12], ['太郎', '東京都'])
    def test_lookup_draft_changed_in_hamlog_is_protected(self):
        self.link.lookup('JA1ABC'); self.api.fields[12] = 'edited'
        with self.assertRaises(LinkError): self.link.transfer(qso(), True)
        self.assertEqual(self.api.fields[12], 'edited'); self.assertFalse(self.api.saved)
    def test_partial_timeout_is_not_retried_after_restart(self):
        self.api.fail_on = 4
        with self.assertRaises(LinkError): self.link.transfer(qso(), True)
        self.api.fail_on = None; self.api.fields = [''] * 14
        second = HamlogLink(self.link.journal, lambda: self.api)
        before = list(self.api.commands)
        with self.assertRaises(LinkError): second.transfer(qso(), True)
        self.assertEqual(before, self.api.commands); self.assertFalse(self.api.saved)
    def test_mismatched_frequency_cannot_auto_save(self):
        self.api.mismatch = True
        with self.assertRaises(LinkError): self.link.transfer(qso(), True)
        self.assertFalse(self.api.saved)
    def test_save_not_clearing_input_reports_uncertainty(self):
        self.api.stuck_save = True
        with self.assertRaises(LinkError): self.link.transfer(qso(), True)
        self.assertEqual(json.loads(self.link.journal.read_text(encoding='utf-8').splitlines()[-1])['state'], 'attempted')
    def test_invalid_qso_or_journal_io_error_never_writes_hamlog(self):
        invalid = qso(); invalid.freq_hz = None
        with self.assertRaises(LinkError): self.link.transfer(invalid, True)
        self.assertFalse(self.api.commands)
        with patch.object(self.link, '_journal', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): self.link.transfer(qso(), True)
        self.assertEqual([x[0] for x in self.api.commands], [115])
    def test_native_command_flags_protect_existing_record_edit_windows(self):
        from psrtty.hamlog_link import wire_command, THW_APPLIHWND, THW_SHUUSEI_WIN
        self.assertEqual(wire_command(115, True), 115 | THW_APPLIHWND)
        self.assertEqual(wire_command(1 | THW_ENTER), 1 | THW_ENTER | THW_SHUUSEI_WIN)
        self.assertEqual(wire_command(18 | THW_SAVEBOX_OFF), 18 | THW_SAVEBOX_OFF | THW_SHUUSEI_WIN)

    def test_reply_format_and_platform_errors(self):
        with self.assertRaises(LinkError): input_fields('bad')
        from psrtty.hamlog_link import Win32Transport
        with patch('psrtty.hamlog_link.sys.platform', 'linux'):
            with self.assertRaisesRegex(LinkError, 'Windows'): Win32Transport().__enter__()


class ZLog107Tests(unittest.TestCase):
    def export(self, record, profile):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'test.adi'; export_adif(path, [record], profile=profile)
            return path.read_text(encoding='utf-8')
    def test_serial_original_text_rst_and_utc_rollover(self):
        text = self.export(qso(), 'zlog')
        for field in ('<QSO_DATE:8>20261002','<TIME_ON:6>160105','<RST_SENT:3>579',
                      '<RST_RCVD:3>589','<STX:1>1','<SRX:1>7','<SRX_STRING:3>007','RCVD=007'):
            self.assertIn(field, text)
    def test_jarl_age_and_cqww_zone_state_remain_separate(self):
        q = qso(); q.rcvd = '09'
        self.assertIn('<AGE:1>9', self.export(q, 'zlog_jarl'))
        q.rcvd = '05 MA'; text = self.export(q, 'zlog_cqww')
        for field in ('<CQZ:1>5', '<STATE:2>MA', '<SRX_STRING:5>05 MA', 'RCVD=05 MA'):
            self.assertIn(field, text)
        self.assertNotIn('<CQZ:5>05 MA', text)
    def test_invalid_exchange_preserves_existing_destination(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'test.adi'; path.write_text('original', encoding='utf-8')
            for profile, exchange in [('zlog_cqww','41'),('zlog_jarl','05 MA')]:
                q = qso(); q.rcvd = exchange
                with self.assertRaises(ValueError): export_adif(path, [q], profile=profile)
                self.assertEqual(path.read_text(encoding='utf-8'), 'original')
    def test_standard_output_is_unchanged(self):
        from psrtty.adif import adif_header, adif_record
        self.assertEqual(self.export(qso(), 'standard').replace('\n','\r\n'), adif_header() + adif_record(qso()))


class Radio107Tests(unittest.TestCase):
    def ctl(self, model):
        ctl = HamlibController(model); ctl.lib = RadioLibrary(); ctl.handle = 3
        ctl.status = CIVStatus(connected=True); return ctl
    def test_nb_nr_all_listed_models_and_tx_guard(self):
        for model in HAMLIB_MODELS:
            ctl = self.ctl(model)
            for name in ('NB','NR'):
                self.assertIs(ctl.read_feature(name), False, model)
                self.assertTrue(ctl.set_feature(name, True), model)
            ctl.lib.tx = 1; before = list(ctl.lib.commands)
            self.assertFalse(ctl.set_feature('NB', False)); self.assertEqual(before, ctl.lib.commands)
    def test_yaesu_tables_and_mode_guards(self):
        for model in HAMLIB_MODELS:
            if not model.startswith('FT'): continue
            ctl = self.ctl(model); state = ctl.read_filter()
            self.assertTrue(ctl.set_filter(1200, state), model)
            if model in ('FT-710','FTDX10','FTDX101D','FTDX101MP','FTX-1'):
                self.assertIn((4000,'4000 Hz'), state['options'])
            ctl.lib.mode = 4
            if model == 'FTX-1':
                options = dict(ctl.read_filter()['options'])
                self.assertIn(2250, options); self.assertNotIn(2200, options)
            self.assertFalse(ctl.set_filter(1200, state))
    def test_kenwood_unimplemented_width_is_not_falsely_reported(self):
        for model in ('TS-890S','TS-990S'):
            ctl = self.ctl(model)
            self.assertIsNone(ctl.read_filter()); self.assertTrue(ctl.set_feature('NR', True))
    def test_ts590_width_preserves_low_cut_and_rejects_changed_low(self):
        ctl = self.ctl('TS-590SG'); lib = ctl.lib
        lib.high = 2400; lib.low = 300
        lib.rig_parse_level = lambda name: 1 if name == b'SLOPE_HIGH' else 2
        def getlevel(h,v,flag,out): out._obj.i = lib.high if flag == 1 else lib.low; return 0
        def setlevel(h,v,flag,value): self.assertEqual(flag,1); lib.high = value.i; return 0
        lib.rig_get_level = getlevel; lib.rig_set_level = setlevel
        state = ctl.read_filter(); self.assertEqual(state['value'], 2100)
        self.assertTrue(ctl.set_filter(1700,state)); self.assertEqual((lib.high,lib.low),(2000,300))
        lib.low = 100
        self.assertFalse(ctl.set_filter(1700,state)); self.assertEqual(lib.high,2000)


class UI107Tests(unittest.TestCase):
    setUpClass = classmethod(fixture.UITests.setUpClass.__func__)
    setUp = fixture.UITests.setUp; tearDown = fixture.UITests.tearDown; pump = fixture.UITests.pump
    def test_release_version_matches_title_about_config_adif_and_history(self):
        from psrtty import __version__
        from psrtty.config import DEFAULT_CONFIG
        from psrtty.adif import adif_header
        from psrtty.ui.about_dialog import ABOUT_TEXT, ABOUT_TEXT_EN
        from psrtty.update_history import HISTORY_TEXT
        from psrtty.update_history_en import HISTORY_TEXT_EN
        self.assertEqual(self.window.windowTitle(), f'PSRTTY {__version__}')
        self.assertEqual(DEFAULT_CONFIG['version'], __version__)
        for body in (ABOUT_TEXT, ABOUT_TEXT_EN):
            self.assertIn(f'PSRTTY {__version__}', body)
        self.assertIn(f'<PROGRAMVERSION:{len(__version__)}>{__version__}', adif_header())
        for history in (HISTORY_TEXT, HISTORY_TEXT_EN):
            self.assertIn(f'Ver{__version__}', history.splitlines()[0])

    def test_menus_guide_and_thanks_bilingual(self):
        from psrtty.ui.guide import GuideWindow
        from psrtty.ui.special_thanks_dialog import SpecialThanksDialog
        from psrtty.ui.integration_dialog import HamlogSettingsDialog, ZLogSettingsDialog
        self.assertEqual([a.text() for a in self.window.menuBar().actions()][-3:], ['連携','Language','ヘルプ'])
        for language in ('ja','en'):
            configure(language)
            d = HamlogSettingsDialog(self.window.integration, self.window)
            self.assertFalse(d.enabled.isChecked()); self.assertFalse(d.save_mode.currentData())
            self.assertEqual(d.windowTitle(), tr('HAMLOG連携設定'))
            g = GuideWindow(self.window); self.assertIn('HAMLOG',g.tabs.tabText(g.tabs.count()-1))
            thanks = SpecialThanksDialog(self.window); thanks.resize(420,260); thanks.show(); self.pump(.02)
            self.assertGreater(thanks.scroll.verticalScrollBar().maximum(), 0)
            self.assertIn('JG2AJK\nJQ7FIU\n7K2COL', thanks.names.text())
            self.assertIn('zLog', thanks.closing_message.text())
            for dialog in (d,g,thanks): dialog.close()
        configure('ja')
    def test_csv_export_hides_zlog_controls_and_english_navigation(self):
        from psrtty.ui.hamlog_export_dialog import HamlogExportDialog
        configure('en')
        dialog=HamlogExportDialog(self.window.adif,self.store,self.window)
        self.assertTrue(dialog.profile.isHidden()); self.assertTrue(dialog.profile_note.isHidden())
        self.assertEqual(dialog.next.text(),'Next'); self.assertEqual(tr('保存しました：'),'Saved: ')
        dialog.close(); configure('ja')

    def test_record_transfer_only_after_local_adif_success(self):
        w = self.window; w.q_call.setText('JA1ABC'); w.current_freq_hz = 14085000
        with patch.object(w.integration, 'record') as transfer:
            w._add_qso(); transfer.assert_called_once()
            sent_qso = transfer.call_args.args[0]; self.assertEqual(sent_qso.call,'JA1ABC')
            transfer.reset_mock(); w.q_call.setText('JA9ABC')
            w.adif.append.side_effect = OSError('disk full')
            with patch('psrtty.ui.main_window.QMessageBox.warning'):
                w._add_qso()
            transfer.assert_not_called()
    def test_background_link_keeps_gui_ticking(self):
        ticks = []; timer = QTimer(); timer.setInterval(5); timer.timeout.connect(lambda:ticks.append(1)); timer.start()
        done = []
        start = time.monotonic()
        self.window.integration.run(lambda:(time.sleep(.15),'OK')[1], lambda r,e:done.append((r,e)))
        self.assertLess(time.monotonic()-start,.1)
        self.pump(.25); timer.stop()
        self.assertGreater(len(ticks),10); self.assertEqual(done,[('OK',None)])
    def test_failure_dialog_preserves_local_qso_and_has_recovery(self):
        from psrtty.adif import ADIFLog
        w=self.window; w.adif=ADIFLog(Path(self.tmp.name)/'logs'); w.qsos=[]
        self.store.data['hamlog']['enabled']=True
        w.q_call.setText('JA1ABC'); w.current_freq_hz=14085000
        configure('en')
        with patch.object(w.integration.link,'transfer',side_effect=LinkError('HAMLOG missing')), patch('psrtty.ui.integration_dialog.QMessageBox.warning') as warn:
            w._add_qso(); self.pump(.1)
            self.assertEqual(len(w.qsos),1); self.assertIn('Do not add this QSO again',warn.call_args.args[2])
        configure('ja')


class Config107Tests(unittest.TestCase):
    def test_old_config_defaults_and_settings_persist(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'config.json'; macro=Path(td)/'macros.json'; path.write_text('{"version":"1.06"}', encoding='utf-8')
            store=ConfigStore(path,macro); self.assertEqual(store.data['hamlog'],{'enabled':False,'auto_save':False})
            store.data['hamlog']={'enabled':True,'auto_save':True}; store.save()
            self.assertEqual(ConfigStore(path,macro).data['hamlog'],store.data['hamlog'])
    def test_all_new_ui_messages_have_english(self):
        root=Path(__file__).resolve().parents[1]/'psrtty'
        for name in ('hamlog_link.py','zlog_export.py','ui/integration_dialog.py'):
            for node in ast.walk(ast.parse((root/name).read_text(encoding='utf-8'))):
                if isinstance(node,ast.Constant) and isinstance(node.value,str) and any('\u3040'<=ch<='\u9fff' for ch in node.value):
                    self.assertIn(node.value,TEXT, (name,node.value))
