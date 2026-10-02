from __future__ import annotations
from ..i18n import tr
from .. import i18n

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QHBoxLayout, QFrame, QWidget, QPushButton

from .. import __version__
from ..paths import resource_path
from ..paths import app_root


def hamlib_about():
    version=app_root()/'lib/hamlib/VERSION.txt'
    if not version.is_file():return tr('Hamlib：同梱ファイルを確認できません。')
    try:
        value=version.read_text(encoding='ascii').strip()
        if not value or len(value)>30:return tr('Hamlib：版情報を確認できません。')
    except OSError:return tr('Hamlib：版情報を確認できません。')
    return tr('Hamlib：Ver {value}（Yaesu・KenwoodのCAT制御）<br>ライセンス：LGPL 2.1以降。詳細：lib/hamlib/THIRD_PARTY_NOTICES.txt').format(value=value)


ABOUT_TEXT = f"""<h2>PSRTTY {__version__}</h2>
<p>Python / PySide6によるRTTYコンテスト向け通信ソフト。</p>
<p>ICOM無線機とのCI-V接続およびUSB Audioを利用し、RTTYの送受信、マクロ送信、QSO記録を行います。</p>
<p>Yaesu・Kenwoodの選択機種はHamlibによるCAT接続を利用します。</p>
<p>通信内容は、生ログとして <b>Pipe Separator形式（PS形式）</b> でTXT保存します。PS形式では、時刻と内容をパイプ記号 <code>|</code> で区切って記録します。</p>
<p>確定したQSOはADIF形式で保存します。</p>
<h3>作者からの案内</h3>
<p>PSRTTYは、H.Tanakaが自身のアマチュア無線RTTY運用およびコンテスト運用のために私的に開発し、利用するソフトウェアです。</p>
<p>作者自身の使いやすさを優先しており、第三者の要望への対応、サポート、不具合修正や継続提供を約束するものではありません。</p>
<p>利用・改良は利用条件の範囲で自由ですが、利用者自身の判断と責任で行ってください。デコード結果、送信内容、交信記録、ADIF、Cabrillo等の提出ファイルについては、利用者自身で内容を確認してください。また、必要なバックアップは利用者が行ってください。</p>
<p><b>PSRTTY</b><br>
Copyright (c) 2026 H.Tanaka (JH1HST)<br>
Originally developed by H.Tanaka (JH1HST)<br>
AKIHABARA-GIKEN</p>
<h3>再配布について</h3>
<p>無改変版の再配布は認めていません。作者の配布元を案内してください。</p>
<p>改良版を再配布する場合は、元となるPSRTTYの版、変更箇所・変更内容、改良版の名称と版、配布責任者を明示してください。</p>
<p>また、対応する改良版のソースコード全体と、ビルドに必要なスクリプト・設定を受領者が取得できるようにしてください。</p>
<p>改良版の配布前に、作者へ改良内容、配布先、配布者本人の氏名と連絡先を通知してください。作者の個別承認を条件とするものではありません。</p>
<p>元作者の表示を保持し、作者の公式版または作者が保証する版であると誤認させないでください。</p>
<p>Python、PySide6/Qt、PyInstaller、NumPy、sounddevice、pyserialその他の第三者ライブラリには、それぞれの利用条件が適用されます。</p>
<h3>第三者ライブラリ</h3><p>""" + hamlib_about() + """</p>
"""


ABOUT_TEXT_EN = f"""<h2>PSRTTY {__version__}</h2>
<p>RTTY contest communication software built with Python / PySide6.</p>
<p>Uses ICOM CI-V and USB Audio for RTTY reception, transmission, macros and QSO logging.</p>
<p>Selected Yaesu and Kenwood models use Hamlib CAT control.</p>
<p>Raw communication transcripts are saved as TXT in <b>Pipe Separator (PS) format</b>, separating time and content with <code>|</code>.</p>
<p>Confirmed QSOs are saved in ADIF format.</p>
<h3>From the author</h3>
<p>PSRTTY is privately developed and used by H.Tanaka for personal amateur-radio RTTY operation and contests.</p>
<p>The author's own ease of use takes priority. Responding to third-party requests, support, bug fixes and continued availability are not promised.</p>
<p>You may use and improve the software within its terms, at your own discretion and responsibility. Verify decoded text, transmitted content, QSO records and submission files such as ADIF and Cabrillo yourself. Users are also responsible for necessary backups.</p>
<p><b>PSRTTY</b><br>Copyright (c) 2026 H.Tanaka (JH1HST)<br>Originally developed by H.Tanaka (JH1HST)<br>AKIHABARA-GIKEN</p>
<h3>Redistribution</h3>
<p>Redistribution of unmodified versions is not permitted. Direct users to the author's distribution source.</p>
<p>When distributing an improved version, identify the original PSRTTY version, what and where you changed, the improved version's name and version, and the person responsible for distribution.</p>
<p>Make the complete corresponding source code and the scripts / settings required to build it available to recipients.</p>
<p>Before distributing an improved version, notify the author of the improvements, distribution location, and the distributor's own name and contact information. Individual approval from the author is not a condition.</p>
<p>Retain original-author attribution. Do not imply that an improved version is an official release or is guaranteed by the original author.</p>
<p>Python, PySide6/Qt, PyInstaller, NumPy, sounddevice, pyserial and other third-party libraries have their own terms.</p>
<h3>Third-party libraries</h3>"""


def about_html():
    if i18n.LANGUAGE == 'en':
        return ABOUT_TEXT_EN + '<p>' + hamlib_about() + '</p>'
    # Replace only the final library paragraph so language is resolved at display time.
    return ABOUT_TEXT.rsplit('<h3>第三者ライブラリ</h3>', 1)[0] + '<h3>第三者ライブラリ</h3><p>' + hamlib_about() + '</p>'


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("PSRTTYについて"))
        self.resize(650, 650)
        root = QVBoxLayout(self)
        icon = QLabel(); icon.setAlignment(Qt.AlignCenter)
        pix = QPixmap(str(resource_path("assets/psrtty.png")))
        if not pix.isNull(): icon.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        root.addWidget(icon)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); lay = QVBoxLayout(body)
        text = QLabel(about_html()); text.setWordWrap(True); text.setTextFormat(Qt.RichText); text.setOpenExternalLinks(True)
        lay.addWidget(text)
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        lay.addWidget(line)
        row = QHBoxLayout()
        logo = QLabel(); logo.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        anniversary = QPixmap(str(resource_path('assets/amateur_radio_100.png')))
        if not anniversary.isNull():
            logo.setPixmap(anniversary.scaled(200, 105, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        row.addWidget(logo, 0, Qt.AlignTop)
        self.support_text = QLabel(tr('PSRTTYは、100周年記念アクティビティコンテストおよび第1回JARL World Wide RTTYコンテストの企画を応援する目的もあります。みんなで参加して盛り上げていきましょう。\n\n2026年6月 JARL創立100周年\n2027年9月 日本におけるアマチュア無線100周年'))
        self.support_text.setWordWrap(True)
        row.addWidget(self.support_text, 1, Qt.AlignTop); lay.addLayout(row); lay.addStretch(1)
        scroll.setWidget(body); root.addWidget(scroll, 1)
        self.thanks_button=QPushButton(tr('スペシャルサンクス'))
        self.thanks_button.clicked.connect(self._show_thanks)
        buttons=QHBoxLayout()
        buttons.addWidget(self.thanks_button);buttons.addStretch(1)
        self.close_button=QPushButton(tr('閉じる'))
        self.close_button.clicked.connect(self.reject)
        buttons.addWidget(self.close_button);root.addLayout(buttons)
        self.thanks_window=None

    def _show_thanks(self):
        from .special_thanks_dialog import SpecialThanksDialog
        if self.thanks_window is None:
            self.thanks_window=SpecialThanksDialog(self)
        self.thanks_window.show();self.thanks_window.raise_();self.thanks_window.activateWindow()

    def done(self, result):
        if self.thanks_window:self.thanks_window.close()
        super().done(result)
