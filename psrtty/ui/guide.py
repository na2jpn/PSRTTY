from ..i18n import tr
from .. import i18n
from .guide_en import PAGES_EN
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTabWidget, QTextBrowser, QPushButton

STYLE='''body { color:#643600; background:#fffaf2; font-family:"Yu Gothic UI", sans-serif; }
h2 { color:#b85d00; } h3 { color:#a35408; margin-top:20px; }
p,li { line-height:1.65; margin-bottom:12px; }
table { border-collapse:collapse; width:100%; }
th { background:#ffe0b0; } td,th { padding:10px; border:1px solid #e9bf88; }
'''
PAGES=[(i18n.language_text(t,'ja'), i18n.language_text(b,'ja')) for t,b in i18n.GUIDE_KEYS]

class GuideWindow(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent,Qt.Window); self.setWindowTitle(tr('ui.61a34b5ad6c83323'))
        self.resize(900,680); self.setMinimumSize(600,420)
        root=QVBoxLayout(self); self.tabs=QTabWidget(); root.addWidget(self.tabs)
        selected=[(tr(t),tr(b)) for t,b in i18n.GUIDE_KEYS]
        for title,body in selected:
            browser=QTextBrowser(); font=QFont(); font.setPointSize(11); browser.setFont(font)
            style = STYLE
            if i18n.LANGUAGE == "th":
                style = style.replace('"Yu Gothic UI", sans-serif', '"Leelawadee UI", "Noto Sans Thai", "Tahoma", sans-serif')
            browser.document().setDefaultStyleSheet(style)
            browser.setHtml(body); self.tabs.addTab(browser,title)
        close=QPushButton(tr('ui.f6c244f98893cd95')); close.clicked.connect(self.hide); root.addWidget(close)

