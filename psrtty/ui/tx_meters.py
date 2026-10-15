"""Compact TX ALC onset indicator. Raw zero is not a measurement of headroom."""
from PySide6.QtCore import QRectF, QSize
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from ..i18n import tr

class ALCGauge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(125,26)
        self.position=0.; self.color='#70cde5'
        self.fsk=None
        self.setToolTip(tr('v115.alc_hint'))
    def sizeHint(self): return QSize(125,26)
    def set_reading(self, value, gain, onset, transmitting=False):
        self.fsk=None
        self.setToolTip(tr('v115.alc_hint'))
        threshold=.35
        if value < 2:
            self.color='#70cde5'
            self.position=threshold*.85 if transmitting else 0.
        elif value == 2:
            self.color='#208341'; self.position=threshold
        else:
            self.color='#e88919'; self.position=threshold+(1-threshold)*min(1,(value-2)/118)
        if onset is not None and value >= 2 and gain > onset+1e-9:
            self.color='#e88919'
        self.update()
    def set_unavailable(self):
        self.fsk=None
        self.setToolTip(tr('v115.alc_hint'))
        self.position=0.;self.color="#a59d92";self.update()
    def set_fsk(self, confirmed):
        self.fsk=bool(confirmed);self.position=0.
        self.color='#208341' if confirmed else '#a59d92'
        self.setToolTip(tr('v120.fsk_hint') if confirmed else '')
        self.update()
    def paintEvent(self,event):
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        if self.fsk is not None:
            from PySide6.QtCore import Qt
            rect=QRectF(29,5,94,16)
            painter.setPen(QPen(QColor('#c8a87f'),1));painter.setBrush(QColor('#fffdf9'))
            painter.drawRoundedRect(rect,3,3)
            painter.setPen(QColor(self.color))
            painter.drawText(rect,Qt.AlignCenter,'FSK' if self.fsk else '--')
            return
        painter.setPen(QColor('#604b37')); painter.drawText(0,18,'ALC')
        rect=QRectF(29,5,94,16)
        painter.setPen(QPen(QColor('#c8a87f'),1)); painter.setBrush(QColor('#fffdf9')); painter.drawRoundedRect(rect,3,3)
        if self.position == 0:
            painter.setPen(QPen(QColor(self.color),2)); painter.drawLine(31,7,31,19)
        if self.position > 0:
            painter.setPen(QPen(QColor(self.color),0)); painter.setBrush(QColor(self.color))
            painter.drawRoundedRect(QRectF(30,6,92*self.position,14),2,2)
        painter.setPen(QPen(QColor('#604b37'),1)); x=30+92*.35
        painter.drawLine(int(x),4,int(x),22)


def swr_color(value):
    if value is None:return None
    if value>=2.8:return '#d00000'
    if value>=2.2:return '#d94324'
    if value>=1.8:return '#df7900'
    return None

class RadioMeterText(QWidget):
    """Two plain-text rows; SWR color never changes the PWR row."""
    def __init__(self,parent=None):
        super().__init__(parent);self._text=''
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.swr_label=QLabel();self.pwr_label=QLabel()
        layout.addWidget(self.swr_label);layout.addWidget(self.pwr_label)
        self.swr_label.hide();self.pwr_label.hide()
    def text(self):return self._text
    def setText(self,text):
        self._text=text;lines=text.splitlines()
        for prefix,label in [('SWR',self.swr_label),('PWR',self.pwr_label)]:
            row=next((row for row in lines if row.startswith(prefix+' ')), '')
            label.setText(row);label.setVisible(bool(row))
    def set_swr_value(self,value):
        color=swr_color(value)
        self.swr_label.setStyleSheet('color: '+color+';' if color else '')
