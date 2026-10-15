"""Read-only until explicitly operated; never stored in a PSRTTY Profile."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, QProgressBar, QCheckBox
from ..i18n import tr
from ..windows_volume import WindowsVolume, volume_error


class WindowsVolumeWidget(QWidget):
    def __init__(self, combo, kind, parent=None):
        super().__init__(parent)
        self.combo, self.kind = combo, kind
        self.backend = None
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(); root.addWidget(self.label)
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Horizontal); self.slider.setRange(0, 100)
        self.meter = QProgressBar(); self.meter.setRange(0, 100); self.meter.setFixedWidth(100)
        self.meter.setFormat('%v%')
        row.addWidget(self.slider, 1); row.addWidget(self.meter); root.addLayout(row)
        self.mute = QCheckBox(tr('v117.mute')); root.addWidget(self.mute)
        self.note = QLabel(tr('v117.input_shared' if kind == 'input' else 'v117.session_note'))
        self.note.setWordWrap(True); self.note.setObjectName('helpText'); root.addWidget(self.note)
        self.reason = QLabel(); self.reason.setWordWrap(True); self.reason.setObjectName('helpText')
        root.addWidget(self.reason)
        self.slider.valueChanged.connect(self._set_percent)
        self.mute.toggled.connect(self._set_mute)
        combo.currentIndexChanged.connect(self.reset)
        self.timer = QTimer(self); self.timer.setInterval(750); self.timer.timeout.connect(self.refresh)
        self.reset()

    def reset(self, *_):
        self.backend = None
        self.refresh()

    def showEvent(self, event):
        self.refresh(); self.timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        self.backend = None
        super().hideEvent(event)

    def _unavailable(self, error, default='read'):
        title = tr('v117.win_input' if self.kind == 'input' else 'v117.win_app')
        problem = volume_error(error, default)
        self.backend = None
        self.label.setText(title + ': ' + tr('v117.unavailable'))
        self.label.setStyleSheet('color: #777777;')
        self.reason.setText(tr('v117fix2.' + problem.reason))
        self.slider.setEnabled(False); self.mute.setEnabled(False); self.meter.setEnabled(False)
        self.slider.setStyleSheet('QSlider::handle:horizontal { background: transparent; border: none; width: 0px; } QSlider::sub-page:horizontal { background: #cccccc; }')
        self.meter.setValue(0); self.meter.setFormat(tr('v117.unavailable'))
        self.mute.blockSignals(True); self.mute.setChecked(False); self.mute.blockSignals(False)

    def refresh(self):
        title = tr('v117.win_input' if self.kind == 'input' else 'v117.win_app')
        try:
            if self.backend is None:
                self.backend = WindowsVolume(self.combo.currentData(), self.kind)
            state = self.backend.read()
        except Exception as exc:
            self._unavailable(exc)
            return
        self.reason.clear()
        self.slider.setEnabled(True); self.mute.setEnabled(True); self.meter.setEnabled(True)
        self.slider.setStyleSheet('')
        self.meter.setFormat('%v%'); self.meter.setValue(state.percent)
        self.label.setText(title + f': {state.percent}%' + (' / ' + tr('v117.muted') if state.muted else ''))
        self.label.setStyleSheet('color: #c53030;' if state.muted or state.percent == 0 else '')
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True); self.slider.setValue(state.percent); self.slider.blockSignals(False)
        self.mute.blockSignals(True); self.mute.setChecked(state.muted); self.mute.blockSignals(False)

    def _set_percent(self, value):
        if self.backend:
            try: self.backend.set_percent(value)
            except Exception as exc:
                self._unavailable(exc, 'write'); return
        self.refresh()

    def _set_mute(self, value):
        if self.backend:
            try: self.backend.set_mute(value)
            except Exception as exc:
                self._unavailable(exc, 'write'); return
        self.refresh()
