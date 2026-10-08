from ..i18n import tr
"""Scrollable release history shown from the Help menu."""

from html import escape

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from ..update_history import HISTORY_TEXT
from ..update_history_en import HISTORY_TEXT_EN
from .. import i18n


def history_html() -> str:
    blocks = []
    for section in tr('history.body').split("\n\n"):
        lines = section.splitlines()
        if not lines:
            continue
        heading, *changes = lines
        items = "".join(f"<li>{escape(line.removeprefix('・'))}</li>" for line in changes)
        blocks.append(f"<h3>{escape(heading)}</h3><ul>{items}</ul>")
    return (
        "<html><head><style>"
        "body { color: #4a2b12; font-size: 10.5pt; }"
        "h3 { color: #a4510b; margin-top: 17px; margin-bottom: 5px; }"
        "ul { margin-top: 3px; margin-bottom: 11px; }"
        "li { margin-bottom: 4px; }"
        "</style></head><body><h2>" + escape(tr('ui.3c557b21e44807da')) + "</h2>"
        + "".join(blocks) + "</body></html>"
    )


class HistoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.3c557b21e44807da'))
        self.resize(760, 650)
        layout = QVBoxLayout(self)
        self.history_view = QTextBrowser()
        self.history_view.setOpenExternalLinks(False)
        self.history_view.setHtml(history_html())
        layout.addWidget(self.history_view)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr('ui.f6c244f98893cd95'))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
