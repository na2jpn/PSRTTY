from copy import deepcopy
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QFormLayout,QComboBox,QCheckBox,
    QSpinBox,QDoubleSpinBox,QLabel,QDialogButtonBox,QPushButton)
from ..i18n import tr
from ..printer import normalize_settings
from ..civ import CIVController


class PrinterDialog(QDialog):
    settings_saved=Signal()
    def __init__(self, store, apply_settings, parent=None):
        super().__init__(parent)
        self.store=store;self.apply_settings=apply_settings
        self.setWindowTitle(tr('プリンター設定'));self.resize(610,500)
        self.values=normalize_settings(store.data.get('printer'))
        root=QVBoxLayout(self);form=QFormLayout();root.addLayout(form)
        self.port=QComboBox();self.port.setEditable(True)
        self.port.addItem('', '')
        for port,label in CIVController.port_choices():self.port.addItem(label,port)
        selected=self.values['port'];index=self.port.findData(selected)
        if index>=0:self.port.setCurrentIndex(index)
        else:self.port.setEditText(selected)
        form.addRow(tr('プリンターのCOMポート'),self.port)
        self.baud=QComboBox()
        for value in (9600,19200,38400,57600,115200):self.baud.addItem(str(value),value)
        if self.baud.findData(self.values['baud'])<0:self.baud.addItem(str(self.values['baud']),self.values['baud'])
        self.baud.setCurrentIndex(self.baud.findData(self.values['baud']));form.addRow(tr('通信速度'),self.baud)
        self.ignore=QCheckBox(tr('指定文字数以下は印刷しない'));self.ignore.setChecked(self.values['ignore_short'])
        self.threshold=QSpinBox();self.threshold.setRange(0,300);self.threshold.setValue(self.values['min_chars'])
        self.ignore.toggled.connect(self.threshold.setEnabled);self.threshold.setEnabled(self.ignore.isChecked())
        form.addRow(self.ignore,self.threshold)
        self.columns=QSpinBox();self.columns.setRange(16,80);self.columns.setValue(self.values['columns']);form.addRow(tr('1行の文字数'),self.columns)
        self.delay=QDoubleSpinBox();self.delay.setRange(.05,5.0);self.delay.setDecimals(2);self.delay.setSingleStep(.1);self.delay.setValue(self.values['line_delay']);self.delay.setSuffix(tr(' 秒'));form.addRow(tr('行ごとの送出間隔'),self.delay)
        self.ack=QCheckBox(tr('ACKを待つ（対応ファーム用）'));self.ack.setChecked(self.values['ack']);form.addRow(self.ack)
        self.timeout=QDoubleSpinBox();self.timeout.setRange(1,60);self.timeout.setValue(self.values['ack_timeout']);self.timeout.setSuffix(tr(' 秒'));form.addRow(tr('ACK待ち時間'),self.timeout)
        self.ack.toggled.connect(self.timeout.setEnabled);self.timeout.setEnabled(self.ack.isChecked())
        self.limit=QSpinBox();self.limit.setRange(10,2000);self.limit.setValue(self.values['max_jobs']);form.addRow(tr('印刷待ち上限（件）'),self.limit)
        self.timestamps=QCheckBox(tr('時刻を印刷する'));self.timestamps.setChecked(self.values['timestamps']);form.addRow(self.timestamps)
        note=QLabel(tr('メインの受信・送信だけを印刷します。サブデコは含みません。短文判定は本文の前後の空白・改行を除いた文字数です。\nUSBシリアルへASCII＋改行で送ります。送出間隔は実機に合わせて調整してください。ACK使用時は各行へのOK応答が必要です。\n設定変更前に出力をOFFにしてください。OFFと印刷待ち消去は未送出分を取り消しますが、送出済みの印刷は止められない場合があります。'))
        note.setWordWrap(True);root.addWidget(note)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color:#b3261e');root.addWidget(self.error)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('保存'));buttons.button(QDialogButtonBox.Cancel).setText(tr('キャンセル'))
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);root.addWidget(buttons)

    def save(self):
        values=dict(self.values)
        values['target']=normalize_settings(self.store.data.get('printer'))['target']
        # An edited port name must not accidentally use stale itemData.
        index=self.port.currentIndex()
        port=self.port.itemData(index) if index>=0 and self.port.currentText()==self.port.itemText(index) else self.port.currentText()
        values.update(port=str(port or '').strip(),baud=self.baud.currentData(),ignore_short=self.ignore.isChecked(),
            min_chars=self.threshold.value(),columns=self.columns.value(),line_delay=self.delay.value(),ack=self.ack.isChecked(),
            ack_timeout=self.timeout.value(),max_jobs=self.limit.value(),timestamps=self.timestamps.isChecked())
        error=self.apply_settings(values)
        if error:self.error.setText(error);return
        self.settings_saved.emit();self.accept()
