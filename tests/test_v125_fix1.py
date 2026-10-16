import time
import unittest
from unittest.mock import patch
import numpy as np
from psrtty.decoder import RTTYDecoder
from psrtty.live_tx import ToneEncoder
from tests.test_ui_v02 import UITests as Fixture


def waveform(groups, gap=.09, baud=45.45, invert=False):
    e = ToneEncoder(48000, baud, 2125, 2295, invert)
    chunks = [e.tone(True, 3), e.code(31)]
    for text in groups:
        chunks.extend(e.char(ch) for ch in text)
        chunks.append(e.tone(True, baud * gap))
    chunks.append(e.tone(True, baud * .4))
    return np.concatenate(chunks)


class FrameContinuityTests(unittest.TestCase):
    def test_short_runs_split_in_audio_time_even_in_one_feed(self):
        events=[]
        d=RTTYDecoder(on_char=lambda c:events.append(c), on_break=lambda:events.append('|'))
        d.sq_level=7
        d.feed(waveform(['A','BC','DEF']))
        self.assertEqual(''.join(events), 'A|BC|DEF|')

    def test_continuous_text_with_shift_codes_survives_chunk_boundaries(self):
        for baud in (45.45,50):
            for invert in (False,True):
                with self.subTest(baud=baud,invert=invert):
                    out=[];breaks=[]
                    d=RTTYDecoder(baud=baud,invert=invert,on_char=out.append,on_break=lambda:breaks.append(len(out)))
                    d.sq_level=7
                    wave=waveform(['CQ JA1ABC 599 001'],baud=baud,invert=invert)
                    for start in range(0,len(wave),733):d.feed(wave[start:start+733])
                    self.assertEqual(''.join(out),'CQ JA1ABC 599 001')
                    self.assertEqual(breaks,[len(out)])

    def test_bad_stop_breaks_run_before_next_valid_character(self):
        e=ToneEncoder(48000,45.45,2125,2295,False)
        wave=np.concatenate([e.tone(True,3),e.code(31),e.char('A'),
                             e.tone(False,7.5),e.tone(True,1.5),e.char('B'),e.tone(True,20)])
        out=[];d=RTTYDecoder(on_char=out.append,on_break=lambda:out.append('|'))
        d.feed(wave)
        self.assertEqual(''.join(out),'A|B|')

    def test_continuity_callback_does_not_change_raw_decoded_characters(self):
        wave=waveform(['A','BC','CQ TEST 599'])
        left=[];right=[];breaks=[]
        RTTYDecoder(on_char=left.append).feed(wave)
        RTTYDecoder(on_char=right.append,on_break=lambda:breaks.append(True)).feed(wave)
        self.assertEqual(left,right)
        self.assertEqual(''.join(left),'ABCCQ TEST 599')
        self.assertEqual(len(breaks),3)

    def test_reset_has_no_stale_boundary_and_timeout_scales_with_baud(self):
        events=[];d=RTTYDecoder(on_break=lambda:events.append(True))
        d.feed(waveform(['A'],gap=0)[:-19200])
        d.reset();d.feed(np.zeros(24000,dtype=np.float32))
        self.assertEqual(events,[])
        self.assertAlmostEqual(d.continuity_timeout,10/45.45)
        d.configure(50,2125,2295,False)
        self.assertAlmostEqual(d.continuity_timeout,.2)


class BufferedAudioContinuityTests(unittest.TestCase):
    setUpClass=classmethod(Fixture.setUpClass.__func__)
    setUp=Fixture.setUp
    tearDown=Fixture.tearDown

    def cards(self):
        w=self.window
        return [w.cards_layout.itemAt(i).widget().body.text() for i in range(w.cards_layout.count())]

    def test_four_char_limit_discards_separate_one_two_three_four_char_runs(self):
        w=self.window;w.store.data['ui']['decode_ignore_chars']=4;w.audio.set_decode_sq(7)
        with patch.object(w,'_consider_auto_extract') as extract:
            w.audio.decoder.feed(waveform(['A','BC','DEF','GHIJ']))
            self.assertEqual(self.cards(),[]);extract.assert_not_called()
            self.assertEqual(w.rx_buffer,'')

    def test_valid_continuous_message_is_displayed_once_and_extracted(self):
        w=self.window;w.store.data['ui']['decode_ignore_chars']=4;w.audio.set_decode_sq(7)
        with patch.object(w,'_consider_auto_extract') as extract:
            w.audio.decoder.feed(waveform(['A','BC','CQ JA1ABC 599']))
            self.assertEqual(self.cards(),['CQ JA1ABC 599'])
            extract.assert_called_once_with('CQ JA1ABC 599')

    def test_queued_events_keep_boundaries_when_gui_receives_them_together(self):
        w=self.window;w.store.data['ui']['decode_ignore_chars']=4
        events=[];w.bridge.char.disconnect(w._rx_char);w.bridge.char.connect(events.append)
        w.audio.decoder.feed(waveform(['A','BC','DEF','CQ TEST']))
        w.bridge.char.disconnect(events.append);w.bridge.char.connect(w._rx_char)
        for event in events:w._rx_char(event)
        self.assertEqual(self.cards(),['CQ TEST'])

    def test_live_ignores_frame_boundaries_and_keeps_short_preview(self):
        w=self.window;w.store.data['ui']['decode_ignore_chars']=4
        w.decode_display.setCurrentIndex(w.decode_display.findData('live'))
        w.audio.decoder.feed(waveform(['A','BC','DEF']))
        self.assertEqual(w.rx_live_card.body.text(),'ABCDEF')
        self.assertFalse(w.rx_live_card.finalized)

    def test_stale_break_cannot_finalize_new_generation(self):
        w=self.window;w._rx_char('A')
        w._rx_char((w.audio.decode_generation-1,None,time.monotonic()))
        self.assertEqual(w.rx_buffer,'A');self.assertEqual(self.cards(),[])


del Fixture
