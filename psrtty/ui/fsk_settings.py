"""Profile-scoped FSK settings, using the existing connection/test lifecycle."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QFormLayout,QLabel,QComboBox,QCheckBox,QPushButton,QMessageBox,QHBoxLayout,QGroupBox,QVBoxLayout
from ..i18n import tr
from .questions import ask_question
from .fsk_help import settings_html
from .fsk_notice import notice_color,notice_key
from ..fsk import SUPPORTED,enabled,validate
from ..civ import CIVController
from ..fsk_models import USB_KEYING, KENWOOD_FSK, YAESU_FSK, YAESU_AFSK_ONLY, modes_for, warning_key

class FSKSettingsMixin:
    def _fsk_switch_button(self,form):
        form.addRow(QLabel(''))
        self.fsk_group=QGroupBox(tr('fsk.method'))
        layout=QVBoxLayout(self.fsk_group)
        layout.setContentsMargins(12,16,12,12)
        self.fsk_switch=QPushButton(tr('fsk.to_afsk' if enabled(self.working) else 'fsk.to_fsk'))
        self.fsk_switch.clicked.connect(self._switch_fsk)
        self.fsk_model_notice=QLabel();self.fsk_model_notice.setWordWrap(True)
        layout.addWidget(self.fsk_model_notice)
        layout.addWidget(self.fsk_switch)
        self.rig.currentIndexChanged.connect(self._refresh_fsk_model_notice)
        self._refresh_fsk_model_notice()
        form.addRow(self.fsk_group)
    def _switch_fsk(self):
        parent=self.parent()
        if self.tx_testing or self.test_pending or (parent and (parent.audio._tx_active or parent.connecting or parent.antenna_tuning)):
            QMessageBox.warning(self,tr('fsk.title'),tr('fsk.busy'));return
        target=not enabled(self.working)
        if target and self.rig.currentData() not in SUPPORTED:
            QMessageBox.information(self,tr('fsk.title'),tr(warning_key(self.rig.currentData())));return
        if ask_question(self,tr('fsk.title'),tr('fsk.confirm' if target else 'fsk.confirm_afsk'),
                'fsk.yes' if target else 'fsk.afsk_yes','fsk.no' if target else 'fsk.afsk_no')!=QMessageBox.Yes:return
        if not self._capture_profile():return
        self._stop_external_test();self._release_test_controller()
        self.working['radio']['tx_method']='fsk' if target else 'afsk'
        if target:
            if self.rig.currentData() not in USB_KEYING and self.working['fsk'].get('port')=='RADIO':self.working['fsk']['port']=''
        self.working_profiles[self.profile_index]['radio'].update(self.working['radio'])
        self._rebuild_inner_tabs();self.tabs.setCurrentIndex(1)
    def _build_fsk_tab(self):
        tab=QWidget();form=QFormLayout(tab)
        note=QLabel(tr('fsk.note'));note.setWordWrap(True);note.setObjectName('helpText');form.addRow(note)
        self.fsk_port=QComboBox();self.fsk_port.addItem(tr('fsk.port_select'),'')
        if self.working['radio'].get('model') in USB_KEYING:self.fsk_port.addItem(tr('fsk.shared'),'RADIO')
        for port,label in CIVController.port_choices():self.fsk_port.addItem(label,port)
        port=self.working['fsk'].get('port','RADIO')
        if self.fsk_port.findData(port)<0:self.fsk_port.addItem(port,port)
        self._select_data(self.fsk_port,port);form.addRow(tr('fsk.port'),self.fsk_port)
        self.fsk_line=QComboBox();self.fsk_line.addItems(['DTR','RTS']);self.fsk_line.setCurrentText(self.working['fsk'].get('line','DTR'))
        form.addRow(tr('fsk.line'),self.fsk_line)
        self.fsk_invert=QCheckBox(tr('fsk.invert'));self.fsk_invert.setChecked(self.working['fsk'].get('invert',False));form.addRow(self.fsk_invert)
        self.fsk_help=QLabel();self.fsk_help.setWordWrap(True);self.fsk_help.setOpenExternalLinks(True)
        self.fsk_help.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.LinksAccessibleByMouse)
        self.rig.currentIndexChanged.connect(self._refresh_fsk_help)
        self.ptt.currentIndexChanged.connect(self._refresh_fsk_help)
        self.fsk_line.currentIndexChanged.connect(self._refresh_fsk_help)
        self.fsk_invert.toggled.connect(self._refresh_fsk_help)
        self._refresh_fsk_help()
        for widget in (self.fsk_port,self.fsk_line):widget.currentIndexChanged.connect(self._test_controls_changed)
        self.fsk_invert.toggled.connect(self._test_controls_changed)
        self.test_tx_button.setText(tr('fsk.test'))
        row=QHBoxLayout();row.addWidget(self.audio_connect_button);row.addWidget(self.test_tx_button);row.addWidget(self.test_count_label)
        form.addRow(row);form.addRow(self.tx_test_note)
        form.addRow(self.fsk_help)
        self.tabs.addTab(tab,tr('fsk.output'))
    def _refresh_fsk_model_notice(self,*_):
        model=self.rig.currentData()
        self.fsk_model_notice.setStyleSheet('color:'+notice_color(model)+';')
        self.fsk_model_notice.setText(tr(notice_key(model)) if (model or '').startswith('IC-') or model=='その他ICOM' or model in KENWOOD_FSK|YAESU_FSK|YAESU_AFSK_ONLY else '')
        if hasattr(self,'data_mode') and enabled(self.working):
            current=self.data_mode.currentText();self.data_mode.blockSignals(True)
            self.data_mode.clear();self.data_mode.addItems(modes_for(model))
            self.data_mode.setCurrentText(current);self.data_mode.blockSignals(False)
    def _refresh_fsk_help(self,*_):
        if not hasattr(self,'fsk_help'):return
        self.fsk_help.setText(settings_html(self.rig.currentData(),self.fsk_line.currentText(),
            self.ptt.currentData() or self.ptt.currentText(),self.fsk_invert.isChecked()))

    def _fsk_values(self):
        values=dict(self.working['fsk'])
        if enabled(self.working):
            values.update(port=self.fsk_port.currentData() or '',line=self.fsk_line.currentText(),invert=self.fsk_invert.isChecked())
            if hasattr(self,'data_mode') and self.data_mode.currentText() in ('RTTY','RTTY-R'):values['mode']=self.data_mode.currentText()
        return values
