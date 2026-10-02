"""Integration settings and background dispatch, independent of RX/TX I/O."""
from copy import deepcopy

from PySide6.QtCore import QObject, Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..hamlog_link import HamlogLink, TARGET_VERSION, API_VERSION
from ..i18n import tr
from .background import BackgroundJob

VERSION_NOTICE = '対応対象：Turbo HAMLOG/Win Ver{version}（公開連携API Ver{api}以降）。'
ZLOG_NOTICE = '対応対象：zLog 3.0.4.0（ZLOG3040）のADIF読み込み仕様。リアルタイム連動ではありません。'


class IntegrationController(QObject):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.link = HamlogLink(main.paths['var'] / 'hamlog-transfer.jsonl')
        self.busy = False
        self.dialog = None

    def settings(self):
        if self.dialog is None:
            self.dialog = HamlogSettingsDialog(self, self.main)
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def run(self, work, done):
        if self.busy:
            QMessageBox.warning(self.main, tr('HAMLOG連携'), tr('HAMLOGとの通信中です。終了してから操作してください。'))
            return False
        self.busy = True
        def completed(result, error):
            self.busy = False
            done(result, error)
        self.job = BackgroundJob(self, work, completed)
        return True

    def record(self, qso):
        options = self.main.store.data.get('hamlog', {})
        if not options.get('enabled', False):
            return
        def finished(result, error):
            if error:
                QMessageBox.warning(self.main, tr('HAMLOG連携'),
                    tr('PSRTTYのADIFには保存済みです。QSOを再追加しないでください。\nHAMLOG転送を完了できませんでした。\n{error}\n\nHAMLOGで未登録の場合は手動登録、またはHAMLOG CSV出力を利用してください。').format(error=error))
            else:
                self.main.statusBar().showMessage(result, 10000)
        if self.busy:
            finished(None, tr('前のHAMLOG処理が完了していません。この交信は転送していません。'))
            return
        qso = deepcopy(qso)
        auto_save = options.get('auto_save', False)
        self.run(lambda: self.link.transfer(qso, auto_save), finished)


class HamlogSettingsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(tr('HAMLOG連携設定'))
        self.resize(640, 480)
        root = QVBoxLayout(self)
        for text in (tr(VERSION_NOTICE).format(version=TARGET_VERSION, api=API_VERSION),
                     tr('PSRTTYで記録した交信をHAMLOGへ転送します。手動記録とTU73自動記録で共通です。逆方向の記録・編集・削除の同期は行いません。')):
            label = QLabel(text); label.setWordWrap(True); root.addWidget(label)
        self.enabled = QCheckBox(tr('記録時にHAMLOGへ転送する'))
        self.enabled.setChecked(controller.main.store.data.get('hamlog', {}).get('enabled', False))
        root.addWidget(self.enabled)
        self.save_mode = QComboBox()
        self.save_mode.addItem(tr('入力欄へ転送のみ（HAMLOGで保存）'), False)
        self.save_mode.addItem(tr('転送後にHAMLOGへ保存指示を送る'), True)
        self.save_mode.setCurrentIndex(int(controller.main.store.data.get('hamlog', {}).get('auto_save', False)))
        form = QFormLayout(); form.addRow(tr('HAMLOG側の保存'), self.save_mode); root.addLayout(form)
        note = QLabel(tr('入力中の別の交信は上書きしません。途中で通信が切れた場合は自動再送せず、内容の確認を案内します。入力欄への転送のみを選んだ場合は、次の交信までにHAMLOGで保存してください。'))
        note.setWordWrap(True); root.addWidget(note)
        self.check_button = QPushButton(tr('HAMLOGの接続を確認'))
        self.check_button.clicked.connect(self.check); root.addWidget(self.check_button)
        row = QHBoxLayout()
        self.call = QLineEdit(); self.call.setPlaceholderText(tr('検索するCALL'))
        self.search_button = QPushButton(tr('CALL検索・氏名／QTH取得'))
        self.search_button.clicked.connect(self.lookup)
        row.addWidget(self.call); row.addWidget(self.search_button); root.addLayout(row)
        note = QLabel(tr('検索はHAMLOGの空の入力欄へCALLを入れ、HAMLOGの検索機能を使います。取得内容はHAMLOGの設定と登録データに従います。'))
        note.setWordWrap(True); root.addWidget(note)
        self.result = QLabel(); self.result.setWordWrap(True); self.result.setTextFormat(Qt.PlainText)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse); root.addWidget(self.result)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('保存'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('キャンセル'))
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _work(self, work, render):
        def done(result, error):
            self.check_button.setEnabled(True); self.search_button.setEnabled(True)
            if error:
                QMessageBox.warning(self, tr('HAMLOG連携'), str(error))
            else:
                self.result.setText(render(result))
        if self.controller.run(work, done):
            self.check_button.setEnabled(False); self.search_button.setEnabled(False)
            self.result.setText(tr('HAMLOGと通信中…'))

    def check(self):
        self._work(self.controller.link.check, lambda title: tr('応答を確認しました：{title}').format(title=title))

    def lookup(self):
        call = self.call.text()
        self._work(lambda: self.controller.link.lookup(call),
                   lambda result: tr('CALL: {call}\n氏名: {name}\nQTH: {qth}').format(**result))

    def save(self):
        data = self.controller.main.store.data
        previous = deepcopy(data.get('hamlog', {}))
        data['hamlog'] = {'enabled': self.enabled.isChecked(), 'auto_save': self.save_mode.currentData()}
        try:
            self.controller.main.store.save()
        except Exception as exc:
            data['hamlog'] = previous
            QMessageBox.warning(self, tr('設定の保存'), str(exc)); return
        self.accept()


class ZLogSettingsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.setWindowTitle(tr('zLog令和版連携設定')); self.resize(630, 340)
        root = QVBoxLayout(self)
        for text in (tr(ZLOG_NOTICE), tr('ADIFファイル出力で、標準・zLog一般・JARL WW RTTY・CQ WW RTTYを選択できます。zLogでコンテスト・自局CALL・時刻設定を合わせ、ADIFを読み込んでください。'),
                     tr('CQ WW RTTYの州・地域はzLogのADIF読み込みでは受信番号に入りません。備考に元の交換番号を残します。取り込み後、該当局の受信番号とマルチを確認・修正してください。')):
            label = QLabel(text); label.setWordWrap(True); root.addWidget(label)
        button = QPushButton(tr('ADIFファイル出力を開く'))
        button.clicked.connect(main._export_adif); root.addWidget(button)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(tr('閉じる'))
        buttons.rejected.connect(self.reject); root.addWidget(buttons)
