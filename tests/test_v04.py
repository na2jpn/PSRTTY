import copy
import importlib.util
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from psrtty import __version__
from psrtty.config import DEFAULT_CONFIG, DEFAULT_MACROS, ConfigStore, RIG_MODELS
from psrtty.civ import CIVController, CIVStatus, connect_configured
from psrtty.yaesu import YaesuController, YAESU_MODELS
from psrtty.radio import create_controller
from psrtty.audio_devices import enumerate_devices, resolve_device
from psrtty.audio_engine import AudioEngine
from psrtty.updater import inspect_zip, create_manifest, prepare_update, apply_update, MANIFEST
from package_release import build_distribution


class FakeCAT:
    def __init__(self, identity='0840', **kwargs):
        self.identity = identity; self.mode = '8'; self.tx = '0'; self.vfo = '0'
        self.rx = bytearray(); self.writes = []; self.closed = False; self.kwargs = kwargs
        self.silent = False; self.reject = False; self.open_lines = None
    def open(self): self.open_lines = (self.rts, self.dtr)
    def close(self): self.closed = True
    def reset_input_buffer(self): self.rx.clear()
    def read(self, n):
        data = self.rx[:n]; del self.rx[:n]
        if not data: time.sleep(.001)
        return bytes(data)
    def write(self, data):
        self.writes.append(data)
        if self.silent: return
        if data == b'ID;': reply = f'ID{self.identity};'
        elif data == b'FA;': reply = 'FA014085000;'
        elif data == b'MD0;': reply = f'MD0{self.mode};'
        elif data.startswith(b'MD0'):
            self.mode = chr(data[3]); reply = ''
        elif data == b'FT;': reply = f'FT{self.vfo};'
        elif data == b'TX;': reply = f'TX{self.tx};'
        elif data in (b'TX0;', b'TX1;'):
            if not self.reject: self.tx = chr(data[2])
            reply = '?;' if self.reject else ''
        else: reply = '?;'
        self.rx.extend(reply.encode())


class Radio04Tests(unittest.TestCase):
    def test_icom_new_addresses_and_user_override(self):
        self.assertEqual(RIG_MODELS['IC-7300MK2'], 0xB6)
        self.assertEqual(RIG_MODELS['IC-905'], 0xAC)
        self.assertEqual(create_controller(dict(model='IC-905', civ_address='90')).address, 0x90)
    def test_ic905_six_byte_frequency(self):
        ctl=CIVController(0xAC); ctl.ser=Mock()
        frame=bytes.fromhex('FE FE E0 AC 03 00 00 40 02 01 01 FD')
        with patch.object(ctl, '_read_response', return_value=frame):
            self.assertEqual(ctl.read_frequency(),10_102_400_000)

    def test_factory_and_only_two_yaesu_choices(self):
        self.assertEqual(len(YAESU_MODELS), 2)
        self.assertTrue(all(x.endswith('（試験用）') for x in YAESU_MODELS.values()))
        self.assertIsInstance(create_controller(dict(model='FTX-1', ptt='CAT')), YaesuController)
        with self.assertRaises(ValueError): create_controller(dict(model='その他Yaesu', ptt='CAT'))
        with self.assertRaises(ValueError): create_controller(dict(model='FTX-1', ptt='RTS'))
    def test_each_identity_mode_and_ptt_readback(self):
        for model, identity, bits in [('FT-991 / FT-991A','0570',2), ('FT-991 / FT-991A','0670',2), ('FTX-1','0840',1)]:
            with self.subTest(model=model, identity=identity):
                fake = FakeCAT(identity); ctl = YaesuController(model)
                with patch('psrtty.yaesu.serial') as serial:
                    serial.Serial.return_value = fake
                    status = connect_configured(ctl, dict(com_port='COM7', cat_baud='38400', ptt='CAT'), dict(data_mode='LSB-D'))
                    self.assertTrue(status.connected); self.assertEqual(status.frequency_hz,14085000)
                    self.assertEqual(serial.Serial.call_args.kwargs['stopbits'],bits)
                    self.assertEqual(fake.open_lines,(False,False))
                    self.assertTrue(ctl.set_data_mode('USB-D')); self.assertEqual(fake.mode,'C')
                    self.assertTrue(ctl.set_ptt(True)); self.assertEqual(fake.tx,'1')
                    ctl.cancel.set(); self.assertTrue(ctl.set_ptt(False)); self.assertEqual(fake.tx,'0')
                    ctl.disconnect(); self.assertTrue(fake.closed)
    def test_wrong_model_not_connected_and_does_not_change_mode(self):
        fake=FakeCAT('0840'); ctl=YaesuController('FT-991 / FT-991A')
        with patch('psrtty.yaesu.serial') as serial:
            serial.Serial.return_value=fake
            self.assertFalse(ctl.connect('COM1',38400).connected)
        self.assertFalse(any(x.startswith(b'MD') or x == b'TX1;' for x in fake.writes))
    def test_cat_timeout_and_cancel(self):
        fake=FakeCAT(); fake.silent=True; ctl=YaesuController('FTX-1')
        with patch('psrtty.yaesu.serial') as serial:
            serial.Serial.return_value=fake; started=time.monotonic()
            self.assertFalse(ctl.connect('COM1','AUTO',timeout=.05).connected)
            self.assertLess(time.monotonic()-started,.3)
            ctl.cancel.set(); serial.Serial.reset_mock()
            self.assertFalse(ctl.connect('COM1',38400).connected); serial.Serial.assert_not_called()
    def test_ptt_refuses_other_vfo_wrong_mode_and_no_response(self):
        ctl=YaesuController('FTX-1'); fake=FakeCAT(); ctl.ser=fake; ctl.status.connected=True
        fake.vfo='1'; self.assertFalse(ctl.set_ptt(True)); self.assertNotIn(b'TX1;',fake.writes)
        fake.vfo='0'; fake.mode='2'; self.assertFalse(ctl.set_ptt(True)); self.assertNotIn(b'TX1;',fake.writes)
        fake.mode='8'; fake.reject=True; self.assertFalse(ctl.set_ptt(True)); self.assertIn(b'TX0;',fake.writes)
        fake.silent=True; self.assertFalse(ctl.set_ptt(True))
    def test_com_choices_keep_description(self):
        from serial.tools.list_ports_common import ListPortInfo
        a=ListPortInfo('COM10'); a.description='Enhanced COM Port'
        b=ListPortInfo('COM2'); b.description='Standard COM Port'
        with patch('psrtty.civ.list_ports') as ports:
            ports.comports.return_value=[a,b]
            choices=CIVController.port_choices()
        self.assertEqual([x[0] for x in choices],['COM2','COM10'])
        self.assertIn('Enhanced',choices[1][1])


class AudioDevice04Tests(unittest.TestCase):
    def setUp(self):
        self.sd=Mock()
        self.sd.query_hostapis.return_value=[dict(name='MME'),dict(name='Windows WASAPI',default_input_device=1,default_output_device=4)]
        self.sd.query_devices.return_value=[
            dict(name='Mic',hostapi=0,max_input_channels=1,max_output_channels=0),
            dict(name='USB Audio',hostapi=1,max_input_channels=1,max_output_channels=0),
            dict(name='USB Audio',hostapi=1,max_input_channels=1,max_output_channels=0),
            dict(name='Disabled',hostapi=1,max_input_channels=1,max_output_channels=0),
            dict(name='Speaker',hostapi=1,max_input_channels=0,max_output_channels=2)]
        self.platform=patch('psrtty.audio_devices.sys.platform','win32'); self.platform.start()
        self.endpoint=patch('psrtty.audio_devices.wasapi_endpoint',side_effect=lambda sd,idx:(f'endpoint-{idx}',idx!=3))
        self.endpoint.start()
    def tearDown(self): self.endpoint.stop(); self.platform.stop()
    def test_only_active_wasapi_without_merging_distinct_same_name(self):
        devices=enumerate_devices(self.sd,'input')
        self.assertEqual([d['index'] for d in devices],[1,2])
        self.assertNotEqual(devices[0]['label'],devices[1]['label'])
        self.assertEqual([d['index'] for d in enumerate_devices(self.sd,'output')],[4])
    def test_stable_id_after_device_renumber(self):
        choice=enumerate_devices(self.sd,'input')[0]['choice']
        with patch('psrtty.audio_devices.wasapi_endpoint',side_effect=lambda sd,idx:('endpoint-1' if idx==2 else f'other-{idx}',True)):
            self.assertEqual(resolve_device(self.sd,choice,'input'),2)
    def test_missing_device_does_not_fall_back_to_default(self):
        choice=dict(backend='wasapi',id='unplugged',kind='output',name='Radio')
        with self.assertRaises(ValueError): resolve_device(self.sd,choice,'output')
        with self.assertRaises(ValueError): resolve_device(self.sd,'5','output')
    def test_auto_means_active_wasapi_default(self):
        self.assertEqual(resolve_device(self.sd,'AUTO','input'),1)
        with patch('psrtty.audio_devices.wasapi_endpoint',return_value=('id',False)):
            with self.assertRaises(ValueError): resolve_device(self.sd,'AUTO','input')
    def test_explicit_output_failure_never_keys_ptt(self):
        engine=AudioEngine(); on=Mock()
        with patch('psrtty.audio_engine.sd',self.sd):
            ok,_=engine.send_text('CQ',dict(backend='wasapi',id='missing',kind='output',name='Radio'),45.45,2125,2295,False,.3,on,Mock())
        self.assertFalse(ok); on.assert_not_called(); self.sd.OutputStream.assert_not_called()


class PTTRelease04Tests(unittest.TestCase):
    def test_release_failure_reports_failure_after_playback(self):
        for off in [Mock(return_value=False), Mock(side_effect=OSError('lost'))]:
            engine=AudioEngine(); done=Mock()
            with patch('psrtty.audio_engine.sd'), patch('psrtty.audio_engine.resolve_device',return_value=None):
                engine.send_text('CQ','AUTO',45.45,2125,2295,False,.3,lambda:True,off,done)
                engine.wait_tx()
            self.assertFalse(done.call_args.args[0]); self.assertIn('PTT解除',done.call_args.args[1])
            self.assertFalse(engine._tx_active)


# Reuse the existing isolated GUI fixture without rerunning its test methods.
from tests.test_ui_v02 import UITests as _Fixture
from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from psrtty.ui.settings_dialog import SettingsDialog
class UI04Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump
    def ready(self):
        self.window.radio=CIVController(0xA4); self.window.radio.status.connected=True
        self.window._set_radio_controls()
    def test_single_call_and_immediate_macro_expansion(self):
        from psrtty.macros import jarl_ww_template
        self.store.macros = jarl_ww_template()
        w=self.window; self.assertIs(w.q_call,w.his_call)
        w.q_call.setText('JX1XXX'); w.sent.setText('002'); w.my_call.setText('JH1HST')
        self.assertIn('002 002',w.macro_buttons[2].toolTip())
        self.assertIn('JX1XXX',w.macro_buttons[2].toolTip())
        self.assertIn('JH1HST',w.auto_cq_button.toolTip())
        self.assertNotIn('現在の相手コールサイン',[x.text() for x in w.findChildren(QLabel)])
    def test_auto_extraction_goes_to_single_call(self):
        w=self.window; w.my_call.setText('JH1HST'); w._consider_auto_extract('JX1XXX 599 25 25')
        self.assertEqual(w.q_call.text(),'JX1XXX'); self.assertEqual(w.rcvd.text(),'25')
        w.auto_get.setChecked(False); w._consider_auto_extract('JX1XXX 599 99 99')
        self.assertEqual(w.rcvd.text(),'25')
    def test_latest_default_rows_reserved(self):
        w=self.window; w.window_restored=True; w.resize(1280,800); w.show(); self.pump(.02)
        self.assertGreaterEqual(w.latest_table.height(),2*24+w.latest_table.horizontalHeader().height())
        self.assertEqual(w.centralWidget().verticalScrollBar().maximum(),0)
    def test_auto_cq_defaults_limits_and_no_unconnected_send(self):
        w=self.window; self.assertEqual(w.cq_count.value(),10); self.assertEqual(w.cq_count.maximum(),99)
        self.assertEqual(w.cq_interval.value(),7)
        with patch.object(w.audio,'send_text') as send: w._start_auto_cq(); send.assert_not_called()
    def test_auto_cq_waits_after_completion_and_stops_at_count(self):
        w=self.window; self.ready(); w.cq_count.setValue(2)
        with patch.object(w.audio,'send_text',return_value=(True,'OK')) as send:
            w._start_auto_cq(); first=w.active_tx_id
            self.assertEqual(send.call_count,1); self.assertFalse(w.auto_cq_timer.isActive())
            w._tx_finished(True,'OK',first)
            self.assertTrue(w.auto_cq_timer.isActive()); self.assertEqual(w.auto_cq_remaining,1)
            self.assertGreater(w.auto_cq_deadline-time.monotonic(),6.5)
            w._auto_cq_tick(); self.assertEqual(send.call_count,1)
            w.auto_cq_deadline=time.monotonic()-1; w._auto_cq_tick(); second=w.active_tx_id
            self.assertEqual(send.call_count,2)
            w._tx_finished(True,'OK',first); self.assertEqual(w.active_tx_id,second)
            w._tx_finished(True,'OK',second); self.assertFalse(w.auto_cq_active)
            w._auto_cq_tick(); self.assertEqual(send.call_count,2)
    def test_auto_cq_stop_and_late_completion_do_not_restart(self):
        w=self.window; self.ready()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')) as send:
            w._start_auto_cq(); token=w.active_tx_id; w._stop_tx()
            w._tx_finished(True,'OK',token); w._auto_cq_tick()
            self.assertFalse(w.auto_cq_active); self.assertEqual(send.call_count,1)
    def test_auto_cq_error_and_disconnect_stop(self):
        w=self.window; self.ready()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')):
            w._start_auto_cq(); w._tx_finished(False,'PTT解除失敗',w.active_tx_id)
            self.assertFalse(w.auto_cq_active); self.assertFalse(w.auto_cq_timer.isActive())
            w._start_auto_cq(); token=w.active_tx_id; w.disconnect_radio(); w._tx_finished(True,'OK',token)
            self.assertFalse(w.auto_cq_active)
    def test_other_macro_interrupts_cq_then_waits_for_release(self):
        w=self.window; self.ready()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')) as send:
            w._start_auto_cq(); token=w.active_tx_id; w._send_macro(7)
            self.assertFalse(w.auto_cq_active); self.assertEqual(send.call_count,1)
            w._tx_finished(False,'送信中止',token)
            self.assertEqual(send.call_count,2); self.assertEqual(send.call_args.args[0],'KKK')
            w._tx_finished(True,'OK',w.active_tx_id)
            self.assertFalse(w.auto_cq_timer.isActive())
    def test_queued_macro_does_not_run_if_release_failed(self):
        w=self.window; self.ready()
        with patch.object(w.audio,'send_text',return_value=(True,'OK')) as send:
            w._start_auto_cq(); token=w.active_tx_id; w._send_macro(7)
            w._tx_finished(False,'PTT解除失敗',token); self.assertEqual(send.call_count,1)
    def test_fixed_and_serial_increment_only_after_successful_save(self):
        w=self.window; w.qsos=[]; w.adif.append.return_value=Path('log.adi')
        self.assertTrue(w.sent_fixed.isChecked())
        w.sent.setText('25'); w.q_call.setText('JX1XXX'); w._add_qso(); self.assertEqual(w.sent.text(),'25')
        w.sent_fixed.setChecked(False); w.sent.setText('009'); w.q_call.setText('JX1XXX'); w._add_qso()
        self.assertEqual(w.qsos[-1].sent,'009'); self.assertEqual(w.sent.text(),'010')
        self.assertEqual(self.store.data['qso']['sent'],'010')
        w.sent.setText('ABC'); w.q_call.setText('JX1XXX'); w._add_qso(); self.assertEqual(w.sent.text(),'ABC')
        w.sent.setText('002'); w.q_call.setText('JX1XXX'); w.adif.append.side_effect=OSError('full')
        with patch.object(QMessageBox,'warning'): w._add_qso()
        self.assertEqual(w.sent.text(),'002'); self.assertEqual(w.q_call.text(),'JX1XXX')
    def test_settings_failure_after_adif_does_not_leave_duplicate_qso(self):
        w=self.window; w.qsos=[]; w.adif.append.return_value=Path('log.adi')
        w.q_call.setText('JX1XXX'); w.sent_fixed.setChecked(False); w.sent.setText('009')
        with patch.object(self.store,'save',side_effect=OSError('full')), patch.object(QMessageBox,'warning') as warn:
            w._add_qso()
        self.assertEqual(len(w.qsos),1); self.assertEqual(w.q_call.text(),'')
        self.assertEqual(w.sent.text(),'010'); self.assertIn('ADIF',warn.call_args.args[2])
    def test_settings_dynamic_fields_and_addresses(self):
        dlg=SettingsDialog(self.store)
        self.assertFalse(dlg.specific.isEnabled())
        dlg.rig.setCurrentText('IC-7300MK2'); self.assertEqual(dlg.civ_addr.currentText(),'B6')
        dlg.rig.setCurrentText('IC-905'); self.assertEqual(dlg.civ_addr.currentText(),'AC')
        self.assertEqual(dlg.baud.currentText(),'自動'); self.assertEqual(dlg._radio_values()['civ_baud'],'AUTO')
        dlg.rig.setCurrentIndex(dlg.rig.findData('FTX-1'))
        self.assertTrue(dlg.civ_addr.isHidden()); self.assertFalse(dlg.stopbits.isHidden())
        self.assertEqual(dlg.ptt.currentText(),'CAT'); self.assertEqual(dlg.stopbits.currentData(),1)
        self.assertIn('DATA-L',dlg.auto_mode.text())
        dlg.rig.setCurrentIndex(dlg.rig.findData('FT-991 / FT-991A')); self.assertEqual(dlg.stopbits.currentData(),2)
        dlg._save(); self.assertIsInstance(create_controller(self.store.data['radio']),YaesuController)
    def test_missing_audio_and_settings_save_do_not_discard_qso_edits(self):
        self.store.data['audio']['output_device']=dict(backend='wasapi',id='gone',name='Radio',kind='output')
        dlg=SettingsDialog(self.store)
        self.assertIn('未接続',dlg.audio_out.currentText())
        self.window.sent.setText('075'); dlg._save()
        self.assertEqual(self.store.data['qso']['sent'],'075')
        self.assertEqual(self.store.data['audio']['output_device']['id'],'gone')


del _Fixture


class Update04Tests(unittest.TestCase):
    def test_packaged_v04_update_preserves_all_data_and_refuses_same_old(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); root=base/'installed'; root.mkdir()
            for name in ('config','logdata','var'): (root/name).mkdir()
            (root/'psrtty.exe').write_bytes(b'MZ-v03'); create_manifest(root,'0.03')
            saved={'config/psrtty.json':b'{"radio":{"model":"IC-705"}}','config/macros.json':b'custom macro',
                   'logdata/20260924_all.txt':b'timestamp | RX CQ','logdata/20260924.adi':b'<eor>', 'var/user.bin':b'keep'}
            for name,data in saved.items(): (root/name).write_bytes(data)
            exe=base/'new.exe'; exe.write_bytes(b'MZ-v04'); archive=build_distribution(exe,base/'release')
            self.assertEqual(inspect_zip(archive,'0.03')['version'],__version__)
            stage=prepare_update(archive,root,'0.03'); backup=apply_update(stage,root,'0.03')
            self.assertEqual((root/'psrtty.exe').read_bytes(),b'MZ-v04')
            for name,data in saved.items():
                self.assertEqual((root/name).read_bytes(),data); self.assertEqual((backup/name).read_bytes(),data)
            self.assertEqual({x.name for x in root.iterdir()},{'psrtty.exe','config','logdata','var'})
            for current in (__version__,'0.99'):
                with self.assertRaises(ValueError): inspect_zip(archive,current)
