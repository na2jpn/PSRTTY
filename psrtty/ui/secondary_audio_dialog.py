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
        self.setWindowTitle(tr('ui.acd8e57f9bb73955'))
        self.resize(520, 260)
        root = QVBoxLayout(self)
        self.enabled = QCheckBox(tr('ui.64b37725c87dd71a'))
        self.enabled.setChecked(values['enabled']); root.addWidget(self.enabled)
        note = QLabel(tr('ui.6b1a14b12d2cddef'))
        note.setWordWrap(True); root.addWidget(note)
        excluded_note = QLabel(tr('ui.a471ca224b532e4b'))
        excluded_note.setWordWrap(True); root.addWidget(excluded_note)
        form = QFormLayout(); root.addLayout(form)
        self.device = QComboBox(); self.device.addItem(tr('ui.6213305916949e4c'), 'UNSET')
        try:
            for choice, label in choices:
                self.device.addItem(label, choice)
        except Exception as exc:
            note.setText(note.text() + '\n' + tr(str(exc)))
        index = self.device.findData(values['device'])
        if index < 0:
            selected = values['device']
            label = selected.get('name','') if isinstance(selected,dict) else str(selected)
            self.device.addItem(label + tr('ui.1184daf535ccfd3e'), selected)
            index = self.device.count()-1
        self.device.setCurrentIndex(index)
        form.addRow(tr('ui.83d4a06ddba451af'), self.device)
        self.gain = QSlider(Qt.Horizontal); self.gain.setRange(0, 200)
        self.gain.setValue(round(values['gain'] * 100))
        self.value = QLabel(); row = QHBoxLayout()
        row.addWidget(self.gain, 1); row.addWidget(self.value)
        form.addRow(tr('ui.8bf8b9780d342816'), row)
        self.gain.valueChanged.connect(self.update_gain); self.update_gain(self.gain.value())
        warning = QLabel(tr('ui.89b7db98eb938d41'))
        warning.setWordWrap(True); root.addWidget(warning)
        self.status = QLabel(); self.status.setWordWrap(True); root.addWidget(self.status)
        buttons = QHBoxLayout(); buttons.addStretch()
        self.save_button = QPushButton(tr('ui.a3030bf8f16dc63c')); self.close_button = QPushButton(tr('ui.f6c244f98893cd95'))
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
            self.status.setText(tr('ui.29441ac1db710a7f')); return
        try:
            self.save_settings(values)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.acd8e57f9bb73955'), tr(str(exc))); return
        self.status.setText(tr('ui.f9b3849f177f5d1e'))
