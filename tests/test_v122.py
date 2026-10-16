"""FSK connection ownership, startup ordering and PTT isolation."""
import copy
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from psrtty import i18n
from psrtty.audio_engine import AudioEngine
from psrtty.civ import CIVController, CIVStatus, connect_configured
from psrtty.config import DEFAULT_CONFIG
from psrtty.external_ptt import ExternalPTT
from psrtty.fsk import SerialKey, prepare_connection, release_connection, start_fsk, borrow_for_ptt_test
from psrtty.hamlib_radio import HamlibController
from psrtty.tx_keying import keying_callbacks


class Port122Tests(unittest.TestCase):
    def setUp(self):
        i18n.configure('ja')
        self.addCleanup(i18n.configure, 'ja')
        self.settle=patch('psrtty.fsk.PORT_SETTLE_SECONDS',0.)
        self.settle.start();self.addCleanup(self.settle.stop)
        self.ctl=HamlibController('FT-991 / FT-991A')
        self.ctl.handle=1;self.ctl.lib=Mock();self.ctl.status=CIVStatus(True,'COM3')
        self.ctl.read_transmitting=Mock(return_value=False)
        self.ctl.set_fsk_mode=Mock(return_value=True)
        self.radio=dict(DEFAULT_CONFIG['radio'],model=self.ctl.model,com_port='COM3',ptt='CAT',tx_method='fsk')
        self.options=dict(DEFAULT_CONFIG['fsk'],port='COM4')
        self.ext=copy.deepcopy(DEFAULT_CONFIG['external'])
        self.addCleanup(release_connection,self.ctl)

    def send(self, on=None, off=None):
        engine=AudioEngine();on=on or Mock(return_value=True);off=off or Mock(return_value=True);done=Mock()
        self.assertTrue(start_fsk(engine,self.ctl,self.radio,self.options,DEFAULT_CONFIG['advanced'],on,off,done,text='RY',external=self.ext)[0])
        engine._tx_thread.join(2)
        self.assertFalse(engine._tx_thread.is_alive())
        return done,on,off

    def test_connect_prepares_port_and_repeated_send_reuses_until_disconnect(self):
        device=Mock(is_open=True)
        self.ctl.connect=Mock(return_value=self.ctl.status)
        with patch('serial.Serial',return_value=device) as opening,patch('psrtty.fsk.BitClock'):
            status=connect_configured(self.ctl,self.radio,DEFAULT_CONFIG['advanced'],self.options,self.ext)
            self.assertTrue(status.connected)
            self.ctl.lib.rig_set_ptt.assert_not_called()
            for _ in range(3):
                done,on,off=self.send();self.assertTrue(done.call_args.args[0]);on.assert_called_once();off.assert_called_once()
            opening.assert_called_once();device.open.assert_called_once();device.close.assert_not_called()
            self.ctl.disconnect();device.close.assert_called_once()
            self.assertIsNone(self.ctl._fsk_key_session)

    def test_fallback_checks_mode_before_port_and_never_reopens_on_resend(self):
        events=[];device=Mock(is_open=True)
        self.ctl.set_fsk_mode.side_effect=lambda *a,**k:events.append('mode') or True
        device.open.side_effect=lambda:events.append('open')
        on=Mock(side_effect=lambda:events.append('ptt') or True)
        with patch('serial.Serial',return_value=device) as opening,patch('psrtty.fsk.BitClock'):
            for _ in range(2):self.assertTrue(self.send(on=on)[0].call_args.args[0])
            self.assertEqual(events,['mode','open','ptt','mode','ptt'])
            opening.assert_called_once();device.close.assert_not_called()

    def test_mode_failure_neither_opens_port_nor_sends_ptt_off(self):
        self.ctl.set_fsk_mode.return_value=False
        with patch('serial.Serial') as opening:
            done,on,off=self.send()
            opening.assert_not_called();on.assert_not_called();off.assert_not_called()
            self.assertFalse(done.call_args.args[0]);self.assertIn('RTTYモード確認',done.call_args.args[1])

    def test_initialization_ptt_pulse_must_return_to_rx_before_real_ptt(self):
        device=Mock(is_open=True);readings=iter([True,False])
        self.ctl.read_transmitting.side_effect=lambda:next(readings,False)
        def on():
            self.assertFalse(self.ctl.read_transmitting())
            return True
        with patch('serial.Serial',return_value=device),patch('psrtty.fsk.BitClock'):
            done,_,_=self.send(on=Mock(side_effect=on))
            self.assertTrue(done.call_args.args[0])
            self.assertIn('receive_after_port',self.ctl.fsk_start_diagnostic['events'])

    def test_sustained_or_unknown_tx_after_open_never_starts_or_forces_rx(self):
        for state in (True,None):
            release_connection(self.ctl)
            self.ctl.read_transmitting.side_effect=None;self.ctl.read_transmitting.return_value=state
            with patch('serial.Serial',return_value=Mock(is_open=True)),patch('psrtty.fsk.BitClock') as clock:
                done,on,off=self.send()
                on.assert_not_called();off.assert_not_called();clock.assert_not_called()
                self.assertFalse(done.call_args.args[0]);self.assertIn('受信確認',done.call_args.args[1])
                self.assertEqual(self.ctl.fsk_start_diagnostic['stage'],'receive')

    def test_cancel_while_initializing_never_keys_and_retains_port_until_disconnect(self):
        device=Mock(is_open=True);engine=AudioEngine();done=Mock();on=Mock();off=Mock()
        device.open.side_effect=engine.stop_tx
        with patch('serial.Serial',return_value=device),patch('psrtty.fsk.BitClock') as clock:
            self.assertTrue(start_fsk(engine,self.ctl,self.radio,self.options,DEFAULT_CONFIG['advanced'],on,off,done,text='RY')[0])
            engine._tx_thread.join(2)
            self.assertFalse(engine._tx_thread.is_alive());on.assert_not_called();off.assert_not_called();clock.assert_not_called()
            device.close.assert_not_called();self.ctl.disconnect();device.close.assert_called_once()

    def test_disconnect_releases_even_when_device_is_unplugged(self):
        device=Mock(is_open=True)
        with patch('serial.Serial',return_value=device):prepare_connection(self.ctl,self.radio,self.options,self.ext)
        device.close.side_effect=OSError('unplugged')
        self.ctl.disconnect()
        self.assertFalse(self.ctl.status.connected);self.assertIsNone(self.ctl._fsk_key_session)
        self.assertIsNone(self.ctl.handle);device.close.assert_called_once()

    def test_port_or_line_change_releases_old_session_before_new_open(self):
        devices=[Mock(is_open=True),Mock(is_open=True),Mock(is_open=True)]
        with patch('serial.Serial',side_effect=devices):
            prepare_connection(self.ctl,self.radio,self.options,self.ext)
            self.options['port']='COM5';prepare_connection(self.ctl,self.radio,self.options,self.ext)
            devices[0].close.assert_called_once();devices[1].close.assert_not_called()
            self.options['line']='RTS';prepare_connection(self.ctl,self.radio,self.options,self.ext)
            devices[1].close.assert_called_once();devices[2].close.assert_not_called()

    def test_polarity_and_ptt_idle_are_set_before_open(self):
        device=Mock(is_open=True)
        self.options['invert']=True
        self.ext.update(enabled=True,com_port='COM4',line='RTS',role='ptt',reversed=True)
        def opening():self.assertTrue(device.dtr);self.assertTrue(device.rts)
        device.open.side_effect=opening
        with patch('serial.Serial',return_value=device):prepare_connection(self.ctl,self.radio,self.options,self.ext)
        self.assertTrue(device.dtr);self.assertTrue(device.rts)

    def test_external_ptt_shares_persistent_fsk_port_and_releases_each_tx(self):
        self.radio['ptt']='外部接続'
        self.ext.update(enabled=True,com_port='COM4',line='RTS',role='ptt',reversed=False)
        device=Mock(is_open=True)
        with patch('serial.Serial',return_value=device) as opening,patch('psrtty.fsk.BitClock'):
            prepare_connection(self.ctl,self.radio,self.options,self.ext)
            for _ in range(2):
                engine=AudioEngine();seq=ExternalPTT(self.ext,'COM3',engine._tx_cancel);done=Mock()
                on,off=keying_callbacks(self.ctl,'外部接続',seq,lambda:True)
                self.assertTrue(start_fsk(engine,self.ctl,self.radio,self.options,DEFAULT_CONFIG['advanced'],on,off,done,text='RY',external=self.ext,sequencer=seq)[0])
                engine._tx_thread.join(2);self.assertFalse(engine._tx_thread.is_alive());self.assertTrue(done.call_args.args[0])
                self.assertFalse(device.rts);self.assertFalse(self.ctl.external_transmitting)
            opening.assert_called_once();device.close.assert_not_called()

    def test_external_ptt_test_borrows_held_port_and_rejects_key_line(self):
        device=Mock(is_open=True)
        self.ext.update(enabled=True,com_port='COM4',line='RTS',role='ptt',reversed=False)
        with patch('serial.Serial',return_value=device) as opening:
            prepare_connection(self.ctl,self.radio,self.options,self.ext)
            seq=ExternalPTT(self.ext,'COM3')
            seq.borrowed_serial=borrow_for_ptt_test(self.ctl,self.ext)
            self.assertIs(seq.borrowed_serial,device)
            self.assertTrue(seq.before_ptt());self.assertTrue(device.rts)
            seq.after_ptt();self.assertFalse(device.rts)
            opening.assert_called_once();device.close.assert_not_called()
            for change in ({'line':'DTR'},{'reversed':True}):
                with self.assertRaises(ValueError):borrow_for_ptt_test(self.ctl,dict(self.ext,**change))
            self.assertIsNone(borrow_for_ptt_test(self.ctl,dict(self.ext,com_port='COM7')))

    def test_settings_external_ptt_button_uses_the_held_interface(self):
        from psrtty.ui.settings_dialog import SettingsDialog
        device=Mock(is_open=True)
        self.ext.update(enabled=True,com_port='COM4',line='RTS',role='ptt',reversed=False)
        parent=SimpleNamespace(radio=self.ctl)
        dialog=SimpleNamespace(parent=lambda:parent,tx_testing=False,test_pending=False,test_controller=None,
            _stop_external_test=Mock(),_external_values=lambda:self.ext,rig=Mock(),com=Mock(),
            external_test_status=Mock(),external_test_timer=Mock())
        dialog.rig.currentData.return_value=self.ctl.model;dialog.com.currentData.return_value='COM3'
        with patch('serial.Serial',return_value=device) as opening:
            prepare_connection(self.ctl,self.radio,self.options,self.ext)
            SettingsDialog._start_external_test(dialog)
            self.assertIs(dialog._external_test.borrowed_serial,device)
            self.assertTrue(device.rts);dialog.external_test_timer.start.assert_called_once_with(3000)
            dialog._external_test.after_ptt();self.assertFalse(device.rts)
            opening.assert_called_once();device.close.assert_not_called()

    def test_icom_shared_cat_port_is_never_owned_by_fsk(self):
        ctl=CIVController(0x94,model='IC-7300');ctl.status.connected=True;ctl.ser=Mock()
        radio=dict(self.radio,model='IC-7300',ptt='CI-V');options=dict(self.options,port='RADIO')
        with patch('serial.Serial') as opening:
            key=SerialKey(ctl,radio,options);key.open();key.close();release_connection(ctl)
            opening.assert_not_called();ctl.ser.close.assert_not_called()
            ctl.disconnect();self.assertIsNone(ctl.ser)

    def test_connection_initialization_failure_closes_all_ports(self):
        self.ctl.connect=Mock(return_value=self.ctl.status)
        device=Mock(is_open=True);device.open.side_effect=OSError('COM4 unavailable')
        with patch('serial.Serial',return_value=device):
            status=connect_configured(self.ctl,self.radio,DEFAULT_CONFIG['advanced'],self.options,self.ext)
            self.assertFalse(status.connected);self.assertIn('COM4 unavailable',status.message)
            self.assertIsNone(self.ctl._fsk_key_session);self.assertIsNone(self.ctl.handle)
            device.close.assert_called_once()

    def test_afsk_connection_does_not_prepare_fsk_port(self):
        self.ctl.connect=Mock(return_value=self.ctl.status);self.ctl.set_data_mode=Mock(return_value=True)
        with patch('serial.Serial') as opening:
            status=connect_configured(self.ctl,dict(self.radio,tx_method='afsk'),DEFAULT_CONFIG['advanced'],self.options,self.ext)
            self.assertTrue(status.connected);opening.assert_not_called()

    def test_stop_then_resend_reuses_port_and_releases_ptt(self):
        device=Mock(is_open=True);engine=AudioEngine();done=Mock();on=Mock(return_value=True);off=Mock(return_value=True)
        def stop(code):engine.stop_tx();return False
        with patch('serial.Serial',return_value=device) as opening,patch('psrtty.fsk.BitClock') as clock:
            clock.return_value.code.side_effect=stop
            self.assertTrue(start_fsk(engine,self.ctl,self.radio,self.options,DEFAULT_CONFIG['advanced'],on,off,done,text='RY')[0])
            engine._tx_thread.join(2);self.assertFalse(engine._tx_thread.is_alive())
            self.assertFalse(done.call_args.args[0]);off.assert_called_once();device.close.assert_not_called()
            clock.return_value.code.side_effect=None
            self.assertTrue(self.send()[0].call_args.args[0]);opening.assert_called_once()

    def test_ptt_start_failure_releases_ptt_and_keeps_port(self):
        device=Mock(is_open=True)
        with patch('serial.Serial',return_value=device),patch('psrtty.fsk.BitClock') as clock:
            done,on,off=self.send(on=Mock(return_value=False))
            on.assert_called_once();off.assert_called_once();clock.assert_not_called()
            self.assertFalse(done.call_args.args[0]);device.close.assert_not_called()
            self.assertEqual(self.ctl.fsk_start_diagnostic['stage'],'ptt')

    def test_connected_profile_has_its_own_session(self):
        device1=Mock(is_open=True);device2=Mock(is_open=True)
        other=HamlibController('FT-891');other.handle=2;other.lib=Mock();other.status=CIVStatus(True,'COM5')
        other.read_transmitting=Mock(return_value=False)
        with patch('serial.Serial',side_effect=[device1,device2]):
            prepare_connection(self.ctl,self.radio,self.options,self.ext)
            self.ctl.disconnect();device1.close.assert_called_once()
            prepare_connection(other,dict(self.radio,model='FT-891',com_port='COM5'),dict(self.options,port='COM6'),self.ext)
            self.assertIs(other._fsk_key_session[0],device2);self.assertIsNone(self.ctl._fsk_key_session)
            other.disconnect();device2.close.assert_called_once()

    def test_all_eight_languages_have_startup_error_stages(self):
        for lang in i18n.LANGUAGES:
            i18n.configure(lang)
            for suffix in ('cancelled','receive_failed','stage_mode','stage_port','stage_receive','stage_ptt','stage_keying'):
                self.assertNotEqual(i18n.tr('v122.'+suffix),'v122.'+suffix)


if __name__=='__main__':unittest.main()
