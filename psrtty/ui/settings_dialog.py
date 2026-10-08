from __future__ import annotations
from ..i18n import tr

from copy import deepcopy
import time

from PySide6.QtCore import Qt, QTimer, Signal, QRegularExpression
from PySide6.QtGui import QColor, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget, QGroupBox, QLineEdit, QPlainTextEdit, QProgressBar,
)

from ..audio_engine import AudioEngine
from ..civ import CIVController, connect_configured
from ..radio import create_controller, validate_radio
from ..external_ptt import ExternalPTT, validate_external
from ..yaesu import YAESU_MODELS
from ..hamlib_radio import HAMLIB_MODELS
from .background import BackgroundJob
from ..config import DEFAULT_CONFIG, RIG_MODELS, PROFILE_KEYS, profile_name


class SettingsDialog(QDialog):
    before_save = Signal()
    tx_test_finished = Signal(bool, str)
    def __init__(self, config_store, parent=None):
        super().__init__(parent)
        self.test_controller = None
        self.test_uses_main = False
        self.test_pending = False
        self.test_timed_out = False
        self.verified_values = None
        self.tx_testing = False
        self.alc_busy = False
        self.alc_onset = None
        self.alc_value = None
        self.test_deadline = 0.0
        self.test_connection_generation = 0
        self.connect_requested = False
        self.store = config_store
        self.working = deepcopy(config_store.data)
        self.profile_index = 0
        self.active_profile_index = config_store.data['active_profile']
        self.working_profiles = deepcopy(config_store.data['profiles'])
        # The main window may have edited the active settings since the last save.
        # Show those live values if its Profile is selected without changing the store.
        self.working_profiles[self.active_profile_index].update(
            {key: deepcopy(config_store.data[key]) for key in PROFILE_KEYS})
        self.working.update({key: deepcopy(self.working_profiles[0][key]) for key in PROFILE_KEYS})
        self.setWindowTitle(tr('ui.e5c2ff2ea7d4fb50'))
        self.resize(660, 600)

        root = QVBoxLayout(self)
        intro = QLabel(
            tr('ui.d75c3ae48c5ec3ce')
        )
        intro.setWordWrap(True)
        intro.setObjectName("helpText")
        root.addWidget(intro)

        self.profile_tabs = QTabWidget()
        root.addWidget(self.profile_tabs, 1)
        for profile in self.working_profiles:
            page = QWidget(); page.setLayout(QVBoxLayout())
            page.layout().setContentsMargins(0, 2, 0, 0)
            self.profile_tabs.addTab(page, profile['name'])
        add_profile = QPushButton(tr('ui.a0d9f4ff64b05071'))
        add_profile.setMinimumHeight(28)
        add_profile.clicked.connect(self._add_profile)
        self.profile_tabs.setCornerWidget(add_profile, Qt.TopRightCorner)
        self._rebuild_inner_tabs()
        self.profile_tabs.currentChanged.connect(self._profile_changed)
        self.profile_tabs.currentChanged.connect(self._update_profile_tab_colors)
        self._update_profile_tab_colors()

        actions = QHBoxLayout()
        self.delete_profile_button = QPushButton(tr('ui.49cee7d28b4f3090'))
        self.delete_profile_button.clicked.connect(self._delete_profile)
        actions.addWidget(self.delete_profile_button)
        actions.addStretch(1)
        self.secondary_button = QPushButton(tr('ui.acd8e57f9bb73955'))
        self.secondary_button.clicked.connect(self._open_secondary_audio)
        self.secondary_button.hide()
        actions.addWidget(self.secondary_button)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr('ui.a3030bf8f16dc63c'))
        buttons.button(QDialogButtonBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        actions.addWidget(buttons)
        root.addLayout(actions)
        self.tx_test_finished.connect(self._test_tx_finished)
        self.countdown = QTimer(self); self.countdown.setInterval(200)
        self.countdown.timeout.connect(self._tick_test_tx)
        self.level_timer = QTimer(self); self.level_timer.setInterval(100)
        self.level_timer.timeout.connect(self._refresh_rx_meter)
        self.level_timer.start()

    def _build_basic_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        self.profile_name_edit = QLineEdit(self.working_profiles[self.profile_index]['name'])
        self.profile_name_edit.setMaxLength(10)
        self.profile_name_edit.setValidator(QRegularExpressionValidator(QRegularExpression('[A-Za-z0-9/-]{0,10}'), self.profile_name_edit))
        form.addRow(tr('ui.6d0497876c48026d'), self.profile_name_edit)
        self.my_call = QLineEdit(self.working.get('station_callsign', ''))
        self.my_call.setPlaceholderText(tr('ui.25533bf82cf78b98'))
        station = self.working['station']
        self.my_qth = QLineEdit(station['qth'])
        self.my_qth.setPlaceholderText(tr('ui.5f7936285da3f143'))
        self.my_jcc_jcg = QLineEdit(station['jcc_jcg'])
        self.my_jcc_jcg.setPlaceholderText(tr('ui.8e3c0baaaddfca68'))
        self.my_text = QPlainTextEdit(station['text'])
        self.my_text.setPlaceholderText(tr('ui.a1a062efb75ab178'))
        form.addRow(tr('ui.18619d6669e0866e'), self.my_call)
        form.addRow(tr('ui.2097a2f37bbe4363'), self.my_qth)
        form.addRow('JCC/JCG {MYJCCJCG}', self.my_jcc_jcg)
        form.addRow(tr('ui.1a0f216487deae85'), self.my_text)
        note = QLabel(tr('ui.fa6c7f957970e52c'))
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        self.tabs.addTab(tab, tr('ui.a37d92500512aa67'))

    def _rebuild_inner_tabs(self):
        page = self.profile_tabs.widget(self.profile_index)
        if hasattr(self, 'tabs'):
            page.layout().removeWidget(self.tabs)
            self.tabs.deleteLater()
        self.tabs = QTabWidget(page)
        page.layout().addWidget(self.tabs)
        for method in (self._build_basic_tab, self._build_radio_tab,
                       self._build_audio_in_tab, self._build_audio_out_tab,
                       self._build_external_tab, self._build_advanced_tab):
            method()
        self.tabs.currentChanged.connect(self._update_inner_tab_colors)
        self._update_inner_tab_colors()
        for combo in (self.rig, self.com, self.ptt, self.baud, self.stopbits, self.data_mode):
            combo.currentIndexChanged.connect(self._test_controls_changed)
        self.civ_addr.currentTextChanged.connect(self._test_controls_changed)
        self.auto_mode.toggled.connect(self._test_controls_changed)
        if self.profile_index == self.active_profile_index:
            self._adopt_main_connection()
        else:
            self.connect_button.setEnabled(False)
            self.connect_button.setToolTip(tr('ui.4d2025f57bff3bbe'))

    def _capture_profile(self):
        name = profile_name(self.profile_name_edit.text().strip())
        if not name:
            QMessageBox.warning(self, tr('ui.88961610d2a4c6ac'), tr('ui.a3fb0d3ca1a1210c'))
            return False
        if any(i != self.profile_index and p['name'].lower() == name.lower()
               for i, p in enumerate(self.working_profiles)):
            QMessageBox.warning(self, tr('ui.88961610d2a4c6ac'), tr('ui.26b9020f630663cf'))
            return False
        self.working_profiles[self.profile_index]['name'] = name
        self.profile_tabs.setTabText(self.profile_index, name)
        self.working['radio'].update(self._radio_values())
        self.working['external'].update(self._external_values())
        self.working['audio'].update(input_device=self.audio_in.currentData() or 'AUTO',
                                     output_device=self.audio_out.currentData() or 'AUTO',
                                     rx_gain=self.rx_gain.value()/100, tx_gain=self.tx_gain.value()/100)
        self.working['advanced'].update(data_mode=self.data_mode.currentText(),
            rtty_baud=self.rtty_baud.value(), shift_hz=self.shift.value(),
            mark_hz=self.mark.value(), space_hz=self.space.value(), invert=self.invert.isChecked(),
            spectrum_width_hz=self.spec_width.currentData(), auto_tune_tolerance_hz=self.tune_tol.value())
        from ..parser import normalize_call
        self.working['station_callsign'] = normalize_call(self.my_call.text())
        self.working['station'].update(qth=self.my_qth.text().strip(),
            jcc_jcg=self.my_jcc_jcg.text().strip(), text=self.my_text.toPlainText().strip())
        self.working_profiles[self.profile_index].update(
            {key: deepcopy(self.working[key]) for key in PROFILE_KEYS})
        return True

    def _profile_changed(self, index):
        if index < 0 or index == self.profile_index:
            return
        if self.tx_testing or self.test_pending or not self._capture_profile():
            self.profile_tabs.blockSignals(True)
            self.profile_tabs.setCurrentIndex(self.profile_index)
            self.profile_tabs.blockSignals(False)
            return
        self._release_test_controller()
        old = self.tabs
        self.profile_tabs.widget(self.profile_index).layout().removeWidget(old)
        old.deleteLater()
        del self.tabs
        self.profile_index = index
        self.working = deepcopy(self.store.data)
        self.working.update({key: deepcopy(self.working_profiles[index][key]) for key in PROFILE_KEYS})
        self._rebuild_inner_tabs()

    def _add_profile(self):
        if len(self.working_profiles) >= 6:
            QMessageBox.information(self, tr('ui.5be15c5e5420e0c5'), tr('ui.c439d65e7b5d0271')); return
        if not self._capture_profile(): return
        used = {p['name'].lower() for p in self.working_profiles}
        number = next(n for n in range(1, 10) if f'profile{n}' not in used)
        new = deepcopy(self.working_profiles[self.profile_index])
        new['name'] = f'Profile{number}'
        self.working_profiles.append(new)
        page = QWidget(); page.setLayout(QVBoxLayout())
        page.layout().setContentsMargins(0, 2, 0, 0)
        self.profile_tabs.addTab(page, new['name'])
        self.profile_tabs.setCurrentIndex(len(self.working_profiles)-1)

    def _update_profile_tab_colors(self, *_):
        bar = self.profile_tabs.tabBar()
        for index in range(self.profile_tabs.count()):
            bar.setTabTextColor(index, QColor('#c6670b' if index == self.profile_tabs.currentIndex() else '#604b37'))

    def _update_inner_tab_colors(self, *_):
        if hasattr(self, 'secondary_button'):
            self.secondary_button.setVisible(self.tabs.tabText(self.tabs.currentIndex()) == 'Audio OUT')
        bar = self.tabs.tabBar()
        for index in range(self.tabs.count()):
            bar.setTabTextColor(index, QColor('#c6670b' if index == self.tabs.currentIndex() else '#604b37'))

    def _delete_profile(self):
        index = self.profile_index
        if index == 0:
            QMessageBox.information(self, tr('ui.ddca9a49fef40d64'), tr('ui.938723042f443c6c'))
            return
        if index == self.active_profile_index:
            QMessageBox.information(self, tr('ui.ddca9a49fef40d64'), tr('ui.04864c7da4dae51f'))
            return
        if self.tx_testing or self.test_pending:
            QMessageBox.information(self, tr('ui.ddca9a49fef40d64'), tr('ui.396888a93624ff49'))
            return
        name = self.working_profiles[index]['name']
        if QMessageBox.question(self, tr('ui.ddca9a49fef40d64'), tr('ui.e1ed8e390038d0e0').format(name=name)) != QMessageBox.Yes:
            return
        self._release_test_controller()
        old = self.tabs
        self.profile_tabs.widget(index).layout().removeWidget(old)
        old.deleteLater()
        del self.tabs
        self.profile_tabs.blockSignals(True)
        self.profile_tabs.removeTab(index)
        self.profile_tabs.setCurrentIndex(0)
        self.profile_tabs.blockSignals(False)
        del self.working_profiles[index]
        if index < self.active_profile_index:
            self.active_profile_index -= 1
        self.profile_index = 0
        self.working = deepcopy(self.store.data)
        self.working.update({key: deepcopy(self.working_profiles[0][key]) for key in PROFILE_KEYS})
        self._rebuild_inner_tabs()
        self._update_profile_tab_colors()

    def _build_radio_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.rig = QComboBox(); self.rig.addItem(tr('ui.0de0988dea1ae0b7'), '')
        from ..radio_support import ICOM_EXTERNAL_AUDIO, ICOM_EXTERNAL_PTT
        groups=[(tr('ui.63998b8a254e5921'), [m for m in RIG_MODELS if m not in ICOM_EXTERNAL_AUDIO and m not in ICOM_EXTERNAL_PTT and m != 'その他ICOM']),
                (tr('ui.052eb3a7ebf8c24c'), list(ICOM_EXTERNAL_AUDIO)),
                (tr('ui.1865f48534f2ba77'), list(ICOM_EXTERNAL_PTT))]
        for heading,models in groups:
            self.rig.addItem(heading, '')
            self.rig.model().item(self.rig.count()-1).setEnabled(False)
            for model in models:self.rig.addItem(model,model)
        self.rig.addItem(tr('ui.148cbb4bebaec374'),'その他ICOM')
        for model, (_,label) in HAMLIB_MODELS.items(): self.rig.addItem(label, model)
        self._select_data(self.rig, self.working['radio']['model'])
        form.addRow(tr('ui.45bf10f170732eed'), self.rig)
        self.com = QComboBox(); self.com.addItem(tr('ui.36147b7e34df7ac8'), 'AUTO')
        for port, name in CIVController.port_choices(): self.com.addItem(name, port)
        target = self.working['radio']['com_port']
        if self.com.findData(target) < 0:
            self.com.addItem(f"{target}{tr('ui.fdaf3eaa9227aabe')}", target)
        self._select_data(self.com, target)
        form.addRow(tr('ui.6bf76187430ec90a'), self.com)
        self.port_note = QLabel(); self.port_note.setWordWrap(True); self.port_note.setObjectName('helpText')
        form.addRow('', self.port_note)
        self.specific = QGroupBox(tr('ui.e3dee3c5ad0acd89'))
        self.specific_form = f = QFormLayout(self.specific)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.civ_addr = QComboBox(); self.civ_addr.setEditable(True)
        self.civ_addr.addItems([f'{v:02X}' for v in sorted(set(RIG_MODELS.values())) if v])
        self.civ_addr.setCurrentText(self.working['radio']['civ_address'])
        self.address_label = QLabel(tr('ui.6c64150cb31ca77d')); f.addRow(self.address_label, self.civ_addr)
        self.address_note = QLabel(tr('ui.2821e46ec62f4b24'))
        self.address_note.setWordWrap(True); self.address_note.setObjectName('helpText'); f.addRow(self.address_note)
        self.ptt = QComboBox(); f.addRow(tr('ui.b000e357ff8c5615'), self.ptt)
        self.baud = QComboBox(); self.baud_label = QLabel(); f.addRow(self.baud_label, self.baud)
        self.stopbits = QComboBox(); self.stopbits.addItem('1', 1); self.stopbits.addItem('2', 2)
        self.stopbits_label = QLabel(tr('ui.2897a2b4ec27d731')); f.addRow(self.stopbits_label, self.stopbits)
        self.auto_mode = QCheckBox(); self.auto_mode.setChecked(self.working['radio'].get('auto_data_mode', True))
        f.addRow(self.auto_mode)
        self.cat_note = QLabel(tr('ui.95a6d1cca4557c83'))
        self.cat_note.setWordWrap(True); self.cat_note.setObjectName('helpText'); f.addRow(self.cat_note)
        form.addRow(self.specific)
        self.test_button = QPushButton(tr('ui.3ee76ae7045f1ff8')); self.test_button.clicked.connect(self._test_radio)
        form.addRow('', self.test_button)
        self.test_note = QLabel(); self.test_note.setWordWrap(True); form.addRow(self.test_note)
        self.connect_button = QPushButton(tr('ui.d528fb88a6930dfb'))
        self.connect_button.clicked.connect(self._connect_saved)
        form.addRow("", self.connect_button)
        self.rig.currentIndexChanged.connect(self._rig_changed)
        self._rig_changed(initial=True)
        self.tabs.addTab(tab, tr('ui.45bf10f170732eed'))

    def _build_external_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        values = self.working['external']
        self.external_enabled = QCheckBox(tr('ui.956da5cd42c70171'))
        self.external_enabled.setChecked(bool(values['enabled']))
        form.addRow(self.external_enabled)
        self.external_role = QComboBox()
        self.external_role.addItem(tr('ui.0289ec3b89c43dc1'), 'prekey')
        self.external_role.addItem(tr('ui.548dfef1e28627a1'), 'ptt')
        self._select_data(self.external_role, values.get('role', 'prekey'))
        form.addRow(tr('ui.bf4c22dd0b17534a'), self.external_role)
        ptt_note = QLabel(tr('ui.5b93a2afd56d0f63'))
        ptt_note.setWordWrap(True); form.addRow(ptt_note)
        self.external_port = QComboBox()
        self.external_port.addItem(tr('ui.0de0988dea1ae0b7'), '')
        for port, label in CIVController.port_choices():
            self.external_port.addItem(label, port)
        selected = values.get('com_port', '')
        if selected and self.external_port.findData(selected) < 0:
            self.external_port.addItem(f"{selected}{tr('ui.fdaf3eaa9227aabe')}", selected)
        self._select_data(self.external_port, selected)
        form.addRow(tr('ui.8a74968e2d064881'), self.external_port)
        self.external_line = QComboBox()
        self.external_line.addItems(['RTS', 'DTR'])
        self.external_line.setCurrentText(values.get('line', 'RTS'))
        form.addRow(tr('ui.16b0af04bae02158'), self.external_line)
        self.external_delay = QDoubleSpinBox()
        self.external_delay.setRange(.1, 9.9)
        self.external_delay.setSingleStep(.1)
        self.external_delay.setDecimals(1)
        self.external_delay.setSuffix(tr('ui.00fe8dda1fd70f64'))
        self.external_delay.setValue(float(values.get('delay_seconds', .1)))
        form.addRow(tr('ui.57585c17a31bb792'), self.external_delay)
        note = QLabel(tr('ui.5ba4d8ac67fd501e'))
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        spacer = QWidget(); spacer.setFixedHeight(9); form.addRow(spacer)
        self.external_reverse = QCheckBox(tr('ui.7f83d32e5f1fd39d'))
        self.external_reverse.setChecked(bool(values.get('reversed', False)))
        form.addRow(self.external_reverse)
        reverse_note = QLabel(tr('ui.80ef022b95e55fe9'))
        reverse_note.setWordWrap(True); reverse_note.setObjectName('helpText'); form.addRow(reverse_note)
        self.tabs.addTab(tab, tr('ui.c66e3b1994a02069'))

    def _external_values(self):
        return dict(role=self.external_role.currentData(), enabled=self.external_enabled.isChecked(),
                    com_port=self.external_port.currentData() or '',
                    line=self.external_line.currentText(), reversed=self.external_reverse.isChecked(),
                    delay_seconds=self.external_delay.value())

    def _rig_changed(self, *_, initial=False):
        model = self.rig.currentData() or ''
        yaesu = model in HAMLIB_MODELS
        self.specific.setEnabled(bool(model)); self.test_button.setEnabled(bool(model))
        self.connect_button.setEnabled(bool(model))
        for widget in (self.address_label, self.civ_addr, self.address_note): widget.setVisible(not yaesu)
        for widget in (self.stopbits_label, self.stopbits): widget.setVisible(False)
        self.cat_note.setVisible(yaesu)
        from ..radio_support import LEGACY_MODE, connection_note, ICOM_EXTERNAL_PTT
        if not initial and model in LEGACY_MODE: self.auto_mode.setChecked(False)
        if not initial and not yaesu:
            addr = RIG_MODELS.get(model, 0)
            self.civ_addr.setCurrentText(f'{addr:02X}' if addr else '')
        self.ptt.clear(); self.ptt.addItems(['CAT'] if yaesu else (['外部接続'] if model in ICOM_EXTERNAL_PTT else ['CI-V', 'RTS', 'DTR', '外部接続']))
        saved = self.working['radio']
        if initial: self.ptt.setCurrentText(saved.get('ptt', 'CAT' if yaesu else 'CI-V'))
        for index in range(self.ptt.count()):
            if self.ptt.itemText(index) == '外部接続':
                self.ptt.setItemData(index, '外部接続'); self.ptt.setItemText(index, tr('ui.c66e3b1994a02069'))
        self.baud.clear(); self.baud.addItem(tr('ui.36147b7e34df7ac8'), 'AUTO')
        speeds = [115200, 38400, 19200, 9600, 4800] if yaesu else [115200, 57600, 38400, 19200, 9600, 4800]
        for speed in speeds: self.baud.addItem(str(speed), str(speed))
        self._select_data(self.baud, saved.get('cat_baud' if yaesu else 'civ_baud', 'AUTO'))
        self.baud_label.setText(tr('ui.040c990b28af8cdc') if yaesu else tr('ui.282ae772aeb81bab'))
        bits = saved.get('cat_stopbits') if initial else None
        self._select_data(self.stopbits, bits or (1 if model == 'FTX-1' else 2))
        self.port_note.setText(tr('ui.23dc07621ef4d739') if yaesu else tr('ui.7e882691990d3ed6'))
        if connection_note(model):
            self.port_note.setText(connection_note(model))
        self.port_note.setStyleSheet("color:#075aa6;" if model in ICOM_EXTERNAL_PTT else "")
        self.cat_note.setText(tr('ui.572e3f063948c095'))
        self._mode_caption()

    def _mode_caption(self, *_):
        mode = self.data_mode.currentText() if hasattr(self, 'data_mode') else self.working['advanced'].get('data_mode', 'LSB-D')
        model=self.rig.currentData()
        if model=='TS-990S':mode=('LSB-D1' if mode=='LSB-D' else 'USB-D1')
        elif model.startswith('TS-'):mode=('LSB-DATA' if mode=='LSB-D' else 'USB-DATA')
        elif model in HAMLIB_MODELS:
            mode = ('DATA-L' if mode == 'LSB-D' else 'DATA-U') if model == 'FTX-1' else ('DATA-LSB' if mode == 'LSB-D' else 'DATA-USB')
        self.auto_mode.setText(tr('ui.5a1692fc86baebf3').format(mode=mode))

    def _audio_choices(self, combo, kind, selected):
        if kind == 'input': combo.addItem(tr('ui.6213305916949e4c'), 'UNSET')
        combo.addItem(tr('ui.36147b7e34df7ac8'), 'AUTO')
        try:
            for choice, label in AudioEngine.devices(kind):
                combo.addItem(label, choice)
                if isinstance(choice, dict) and isinstance(selected, dict) and all(choice.get(k) == selected.get(k) for k in ('backend', 'id', 'kind')):
                    selected = choice
        except Exception as exc:
            self.audio_error = tr(str(exc))
        if combo.findData(selected) < 0:
            if isinstance(selected, dict):
                label = selected.get('name', '') + tr('ui.1184daf535ccfd3e')
            else:
                label = tr('ui.db352cdf32e298b2').format(selected=selected)
            combo.addItem(label, selected)
        self._select_data(combo, selected)

    def _build_audio_in_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        self.audio_in = QComboBox()
        self.audio_error = ''
        self._audio_choices(self.audio_in, 'input', self.working['audio']['input_device'])
        form.addRow("Audio IN", self.audio_in)
        n1 = QLabel(tr('ui.f64ba79915c04f8b'))
        n1.setWordWrap(True); n1.setObjectName("helpText"); form.addRow("", n1)

        self.rx_gain = QSlider(Qt.Horizontal)
        self.rx_gain.setRange(10, 300)
        self.rx_gain.setValue(int(float(self.working["audio"]["rx_gain"]) * 100))
        self.rx_label = QLabel()
        self.rx_gain.valueChanged.connect(self._rx_gain_changed)
        self.rx_label.setText(f"{self.rx_gain.value()}%")
        preset = QPushButton(tr('ui.6372d78797362875')); preset.setToolTip(tr('ui.288f092e337e724d'))
        preset.clicked.connect(lambda: self.rx_gain.setValue(50))
        row = QHBoxLayout(); row.addWidget(self.rx_gain, 1); row.addWidget(self.rx_label); row.addWidget(preset)
        form.addRow(tr('ui.e0989c705a08bff3'), row)
        self.rx_meter = QProgressBar(); self.rx_meter.setRange(0,100)
        self.rx_meter.setFormat('%v%')
        self.rx_state = QLabel(''); self.rx_state.setFixedWidth(42)
        meter_row = QHBoxLayout(); meter_row.addWidget(self.rx_meter, 1); meter_row.addWidget(self.rx_state)
        form.addRow(tr('ui.cd8dc38be5fb329b'), meter_row)
        self.rx_good = QLabel(tr('ui.a281684c744c4a90'))
        form.addRow('', self.rx_good)
        n2 = QLabel(tr('ui.f045587050bec9bd'))
        n2.setWordWrap(True); n2.setObjectName("helpText"); form.addRow("", n2)
        save_in = QPushButton(tr('ui.6e82b2bf5e205f8f')); save_in.clicked.connect(self._save_audio_in)
        form.addRow('', save_in)
        self.tabs.addTab(tab, 'Audio IN')

    def _build_audio_out_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        self.audio_out = QComboBox()
        self._audio_choices(self.audio_out, 'output', self.working['audio']['output_device'])
        form.addRow("Audio OUT", self.audio_out)
        self.audio_out_status = QLabel()
        self.audio_out_status.setWordWrap(True)
        self.audio_out_status.setStyleSheet('color: #725d49; background: transparent; border: none; padding: 0;')
        self.rebind_audio_out = QPushButton(tr('ui.3a13935e213d6a26'))
        self.rebind_audio_out.clicked.connect(self._rebind_audio_out)
        refresh = QPushButton(tr('ui.35034c60be24bfaf'))
        refresh.clicked.connect(self._refresh_audio_out_choices)
        row_device = QHBoxLayout()
        row_device.addWidget(self.rebind_audio_out)
        row_device.addWidget(refresh)
        row_device.addWidget(self.audio_out_status, 1)
        form.addRow('', row_device)
        self.audio_out.currentIndexChanged.connect(self._update_audio_out_availability)
        self._update_audio_out_availability()
        n3 = QLabel(tr('ui.09acce0bec978e52'))
        n3.setWordWrap(True); n3.setObjectName("helpText"); form.addRow("", n3)

        self.tx_gain = QSlider(Qt.Horizontal)
        self.tx_gain.setRange(1, 90)
        self.tx_gain.setValue(int(float(self.working["audio"]["tx_gain"]) * 100))
        self.tx_label = QLabel()
        self.tx_gain.valueChanged.connect(self._tx_gain_changed)
        self.tx_label.setText(f"{self.tx_gain.value()}%")
        row2 = QHBoxLayout(); row2.addWidget(self.tx_gain, 1); row2.addWidget(self.tx_label)
        form.addRow(tr('ui.4cd82636e7230603'), row2)
        n4 = QLabel(tr('ui.7baf25c906bf109b'))
        n4.setWordWrap(True); n4.setMinimumHeight(n4.fontMetrics().lineSpacing() * 6)
        n4.setObjectName("helpText"); form.addRow("", n4)
        self.alc_meter = QProgressBar(); self.alc_meter.setRange(0,120); self.alc_meter.setValue(0)
        self.alc_meter.setFormat(tr('ui.9b5652a9d2212a19'))
        form.addRow(tr('ui.e0d7761322289d68'), self.alc_meter)
        from ..alc_display import calibration_onset
        self.alc_onset=calibration_onset(self.working['audio'],self.working['radio'])
        self.alc_good = QLabel(tr('ui.1e97c80054138853'))
        form.addRow('', self.alc_good)
        self.alc_note = QLabel(tr('ui.7d3c34926543670f'))
        self.alc_note.setWordWrap(True); self.alc_note.setObjectName('helpText'); form.addRow('', self.alc_note)
        self.test_tx_button = QPushButton(tr('ui.e34d5bd94eb35240')); self.test_tx_button.setEnabled(False)
        self.test_tx_button.clicked.connect(self._toggle_test_tx)
        self.test_count_label = QLabel(tr('ui.2f3ee0fc058199a7'))
        test_row=QHBoxLayout(); test_row.addWidget(self.test_tx_button); test_row.addWidget(self.test_count_label); test_row.addStretch(1)
        form.addRow('', test_row)
        self.tx_test_note = QLabel(tr('ui.4f2331557b0415ba'))
        self.tx_test_note.setWordWrap(True); self.tx_test_note.setObjectName('helpText'); form.addRow('', self.tx_test_note)
        self.save_out_button = QPushButton(tr('ui.6e82b2bf5e205f8f')); self.save_out_button.clicked.connect(self._save_audio_out)
        form.addRow('', self.save_out_button)

        note = QLabel(self.audio_error or tr('ui.576351e2ada676f7'))
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        self.tabs.addTab(tab, 'Audio OUT')

    def _open_secondary_audio(self):
        from .secondary_audio_dialog import SecondaryAudioDialog
        if not self._confirm_primary_audio_save(): return
        try:
            primary = self._save_primary_before_secondary()
            dialog = SecondaryAudioDialog(self.working['audio'].get('secondary'),
                self._save_secondary_audio, self, primary_device=primary)
        except Exception as exc:
            QMessageBox.warning(self, tr('ui.acd8e57f9bb73955'), tr(str(exc)))
            return
        dialog.exec()

    def _confirm_primary_audio_save(self):
        box = QMessageBox(self)
        box.setWindowTitle(tr('ui.acd8e57f9bb73955'))
        box.setText(tr('ui.95d3a4734b58c555'))
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
        box.button(QMessageBox.Save).setText(tr('ui.2bd03e1cf1453880'))
        box.button(QMessageBox.Cancel).setText(tr('ui.bca84ea5c65fee0e'))
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Save

    def _save_primary_before_secondary(self):
        parent = self.parent()
        if self.tx_testing or (parent and parent.audio._tx_active):
            raise ValueError(tr('ui.f4cdea9046ecf0ce'))
        if [item['name'] for item in self.working_profiles] != [item['name'] for item in self.store.data['profiles']]:
            raise ValueError(tr('ui.4addcf30bcab9b5d'))
        values = dict(output_device=deepcopy(self.audio_out.currentData() or 'AUTO'), tx_gain=self.tx_gain.value()/100)
        old = deepcopy(self.store.data)
        try:
            self.store.data['profiles'][self.profile_index]['audio'].update(deepcopy(values))
            if self.profile_index == self.store.data['active_profile']:
                self.store.data['audio'].update(deepcopy(values))
            self.store.save()
        except Exception:
            self.store.data = old
            raise
        self.working['audio'].update(deepcopy(values))
        self.working_profiles[self.profile_index]['audio'].update(deepcopy(values))
        if parent and self.profile_index == self.store.data['active_profile']:
            parent.audio.set_tx_gain(values['tx_gain'])
        return values['output_device']

    def _save_secondary_audio(self, values):
        from ..secondary_audio import normalize_settings
        parent = self.parent()
        if self.tx_testing or (parent and parent.audio._tx_active):
            raise ValueError(tr('ui.f4cdea9046ecf0ce'))
        if [item['name'] for item in self.working_profiles] != [item['name'] for item in self.store.data['profiles']]:
            raise ValueError(tr('ui.4addcf30bcab9b5d'))
        values = normalize_settings(values)
        if values['enabled'] and values['device'] == self.audio_out.currentData():
            raise ValueError(tr('ui.09337e8c26ad0762'))
        old = deepcopy(self.store.data)
        try:
            self.store.data['profiles'][self.profile_index]['audio']['secondary'] = deepcopy(values)
            if self.profile_index == self.store.data['active_profile']:
                self.store.data['audio']['secondary'] = deepcopy(values)
            self.store.save()
        except Exception:
            self.store.data = old
            raise
        self.working['audio']['secondary'] = deepcopy(values)
        self.working_profiles[self.profile_index]['audio']['secondary'] = deepcopy(values)
        if parent and self.profile_index == self.store.data['active_profile']:
            parent.audio.configure_secondary(values)
            parent.audio.secondary_notice = ''

    def _build_advanced_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        warning = QLabel(tr('ui.554478281f77814e'))
        warning.setWordWrap(True); warning.setObjectName("helpText")
        root.addWidget(warning)
        form = QFormLayout(); root.addLayout(form)

        adv = self.working["advanced"]
        self.rtty_baud = QDoubleSpinBox(); self.rtty_baud.setRange(30, 300); self.rtty_baud.setDecimals(2); self.rtty_baud.setValue(float(adv["rtty_baud"])); self.rtty_baud.setSuffix(" baud")
        self.shift = QSpinBox(); self.shift.setRange(50, 1000); self.shift.setValue(int(adv["shift_hz"])); self.shift.setSuffix(" Hz")
        self.mark = QSpinBox(); self.mark.setRange(300, 3500); self.mark.setValue(int(adv["mark_hz"])); self.mark.setSuffix(" Hz")
        self.space = QSpinBox(); self.space.setRange(300, 3500); self.space.setValue(int(adv["space_hz"])); self.space.setSuffix(" Hz")
        self.invert = QCheckBox(tr('ui.cbbd64975fc85d89')); self.invert.setChecked(bool(adv["invert"]))
        self.spec_width = QComboBox()
        for v in (500, 1000, 2000, 3000): self.spec_width.addItem(f"{v if v<1000 else v//1000 if v%1000==0 else v/1000} {'Hz' if v<1000 else 'kHz'}", v)
        self._select_data(self.spec_width, int(adv["spectrum_width_hz"]))
        self.tune_tol = QSpinBox(); self.tune_tol.setRange(20, 250); self.tune_tol.setValue(int(adv["auto_tune_tolerance_hz"])); self.tune_tol.setSuffix(" Hz")

        self.data_mode = QComboBox(); self.data_mode.addItems(["LSB-D", "USB-D"])
        self.data_mode.setCurrentText(adv.get("data_mode", "LSB-D"))
        self.data_mode.currentTextChanged.connect(self._mode_caption)
        self._mode_caption()
        form.addRow(tr('ui.a0a3d4182392ee0e'), self.data_mode)
        form.addRow(tr('ui.50022e97e35f13db'), self.rtty_baud)
        form.addRow("Shift", self.shift)
        form.addRow("Mark", self.mark)
        form.addRow("Space", self.space)
        form.addRow(tr('ui.1f4b4a7dd5e867a6'), self.invert)
        form.addRow(tr('ui.b4810bd0256c51ef'), self.spec_width)
        form.addRow(tr('ui.c747e4873d78574c'), self.tune_tol)

        def shift_changed(v):
            self.space.blockSignals(True); self.space.setValue(self.mark.value() + v); self.space.blockSignals(False)
        self.shift.valueChanged.connect(shift_changed)
        self.mark.valueChanged.connect(lambda v: shift_changed(self.shift.value()))
        self.space.valueChanged.connect(lambda v: self.shift.setValue(abs(v - self.mark.value())))

        reset = QPushButton(tr('ui.01956a753c3d1f99'))
        reset.clicked.connect(self._reset_advanced)
        root.addWidget(reset)
        root.addStretch(1)
        self.tabs.addTab(tab, tr('ui.9652fd780df9e978'))

    @staticmethod
    def _select_data(combo: QComboBox, value):
        idx = combo.findData(value)
        if idx < 0:
            idx = combo.findData(str(value))
        if idx >= 0: combo.setCurrentIndex(idx)

    def _reset_advanced(self):
        d = DEFAULT_CONFIG["advanced"]
        self.data_mode.setCurrentText(d["data_mode"])
        self.rtty_baud.setValue(d["rtty_baud"]); self.shift.setValue(d["shift_hz"])
        self.mark.setValue(d["mark_hz"]); self.space.setValue(d["space_hz"])
        self.invert.setChecked(d["invert"]); self._select_data(self.spec_width, d["spectrum_width_hz"])
        self.tune_tol.setValue(d["auto_tune_tolerance_hz"])

    def _radio_values(self):
        values = dict(self.working['radio'])
        yaesu = self.rig.currentData() in HAMLIB_MODELS
        values.update(model=self.rig.currentData() or '', civ_address=self.civ_addr.currentText().strip().upper(),
                      com_port=self.com.currentData() or 'AUTO', ptt=self.ptt.currentData() or self.ptt.currentText(),
                      auto_data_mode=self.auto_mode.isChecked())
        values['cat_baud' if yaesu else 'civ_baud'] = self.baud.currentData() or 'AUTO'
        if yaesu: values['cat_stopbits'] = self.stopbits.currentData()
        return values

    def _test_controls_changed(self, *_):
        if not self.tx_testing and self.verified_values != self._radio_values():
            self.test_tx_button.setEnabled(False)
            if self.verified_values:
                self.tx_test_note.setText(tr('ui.1917f6d1076ed413'))

    def _adopt_main_connection(self):
        parent=self.parent()
        if (parent is None or not hasattr(parent,'_connected') or not parent._connected()
            or self._radio_values()!=parent.store.data['radio']):
            return False
        if self.test_controller and not self.test_uses_main:
            self._release_test_controller()
        self.test_controller=parent.radio
        self.test_uses_main=True
        self.verified_values=self._radio_values()
        self.test_tx_button.setEnabled(True)
        self.test_note.setText(tr('ui.fe6aa465e8d7f98f'))
        return True

    def _rx_gain_changed(self, value):
        self.rx_label.setText(f'{value}%')
        parent = self.parent()
        if self.profile_index == self.store.data['active_profile'] and parent and hasattr(parent, 'audio'):
            parent.audio.set_rx_gain(value/100)

    def _tx_gain_changed(self, value):
        self.tx_label.setText(f'{value}%')
        parent = self.parent()
        if self.profile_index == self.store.data['active_profile'] and parent and hasattr(parent, 'audio'):
            parent.audio.set_tx_gain(value/100)
        if self.tx_testing: self._show_alc(self.alc_value)

    def _refresh_rx_meter(self):
        parent = self.parent()
        value = parent.level.value() if parent and hasattr(parent, 'level') else 0
        if parent and (parent.active_tx_id is not None or parent.audio._tx_active):
            value=round(parent.rx_display.percent)
        self.rx_meter.setValue(value)
        from ..rx_level import level_band, LABELS, COLORS, TEXT_COLORS
        display=getattr(parent, 'rx_display', None)
        band=display.band if display is not None else level_band(value)
        self.rx_meter.setStyleSheet(f'QProgressBar::chunk {{ background: {COLORS[band]}; }}')
        self.rx_meter.setFormat(f'{value}%')
        self.rx_state.setText(LABELS[band])
        self.rx_state.setStyleSheet(f'color: {TEXT_COLORS[band]}; font-weight: bold;')
        self.rx_state.setToolTip(tr('ui.ab87f3c2cbea0e9a'))

    def _save_audio_in(self):
        parent=self.parent()
        if self.profile_index != self.store.data['active_profile']:
            self.test_note.setText(tr('ui.5b9b2e8703cdd590'))
            return
        old=self.store.data['audio']['input_device']
        self.store.data['audio'].update(input_device=self.audio_in.currentData() or 'AUTO', rx_gain=self.rx_gain.value()/100)
        self.working['audio'].update(self.store.data['audio'])
        self.store.save()
        if parent and old != self.store.data['audio']['input_device']: parent._restart_audio_input()
        self.test_note.setText(tr('ui.65004674ef6f3b17'))

    def _save_audio_out(self):
        if self.profile_index != self.store.data['active_profile']:
            self.tx_test_note.setText(tr('ui.5b9b2e8703cdd590'))
            return
        if self.tx_testing or self.parent().audio._tx_active:
            self.tx_test_note.setText(tr('ui.f4cdea9046ecf0ce')); return
        if 'alc_calibration' in self.working['audio']:
            self.store.data['audio']['alc_calibration']=deepcopy(self.working['audio']['alc_calibration'])
        self.store.data['audio'].update(output_device=self.audio_out.currentData() or 'AUTO', tx_gain=self.tx_gain.value()/100)
        self.working['audio'].update(self.store.data['audio'])
        self.store.save()
        self.tx_test_note.setText(tr('ui.66fc26834d7a8509'))

    def _refresh_audio_out_choices(self):
        selected = self.audio_out.currentData()
        self.audio_out.blockSignals(True)
        self.audio_out.clear()
        self._audio_choices(self.audio_out, 'output', selected)
        self.audio_out.blockSignals(False)
        self._update_audio_out_availability()

    def _matching_audio_out(self):
        selected = self.audio_out.currentData()
        if not isinstance(selected, dict) or tr('ui.fd07aab3e60ac251') not in self.audio_out.currentText():
            return []
        return [index for index in range(self.audio_out.count())
                if isinstance(self.audio_out.itemData(index), dict)
                and self.audio_out.itemData(index).get('name') == selected.get('name')
                and self.audio_out.itemData(index).get('kind') == 'output'
                and self.audio_out.itemData(index).get('backend') == selected.get('backend')
                and self.audio_out.itemData(index).get('id') != selected.get('id')]

    def _update_audio_out_availability(self, *_):
        stale = tr('ui.fd07aab3e60ac251') in self.audio_out.currentText()
        matches = self._matching_audio_out() if stale else []
        self.rebind_audio_out.setVisible(len(matches) == 1)
        self.audio_out_status.setVisible(stale)
        if stale:
            self.audio_out_status.setText(tr('ui.aa672587f14fb7f2')
                + (tr('ui.fbecbb2692fe4ba9') if len(matches) == 1 else
                   tr('ui.9b93f629e40c1b41')))
        else:
            self.audio_out_status.setText('')

    def _rebind_audio_out(self):
        matches = self._matching_audio_out()
        if len(matches) == 1:
            self.audio_out.setCurrentIndex(matches[0])
            self.tx_test_note.setText(tr('ui.e8acf2e95aa01f7f'))

    def _show_alc(self, value):
        self.alc_value=value
        if value is None:
            self.alc_meter.setValue(0); self.alc_meter.setFormat(tr('ui.08acbe39bbb1062d'))
            self.alc_good.setText(tr('ui.8b44eb7116cf4984'))
            self.alc_good.setStyleSheet('color: #765d44;')
            self.alc_note.setText(tr('ui.8b3d01bf8a09cae0'))
            self.alc_meter.setStyleSheet('')
            return
        self.alc_meter.setValue(min(120,value))
        self.alc_meter.setFormat(f'ALC {value} / 120')
        gain=self.tx_gain.value()
        from ..alc_display import classify
        good, color = classify(value,gain,self.alc_onset)
        self.alc_good.setText(tr('ui.7fcb53e00458f9a5') if good else tr('ui.581dce38e3ecb48f'))
        self.alc_good.setStyleSheet('background: #208341; color: white; padding: 4px; font-weight: bold;' if good else 'color: #765d44;')

        self.alc_meter.setStyleSheet(f'QProgressBar::chunk {{ background: {color}; }}; QProgressBar {{ border: 2px solid {color}; }}')
        self.alc_note.setText(tr('ui.b0616e27bddaf033') if good else
                              tr('ui.8b75f49df672a1a5'))

    def _toggle_test_tx(self):
        if self.tx_testing:
            self._stop_test_tx(); return
        parent=self.parent()
        if (not self.test_controller or not self.test_controller.status.connected or
            self.verified_values != self._radio_values() or
            (parent._connected() and not self.test_uses_main) or
            (self.test_uses_main and (not parent._connected() or parent.radio is not self.test_controller)) or
            parent.antenna_tuning or parent.auto_cq_active or
            parent.audio._tx_active):
            self.test_tx_button.setEnabled(False)
            self.tx_test_note.setText(tr('ui.15cf5f8c1e1471fc')); return
        ctl=self.test_controller
        mode=self.verified_values['ptt']
        ptt={'CI-V':ctl.set_ptt,'CAT':ctl.set_ptt,'RTS':ctl.set_rts,'DTR':ctl.set_dtr}.get(mode)
        if not ptt and mode != '外部接続':

            self.tx_test_note.setText(tr('ui.3013aa78f5fcae4d')); return
        adv=self.working['advanced']
        # RY alternation exercises both mark and space. The worker is cut off at 10 s.
        text='RY ' * 70
        try:
            sequencer=ExternalPTT(self._external_values(), ctl.status.port, parent.audio._tx_cancel)
        except ValueError as exc:
            self.tx_test_note.setText(tr(str(exc))); return
        from ..tx_keying import keying_callbacks
        try:
            on, off = keying_callbacks(ctl, mode, sequencer,
                lambda: self.test_controller is ctl and ctl.status.connected)
        except ValueError as exc:
            self.tx_test_note.setText(tr(str(exc))); return
        ok,msg=parent.audio.send_text(text,self.audio_out.currentData(),adv['rtty_baud'],
            adv['mark_hz'],adv['space_hz'],adv['invert'],self.tx_gain.value()/100,
            on, off, lambda success,note:self.tx_test_finished.emit(success,note))
        if not ok:
            self.tx_test_note.setText(msg); return
        self.tx_testing=True; self.test_deadline=time.monotonic()+10
        self.test_tx_button.setText(tr('ui.aa5a54ec36936dd5'))
        self.test_count_label.setText(tr('ui.59c8551120be3c6c'))
        self.save_out_button.setEnabled(False)
        self.tx_test_note.setText(tr('ui.3dd8bb2ff31785ed'))
        self.countdown.start()

    def _tick_test_tx(self):
        remaining=max(0,self.test_deadline-time.monotonic())
        self.test_count_label.setText(f"{tr('ui.f79606416528fb2b')}{int(remaining + 0.999)}{tr('ui.9dcdc2b289b9d233')}" if remaining else tr('ui.02099d7931da52b4'))
        if remaining <= 0:
            self._stop_test_tx(); return
        if self.alc_busy or not self.test_controller or not hasattr(self.test_controller,'read_alc'): return
        ctl=self.test_controller
        self.alc_busy=True
        def done(value,error):
            self.alc_busy=False
            if ctl is not self.test_controller or not self.tx_testing: return
            if error: value=None
            if value is not None and value >= 2 and self.alc_onset is None:
                self.alc_onset=self.tx_gain.value()
                from ..alc_display import signature
                self.working['audio']['alc_calibration']={'onset':self.alc_onset,'signature':signature(self._radio_values(),self.audio_out.currentData())}
            self._show_alc(value)
        self.alc_job=BackgroundJob(self,ctl.read_alc,done)

    def _stop_test_tx(self):
        if not self.tx_testing: return
        self.countdown.stop()
        self.test_count_label.setText(tr('ui.02099d7931da52b4'))
        self.parent().audio.stop_tx()

    def _test_tx_finished(self, success, message):
        self.tx_testing=False; self.countdown.stop()
        self.test_tx_button.setText(tr('ui.e34d5bd94eb35240'))
        self.test_count_label.setText(tr('ui.ca4d973c0b006b75'))
        self.save_out_button.setEnabled(True)
        self.alc_meter.setValue(0); self.alc_meter.setFormat(tr('ui.07534165f419d0c6'))
        self.alc_good.setText(tr('ui.6dfd71243d7c36d2'));self.alc_good.setStyleSheet('color: #765d44;')
        self.tx_test_note.setText(tr('ui.087d32aadb80dca2') if success or message==tr('ui.63e1879b6cfd6a0e') else message)
        if not self.isVisible(): self._release_test_controller()

    def _release_test_controller(self):
        self.test_connection_generation += 1
        self.test_pending = False
        ctl,self.test_controller=self.test_controller,None
        borrowed=self.test_uses_main
        self.test_uses_main=False
        self.verified_values=None
        if ctl and not borrowed:
            ctl.cancel.set()
            # If TX is still unwinding, its completion callback owns PTT release.
            parent=self.parent()
            if not parent or not hasattr(parent,'audio') or not parent.audio._tx_active: ctl.disconnect()

    def _test_radio(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, '_connected') and (parent._connected() or parent.connecting):
            if not self._adopt_main_connection():
                self.test_note.setText(tr('ui.4102ec0494913a11'))
            return
        if self.tx_testing: return
        if self.test_controller:
            self._release_test_controller()
        values = self._radio_values()
        try:
            ctl = create_controller(values)
        except ValueError as exc:
            QMessageBox.warning(self, tr('ui.3ee76ae7045f1ff8'), tr(str(exc))); return
        self.test_controller = ctl
        self.test_uses_main = False
        self.test_pending = True
        self.test_timed_out = False
        self.verified_values = None
        self.alc_onset = None
        self._show_alc(None)
        self.test_tx_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.test_note.setText(tr('ui.c1083127083f08e6'))
        advanced = dict(data_mode=self.data_mode.currentText())
        self.test_button.setEnabled(False); self.test_button.setText(tr('ui.c1083127083f08e6'))
        def work():
            return connect_configured(ctl, values, advanced)
        self.test_job = BackgroundJob(self, work, lambda st, err: self._test_done(st, err, values) if self.test_controller is ctl else None)
        def deadline():
            if self.test_controller is ctl and self.test_pending:
                self.test_timed_out = True
                ctl.cancel.set()
                self.test_note.setText(tr('ui.d4e6b390bdb33e67'))
                if self.isVisible():
                    QMessageBox.warning(self, tr('ui.3ee76ae7045f1ff8'), tr('ui.86d2eac7a8dea68a'))
        QTimer.singleShot(10000, self, deadline)

    def _test_done(self, status, error, values):
        timed_out = self.test_timed_out
        self.test_pending = False
        failed = timed_out or error or not status or not status.connected
        if failed:
            self._release_test_controller()
        else:
            self.verified_values=values
            self.test_tx_button.setEnabled(True)
        self.connect_button.setEnabled(bool(self.rig.currentData()))
        self.test_note.setText(tr('ui.c65cb3ae8835c7ef') if failed else tr('ui.65af76f90e2a2ada'))
        self.test_button.setEnabled(True); self.test_button.setText(tr('ui.3ee76ae7045f1ff8'))
        if not self.isVisible():
            return
        if timed_out:
            return
        if failed:
            QMessageBox.warning(self, tr('ui.3ee76ae7045f1ff8'), tr(str(error)) if error else tr(status.message) if status else tr('ui.382bfcb90044d03c'))
        else:
            QMessageBox.information(self, tr('ui.3ee76ae7045f1ff8'), tr('ui.0a9d893efceea360').format(port=status.port, baud=status.baud, frequency=status.frequency_hz))
            if self.test_controller and not self.test_uses_main:
                self.test_connection_generation += 1
                generation=self.test_connection_generation
                QTimer.singleShot(10000, self, lambda: self._expire_test_connection(generation))

    def _expire_test_connection(self, generation):
        if generation != self.test_connection_generation or not self.test_controller or self.test_uses_main:return
        if self.tx_testing:
            QTimer.singleShot(200, self, lambda: self._expire_test_connection(generation))
            return
        self._release_test_controller()
        self.test_tx_button.setEnabled(False)
        self.test_note.setText(tr('ui.6b3c79a9a83a317f'))

    def done(self, result):
        self.level_timer.stop()
        if self.tx_testing:
            self._stop_test_tx()
        else:
            self._release_test_controller()
        parent=self.parent()
        if parent and hasattr(parent,'audio'):
            parent.audio.set_rx_gain(self.store.data['audio']['rx_gain'])
            parent.audio.set_tx_gain(self.store.data['audio']['tx_gain'])
        super().done(result)

    def basic_call_changed(self):
        return self.my_call.text() != self.working.get('station_callsign', '')

    def _connect_saved(self):
        if self.tx_testing or self.profile_index != self.store.data['active_profile']: return
        self._release_test_controller()
        self.connect_requested = True
        self._save()
        if self.result() != QDialog.Accepted: self.connect_requested = False

    def _save(self):
        if self.tx_testing or (self.test_controller and not self.verified_values):
            self.test_note.setText(tr('ui.396888a93624ff49'))
            return
        self._release_test_controller()
        values = self._radio_values()
        try:
            if values["model"]:
                validate_radio(values)
        except ValueError as exc:
            QMessageBox.warning(self, tr('ui.0d8619aae051ae34'), tr(str(exc))); return
        try:
            validate_external(self._external_values(), values['com_port'])
            external=self._external_values()
            if values['ptt'] == '外部接続' and (not external['enabled'] or external['role'] != 'ptt'):
                raise ValueError(tr('ui.3e8772d73f01525a'))
        except ValueError as exc:
            QMessageBox.warning(self, tr('ui.c66e3b1994a02069'), tr(str(exc))); return
        call_edited = self.basic_call_changed()
        if not self._capture_profile(): return
        self.before_save.emit()
        active = self.active_profile_index
        # Keep edits made to the main-window callsign while this dialog was open.
        if active == self.profile_index and not call_edited and self.parent() and hasattr(self.parent(), 'my_call'):
            from ..parser import normalize_call
            self.working_profiles[active]['station_callsign'] = normalize_call(self.parent().my_call.text())
        elif active != self.profile_index:
            self.working_profiles[active]['station_callsign'] = self.store.data['station_callsign']
        self.store.data['profiles'] = self.working_profiles
        self.store.data['active_profile'] = active
        for key in PROFILE_KEYS:
            self.store.data[key] = deepcopy(self.working_profiles[active][key])
        self.store.save()
        self.accept()
