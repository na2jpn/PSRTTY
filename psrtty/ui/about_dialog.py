from __future__ import annotations
from ..i18n import tr
from .. import i18n

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame, QWidget, QPushButton

from .. import __version__
from ..paths import resource_path
from ..paths import app_root


def hamlib_about():
    version=app_root()/'lib/hamlib/VERSION.txt'
    if not version.is_file():return tr('ui.2d449b2b5ce5c372')
    try:
        value=version.read_text(encoding='ascii').strip()
        if not value or len(value)>30:return tr('ui.10166ff42a6f44b6')
    except OSError:return tr('ui.10166ff42a6f44b6')
    return tr('ui.c2f9ceee5a00ecff').format(value=value)


ABOUT_TEXT = i18n.language_text('about.body','ja')
ABOUT_TEXT_EN = i18n.language_text('about.body','en')

def about_html():
    return tr('about.body').replace('PSRTTY 1.10','PSRTTY '+__version__)+'<p>'+hamlib_about()+'</p>'


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.56abe64e827e4416'))
        self.resize(650, 650)
        root = QVBoxLayout(self)
        icon = QLabel(); icon.setAlignment(Qt.AlignCenter)
        from ..app_identity import application_icon
        pix = application_icon().pixmap(96, 96)
        if not pix.isNull(): icon.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        root.addWidget(icon)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); lay = QVBoxLayout(body)
        text = QLabel(about_html()); text.setWordWrap(True); text.setTextFormat(Qt.RichText); text.setOpenExternalLinks(True)
        lay.addWidget(text)
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)
        row = QHBoxLayout()
        logo = QLabel(); logo.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        anniversary = QPixmap(str(resource_path('assets/amateur_radio_100.png')))
        if not anniversary.isNull():
            logo.setPixmap(anniversary.scaled(200, 105, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        row.addWidget(logo, 0, Qt.AlignTop)
        self.support_text = QLabel(tr('ui.d2f15802aeb60d3e'))
        self.support_text.setWordWrap(True)
        row.addWidget(self.support_text, 1, Qt.AlignTop); lay.addLayout(row); lay.addStretch(1)
        scroll.setWidget(body); root.addWidget(scroll, 1)
        self.thanks_button=QPushButton(tr('ui.13b044e575dd7a62'))
        self.thanks_button.clicked.connect(self._show_thanks)
        buttons=QHBoxLayout()
        buttons.addWidget(self.thanks_button);buttons.addStretch(1)
        self.close_button=QPushButton(tr('ui.f6c244f98893cd95'))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button);root.addLayout(buttons)
        self.thanks_window=None

    def _show_thanks(self):
        from .special_thanks_dialog import SpecialThanksDialog
        if self.thanks_window is None:
            self.thanks_window=SpecialThanksDialog(self)
        self.thanks_window.show();self.thanks_window.raise_();self.thanks_window.activateWindow()

    def done(self, result):
        if self.thanks_window:self.thanks_window.close()
        super().done(result)
