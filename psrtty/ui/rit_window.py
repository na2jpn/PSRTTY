"""Connection-scoped RIT state and an independently owned nonmodal tool."""
import time
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QSlider, QPushButton, QSpinBox, QComboBox
from ..i18n import tr
from .background import BackgroundJob
from .window_state import independent_tool_window, place_tool_window, save_window


class RITSlider(QSlider):
    """One wheel notch is one selected STEP, independent of scroll lines."""
    def wheelEvent(self,event):
        if not self.isEnabled():
            event.ignore();return
        self._wheel_delta=getattr(self,'_wheel_delta',0)+event.angleDelta().y()
        steps=int(self._wheel_delta/120);self._wheel_delta-=steps*120
        if steps:self.setValue(self.value()+steps*self.singleStep())
        event.accept()


class RITService(QObject):
    changed=Signal()
    def __init__(self, main):
        super().__init__(main); self.main=main
        self.state=None; self.identity=None; self.busy=False; self.pending=None; self.last_poll=0.; self.error=''; self.inflight=None
        self._disabled_marker=None
        self.timer=QTimer(self); self.timer.setInterval(100); self.timer.timeout.connect(self.tick); self.timer.start()

    def invalidate(self):
        self.state=None; self.identity=None; self.pending=None; self.last_poll=0.; self.error=''; self.inflight=None
        self.changed.emit()

    def ready(self):
        m=self.main
        return (not m.closing and m._connected() and not m.connecting and
                not getattr(m.radio,'manual',False) and m.active_tx_id is None and
                not m.audio._tx_active and not m.auto_cq_active and not m.antenna_tuning and
                m.pending_manual is None)

    def request(self, **change):
        if not self.ready() or not self.state:return
        if 'offset' in change and not self.state.get('offset_write'):return
        if 'on' in change and not self.state.get('on_write'):return
        self.pending={**(self.pending or {}),**change}
        self.tick()
        self.changed.emit()  # Explicit edits only; periodic reads do not repaint.

    def tick(self):
        m=self.main
        identity=(id(m.radio),m.connection_generation) if m._connected() else None
        if identity!=self.identity:
            self.invalidate(); self.identity=identity
        if not self.ready():
            self.pending=None
            # Refresh enablement on transitions, not ten times per second.
            marker=(identity, self.ready())
            if getattr(self, '_disabled_marker', None)!=marker:
                self._disabled_marker=marker; self.changed.emit()
            return
        if self._disabled_marker is not None:
            self._disabled_marker=None; self.changed.emit()
        if m.control_window and any(x is not None for x in (m.control_window.pending, m.control_window.feature_pending, m.control_window.mode_pending)):return
        if self.busy or m.polling or getattr(m,'alc_busy',False) or (m.control_window and m.control_window.busy):return
        visible=bool(m.rit_window and m.rit_window.isVisible())
        if visible and m.rit_window.slider.isSliderDown(): return
        interval=3. if visible else 5.
        if self.pending is None and time.monotonic()-self.last_poll<interval:return
        ctl=m.radio; generation=m.connection_generation; request,self.pending=self.pending,None
        self.busy=True; self.inflight=request; self.last_poll=time.monotonic()
        def work():
            with ctl._lock:
                if ctl.cancel.is_set():return None,False
                ok=ctl.set_rit(**request) if request else True
                return ctl.read_rit(),ok
        def done(result,error):
            self.busy=False; self.inflight=None
            if generation!=m.connection_generation or m.radio is not ctl:return
            previous=(self.state,self.error)
            self.state=dict(result[0]) if result and result[0] and not error else None
            self.error=tr('v127.rit_failed') if error or request and (not result or not result[1]) else ''
            if previous!=(self.state,self.error) or request:
                self.changed.emit()
            if m.control_window:m.control_window.refresh_enabled()
        self.job=BackgroundJob(self,work,done)


class RITWindow(QDialog):
    def __init__(self,main):
        super().__init__(None,Qt.Window); self.main=main; self.service=main.rit_service
        independent_tool_window(self,main); self.setModal(False); self.setWindowTitle('RIT')
        root=QVBoxLayout(self)
        self.value=QLabel('— Hz'); self.value.setAlignment(Qt.AlignCenter)
        self.value.setStyleSheet('font-size:22px;'); root.addWidget(self.value)
        self.on=QCheckBox('RIT ON'); root.addWidget(self.on)
        self.slider=RITSlider(Qt.Horizontal); self.slider.setTracking(False); self.slider.setRange(-9999,9999)
        slider_row=QHBoxLayout()
        self.minus=QPushButton('−'); self.plus=QPushButton('+')
        for button in (self.minus,self.plus):button.setFixedWidth(32)
        slider_row.addWidget(self.minus);slider_row.addWidget(self.slider);slider_row.addWidget(self.plus)
        root.addLayout(slider_row)
        row=QHBoxLayout();self.amount=QSpinBox();self.amount.setRange(-9999,9999);self.amount.setSuffix(' Hz');self.amount.setKeyboardTracking(False)
        self.zero=QPushButton('0 Hz'); row.addWidget(self.amount);row.addWidget(self.zero);root.addLayout(row)
        step_row=QHBoxLayout();step_row.addWidget(QLabel('STEP'))
        self.step=QComboBox()
        for hz in (1,2,3,4,5,7,10,15,20):self.step.addItem(f'{hz} Hz',hz)
        step_row.addWidget(self.step);step_row.addStretch();root.addLayout(step_row)
        self.step.currentIndexChanged.connect(self.save_step)
        self.minus.clicked.connect(lambda:self.nudge(-1));self.plus.clicked.connect(lambda:self.nudge(1))
        self.note=QLabel(); self.note.setWordWrap(True); root.addWidget(self.note)
        self.on.clicked.connect(lambda checked:self.service.request(on=checked))
        self.slider.valueChanged.connect(lambda v:self.service.request(offset=v))
        self.amount.valueChanged.connect(lambda v:self.service.request(offset=v))
        self.zero.clicked.connect(lambda:self.service.request(offset=0))
        self.service.changed.connect(self.refresh);self.refresh()

    def save_step(self):
        self.main.store.data['advanced']['rit_step_hz']=self.step.currentData()
        self.main.store.save()
        self.apply_step()

    def apply_step(self):
        hz=self.main.store.data['advanced'].get('rit_step_hz',1)
        index=self.step.findData(hz)
        self.step.blockSignals(True);self.step.setCurrentIndex(max(0,index));self.step.blockSignals(False)
        hz=self.step.currentData()
        self.slider.setSingleStep(hz);self.slider.setPageStep(hz);self.amount.setSingleStep(hz)

    def nudge(self,direction):
        state=self.service.state
        if not state:return
        base=state['offset']
        for request in (self.service.inflight,self.service.pending):
            if request and 'offset' in request:base=request['offset']
        limit=state['limit']
        self.service.request(offset=max(-limit,min(limit,base+direction*self.step.currentData())))

    def reveal(self):
        self.showNormal();place_tool_window(self,self.main,(350,260),(300,240),self.main.store.data['ui'].get('rit_window'))
        self.raise_();self.activateWindow();self.service.last_poll=0.;self.service.tick()

    def refresh(self):
        state=self.service.state;ready=self.service.ready()
        self.apply_step()
        self.on.setEnabled(ready and bool(state and state['on_write']))
        writable=ready and bool(state and state['offset_write'] and (state.get('on_write') or type(self.main.radio).__name__=='CIVController'))
        for w in (self.slider,self.amount,self.zero,self.minus,self.plus):w.setEnabled(writable)
        if state:
            state=dict(state)
            for change in (self.service.inflight,self.service.pending):
                if change:state.update(change)
        self.value.setText(f"{state['offset']:+d} Hz" if state else '— Hz')
        for w in (self.on,self.slider,self.amount):w.blockSignals(True)
        self.on.setText('RIT —' if not state or state['on'] is None else 'RIT ON')
        self.on.setChecked(bool(state and state['on']))
        if state:
            limit=max(state['limit'],abs(state['offset']))
            self.slider.setRange(-limit,limit);self.amount.setRange(-limit,limit)
            if not self.slider.isSliderDown():self.slider.setValue(state['offset'])
            if not self.amount.hasFocus() or self.service.error:self.amount.setValue(state['offset'])
        else:
            self.amount.lineEdit().setText('—')
        for w in (self.on,self.slider,self.amount):w.blockSignals(False)
        self.note.setText(self.service.error or (tr('v127.rit_xit') if state and state['xit'] else tr('v127.rit_help') if writable else tr('v127.rit_readonly') if state else tr('v127.rit_unavailable')))

    def closeEvent(self,event):
        self.service.pending=None
        self.main.store.data['ui']['rit_window']=save_window(self)
        super().closeEvent(event)
