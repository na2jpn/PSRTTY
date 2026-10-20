import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import numpy as np
from psrtty.ry_ja import ja_rtty,ja_pair,ja_band,JA_RTTY_HZ
from psrtty.ry_radar import RadarFeeds,load_sources
from psrtty.ry_skimmer import SkimmerEngine
from psrtty.ry_spots import Spot
from tests import test_ui_v02 as fixture


class FilterFeedTests(unittest.TestCase):
    def test_ja_segments_exclude_cw_gaps_foreign_bands_and_beacons(self):
        for hz in (1831000,1908000,3531000,3600000,3703000,7035000,10121000,14085000,18081000,
                   21078000,21200000,24910000,28080000,50303000,144300000,430200000,1294300000):
            self.assertTrue(ja_rtty(hz),hz)
        for hz in (1801000,1880000,3590000,5357000,7020000,10110000,14060000,14100000,21150000,
                   70100000,220100000,144050000,430000000,431100000,1294550000):
            self.assertFalse(ja_rtty(hz),hz)
        self.assertTrue(ja_band(1200));self.assertFalse(ja_band(5));self.assertFalse(ja_band(220))

    def test_both_fsk_tones_must_fit_and_not_cross_beacon(self):
        self.assertFalse(ja_pair(21070050));self.assertTrue(ja_pair(21070200))
        self.assertFalse(ja_pair(21150080));self.assertFalse(ja_pair(21149920,False))
        self.assertTrue(ja_pair(21078000,False))
        for lo,hi in JA_RTTY_HZ:
            self.assertFalse(ja_pair(lo+50),lo)

    def test_manual_and_automatic_channels_filtered_before_decode(self):
        e=SkimmerEngine(ja_only=True);e.reset(48000,21070000)
        e.add_channel(21069000);self.assertFalse(e.channels)
        e.add_channel(21078000);self.assertEqual(len(e.channels),1)
        e.ja_only=False;e.add_channel(21069000);self.assertEqual(len(e.channels),2)
        e.ja_only=True;e.feed(np.zeros(1),48000,21070000);self.assertEqual(len(e.channels),1)
        e=SkimmerEngine(ja_only=True);e.reset(48000,5357000)
        freqs=np.arange(-12000,12000,5);db=np.full(len(freqs),-80.)
        db[np.where(freqs==-85)[0]]=0;db[np.where(freqs==85)[0]]=0
        e._scan(freqs,db);self.assertFalse(e.channels)
        e.ja_only=False;e._scan(freqs,db);self.assertEqual(len(e.channels),1)

    def test_only_exact_shipped_shanghai_migrates_and_backup_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'sources.json';d=load_sources(p)
            official=d['rbn'][2];self.assertEqual(official['host'],'telnet.reversebeacon.net')
            d['rbn'][2]=dict(name='BH4HKZ / Shanghai',host='spots.bh4hkz.com',port=7373,commands=['set dx filt'],enabled=True)
            raw=json.dumps(d).encode();p.write_bytes(raw)
            got=load_sources(p);self.assertEqual(got['rbn'][2],official)
            backup=p.with_name(p.name+'.pre-fix4.bak');self.assertEqual(backup.read_bytes(),raw)
            load_sources(p);self.assertEqual(backup.read_bytes(),raw)
            d['rbn'][2]['enabled']=False;p.write_text(json.dumps(d),encoding='utf-8')
            self.assertFalse(load_sources(p)['rbn'][2]['enabled']);self.assertEqual(load_sources(p)['rbn'][2]['host'],'spots.bh4hkz.com')

    def test_rotation_announces_waiting_and_current_index(self):
        f=RadarFeeds({'rbn':[dict(name='A'),dict(name='B')],'clusters':[],'dwell':60},'JX1XXX')
        def session(source,end):
            if source['name']=='B':f.stop_event.set()
        f._telnet=session
        with patch.object(f.stop_event,'wait',return_value=False):f._cycle()
        events=list(f.events.queue)
        self.assertIn(('status','A','waiting',''),events)
        self.assertEqual([e for e in events if e[0]=='rotation'],[('rotation','A',1,2),('rotation','B',2,2)])

    def test_server_close_is_error_not_normal_rotation(self):
        s=Mock();s.recv.return_value=b''
        f=RadarFeeds({'rbn':[],'clusters':[]},'JX1XXX',connector=lambda *a,**k:s)
        f._telnet(dict(name='A',host='example.org',port=7000),time.monotonic()+60)
        states=[e[2] for e in f.events.queue if e[0]=='status']
        self.assertEqual(states,['connecting','connected','error']);s.close.assert_called_once()

    def test_normal_rotation_end_is_waiting(self):
        s=Mock();f=RadarFeeds({'rbn':[],'clusters':[]},'JX1XXX',connector=lambda *a,**k:s)
        f._telnet(dict(name='A',host='example.org',port=7000),time.monotonic()-1)
        self.assertEqual(list(f.events.queue)[-1],('status','A','waiting',''))


class Fix4UITests(unittest.TestCase):
    setUpClass=classmethod(fixture.UITests.setUpClass.__func__)
    setUp=fixture.UITests.setUp
    tearDown=fixture.UITests.tearDown
    pump=fixture.UITests.pump

    def test_radar_filters_frequency_not_nationality_and_restores(self):
        from psrtty.ui.ry_windows import RadarWindow
        r=RadarWindow(self.window);self.window.ry_radar_window=r;r.timer.stop()
        self.assertTrue(r.ja_only.isChecked());now=time.time()
        r.cache.put(Spot('W1AW',21078000,now),now);r.cache.put(Spot('JA1ABC',21060000,now),now)
        with patch.object(self.window,'_connected',return_value=True):
            self.window.current_freq_hz=21078000;r.refresh()
            self.assertEqual([s.call for s,c in r.left.spots],['W1AW'])
            r.ja_only.setChecked(False);self.assertEqual(len(r.left.spots),2)
            self.assertFalse(self.store.data['ui']['ry_radar_ja_only']);self.store.save.assert_called()
        r.close()
        second=RadarWindow(self.window);self.assertFalse(second.ja_only.isChecked());second.close()

    def test_unwanted_band_buttons_hidden_but_selection_retained(self):
        from psrtty.ui.ry_windows import RadarWindow
        self.store.data['ui']['ry_radar_bands']=[5,7,70,220]
        r=RadarWindow(self.window);self.window.ry_radar_window=r;r.timer.stop()
        for b in (5,70,220):self.assertTrue(r.band_buttons[b].isHidden());self.assertNotIn(b,r.panels)
        r.ja_only.setChecked(False)
        for b in (5,70,220):self.assertFalse(r.band_buttons[b].isHidden());self.assertIn(b,r.panels)
        r.close()

    def test_status_error_survives_wait_and_rotation_count_visible(self):
        from psrtty.ui.ry_windows import RadarWindow
        import queue
        from psrtty.i18n import tr
        r=RadarWindow(self.window);self.window.ry_radar_window=r;r.timer.stop()
        r.feeds=Mock(events=queue.Queue())
        for e in [('rotation','JP',2,5),('status','JP','connecting',''),('status','JP','error','DNS'),('status','JP','closed','')]:r.feeds.events.put(e)
        r.refresh();self.assertIn('2/5',r.status.text());self.assertIn('DNS',r.status.text())
        r.feeds.events.put(('status','JP','connecting',''));r.refresh();self.assertNotIn('DNS',r.status.text())
        r.close()

    def test_icom_setup_model_hints_hidden_sdr_fields_and_links(self):
        from psrtty.ui.ry_windows import SkimmerSetup
        from PySide6.QtGui import QDesktopServices
        d=SkimmerSetup(self.window);d.choose('extio')
        self.assertFalse(d.form.isRowVisible(d.devices_row));self.assertFalse(d.form.isRowVisible(d.direct))
        self.assertTrue(d.form.isRowVisible(d.model));self.assertIn('USB 2',d.hint.text())
        with patch.object(QDesktopServices,'openUrl') as op:
            d.open_download();self.assertTrue(op.call_args.args[0].toString().endswith('1956/'))
            d.model.setCurrentText('IC-7760');d.open_download();self.assertTrue(op.call_args.args[0].toString().endswith('4190/'))
        self.assertNotIn('USB 2',d.hint.text());d.close()

    def test_rtl_setup_flow_and_scoped_dll_search(self):
        from psrtty.ui.ry_windows import SkimmerSetup
        from PySide6.QtWidgets import QFileDialog
        d=SkimmerSetup(self.window);d.choose('rtl')
        self.assertTrue(d.form.isRowVisible(d.devices_row));self.assertTrue(d.form.isRowVisible(d.direct));self.assertFalse(d.form.isRowVisible(d.model))
        self.assertIn('V3',d.hint.text());self.assertIn('V4',d.hint.text())
        with tempfile.TemporaryDirectory() as td:
            p=Path(td);(p/'rtlsdr.dll').write_bytes(b'x');(p/'other.dll').write_bytes(b'x')
            with patch.object(QFileDialog,'getExistingDirectory',return_value=td):d.choose_dll_folder()
            self.assertEqual(d.candidates.count(),1);self.assertEqual(d.dll.text(),str(p/'rtlsdr.dll'))
        d.close()

    def test_skimmer_filter_hides_labels_and_persists(self):
        from psrtty.ui.ry_windows import SkimmerWindow
        s=SkimmerWindow(self.window);self.window.ry_skimmer_window=s;s.timer.stop()
        self.assertTrue(s.ja_only.isChecked())
        s.post('text',5357000,'W1AW','CQ','CQ W1AW');s.post('text',21078000,'JA1ABC','CQ','CQ JA1ABC');s.refresh()
        self.assertEqual([row.call for row,c in s.canvas.spots],['JA1ABC'])
        s.ja_only.setChecked(False);self.assertFalse(self.store.data['ui']['ry_skimmer_ja_only'])
        s.post('text',5357000,'W1AW','CQ','CQ W1AW');s.refresh();self.assertEqual(len(s.canvas.spots),2)
        s.close()

    def test_axis_still_expands_and_displaced_labels_tune_exact_frequency(self):
        from psrtty.ui.ry_windows import BandCanvas
        c=BandCanvas(21);self.assertEqual(c.limits(),(21060000,21150000))
        c.set_rows([Spot('W1AW',21200000,time.time())]);self.assertGreater(c.limits()[1],21200000)
        c.resize(380,400);c.grab();self.assertEqual(c.hits[0][1].hz,21200000);c.close()
