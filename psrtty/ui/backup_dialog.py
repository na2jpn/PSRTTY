from ..i18n import tr
from copy import deepcopy
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QSpinBox, QLabel, QPushButton, QDialogButtonBox, QMessageBox


class BackupDialog(QDialog):
    def __init__(self, store, backup_now, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr('ui.3d3ce645af03466b'))
        self.resize(490, 220)
        values = store.data.get('backup', {})
        root = QVBoxLayout(self)
        self.on_exit = QCheckBox(tr('ui.306d83fe2d048600'))
        self.on_exit.setChecked(values.get('on_exit', True)); root.addWidget(self.on_exit)
        row = QHBoxLayout()
        self.every = QCheckBox(tr('ui.9bce269cb36c4072'))
        self.every.setChecked(values.get('every_enabled', False)); row.addWidget(self.every)
        self.count = QSpinBox(); self.count.setRange(1, 1000000)
        self.count.setValue(values.get('every_count', 30)); row.addWidget(self.count)
        row.addWidget(QLabel(tr('ui.bd98f692e864daad'))); row.addStretch()
        self.count.setEnabled(self.every.isChecked())
        self.every.toggled.connect(self.count.setEnabled); root.addLayout(row)
        note = QLabel(tr('ui.7e9a0fc83c7c277b'))
        note.setWordWrap(True); root.addWidget(note)
        now = QPushButton(tr('ui.b4600d946d7bf45d')); now.clicked.connect(lambda: backup_now()); root.addWidget(now)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('ui.a3030bf8f16dc63c'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        buttons.accepted.connect(self._save); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _save(self):
        previous = deepcopy(self.store.data.get('backup', {}))
        values = dict(previous)
        values.update(on_exit=self.on_exit.isChecked(), every_enabled=self.every.isChecked(), every_count=self.count.value())
        self.store.data['backup'] = values
        try:
            self.store.save()
        except Exception as exc:
            self.store.data['backup'] = previous
            QMessageBox.warning(self, tr('ui.3d3ce645af03466b'), tr('ui.9cee958adf0b643f').format(exc))
            return
        self.accept()
