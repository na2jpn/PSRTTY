from copy import deepcopy
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QCheckBox, QSpinBox, QLabel, QPushButton, QDialogButtonBox, QMessageBox


class BackupDialog(QDialog):
    def __init__(self, store, backup_now, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('バックアップ設定')
        self.resize(490, 220)
        values = store.data.get('backup', {})
        root = QVBoxLayout(self)
        self.on_exit = QCheckBox('終了時にログをバックアップする。')
        self.on_exit.setChecked(values.get('on_exit', True)); root.addWidget(self.on_exit)
        row = QHBoxLayout()
        self.every = QCheckBox('QSOログ')
        self.every.setChecked(values.get('every_enabled', False)); row.addWidget(self.every)
        self.count = QSpinBox(); self.count.setRange(1, 1000000)
        self.count.setValue(values.get('every_count', 30)); row.addWidget(self.count)
        row.addWidget(QLabel('件ごとにバックアップする。')); row.addStretch()
        self.count.setEnabled(self.every.isChecked())
        self.every.toggled.connect(self.count.setEnabled); root.addLayout(row)
        note = QLabel('対象：ADIF・生ログTXT／保存先：logdata/backups\n新しく保存したQSOを数え、成功したバックアップから数え直します。')
        note.setWordWrap(True); root.addWidget(note)
        now = QPushButton('いますぐバックアップ'); now.clicked.connect(lambda: backup_now()); root.addWidget(now)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("キャンセル")
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
            QMessageBox.warning(self, 'バックアップ設定', f'設定を保存できませんでした。\n{exc}')
            return
        self.accept()
