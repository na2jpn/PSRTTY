from __future__ import annotations
from ..i18n import tr

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHeaderView, QLabel, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QComboBox, QPushButton, QHBoxLayout, QLineEdit, QCheckBox,
)

from ..macros import TEMPLATES, TEMPLATE_HELP, NORMAL_TEMPLATE_NAME, TEMPLATE_NAME, CQWW_TEMPLATE_NAME

class MacroDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.macros = deepcopy(store.macros)
        self.setWindowTitle(tr('ui.e48ef08ab23993c9'))
        self.resize(820, 590)
        root = QVBoxLayout(self)
        instruction = QLabel(tr('ui.a5e498c4b446e65b'))
        instruction.setWordWrap(True)
        root.addWidget(instruction)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr('ui.ee5b8eef33fb2c2d')))
        self.template = QComboBox(); row.addWidget(self.template, 1)
        for key in TEMPLATES:
            self.template.addItem(tr(key), key)
        self.applied_template = store.data.get("macro_template", NORMAL_TEMPLATE_NAME)
        if self.applied_template in TEMPLATES:
            self.template.setCurrentIndex(self.template.findData(self.applied_template))
        apply = QPushButton(tr('ui.edf99ff4e1cb3cdc')); apply.clicked.connect(self._apply_template); row.addWidget(apply)
        root.addLayout(row)
        note = QLabel(tr('ui.d55b709679b093a7')); note.setWordWrap(True)
        root.addWidget(note)
        root.addWidget(QLabel(tr('ui.2aedd9acecd6817d')))
        self.table = QTableWidget(9, 4)
        self.table.setColumnHidden(3, True)  # Preserve legacy metadata without presenting an obsolete control.
        self.table.setHorizontalHeaderLabels([tr('ui.1771ccbd34bfe4b9'), tr('ui.d44e9b3d3b31d37b'), tr('ui.54f1b4626a1b7e56'), tr('ui.77aef86700ba00ae')])
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
            flag.setToolTip(tr('ui.fe56233372f95b70'))
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
        sent_row = QHBoxLayout()
        sent_row.addStretch(1)
        sent_row.addWidget(QLabel("SENT"))
        self.sent = QLineEdit(str(store.data['qso']['sent']))
        self.sent.setFixedWidth(140)
        self.sent_fixed = QCheckBox(tr('ui.d4b3f49cd2e4254f'))
        self.sent_fixed.setChecked(store.data['qso']['sent_fixed'])
        self.sent_fixed.setToolTip(tr('ui.31139339921c3334'))
        sent_row.addWidget(self.sent)
        sent_row.addWidget(self.sent_fixed)
        root.addLayout(sent_row)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('ui.a3030bf8f16dc63c'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        buttons.accepted.connect(self._save); buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def showEvent(self, event):
        super().showEvent(event)
        self.table.setFixedHeight(self.table.horizontalHeader().height() + self.table.verticalHeader().length() + 2 * self.table.frameWidth() + 4)

    def _update_template_help(self):
        self.template_help.setText(tr(TEMPLATE_HELP.get(self.template.currentData(), "")))

    def _apply_template(self):
        self.applied_template = self.template.currentData()
        self.macros = TEMPLATES[self.template.currentData()]()
        self.sent.setText({CQWW_TEMPLATE_NAME: "25", TEMPLATE_NAME: "01",
                           NORMAL_TEMPLATE_NAME: ""}.get(self.applied_template, ""))
        self.sent_fixed.setChecked(True)
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
        self.store.data['qso'].update(sent=self.sent.text(), sent_fixed=self.sent_fixed.isChecked())
        self.store.macros = self.macros
        self.store.save()
        self.accept()
