"""Optional, lower-priority receive-only decoders for the nearby spectrum."""
from __future__ import annotations

import queue
import threading

import numpy as np

from .decoder import RTTYDecoder


class SubDecodeWorker:
    """Bounded audio mailbox: a slow sub decoder must never hold up main RX."""

    def __init__(self, sample_rate, on_char):
        self.sample_rate = sample_rate
        self.on_char = on_char
        self._queue = queue.Queue(maxsize=8)
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread = None
        self._generation = 0
        self.dropped = 0
        self.enabled = [True, True]
        self.decoders = [RTTYDecoder(sample_rate, on_char=lambda c, i=i: self.on_char(i, c))
                         for i in range(2)]

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name='PSRTTY-SubRX', daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=1.0)
        self._thread = None
        self.clear()

    def clear(self):
        self._generation += 1
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        with self._lock:
            for decoder in self.decoders:
                decoder.reset()

    def offer(self, samples):
        # Called after main RX. Never wait for the worker or its decoder lock.
        if self._stop.is_set():
            return
        try:
            self._queue.put_nowait((self._generation, samples.copy()))
        except queue.Full:
            self.dropped += 1
            try:
                self._queue.get_nowait()
                self._queue.put_nowait((self._generation, samples.copy()))
            except (queue.Empty, queue.Full):
                pass

    def backlog(self):
        return self._queue.qsize()

    def configure(self, index, baud, mark, space, invert, sq=4):
        with self._lock:
            decoder = self.decoders[index]
            decoder.configure(baud, mark, space, invert)
            decoder.sq_level = sq
            decoder.reset()

    def set_enabled(self, index, enabled):
        with self._lock:
            self.enabled[index] = bool(enabled)
            self.decoders[index].reset()

    def _run(self):
        while not self._stop.is_set():
            try:
                item = self._queue.get(timeout=.1)
            except queue.Empty:
                continue
            if item is None:
                continue
            generation, samples = item
            if generation != self._generation:
                continue
            with self._lock:
                if generation != self._generation:
                    continue
                for enabled, decoder in zip(self.enabled, self.decoders):
                    if enabled:
                        decoder.feed(samples)


def pair_candidates(freqs, power, center, shift, side, other=None, guard=15):
    """Rank genuine 170-Hz-like peaks outside the main center guard."""
    freqs = np.asarray(freqs); power = np.asarray(power)
    if len(freqs) < 5 or len(freqs) != len(power):
        return []
    floor = float(np.percentile(power, 35))
    peaks = np.flatnonzero((power[1:-1] > power[:-2]) & (power[1:-1] >= power[2:])) + 1
    peaks = [int(i) for i in peaks if power[i] > floor + 9]
    peaks.sort(key=lambda i: float(power[i]), reverse=True)
    result = []
    main_tones = (center - shift/2, center + shift/2)
    for i in peaks[:28]:
        low = float(freqs[i])
        for j in peaks[:28]:
            high = float(freqs[j])
            if not 0 < high-low or abs(high-low-shift) > 25:
                continue
            candidate = (low+high)/2
            if side == 0 and candidate >= center-25 or side == 1 and candidate <= center+25:
                continue
            if min(abs(t-u) for t in (low,high) for u in main_tones) < guard:
                continue
            if other is not None and min(abs(t-u) for t in (low,high)
                                         for u in (other-shift/2,other+shift/2)) < guard:
                continue
            strength = min(float(power[i]),float(power[j])) - floor
            result.append((candidate, strength))
    # Visit the outer detectable pairs first. A sweep advances toward main.
    result.sort(key=lambda x: (abs(x[0]-center), x[1]), reverse=True)
    return result
