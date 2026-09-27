"""Receive-center estimate. Separate from decoding and the XY display."""
import time
from collections import deque
import numpy as np


def estimate_center(samples, sample_rate, mark, space):
    x = np.asarray(samples, dtype=float)
    if len(x) < sample_rate*.12 or not np.all(np.isfinite(x)) or np.sqrt(np.mean(x*x)) < 1e-5:
        return None
    # A broad, flat audio passband rejects remote noise. Measure periods only
    # inside stable MARK and SPACE runs; FFT maxima are biased by FSK keying.
    n=len(x); size=1 << (2*n-1).bit_length()
    frequencies=np.fft.rfftfreq(size,1/sample_rate)
    width=max(450.,abs(space-mark)*1.5)
    response=np.exp(-((frequencies-(mark+space)/2)/width)**8)
    y=np.fft.irfft(np.fft.rfft(x,size)*response,size)[:n]
    crossings=np.flatnonzero((y[:-1]<=0)&(y[1:]>0))
    guard=int(sample_rate*.010)
    crossings=crossings[(crossings>guard)&(crossings<n-guard)]
    if len(crossings)<20: return None
    positions=crossings-y[crossings]/(y[crossings+1]-y[crossings])
    periods=np.diff(positions)
    instant=sample_rate/periods
    runs=np.lib.stride_tricks.sliding_window_view(instant,8)
    stable=np.std(runs,axis=1)<2.0
    centers=np.median(runs,axis=1)
    measured=sample_rate*8/(positions[8:]-positions[:-8])
    offsets=[]
    for tone in (mark,space):
        selected=stable & (abs(centers-tone)<min(65.,abs(space-mark)*.4))
        if np.count_nonzero(selected)<3: return None
        offsets.append(float(np.median(measured[selected]))-tone)
    if abs(offsets[0]-offsets[1])>3: return None
    value=float(np.mean(offsets))
    return value if abs(value)<25 else None



class CenterTuning:
    def __init__(self):
        self.history=deque(); self.stamp=None; self.tones=None
    def update(self, frame, sample_rate, now=None):
        now=time.monotonic() if now is None else now
        if frame is None or now-frame[0] > .5:
            self.history.clear(); self.stamp=None
            return None
        stamp,samples,tones=frame
        if tones != self.tones:
            self.history.clear(); self.stamp=None; self.tones=tones
        if stamp != self.stamp:
            self.stamp=stamp
            value=estimate_center(samples,sample_rate,*tones[:2])
            if value is None:
                self.history.clear(); return None
            self.history.append((stamp,value))
        while self.history and now-self.history[0][0] > .5: self.history.popleft()
        return float(np.mean([v for _,v in self.history])) if self.history else None


def tuning_display(value):
    if value is None or not np.isfinite(value) or abs(value) >= 25:
        return 'C同調 -', '#000000'
    # Classify the displayed value so rounded boundary values match their color.
    value=round(value,1)
    if abs(value)>=25: return 'C同調 -', '#000000'
    color=next(color for limit,color in [(5,'#0055dd'),(9,'#006400'),(11,'#80b918'),(15,'#e0bd00'),(20,'#f28c00'),(25,'#e34234')] if abs(value)<limit)
    number='0.0' if value == 0 else f'{value:+.1f}'
    return f'C同調 {number} Hz',color
