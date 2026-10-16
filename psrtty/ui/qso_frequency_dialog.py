"""Ask for a missing QSO frequency before any log or external write."""
from decimal import Decimal,InvalidOperation
import re
import unicodedata

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QDialogButtonBox,QHBoxLayout,QLabel,QLineEdit,QVBoxLayout
from ..i18n import tr


def parse_mhz(text):
    value=unicodedata.normalize('NFKC',str(text)).strip()
    if len(value)>32 or not re.fullmatch(r'[0-9]+(?:[.,][0-9]+)?',value):
        raise ValueError(tr('v124.invalid'))
    try:
        hz=Decimal(value.replace(',','.'))*1000000
        # Match the range and whole-Hz precision accepted by the QSO log editor.
        if not hz.is_finite() or hz!=hz.to_integral_value() or not 0<hz<15000000000:
            raise ValueError(tr('v124.invalid'))
        return int(hz)
    except InvalidOperation as exc:
        raise ValueError(tr('v124.invalid')) from exc


class QSOFrequencyDialog(QDialog):
    def __init__(self,call,parent=None):
        super().__init__(parent)
        self.frequency_hz=None
        self.setWindowTitle(tr('v124.title'));self.resize(540,230)
        root=QVBoxLayout(self)
        self.explanation=QLabel(tr('v124.explanation'));self.explanation.setWordWrap(True)
        root.addWidget(self.explanation)
        self.call_label=QLabel(tr('v124.call').format(call=call));self.call_label.setTextFormat(Qt.PlainText)
        self.call_label.setTextInteractionFlags(Qt.TextSelectableByMouse);root.addWidget(self.call_label)
        row=QHBoxLayout();label=QLabel(tr('v124.frequency'));row.addWidget(label)
        self.frequency=QLineEdit();self.frequency.setMaxLength(32);label.setBuddy(self.frequency)
        self.frequency.setAccessibleName(tr('v124.frequency')+' MHz');row.addWidget(self.frequency)
        row.addWidget(QLabel('MHz'));root.addLayout(row)
        self.examples=QLabel(tr('v124.examples'));self.examples.setWordWrap(True);root.addWidget(self.examples)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color:#b3261e;');root.addWidget(self.error)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText(tr('v124.register'))
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        self.buttons.accepted.connect(self.accept);self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons);self.frequency.setFocus()

    def accept(self):
        try:frequency=parse_mhz(self.frequency.text())
        except ValueError as exc:
            self.error.setText(str(exc));self.frequency.setFocus();return
        self.frequency_hz=frequency
        super().accept()


def request_qso_frequency(call,parent=None):
    dialog=QSOFrequencyDialog(call,parent)
    try:return dialog.frequency_hz if dialog.exec()==QDialog.Accepted else None
    finally:dialog.deleteLater()
