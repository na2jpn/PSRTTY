import os
import time
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from psrtty.timebase import JST, UTC
from psrtty.adif import ADIFLog,QSORecord
from psrtty.logging_store import TranscriptLogger
from psrtty.ui.qso_log_dialog import QSOEditDialog
from psrtty.ui.control_window import ControlWindow
from tests.test_ui_v02 import UITests as _Fixture

@contextmanager
def host_zone(zone):
    old=os.environ.get('TZ');os.environ['TZ']=zone
    if hasattr(time,'tzset'):time.tzset()
    try:yield
    finally:
        if old is None:os.environ.pop('TZ',None)
        else:os.environ['TZ']=old
        if hasattr(time,'tzset'):time.tzset()

class Frozen(datetime):
    instant=datetime(2026,9,30,15,30,tzinfo=UTC)
    @classmethod
    def now(cls,tz=None):return cls.instant.astimezone(tz) if tz else cls.instant.replace(tzinfo=None)

class Storage78Tests(unittest.TestCase):
    def test_utc_month_matches_content_jst_day_matches_raw(self):
        for host in ('UTC','America/New_York'):
            with host_zone(host),tempfile.TemporaryDirectory() as td:
                log=ADIFLog(Path(td));raw=TranscriptLogger(Path(td))
                for stamp,name,day,hour in [
                    (datetime(2026,10,1,0,30,tzinfo=JST),'202609.adi','20260930','153000'),
                    (datetime(2026,10,1,9,0,tzinfo=JST),'202610.adi','20261001','000000'),
                    (datetime(2027,1,1,0,0,tzinfo=JST),'202612.adi','20261231','150000')]:
                    p=log.append(QSORecord('JH1HST',when_utc=stamp),datetime(2030,1,1))
                    self.assertEqual(p.name,name)
                    text=p.read_text(encoding='utf-8');self.assertIn(day,text);self.assertIn(hour,text)
                p=raw.append('RX TEST',Frozen.instant)
                self.assertEqual(p.name,'20261001_all.txt');self.assertIn('2026-10-01 00:30:00',p.read_text(encoding='utf-8-sig'))
                with patch('psrtty.adif.datetime',Frozen),patch('psrtty.logging_store.datetime',Frozen):
                    self.assertEqual(log.ensure_file().name,'202609.adi');self.assertEqual(raw.ensure_file().name,'20261001_all.txt')

    def test_edit_moves_month_preserves_unknown_fields_and_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            log=ADIFLog(Path(td));p=log.append(QSORecord('JH1HST',when_utc=Frozen.instant))
            p.write_text(p.read_text(encoding='utf-8').replace('<EOR>','<APP_TEST:3>ABC <EOR>'),encoding='utf-8')
            original=log.load_recent()[0];future=replace(original,when_utc=datetime(2026,10,1,tzinfo=UTC))
            target=Path(td)/'202610.adi';before=p.read_bytes()
            real_replace=os.replace
            def fail_source(src,dst):
                if Path(dst)==p:raise OSError('simulated source write error')
                return real_replace(src,dst)
            with patch('psrtty.adif.os.replace',side_effect=fail_source):
                with self.assertRaises(OSError):log.modify(original,future)
            self.assertEqual(p.read_bytes(),before);self.assertFalse(target.exists())
            log.modify(original,future)
            rows=log.load_recent();self.assertEqual(len(rows),1);self.assertEqual(Path(rows[0].source_path).name,'202610.adi')
            self.assertIn('<APP_TEST:3>ABC',target.read_text(encoding='utf-8'))
            self.assertNotIn('<EOR>',p.read_text(encoding='utf-8'))

class UI78Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def test_manual_jst_and_latest_are_independent_of_host_zone(self):
        w=self.window
        for host in ('UTC','America/New_York'):
            with host_zone(host):
                w.q_call.setText('JH1HST');w.q_datetime.setText('2026-10-01 00:30');w._add_qso()
                q=w.adif.append.call_args.args[0];self.assertEqual(q.when_utc,Frozen.instant)
                w.qsos=[q];w._refresh_latest_qsos()
                self.assertEqual(w.latest_table.item(0,1).text(),'2026-10-01 00:30')
                self.assertEqual(w.latest_table.horizontalHeaderItem(1).text(),'日時（JST）')
                d=QSOEditDialog(q,w)
                self.assertEqual(d.fields['when'].text(),'2026-10-01 00:30:00');d.save()
                self.assertEqual(d.result_record.when_utc,Frozen.instant);d.close()
        self.assertEqual(w.q_datetime.zone_label.text(),'JST')
        with patch('psrtty.ui.qso_datetime.datetime',Frozen):
            w.q_datetime.clear();self.assertEqual(w.q_datetime.date.text(),'2026-10-01')
            self.assertEqual(w.q_datetime.time.text(),'00:30')

    def test_menu_opens_live_utc_month_and_jst_day(self):
        w=self.window;w.adif=ADIFLog(self.paths['logdata']);w.transcript=TranscriptLogger(self.paths['logdata'])
        with patch('psrtty.adif.datetime',Frozen),patch('psrtty.logging_store.datetime',Frozen),patch.object(w,'_open_path') as opened:
            w._open_adif();self.assertEqual(opened.call_args.args[0].name,'202609.adi')
            w._open_transcript();self.assertEqual(opened.call_args.args[0].name,'20261001_all.txt')
        w._refresh_log_menu();self.assertEqual(w.adif_action.text(),'今月のADIFを開く（UTC基準）')

    def test_yaesu_labels_switch_without_changing_command_keys(self):
        d=ControlWindow(self.window);d.timer.stop()
        try:
            for model,expected in [('FTX-1','DNR'),('FT-991 / FT-991A','DNR'),('IC-7300','NR')]:
                self.store.data['radio']['model']=model;d.refresh_enabled()
                self.assertTrue(d.buttons['NR'].text().startswith(expected+' '))
                self.assertTrue(d.buttons['NB'].text().startswith('NB '))
                self.assertEqual(d.notch.itemData(0),'AN')
                self.assertEqual(d.notch.itemText(0),'自動' if model=='IC-7300' else 'DNF')
        finally:d.close()

del _Fixture
