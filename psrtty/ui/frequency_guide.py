"""Offline, modeless RTTY reference with language-independent region tabs."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QTextBrowser, QPushButton
from .. import i18n
from ..frequency_guide import REGIONS, page_html
from .guide import STYLE


class FrequencyGuide(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle(i18n.tr('freq.title'))
        self.resize(1000, 720)
        self.setMinimumSize(480, 340)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        style = STYLE
        if i18n.LANGUAGE == 'th':
            style = style.replace('"Yu Gothic UI", sans-serif', '"Leelawadee UI", "Noto Sans Thai", "Tahoma", sans-serif')
        for region in (None,) + REGIONS:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            font = QFont(); font.setPointSize(11); browser.setFont(font)
            browser.document().setDefaultStyleSheet(style)
            browser.setHtml(page_html(region))
            self.tabs.addTab(browser, i18n.tr('freq.' + (region or 'common')))
        self.close_button = QPushButton(i18n.tr('ui.f6c244f98893cd95'))
        self.close_button.clicked.connect(self.hide)
        layout.addWidget(self.close_button)
