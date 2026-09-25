"""Single-instance, non-modal radio controls with a coalesced tuning target."""
from decimal import Decimal, InvalidOperation
import math
import time
from PySide6.QtCore import Qt, QTimer, Signal, QPointF
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QCheckBox, QGroupBox
from .background import BackgroundJob
from .formatting import frequency_text

# Recall presets only; not transmit permissions. Use last observed frequency thereafter.
BANDS = [('1.8',1800000,2000000,1908000),('3.5',3500000,4000000,3520000),
 ('7',7000000,7300000,7040000),('10',10100000,10150000,10130000),
 ('14',14000000,14350000,14080000),('18',18068000,18168000,18100000),
 ('21',21000000,21450000,21080000),('24',24890000,24990000,24920000),
 ('28',28000000,29700000,28080000),('50',50000000,54000000,50200000),
 ('144',144000000,148000000,144100000),('430',430000000,450000000,430100000),
 ('1.2G',1240000000,1300000000,1296100000),('2.4G',2400000000,2450000000,2400100000),
 ('5.6G',5650000000,5850000000,5760100000),('10G',10000000000,10500000000,10450100000)]

def model_bands(model):
    if model == 'IC-905': return BANDS[10:]
    if model == 'IC-9700': return BANDS[10:13]
    if model in ('IC-705','IC-7100','FT-991 / FT-991A','FTX-1'): return BANDS[:12]
    if model == 'その他ICOM': return BANDS
    return BANDS[:10]

class JogDial(QWidget):
    steps=Signal(int)
    def __init__(self,parent=None):
        super().__init__(parent); self.setFixedSize(174,174)
        self.setToolTip('円周に沿ってドラッグ：時計回り＋、反時計回り－。ホイールは標準で手前＋、奥－')
        self.last=None; self.remainder=0.; self.wheel_remainder=0.; self.angle=0.; self.wheel_reverse=False
    def paintEvent(self,event):
        p=QPainter(self); p.setRenderHint(QPainter.Antialiasing); p.translate(self.rect().center())
        p.setPen(QPen(QColor('#bc670d'),2)); p.setBrush(QColor('#ffb34c' if self.last else '#f5c37e'))
        p.drawEllipse(QPointF(0,0),65,65)
        for i in range(24):
            a=i*math.pi/12
            p.drawLine(QPointF(69*math.sin(a),69*math.cos(a)),QPointF(75*math.sin(a),75*math.cos(a)))
        a=math.radians(self.angle); p.setBrush(QColor('#fff7e9'))
        p.drawEllipse(QPointF(44*math.sin(a),-44*math.cos(a)),9,9)
        p.drawText(-24,-8,48,24,Qt.AlignCenter,'TUNE'); p.end()
    def turn(self,n):
        if n: self.angle+=n*15; self.steps.emit(n); self.update()
    def pointer_angle(self, pos):
        delta=pos-QPointF(self.rect().center())
        if math.hypot(delta.x(),delta.y())<18: return None
        return math.degrees(math.atan2(delta.x(),-delta.y()))
    def mousePressEvent(self,e):
        if e.button()==Qt.LeftButton and self.isEnabled():
            self.last=self.pointer_angle(e.position()); self.remainder=0.; self.update(); e.accept()
    def mouseMoveEvent(self,e):
        if not (e.buttons() & Qt.LeftButton) or not self.isEnabled(): return
        angle=self.pointer_angle(e.position())
        if angle is None: self.last=None; return
        if self.last is None: self.last=angle; return
        delta=(angle-self.last+180)%360-180; self.last=angle
        self.angle+=delta; self.remainder+=delta
        n=int(self.remainder/15); self.remainder-=n*15
        if n: self.steps.emit(n)
        self.update()
    def mouseReleaseEvent(self,e): self.last=None; self.update()
    def wheelEvent(self,e):
        if not self.isEnabled(): return
        self.wheel_remainder+=e.angleDelta().y()/120*(1 if self.wheel_reverse else -1)
        n=int(self.wheel_remainder); self.wheel_remainder-=n; self.turn(n); e.accept()

class ControlWindow(QDialog):
    def __init__(self,main):
        super().__init__(main,Qt.Window); self.main=main
        self.setWindowTitle('PSRTTY コントロール'); self.setModal(False); self.resize(480,565)
        self.busy=False; self.pending=None; self.target=None; self.feature_pending=None
        self.states={}; self.last_poll=0.; self.controller=None; self.band_memory={}; self.band_profile=None
        root=QVBoxLayout(self); self.frequency=QLabel('---.------ MHz'); self.frequency.setObjectName('freqLabel'); root.addWidget(self.frequency)
        row=QHBoxLayout(); self.entry=QLineEdit(); self.entry.setPlaceholderText('周波数 MHz')
        self.apply=QPushButton('設定'); self.apply.clicked.connect(self.apply_frequency); self.entry.returnPressed.connect(self.apply_frequency)
        row.addWidget(self.entry,1); row.addWidget(QLabel('MHz')); row.addWidget(self.apply); root.addLayout(row)
        root.addWidget(QLabel('バンド：MHz（GはGHz）'))
        self.band_grid=QGridLayout(); root.addLayout(self.band_grid); self.band_buttons=[]
        row=QHBoxLayout(); row.addStretch(1)
        self.minus=QPushButton('－'); self.minus.clicked.connect(lambda:self.nudge(-1)); row.addWidget(self.minus)
        self.dial=JogDial(); self.dial.steps.connect(self.nudge); row.addWidget(self.dial)
        self.plus=QPushButton('＋'); self.plus.clicked.connect(lambda:self.nudge(1)); row.addWidget(self.plus); row.addStretch(1); root.addLayout(row)
        row=QHBoxLayout(); row.addWidget(QLabel('STEP')); self.step=QComboBox()
        for title,n in [('1 Hz',1),('10 Hz',10),('100 Hz',100),('1 kHz',1000),('10 kHz',10000)]: self.step.addItem(title,n)
        self.step.setCurrentIndex(1)
        row.addWidget(self.step); row.addStretch(1)
        self.reverse=QCheckBox('ホイール反転'); self.reverse.setChecked(bool(main.store.data['ui'].get('wheel_reverse',False)))
        self.dial.wheel_reverse=self.reverse.isChecked(); self.reverse.toggled.connect(self.set_wheel_reverse)
        row.addWidget(self.reverse); root.addLayout(row)
        row=QHBoxLayout(); self.buttons={}
        for name in ('NB','NR','NOTCH'):
            b=QPushButton(name+' —'); b.setCheckable(True); self.buttons[name]=b
            b.clicked.connect(lambda checked=False,n=name:self.toggle_feature(n)); 
            if name!='NOTCH': row.addWidget(b)
        notch_box=QGroupBox('NOTCH'); notch_row=QHBoxLayout(notch_box); notch_row.addWidget(self.buttons['NOTCH'])
        self.notch=QComboBox(); self.notch.addItem('自動','AN'); self.notch.addItem('手動','MN')
        self.notch.currentIndexChanged.connect(self.refresh_enabled); notch_row.addWidget(self.notch); row.addWidget(notch_box); root.addLayout(row)
        self.filter_box=QGroupBox('FILTER'); filter_row=QHBoxLayout(self.filter_box)
        self.filter_buttons=[]
        for value in (1,2,3):
            button=QPushButton(f'FIL{value}'); button.setCheckable(True)
            button.clicked.connect(lambda checked=False,v=value:self.request_filter(v))
            filter_row.addWidget(button); self.filter_buttons.append(button)
        self.width_label=QLabel('WIDTH'); filter_row.addWidget(self.width_label)
        self.width=QComboBox(); filter_row.addWidget(self.width,1)
        self.width.activated.connect(lambda i:self.request_filter(self.width.itemData(i)))
        self.narrow=QPushButton('NARROW —'); self.narrow.setCheckable(True)
        self.narrow.clicked.connect(self.request_narrow); filter_row.addWidget(self.narrow)
        root.addWidget(self.filter_box)
        self.note=QLabel(); self.note.setWordWrap(True); root.addWidget(self.note)
        self.setStyleSheet('QPushButton:checked { background: #ed8b19; color: white; border: 2px solid #9b4c00; }')
        self.timer=QTimer(self); self.timer.setInterval(100); self.timer.timeout.connect(self.tick); self.timer.start(); self.refresh_enabled()
    def set_wheel_reverse(self, checked):
        self.dial.wheel_reverse=checked; self.dial.wheel_remainder=0.
        self.main.store.data['ui']['wheel_reverse']=checked; self.main.store.save()
    def ready(self):
        m=self.main
        return m._connected() and not m.closing and m.active_tx_id is None and not m.audio._tx_active and not m.auto_cq_active and m.pending_manual is None
    def reveal(self):
        self.showNormal(); area=self.main.screen().availableGeometry()
        self.resize(min(480,area.width()),min(565,area.height()))
        rect=self.frameGeometry(); rect.moveCenter(self.main.frameGeometry().center())
        rect.moveLeft(max(area.left(),min(rect.left(),area.right()-rect.width()+1)))
        rect.moveTop(max(area.top(),min(rect.top(),area.bottom()-rect.height()+1)))
        self.move(rect.topLeft()); self.raise_(); self.activateWindow(); self.last_poll=0; self.refresh_enabled()
    def observe_frequency(self,hz):
        if hz:
            self.frequency.setText(frequency_text(hz))
            if not self.entry.isModified() and not self.entry.hasFocus(): self.entry.setText(f'{hz/1e6:.6f}')
            if self.target is None:
                model=self.main.store.data['radio']['model']
                for label,low,high,default in model_bands(model):
                    if low<=hz<=high: self.band_memory[(model,label)]=hz
        else: self.frequency.setText(frequency_text(None))
        for band,b in self.band_buttons: b.setChecked(bool(hz and band[1]<=hz<=band[2]))
    def refresh_enabled(self):
        model=self.main.store.data['radio']['model']
        if model!=self.band_profile:
            self.band_profile=model
            for _,b in self.band_buttons: self.band_grid.removeWidget(b); b.deleteLater()
            self.band_buttons=[]
            for i,band in enumerate(model_bands(model)):
                b=QPushButton(band[0]); b.setCheckable(True)
                b.clicked.connect(lambda checked=False,v=band:self.request_frequency(self.band_memory.get((self.band_profile,v[0]),v[3])))
                self.band_grid.addWidget(b,i//6,i%6); self.band_buttons.append((band,b))
        yaesu=model in ('FT-991 / FT-991A','FTX-1')
        self.notch.setItemText(0,'DNF' if yaesu else '自動')
        self.notch.setItemText(1,'NOTCH' if yaesu else '手動')
        ready=self.ready()
        if self.controller is not self.main.radio:
            self.controller=self.main.radio; self.states={}; self.pending=self.target=self.feature_pending=None; self.last_poll=0
        if not ready: self.pending=self.target=self.feature_pending=None; self.dial.last=None
        for w in [self.entry,self.apply,self.dial,self.minus,self.plus]+[b for _,b in self.band_buttons]: w.setEnabled(ready)
        for name,b in self.buttons.items():
            key=self.notch.currentData() if name=='NOTCH' else name; value=self.states.get(key) if ready else None
            b.setText((('' if name=='NOTCH' else ('DNR' if yaesu and name=='NR' else name))+' '+('ON' if value is True else 'OFF' if value is False else '—')).strip())
            b.setChecked(value is True); b.setEnabled(ready and value is not None and not self.busy and self.feature_pending is None)
            b.setToolTip('状態未取得／この機種・モードでは非対応' if value is None else ('自動ノッチ' if key=='AN' else '手動ノッチ' if key=='MN' else name))
        self.refresh_filter(ready)
        if not ready: self.note.setText('接続後、受信中に操作できます。送信中・Auto CQ中は停止します。')
        self.observe_frequency(self.main.current_freq_hz)
    def refresh_filter(self, ready):
        yaesu=self.band_profile in ('FT-991 / FT-991A','FTX-1')
        state=self.states.get('FILTER') if ready else None
        if not isinstance(state,dict): state=None
        enabled=ready and not self.busy and self.feature_pending is None and bool(state)
        for i,button in enumerate(self.filter_buttons,1):
            button.setVisible(not yaesu); button.setEnabled(enabled)
            button.setChecked(bool(state and state.get('value')==i))
        for widget in (self.width_label,self.width,self.narrow): widget.setVisible(yaesu)
        options=state.get('options',[]) if state else []
        current=[(self.width.itemData(i),self.width.itemText(i)) for i in range(self.width.count())]
        if current!=options:
            self.width.clear()
            for value,label in options: self.width.addItem(label,value)
        self.width.setCurrentIndex(self.width.findData(state.get('value')) if state else -1)
        self.width.setEnabled(enabled and bool(options) and state.get('value') is not None)
        value=state.get('narrow') if state else None
        self.narrow.setText('NARROW '+('ON' if value is True else 'OFF' if value is False else '—'))
        self.narrow.setChecked(value is True); self.narrow.setEnabled(enabled and value is not None)
        self.filter_box.setToolTip('無線機側の受信フィルター。状態未取得・非対応時は操作できません。')

    def request_filter(self, value):
        state=self.states.get('FILTER')
        if self.ready() and not self.busy and isinstance(state,dict) and value in dict(state['options']):
            self.feature_pending=('FILTER',(value,dict(state)))
        self.refresh_enabled()

    def request_narrow(self, checked=False):
        state=self.states.get('FILTER')
        if self.ready() and not self.busy and isinstance(state,dict) and state.get('narrow') is not None:
            self.feature_pending=('NARROW',(not state['narrow'],dict(state)))
        self.refresh_enabled()

    def apply_frequency(self):
        try:
            value=Decimal(self.entry.text().strip())*1000000
            if not value.is_finite() or value!=value.to_integral_value(): raise ValueError()
            hz=int(value)
        except (InvalidOperation,ValueError,OverflowError):
            self.note.setText('MHzを数値で入力してください（小数点以下6桁まで）。'); return
        self.entry.setModified(False); self.request_frequency(hz)
    def request_frequency(self,hz):
        if not self.ready(): return
        maximum=15000000000 if self.band_profile in ('IC-905','その他ICOM') else 1500000000 if self.band_profile=='IC-9700' else 470000001 if len(model_bands(self.band_profile))>10 else 60000000
        if not 100000<=hz<maximum:
            self.note.setText('機種の周波数範囲を確認してください。'); return
        self.pending=self.target=hz; self.note.setText(f'設定待ち: {hz/1e6:.6f} MHz')
    def nudge(self,n):
        base=self.target if self.target is not None else self.main.current_freq_hz
        if base: self.request_frequency(base+n*self.step.currentData())
    def toggle_feature(self,name):
        key=self.notch.currentData() if name=='NOTCH' else name; value=self.states.get(key)
        if self.ready() and not self.busy and value is not None: self.feature_pending=(key,not value)
        self.refresh_enabled()
    def tick(self):
        self.refresh_enabled()
        if not self.isVisible() or not self.ready() or self.busy or self.main.polling: return
        ctl=self.main.radio; generation=self.main.connection_generation
        hz,self.pending=self.pending,None; feature,self.feature_pending=self.feature_pending,None
        if hz is None and feature is None and time.monotonic()-self.last_poll<1.2: return
        self.busy=True; self.last_poll=time.monotonic()
        def work():
            ok=True
            if hz is not None: ok=ctl.set_frequency(hz)
            if feature is not None:
                if feature[0]=='FILTER': ok=ctl.set_filter(*feature[1]) and ok
                elif feature[0]=='NARROW': ok=ctl.set_narrow(*feature[1]) and ok
                else: ok=ctl.set_feature(*feature) and ok
            freq=ctl.read_frequency(); states={}
            if hz is None:
                for name in ('NB','NR','AN','MN'):
                    if ctl.cancel.is_set(): break
                    states[name]=ctl.read_feature(name)
                if not ctl.cancel.is_set(): states['FILTER']=ctl.read_filter()
            return ok,freq,states
        def done(result,error):
            self.busy=False
            if generation!=self.main.connection_generation or self.main.radio is not ctl: return
            if error:
                self.states={}; self.target=None; self.note.setText(f'操作失敗: {error}'); self.main._radio_observed(None,error)
            else:
                ok,freq,states=result; self.states.update(states)
                if self.pending is None: self.target=None
                self.main._radio_observed(freq)
                self.note.setText('無線機の状態を取得しました。' if ok else '設定できませんでした。無線機のモード・送信状態を確認してください。')
            self.refresh_enabled()
        self.job=BackgroundJob(self,work,done)
    def hideEvent(self,event):
        self.pending=self.target=self.feature_pending=None; super().hideEvent(event)
