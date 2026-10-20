"""Regression cases from the 1.27 FIX1 reports."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from psrtty import i18n
from psrtty.hamlog_link import HamlogLink,LinkError,THW_SAVEBOX_OFF
from psrtty.hamlog_csv import hamlog_row
from psrtty.parser import parse_exchange
from tests.test_v107 import qso
from tests.test_v123 import EnterHamlog
from tests.test_v127 import UI127Tests as _Fixture


class HamlogFix1Tests(unittest.TestCase):
    def test_truncates_wire_frequency_and_saves_after_decimal_readback(self):
        for hz,expected in [(21079820,'21.079'),(7045999,'7.045'),(50303999,'50.303'),
                            (144123456,'144.123'),(1294123456,'1294.123')]:
            with self.subTest(hz=hz),tempfile.TemporaryDirectory() as td:
                api=EnterHamlog();api.alter={5:expected+'0'}
                link=HamlogLink(Path(td)/'j',lambda:api);record=qso();record.freq_hz=hz
                original=hamlog_row(record)[5];link.transfer(record,True)
                self.assertIn((6,expected,False),api.commands)
                self.assertEqual(len(api.saved),1)
                self.assertEqual(hamlog_row(record)[5],original)
                self.assertEqual(record.freq_hz,hz)
                self.assertIn(18|THW_SAVEBOX_OFF,[c[0] for c in api.commands])

    def test_wrong_frequency_still_prevents_save(self):
        with tempfile.TemporaryDirectory() as td:
            api=EnterHamlog();api.alter={5:'21.080'};record=qso();record.freq_hz=21079820
            with self.assertRaises(LinkError):HamlogLink(Path(td)/'j',lambda:api).transfer(record,True)
            self.assertFalse(api.saved)

    def test_original_precision_journal_blocks_duplicate_from_previous_build(self):
        with tempfile.TemporaryDirectory() as td:
            api=EnterHamlog();record=qso();record.freq_hz=21079820
            key=hashlib.sha256(json.dumps([hamlog_row(record),record.when_utc.isoformat()],ensure_ascii=False).encode()).hexdigest()
            path=Path(td)/'j';path.write_text(json.dumps(dict(key=key,state='attempted'))+'\n',encoding='utf-8')
            with self.assertRaises(LinkError):HamlogLink(path,lambda:api).transfer(record,True)
            self.assertFalse(api.commands)

    def test_input_only_never_saves_and_existing_draft_is_protected(self):
        with tempfile.TemporaryDirectory() as td:
            api=EnterHamlog();record=qso();record.freq_hz=21079820
            link=HamlogLink(Path(td)/'j',lambda:api);link.transfer(record,False)
            self.assertEqual(api.fields[5],'21.079');self.assertFalse(api.saved)
            other=qso();other.call='JA9XYZ';before=list(api.fields)
            with self.assertRaises(LinkError):link.transfer(other,True)
            self.assertEqual(api.fields,before)

    def test_599_priority_does_not_consume_exchange_after_noise_report_run(self):
        for reports in ('299 599','399 599','599 299','399 599 299','299-599'):
            with self.subTest(reports=reports):
                result=parse_exchange(reports+' 001 001 DE JA1ABC K')
                self.assertEqual((result.rst,result.exchange,result.callsign),('599','001','JA1ABC'))
        for text,rst,exchange in [('579 001 599','579','001'),('579 001-001','579','001'),
                                  ('599 25 CA 599','599','25 CA'),('299 001 599','299','001')]:
            result=parse_exchange(text,cqww=True)
            self.assertEqual((result.rst,result.exchange),(rst,exchange),text)


class RITFix1Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump
    connected=_Fixture.connected

    def test_poll_keeps_off_controls_enabled_and_emits_only_on_changed_state(self):
        w,c=self.connected();c.read_rit.return_value['on']=False
        w._show_rit();self.pump(.08);s=w.rit_service;s.timer.stop()
        signals=[];s.changed.connect(lambda:signals.append(True));captured=[]
        class Job:
            def __init__(self,parent,work,done):captured.extend([work,done])
        s.last_poll=0
        with patch('psrtty.ui.rit_window.BackgroundJob',Job):s.tick()
        self.assertTrue(s.busy);self.assertTrue(w.rit_window.slider.isEnabled())
        self.assertFalse(signals)
        captured[1](captured[0](),None);self.assertFalse(signals)
        self.assertFalse(w.rit_window.on.isChecked())
        s.last_poll=0;captured.clear()
        with patch('psrtty.ui.rit_window.BackgroundJob',Job):s.tick()
        c.read_rit.return_value.update(offset=-200,on=True)
        captured[1](captured[0](),None)
        self.assertEqual(len(signals),1);self.assertEqual(w.rit_window.value.text(),'-200 Hz')

    def test_visible_poll_waits_three_seconds(self):
        w,c=self.connected();w._show_rit();self.pump(.08);s=w.rit_service;s.timer.stop()
        c.read_rit.reset_mock();s.last_poll=100
        with patch('psrtty.ui.rit_window.time.monotonic',return_value=102.9):s.tick()
        self.assertFalse(s.busy);c.read_rit.assert_not_called()
        with patch('psrtty.ui.rit_window.time.monotonic',return_value=103.1):s.tick()
        self.pump(.08);c.read_rit.assert_called_once()

    def test_meter_poll_defers_rit_until_cat_is_available(self):
        w,c=self.connected();w.alc_busy=True;w.rit_service.tick()
        self.assertFalse(w.rit_service.busy);c.read_rit.assert_not_called()
        w.alc_busy=False;w.rit_service.tick();self.pump(.08)
        self.assertEqual(w.rit_service.state['offset'],125)

    def test_plus_minus_step_and_profile_persistence(self):
        from psrtty.config import ConfigStore
        from copy import deepcopy
        w,c=self.connected()
        store=ConfigStore(Path(self.tmp.name)/'settings.json',Path(self.tmp.name)/'macros.json')
        store.data=deepcopy(w.store.data);w.store=store
        w._show_rit();self.pump(.08);d=w.rit_window
        self.assertEqual([d.step.itemData(i) for i in range(d.step.count())],[1,2,3,4,5,7,10,15,20])
        d.step.setCurrentIndex(d.step.findData(7))
        self.assertEqual((d.slider.singleStep(),d.slider.pageStep(),d.amount.singleStep()),(7,7,7))
        c.set_rit.side_effect=lambda **change:(c.read_rit.return_value.update(change) or True)
        d.plus.click();self.pump(.12);self.assertEqual(d.value.text(),'+132 Hz')
        d.minus.click();self.pump(.12);self.assertEqual(d.value.text(),'+125 Hz')
        store=ConfigStore(w.store.config_path,w.store.macro_path)
        self.assertEqual(store.data['advanced']['rit_step_hz'],7)

    def test_pending_steps_accumulate_without_readback_bounce(self):
        w,c=self.connected();w._show_rit();self.pump(.08);s=w.rit_service;s.timer.stop();d=w.rit_window
        d.step.setCurrentIndex(d.step.findData(10));captured=[]
        class Job:
            def __init__(self,parent,work,done):captured.extend([work,done])
        with patch('psrtty.ui.rit_window.BackgroundJob',Job):
            d.plus.click();d.plus.click();d.plus.click()
        self.assertEqual(s.inflight,{'offset':135});self.assertEqual(s.pending,{'offset':155})
        captured[1]((dict(c.read_rit.return_value,offset=135),True),None)
        self.assertEqual(d.value.text(),'+155 Hz')
        s.pending=None

    def test_keyboard_wheel_and_numeric_arrows_use_one_selected_step(self):
        from PySide6.QtCore import Qt,QPoint,QPointF
        from PySide6.QtGui import QWheelEvent
        from PySide6.QtTest import QTest
        w,c=self.connected();w._show_rit();self.pump(.08);d=w.rit_window
        d.step.setCurrentIndex(d.step.findData(7));w.rit_service.timer.stop()
        with patch.object(w.rit_service,'request') as request:
            event=QWheelEvent(QPointF(5,5),QPointF(5,5),QPoint(),QPoint(0,120),
                Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
            self.app.sendEvent(d.slider,event)
            request.assert_called_once_with(offset=132)
            request.reset_mock();QTest.keyClick(d.slider,Qt.Key_Right)
            request.assert_called_once_with(offset=139)
            request.reset_mock();d.amount.stepUp()
            request.assert_called_once_with(offset=132)

    def test_profile_switch_restores_each_step(self):
        from copy import deepcopy
        from psrtty.config import ConfigStore
        w,c=self.connected();store=ConfigStore(Path(self.tmp.name)/'settings.json',Path(self.tmp.name)/'macros.json')
        store.data=deepcopy(w.store.data);w.store=store
        store.data['profiles'].append(deepcopy(store.data['profiles'][0]))
        store.data['profiles'][1]['advanced']['rit_step_hz']=20
        w._show_rit();self.pump(.08);d=w.rit_window
        d.step.setCurrentIndex(d.step.findData(3))
        store.activate_profile(1);d.refresh();self.assertEqual(d.step.currentData(),20)
        store.activate_profile(0);d.refresh();self.assertEqual(d.step.currentData(),3)

    def test_search_widgets_removed_and_frequency_note_in_all_languages(self):
        from psrtty.ui.integration_dialog import HamlogSettingsDialog
        from PySide6.QtWidgets import QLineEdit,QLabel
        for code in i18n.LANGUAGES:
            i18n.configure(code);d=HamlogSettingsDialog(self.window.integration,self.window)
            self.assertFalse(d.findChildren(QLineEdit));self.assertFalse(hasattr(d,'search_button'))
            self.assertIn('21.07982',i18n.tr('v127fix1.hamlog_frequency'))
            self.assertTrue(any('21.07982' in x.text() for x in d.findChildren(QLabel)))
            self.assertIn('21.07982',i18n.tr('guide.8.body'))
            d.close();d.deleteLater()
        i18n.configure('ja')

del _Fixture
