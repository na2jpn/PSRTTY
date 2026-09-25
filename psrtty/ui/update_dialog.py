from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from .. import __version__


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('PSRTTYのバージョンアップ')
        self.resize(560, 360)
        layout = QVBoxLayout(self)
        text = QLabel(
            f'現在のバージョン：PSRTTY Ver{__version__}\n\n'
            '新しいバージョンへの更新、内容が異なる同じバージョンの修復・再インストールができます。\n\n'
            'Windows配布用のPSRTTY_版.zipを、展開せずそのまま指定してください。'
            'ソース用・PATCH ZIPは使用できません。\n\n'
            '更新前に自動でバックアップを作成します。ログ・設定・マクロなどの利用者データは保持されます。\n\n'
            '更新成功後はPSRTTYを自動で再起動します。'
            '更新に失敗した場合は復元結果とバックアップの場所を表示します。\n\n'
            '同じ内容のZIP、古いバージョンへの更新はできません。')
        text.setWordWrap(True); layout.addWidget(text)
        buttons = QDialogButtonBox()
        buttons.addButton('更新ZIPを選択…', QDialogButtonBox.AcceptRole)
        buttons.addButton('キャンセル', QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
