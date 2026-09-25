"""Receive-only XY view. DSP runs in the GUI timer, never in the decoder."""
import time
import numpy as np
from PySide6.QtCore import Qt, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPolygonF
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QWidget


def scope_points(samples, sample_rate, mark, space, baud):
    """Overlapping resonator responses with phase compensation.

    H(f)=1/(1+j*(f-f0)/bandwidth). Unlike disjoint, zero-phase
    bandpasses, each tone reaches both axes with a phase difference.
    Compensation makes that difference 90 degrees at mark AND space;
    detuning changes the phase difference and tilts the measured ellipse.
    Real inverse FFT imposes conjugate symmetry. No synthetic ellipse is drawn.
    """
    samples = np.asarray(samples, dtype=float)
    if len(samples) < 64 or not np.all(np.isfinite(samples)):
        return np.empty((0, 2))
    shift = space-mark
    if abs(shift) < 1:
        return np.empty((0, 2))
    n = len(samples)
    # Padding and the central crop keep block-boundary transients off screen.
    size = 2*n
    frequencies = np.fft.rfftfreq(size, 1 / sample_rate)
    spectrum = np.fft.rfft(samples, n=size)
    bandwidth = min(abs(shift)*.4, max(abs(shift)*.20, baud*.8))
    phase = np.sign(shift)*(np.pi/2-np.arctan(abs(shift)/bandwidth))
    channels = []
    for tone, rotation in ((mark, 0), (space, phase)):
        response = np.exp(1j*rotation)/(1+1j*(frequencies-tone)/bandwidth)
        # Suppress leakage of the opposite *configured* tone, without narrowing
        # the main resonator (which would slow its response to symbol changes).
        # A finite floor keeps the on-tune trace a thin ellipse. Away from the
        # notch, cross-axis response increases naturally; no XY rescaling.
        opposite = space if tone == mark else mark
        distance = (frequencies-opposite)/max(abs(shift)*.20, 1.)
        notch = .18 + .82*distance**2/(1+distance**2)
        response *= notch
        channels.append(np.fft.irfft(spectrum*response, size)[n//4:3*n//4])
    xy = np.column_stack(channels)
    peak = float(np.max(np.abs(xy)))
    if peak < 1e-6:
        return np.empty((0, 2))
    return xy / max(peak, .005) * .85


def stable_traces(samples, sample_rate, mark, space, baud, tagged=False):
    """Keep short measured runs with stable envelopes; never bridge gaps.

    At most one run per dominant axis and three audio cycles per run avoids
    repeatedly drawing changing radii. Detuning/phase remain in actual samples.
    """
    xy = scope_points(samples, sample_rate, mark, space, baud)
    n = len(xy)
    if n < 64:
        return []
    # Analytic envelopes of the two measured axes, used only for display gating.
    h = np.zeros(n)
    h[0] = 1
    h[1:(n+1)//2] = 2
    if n % 2 == 0:
        h[n//2] = 1
    envelopes = np.abs(np.fft.ifft(np.fft.fft(xy, axis=0)*h[:, None], axis=0))
    lag = max(1, round(sample_rate*.002))
    scale = np.maximum(envelopes.max(axis=1), .02)
    change = np.max(np.abs(envelopes-np.roll(envelopes, lag, axis=0)), axis=1)/scale
    stable = change < .07
    stable[:2*lag] = False
    stable[-2*lag:] = False
    # Require a quiet neighbourhood around each sample (about 3 ms).
    guard = max(1, round(sample_rate*.0015))
    stable = np.convolve(stable.astype(int), np.ones(2*guard+1), 'same') == 2*guard+1
    dominant = np.argmax(envelopes, axis=1)
    traces = []
    for axis, tone in enumerate((mark, space)):
        valid = stable & (dominant == axis)
        edges = np.diff(np.r_[False, valid, False].astype(int))
        runs = list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))
        if not runs:
            continue
        start, end = max(runs, key=lambda pair: pair[1]-pair[0])
        cycle = max(4, round(sample_rate/max(tone, 1)))
        if end-start < cycle*2:
            continue
        count = min(end-start, cycle*3)
        start += (end-start-count)//2
        trace = xy[start:start+count]
        traces.append((axis, trace) if tagged else trace)
    return traces



class ScopeAfterglow:
    """Latest and previous measured traces per axis, expiring by acquisition time."""
    lifetime = .7

    def __init__(self):
        self.clear()

    def clear(self):
        self.latest = {}
        self.tones = None
        self.last_stamp = None

    def accept(self, stamp, tones, traces):
        if tones != self.tones:
            self.clear()
            self.tones = tones
        if self.last_stamp is not None and stamp <= self.last_stamp:
            return
        self.last_stamp = stamp
        for axis, trace in traces:
            history = self.latest.get(axis, [])
            self.latest[axis] = (history + [(stamp, trace)])[-2:]

    def visible(self, now):
        self.latest = {axis: [(stamp, trace) for stamp, trace in history
                              if 0 <= now-stamp < self.lifetime]
                       for axis, history in self.latest.items()}
        self.latest = {axis: history for axis, history in self.latest.items() if history}
        visible = []
        for axis, history in sorted(self.latest.items()):
            for index, (stamp, trace) in enumerate(history):
                # Paint the dim previous trace first, then the brighter latest.
                brightness = .45 if index < len(history)-1 else 1.
                visible.append((trace, brightness*(1-(now-stamp)/self.lifetime)))
        return visible



class ScopeCanvas(QWidget):
    def __init__(self):
        super().__init__()
        self.points = np.empty((0, 2))
        self.traces = []
        self.alphas = []
        self.setMinimumSize(220, 220)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor('#151515'))
        center = self.rect().center()
        scale = min(self.width(), self.height())*.43
        painter.setPen(QPen(QColor('#454545'), 1))
        painter.drawLine(QPointF(center.x()-scale, center.y()), QPointF(center.x()+scale, center.y()))
        painter.drawLine(QPointF(center.x(), center.y()-scale), QPointF(center.x(), center.y()+scale))
        painter.setPen(QColor('#8cb89c'))
        painter.drawText(8, 18, 'SPACE ↑   MARK →')
        painter.setPen(QPen(QColor('#8be9a0'), 1))
        painter.setRenderHint(QPainter.Antialiasing)
        for index, trace in enumerate(self.traces):
            color = QColor('#8be9a0')
            color.setAlphaF(self.alphas[index] if index < len(self.alphas) else 1.)
            painter.setPen(QPen(color, 1))
            painter.drawPolyline(QPolygonF([QPointF(center.x()+x*scale,
                center.y()-y*scale) for x, y in trace]))


class CrossScopeWindow(QDialog):
    def __init__(self, audio, parent=None):
        super().__init__(parent)
        self.audio = audio
        self.afterglow = ScopeAfterglow()
        self.setWindowTitle('クロススコープ')
        self.setWindowModality(Qt.NonModal)
        self.resize(330, 365)
        layout = QVBoxLayout(self)
        self.canvas = ScopeCanvas()
        layout.addWidget(self.canvas)
        self.caption = QLabel()
        layout.addWidget(self.caption)
        note = QLabel('横長：MARK  縦長：SPACE\n縦横の楕円が同調の目安（SQとは独立）')
        layout.addWidget(note)
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self.refresh)
        # Only opacity/repaint at 20 Hz; signal analysis remains at 5 Hz.
        self.fade_timer = QTimer(self)
        self.fade_timer.setInterval(50)
        self.fade_timer.timeout.connect(self._paint_afterglow)

    def showEvent(self, event):
        self.audio.scope_frame = None
        self.audio.scope_enabled = True
        self.afterglow.clear()
        self.timer.start()
        self.fade_timer.start()
        self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        self.fade_timer.stop()
        self.afterglow.clear()
        self.audio.scope_enabled = False
        self.audio.scope_frame = None
        self.canvas.points = np.empty((0, 2))
        self.canvas.traces = []
        self.canvas.alphas = []
        super().hideEvent(event)

    def _paint_afterglow(self):
        frame = self.audio.scope_frame
        if frame is None or (self.afterglow.tones is not None and frame[2] != self.afterglow.tones):
            self.afterglow.clear()
        visible = self.afterglow.visible(time.monotonic())
        self.canvas.traces = [trace for trace, alpha in visible]
        self.canvas.alphas = [alpha for trace, alpha in visible]
        self.canvas.points = (np.concatenate(self.canvas.traces) if self.canvas.traces
                              else np.empty((0, 2)))
        self.canvas.update()

    def refresh(self):
        frame = self.audio.scope_frame
        if frame is None or time.monotonic()-frame[0] > .5:
            self.afterglow.clear()
            self.caption.setText('受信音待ち')
        else:
            stamp, samples, tones = frame
            mark, space, baud = tones
            if stamp != self.afterglow.last_stamp or tones != self.afterglow.tones:
                traces = stable_traces(samples, self.audio.sample_rate, mark, space, baud, tagged=True)
                self.afterglow.accept(stamp, tones, traces)
            self.caption.setText(f'MARK {mark:g} Hz / SPACE {space:g} Hz')
        self._paint_afterglow()
