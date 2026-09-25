import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import zipfile
from psrtty.config import ConfigStore, DEFAULT_CONFIG, DEFAULT_MACROS
from psrtty.civ import CIVController, CIVStatus, radio_address, connect_configured
from psrtty.macros import jarl_ww_template, expand_macro, completes_qso
from psrtty.updater import MANIFEST, apply_update, create_manifest, inspect_zip, prepare_update, version_key
from psrtty.audio_engine import AudioEngine
from psrtty.adif import ADIFLog, QSORecord
from package_release import package_release

class ConfigMacroTests(unittest.TestCase):
    def test_unselected_default_and_address_validation(self):
        self.assertEqual(DEFAULT_CONFIG['radio']['model'], '')
        self.assertEqual(DEFAULT_CONFIG['radio']['civ_address'], '')
        self.assertTrue(DEFAULT_CONFIG['radio']['auto_data_mode'])
        with self.assertRaises(ValueError): radio_address(DEFAULT_CONFIG['radio'])
        self.assertEqual(radio_address(dict(model='IC-705', civ_address='90')), 0x90)
        for addr in ('', 'GG', '100', '00', 'E0'):
            with self.assertRaises(ValueError): radio_address(dict(model='IC-705', civ_address=addr))

    def test_existing_settings_and_eight_macros_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td); data=dict(radio=dict(model='IC-7300', civ_address='99'), custom='keep')
            macros=copy.deepcopy(DEFAULT_MACROS[:8]); macros[0]['text']='CUSTOM'
            (base/'settings.json').write_text(json.dumps(data)); (base/'macros.json').write_text(json.dumps(macros))
            with patch('psrtty.config.ensure_runtime_dirs',return_value={'config':base}):
                store=ConfigStore(base/'settings.json',base/'macros.json')
            self.assertEqual(len(store.macros),9); self.assertEqual(store.macros[:8],macros)
            self.assertEqual(store.data['radio']['civ_address'],'99'); self.assertEqual(store.data['custom'],'keep')
            self.assertFalse(store.data['ui']['auto_log'])

    def test_template_exact_and_independent(self):
        rows=jarl_ww_template()
        self.assertEqual([m['key'] for m in rows],[f'F{i}' for i in range(1,10)])
        self.assertEqual([m['text'] for m in rows],[
            'CQ TEST {MYCALL} {MYCALL}','{MYCALL} {MYCALL}',
            '{HISCALL} 599 {SENT} {SENT}','RRR TU 73 {MYCALL}',
            '{MYCALL} QRZ?','NR? NR?',
            'RRR {HISCALL} 599 {SENT} {SENT}','KKK',''])
        rows[0]['text']='EDIT'; self.assertNotEqual(jarl_ww_template()[0]['text'],'EDIT')
        self.assertTrue(completes_qso('RRR TU 73 JH1HST')); self.assertFalse(completes_qso('TU JH1HST TEST')); self.assertFalse(completes_qso('599 01 01'))
        self.assertEqual(expand_macro('{SENT}',{'SENT':'01A'}),'01A')

    def test_exchange_strings_adif_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            log=ADIFLog(Path(td)); path=log.append(QSORecord('JX1XXX',sent='01',rcvd='25A'))
            q=log.load_recent(path)[0]; self.assertEqual((q.sent,q.rcvd),('01','25A'))

class CIVTests(unittest.TestCase):
    def test_connect_deadline(self):
        ctl=CIVController(0xA4)
        with patch('psrtty.civ.serial') as serial, patch.object(ctl,'available_ports',return_value=['COM1']):
            st=ctl.connect(timeout=0)
        self.assertFalse(st.connected); self.assertIn('タイムアウト',st.message); serial.Serial.assert_not_called()

    def test_connection_exception_closes_port(self):
        ctl=CIVController(0xA4)
        with patch('psrtty.civ.serial') as serial:
            serial.Serial.side_effect=OSError('unplugged'); st=ctl.connect('COM1',19200)
        self.assertFalse(st.connected); self.assertIsNone(ctl.ser)

    def test_cancelled_connect(self):
        ctl=CIVController(0xA4); ctl.cancel.set()
        with patch('psrtty.civ.serial') as serial: st=ctl.connect('COM1',19200)
        self.assertFalse(st.connected); serial.Serial.assert_not_called()

    def test_ptt_requires_connected_and_ack(self):
        ctl=CIVController(0xA4); ctl.ser=Mock()
        self.assertFalse(ctl.set_ptt(True)); ctl.ser.write.assert_not_called(); ctl.status.connected=True
        with patch.object(ctl,'_read_response',return_value=b''): self.assertFalse(ctl.set_ptt(True))
        with patch.object(ctl,'_read_response',return_value=bytes.fromhex('fefe e0 a4 fb fd')): self.assertTrue(ctl.set_ptt(True))

    def test_data_mode_commands(self):
        ctl=CIVController(0xA4); ctl.ser=Mock(); ctl.status.connected=True
        with patch.object(ctl,'_read_response',return_value=bytes.fromhex('fefe e0 a4 fb fd')):
            self.assertTrue(ctl.set_data_mode('LSB-D'))
        self.assertEqual([c.args[0] for c in ctl.ser.write.call_args_list], [bytes.fromhex('fefe a4 e0 06 00 fd'),bytes.fromhex('fefe a4 e0 1a 06 01 01 fd')])

    def test_data_mode_failure_disconnects(self):
        ctl=CIVController(0xA4)
        def connect(*args): ctl.status=CIVStatus(True); return ctl.status
        with patch.object(ctl,'connect',side_effect=connect), patch.object(ctl,'set_data_mode',return_value=False):
            st=connect_configured(ctl,DEFAULT_CONFIG['radio'],DEFAULT_CONFIG['advanced'])
        self.assertFalse(st.connected); self.assertIn('DATA',st.message)

    def test_no_mode_command_when_disabled(self):
        ctl=CIVController(0xA4); ctl.status=CIVStatus(True)
        with patch.object(ctl,'connect',return_value=ctl.status), patch.object(ctl,'set_data_mode') as mode:
            self.assertTrue(connect_configured(ctl,{'auto_data_mode':False},{}).connected); mode.assert_not_called()

class AudioSafetyTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('psrtty.audio_engine.resolve_device',return_value=None))
    def send(self,engine,on,off,finished):
        return engine.send_text('TEST','AUTO',45.45,2125,2295,False,.35,on,off,finished)
    def test_ptt_failure_never_plays_audio(self):
        engine=AudioEngine(); done=Mock(); off=Mock()
        with patch('psrtty.audio_engine.sd') as sd:
            self.assertTrue(self.send(engine,lambda:False,off,done)[0]); engine.wait_tx(); sd.OutputStream.assert_not_called()
        self.assertFalse(done.call_args.args[0]); off.assert_called_once()
    def test_stop_during_leadin(self):
        engine=AudioEngine(); keyed=threading.Event(); off=Mock(); done=Mock()
        def on(): keyed.set(); return True
        with patch('psrtty.audio_engine.sd') as sd:
            self.send(engine,on,off,done); self.assertTrue(keyed.wait(1)); engine.stop_tx(); engine.wait_tx(); sd.OutputStream.assert_not_called()
        off.assert_called_once(); self.assertFalse(done.call_args.args[0])
    def test_success_and_double_send_guard(self):
        engine=AudioEngine(); done=Mock(); off=Mock()
        with patch('psrtty.audio_engine.sd'):
            self.assertTrue(self.send(engine,lambda:True,off,done)[0]); self.assertFalse(self.send(engine,lambda:True,off,done)[0]); engine.wait_tx()
        self.assertTrue(done.call_args.args[0]); off.assert_called_once()

class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name); self.root=self.base/'installed'; self.root.mkdir()
        for folder in ('config','logdata','var'):
            (self.root/folder).mkdir(); (self.root/folder/'mine.txt').write_bytes((folder+'-unique').encode())
        (self.root/'psrtty.exe').write_bytes(b'MZold'); create_manifest(self.root,'0.02')
        release=self.base/'PSRTTY_0.03'; release.mkdir(); (release/'psrtty.exe').write_bytes(b'MZnew'); create_manifest(release,'0.03')
        self.zip=self.base/'release.zip'
        with zipfile.ZipFile(self.zip,'w') as z:
            for name in ('psrtty.exe',MANIFEST): z.write(release/name,'PSRTTY_0.03/'+name)
    def tearDown(self): self.tmp.cleanup()
    def rewrite(self,edit):
        with zipfile.ZipFile(self.zip) as z: entries={i.filename:z.read(i) for i in z.infolist()}
        edit(entries)
        with zipfile.ZipFile(self.zip,'w') as z:
            for k,v in entries.items(): z.writestr(k,v)
    def test_version_comparison(self):
        for old,new in [('0.01','0.02'),('0.02','0.021'),('0.029','0.03'),('0.09','0.10'),('0.99','1.00')]: self.assertLess(version_key(old),version_key(new))
        self.assertEqual(version_key('0.020'),version_key('0.02'))
        for bad in ('2','0.2-beta','../../','0.0000001',None):
            with self.assertRaises(ValueError): version_key(bad)
    def test_new_only(self):
        self.assertEqual(inspect_zip(self.zip,'0.02')['version'],'0.03')
        for current in ('0.03','0.04'):
            with self.assertRaises(ValueError): inspect_zip(self.zip,current)
    def test_wrong_product(self):
        def edit(d):
            k='PSRTTY_0.03/'+MANIFEST; m=json.loads(d[k]); m['product']='PSLog'; d[k]=json.dumps(m)
        self.rewrite(edit)
        with self.assertRaises(ValueError): inspect_zip(self.zip,'0.02')
    def test_corrupt_hash(self):
        self.rewrite(lambda d:d.update({'PSRTTY_0.03/psrtty.exe':b'MZtampered'}))
        with self.assertRaises(ValueError): inspect_zip(self.zip,'0.02')
    def test_no_manifest(self):
        self.rewrite(lambda d:d.pop('PSRTTY_0.03/'+MANIFEST))
        with self.assertRaises(ValueError): inspect_zip(self.zip,'0.02')
    def test_user_data_in_zip_rejected(self):
        self.rewrite(lambda d:d.update({'PSRTTY_0.03/config/psrtty.json':b'{}'}))
        with self.assertRaises(ValueError): inspect_zip(self.zip,'0.02')
    def test_traversal_rejected(self):
        self.rewrite(lambda d:d.update({'../escape':b'bad'}))
        with self.assertRaises(ValueError): inspect_zip(self.zip,'0.02')
        self.assertFalse((self.base/'escape').exists())
    def test_success_backup_and_user_data_preservation(self):
        stage=prepare_update(self.zip,self.root,'0.02'); backup=apply_update(stage,self.root,'0.02')
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZnew'); self.assertEqual((backup/'psrtty.exe').read_bytes(),b'MZold')
        for folder in ('config','logdata','var'):
            expected=(folder+'-unique').encode(); self.assertEqual((self.root/folder/'mine.txt').read_bytes(),expected); self.assertEqual((backup/folder/'mine.txt').read_bytes(),expected)
        self.assertEqual(json.loads((stage/'result.json').read_text())['status'],'succeeded')
    def test_failed_second_replace_rolls_back(self):
        from psrtty.updater import _atomic_copy
        stage=prepare_update(self.zip,self.root,'0.02')
        def fail(source,target):
            if 'payload' in source.parts and target.name==Path(MANIFEST).name: raise OSError('simulated disk failure')
            _atomic_copy(source,target)
        with patch('psrtty.updater._atomic_copy',side_effect=fail):
            with self.assertRaises(RuntimeError): apply_update(stage,self.root,'0.02')
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZold'); self.assertEqual(json.loads((self.root/MANIFEST).read_text())['version'],'0.02')
        self.assertEqual(json.loads((stage/'result.json').read_text())['status'],'rolled_back')
    def test_backup_failure_does_not_touch_executable(self):
        stage=prepare_update(self.zip,self.root,'0.02')
        with patch('psrtty.updater.shutil.copytree',side_effect=OSError('disk full')):
            with self.assertRaises(OSError): apply_update(stage,self.root,'0.02')
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZold')
    def test_snapshot_not_original_is_applied(self):
        stage=prepare_update(self.zip,self.root,'0.02'); self.zip.write_bytes(b'changed'); apply_update(stage,self.root,'0.02')
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZnew')
    def test_changed_install_rejected(self):
        stage=prepare_update(self.zip,self.root,'0.02'); create_manifest(self.root,'0.04')
        with self.assertRaises(ValueError): apply_update(stage,self.root,'0.02')
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZold')
    def test_build_package_filename_and_validation(self):
        release=self.base/'PSRTTY_0.02'; release.mkdir(); (release/'psrtty.exe').write_bytes(b'MZbuild'); archive=package_release(release)
        self.assertEqual(archive.name,'PSRTTY_0.02.zip'); self.assertEqual(inspect_zip(archive,'0.01')['version'],__import__('psrtty').__version__)
    def test_migration_failure_restores_settings_and_program(self):
        stage=prepare_update(self.zip,self.root,'0.02')
        def fail(root,*args):
            (root/'config'/'mine.txt').write_bytes(b'changed')
            raise ValueError('migration failed')
        with patch('psrtty.updater.migrate_settings',side_effect=fail):
            with self.assertRaises(RuntimeError): apply_update(stage,self.root,'0.02')
        self.assertEqual((self.root/'config'/'mine.txt').read_bytes(),b'config-unique')
        self.assertEqual((self.root/'psrtty.exe').read_bytes(),b'MZold')
