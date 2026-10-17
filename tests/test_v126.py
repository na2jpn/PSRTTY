import unittest
import numpy as np
from psrtty.rtty_codec import ITA2Decoder,encode_ita2_codes,encode_text_audio
from psrtty.live_tx import ToneEncoder
from psrtty.fsk import CodeEncoder
from psrtty.decoder import RTTYDecoder


class Receiver(ITA2Decoder):
    def __init__(self,usos):super().__init__();self.usos=usos
    def decode_code(self,code):
        text=super().decode_code(code)
        if self.usos and code==4:self.figures=False
        return text


def read(codes,usos):
    d=Receiver(usos)
    return ''.join(d.decode_code(code) for code in codes)


def streamed(text,kind):
    if kind=='fsk':
        e=CodeEncoder();return [c for ch in text for c in e.char(ch)]
    e=ToneEncoder(48000,45.45,2125,2295,False)
    e.code=lambda code:np.array([code],dtype=int)
    return [int(c) for ch in text for c in e.char(ch)]


class USOSTransmissionTests(unittest.TestCase):
    def test_reproduces_original_space_failure_without_reassertion(self):
        old=[27,16,24,24,4,22,22,23]  # FIGS 599 SPACE 001
        self.assertEqual(read(old,False),'599 001')
        self.assertEqual(read(old,True),'599 PPQ')

    def test_all_three_encoders_work_with_both_receiver_policies(self):
        cases=['599 001','599 25 25','599 001 002 003','599 JA1ABC 599',
               '599-001','599 /P 001','599  001','599 \r\n001',
               '599\r001','599.001','CQ JA1ABC DE JH1HST 599 001 K',
               '599 ? 001','599 ☃001']
        for text in cases:
            expected=text.replace('☃',' ')
            for kind in ('batch','fsk','direct'):
                codes=encode_ita2_codes(text) if kind=='batch' else streamed(text,kind)
                for usos in (False,True):
                    with self.subTest(text=text,kind=kind,usos=usos):
                        self.assertEqual(read(codes,usos),expected if kind=='batch' else expected.replace('\n','\r\n'))

    def test_reassert_only_at_needed_boundaries_not_every_digit(self):
        for kind in ('batch','fsk','direct'):
            codes=encode_ita2_codes('599 001') if kind=='batch' else streamed('599 001',kind)
            self.assertEqual(codes,[27,16,24,24,4,27,22,22,23])
            self.assertEqual(codes.count(27),2)

    def test_letters_after_figure_space_still_shift_for_non_usos_receiver(self):
        for kind in ('batch','fsk','direct'):
            codes=encode_ita2_codes('599 CQ') if kind=='batch' else streamed('599 CQ',kind)
            self.assertEqual(codes,[27,16,24,24,4,31,14,23])
            self.assertEqual(read(codes,False),'599 CQ')

    def test_afsk_audio_decodes_with_usos_on_and_off(self):
        for reverse in (False,True):
            for usos in (False,True):
                out=[];d=RTTYDecoder(invert=reverse,on_char=out.append);d._ita2=Receiver(usos)
                wave=encode_text_audio('599 001 25 CQ',invert=reverse)
                for i in range(0,len(wave),960):d.feed(wave[i:i+960])
                self.assertEqual(''.join(out),'599 001 25 CQ\r\n')

    def test_direct_audio_and_fsk_frames_decode_with_both_policies(self):
        text='599 001 25 CQ'
        for mode in ('direct','fsk'):
            for usos in (False,True):
                e=ToneEncoder(48000,45.45,2125,2295,False)
                blocks=[e.tone(True,3),e.code(31)]
                if mode=='direct':blocks.extend(e.char(ch) for ch in text)
                else:
                    c=CodeEncoder()
                    blocks.extend(e.code(code) for ch in text for code in c.char(ch))
                blocks.append(e.tone(True,3))
                out=[];d=RTTYDecoder(on_char=out.append);d._ita2=Receiver(usos)
                wave=np.concatenate(blocks)
                for i in range(0,len(wave),733):d.feed(wave[i:i+733])
                self.assertEqual(''.join(out),text)

    def test_direct_idle_and_fsk_replay_state_still_reassert_figures(self):
        e=ToneEncoder(48000,45.45,2125,2295,False)
        e.code=lambda c:np.array([c])
        a=[int(c) for ch in '599 ' for c in e.char(ch)]
        a.extend(map(int,e.idle()))
        a.extend(int(c) for ch in '001' for c in e.char(ch))
        for usos in (False,True):self.assertEqual(read(a,usos),'599 001')
        f=CodeEncoder()
        for ch in '599 ':f.char(ch)
        f.figures=False
        self.assertEqual(f.char('0'),[27,22])


class ContestMacro126Tests(unittest.TestCase):
    def test_hyphen_repetitions_extract_as_one_exchange(self):
        from psrtty.parser import parse_exchange
        for text, expected in [('001-001','001'),('25-25','25'),('01-02','01-02'),('01A-01A','01A-01A')]:
            for cqww in (False,True):
                self.assertEqual(parse_exchange('599 '+text,cqww=cqww).exchange,expected)
        for value in ('05 MA','01 NWT','05 PEI'):
            self.assertEqual(parse_exchange('599 '+value+'-'+value,cqww=True).exchange,value)

    def test_jarl_and_cqww_use_hyphen_with_both_usos_policies(self):
        from psrtty.macros import jarl_ww_template,cqww_rtty_template,expand_macro
        for template in (jarl_ww_template,cqww_rtty_template):
            text=expand_macro(template()[2]['text'],{'HISCALL':'JA1ABC','MYCALL':'JH1HST','SENT':'001'})
            self.assertEqual(text,'JA1ABC 599 001-001 DE JH1HST K')
            for kind in ('batch','fsk','direct'):
                codes=encode_ita2_codes(text) if kind=='batch' else streamed(text,kind)
                for usos in (False,True):self.assertEqual(read(codes,usos),text)
