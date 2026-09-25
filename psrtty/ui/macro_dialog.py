from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QComboBox, QPushButton, QHBoxLayout,
)

from ..macros import TEMPLATES, TEMPLATE_HELP, NORMAL_TEMPLATE_NAME

class MacroDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.macros = deepcopy(store.macros)
        self.setWindowTitle("マクロ編集")
        self.resize(820, 590)
        root = QVBoxLayout(self)
        instruction = QLabel("テンプレートを選択し、［反映］を押してから［Save］してください。")
        instruction.setWordWrap(True)
        root.addWidget(instruction)
        row = QHBoxLayout()
        row.addWidget(QLabel("テンプレート"))
        self.template = QComboBox(); self.template.addItems(list(TEMPLATES)); row.addWidget(self.template, 1)
        self.applied_template = store.data.get("macro_template", NORMAL_TEMPLATE_NAME)
        if self.applied_template in TEMPLATES:
            self.template.setCurrentText(self.applied_template)
        apply = QPushButton("反映"); apply.clicked.connect(self._apply_template); row.addWidget(apply)
        root.addLayout(row)
        note = QLabel("使用可能: {MYCALL} {HISCALL} {RSTS} {RSTR} {SENT} {RCVD}\n{MYQTH} {MYJCCJCG} {MYTXT}"); note.setWordWrap(True)
        root.addWidget(note)
        root.addWidget(QLabel("自動ログ: 送信文に TU 73 / TU73 がある場合、正常送信終了後に追加します。"))
        self.table = QTableWidget(9, 4)
        self.table.setColumnHidden(3, True)  # Preserve legacy metadata without presenting an obsolete control.
        self.table.setHorizontalHeaderLabels(["キー", "名称", "送信内容", "QSO完了"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for r, m in enumerate(self.macros):
            k = QTableWidgetItem(m["key"]); k.setFlags(k.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, 0, k)
            self.table.setItem(r, 1, QTableWidgetItem(m["name"]))
            self.table.setItem(r, 2, QTableWidgetItem(m["text"]))
            flag = QTableWidgetItem()
            flag.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            flag.setCheckState(Qt.Checked if m.get("completes_qso") is True else Qt.Unchecked)
            flag.setToolTip("正常送信完了時に日時を設定。自動ログONなら追加します。")
            self.table.setItem(r, 3, flag)
        root.addWidget(self.table)
        self.template_help = QLabel()
        self.template_help.setWordWrap(True)
        self.template_help.setTextFormat(Qt.PlainText)
        self.template_help.setStyleSheet("color: #1459a0;")
        self.template_help.setMinimumHeight(self.template_help.fontMetrics().lineSpacing() * 4 + 8)
        root.addWidget(self.template_help)
        self.template.currentTextChanged.connect(self._update_template_help)
        self._update_template_help()
        root.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        self.table.setFixedHeight(self.table.horizontalHeader().height() + self.table.verticalHeader().length() + 2 * self.table.frameWidth() + 4)

    def _update_template_help(self):
        self.template_help.setText(TEMPLATE_HELP.get(self.template.currentText(), ""))

    def _apply_template(self):
        self.applied_template = self.template.currentText()
        self.macros = TEMPLATES[self.template.currentText()]()
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for r, m in enumerate(self.macros):
            self.table.item(r, 1).setText(m["name"])
            self.table.item(r, 2).setText(m["text"])
            self.table.item(r, 3).setCheckState(Qt.Checked if m.get("completes_qso") is True else Qt.Unchecked)

    def _save(self):
        for r in range(9):
            self.macros[r]["name"] = self.table.item(r, 1).text().strip()
            self.macros[r]["text"] = self.table.item(r, 2).text()
            self.macros[r]["completes_qso"] = self.table.item(r, 3).checkState() == Qt.Checked
        self.store.data["macro_template"] = self.applied_template
        self.store.macros = self.macros
        self.store.save()
        self.accept()
