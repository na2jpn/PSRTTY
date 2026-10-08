"""Modeless keyboard TX with an editable pending tail and explicit stop."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QCheckBox, QPushButton, QLabel
from ..i18n import tr
from ..live_tx import LiveText
from .window_state import place_tool_window, save_window

PENDING_COLOR = '#8899AF'


class DirectTxWindow(QWidget):
    def __init__(self, main):
        super().__init__(None, Qt.Window)
        from .window_state import independent_tool_window
        independent_tool_window(self, main)
        self.main=main;self.session=None;self.sent=0;self.changing=False;self.last_text='';self.suppressed=False;self.input_times=[]
        self.setWindowTitle(tr('guide.9.title'))
        self.setWindowIcon(main.windowIcon())
        lay=QVBoxLayout(self)
        self.editor=QTextEdit();self.editor.setAcceptRichText(False);self.editor.setMinimumHeight(65)
        self.editor.setPlaceholderText(tr('ui.6ec1e6de948549b9'))
        lay.addWidget(self.editor)
        row=QHBoxLayout();left=QVBoxLayout()
        self.auto=QCheckBox(tr('ui.8f6169b00e165c20'));self.auto.setChecked(main.store.data['ui'].get('direct_auto_tx',True))
        left.addWidget(self.auto);left.addWidget(QLabel(tr('ui.14cd3a02c38b52d8')));row.addLayout(left);row.addStretch()
        self.clear_button=QPushButton(tr('ui.df8b14c87ba1216c'));self.clear_button.clicked.connect(self.clear)
        self.tx_button=QPushButton(tr('ui.c79fb302350cd0ea'));self.tx_button.clicked.connect(self.button)
        row.addWidget(self.clear_button);row.addWidget(self.tx_button);lay.addLayout(row)
        note=QLabel(tr('ui.25f3e182f89868fa'))
        note.setWordWrap(True);lay.addWidget(note)
        self.status=QLabel(tr('ui.2f3ee0fc058199a7'));self.status.setWordWrap(True);lay.addWidget(self.status)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(500);self.timer.timeout.connect(self.auto_start)
        self.editor.textChanged.connect(self.changed);self.auto.toggled.connect(self.mode_changed)
        place_tool_window(self,main,(720,220),(340,180),main.store.data['ui'].get('direct_window'))
    def focus_input(self):
        if self.isMinimized():self.showNormal()
        self.show();self.raise_();self.activateWindow();self.editor.setFocus()
    def paint(self):
        self.changing=True
        position=self.editor.textCursor().position()
        cursor=QTextCursor(self.editor.document());cursor.select(QTextCursor.Document)
        fmt=QTextCharFormat();fmt.setForeground(QColor(PENDING_COLOR));cursor.mergeCharFormat(fmt)
        cursor=QTextCursor(self.editor.document());cursor.setPosition(0);cursor.setPosition(min(self.sent,len(self.last_text)),QTextCursor.KeepAnchor)
        fmt.setForeground(QColor('black'));cursor.mergeCharFormat(fmt)
        cursor.clearSelection();cursor.setPosition(min(position,len(self.last_text)));self.editor.setTextCursor(cursor)
        self.changing=False
    def changed(self):
        if self.changing:return
        text=self.editor.toPlainText().upper()
        # No unsupported characters are silently displayed as successfully transmitted.
        from ..rtty_codec import LTRS_ENCODE, FIGS_ENCODE
        text=''.join(ch for ch in text if ch in LTRS_ENCODE or ch in FIGS_ENCODE)
        if text.count('\n')>1:text='\n'.join(text.split('\n')[:2])
        if self.session and self.main.active_tx_id is not None and not self.session.update(text):text=self.last_text
        elif not self.session:
            if text!=self.last_text:self.sent=0
        cursor=self.editor.textCursor().position()
        if text!=self.editor.toPlainText():
            self.changing=True;self.editor.setPlainText(text)
            c=self.editor.textCursor();c.setPosition(min(cursor,len(text)));self.editor.setTextCursor(c);self.changing=False
        import time
        common=0
        while common<min(len(text),len(self.last_text)) and text[common]==self.last_text[common]:common+=1
        self.input_times=self.input_times[:common]+[time.monotonic()]*(len(text)-common)
        self.last_text=text;self.paint()
        self.suppressed=False
        if self.auto.isChecked() and not self.session and text and not self.timer.isActive():self.timer.start()
    def mode_changed(self, enabled):
        self.main.store.data['ui']['direct_auto_tx']=enabled
        self.timer.stop()
        if self.session:self.session.hold=enabled
    def auto_start(self):
        if self.isVisible() and self.auto.isChecked() and not self.session and not self.suppressed and self.last_text:
            self.start(replay=False)
    def start(self,replay=False):
        self.timer.stop();self.suppressed=False
        if self.session:
            if replay:
                self.session.replay();self.sent=0;self.paint()
            return
        if self.main.active_tx_id is not None:return
        text=self.last_text
        if not text and not self.auto.isChecked():return
        # Editing after STOP allows the whole text to be edited. F11 resumes only the unsent tail.
        self.session=LiveText(text,delay=0 if replay or not self.auto.isChecked() else .5,hold=self.auto.isChecked())
        if not replay:
            self.session.position=self.sent
            self.session.times=self.input_times.copy()
        else:self.sent=0;self.paint()
        if not self.main._send_text(text, live_session=self.session):self.session=None;return
        self.tx_button.setText(tr('ui.0d16c18e1b0c0af1'));self.status.setText(tr('ui.19ae7f1dfcb6e2d3'))
    def stop(self):
        self.timer.stop();self.suppressed=True;self.main._stop_tx()
    def toggle(self):
        if self.session:self.stop()
        else:self.start()
    def replay(self):self.start(replay=True)
    def button(self):
        if self.session:self.stop()
        else:self.replay()
    def progress(self,epoch,count,ch):
        if not self.session or epoch!=self.session.epoch:return
        self.sent=count;self.paint()
    def finished(self):
        self.session=None;self.suppressed=True;self.timer.stop();self.editor.setReadOnly(False)
        self.tx_button.setText(tr('ui.c79fb302350cd0ea'));self.status.setText(tr('ui.2f3ee0fc058199a7'))
    def clear(self):
        self.stop();self.changing=True;self.editor.clear();self.changing=False
        self.last_text='';self.sent=0;self.input_times=[]
        if self.session:self.editor.setReadOnly(True)
        if self.session:
            # Cancellation discards every queued character; late progress cannot recolor new input.
            with self.session.lock:self.session.epoch+=1
    def closeEvent(self,event):
        self.stop();self.main.store.data['ui']['direct_window']=save_window(self)
        self.main.activateWindow();event.accept()
