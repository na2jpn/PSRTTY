"""RIT protocol/state isolation, external club data, and explicit card selection."""
import ctypes
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from psrtty import i18n
from psrtty.parser import card_callsign
from psrtty.card_entity import entity_name
from psrtty.club_database import load_clubs
from psrtty.civ import CIVController,CIVStatus
from psrtty.hamlib_radio import HamlibController,VFO
from tests.test_ui_v02 import UITests as _Fixture


class Protocol127Tests(unittest.TestCase):
    def tearDown(self):i18n.configure('ja')

    def test_card_unique_noise_repeats_and_no_embedded_repair(self):
        for text,expected in [('JA1ABC','JA1ABC'),('JA1ABC JA1ABC','JA1ABC'),
          ('VHKJHT JA1ABC !#H1HST','JA1ABC'),('JH1HST/1 JH1HST/1','JH1HST/1'),
          ('JGIUUYFJH1HSTUH＃',''),('!#H1HST',''),('JA1ABC W1AW',''),
          ('JA1ABC/INVALID',''),('CQ DE JA1ABC','JA1ABC')]:
            self.assertEqual(card_callsign(text),expected,text)
        self.assertEqual(card_callsign('JH1HST JH1HST','JH1HST'),'JH1HST')
        self.assertEqual(card_callsign('VHKJHT JH1HST !#H1HST','JH1HST'),'JH1HST')

    def test_country_localized_and_ambiguous_sites_blank(self):
        for language in i18n.LANGUAGES:
            i18n.configure(language);self.assertTrue(entity_name('JA1ABC'))
        i18n.configure('ja');self.assertEqual(entity_name('JA1ABC'),'日本')
        for call in ['JH1HST/JD1','JD1ABC','JA1ABC/MM','JA1ABC/AM','garbage']:
            self.assertEqual(entity_name(call),'',call)
        self.assertEqual(entity_name('JA1ABC/1'),'日本')

    def test_external_csv_bom_invalid_rows_and_updated_date(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);csv=root/'club_db.csv'
            csv.write_text('number,name\n0123,テストクラブ\n0123,重複\n!,不正\n0456,第二\n',encoding='utf-8-sig')
            (root/'club_db_meta.json').write_text(json.dumps({'checked_at':'2026-10-19','sha256':hashlib.sha256(csv.read_bytes()).hexdigest()}))
            rows,date,bad=load_clubs(root)
            self.assertEqual(rows,[('0123','テストクラブ'),('0456','第二')]);self.assertEqual(date,'2026-10-19');self.assertTrue(bad)
            csv.write_text('number,name\n9999,変更\n',encoding='utf-8')
            self.assertEqual(load_clubs(root)[1],'')
            csv.write_bytes(b'\xff\xfe\xff');self.assertEqual(load_clubs(root),([], '', True))
            csv.write_text('wrong,headers\n1,foo\n');self.assertTrue(load_clubs(root)[2])

    def icom(self):
        c=CIVController(0x94,model='IC-7300');c.ser=Mock();c.status=CIVStatus(connected=True)
        return c

    def test_icom_read_bcd_sign_flag_and_no_setting_write(self):
        c=self.icom()
        with patch('psrtty.rit._icom_query',side_effect=[bytes((0x34,0x12,1)),b'\x01',b'\x00']):
            state=c.read_rit()
        self.assertEqual(state['offset'],-1234);self.assertTrue(state['on']);c.ser.write.assert_not_called()
        with patch('psrtty.rit._icom_query',return_value=bytes((0xFA,0x12,0))):self.assertIsNone(c.read_rit())

    def test_icom_write_only_explicit_request_with_readback_and_rx_guard(self):
        c=self.icom();before=dict(offset=120,on=True,limit=9999,offset_write=True,on_write=True)
        with patch.object(c,'read_transmitting',return_value=False),patch('psrtty.rit.icom_read_rit',side_effect=[before,{**before,'offset':-345}]),patch.object(c,'_read_response',return_value=b'\xfe\xfe\xe0\x94\xfb\xfd'):
            self.assertTrue(c.set_rit(offset=-345))
        self.assertEqual(c.ser.write.call_args.args[0],c._frame(0x21,0,0x45,0x03,1))
        c.ser.write.reset_mock()
        with patch.object(c,'read_transmitting',return_value=True):self.assertFalse(c.set_rit(offset=1))
        c.ser.write.assert_not_called()

    def test_icom_xit_blocks_shared_offset(self):
        c=self.icom()
        with patch('psrtty.rit._icom_query',side_effect=[b'\x00\x00\x00',b'\x01',b'\x01']):
            s=c.read_rit();self.assertFalse(s['offset_write']);self.assertTrue(s['xit'])

    def hamlib(self):
        c=HamlibController('FT-991 / FT-991A');c.handle=1;c.status=CIVStatus(connected=True);c.lib=Mock()
        c.lib.rig_get_rit.side_effect=lambda h,v,p:(setattr(ctypes.cast(p,ctypes.POINTER(ctypes.c_long)).contents,'value',-120) or 0)
        c.lib.rig_get_func.side_effect=lambda h,v,f,p:(setattr(ctypes.cast(p,ctypes.POINTER(ctypes.c_int)).contents,'value',1 if f==1<<24 else 0) or 0)
        c.lib.rig_has_set_func.return_value=1<<24;c.lib.rig_parse_func.return_value=1<<30
        return c

    def test_hamlib_read_does_not_write_and_requires_success(self):
        c=self.hamlib();s=c.read_rit();self.assertEqual(s['offset'],-120);self.assertTrue(s['on'])
        c.lib.rig_set_rit.assert_not_called();c.lib.rig_set_func.assert_not_called()
        c.lib.rig_get_rit.side_effect=None;c.lib.rig_get_rit.return_value=-4;self.assertIsNone(c.read_rit())

    def test_hamlib_zero_reset_preserves_on_state(self):
        c=self.hamlib();state=dict(offset=100,on=True,limit=9999,offset_write=True,on_write=True)
        c.lib.rig_set_rit.return_value=0;c.lib.rig_set_func.return_value=0
        with patch.object(c,'read_transmitting',return_value=False),patch('psrtty.rit.hamlib_read_rit',side_effect=[state,{**state,'offset':0}]):
            self.assertTrue(c.set_rit(offset=0))
        c.lib.rig_set_rit.assert_called_once_with(1,VFO,0)
        c.lib.rig_set_func.assert_called_once_with(1,VFO,1<<24,1)


class UI127Tests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def connected(self):
        w=self.window;w.store.data['radio'].update(model='IC-7300',civ_address='94')
        # These tests mock RIT only. Do not let the unrelated 250-ms meter
        # poll seize the CAT lock while asserting an immediate RIT poll.
        # RIT deferral for occupied CAT is covered explicitly in FIX1 tests.
        w.printer_timer.stop()
        c=CIVController(0x94,model='IC-7300');c.status=CIVStatus(connected=True,frequency_hz=7045000)
        c.read_rit=Mock(return_value=dict(offset=125,on=True,limit=9999,offset_write=True,on_write=True,xit=False))
        c.set_rit=Mock(return_value=True);w.radio=c;w.current_freq_hz=7045000
        return w,c

    def test_card_click_and_country_share_candidate(self):
        w=self.window;card=w._add_card('VHKJHT JA1ABC JA1ABC !#H1HST','RX')
        self.assertEqual(card.entity_label.text(),'日本')
        card.clicked.emit(card.text_value);self.assertEqual(w.q_call.text(),'JA1ABC')
        card=w._add_card('JA1ABC W1AW','RX');self.assertTrue(card.entity_label.isHidden())
        tx=w._add_card('JA1ABC','TX');self.assertTrue(tx.entity_label.isHidden())

    def test_connection_reads_without_open_window_or_writes(self):
        w,c=self.connected();w.rit_service.tick();self.pump(.06)
        self.assertEqual(w.rit_service.state['offset'],125);self.assertIsNone(w.rit_window)
        c.set_rit.assert_not_called()
        w.rit_service.last_poll=0;c.read_rit.return_value.update(offset=-350,on=False)
        w.rit_service.tick();self.pump(.06);self.assertEqual(w.rit_service.state['offset'],-350)

    def test_rit_window_survives_control_close_and_is_single_instance(self):
        w,c=self.connected();w._show_rit();self.pump(.06);w._show_control();self.pump(.02)
        self.assertTrue(w.control_window.rit_button.isEnabled())
        rit=w.rit_window;w.control_window.close();self.assertTrue(rit.isVisible())
        w._show_rit();self.assertIs(w.rit_window,rit);c.set_rit.assert_not_called()
        w.disconnect_radio();self.assertFalse(rit.slider.isEnabled());self.assertIsNone(w.rit_service.state)

    def test_tx_and_stale_connection_cannot_update_rit(self):
        w,c=self.connected();w.active_tx_id=42;w.rit_service.tick();c.read_rit.assert_not_called()
        w.active_tx_id=None
        captured=[]
        class Job:
            def __init__(self,parent,work,done):captured.extend([work,done])
        with patch('psrtty.ui.rit_window.BackgroundJob',Job):w.rit_service.tick()
        w.connection_generation+=1;w.rit_service.invalidate()
        captured[1]((dict(offset=999),True),None);self.assertIsNone(w.rit_service.state)

    def test_explicit_rit_action_is_read_back_and_tx_cannot_change_it(self):
        w,c=self.connected();w._show_rit();self.pump(.08)
        state=c.read_rit.return_value
        def write(**change):
            state.update(change);return True
        c.set_rit.side_effect=write
        w.rit_window.zero.click();self.pump(.12)
        c.set_rit.assert_called_once_with(offset=0)
        self.assertEqual(w.rit_window.value.text(),'+0 Hz')
        self.assertTrue(w.rit_window.on.isChecked())
        w.active_tx_id=42;w.rit_service.request(offset=900);self.pump(.12)
        self.assertEqual(c.set_rit.call_count,1)
        w.active_tx_id=None

    def test_corrupt_club_list_keeps_manual_entry_available(self):
        from psrtty.ui.cabrillo_dialog import CabrilloDialog
        with patch('psrtty.club_database.load_clubs',return_value=([], '', True)):
            d=CabrilloDialog(self.window.adif,self.window.store)
        self.assertEqual(d.club_choices.count(),1)
        self.assertIn('読み込めません',d.club_note.text())
        d.set_value('CLUB','99-4-123');self.assertEqual(d.fields['CLUB'].text(),'99-4-123')
        d.close();d.deleteLater()

    def test_direct_tx_waits_for_rit_and_stop_cancels_retry(self):
        from psrtty.ui.direct_tx import DirectTxWindow
        w=self.window;d=DirectTxWindow(w);w.direct_window=d;d.show()
        d.auto.setChecked(False);d.editor.setPlainText('CQ')
        w.rit_service.busy=True
        with patch.object(w,'_send_text',return_value=True) as send:
            d.start();send.assert_not_called();self.assertTrue(d.rit_retry.isActive())
            w.rit_service.busy=False;self.pump(.08);send.assert_called_once()
            d.session=None;w.rit_service.busy=True;send.reset_mock()
            d.start();d.stop();w.rit_service.busy=False;self.pump(.08);send.assert_not_called()
        d.close()

    def test_latest_qso_caption_translated(self):
        for code in i18n.LANGUAGES:
            i18n.configure(code);self.assertNotIn('ui.',i18n.tr('ui.df6b49184a0fd279'))
        i18n.configure('ja');self.assertEqual(i18n.tr('ui.df6b49184a0fd279'),'最新のQSO（ダブルクリックで詳細を開く）')

# Do not run the imported fixture's own tests again in this module.
del _Fixture
