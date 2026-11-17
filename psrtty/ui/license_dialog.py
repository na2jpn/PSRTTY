"""Offline license information, shared by Help and About."""
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QPlainTextEdit, QTabWidget, QTextBrowser,
    QVBoxLayout,
)

from ..i18n import tr
from ..paths import app_root, resource_path


DOCUMENTS = (
    ('LICENSE.md', 'about.license'),
    ('LICENSING.md', 'about.policy'),
    ('DISTRIBUTION_TERMS.txt', 'license.third_party'),
)


def license_document(name):
    if name not in {item[0] for item in DOCUMENTS}:
        raise ValueError(name)
    # A frozen EXE has an offline copy even if the external docs are missing.
    for path in (app_root() / 'docs' / name,
                 resource_path('licenses/' + name), app_root() / name):
        try:
            if path.is_file():
                return path.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError):
            continue
    return tr('about.license_missing').format(name=name)


class LicenseDialog(QDialog):
    def __init__(self, parent=None, document=None):
        super().__init__(parent)
        self.setWindowTitle(tr('license.title'))
        self.resize(850, 650)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget(self)
        # Long translations remain accessible on smaller displays.
        self.tabs.setUsesScrollButtons(True)
        self.summary = QTextBrowser(self)
        self.summary.setOpenExternalLinks(True)
        self.summary.setHtml(tr('license.summary'))
        self.tabs.addTab(self.summary, tr('license.overview'))
        self.documents = {}
        for name, title in DOCUMENTS:
            view = QPlainTextEdit(self)
            view.setReadOnly(True)
            view.setPlainText(license_document(name))
            self.documents[name] = view
            index = self.tabs.addTab(view, tr(title))
            self.tabs.setTabToolTip(index, name)
            if document == name:
                self.tabs.setCurrentIndex(index)
        layout.addWidget(self.tabs, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText(tr('ui.f6c244f98893cd95'))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
