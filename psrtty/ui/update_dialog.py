from ..i18n import tr
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox
from .. import __version__


class UpdateDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('PSRTTYのバージョンアップ'))
        self.resize(600, 420)
        layout = QVBoxLayout(self)
        text = QLabel(
            tr('現在のバージョン：PSRTTY Ver{version}\n\n新しいバージョンへの更新、内容が異なる同じバージョンの修復・再インストールができます。\n\nWindows配布用のPSRTTY_版.zipを、展開せずそのまま指定してください。ソース用・PATCH ZIPは使用できません。\n\n更新前に自動でバックアップを作成します。ログ・設定・マクロなどの利用者データは保持されます。\n\n更新成功後はPSRTTYを自動で再起動します。更新に失敗した場合は復元結果とバックアップの場所を表示します。\n\n同じ内容のZIP、古いバージョンへの更新はできません。').format(version=__version__))
        text.setWordWrap(True); layout.addWidget(text)
        warning=QLabel(tr('バージョンが大きく離れていると画面内で更新できない場合があります。\n'
                       'その場合はPSRTTYを閉じ、新しいバイナリー配布ZIPを開いて、'
                       '中身を既存のPSRTTYフォルダーへ上書きしてください。'))
        warning.setWordWrap(True)
        warning.setStyleSheet('color:#bb5a00; font-weight:bold; background:#fff0d8; '
                              'border:1px solid #e6a45b; padding:8px;')
        layout.addWidget(warning)
        buttons = QDialogButtonBox()
        buttons.addButton(tr('更新ZIPを選択…'), QDialogButtonBox.AcceptRole)
        buttons.addButton(tr('キャンセル'), QDialogButtonBox.RejectRole)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
