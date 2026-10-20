import io
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from scipy.signal import hilbert,lfilter
from psrtty.ry_spots import Spot,SpotCache,age_color,band_for,parse_telnet,parse_jcluster,short_frequency
from psrtty.ry_radar import RadarFeeds,TelnetText,load_sources,bounded_io
from psrtty.ry_skimmer import FIRDecimator,SkimmerEngine,SkimmerWorker,dial_for_mark
from tests.test_ui_v02 import UITests as _Fixture


class RadarDataTests(unittest.TestCase):
    def test_call_band_newest_only_and_multiop(self):
        c=SpotCache();now=10000
        self.assertTrue(c.put(Spot('JA1ABC',7070000,now-1500,'one'),now))
        self.assertFalse(c.put(Spot('JA1ABC',7071000,now-1500,'two'),now))
        self.assertFalse(c.put(Spot('JA1ABC',7072000,now-1501,'two'),now))
        self.assertTrue(c.put(Spot('JA1ABC',7073000,now-1,'two'),now))
        self.assertTrue(c.put(Spot('JA1ABC',14085000,now-10,'two'),now))
        self.assertEqual(len(c.rows),2);self.assertEqual(c.rows['JA1ABC',7].hz,7073000)
        self.assertEqual(age_color(now-c.rows['JA1ABC',7].stamp),'#cf2424')

    def test_retention_clock_and_invalid_calls(self):
        c=SpotCache();now=10000
        for spot in (Spot('JA1ABC',7070000,now-1800),Spot('JA1ABC',7070000,now+1),
                     Spot('JUNK',7070000,now),Spot('JA1ABC',9000000,now)):
            self.assertFalse(c.put(spot,now))
        c.put(Spot('JA1ABC',7070000,now),now);c.expire(now+1799);self.assertEqual(len(c.rows),1)
        c.expire(now+1800);self.assertFalse(c.rows)

    def test_all_age_boundaries_and_frequency(self):
        for sec,color in [(0,'#cf2424'),(179,'#cf2424'),(180,'#d44831'),(360,'#ad557b'),(720,'#aa6a2c'),(1440,'#727272'),(1799,'#727272'),(1800,None)]:
            self.assertEqual(age_color(sec),color)
        self.assertEqual(short_frequency(21078000),'.078');self.assertEqual(short_frequency(21079820),'.07982')
        self.assertEqual(band_for(1900000),1.8);self.assertEqual(band_for(1296000000),1200)

    def test_telnet_requires_explicit_rtty_and_utc_rollover(self):
        now=datetime(2026,10,20,0,1,tzinfo=timezone.utc)
        base='DX de W3LPL-#: 14085.0 JA1ABC {} 2359Z'
        spot=parse_telnet(base.format('RTTY 12 dB 45 BPS CQ'),'RBN',now)
        self.assertEqual(spot.hz,14085000);self.assertEqual(datetime.fromtimestamp(spot.stamp,timezone.utc).day,19)
        for desc in ('CW','FT8','CQ','RTTY FT4','NOTRTTY'):
            self.assertIsNone(parse_telnet(base.format(desc),'RBN',now))

    def test_xml_timezone_and_strict_mode(self):
        def xml(mode):return f'''<?xml version="1.0" encoding="UTF-8"?><List><Spot ID="1"><Date>2026/10/20</Date><Time>12:30</Time><TimeZone>+9:00</TimeZone><Freq>21078.5</Freq><Mode>{mode}</Mode><SpotStation><CallSign>JA1ABC</CallSign></SpotStation><ReportStation><CallSign>JA2XYZ</CallSign></ReportStation><Message>CQ</Message></Spot></List>'''.encode()
        s=parse_jcluster(xml('RTTY'))[0]
        self.assertEqual(s.hz,21078500);self.assertEqual(datetime.fromtimestamp(s.stamp,timezone.utc).hour,3)
        self.assertFalse(parse_jcluster(xml('FT8')))
        with self.assertRaises(ValueError):parse_jcluster(b'<!ENTITY x "abc"><List/>')
        with self.assertRaises(ValueError):parse_jcluster(b'x'*2000001)

    def test_telnet_negotiation_split_at_every_byte(self):
        p=TelnetText();text='';reply=b''
        for b in b'Login:\xff\xfb\x01\xff\xfa\x01abcd\xff\xf0\xff\xfd\x03':
            t,r=p.feed(bytes([b]));text+=t;reply+=r
        self.assertEqual(text,'Login:');self.assertEqual(reply,b'\xff\xfe\x01\xff\xfc\x03')

    def test_external_sources_preserved_and_bad_entry_identified(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'config/sources.json';data=load_sources(p)
            self.assertEqual(len(data['rbn']),5);self.assertEqual(len(data['clusters']),3)
            self.assertEqual(data['dwell'],60);self.assertEqual(data['clusters'][0]['interval'],90)
            self.assertEqual(data['rbn'][2]['host'],'telnet.reversebeacon.net')
            p.write_text('{bad',encoding='utf-8');raw=p.read_bytes()
            with self.assertRaises(ValueError):load_sources(p)
            self.assertEqual(p.read_bytes(),raw)
            data['rbn'][2]['port']=0;p.write_text(json.dumps(data),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,r'rbn\[2\]'):load_sources(p)

    def test_cycle_visits_five_in_order_and_waits_sixty_seconds(self):
        nodes=[dict(name=str(i)) for i in range(5)]
        f=RadarFeeds({'rbn':nodes,'clusters':[],'dwell':60},'JX1XXX');seen=[]
        def session(s,end):
            seen.append(s['name'])
            if len(seen)==5:f.stop_event.set()
        f._telnet=session
        with patch.object(f.stop_event,'wait',return_value=False) as wait,patch('psrtty.ry_radar.time.monotonic',return_value=100):f._cycle()
        self.assertEqual(seen,list('01234'));self.assertTrue(all(c.args==(60,) for c in wait.call_args_list))

    def test_prompt_without_newline_and_read_only_session(self):
        class Sock:
            def __init__(self):self.parts=[b'login:',b'\r\nDX de W3LPL: 14085 JA1ABC RTTY 1200Z\r\n',b''];self.sent=[]
            def settimeout(self,v):pass
            def recv(self,n):return self.parts.pop(0)
            def sendall(self,b):self.sent.append(b)
            def close(self):pass
        s=Sock();f=RadarFeeds({'rbn':[],'clusters':[]},'JX1XXX',connector=lambda *a,**k:s)
        f._telnet(dict(name='node',host='example.org',port=7300))
        self.assertEqual(s.sent,[b'JX1XXX\r\n']);self.assertFalse(f.sockets)
        events=list(f.events.queue);self.assertTrue(any(e[0]=='spot' for e in events))

    def test_cancelled_dns_caller_returns_and_late_socket_is_closed(self):
        gate=threading.Event();stop=threading.Event();stop.set();sock=Mock();done=threading.Event()
        def dial():gate.wait(.5);return sock
        def close(value):value.close();done.set()
        with self.assertRaises(TimeoutError):bounded_io(('unit','slow'),dial,stop,.05,close)
        with self.assertRaises(TimeoutError):bounded_io(('unit','slow'),dial,stop,.05,close)
        gate.set();self.assertTrue(done.wait(.5));sock.close.assert_called_once()


class IQTests(unittest.TestCase):
    def test_polyphase_preserves_arbitrary_block_boundaries(self):
        x=(np.random.default_rng(5).normal(size=15007)+1j*np.random.default_rng(6).normal(size=15007)).astype(np.complex64)
        for factor in (2,5,8,40):
            d=FIRDecimator(factor);got=np.concatenate([d.feed(x[i:i+733]) for i in range(0,len(x),733)])
            np.testing.assert_allclose(got,lfilter(d.taps,[1],x)[::factor],atol=2e-7)

    def test_two_simultaneous_rtty_signals_identified_without_duplicate_channels(self):
        from psrtty.live_tx import ToneEncoder
        rate=48000;signals=[]
        for offset,call in [(-3000,'JA1ABC'),(3000,'JA2XYZ')]:
            e=ToneEncoder(rate,45.45,2210,2040,False)
            text=('CQ CQ DE '+call+' '+call+' 599 001 ')*3
            audio=np.concatenate([e.tone(True,8),e.code(31),*[e.char(ch) for ch in text],e.tone(True,20)])
            signals.append(hilbert(audio)*np.exp(2j*np.pi*(offset-2125)*np.arange(len(audio))/rate))
        iq=sum(signals);out=[];engine=SkimmerEngine(on_text=lambda *a:out.append(a))
        for i in range(0,len(iq),4096):engine.feed(iq[i:i+4096],rate,14090000)
        self.assertEqual({a[1] for a in out},{'JA1ABC','JA2XYZ'})
        self.assertLessEqual(len(engine.channels),2)
        for hz,call,text,recent in out:
            self.assertIn('599 001',text);self.assertIn(call,text)
            self.assertAlmostEqual(hz,14090000+(-3000 if call=='JA1ABC' else 3000)+85,delta=12)

    def test_gap_and_center_change_reset_decoders(self):
        e=SkimmerEngine();e.feed(np.zeros(10000),48000,14090000);e.add_channel(14093085)
        self.assertEqual(len(e.channels),1)
        e.feed(np.zeros(1),48000,14090000,True);self.assertFalse(e.channels)
        e.add_channel(14093085);e.feed(np.zeros(1),48000,7070000);self.assertFalse(e.channels)

    def test_worker_backpressure_marks_discontinuity(self):
        w=SkimmerWorker()
        for _ in range(9):w.offer(np.zeros(10),48000,1e7)
        self.assertEqual(w.dropped,1)
        for _ in range(8):w.queue.get_nowait()
        w.offer(np.zeros(10),48000,1e7);self.assertTrue(w.queue.get_nowait()[3])

    def test_mark_to_dial_offsets(self):
        self.assertEqual(dial_for_mark(14085000,'afsk','LSB-D',2125),14087125)
        self.assertEqual(dial_for_mark(14085000,'afsk','USB-D',2125),14082875)
        self.assertEqual(dial_for_mark(14085000,'fsk','RTTY',2125),14085000)

    def test_extio_packet_reader_preserves_gap_metadata(self):
        import struct
        from psrtty.ry_iq import ExtIOInput
        frames=[]
        for pos in (0,2,6):frames.append(struct.pack('<4sIIdq',b'RYIQ',2,48000,14090000,pos)+np.array([1,2,3,4],dtype='<f4').tobytes())
        out=[];src=ExtIOInput('test.dll',14090000,lambda *a:out.append(a),lambda e:None)
        src.process=Mock(stdout=io.BytesIO(b''.join(frames)),stderr=io.BytesIO())
        src._read();self.assertEqual([a[3] for a in out],[False,False,True])
        np.testing.assert_equal(out[0][0],np.array([1+2j,3+4j]))

    def test_rtl_uses_usb_serial_and_complex_iq_not_audio_port(self):
        import ctypes as C
        from psrtty.ry_iq import RTLInput
        lib=Mock();lib.rtlsdr_get_device_count.return_value=2
        def usb(index,m,p,s):p.value=b'RTL';s.value=str(index).encode();return 0
        lib.rtlsdr_get_device_usb_strings.side_effect=usb
        def opened(pointer,index):pointer._obj.value=1234;return 0
        lib.rtlsdr_open.side_effect=opened
        for name in ('rtlsdr_set_sample_rate','rtlsdr_set_center_freq','rtlsdr_set_tuner_gain_mode','rtlsdr_reset_buffer','rtlsdr_set_direct_sampling'):
            getattr(lib,name).return_value=0
        out=[];error=[];src=RTLInput('x.dll','1',14090000,lambda *a:out.append(a),error.append)
        def read(handle,callback,context,count,length):
            data=(C.c_ubyte*4)(255,0,127,128);callback(data,4,None);src.stopped.set();return 0
        lib.rtlsdr_read_async.side_effect=read
        with patch.object(src,'_library',return_value=lib):src.start();src.thread.join(.5)
        self.assertFalse(src.thread.is_alive());self.assertFalse(error)
        self.assertEqual(lib.rtlsdr_open.call_args.args[1],1)
        self.assertEqual(out[0][1:],(240000,14090000))
        np.testing.assert_allclose(out[0][0],[(127.5-127.5j)/128,(-.5+.5j)/128])
        lib.rtlsdr_close.assert_called_once()


class RYUITests(unittest.TestCase):
    setUpClass=classmethod(_Fixture.setUpClass.__func__)
    setUp=_Fixture.setUp
    tearDown=_Fixture.tearDown
    pump=_Fixture.pump

    def radar(self):
        from psrtty.ui.ry_windows import RadarWindow
        self.window.ry_radar_window=RadarWindow(self.window)
        return self.window.ry_radar_window

    def test_button_grid_equal_size_and_blank_lower_left(self):
        w=self.window
        buttons=[w.control_button,w.scope_button,w.sub_button,w.ry_skimmer_button,w.ry_radar_button]
        self.assertEqual(len({(b.width(),b.height()) for b in buttons}),1)
        self.assertEqual(buttons[0].height(),w.profile_buttons.itemAt(0).widget().height())
        self.assertIsNone(w.tool_buttons.itemAtPosition(1,0))
        self.assertIs(w.tool_buttons.itemAtPosition(1,1).widget(),w.ry_skimmer_button)

    def test_current_band_automatic_and_other_bands_remain(self):
        w=self.window;r=self.radar();self.assertIsNone(r.parent())
        r.refresh();self.assertTrue(r.left.message)
        with patch.object(w,'_connected',return_value=True):
            w.current_freq_hz=7070000;r.refresh();self.assertEqual(r.active_band,7)
            self.assertFalse(r.panels[7].isVisible())
            w.current_freq_hz=14085000;r.refresh();self.assertEqual(r.active_band,14)
            self.assertIn(7,r.panels)
        r.close();self.assertIn('ry_radar_window',w.store.data['ui'])

    def test_shifted_labels_single_click_selects_double_click_tunes_exact_hz(self):
        from PySide6.QtTest import QTest
        from PySide6.QtCore import Qt
        r=self.radar();r.show();r.timer.stop();self.pump(.03);c=r.panels[7].widget()
        now=time.time();rows=[Spot('JA1A'+chr(65+i),7078000+i*10,now) for i in range(8)]
        c.set_rows(rows);self.pump(.03);c.grab()
        self.assertEqual(len(c.hits),8)
        for (a,_),(b,_) in zip(c.hits,c.hits[1:]):self.assertLessEqual(a.bottom(),b.top()+1)
        selected=[];tuned=[];c.selected.connect(selected.append);c.tune.connect(tuned.append)
        point=c.hits[2][0].center().toPoint();QTest.mouseClick(c,Qt.LeftButton,pos=point)
        self.assertFalse(tuned);self.assertEqual(selected[-1].hz,rows[2].hz)
        QTest.mouseDClick(c,Qt.LeftButton,pos=point);self.assertEqual(tuned,[rows[2].hz])
        r.close()

    def test_tuning_is_blocked_during_tx_and_disconnected(self):
        w=self.window
        with patch.object(w,'_connected',return_value=False):w._ry_tune(7078000)
        self.assertIsNone(w.control_window)
        with patch.object(w,'_connected',return_value=True):
            w.active_tx_id=123;w._ry_tune(7078000);w.active_tx_id=None
        self.assertIsNone(w.control_window)
        from psrtty.ui.ry_windows import SkimmerWindow
        w.ry_skimmer_window=SkimmerWindow(w);w.ry_skimmer_window.options={'method':'extio'}
        w.active_tx_id=123;w.ry_skimmer_window.start_input();w.active_tx_id=None
        self.assertIsNone(w.ry_skimmer_window.input)

    def test_subdecode_discards_two_character_runs_only(self):
        from psrtty.ui.sub_decode import SubDecodeWindow
        w=self.window;w.sub_window=SubDecodeWindow(w);s=w.sub_window
        for text in ('A','BC','A B','  '):s.buffers[0]=text;s._flush(0)
        self.assertEqual(s.outputs[0].toPlainText(),'')
        s.buffers[0]='CQ TEST';s._flush(0);self.assertEqual(s.outputs[0].toPlainText(),'CQ TEST')

    def test_eight_languages_setup_and_no_implicit_network(self):
        from psrtty import i18n
        from psrtty.ui.ry_windows import SkimmerSetup
        for code in i18n.LANGUAGES:
            i18n.configure(code);r=self.radar();self.assertFalse(r.feeds)
            self.assertNotIn('ry.',r.explanation.text())
            d=SkimmerSetup(self.window);d.choose('extio');self.assertFalse(d.options)
            self.assertNotIn('ry.',d.note.text());d.close();r.close()
        i18n.configure('ja')


del _Fixture
