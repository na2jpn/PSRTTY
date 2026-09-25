from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class SpectrumWidget(QWidget):
    frequency_clicked = Signal(float)
    tones_dragged = Signal(float, float)
    tones_committed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(110)
        self.setMaximumHeight(145)
        self.freqs = np.array([], dtype=np.float32)
        self.power = np.array([], dtype=np.float32)
        self.mark_hz = 2125.0
        self.space_hz = 2295.0
        self.width_hz = 1000.0
        self.gain_db = 0.0
        self.drag = None
        self.view_bounds = None
        self.setMouseTracking(True)
        self.setToolTip("クリックでMARKを移動。MARK／Center／SPACEの線をドラッグすると間隔を保って移動します。")

    def set_data(self, freqs: np.ndarray, power: np.ndarray) -> None:
        same = len(self.freqs)==len(freqs) and np.array_equal(self.freqs,freqs)
        self.power = self.power*0.65 + power*0.35 if same else power.copy()
        self.freqs = freqs.copy()
        self.update()

    def set_tones(self, mark: float, space: float) -> None:
        self.mark_hz = float(mark)
        self.space_hz = float(space)
        self.update()

    def set_width(self, width_hz: float) -> None:
        self.width_hz = max(300.0, float(width_hz))
        self.update()

    def _bounds(self) -> tuple[float, float]:
        if self.view_bounds is not None: return self.view_bounds
        center = (self.mark_hz + self.space_hz) / 2.0
        return center - self.width_hz / 2.0, center + self.width_hz / 2.0

    def _x(self, f: float) -> float:
        lo, hi = self._bounds()
        return (f - lo) / max(1.0, hi - lo) * self.width()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.fillRect(self.rect(), QColor("#171717"))
        for i in range(1, 5):
            # Upper-middle guide: visible, but thinner/dimmer than the trace.
            p.setPen(QPen(QColor("#b39a50" if i == 2 else "#3d3d3d"), 1))
            y = self.height() * i / 5
            p.drawLine(0, int(y), self.width(), int(y))

        lo, hi = self._bounds()
        if len(self.freqs) and len(self.power):
            mask = (self.freqs >= lo) & (self.freqs <= hi)
            f = self.freqs[mask]
            db = self.power[mask]
            if len(f) > 1:
                floor = -90.0 - self.gain_db
                ceil = -10.0 - self.gain_db
                path = QPainterPath()
                for idx, (ff, vv) in enumerate(zip(f, db)):
                    x = self._x(float(ff))
                    norm = (float(vv) - floor) / (ceil - floor)
                    y = self.height() - max(0.0, min(1.0, norm)) * (self.height() - 8) - 4
                    if idx == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                p.setPen(QPen(QColor("#ffd58a"), 1.5))
                p.drawPath(path)

        for hz, label, color in [
            (self.mark_hz, "MARK", QColor("#7CFC9A")),
            (self.space_hz, "SPACE", QColor("#69C8FF")),
        ]:
            x = self._x(hz)
            p.setPen(QPen(color, 2))
            p.drawLine(int(x), 0, int(x), self.height())
            p.drawText(int(x) + 4, 16, label)

        center_x = int(self._x((self.mark_hz + self.space_hz) / 2))
        p.setPen(QPen(QColor("#909090"), 1))
        p.drawLine(center_x, 0, center_x, 12)

        p.setPen(QColor("#bdbdbd"))
        p.drawText(8, self.height() - 7, f"{lo:.0f} Hz")
        txt = f"{hi:.0f} Hz"
        p.drawText(self.width() - 70, self.height() - 7, txt)

    def set_gain(self, value):
        self.gain_db = float(value); self.update()

    def _near_handle(self, position):
        x, y = position.x(), position.y()
        return (min(abs(x-self._x(self.mark_hz)),abs(x-self._x(self.space_hz))) <= 10
                or (y <= 22 and abs(x-self._x((self.mark_hz+self.space_hz)/2)) <= 10))

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton: return
        lo, hi = self._bounds()
        x = event.position().x()
        if self._near_handle(event.position()):
            self.view_bounds = (lo,hi)
            self.drag = (x,self.mark_hz,self.space_hz,hi-lo)
            self.setCursor(Qt.ClosedHandCursor)
        else:
            hz = lo + x / max(1,self.width()) * (hi-lo)
            self.frequency_clicked.emit(float(hz))
        event.accept()

    def mouseMoveEvent(self,event):
        if self.drag is not None:
            x, mark, space, width = self.drag
            delta = (event.position().x()-x)/max(1,self.width())*width
            delta = max(100-min(mark,space),min(3900-max(mark,space),delta))
            self.tones_dragged.emit(mark+delta,space+delta)
        else:
            x=event.position().x()
            near=self._near_handle(event.position())
            self.setCursor(Qt.OpenHandCursor if near else Qt.CrossCursor)

    def mouseReleaseEvent(self,event):
        was_dragging=self.drag is not None
        self.drag=None; self.view_bounds=None; self.unsetCursor(); self.update()
        if was_dragging: self.tones_committed.emit()
