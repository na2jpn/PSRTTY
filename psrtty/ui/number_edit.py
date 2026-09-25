"""Plain number field: commit defaults invalid text and clamps integers."""
import re
import unicodedata
from PySide6.QtWidgets import QLineEdit


class NumberEdit(QLineEdit):
    def __init__(self, default, value, parent=None):
        super().__init__(parent)
        self.default = default
        self.setMaximumWidth(46)
        self.setMaxLength(64)
        self.setText(str(value))
        self.normalize()
        self.editingFinished.connect(self.normalize)

    def value(self):
        text = unicodedata.normalize('NFKC', self.text()).strip()
        if not re.fullmatch(r'[+-]?[0-9]+', text):
            return self.default
        return max(1, min(99, int(text)))

    def normalize(self):
        self.setText(str(self.value()))

    def setValue(self, value):
        self.setText(str(value)); self.normalize()

    def maximum(self):
        return 99
