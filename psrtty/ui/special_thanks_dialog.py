from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QScrollArea, QWidget, QApplication
from ..i18n import tr

CALLSIGNS = ('JG1RFE','JH1DUK','JJ1JPE','JN1ATL','JG2AJK','JQ7FIU','7K2COL','7M2FTR')

class SpecialThanksDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('スペシャルサンクス'))
        area = QApplication.primaryScreen().availableGeometry()
        self.resize(min(600, area.width()), min(600, area.height()))
        layout=QVBoxLayout(self)
        title=QLabel(tr('スペシャルサンクス'))
        font=title.font();font.setPointSize(16);font.setBold(True);title.setFont(font)
        layout.addWidget(title)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        content = QWidget(); body = QVBoxLayout(content)
        self.scroll.setWidget(content); layout.addWidget(self.scroll, 1)
        self.message=QLabel(tr('ご意見やアイディアをだされた方、試験や開発に協力いただいた方々へ感謝いたします。'))
        self.message.setWordWrap(True);body.addWidget(self.message)
        self.names=QLabel('JS1YCP '+tr('秋葉原無線部')+'\nJA1YML '+tr('草加アマチュア無線クラブ')+'\n\n'+'\n'.join(CALLSIGNS))
        self.names.setTextFormat(Qt.PlainText);self.names.setTextInteractionFlags(Qt.TextSelectableByMouse)
        body.addWidget(self.names)
        body.addSpacing(20)
        self.closing_message = QLabel(tr('MMTTY、Turbo HAMLOG、zLogをはじめ、多くの関連するソフトウェアを開発された先駆者の方々に感謝します。'))
        self.closing_message.setWordWrap(True); body.addWidget(self.closing_message); body.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr('閉じる'))
        buttons.rejected.connect(self.reject);layout.addWidget(buttons)
