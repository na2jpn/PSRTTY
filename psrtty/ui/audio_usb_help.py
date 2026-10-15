"""Shared, localized USB modulation reminder with packaged illustration."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QTextBrowser,QDialogButtonBox
from ..paths import resource_path
from ..i18n import tr
from .. import i18n

def usb_help_html():
    uri=resource_path('assets/audio_usb_examples.png').as_uri()
    return ('<p><b>'+escape(tr('v115fix4.usb_check'))+'</b></p>'
            '<p><img src="'+uri+'" width="520" height="222"></p>'
            '<p><small>'+escape(tr('v115fix4.usb_example_note'))+'</small></p>')

class ProfileAudioNotice(QDialog):
    def __init__(self,parent=None):
        super().__init__(parent);self.setWindowTitle(tr('v115.audio_notice_title'))
        layout=QVBoxLayout(self);self.browser=QTextBrowser()
        if i18n.LANGUAGE == 'th':
            self.browser.document().setDefaultStyleSheet('body { font-family:"Leelawadee UI", "Noto Sans Thai", "Tahoma", sans-serif; }')
        self.browser.setHtml('<p>'+escape(tr('v115.audio_notice'))+'</p>'+usb_help_html()+'<p>'+escape(tr('fsk.notice'))+'</p>')
        layout.addWidget(self.browser)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok);buttons.accepted.connect(self.accept);layout.addWidget(buttons)
        available=self.screen().availableGeometry()
        self.resize(min(600,available.width()-40),min(520,available.height()-60))
