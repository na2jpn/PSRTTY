from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QScrollArea, QWidget, QApplication
from ..i18n import tr

CALLSIGNS = ('JG1QZW','JG1RFE','JH1DUK','JH1PGF','JJ1JPE','JN1ATL','JG2AJK','JQ7FIU','7K2COL','7M2FTR')

class SpecialThanksDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('ui.13b044e575dd7a62'))
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(600, area.width()), min(600, area.height()))
        layout=QVBoxLayout(self)
        title=QLabel(tr('ui.5dad921034a95bdf'))
        font=title.font();font.setPointSize(16);font.setBold(True);title.setFont(font)
        layout.addWidget(title)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        content = QWidget(); body = QVBoxLayout(content)
        self.scroll.setWidget(content); layout.addWidget(self.scroll, 1)
        self.message=QLabel(tr('ui.bee799075939298a'))
        self.message.setWordWrap(True);body.addWidget(self.message)
        self.names=QLabel('JS1YCP '+tr('ui.775585f376581460')+'\nJA1YML '+tr('ui.1cc3ad59bd9a4655')+'\n\n'+'\n'.join(CALLSIGNS))
        self.names.setTextFormat(Qt.PlainText);self.names.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.names)
        body.addSpacing(20)
        self.closing_message = QLabel(tr('ui.5ccf11412b0b1399'))
        self.closing_message.setWordWrap(True); body.addWidget(self.closing_message)
        body.addSpacing(24)
        self.media_title = QLabel(tr('ui.dd1c2b09eccb2c53'))
        self.media_title.setFont(font); body.addWidget(self.media_title)
        self.media_names = QLabel('hamlife.jp'); body.addWidget(self.media_names)
        body.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr('ui.f6c244f98893cd95'))
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)
