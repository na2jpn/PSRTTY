"""Compact, opt-in receive-only window with independent A/B tuning."""
from __future__ import annotations
from ..i18n import tr

import re
import time

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextCursor
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QPlainTextEdit, QVBoxLayout, QWidget)

from ..sub_decode import SubDecodeWorker, pair_candidates

COLORS = ('#dd3030', '#3154d7')


class SubTextOutput(QPlainTextEdit):
    line_clicked = Signal(str)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            text = self.cursorForPosition(event.position().toPoint()).block().text().strip()
            if text:
                self.line_clicked.emit(text)
        super().mouseReleaseEvent(event)


def valid_position(center, index, main_center, shift, other_center=None):
    if not 100+shift/2 <= center <= 3900-shift/2:
        return False
    # Manual tuning may cross the main position; only overlapping tone pairs
    # are excluded. The sweep's preferred starting sides are handled separately.
    targets = [main_center]
    if other_center is not None:
        targets.append(other_center)
    return all(min(abs(t-u) for t in (center-shift/2,center+shift/2)
                   for u in (other-shift/2,other+shift/2)) >= 15 for other in targets)


class SubSpectrum(QWidget):
    moved = Signal(int, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.setMaximumHeight(110)
        self.setMouseTracking(True)
        self.main_center = 2210.
        self.width_hz = 1000.
        self.shift = 170.
        self.centers = [1960., 2460.]
        self.freqs = np.empty(0); self.power = np.empty(0)
        self.drag = None
        self.drag_origin = None
        self.setToolTip(tr('赤い線はA、青い線はB。各2本の線をドラッグして受信位置を動かします。'))

    def set_spectrum(self, freqs, power, main_center, width, shift, centers):
        self.freqs = freqs; self.power = power
        self.main_center = float(main_center); self.width_hz = float(width)
        self.shift = abs(float(shift)); self.centers = list(centers)
        self.update()

    def _x(self, hz):
        return (hz-self.main_center+self.width_hz/2) / self.width_hz * max(1,self.width())

    def _freq(self, x):
        return self.main_center-self.width_hz/2+x/max(1,self.width())*self.width_hz

    def paintEvent(self, event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#171717'))
        lo=self.main_center-self.width_hz/2;hi=lo+self.width_hz
        p.fillRect(int(self._x(self.main_center-70)),0,
                   max(1,int(self._x(self.main_center+70)-self._x(self.main_center-70))),
                   self.height(),QColor(120,120,120,65))
        if len(self.freqs) and len(self.power):
            mask=(self.freqs>=lo)&(self.freqs<=hi)
            values=self.freqs[mask];db=self.power[mask]
            if len(values)>1:
                path=QPainterPath()
                for k,(f,v) in enumerate(zip(values,db)):
                    y=self.height()-6-max(0.,min(1.,(float(v)+90)/80))*(self.height()-15)
                    if k:path.lineTo(self._x(float(f)),y)
                    else:path.moveTo(self._x(float(f)),y)
                p.setPen(QPen(QColor('#eacb91'),1));p.drawPath(path)
        for index,center in enumerate(self.centers):
            color=QColor(COLORS[index]);p.setPen(QPen(color,2))
            for freq in (center-self.shift/2,center+self.shift/2):
                x=int(self._x(freq));p.drawLine(x,0,x,self.height())
            p.drawText(int(self._x(center))-5,14,'AB'[index])
        p.setPen(QPen(QColor('#aaa'),1));p.drawText(5,self.height()-5,f'{lo:.0f} Hz')
        p.drawText(max(0,self.width()-70),self.height()-5,f'{hi:.0f} Hz')

    def mousePressEvent(self,event):
        if event.button()!=Qt.LeftButton:return
        x=event.position().x(); y=event.position().y()
        handles=[]
        for index,center in enumerate(self.centers):
            positions=[self._x(center-self.shift/2),self._x(center+self.shift/2)]
            # The A/B label between the two lines is a handle as well.
            distances=[abs(x-v) for v in positions]
            if y<=22:distances.append(abs(x-self._x(center)))
            handles.append(min(distances))
        index=int(np.argmin(handles))
        if handles[index]>14:return
        self.drag=index
        self.drag_origin=(x,self.centers[index])
        self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def _drag_to(self,hz):
        if self.drag is None:return
        index=self.drag
        other=self.centers[1-index]
        if valid_position(hz,index,self.main_center,self.shift,other):
            self.moved.emit(index,hz)

    def mouseMoveEvent(self,event):
        if self.drag is not None:
            x,center=self.drag_origin
            self._drag_to(center+(event.position().x()-x)*self.width_hz/max(1,self.width()))
        else:
            x=event.position().x();y=event.position().y()
            near=any(min([abs(x-self._x(c-self.shift/2)),abs(x-self._x(c+self.shift/2))]
                         + ([abs(x-self._x(c))] if y<=22 else []))<=14 for c in self.centers)
            self.setCursor(Qt.OpenHandCursor if near else Qt.ArrowCursor)

    def mouseReleaseEvent(self,event):
        self.drag=None
        self.drag_origin=None
        self.unsetCursor()


class SubDecodeWindow(QDialog):
    def __init__(self, main):
        super().__init__(None,Qt.Window)
        self.main=main
        from .window_state import independent_tool_window
        independent_tool_window(self, main)
        self.setWindowTitle(tr('PSRTTY サブデコ'))
        self.setMinimumSize(400,300);self.resize(480,400)
        self.worker=SubDecodeWorker(main.audio.sample_rate,
                                    lambda i,c: main.bridge.sub_char.emit(i,c))
        self.centers=[float((main.spectrum.mark_hz+main.spectrum.space_hz)/2)+d
                      for d in (-120,120)]
        self.last_change=[0.,0.];self.last_char=[0.,0.]
        self.last_sweep=[0.,0.];self.duplicate=[False,False]
        self.buffers=['',''];self.sub_recent=['',''];self.main_recent=''
        self.main_last_char=0.
        root=QVBoxLayout(self);root.setContentsMargins(8,8,8,8);root.setSpacing(4)
        self.scope=SubSpectrum();self.scope.moved.connect(self._manual)
        root.addWidget(self.scope)
        options=QHBoxLayout();self.checks=[];self.offsets=[]
        for index in range(2):
            check=QCheckBox(tr('{side}：自動スイープ').format(side="AB"[index]));check.setChecked(True)
            check.setStyleSheet(f'color:{COLORS[index]};font-weight:bold')
            options.addWidget(check);self.checks.append(check)
            label=QLabel();label.setStyleSheet(f'color:{COLORS[index]}')
            options.addWidget(label);self.offsets.append(label)
        root.addLayout(options)
        row=QHBoxLayout();self.outputs=[];self.output_lines=[0,0]
        for index in range(2):
            column=QVBoxLayout();header=QLabel(f'{"AB"[index]}-RX')
            header.setStyleSheet(f'color:{COLORS[index]};font-weight:bold')
            column.addWidget(header)
            output=SubTextOutput();output.setReadOnly(True)
            output.line_clicked.connect(self._line_clicked)
            font=output.font();font.setPointSize(max(8,main.store.data['ui'].get('rx_card_font_size',12)-1))
            output.setFont(font);output.setStyleSheet('background:#fffdf8;')
            output.document().setMaximumBlockCount(150)
            column.addWidget(output,1);self.outputs.append(output)
            row.addLayout(column,1)
        root.addLayout(row,1)
        self.timer=QTimer(self);self.timer.setInterval(650);self.timer.timeout.connect(self.refresh)
        self.load_level=0;self.clear_cycles=0;self.last_dropped=0
        self.idle=QTimer(self);self.idle.setInterval(300);self.idle.timeout.connect(self._flush_idle)
        self._configure_all()
        self._last_shift=main.spectrum.space_hz-main.spectrum.mark_hz

    def showEvent(self,event):
        self.main.audio.sub_worker=self.worker
        self.worker.start();self.timer.start();self.idle.start()
        self.refresh()
        super().showEvent(event)

    def hideEvent(self,event):
        self.timer.stop();self.idle.stop()
        from .window_state import save_window
        self.main.store.data['ui']['sub_window']=save_window(self)
        if self.main.audio.sub_worker is self.worker:
            self.main.audio.sub_worker=None
        self.worker.stop()
        super().hideEvent(event)

    def _configure_all(self):
        for index in range(2):self._configure(index)

    def _configure(self,index):
        main=self.main;shift=main.spectrum.space_hz-main.spectrum.mark_hz
        center=self.centers[index];a=main.store.data['advanced']
        self.worker.configure(index,a['rtty_baud'],center-shift/2,
                              center+shift/2,a['invert'],int(main.decode_sq.currentData()))

    def _move(self,index,center):
        if abs(self.centers[index]-center)<2:return
        self.centers[index]=center;self.last_change[index]=time.monotonic()
        self.scope.centers[index]=center;self.scope.update()
        self.sub_recent[index]=''
        self._configure(index);self._label()

    def _manual(self,index,center):
        self.checks[index].setChecked(False)
        self._move(index,center)

    def _label(self):
        center=(self.main.spectrum.mark_hz+self.main.spectrum.space_hz)/2
        for index in range(2):
            self.offsets[index].setText(tr('メインから{offset:+.0f} Hz').format(offset=self.centers[index]-center))

    def refresh(self):
        main=self.main
        overloaded=self.worker.dropped>self.last_dropped or self.worker.backlog()>=5
        self.last_dropped=self.worker.dropped
        if overloaded:
            self.load_level=min(3,self.load_level+1);self.clear_cycles=0
        else:
            self.clear_cycles+=1
            if self.clear_cycles>=8 and self.load_level:
                self.load_level-=1;self.clear_cycles=0
        interval=(650,900,1300,1800)[self.load_level]
        if self.timer.interval()!=interval:self.timer.setInterval(interval)
        center=(main.spectrum.mark_hz+main.spectrum.space_hz)/2
        shift=abs(main.spectrum.space_hz-main.spectrum.mark_hz)
        signed_shift=main.spectrum.space_hz-main.spectrum.mark_hz
        if signed_shift!=self._last_shift:
            self._last_shift=signed_shift
            self._configure_all()
        width=main.spectrum.width_hz
        if main.last_spectrum:
            freqs,power=main.last_spectrum
            self.scope.set_spectrum(freqs,power,center,width,shift,self.centers)
        self._label()
        if main.active_tx_id is not None or not main.last_spectrum:return
        now=time.monotonic();freqs,power=main.last_spectrum
        lo,hi=center-width/2,center+width/2
        mask=(freqs>=lo)&(freqs<=hi)
        for index in range(2):
            if not self.checks[index].isChecked():continue
            if now-self.last_char[index]<1.5 and not self.duplicate[index]:continue
            if now-self.last_sweep[index]<2.5+self.load_level*.8:continue
            other=self.centers[1-index]
            candidates=pair_candidates(freqs[mask],power[mask],center,shift,index,other)
            if self.duplicate[index]:
                candidates=[c for c in candidates if abs(c[0]-self.centers[index])>=50]
            if candidates:
                # After silence, step from the outer edge toward main;
                # do not repeatedly retry the same empty pair.
                current=abs(self.centers[index]-center)
                next_inner=[c for c in candidates if abs(c[0]-center)<current-25]
                target=(next_inner[0] if next_inner else candidates[0])[0]
                if valid_position(target,index,center,shift,other):
                    self._move(index,target)
                    self.duplicate[index]=False
            self.last_sweep[index]=now

    def main_char(self,char):
        self.main_last_char=time.monotonic()
        if char in '\r\n':self.main_recent+=' '
        else:self.main_recent+=char
        self.main_recent=self.main_recent[-300:]
        for index in range(2):self._detect_duplicate(index)

    def _detect_duplicate(self,index):
        sub=re.sub(r'[^A-Z0-9]','',self.sub_recent[index].upper())
        main=re.sub(r'[^A-Z0-9]','',self.main_recent.upper())
        if (abs(self.main_last_char-self.last_char[index])<=3 and
            len(sub)>=10 and len(main)>=10 and
            (sub[-10:] in main[-100:] or main[-10:] in sub[-100:])):
            self.duplicate[index]=True

    def sub_char(self,index,char):
        if not self.isVisible() or index not in (0,1):return
        self.last_char[index]=time.monotonic()
        if char in '\r\n':
            self._flush(index);return
        self.buffers[index]+=char
        self.sub_recent[index]=(self.sub_recent[index]+char)[-300:]
        self._detect_duplicate(index)
        if len(self.buffers[index])>=100:self._flush(index)

    def _flush_idle(self):
        now=time.monotonic()
        for index in range(2):
            if self.buffers[index] and now-self.last_char[index]>.9:
                self._flush(index)

    def _flush(self,index):
        text=' '.join(self.buffers[index].split());self.buffers[index]=''
        if text:
            output=self.outputs[index]
            output.appendPlainText(text)
            cursor=output.textCursor()
            cursor.movePosition(QTextCursor.End)
            block_format=cursor.blockFormat()
            tint = ('#f5e8e8', '#e8eef8')[index]
            block_format.setBackground(QColor(tint if self.output_lines[index] % 2 else '#ffffff'))
            cursor.setBlockFormat(block_format)
            self.output_lines[index]+=1

    def _line_clicked(self,text):
        from ..parser import parse_exchange
        parsed=parse_exchange(text,self.main.my_call.text(),
            cqww=self.main.store.data.get('macro_template') == 'CQ WW RTTY DXコンテスト')
        if parsed.callsign:
            self.main.q_call.setText(parsed.callsign)
            self.main.call_locked=True
            self.main._refresh_macros()
