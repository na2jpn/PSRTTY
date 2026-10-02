import copy
import csv
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QRect, Qt
from psrtty.adif import QSORecord, ADIFLog
from psrtty.hamlog_csv import export_hamlog
from psrtty.hamlib_radio import HamlibController, load_library
from psrtty.audio_devices import resolve_device
from psrtty.civ import CIVStatus
from psrtty.config import ConfigStore
from psrtty.i18n import configure, tr
from psrtty.ui.window_state import fitted_rect
from tests.test_ui_v02 import UITests as _Fixture


class Export106Tests(unittest.TestCase):
    def qso(self):
        return QSORecord('JA1ABC', '579', '589', '001', '002', 'JH1HST/JD1', 7040000,
                         datetime(2026, 9, 30, 16, 25, tzinfo=timezone.utc))

    def test_csv_order_asymmetric_rst_jst_rollover_exchanges(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'hamlog.csv'
            export_hamlog(path, [self.qso()])
            data = path.read_bytes()
            self.assertTrue(data.endswith(b'\r\n'))
            rows = list(csv.reader(io.StringIO(data.decode('cp932'))))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0], ['JA1ABC','26/10/01','01:25J','579','589','7.04','RTTY',
                                       '','','','','','SENT:001 RCVD:002','MYCALL:JH1HST/JD1',''])

    def test_station_optional_and_csv_escaping(self):
        q = self.qso(); q.sent = 'a,"b"'
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'hamlog.csv'; export_hamlog(path, [q], include_station=False)
            row = next(csv.reader(io.StringIO(path.read_text(encoding='cp932'))))
            self.assertEqual(row[12], 'SENT:a,"b" RCVD:002'); self.assertEqual(row[13], '')

    def test_failed_export_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'hamlog.csv'; path.write_bytes(b'original')
            for bad in ('a'*57, 'unsupported\U0001f600', 'line\nbreak'):
                q = self.qso(); q.sent = bad
                with self.assertRaises(ValueError): export_hamlog(path, [q])
                self.assertEqual(path.read_bytes(), b'original')
            with self.assertRaises(ValueError): export_hamlog(path, [])
            with self.assertRaises(ValueError): export_hamlog(path, [self.qso()], protected=[path])

    def test_small_screen_includes_frame_and_taskbar(self):
        area = QRect(0, 0, 800, 560)
        fitted = fitted_rect(dict(x=-100,y=-100,w=1280,h=800), [area], margins=(8,32,8,8))
        outer = fitted.adjusted(-8,-32,8,8)
        self.assertTrue(area.contains(outer))
        self.assertEqual((fitted.width(), fitted.height()), (784,520))

    def test_saved_language_and_invalid_value(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'config.json'; macros = Path(td)/'macros.json'
            store = ConfigStore(path, macros); self.assertEqual(store.data['ui']['language'], 'ja')
            store.data['ui']['language']='en'; store.save()
            self.assertEqual(ConfigStore(path, macros).data['ui']['language'], 'en')
            store.data['ui']['language']='invalid'; store.save()
            self.assertEqual(ConfigStore(path, macros).data['ui']['language'], 'ja')

    def test_windows_never_searches_system_library(self):
        with patch('psrtty.hamlib_radio.sys.platform','win32'), \
             patch('psrtty.hamlib_radio.ctypes.util.find_library') as find, \
             patch('psrtty.hamlib_radio.ctypes.CDLL') as cdll:
            with self.assertRaises(FileNotFoundError): load_library('/missing/hamlib.dll')
        find.assert_not_called(); cdll.assert_not_called()

    def test_default_audio_pair_object(self):
        class Pair:
            def __getitem__(self, index): return (3,4)[index]
        class Audio:
            default = type('Default', (), {'device': Pair()})()
        with patch('psrtty.audio_devices.sys.platform', 'freebsd13'):
            self.assertEqual(resolve_device(Audio(), 'AUTO', 'input'), 3)
            self.assertEqual(resolve_device(Audio(), 'AUTO', 'output'), 4)


class RadioLibrary:
    def __init__(self): self.mode=1024; self.width=500; self.tx=0; self.flags={}; self.fail=False; self.commands=[]
    def rig_parse_mode(self, name): return {b'PKTLSB':1024,b'PKTUSB':2048,b'RTTY':4096,b'RTTYR':8192,b'LSB':2,b'USB':4}[name]
    def rig_get_mode(self,h,v,m,w): m._obj.value=self.mode;w._obj.value=self.width;return 0
    def rig_set_mode(self,h,v,m,w): self.commands.append((m,w));self.mode=m;self.width=w;return 0
    def rig_get_ptt(self,h,v,out):out._obj.value=self.tx;return 0
    def rig_parse_func(self,name):return {b'NB':2,b'NR':512}[name]
    def rig_get_func(self,h,v,f,out):out._obj.value=self.flags.get(f,0);return -1 if self.fail else 0
    def rig_set_func(self,h,v,f,on):self.commands.append((f,on));self.flags[f]=on;return 0


class Radio106Tests(unittest.TestCase):
    def controller(self, model='FTX-1'):
        c=HamlibController(model);c.lib=RadioLibrary();c.handle=123;c.status=CIVStatus(connected=True)
        return c

    def test_features_both_models_readback_and_transmit_guard(self):
        for model in ('FTX-1','FT-991 / FT-991A'):
            c=self.controller(model)
            for name in ('NB','NR'):
                self.assertIs(c.read_feature(name), False);self.assertTrue(c.set_feature(name,True))
                self.assertIs(c.read_feature(name), True);self.assertTrue(c.set_feature(name,False))
            c.lib.tx=1;before=list(c.lib.commands)
            self.assertFalse(c.set_feature('NB',True));self.assertEqual(c.lib.commands,before)
            c.lib.fail=True;self.assertIsNone(c.read_feature('NR'))
            self.assertIsNone(c.read_feature('AN'))

    def test_filter_mode_and_width_readback_and_guards(self):
        for model in ('FTX-1','FT-991 / FT-991A'):
            c=self.controller(model);state=c.read_filter()
            self.assertIn((500,'500 Hz'),state['options']);self.assertTrue(c.set_filter(1200,state))
            self.assertEqual(c.read_filter()['value'],1200)
            c.lib.tx=1;self.assertFalse(c.set_filter(500,state));c.lib.tx=0
            c.lib.mode=4;self.assertFalse(c.set_filter(500,state))
            self.assertFalse(c.set_filter(123456,c.read_filter()))
            c.cancel.set();self.assertIsNone(c.read_filter())


class UI106Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp; tearDown=_Fixture.tearDown; pump=_Fixture.pump

    def test_export_menu_order_and_exclusive_checks(self):
        import gc
        from shiboken6 import isValid
        w = self.window
        menu_bar = w.menuBar()
        menu_actions = menu_bar.actions()
        file_action = menu_actions[0]
        file_menu = file_action.menu()
        self.assertIs(file_menu, w.file_menu)
        gc.collect()
        self.assertTrue(isValid(file_menu))
        self.assertTrue(all(isValid(menu) for menu in w.top_level_menus))
        actions = file_menu.actions()
        i=next(i for i,a in enumerate(actions) if a.text()=='ADIFファイル出力')
        self.assertTrue(actions[i-1].isSeparator())
        self.assertEqual([a.text() for a in actions[i:i+3]], ['ADIFファイル出力','Cabrilloファイル出力','HAMLOG-CSV出力'])
        for group in (w.width_group,w.font_group,w.latest_group):
            self.assertEqual(sum(a.isChecked() for a in group.actions()),1)
        w._set_spectrum_width(3000);w._set_card_font(18);w._set_latest_count(10);w._sync_view_checks()
        self.assertEqual([g.checkedAction().data() for g in (w.width_group,w.font_group,w.latest_group)], [3000,18,10])

    def test_csv_wizard_exports_selected_records_only(self):
        from psrtty.ui.hamlog_export_dialog import HamlogExportDialog
        with tempfile.TemporaryDirectory() as td:
            adif=ADIFLog(Path(td)/'logs');q=Export106Tests().qso();adif.append(q)
            dlg=HamlogExportDialog(adif,self.store,self.window)
            dlg.station.setText(q.station_callsign)
            dlg.start.setDateTime(dlg.start.dateTime().fromString('2026-10-01 00:00','yyyy-MM-dd HH:mm'))
            dlg.end.setDateTime(dlg.end.dateTime().fromString('2026-10-01 02:00','yyyy-MM-dd HH:mm'))
            dlg.go_next();self.assertEqual(dlg.pages.currentIndex(),1)
            next(iter(dlg.band_checks.values())).setChecked(True);dlg.go_next();dlg.go_next()
            self.assertEqual(dlg.pages.currentIndex(),3);self.assertEqual(len(dlg.selected),1)
            path=Path(td)/'out.csv'
            with patch('psrtty.ui.hamlog_export_dialog.QFileDialog.getSaveFileName',return_value=(str(path),'')):
                dlg.go_next()
            self.assertTrue(path.exists());self.assertEqual(adif.load_recent(limit=None)[0].call,q.call)
            dlg.close()

    def test_language_selection_saves_for_next_restart(self):
        w=self.window
        with patch('psrtty.ui.main_window.QMessageBox.information'):
            w._set_language('en')
        self.assertEqual(w.store.data['ui']['language'],'en');w.store.save.assert_called()
        configure('en')
        try:self.assertEqual(tr('HAMLOG-CSV出力'),'Export HAMLOG CSV')
        finally:configure('ja')
