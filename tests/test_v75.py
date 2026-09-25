import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtCore import Qt
from tests.test_ui_v02 import UITests as _Fixture
from psrtty.adif import QSORecord, ADIFLog
from psrtty.cabrillo import build_cabrillo, save_cabrillo, period, DEFAULT_LAYOUT
from psrtty.ui.cabrillo_dialog import CabrilloDialog
from psrtty.ui.backup_dialog import BackupDialog

UTC=timezone.utc

def qso(**kw):
    return replace(QSORecord('W1AW',sent='25',rcvd='05 MA',station_callsign='JH1HST',freq_hz=14085000,when_utc=datetime(2026,9,26,tzinfo=UTC)),**kw)

def info(**kw):
    return dict({'CONTEST':'TEST-RTTY','CALLSIGN':'JH1HST','CATEGORY-OPERATOR':'SINGLE-OP','CATEGORY-POWER':'LOW','CATEGORY-BAND':'ALL','CATEGORY-TRANSMITTER':'ONE','CATEGORY-ASSISTED':'NON-ASSISTED','LOCATION':'DX'},**kw)


class Cabrillo75Tests(unittest.TestCase):
    def test_cqww_golden_crlf_and_optional_headers(self):
        body,errors,warnings=build_cabrillo('cqww',info(),[(qso(),{})])
        self.assertEqual(errors,[])
        line=next(s for s in body.splitlines() if s.startswith('QSO:'))
        self.assertEqual(line.split(),'QSO: 14085 RY 2026-09-26 0000 JH1HST 599 25 DX W1AW 599 05 MA'.split())
        self.assertIn('CONTEST: CQ-WW-RTTY\r\n',body)
        self.assertTrue(body.endswith('END-OF-LOG:\r\n'))
        self.assertNotIn('\n',body.replace('\r\n',''))
        self.assertNotIn('CLAIMED-SCORE:',body)
        self.assertTrue(warnings)
        body.encode('ascii')

    def test_jarl_age_and_multi_validation(self):
        body,errors,_=build_cabrillo('jarl',info(),[(qso(sent='1',rcvd='00'),{})])
        self.assertEqual(errors,[])
        self.assertIn('CONTEST: JARL-WW-RTTY',body)
        self.assertEqual(next(s for s in body.splitlines() if s.startswith('QSO:')).split()[-5:],['599','01','W1AW','599','00'])
        bad=info(**{'CATEGORY-OPERATOR':'MULTI-OP','CATEGORY-POWER':'QRP'})
        self.assertTrue(build_cabrillo('jarl',bad,[(qso(sent='01',rcvd='99'),{})])[1])

    def test_cqww_qth_tx_and_xqso(self):
        self.assertTrue(build_cabrillo('cqww',info(),[(qso(rcvd='05'),{})])[1])
        self.assertTrue(build_cabrillo('cqww',info(),[(qso(rcvd='41 MA'),{})])[1])
        multi=info(**{'CATEGORY-OPERATOR':'MULTI-OP','OPERATORS':'JH1HST JQ7FIU','CATEGORY-TRANSMITTER':'TWO','CATEGORY-POWER':'HIGH'})
        self.assertTrue(build_cabrillo('cqww',multi,[(qso(),{})])[1])
        body,errors,_=build_cabrillo('cqww',multi,[(qso(),{'txid':'1','xqso':True})])
        self.assertEqual(errors,[])
        self.assertTrue(next(s for s in body.splitlines() if s.startswith('X-QSO:')).endswith('1'))
        body,errors,_=build_cabrillo('cqww',info(),[(qso(call='KH6XX',rcvd='31'),{})])
        self.assertEqual(errors,[]);self.assertIn('31 DX',body)

    def test_generic_custom_layout_and_invalid_fields(self):
        layout='{FREQ} {MODE} {DATE} {TIME} {MYCALL} {RSTS} {HISCALL} {RSTR} {SENT} {RCVD} {TXID}'
        body,errors,_=build_cabrillo('generic',info(LAYOUT=layout),[(qso(),{'txid':'0'})])
        self.assertEqual(errors,[]);self.assertIn('JH1HST 599 W1AW 599 25 05 MA 0',body)
        for layout in (DEFAULT_LAYOUT+' {MISSING}',DEFAULT_LAYOUT+' {MYCALL.x}',DEFAULT_LAYOUT+'\nBAD', '{FREQ}'):
            self.assertTrue(build_cabrillo('generic',info(LAYOUT=layout),[(qso(),{})])[1])
        self.assertTrue(build_cabrillo('cqww',info(NAME='日本語'),[(qso(),{})])[1])

    def test_period_dates_full_weekend(self):
        self.assertEqual(period('cqww',2026)[0],datetime(2026,9,26,tzinfo=UTC))
        self.assertEqual(period('cqww',2023)[0],datetime(2023,9,23,tzinfo=UTC))
        self.assertEqual(period('jarl',2026)[0],datetime(2026,10,17,tzinfo=UTC))
        self.assertEqual(period('cqww',2026)[1],datetime(2026,9,27,23,59,59,tzinfo=UTC))

    def test_atomic_save_failure_and_source_protection(self):
        with tempfile.TemporaryDirectory() as td:
            target=Path(td)/'contest.log';target.write_bytes(b'old')
            body=build_cabrillo('cqww',info(),[(qso(),{})])[0]
            with patch('psrtty.cabrillo.os.replace',side_effect=PermissionError('locked')):
                with self.assertRaises(PermissionError):save_cabrillo(target,body)
            self.assertEqual(target.read_bytes(),b'old')
            self.assertEqual(list(Path(td).glob('.psrtty-cabrillo-*')),[])
            for name in ('202609.adi','20260926_all.txt','backup.zip'):
                with self.assertRaises(ValueError):save_cabrillo(Path(td)/name,body)
            with self.assertRaises(ValueError):save_cabrillo(target,body,[target])
            save_cabrillo(target,body);self.assertEqual(target.read_bytes(),body.encode('ascii'))


class UI75Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def dialog(self,records=None,profile=2):
        self.store.data['station_callsign']='JH1HST'
        adif=Mock();adif.load_recent.return_value=records if records is not None else [qso()];adif.read_errors=[]
        d=CabrilloDialog(adif,self.store,self.window);self.addCleanup(d.close)
        d.formats.button(profile).setChecked(True);d.year.setValue(2026);d.go_next()
        return d

    def test_all_profiles_save_and_back_preserves_edits(self):
        for profile in (0,1,2):
            with self.subTest(profile=profile):
                record=qso(sent='01',rcvd='45',when_utc=datetime(2026,10,17,tzinfo=UTC)) if profile==1 else qso()
                d=self.dialog([record],profile)
                if profile==0:
                    d._display_datetime(d.start,datetime(2026,9,1,tzinfo=UTC));d._display_datetime(d.end,datetime(2026,10,1,tzinfo=UTC));d.apply_filter()
                d.table.item(0,7).setText('26' if profile==2 else '01')
                d.go_next();self.assertEqual(d.pages.currentIndex(),2,d.error.text())
                d.set_value('NAME','Test Operator')
                if profile==0:d.set_value('CONTEST','TEST-RTTY')
                d.go_back();self.assertEqual(d.table.item(0,7).text(),'26' if profile==2 else '01')
                d.go_next();self.assertEqual(d.value('NAME'),'Test Operator')
                d.go_next();self.assertEqual(d.pages.currentIndex(),3,d.error.text())
                target=Path(self.tmp.name)/f'{profile}.log'
                with patch('psrtty.ui.cabrillo_dialog.QFileDialog.getSaveFileName',return_value=(str(target),'')):d.save_file()
                self.assertTrue(target.exists());self.assertEqual(target.read_bytes(),d.body.encode('ascii'))
                self.assertEqual(record.sent,'01' if profile==1 else '25')
                d.close()

    def test_timezone_filter_boundaries_selection_and_validation(self):
        records=[qso(when_utc=datetime(2026,9,25,23,59,59,tzinfo=UTC)),qso(),qso(when_utc=datetime(2026,9,27,23,59,59,tzinfo=UTC)),qso(when_utc=datetime(2026,9,28,tzinfo=UTC))]
        d=self.dialog(records);self.assertEqual(len(d.visible),2)
        d.table.item(0,0).setCheckState(Qt.Unchecked)
        d.zone.setCurrentText('UTC');self.assertEqual(d.table.item(0,1).text(),'2026-09-26 00:00')
        self.assertEqual(d.table.item(0,0).checkState(),Qt.Unchecked)
        entries,errors=d.selected_entries();self.assertEqual(errors,[]);self.assertEqual(len(entries),1)
        d.table.item(1,1).setText('2026-09-28 00:00')
        d.go_next();self.assertEqual(d.pages.currentIndex(),1);self.assertIn('期間外',d.error.text())
        d.table.item(1,1).setText('2026-09-27 23:59');d.go_next();d.set_value('CALLSIGN','')
        d.go_next();self.assertEqual(d.pages.currentIndex(),2);self.assertTrue(d.error.text())

    def test_save_cancel_failure_retry_and_config_failure(self):
        d=self.dialog();d.go_next();d.go_next();self.assertEqual(d.pages.currentIndex(),3)
        with patch('psrtty.ui.cabrillo_dialog.QFileDialog.getSaveFileName',return_value=('','')):d.save_file()
        self.assertIsNone(d.saved_path)
        target=Path(self.tmp.name)/'retry.log'
        with patch('psrtty.ui.cabrillo_dialog.QFileDialog.getSaveFileName',return_value=(str(target),'')):
            with patch('psrtty.ui.cabrillo_dialog.save_cabrillo',side_effect=OSError('disk full')):d.save_file()
            self.assertEqual(d.pages.currentIndex(),3);self.assertTrue(d.body);self.assertIn('保存できませんでした',d.error.text());self.assertNotIn('disk full',d.error.text())
            self.store.save.side_effect=OSError('config denied');d.save_file()
            self.assertTrue(target.exists());self.assertIn('ファイルは保存済み',d.error.text())
            self.store.save.side_effect=None;d.save_file()
            self.assertEqual(self.store.data['cabrillo']['cqww']['CALLSIGN'],'JH1HST')

    def test_read_error_blocks_partial_output_and_original_adif_unchanged(self):
        log=ADIFLog(Path(self.tmp.name)/'actual');log.append(qso(),datetime(2026,9,26))
        path=log.path_for(datetime(2026,9,26));before=path.read_bytes()
        d=self.dialog(log.load_recent(limit=None));d.table.item(0,8).setText('04 NY');d.go_next();d.go_next()
        self.assertEqual(d.pages.currentIndex(),3,d.error.text());self.assertEqual(path.read_bytes(),before)
        d.go_back();d.go_back();d.read_errors=['unreadable file'];d.go_next()
        self.assertEqual(d.pages.currentIndex(),1);self.assertIn('読み込みエラー',d.error.text())

    def test_backup_default_and_existing_value(self):
        d=BackupDialog(self.store,Mock());self.addCleanup(d.close);self.assertEqual(d.count.value(),30)
        self.store.data['backup']['every_count']=100
        d2=BackupDialog(self.store,Mock());self.addCleanup(d2.close);self.assertEqual(d2.count.value(),100)


del _Fixture
