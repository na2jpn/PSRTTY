from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser, QPushButton
from ..i18n import tr
from .window_state import place_tool_window,save_window


class ShortcutGuide(QWidget):
    def __init__(self,main):
        super().__init__(None,Qt.Window);self.main=main
        from .window_state import independent_tool_window
        independent_tool_window(self, main)
        self.setWindowTitle(tr('ui.3e9f8e3d03440dc5'));self.setWindowIcon(main.windowIcon())
        lay=QVBoxLayout(self);browser=QTextBrowser();lay.addWidget(browser)
        rows=[('F1–F9',tr('ui.47428f20354d25d3')),
              ('Esc',tr('ui.2b7f539f6c930734')),
              ('Ctrl+F12 / Shift+F12',tr('ui.770fc50811d4311f')),
              ('F11 / F12',tr('ui.5c02779801d1b139')),
              ('F11',tr('ui.5bf1751695a724bc')),
              ('F12',tr('ui.6806a55a17314710')),
              ('Alt+F4',tr('ui.7402e82ecd45f5cb')),
              ('Ctrl+C / Ctrl+V / Ctrl+X / Ctrl+A',tr('ui.24cbbceb3a52dfdf')),
              ('Tab / Shift+Tab',tr('ui.a96b442b114d71c2'))]
        import html
        browser.setHtml('<h2>'+html.escape(tr('ui.93cc491afe522c13'))+'</h2><p>'+html.escape(tr('ui.248093496d227c50'))+'</p><table border="1" cellpadding="6">'+''.join('<tr><td>'+html.escape(k)+'</td><td>'+html.escape(v)+'</td></tr>' for k,v in rows)+'</table>')
        button=QPushButton(tr('ui.f6c244f98893cd95'));button.clicked.connect(self.close);lay.addWidget(button)
        place_tool_window(self,main,(700,480),(340,240),main.store.data['ui'].get('shortcut_window'))
    def closeEvent(self,event):self.main.store.data['ui']['shortcut_window']=save_window(self);event.accept()
