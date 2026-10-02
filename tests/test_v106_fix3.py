"""FIX3: time-zone invariants and bounded, nonblocking serial output."""
import copy
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from psrtty.printer import PrinterSpool, PrintJob, job_lines, normalize_settings, port_key
from psrtty.timebase import JST


class FakeSerial:
    def __init__(self, fail=False, acknowledge=True):
        self.data=bytearray();self.closed=False;self.fail=fail;self.acknowledge=acknowledge
        self.acks=bytearray();self.threads=[]
    def write(self, data):
        self.threads.append(threading.get_ident())
        if self.fail:raise OSError('Disconnected')
        count=min(3,len(data));self.data.extend(data[:count])
        if data[:count].endswith(b'\n') and self.acknowledge:self.acks.extend(b'OK\n')
        return count
    def reset_input_buffer(self):self.acks.clear()
    def read(self, n):
        if self.acks:
            value=bytes(self.acks[:n]);del self.acks[:n];return value
        time.sleep(.005);return b''
    def close(self):self.closed=True


class Printer106Fix3Tests(unittest.TestCase):
    def setUp(self):self.spools=[]
    def tearDown(self):
        for spool in self.spools:
            spool.stop();spool.thread.join(2);self.assertFalse(spool.thread.is_alive())
    def spool(self,device=None,**kw):
        device=device or FakeSerial()
        settings=dict(port='COM9',line_delay=.05,**kw)
        spool=PrinterSpool(settings,lambda **_:device);self.spools.append(spool)
        # Test transport logic without waiting through bridge boot and pacing.
        spool._wait=lambda seconds,generation:not spool._cancelled(generation)
        return spool,device
    def until(self,condition):
        deadline=time.monotonic()+3
        while not condition():
            if time.monotonic()>deadline:self.fail('Timed out')
            time.sleep(.005)

    def test_off_default_short_filter_targets_and_nonblocking_writes(self):
        spool,device=self.spool()
        self.assertFalse(spool.submit('RX','599'))
        spool.enable(True)
        self.assertFalse(spool.submit('RX',' A \n'))
        self.assertFalse(spool.submit('TX','TU'))
        self.assertTrue(spool.submit('RX','TU'))
        self.until(lambda:spool.snapshot()['sent']==1)
        self.assertIn(b'TU\n',device.data)
        self.assertTrue(all(t!=threading.get_ident() for t in device.threads))
        spool.enable(False);self.until(lambda:not spool.snapshot()['waiting'])
        self.assertTrue(spool.configure(dict(port='COM9',target='RXTX',ignore_short=False)))
        spool.enable(True);self.assertTrue(spool.submit('TX','A'));self.assertTrue(spool.submit('RX','B'))
        self.until(lambda:spool.snapshot()['sent']==3)
        self.assertLess(device.data.index(b'A\n'),device.data.index(b'B\n'))

    def test_overflow_keeps_accepted_jobs_and_pauses_intake(self):
        spool,device=self.spool(max_jobs=10)
        with spool.condition:
            spool.enable(True)
            for n in range(10):self.assertTrue(spool.submit('RX','MSG '+str(n)))
            self.assertFalse(spool.submit('RX','OVERFLOW'))
            state=spool.snapshot();self.assertFalse(state['enabled']);self.assertEqual(state['waiting'],10)
            self.assertEqual(state['problem'],'full')
        self.assertEqual(device.data,b'')
        spool.enable(True);self.until(lambda:spool.snapshot()['sent']==10)
        self.assertNotIn(b'OVERFLOW',device.data)

    def test_disconnect_preserves_later_jobs_no_automatic_replay(self):
        device=FakeSerial(fail=True);spool,_=self.spool(device)
        with spool.condition:
            spool.enable(True);spool.submit('RX','FIRST');spool.submit('RX','SECOND')
        self.until(lambda:spool.snapshot()['problem']=='error')
        self.assertEqual(spool.snapshot()['waiting'],1);self.assertFalse(spool.snapshot()['enabled'])
        device.fail=False;spool.enable(True);self.until(lambda:spool.snapshot()['sent']==1)
        self.assertNotIn(b'FIRST',device.data);self.assertIn(b'SECOND',device.data)

    def test_ack_stops_after_unconfirmed_line(self):
        spool,device=self.spool(FakeSerial(acknowledge=False),ack=True,ack_timeout=1.0)
        spool.enable(True);spool.submit('RX','ONE TWO THREE')
        self.until(lambda:spool.snapshot()['problem']=='error')
        self.assertEqual(device.data.count(b'\n'),1)
        self.assertIn('ACK timeout',spool.snapshot()['detail'])
        self.assertEqual(spool.snapshot()['sent'],0)

    def test_ack_success_partial_writes_and_escape_filter(self):
        spool,device=self.spool(ack=True)
        spool.enable(True);spool.submit('RX','ABC\x1b@\x00DEF')
        self.until(lambda:spool.snapshot()['sent']==1)
        self.assertNotIn(b'\x1b',device.data);self.assertNotIn(b'\x00',device.data)
        self.assertIn(b'ABC?@?DEF',device.data)

    def test_queue_clear_off_and_test_bypass_short_filter(self):
        spool,device=self.spool(min_chars=300)
        with spool.condition:
            spool.enable(True);self.assertFalse(spool.submit('RX','CQ TEST'))
            self.assertTrue(spool.submit('TEST','TEST',test=True));spool.clear()
            self.assertEqual(spool.snapshot()['waiting'],0)
            self.assertTrue(spool.submit('TEST','TEST',test=True));spool.enable(False)
            self.assertEqual(spool.snapshot()['waiting'],0)
        self.assertEqual(device.data,b'')
        self.assertTrue(spool.submit('TEST','TEST',test=True))
        self.until(lambda:spool.snapshot()['sent']==1)
        self.assertFalse(spool.snapshot()['enabled'])

    def test_stop_cancels_ack_wait_quickly(self):
        spool,device=self.spool(FakeSerial(acknowledge=False),ack=True,ack_timeout=60)
        spool.enable(True);spool.submit('RX','TEST')
        self.until(lambda:bool(device.data))
        start=time.monotonic();spool.stop();spool.thread.join(1)
        self.assertFalse(spool.thread.is_alive());self.assertLess(time.monotonic()-start,1)

    def test_limits_normalization_ascii_wrap_and_snapshot_time(self):
        self.assertEqual(normalize_settings({'target':'bad','columns':'bad'})['target'],'RX')
        self.assertEqual(port_key('\\\\.\\COM9'),port_key('com9'))
        settings=normalize_settings({'columns':16})
        instant=datetime(2026,9,30,15,30,tzinfo=timezone.utc)
        lines=job_lines(PrintJob('RX','ABC '*30,instant,'JST'),settings)
        self.assertTrue(all(len(line)<=17 for line in lines))
        self.assertIn(b'10-01 00:30:00',b''.join(lines))
        self.assertIn(b'09-30 15:30:00',b''.join(job_lines(PrintJob('RX','CQ',instant,'UTC'),settings)))
        spool,_=self.spool();spool.enable(True)
        self.assertFalse(spool.submit('RX','A'*8193));self.assertEqual(spool.snapshot()['problem'],'full')


from PySide6.QtWidgets import QApplication, QLabel
from psrtty.ui.qso_datetime import QSODatetime
from psrtty.ui.qso_log_dialog import QSOEditDialog
from psrtty.ui.adif_export_dialog import ADIFExportDialog
from psrtty.ui.printer_dialog import PrinterDialog
from psrtty.config import ConfigStore
from psrtty.i18n import configure
from psrtty.adif import QSORecord, ADIFLog
from tests.test_ui_v02 import UITests as Fixture


class TimePrinterUI106Fix3Tests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown
    pump=Fixture.pump

    def test_zone_manual_rollover_preserves_qso_revision_and_saved_utc(self):
        w=self.window;w.adif=ADIFLog(Path(self.tmp.name)/'time-test');w.qsos=[];w.q_datetime.setText('2026-10-01 00:30')
        revision=w.qso_revision
        w._set_time_zone('UTC')
        self.assertEqual(w.q_datetime.text(),'2026-09-30 15:30')
        self.assertEqual(w.q_datetime.zone_label.text(),'UTC');self.assertEqual(w.qso_revision,revision)
        self.assertEqual(w.store.data['ui']['time_zone'],'UTC')
        w.q_call.setText('JA1ABC');w._add_qso()
        self.assertEqual(w.qsos[-1].when_utc,datetime(2026,9,30,15,30,tzinfo=timezone.utc))
        w._set_time_zone('JST')
        self.assertEqual(w.latest_table.horizontalHeaderItem(1).text(),'日時（JST）')
        self.assertEqual(w.latest_table.item(0,1).text(),'2026-10-01 00:30')

    def test_invalid_manual_zone_change_keeps_input_and_selection(self):
        w=self.window;w.q_datetime.setText('2026-10-01 xx:yy');w._set_time_zone('UTC')
        self.assertEqual(w.q_datetime.text(),'2026-10-01 xx:yy');self.assertEqual(w.q_datetime.zone_label.text(),'JST')
        self.assertEqual(w.time_group.checkedAction().data(),'JST')

    def test_existing_cards_update_from_aware_instant_and_tuning_both_states(self):
        w=self.window;w._add_card('CQ','RX');card=w.cards_layout.itemAt(0).widget()
        instant=card.when_utc;w._set_time_zone('UTC')
        self.assertEqual(card.stamp_label.text(),instant.strftime('%H:%M:%S')+' UTC')
        configure('en')
        try:
            for value,expected in [(None,'C tuning ---'),(4.1,'C tuning +4.1 Hz')]:
                with patch.object(w.center_meter,'update',return_value=value):w._refresh_center_tuning()
                self.assertEqual(w.center_tuning.text(),expected)
        finally:configure('ja')

    def test_utc_qso_editor_and_export_bounds(self):
        w=self.window;w._set_time_zone('UTC')
        instant=datetime(2026,9,30,15,30,tzinfo=timezone.utc)
        q=QSORecord('JA1ABC',station_callsign='JH1HST',freq_hz=14085000,when_utc=instant)
        editor=QSOEditDialog(q,w)
        self.assertEqual(editor.fields['when'].text(),'2026-09-30 15:30:00')
        editor.save();self.assertEqual(editor.result_record.when_utc,instant)
        dialog=ADIFExportDialog(w.adif,w.store,w)
        from PySide6.QtCore import QDateTime
        dialog.start.setDateTime(QDateTime.fromString('2026-09-30 15:30','yyyy-MM-dd HH:mm'))
        self.assertEqual(dialog._bounds()[0],instant)
        editor.close();dialog.close()

    def test_menu_order_filter_and_main_only_rx_tx_complete(self):
        w=self.window
        file_actions=w.file_menu.actions();labels=[a.text() for a in file_actions]
        self.assertLess(labels.index('RTTYプリンター'),labels.index('終了'))
        view=next(m for m in w.top_level_menus if m.title()=='表示')
        labels=[a.text() for a in view.actions()]
        self.assertEqual(labels[labels.index('最新QSO表示件数')+1],'時刻表記')
        with patch.object(w.printer,'submit') as submit:
            w.rx_buffer='CQ TEST';w._finalize_rx_card();submit.assert_called_once()
            self.assertEqual(submit.call_args.args[:2],('RX','CQ TEST'))
            submit.reset_mock();w.active_tx_id=2;w.print_tx=(2,'TX DATA',datetime.now(timezone.utc),'JST',w.printer.generation)
            w._tx_finished(False,'cancel',2);submit.assert_not_called()
            w.active_tx_id=3;w.print_tx=(3,'TX DATA',datetime.now(timezone.utc),'JST',w.printer.generation)
            w._tx_finished(True,'done',3);self.assertEqual(submit.call_args.args[:2],('TX','TX DATA'))

    def test_printer_failure_is_nonmodal_and_port_conflicts_rejected(self):
        w=self.window;w.printer.pause('error','Test disconnection');w._refresh_printer_status()
        self.assertIn('通信エラー',w.printer_status.text());self.assertIsNone(self.app.activeModalWidget())
        w.store.data['radio']['com_port']='COM9'
        self.assertTrue(w._printer_port_problem(dict(port='com9')))
        w.store.data['radio'].update(model='IC-705',com_port='AUTO')
        self.assertTrue(w._printer_port_problem(dict(port='COM10')))
        self.assertEqual(w.printer.snapshot()['waiting'],0)
        # RX / logging paths remain callable with a printer error.
        w.rx_buffer='CQ JA1ABC';w._finalize_rx_card();self.assertTrue(w.cards_layout.count())

    def test_printer_settings_default_short_filter_bilingual_no_japanese(self):
        w=self.window;configure('en')
        try:
            with patch('psrtty.ui.printer_dialog.CIVController.port_choices',return_value=[]):
                dialog=PrinterDialog(w.store,lambda values:'',w)
            self.assertTrue(dialog.ignore.isChecked());self.assertEqual(dialog.threshold.value(),1)
            import re
            for label in dialog.findChildren(QLabel):self.assertIsNone(re.search('[ぁ-龥]',label.text()))
            self.assertEqual(dialog.windowTitle(),'Printer settings')
            captured=[];dialog.apply_settings=lambda values:captured.append(values.copy()) or ''
            w.store.data['printer']['target']='TX';dialog.save()
            self.assertEqual(captured[0]['target'],'TX');dialog.close()
        finally:configure('ja')
