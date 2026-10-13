"""Raw UDP ADIF settings; sending test contacts would create real log entries."""
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog,QVBoxLayout,QFormLayout,QCheckBox,QLineEdit,QSpinBox,QLabel,QDialogButtonBox,QMessageBox
from ..i18n import tr
from ..udp_adif import options_checked,DEFAULT_OPTIONS,UdpError

class UdpAdifDialog(QDialog):
    def __init__(self,controller,parent=None):
        super().__init__(parent);self.controller=controller;self.setWindowTitle(tr('udp.title'));self.resize(600,420)
        root=QVBoxLayout(self);self.enabled=QCheckBox(tr('udp.enabled'));root.addWidget(self.enabled)
        form=QFormLayout();self.host=QLineEdit();self.port=QSpinBox();self.port.setRange(1,65535)
        form.addRow(tr('udp.host'),self.host);form.addRow(tr('udp.port'),self.port);root.addLayout(form)
        for key in ('udp.guide','udp.note'):
            label=QLabel(tr(key));label.setWordWrap(True);label.setTextFormat(Qt.PlainText);root.addWidget(label)
        self.status=QLabel();self.status.setWordWrap(True);self.status.setTextFormat(Qt.PlainText);root.addWidget(self.status);root.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('ui.a3030bf8f16dc63c'));buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        buttons.accepted.connect(self.save);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.reload()
    def reload(self):
        try:o=options_checked(self.controller.main.store.data.get('udp_adif',DEFAULT_OPTIONS))
        except UdpError:o=DEFAULT_OPTIONS
        self.enabled.setChecked(o['enabled']);self.host.setText(o['host']);self.port.setValue(o['port']);self.refresh_status()
    def refresh_status(self):
        enabled=self.controller.main.store.data.get('udp_adif',{}).get('enabled',False)
        self.status.setText(self.controller.udp_status)
        self.status.setStyleSheet('color: #168aad;' if enabled else 'color: #777777;')
    def save(self):
        try:o=options_checked({'enabled':self.enabled.isChecked(),'host':self.host.text(),'port':self.port.value()})
        except UdpError as exc:QMessageBox.warning(self,tr('udp.title'),tr(exc.key));return
        store=self.controller.main.store;before=deepcopy(store.data.get('udp_adif',DEFAULT_OPTIONS));store.data['udp_adif']=o
        try:store.save()
        except Exception as exc:
            store.data['udp_adif']=before;QMessageBox.warning(self,tr('udp.title'),str(exc));return
        self.controller.udp_status=tr('udp.idle') if o['enabled'] else tr('udp.disabled');self.accept()
