from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from ..i18n import tr

CALLSIGNS = ('JG1RFE','JH1DUK','JJ1JPE','JN1ATL','JG2AJK','7K2COL','7M2FTR')

class SpecialThanksDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('スペシャルサンクス'))
        self.resize(540,440)
        layout=QVBoxLayout(self)
        title=QLabel(tr('スペシャルサンクス'))
        font=title.font();font.setPointSize(16);font.setBold(True);title.setFont(font)
        layout.addWidget(title)
        self.message=QLabel(tr('ご意見やアイディアをだされた方、試験や開発に協力いただいた方々へ感謝いたします。'))
        self.message.setWordWrap(True);layout.addWidget(self.message)
        self.names=QLabel('JS1YCP '+tr('秋葉原無線部')+'\nJA1YML '+tr('草加アマチュア無線クラブ')+'\n\n'+'\n'.join(CALLSIGNS))
        self.names.setTextFormat(Qt.PlainText);self.names.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.names);layout.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr('閉じる'))
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)
