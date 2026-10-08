from ..i18n import tr
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from .. import __version__


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.8dabb1c0eda28080'))
        self.resize(600, 420)
        layout = QVBoxLayout(self)
        text = QLabel(
            tr('ui.22cd6fc2f3303548').format(version=__version__))
        text.setWordWrap(True); layout.addWidget(text)
        warning=QLabel(tr('ui.7234e999159cf677'))
        warning.setWordWrap(True)
        warning.setStyleSheet('color:#bb5a00; font-weight:bold; background:#fff0d8; '
                              'border:1px solid #e6a45b; padding:8px;')
        layout.addWidget(warning)
        buttons = QDialogButtonBox()
        buttons.addButton(tr('ui.6c3977af297eb645'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('ui.bca84ea5c65fee0e'), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
