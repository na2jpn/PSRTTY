from ..i18n import tr
"""Live local QSO clock, with explicitly selected manual date/time."""
from ..timebase import JST, display_zone
from datetime import datetime
import time
from PySide6.QtCore import Signal, QTimer, QSignalBlocker
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QCheckBox, QLabel

class QSODatetime(QWidget):
    textChanged = Signal(str)
    def __init__(self, parent=None, zone="JST"):
        super().__init__(parent)
        self.zone_name=zone if zone in ("JST","UTC") else "JST"
        self.zone=display_zone(self.zone_name)
        row=QHBoxLayout(self); row.setContentsMargins(0,0,0,0); row.setSpacing(4)
        self.date=QLineEdit(); self.time=QLineEdit(); self.manual=QCheckBox(tr('ui.226cd94a60d1b77b'))
        font=self.time.font();font.setFamily(QFontDatabase.systemFont(QFontDatabase.FixedFont).family());self.time.setFont(font)
        for field,hint in ((self.date,'YYYY-MM-DD'),(self.time,'HH:MM')):
            field.setPlaceholderText(hint)
            field.setFixedWidth(field.fontMetrics().horizontalAdvance(hint)+18)
            field.setToolTip(tr('ui.58dad7d6a8ea8afd'))
            row.addWidget(field)
            field.textChanged.connect(self._edited)
        self.zone_label=QLabel(self.zone_name);row.addWidget(self.zone_label)
        row.addWidget(self.manual);row.addStretch()
        self.manual.toggled.connect(self._mode_changed)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self._tick)
        self._blink_start=time.monotonic()
        self._mode_changed(False);self.timer.start()

    def _edited(self, *_):
        if self.manual.isChecked():self.textChanged.emit(self.text())

    def _display(self, date, clock):
        with QSignalBlocker(self.date), QSignalBlocker(self.time):
            self.date.setText(date);self.time.setText(clock)

    def _tick(self):
        if self.manual.isChecked():return
        now=datetime.now(self.zone)
        clock=now.strftime('%H:%M')
        if int((time.monotonic()-self._blink_start)/2)%2:
            clock=clock.replace(':',' ')
        self._display(now.strftime('%Y-%m-%d'),clock)

    def _mode_changed(self, manual):
        self.date.setReadOnly(not manual);self.time.setReadOnly(not manual)
        if manual:
            # Keep the displayed minute, even if toggled at a minute boundary.
            self._display(self.date.text(),self.time.text().replace(' ',':'))
        else:
            self._blink_start=time.monotonic();self._tick()
        self.textChanged.emit(self.text())

    def text(self):
        if not self.manual.isChecked():return datetime.now(self.zone).strftime('%Y-%m-%d %H:%M')
        return (self.date.text().strip()+' '+self.time.text().strip()).strip()

    def setText(self, value):
        self.manual.setChecked(True)
        date,_,clock=value.partition(' ')
        self._display(date,clock)
        self.textChanged.emit(self.text())

    def clear(self):
        self.manual.setChecked(False)
        self._tick()

    def set_zone(self, name):
        new_zone=display_zone(name)
        converted=None
        if self.manual.isChecked():
            # Validate before mutation; never reinterpret an incomplete manual entry.
            converted=datetime.strptime(self.text(), '%Y-%m-%d %H:%M').replace(tzinfo=self.zone).astimezone(new_zone)
        self.zone_name=name;self.zone=new_zone;self.zone_label.setText(name)
        if converted:self._display(converted.strftime('%Y-%m-%d'),converted.strftime('%H:%M'))
        else:self._tick()
        # A display-zone change is not a QSO edit and must not invalidate auto logging.
