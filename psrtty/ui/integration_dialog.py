"""Integration settings and background dispatch, independent of RX/TX I/O."""
from copy import deepcopy

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QSpinBox)

from ..hamlog_link import HamlogLink, TARGET_VERSION, API_VERSION
from ..i18n import tr
from ..zserver_link import ZServerLink, LinkError, DEFAULT_OPTIONS
from .background import BackgroundJob

VERSION_NOTICE = '対応対象：Turbo HAMLOG/Win Ver{version}（公開連携API Ver{api}以降）。'
ZLOG_NOTICE = 'zlink.notice'


class IntegrationController(QObject):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.link = HamlogLink(main.paths['var'] / 'hamlog-transfer.jsonl')
        self.busy = False
        self.dialog = None
        self.zlog_dialog = None
        self.zlink = ZServerLink(main.paths['var'] / 'zserver-outbox.json')
        self._last_zstatus = None
        self.z_timer = QTimer(self); self.z_timer.setInterval(500)
        self.z_timer.timeout.connect(self.poll_zlog); self.z_timer.start()
        try:self.zlink.configure(main.store.data.get('zlog', {}))
        except Exception as exc:self.zlink._status('zlink.error', str(exc))

    def settings(self):
        if self.dialog is None:
            self.dialog = HamlogSettingsDialog(self, self.main)
        self.dialog.show(); self.dialog.raise_(); self.dialog.activateWindow()

    def zlog_settings(self):
        if self.zlog_dialog is None:self.zlog_dialog = ZLogSettingsDialog(self.main)
        self.zlog_dialog.reload()
        self.zlog_dialog.show(); self.zlog_dialog.raise_(); self.zlog_dialog.activateWindow()

    def zstatus_text(self):
        state, detail, count, confirmed = self.zlink.snapshot()
        result=tr(state) + ' — ' + tr('zlink.pending').format(count=count)
        if detail:result += '\n' + detail
        return result

    def poll_zlog(self):
        status=self.zlink.snapshot()
        if self.zlog_dialog:self.zlog_dialog.status.setText(self.zstatus_text())
        if status != self._last_zstatus and self.main.store.data.get('zlog',{}).get('enabled'):
            self.main.statusBar().showMessage(self.zstatus_text(),8000)
        self._last_zstatus=status

    def close(self):
        self.z_timer.stop();self.zlink.close()
        if self.zlog_dialog:self.zlog_dialog.close()

    def run(self, work, done):
        if self.busy:
            QMessageBox.warning(self.main, tr('ui.0ac34687acceae77'), tr('ui.fdea9eee6b1d0a95'))
            return False
        self.busy = True
        def completed(result, error):
            self.busy = False
            done(result, error)
        self.job = BackgroundJob(self, work, completed)
        return True

    def record(self, qso):
        try:self.zlink.enqueue(deepcopy(qso))
        except Exception as exc:
            detail=tr(exc.key) if isinstance(exc,LinkError) else str(exc)
            QMessageBox.warning(self.main,tr('ui.17cea206eaeefd06'),tr('zlink.record_error').format(error=detail))
        options = self.main.store.data.get('hamlog', {})
        if not options.get('enabled', False):
            return
        def finished(result, error):
            if error:
                QMessageBox.warning(self.main, tr('ui.0ac34687acceae77'),
                    tr('ui.562b84afbfde6dc7').format(error=error))
            else:
                self.main.statusBar().showMessage(result, 10000)
        if self.busy:
            finished(None, tr('ui.8782c571d070c4b3'))
            return
        qso = deepcopy(qso)
        auto_save = options.get('auto_save', False)
        self.run(lambda: self.link.transfer(qso, auto_save), finished)


class HamlogSettingsDialog(QDialog):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.setWindowTitle(tr('ui.2354935a4ee2b937'))
        self.resize(640, 480)
        root = QVBoxLayout(self)
        for text in (tr(VERSION_NOTICE).format(version=TARGET_VERSION, api=API_VERSION),
                     tr('ui.99ebd89f04ffb1bf')):
            label = QLabel(text); label.setWordWrap(True); root.addWidget(label)
        self.enabled = QCheckBox(tr('ui.3965d764b4019026'))
        self.enabled.setChecked(controller.main.store.data.get('hamlog', {}).get('enabled', False))
        root.addWidget(self.enabled)
        self.save_mode = QComboBox()
        self.save_mode.addItem(tr('ui.55abaa225677564c'), False)
        self.save_mode.addItem(tr('ui.b038c248f01d9777'), True)
        self.save_mode.setCurrentIndex(int(controller.main.store.data.get('hamlog', {}).get('auto_save', False)))
        form = QFormLayout(); form.addRow(tr('ui.b7609e3949e19670'), self.save_mode); root.addLayout(form)
        note = QLabel(tr('ui.303123bf66937008'))
        note.setWordWrap(True); root.addWidget(note)
        self.check_button = QPushButton(tr('ui.242261d9bdf8729e'))
        self.check_button.clicked.connect(self.check); root.addWidget(self.check_button)
        row = QHBoxLayout()
        self.call = QLineEdit(); self.call.setPlaceholderText(tr('ui.e54f8ce684788b1b'))
        self.search_button = QPushButton(tr('ui.a3f9a6c76bb95689'))
        self.search_button.clicked.connect(self.lookup)
        row.addWidget(self.call); row.addWidget(self.search_button); root.addLayout(row)
        note = QLabel(tr('ui.028b54989d5885bb'))
        note.setWordWrap(True); root.addWidget(note)
        self.result = QLabel(); self.result.setWordWrap(True); self.result.setTextFormat(Qt.PlainText)
        self.result.setTextInteractionFlags(Qt.TextSelectableByMouse); root.addWidget(self.result)
        root.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('ui.a3030bf8f16dc63c'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def _work(self, work, render):
        def done(result, error):
            self.check_button.setEnabled(True); self.search_button.setEnabled(True)
            if error:
                QMessageBox.warning(self, tr('ui.0ac34687acceae77'), tr(str(error)))
            else:
                self.result.setText(render(result))
        if self.controller.run(work, done):
            self.check_button.setEnabled(False); self.search_button.setEnabled(False)
            self.result.setText(tr('ui.150fad0f11e1eadc'))

    def check(self):
        self._work(self.controller.link.check, lambda title: tr('ui.23c45791e4c46b0f').format(title=title))

    def lookup(self):
        call = self.call.text()
        self._work(lambda: self.controller.link.lookup(call),
                   lambda result: tr('ui.44d815d5ed26e974').format(**result))

    def save(self):
        data = self.controller.main.store.data
        previous = deepcopy(data.get('hamlog', {}))
        data['hamlog'] = {'enabled': self.enabled.isChecked(), 'auto_save': self.save_mode.currentData()}
        try:
            self.controller.main.store.save()
        except Exception as exc:
            data['hamlog'] = previous
            QMessageBox.warning(self, tr('ui.5cfe5f420da9fee5'), tr(str(exc))); return
        self.accept()


class ZLogSettingsDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main=main;self.controller=main.integration
        self.setWindowTitle(tr('ui.17cea206eaeefd06'));self.resize(680,640)
        self.setStyleSheet('QLineEdit, QComboBox, QSpinBox { min-height:22px; padding:4px; }')
        root=QVBoxLayout(self)
        for key in ('zlink.notice','zlink.setup'):
            label=QLabel(tr(key));label.setWordWrap(True);root.addWidget(label)
        self.enabled=QCheckBox(tr('zlink.enabled'));root.addWidget(self.enabled)
        self.host=QLineEdit();self.port=QSpinBox();self.port.setRange(1,65535)
        self.pc_name=QLineEdit();self.pc_name.setMaxLength(20)
        self.operator=QLineEdit();self.operator.setMaxLength(20)
        self.tx=QSpinBox();self.tx.setRange(0,15)
        self.time_basis=QComboBox();self.time_basis.addItem('UTC','UTC');self.time_basis.addItem('JST','JST')
        self.decimal=QComboBox();self.decimal.addItem('.','.');self.decimal.addItem(',',',')
        form=QFormLayout()
        for key,widget in (('host',self.host),('port',self.port),('pc_name',self.pc_name),
                           ('operator',self.operator),('tx',self.tx),('time_basis',self.time_basis),('decimal',self.decimal)):
            form.addRow(tr('zlink.'+key),widget)
        root.addLayout(form)
        note=QLabel(tr('zlink.time_note'));note.setWordWrap(True);root.addWidget(note)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse);root.addWidget(self.status)
        self.connect_button=QPushButton(tr('zlink.save_connect'));self.connect_button.clicked.connect(self.connect_now)
        root.addWidget(self.connect_button)
        note=QLabel(tr('zlink.queue_note'));note.setWordWrap(True);root.addWidget(note)
        button=QPushButton(tr('ui.989d12c480a3da4d'));button.clicked.connect(main._export_adif);root.addWidget(button)
        root.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('ui.a3030bf8f16dc63c'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.reload()

    def reload(self):
        options=dict(DEFAULT_OPTIONS,**self.main.store.data.get('zlog',{}))
        self.enabled.setChecked(options['enabled']);self.host.setText(options['host'])
        self.port.setValue(options['port']);self.pc_name.setText(options['pc_name'])
        self.operator.setText(options['operator']);self.tx.setValue(options['tx'])
        self.time_basis.setCurrentIndex(self.time_basis.findData(options['time_basis']))
        self.decimal.setCurrentIndex(self.decimal.findData(options['decimal']))
        self.status.setText(self.controller.zstatus_text())

    def values(self):
        return {'enabled':self.enabled.isChecked(),'host':self.host.text(),'port':self.port.value(),
                'pc_name':self.pc_name.text(),'operator':self.operator.text(),'tx':self.tx.value(),
                'time_basis':self.time_basis.currentData(),'decimal':self.decimal.currentData()}

    def apply(self):
        previous=deepcopy(self.main.store.data.get('zlog',{}))
        try:
            options=self.controller.zlink.check_options(self.values())
            self.main.store.data['zlog']=options;self.main.store.save()
        except Exception as exc:
            self.main.store.data['zlog']=previous
            detail=tr(exc.key) if isinstance(exc,LinkError) else str(exc)
            QMessageBox.warning(self,tr('ui.17cea206eaeefd06'),detail);return False
        self.controller.zlink.configure(options)
        self.controller.zlink.wake.set();self.controller.poll_zlog();return True

    def connect_now(self):
        self.enabled.setChecked(True);self.apply()

    def save(self):
        if self.apply():self.accept()
