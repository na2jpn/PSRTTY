from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QPushButton
from ..i18n import tr
from .window_state import place_tool_window,save_window


class ShortcutGuide(QWidget):
    def __init__(self,main):
        super().__init__(None,Qt.Window);self.main=main
        from .window_state import independent_tool_window
        independent_tool_window(self, main)
        self.setWindowTitle(tr('ショートカットキーガイド'));self.setWindowIcon(main.windowIcon())
        lay=QVBoxLayout(self);browser=QTextBrowser();lay.addWidget(browser)
        rows=[('F1–F9',tr('メイン画面のマクロ送信。無線機接続または未接続送信許可が必要です。')),
              ('Esc',tr('送信停止。ダイアログやIME変換中は、その画面のキャンセル動作が優先される場合があります。')),
              ('Ctrl+F12 / Shift+F12',tr('ダイレクト画面を開く／閉じる。開くと入力欄へフォーカス。閉じると送信停止。')),
              ('F11 / F12',tr('ダイレクト画面が開いているとき、メインからはフォーカス移動のみ。閉じているときは何もしません。')),
              ('F11',tr('ダイレクト画面がアクティブ：TX／STOP切替。')),
              ('F12',tr('ダイレクト画面がアクティブ：欄の内容を先頭から再送／TX。送信中も再送します。')),
              ('Alt+F4',tr('現在のウィンドウを閉じる。ダイレクト画面を閉じると送信停止。メインでは終了処理を行います。')),
              ('Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+A',tr('入力欄でコピー／貼り付け／切り取り／全選択。送信中の送信済み部分は編集できません。')),
              ('Tab / Shift+Tab',tr('次／前の操作項目へ移動（複数行入力欄ではTabが入力として扱われる場合があります）。'))]
        import html
        browser.setHtml('<h2>'+html.escape(tr('PSRTTYのショートカットキー'))+'</h2><p>'+html.escape(tr('このガイドを表示したままPSRTTYを操作できます。キーはPSRTTY内で有効です。'))+'</p><table border="1" cellpadding="6">'+''.join('<tr><td>'+html.escape(k)+'</td><td>'+html.escape(v)+'</td></tr>' for k,v in rows)+'</table>')
        button=QPushButton(tr('閉じる'));button.clicked.connect(self.close);lay.addWidget(button)
        place_tool_window(self,main,(700,480),(340,240),main.store.data['ui'].get('shortcut_window'))
    def closeEvent(self,event):self.main.store.data['ui']['shortcut_window']=save_window(self);event.accept()
