import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from psrtty.adif import ADIFLog, QSORecord, band_from_hz
from psrtty.civ import decode_bcd_frequency
from psrtty.logging_store import TranscriptLogger
from psrtty.macros import expand_macro
from psrtty.parser import parse_exchange
from psrtty.rtty_codec import ITA2Decoder, encode_ita2_codes, encode_text_audio
from psrtty.decoder import RTTYDecoder


class CoreTests(unittest.TestCase):
    def test_macro(self):
        out = expand_macro("{HISCALL} {MYCALL} 599 {SENT}", {"HISCALL":"JX1XXX","MYCALL":"JH1HST","SENT":"023"})
        self.assertEqual(out, "JX1XXX JH1HST 599 023")

    def test_parse_exchange(self):
        p = parse_exchange("JH1HST 599 123 123", "JH1HST")
        self.assertEqual(p.rst, "599")
        self.assertEqual(p.exchange, "123")
        p2 = parse_exchange("CQ TEST JX1XXX JX1XXX", "JH1HST")
        self.assertEqual(p2.callsign, "JX1XXX")

    def test_ps_log(self):
        with tempfile.TemporaryDirectory() as td:
            log = TranscriptLogger(Path(td))
            now = datetime(2026, 9, 24, 10, 2, 14)
            path = log.append("RX CQ TEST JX1XXX", now)
            text = path.read_text(encoding="utf-8-sig")
            self.assertIn("2026-09-24 10:02:14 | RX CQ TEST JX1XXX", text)
            self.assertEqual(path.name, "20260924_all.txt")

    def test_adif(self):
        with tempfile.TemporaryDirectory() as td:
            log = ADIFLog(Path(td))
            q = QSORecord("JX1XXX", sent="023", rcvd="123", station_callsign="JH1HST", freq_hz=14_085_000, when_utc=datetime(2026,9,24,1,2,3,tzinfo=timezone.utc))
            path = log.append(q, datetime(2026,9,24))
            text = path.read_text(encoding="utf-8")
            self.assertIn("<CALL:6>JX1XXX", text)
            self.assertIn("<MODE:4>RTTY", text)
            self.assertIn("<BAND:3>20m", text)
            self.assertIn("<STX_STRING:3>023", text)
            self.assertIn("<SRX_STRING:3>123", text)

    def test_band(self):
        self.assertEqual(band_from_hz(14_085_000), "20m")

    def test_bcd_frequency(self):
        # 14,074,000 Hz => decimal digits from least significant: 0004704100
        self.assertEqual(decode_bcd_frequency(bytes([0x00,0x40,0x07,0x14,0x00])), 14_074_000)

    def test_ita2_roundtrip_codes(self):
        dec = ITA2Decoder()
        codes = encode_ita2_codes("CQ 123")
        text = "".join(dec.decode_code(c) for c in codes)
        self.assertEqual(text, "CQ 123")

    def test_audio_decoder_roundtrip_clean_signal(self):
        out = []
        dec = RTTYDecoder(on_char=out.append)
        audio = encode_text_audio("CQ TEST")
        for i in range(0, len(audio), 960):
            dec.feed(audio[i:i+960])
        self.assertEqual("".join(out), "CQ TEST\r\n")

if __name__ == '__main__':
    unittest.main()
