import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from tests.test_v75 import UI75Tests as _Fixture, qso
from psrtty.ui.cabrillo_dialog import CabrilloDialog
from psrtty.cabrillo import JST

UTC=timezone.utc

class UI76Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump
    dialog=_Fixture.dialog

    def test_month_start_uses_jst_month_including_year_boundary(self):
        for instant,expected in [(datetime(2026,9,30,15,10,tzinfo=UTC),'2026-10-01 00:00'),(datetime(2026,12,31,15,10,tzinfo=UTC),'2027-01-01 00:00')]:
            class Frozen(datetime):
                @classmethod
                def now(cls,tz=None):return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
            with patch('psrtty.ui.cabrillo_dialog.datetime',Frozen):d=self.dialog([],0)
            self.assertEqual(d.start.dateTime().toString('yyyy-MM-dd HH:mm'),expected)
            self.assertEqual(d.start.displayFormat(),'yyyy-MM-dd HH:mm')
            self.assertEqual(d.end.displayFormat(),'yyyy-MM-dd HH:mm')
            d.close()

    def test_last_second_included_and_original_seconds_preserved(self):
        end=datetime(2026,9,27,23,59,59,999999,tzinfo=UTC)
        d=self.dialog([qso(when_utc=end),qso(when_utc=datetime(2026,9,28,tzinfo=UTC))])
        self.assertEqual(d.visible,[0]);entries,errors=d.selected_entries()
        self.assertEqual(errors,[]);self.assertEqual(entries[0][0].when_utc,end)
        self.assertEqual(d.table.item(0,1).text(),'2026-09-28 08:59')
        d.zone.setCurrentText('UTC');entries,errors=d.selected_entries()
        self.assertEqual(errors,[]);self.assertEqual(entries[0][0].when_utc,end)
        self.assertEqual(d._read_datetime(d.end),end)
        d.table.item(0,1).setText('2026-09-27 23:58')
        self.assertEqual(d.selected_entries()[0][0][0].when_utc.second,0)

    def test_friendly_independent_errors_highlight_and_correction(self):
        d=self.dialog();d.table.item(0,1).setText('bad date');d.table.item(0,4).setText('bad MHz')
        entries,errors=d.selected_entries();message=' '.join(errors)
        self.assertEqual(entries,[]);self.assertIn('日時を確認',message);self.assertIn('周波数は半角数字',message)
        self.assertNotIn('ConversionSyntax',message);self.assertNotIn('ValueError',message)
        for col in (1,4):self.assertEqual(d.table.item(0,col).background().color().name(),'#ffe0e0')
        diagnostic=''.join(p.read_text(encoding='utf-8') for p in self.paths['var'].glob('cabrillo_*.log'))
        self.assertIn('InvalidOperation',diagnostic)
        d.table.item(0,1).setText('2026-09-26 09:00');d.table.item(0,4).setText('14.085')
        entries,errors=d.selected_entries();self.assertEqual(errors,[]);self.assertEqual(len(entries),1)
        self.assertEqual(d.table.item(0,11).text(),'');self.assertFalse(d.table.item(0,4).toolTip())
        for value in ('','NaN','Infinity','1e99999','-1','0'):
            d.table.item(0,4).setText(value);entries,errors=d.selected_entries()
            self.assertTrue(errors);self.assertNotIn('<class',str(errors))

    def test_future_year_notice_and_manual_period(self):
        d=self.dialog();d.year.setValue(2027)
        self.assertEqual(d.dates.text(),'2027年の大会期間を入力')
        self.assertFalse(d.period_note.isHidden());self.assertIn('公式日程を確認',d.period_note.text())
        d.set_period();self.assertEqual(d.start.dateTime().toString('yyyy-MM-dd HH:mm'),'2027-09-25 09:00')
        d._display_datetime(d.start,datetime(2027,9,24,tzinfo=UTC))
        self.assertEqual(d.start.dateTime().toString('yyyy-MM-dd HH:mm'),'2027-09-24 09:00')
        generic=self.dialog([],0);self.assertTrue(generic.period_note.isHidden())

    def test_diagnostic_failure_does_not_block_validation(self):
        d=self.dialog();d.table.item(0,4).setText('bad')
        with patch.object(Path,'open',side_effect=PermissionError('no write')):
            entries,errors=d.selected_entries()
        self.assertEqual(entries,[]);self.assertIn('周波数は半角数字',str(errors))

del _Fixture
