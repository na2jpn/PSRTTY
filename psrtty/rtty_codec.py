from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

# ITA2 / Baudot tables indexed by 5-bit value.
LTRS = [
    "", "E", "\n", "A", " ", "S", "I", "U",
    "\r", "D", "R", "J", "N", "F", "C", "K",
    "T", "Z", "L", "W", "H", "Y", "P", "Q",
    "O", "B", "G", "", "M", "X", "V", "",
]
FIGS = [
    "", "3", "\n", "-", " ", "'", "8", "7",
    "\r", "$", "4", "", ",", "!", ":", "(",
    "5", '"', ")", "2", "#", "6", "0", "1",
    "9", "?", "&", "", ".", "/", ";", "",
]
FIGS_SHIFT = 27
LTRS_SHIFT = 31

LTRS_ENCODE = {ch: i for i, ch in enumerate(LTRS) if ch}
FIGS_ENCODE = {ch: i for i, ch in enumerate(FIGS) if ch}


class ITA2Decoder:
    def __init__(self):
        self.figures = False

    def reset(self) -> None:
        self.figures = False

    def decode_code(self, code: int) -> str:
        code &= 0x1F
        if code == FIGS_SHIFT:
            self.figures = True
            return ""
        if code == LTRS_SHIFT:
            self.figures = False
            return ""
        table = FIGS if self.figures else LTRS
        return table[code]


def encode_ita2_codes(text: str) -> list[int]:
    text = text.upper().replace("\t", " ")
    figures = False
    codes: list[int] = []
    for ch in text:
        if ch in ("\r", "\n", " "):
            code = LTRS_ENCODE.get(ch)
            if code is not None:
                codes.append(code)
            continue
        if ch in LTRS_ENCODE:
            if figures:
                codes.append(LTRS_SHIFT)
                figures = False
            codes.append(LTRS_ENCODE[ch])
        elif ch in FIGS_ENCODE:
            if not figures:
                codes.append(FIGS_SHIFT)
                figures = True
            codes.append(FIGS_ENCODE[ch])
        else:
            codes.append(LTRS_ENCODE[" "])
    return codes


def encode_text_audio(
    text: str,
    sample_rate: int = 48000,
    baud: float = 45.45,
    mark_hz: float = 2125.0,
    space_hz: float = 2295.0,
    invert: bool = False,
    amplitude: float = 0.35,
) -> np.ndarray:
    """Generate AFSK RTTY (ITA2, 1 start, 5 data, 1.5 stop bits)."""
    codes = encode_ita2_codes(text + "\r\n")
    phase = 0.0
    chunks: list[np.ndarray] = []
    sample_error = 0.0

    def tone(logic_mark: bool, bit_units: float = 1.0) -> None:
        nonlocal phase, sample_error
        exact = sample_rate / baud * bit_units + sample_error
        n = max(1, int(round(exact)))
        sample_error = exact - n
        use_mark = logic_mark ^ invert
        freq = mark_hz if use_mark else space_hz
        idx = np.arange(n, dtype=np.float64)
        phases = phase + (2.0 * math.pi * freq / sample_rate) * idx
        chunks.append((np.sin(phases) * amplitude).astype(np.float32))
        phase = float((phases[-1] + 2.0 * math.pi * freq / sample_rate) % (2.0 * math.pi))

    # Small mark idle lead-in so PTT/audio settles.
    tone(True, 3.0)
    for code in codes:
        tone(False, 1.0)  # start bit
        for i in range(5):
            tone(bool((code >> i) & 1), 1.0)
        tone(True, 1.5)  # stop
    tone(True, 2.0)
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks)
