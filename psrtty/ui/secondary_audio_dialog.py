from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QCheckBox, QComboBox,
    QFormLayout, QSlider, QLabel, QHBoxLayout, QPushButton, QMessageBox)
from ..audio_engine import AudioEngine
from ..secondary_audio import normalize_settings, secondary_choices, same_device
from ..i18n import tr


class SecondaryAudioDialog(QDialog):
    def __init__(self, settings, save, parent=None, primary_device=None):
        super().__init__(parent)
        self.save_settings = save
        values = normalize_settings(settings)
        choices, excluded = secondary_choices(primary_device) if primary_device is not None else (AudioEngine.devices('output'), [])
        if any(same_device(values['device'], item) for item in excluded):
            values['device'] = 'UNSET'
        self.setWindowTitle(tr('第二AudioOUTの設定'))
        self.resize(520, 260)
        root = QVBoxLayout(self)
        self.enabled = QCheckBox(tr('第二AudioOUTを有効にする'))
        self.enabled.setChecked(values['enabled']); root.addWidget(self.enabled)
        note = QLabel(tr('主AudioOUTと同じ送信音を、確認用などの別の出力先へ出します。'))
        note.setWordWrap(True); root.addWidget(note)
        excluded_note = QLabel(tr('主AudioOUTで使用する出力先は、一覧に表示されません。'))
        excluded_note.setWordWrap(True); root.addWidget(excluded_note)
        form = QFormLayout(); root.addLayout(form)
        self.device = QComboBox(); self.device.addItem(tr('未設定'), 'UNSET')
        try:
            for choice, label in choices:
                self.device.addItem(label, choice)
        except Exception as exc:
            note.setText(note.text() + '\n' + str(exc))
        index = self.device.findData(values['device'])
        if index < 0:
            selected = values['device']
            label = selected.get('name','') if isinstance(selected,dict) else str(selected)
            self.device.addItem(label + tr('（未接続／無効）'), selected)
            index = self.device.count()-1
        self.device.setCurrentIndex(index)
        form.addRow(tr('出力デバイス'), self.device)
        self.gain = QSlider(Qt.Horizontal); self.gain.setRange(0, 200)
        self.gain.setValue(round(values['gain'] * 100))
        self.value = QLabel(); row = QHBoxLayout()
        row.addWidget(self.gain, 1); row.addWidget(self.value)
        form.addRow(tr('音量'), row)
        self.gain.valueChanged.connect(self.update_gain); self.update_gain(self.gain.value())
        warning = QLabel(tr('100％を超えると音が歪む場合があります。'))
        warning.setWordWrap(True); root.addWidget(warning)
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.save_button = QPushButton(tr('保存')); self.close_button = QPushButton(tr('閉じる'))
        buttons.addWidget(self.save_button); buttons.addWidget(self.close_button); root.addLayout(buttons)
        self.save_button.clicked.connect(self.save); self.close_button.clicked.connect(self.reject)
        self.enabled.toggled.connect(self.update_enabled); self.update_enabled(self.enabled.isChecked())

    def update_enabled(self, enabled):
        self.device.setEnabled(enabled); self.gain.setEnabled(enabled)

    def update_gain(self, value):
        self.value.setText(f'{value}%')
        color = '#d32f2f' if value > 100 else '#d88724'
        self.gain.setStyleSheet(
            'QSlider::groove:horizontal { height: 6px; background: #c7c7c7; border-radius: 3px; }'
            'QSlider::sub-page:horizontal { background: '+color+'; border-radius: 3px; }'
            'QSlider::handle:horizontal { background: #fffaf2; border: 1px solid '+color+'; '
            'width: 14px; margin: -5px 0; border-radius: 6px; }')
        self.value.setStyleSheet('color: '+color+';')

    def save(self):
        values = {'enabled': self.enabled.isChecked(), 'device': deepcopy(self.device.currentData()),
                  'gain': self.gain.value()/100}
        if values['enabled'] and values['device'] == 'UNSET':
            self.status.setText(tr('第二AudioOUTの出力先を選択してください。')); return
        try:
            self.save_settings(values)
        except Exception as exc:
            QMessageBox.warning(self, tr('第二AudioOUTの設定'), str(exc)); return
        self.status.setText(tr('第二AudioOUTの設定を保存しました。'))
