import copy,json,socket,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from unittest.mock import Mock,patch
from psrtty.adif import QSORecord,adif_record
from psrtty.udp_adif import DEFAULT_OPTIONS,UdpError,options_checked,payload,send_qso
from psrtty.config import ConfigStore
from tests import test_ui_v02 as fixture

class Udp116Tests(unittest.TestCase):
    def qso(self):return QSORecord('JA1ABC',freq_hz=14085000,when_utc=datetime(2026,10,12,15,0,tzinfo=timezone(timedelta(hours=9))),sent='25',rcvd='001',station_callsign='JH1HST')
    def test_real_udp_receiver_gets_one_adif_qso(self):
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as receiver:
            try:receiver.bind(('127.0.0.1',0))
            except OSError as exc:self.skipTest(str(exc))
            receiver.settimeout(1);port=receiver.getsockname()[1]
            result=send_qso(self.qso(),{'enabled':True,'host':'127.0.0.1','port':port})
            data,_=receiver.recvfrom(65535)
            self.assertEqual(result,f'127.0.0.1:{port}');self.assertEqual(data,adif_record(self.qso()).encode('utf-8'))
            self.assertEqual(data.count(b'<EOR>'),1);self.assertIn(b'<MODE:4>RTTY',data);self.assertIn(b'<TIME_ON:6>060000',data);self.assertIn(b'<FREQ:6>14.085',data)
            receiver.settimeout(.02)
            with self.assertRaises(socket.timeout):receiver.recvfrom(65535)
    def test_disabled_never_opens_socket(self):
        with patch('psrtty.udp_adif.socket.socket') as opened:
            self.assertIsNone(send_qso(self.qso(),DEFAULT_OPTIONS));opened.assert_not_called()
    def test_strict_options_and_oversize(self):
        for options in ({'host':'bad'}, {'host':'localhost'}, {'port':0},{'port':65536},{'port':True},{'port':'2236'}):
            with self.assertRaises(UdpError):options_checked(options)
        q=self.qso();q.sent='あ'*30000
        with self.assertRaises(UdpError):payload(q)
    def test_ipv6_target_and_failed_send_no_retry(self):
        mocked=Mock();mocked.__enter__=Mock(return_value=mocked);mocked.__exit__=Mock(return_value=False);mocked.sendto.side_effect=OSError('network unavailable')
        with patch('psrtty.udp_adif.socket.socket',return_value=mocked) as opened:
            with self.assertRaises(OSError):send_qso(self.qso(),{'enabled':True,'host':'::1','port':2236})
        opened.assert_called_once_with(socket.AF_INET6,socket.SOCK_DGRAM);self.assertEqual(mocked.sendto.call_args.args[1],('::1',2236,0,0));self.assertEqual(mocked.sendto.call_count,1)
    def test_settings_round_trip_global_and_bad_file_reset(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'settings.json';m=Path(t)/'macros.json';s=ConfigStore(p,m)
            self.assertEqual(s.data['udp_adif'],DEFAULT_OPTIONS)
            value={'enabled':True,'host':'127.0.0.1','port':4567};s.data['udp_adif']=value;s.save();s=ConfigStore(p,m);self.assertEqual(s.data['udp_adif'],value)
            self.assertNotIn('udp_adif',s.data['profiles'][0])
            raw=json.loads(p.read_text());raw['udp_adif']['host']='bad';p.write_text(json.dumps(raw));self.assertEqual(ConfigStore(p,m).data['udp_adif'],DEFAULT_OPTIONS)

class UdpUI116Tests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    def enable(self):self.store.data['udp_adif']={'enabled':True,'host':'127.0.0.1','port':4567}
    def test_only_after_successful_local_qso_save(self):
        self.enable();w=self.window;w.q_call.setText('JA1ABC');w.current_freq_hz=14085000
        with patch('psrtty.udp_adif.send_qso',return_value='127.0.0.1:4567') as send,patch('psrtty.ui.integration_dialog.BackgroundJob',side_effect=lambda p,work,done:done(work(),None)):
            w._add_qso();self.assertEqual(send.call_count,1);self.assertEqual(send.call_args.args[0].call,'JA1ABC');self.assertEqual(w.integration.udp_pending,0)
            w.adif.append.side_effect=OSError('disk full');w.q_call.setText('JA2ABC')
            with patch('psrtty.ui.main_window.QMessageBox.warning'):w._add_qso()
            self.assertEqual(send.call_count,1)
    def test_send_failure_preserves_saved_qso_and_is_not_modal(self):
        self.enable();w=self.window;w.q_call.setText('JA1ABC');w.current_freq_hz=14085000
        from psrtty.adif import ADIFLog
        w.adif=ADIFLog(Path(self.tmp.name)/'saved-log');w.qsos=[]
        def job(parent,work,done):
            try:result=work()
            except Exception as exc:done(None,exc)
            else:done(result,None)
        with patch('psrtty.udp_adif.send_qso',side_effect=OSError('fail')),patch('psrtty.ui.integration_dialog.BackgroundJob',side_effect=job):w._add_qso()
        self.assertEqual(len(w.qsos),1);self.assertEqual(w.adif.load_recent()[0].call,'JA1ABC');self.assertIn('fail',w.integration.udp_status);self.assertEqual(w.integration.udp_pending,0)
    def test_busy_hamlog_does_not_block_udp(self):
        self.enable();ctl=self.window.integration;ctl.busy=True
        with patch('psrtty.udp_adif.send_qso',return_value='127.0.0.1:4567') as send,patch('psrtty.ui.integration_dialog.BackgroundJob',side_effect=lambda p,work,done:done(work(),None)):
            ctl.record(QSORecord('JA1ABC',when_utc=datetime.now(timezone.utc)));send.assert_called_once()
        ctl.busy=False
    def test_dialog_save_invalid_and_cancel(self):
        from psrtty.ui.udp_adif_dialog import UdpAdifDialog
        d=UdpAdifDialog(self.window.integration,self.window);d.enabled.setChecked(True);d.host.setText('127.0.0.1');d.port.setValue(4567);d.save()
        self.assertEqual(self.store.data['udp_adif'],{'enabled':True,'host':'127.0.0.1','port':4567})
        d=UdpAdifDialog(self.window.integration,self.window);before=copy.deepcopy(self.store.data['udp_adif']);d.host.setText('bad')
        with patch('psrtty.ui.udp_adif_dialog.QMessageBox.warning') as warning:d.save();warning.assert_called_once()
        self.assertEqual(self.store.data['udp_adif'],before);d.reject();self.assertEqual(self.store.data['udp_adif'],before)
    def test_menu_and_eight_language_guidance(self):
        from psrtty import i18n
        from psrtty.ui.udp_adif_dialog import UdpAdifDialog
        self.assertTrue(any(a.text()==i18n.tr('udp.title') for menu in self.window.top_level_menus for a in menu.actions()))
        for code in i18n.LANGUAGES:
            i18n.configure(code);d=UdpAdifDialog(self.window.integration,self.window);self.assertEqual(d.windowTitle(),i18n.tr('udp.title'));self.assertIn('ADIF MESSAGE',i18n.tr('udp.guide'));self.assertIn('ADIF UDP',i18n.tr('guide.8.body'));d.close()
        i18n.configure('ja')
