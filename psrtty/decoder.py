from __future__ import annotations

from collections.abc import Callable

import numpy as np

from .rtty_codec import ITA2Decoder


class RTTYDecoder:
    """Small contest-oriented non-coherent AFSK decoder.

    Ver0.01 deliberately favors a simple implementation that can be tuned from
    the spectrum display. It is not presented as a replacement for mature weak
    signal decoders yet; hardware/on-air testing should drive later patches.
    """

    def __init__(
        self,
        sample_rate: int = 48000,
        baud: float = 45.45,
        mark_hz: float = 2125.0,
        space_hz: float = 2295.0,
        invert: bool = False,
        on_char: Callable[[str], None] | None = None,
    ):
        self.sample_rate = sample_rate
        self.baud = baud
        self.mark_hz = mark_hz
        self.space_hz = space_hz
        self.invert = invert
        self.on_char = on_char or (lambda _c: None)
        self.sq_level = 4
        self._quality = 0.0
        self._frame_quality = []
        self.window_ms = 10.0
        self.window_n = max(64, int(sample_rate * self.window_ms / 1000.0))
        self.hop_n = max(1, int(sample_rate * 0.0025))
        self._buf = np.zeros(0, dtype=np.float32)
        self._time = 0.0
        self._last_logic = 1
        self._state = "idle"
        self._start_t = 0.0
        self._next_sample_t = 0.0
        self._bits: list[int] = []
        self._ignore_until = 0.0
        self._ita2 = ITA2Decoder()
        self._rebuild_basis()

    @property
    def bit_time(self) -> float:
        return 1.0 / max(self.baud, 1.0)

    def configure(self, baud: float, mark_hz: float, space_hz: float, invert: bool) -> None:
        self.baud = float(baud)
        changed = (self.mark_hz != mark_hz) or (self.space_hz != space_hz)
        self.mark_hz = float(mark_hz)
        self.space_hz = float(space_hz)
        self.invert = bool(invert)
        if changed:
            self._rebuild_basis()

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)
        self._state = "idle"
        self._bits.clear()
        self._last_logic = 1
        self._ita2.reset()
        self._ignore_until = 0.0
        self._frame_quality = []

    def _rebuild_basis(self) -> None:
        n = np.arange(self.window_n, dtype=np.float64)
        win = np.hanning(self.window_n)
        self._window_sum = float(win.sum())
        self._mark_basis = win * np.exp(-2j * np.pi * self.mark_hz * n / self.sample_rate)
        self._space_basis = win * np.exp(-2j * np.pi * self.space_hz * n / self.sample_rate)

    def _logic(self, segment: np.ndarray) -> tuple[int, float]:
        em = float(abs(np.dot(segment, self._mark_basis)) ** 2)
        es = float(abs(np.dot(segment, self._space_basis)) ** 2)
        energy = float(np.mean(segment.astype(np.float64) ** 2))
        # Tone concentration relative to all input energy, not an SNR in dB.
        self._quality = min(1.0, 2 * max(em, es) / (self._window_sum**2 * energy + 1e-20)) if energy > 1e-14 else 0.0
        total = em + es + 1e-12
        confidence = abs(em - es) / total
        logic = 1 if em >= es else 0
        if self.invert:
            logic ^= 1
        return logic, confidence

    def feed(self, samples: np.ndarray) -> None:
        if samples is None or len(samples) == 0:
            return
        samples = np.asarray(samples, dtype=np.float32).reshape(-1)
        self._buf = np.concatenate((self._buf, samples))
        dt = self.hop_n / self.sample_rate
        while len(self._buf) >= self.window_n:
            seg = self._buf[: self.window_n]
            self._buf = self._buf[self.hop_n :]
            logic, confidence = self._logic(seg)
            center_t = self._time + self.window_n / self.sample_rate / 2.0
            self._time += dt
            self._consume_logic(logic, confidence, center_t)
            self._last_logic = logic

    def _consume_logic(self, logic: int, confidence: float, t: float) -> None:
        threshold = (0.0, .015, .030, .055, .090, .140, .210, .300, .420, .560, .700)[max(0, min(10, int(self.sq_level)))]
        if self._state == "idle":
            if t < self._ignore_until:
                return
            if logic == 0 and self._last_logic == 1:
                self._start_t = t
                self._next_sample_t = t + 0.4 * self.bit_time
                self._bits = []
                self._frame_quality = []
                self._state = "start"
            return
        if t < self._next_sample_t:
            return
        self._frame_quality.append(self._quality)
        if self._state == "start":
            if logic != 0:
                self._state = "idle"
                return
            self._state = "data"
            self._next_sample_t = self._start_t + 1.5 * self.bit_time
        elif self._state == "data":
            self._bits.append(logic)
            self._next_sample_t += self.bit_time
            if len(self._bits) == 5:
                self._state = "stop"
        elif self._state == "stop":
            # Validate stop MARK before changing ITA2 shift state or emitting text.
            if logic == 1 and sum(self._frame_quality)/len(self._frame_quality) >= threshold:
                code = sum((bit & 1) << i for i, bit in enumerate(self._bits))
                char = self._ita2.decode_code(code)
                if char:
                    self.on_char(char)
            self._state = "idle"
            self._ignore_until = self._start_t + 7.1 * self.bit_time
