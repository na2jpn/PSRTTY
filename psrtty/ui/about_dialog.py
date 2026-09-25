from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QScrollArea, QVBoxLayout, QWidget

from ..paths import resource_path


ABOUT_TEXT = """<h2>PSRTTY 0.83</h2>
<p>Python / PySide6によるRTTYコンテスト向け通信ソフト。</p>
<p>ICOM無線機とのCI-V接続およびUSB Audioを利用し、RTTYの送受信、マクロ送信、QSO記録を行います。</p>
<p>Yaesu FT-991 / FT-991A、FTX-1シリーズのCAT接続は試験用です。実機での動作確認は未実施です。</p>
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
"""


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PSRTTYについて")
        self.resize(650, 650)
        root = QVBoxLayout(self)
        icon = QLabel(); icon.setAlignment(Qt.AlignCenter)
        pix = QPixmap(str(resource_path("assets/psrtty.png")))
        if not pix.isNull(): icon.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        root.addWidget(icon)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        body = QWidget(); lay = QVBoxLayout(body)
        text = QLabel(ABOUT_TEXT); text.setWordWrap(True); text.setTextFormat(Qt.RichText); text.setOpenExternalLinks(True)
        lay.addWidget(text); lay.addStretch(1)
        scroll.setWidget(body); root.addWidget(scroll, 1)
