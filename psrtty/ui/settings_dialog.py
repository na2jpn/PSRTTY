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
        self.setWindowTitle(tr("PSRTTY 設定"))
        self.resize(660, 600)

        root = QVBoxLayout(self)
        intro = QLabel(
            tr("使用するCOMポート・音声デバイスを選択してください。\n"
            "ICOMはCI-V、Yaesu・Kenwood機種はHamlibで制御します。")
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
        add_profile = QPushButton(tr('＋ Profile追加'))
        add_profile.setMinimumHeight(28)
        add_profile.clicked.connect(self._add_profile)
        self.profile_tabs.setCornerWidget(add_profile, Qt.TopRightCorner)
        self._rebuild_inner_tabs()
        self.profile_tabs.currentChanged.connect(self._profile_changed)
        self.profile_tabs.currentChanged.connect(self._update_profile_tab_colors)
        self._update_profile_tab_colors()

        actions = QHBoxLayout()
        self.delete_profile_button = QPushButton(tr('このProfileを削除'))
        self.delete_profile_button.clicked.connect(self._delete_profile)
        actions.addWidget(self.delete_profile_button)
        actions.addStretch(1)
        self.secondary_button = QPushButton(tr('第二AudioOUTの設定'))
        self.secondary_button.clicked.connect(self._open_secondary_audio)
        self.secondary_button.hide()
        actions.addWidget(self.secondary_button)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText(tr("保存"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("キャンセル"))
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
        form.addRow(tr('プロファイル名（英数字・-/、10文字以内）'), self.profile_name_edit)
        self.my_call = QLineEdit(self.working.get('station_callsign', ''))
        self.my_call.setPlaceholderText(tr('例: JX1XXX'))
        station = self.working['station']
        self.my_qth = QLineEdit(station['qth'])
        self.my_qth.setPlaceholderText(tr('送信用の地名（英字）'))
        self.my_jcc_jcg = QLineEdit(station['jcc_jcg'])
        self.my_jcc_jcg.setPlaceholderText(tr('JCC/JCGコード'))
        self.my_text = QPlainTextEdit(station['text'])
        self.my_text.setPlaceholderText(tr('名前・設備紹介など、追加で送る英文を自由入力'))
        form.addRow(tr('自局コールサイン {MYCALL}'), self.my_call)
        form.addRow(tr('自局運用場所 {MYQTH}'), self.my_qth)
        form.addRow('JCC/JCG {MYJCCJCG}', self.my_jcc_jcg)
        form.addRow(tr('追加送信文 {MYTXT}'), self.my_text)
        note = QLabel(tr('自局コールサインはメイン画面と共用です。Saveで反映します。\n通常交信では QTH {MYQTH} {MYJCCJCG} の順に送ります。\n追加送信文は複数行・空欄も使用できます。送信文は英数字で入力してください。'))
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        self.tabs.addTab(tab, tr('基本設定'))

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
            self.connect_button.setToolTip(tr('運用するプロファイルはメイン画面で切り替えてください。'))

    def _capture_profile(self):
        name = profile_name(self.profile_name_edit.text().strip())
        if not name:
            QMessageBox.warning(self, tr('プロファイル名'), tr('英数字と - / を10文字以内で入力してください。'))
            return False
        if any(i != self.profile_index and p['name'].lower() == name.lower()
               for i, p in enumerate(self.working_profiles)):
            QMessageBox.warning(self, tr('プロファイル名'), tr('同じ名前のプロファイルがあります。'))
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
            QMessageBox.information(self, tr('プロファイル'), tr('最大6件です。')); return
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
            QMessageBox.information(self, tr('Profile削除'), tr('先頭のProfileは基準となるため削除できません。'))
            return
        if index == self.active_profile_index:
            QMessageBox.information(self, tr('Profile削除'), tr('使用中です。先にメイン画面で別のProfileへ切り替えてください。'))
            return
        if self.tx_testing or self.test_pending:
            QMessageBox.information(self, tr('Profile削除'), tr('接続テスト・送信テストの終了を待ってください。'))
            return
        name = self.working_profiles[index]['name']
        if QMessageBox.question(self, tr('Profile削除'), tr('{name} を削除しますか？\n保存すると削除が確定します。').format(name=name)) != QMessageBox.Yes:
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
        self.rig = QComboBox(); self.rig.addItem(tr('選択してください'), '')
        for model in RIG_MODELS: self.rig.addItem(tr(model), model)
        for model, (_,label) in HAMLIB_MODELS.items(): self.rig.addItem(label, model)
        self._select_data(self.rig, self.working['radio']['model'])
        form.addRow(tr('無線機'), self.rig)
        self.com = QComboBox(); self.com.addItem(tr('自動'), 'AUTO')
        for port, name in CIVController.port_choices(): self.com.addItem(name, port)
        target = self.working['radio']['com_port']
        if self.com.findData(target) < 0:
            self.com.addItem(f"{target}{tr('（未接続）')}", target)
        self._select_data(self.com, target)
        form.addRow(tr('COMポート'), self.com)
        self.port_note = QLabel(); self.port_note.setWordWrap(True); self.port_note.setObjectName('helpText')
        form.addRow('', self.port_note)
        self.specific = QGroupBox(tr('無線機固有の設定'))
        self.specific_form = f = QFormLayout(self.specific)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.civ_addr = QComboBox(); self.civ_addr.setEditable(True)
        self.civ_addr.addItems([f'{v:02X}' for v in sorted(set(RIG_MODELS.values())) if v])
        self.civ_addr.setCurrentText(self.working['radio']['civ_address'])
        self.address_label = QLabel(tr('CI-Vアドレス')); f.addRow(self.address_label, self.civ_addr)
        self.address_note = QLabel(tr('機種選択時に標準値を入力します。無線機側で変更した場合は手修正できます。'))
        self.address_note.setWordWrap(True); self.address_note.setObjectName('helpText'); f.addRow(self.address_note)
        self.ptt = QComboBox(); f.addRow(tr('PTT方式'), self.ptt)
        self.baud = QComboBox(); self.baud_label = QLabel(); f.addRow(self.baud_label, self.baud)
        self.stopbits = QComboBox(); self.stopbits.addItem('1', 1); self.stopbits.addItem('2', 2)
        self.stopbits_label = QLabel(tr('ストップビット')); f.addRow(self.stopbits_label, self.stopbits)
        self.auto_mode = QCheckBox(); self.auto_mode.setChecked(self.working['radio'].get('auto_data_mode', True))
        f.addRow(self.auto_mode)
        self.cat_note = QLabel(tr('Hamlibを使用します。COMポートとCAT速度を指定して接続テストしてください。'
                               '無線機のDATA入力はUSBに設定します。ALCを取得できない場合は無線機本体で確認してください。'))
        self.cat_note.setWordWrap(True); self.cat_note.setObjectName('helpText'); f.addRow(self.cat_note)
        form.addRow(self.specific)
        self.test_button = QPushButton(tr('接続テスト')); self.test_button.clicked.connect(self._test_radio)
        form.addRow('', self.test_button)
        self.test_note = QLabel(); self.test_note.setWordWrap(True); form.addRow(self.test_note)
        self.connect_button = QPushButton(tr("接続"))
        self.connect_button.clicked.connect(self._connect_saved)
        form.addRow("", self.connect_button)
        self.rig.currentIndexChanged.connect(self._rig_changed)
        self._rig_changed(initial=True)
        self.tabs.addTab(tab, tr('無線機'))

    def _build_external_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        values = self.working['external']
        self.external_enabled = QCheckBox(tr('外部機器の先行切替を有効にする'))
        self.external_enabled.setChecked(bool(values['enabled']))
        form.addRow(self.external_enabled)
        self.external_port = QComboBox()
        self.external_port.addItem(tr('選択してください'), '')
        for port, label in CIVController.port_choices():
            self.external_port.addItem(label, port)
        selected = values.get('com_port', '')
        if selected and self.external_port.findData(selected) < 0:
            self.external_port.addItem(f"{selected}{tr('（未接続）')}", selected)
        self._select_data(self.external_port, selected)
        form.addRow(tr('外部機器のCOMポート'), self.external_port)
        self.external_line = QComboBox()
        self.external_line.addItems(['RTS', 'DTR'])
        self.external_line.setCurrentText(values.get('line', 'RTS'))
        form.addRow(tr('制御線'), self.external_line)
        self.external_delay = QDoubleSpinBox()
        self.external_delay.setRange(.1, 9.9)
        self.external_delay.setSingleStep(.1)
        self.external_delay.setDecimals(1)
        self.external_delay.setSuffix(tr(' 秒'))
        self.external_delay.setValue(float(values.get('delay_seconds', .1)))
        form.addRow(tr('PTTより先に切り替える時間'), self.external_delay)
        note = QLabel(tr('送信時、指定COMのRTSまたはDTRを切り替えてから設定秒数後に無線機のPTTをONにします。'
                      '終了時は先にPTTをOFFにしてから外部制御線を戻します。'
                      '無線機のCATとは別のCOMポートが必要です。接続した機器の極性と配線を確認してください。'))
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        spacer = QWidget(); spacer.setFixedHeight(9); form.addRow(spacer)
        self.external_reverse = QCheckBox(tr('動作を反転する'))
        self.external_reverse.setChecked(bool(values.get('reversed', False)))
        form.addRow(self.external_reverse)
        reverse_note = QLabel(tr('送信開始前に外部機器を切り替え、送信終了後に元へ戻します。'
                              '接続先が逆に動く場合だけ「動作を反転する」を選んでください。'))
        reverse_note.setWordWrap(True); reverse_note.setObjectName('helpText'); form.addRow(reverse_note)
        self.tabs.addTab(tab, tr('外部接続'))

    def _external_values(self):
        return dict(enabled=self.external_enabled.isChecked(),
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
        if not initial and not yaesu:
            addr = RIG_MODELS.get(model, 0)
            self.civ_addr.setCurrentText(f'{addr:02X}' if addr else '')
        self.ptt.clear(); self.ptt.addItems(['CAT'] if yaesu else ['CI-V', 'RTS', 'DTR'])
        saved = self.working['radio']
        if initial: self.ptt.setCurrentText(saved.get('ptt', 'CAT' if yaesu else 'CI-V'))
        self.baud.clear(); self.baud.addItem(tr('自動'), 'AUTO')
        speeds = [115200, 38400, 19200, 9600, 4800] if yaesu else [115200, 57600, 38400, 19200, 9600, 4800]
        for speed in speeds: self.baud.addItem(str(speed), str(speed))
        self._select_data(self.baud, saved.get('cat_baud' if yaesu else 'civ_baud', 'AUTO'))
        self.baud_label.setText(tr('CAT速度') if yaesu else tr('CI-V速度'))
        bits = saved.get('cat_stopbits') if initial else None
        self._select_data(self.stopbits, bits or (1 if model == 'FTX-1' else 2))
        self.port_note.setText(tr('Hamlib制御はCOMポートとCAT速度を指定してください。YaesuのUSB接続ではEnhanced COMが一般的です。') if yaesu else tr('通常は「自動」でCI-V応答を確認して接続します。複数の無線機を使用する場合は、接続先のCOMポートを指定してください。'))
        self._mode_caption()

    def _mode_caption(self, *_):
        mode = self.data_mode.currentText() if hasattr(self, 'data_mode') else self.working['advanced'].get('data_mode', 'LSB-D')
        model=self.rig.currentData()
        if model=='TS-990S':mode=('LSB-D1' if mode=='LSB-D' else 'USB-D1')
        elif model.startswith('TS-'):mode=('LSB-DATA' if mode=='LSB-D' else 'USB-DATA')
        elif model in HAMLIB_MODELS:
            mode = ('DATA-L' if mode == 'LSB-D' else 'DATA-U') if model == 'FTX-1' else ('DATA-LSB' if mode == 'LSB-D' else 'DATA-USB')
        self.auto_mode.setText(tr('接続時に {mode} へ自動切替').format(mode=mode))

    def _audio_choices(self, combo, kind, selected):
        if kind == 'input': combo.addItem(tr('未設定'), 'UNSET')
        combo.addItem(tr('自動'), 'AUTO')
        try:
            for choice, label in AudioEngine.devices(kind):
                combo.addItem(label, choice)
                if isinstance(choice, dict) and isinstance(selected, dict) and all(choice.get(k) == selected.get(k) for k in ('backend', 'id', 'kind')):
                    selected = choice
        except Exception as exc:
            self.audio_error = str(exc)
        if combo.findData(selected) < 0:
            if isinstance(selected, dict):
                label = selected.get('name', '') + tr('（未接続／無効）')
            else:
                label = tr('旧設定 [{selected}]（選び直してください）').format(selected=selected)
            combo.addItem(label, selected)
        self._select_data(combo, selected)

    def _build_audio_in_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        self.audio_in = QComboBox()
        self.audio_error = ''
        self._audio_choices(self.audio_in, 'input', self.working['audio']['input_device'])
        form.addRow("Audio IN", self.audio_in)
        n1 = QLabel(tr("受信用：無線機 → パソコン\n未設定では入力しません。設定済みなら無線機未接続でも入力します。\n受信音が入る録音デバイス（USB Audio／LINE IN／マイク入力など）を選んでください。"))
        n1.setWordWrap(True); n1.setObjectName("helpText"); form.addRow("", n1)

        self.rx_gain = QSlider(Qt.Horizontal)
        self.rx_gain.setRange(10, 300)
        self.rx_gain.setValue(int(float(self.working["audio"]["rx_gain"]) * 100))
        self.rx_label = QLabel()
        self.rx_gain.valueChanged.connect(self._rx_gain_changed)
        self.rx_label.setText(f"{self.rx_gain.value()}%")
        preset = QPushButton(tr('暫定50%')); preset.setToolTip(tr('受信音を聞く前の仮設定です。実際の信号を受信してから再調整してください。'))
        preset.clicked.connect(lambda: self.rx_gain.setValue(50))
        row = QHBoxLayout(); row.addWidget(self.rx_gain, 1); row.addWidget(self.rx_label); row.addWidget(preset)
        form.addRow(tr("受信レベル"), row)
        self.rx_meter = QProgressBar(); self.rx_meter.setRange(0,100)
        self.rx_meter.setFormat(tr('%v%　音声レベルの目安'))
        form.addRow(tr('RXメーター'), self.rx_meter)
        self.rx_good = QLabel(tr('青：Good（40～70%）／音が小さいか無信号なら灰色／強すぎる音は注意色'))
        form.addRow('', self.rx_good)
        n2 = QLabel(tr('受信音を聞く前は暫定50%を使用できます。RTTY信号を受信できたら、RXメーターが青いGoodの範囲に入るよう再調整してください。Goodは音声レベルの目安で、復調成功を保証しません。無信号・弱い信号は音量だけでは区別できないため、低い表示を設定不良と判定しません。受信文字も確認してください。'))
        n2.setWordWrap(True); n2.setObjectName("helpText"); form.addRow("", n2)
        save_in = QPushButton(tr('音量設定を保存')); save_in.clicked.connect(self._save_audio_in)
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
        self.rebind_audio_out = QPushButton(tr('同名の有効な機器を選び直す'))
        self.rebind_audio_out.clicked.connect(self._rebind_audio_out)
        refresh = QPushButton(tr('音声デバイスを再検出'))
        refresh.clicked.connect(self._refresh_audio_out_choices)
        row_device = QHBoxLayout()
        row_device.addWidget(self.rebind_audio_out)
        row_device.addWidget(refresh)
        row_device.addWidget(self.audio_out_status, 1)
        form.addRow('', row_device)
        self.audio_out.currentIndexChanged.connect(self._update_audio_out_availability)
        self._update_audio_out_availability()
        n3 = QLabel(tr("送信用：パソコン → 無線機\n送信音を送る再生デバイス（USB Audio／LINE OUT／スピーカー出力など）を選んでください。"))
        n3.setWordWrap(True); n3.setObjectName("helpText"); form.addRow("", n3)

        self.tx_gain = QSlider(Qt.Horizontal)
        self.tx_gain.setRange(1, 90)
        self.tx_gain.setValue(int(float(self.working["audio"]["tx_gain"]) * 100))
        self.tx_label = QLabel()
        self.tx_gain.valueChanged.connect(self._tx_gain_changed)
        self.tx_label.setText(f"{self.tx_gain.value()}%")
        row2 = QHBoxLayout(); row2.addWidget(self.tx_gain, 1); row2.addWidget(self.tx_label)
        form.addRow(tr("送信レベル"), row2)
        n4 = QLabel(tr('試験送信は実際にPTTをONにしてRTTY音を送出します。低いレベルから始め、無線機のALCが動作し始める手前に合わせてください。無線機が運用接続中ならそのまま使用できます。未接続なら無線機タブで接続テストを成功させてください。'))
        n4.setWordWrap(True); n4.setMinimumHeight(n4.fontMetrics().lineSpacing() * 6)
        n4.setObjectName("helpText"); form.addRow("", n4)
        self.alc_meter = QProgressBar(); self.alc_meter.setRange(0,120); self.alc_meter.setValue(0)
        self.alc_meter.setFormat(tr('ALC：未取得'))
        form.addRow(tr('無線機ALC'), self.alc_meter)
        self.alc_good = QLabel(tr('ALC調整目安：未判定'))
        form.addRow('', self.alc_good)
        self.alc_note = QLabel(tr('ALCを取得できない場合は無線機本体のALCメーターを確認してください。'))
        self.alc_note.setWordWrap(True); self.alc_note.setObjectName('helpText'); form.addRow('', self.alc_note)
        self.test_tx_button = QPushButton(tr('テスト音＋TX-PTT')); self.test_tx_button.setEnabled(False)
        self.test_tx_button.clicked.connect(self._toggle_test_tx)
        self.test_count_label = QLabel(tr('待機中'))
        test_row=QHBoxLayout(); test_row.addWidget(self.test_tx_button); test_row.addWidget(self.test_count_label); test_row.addStretch(1)
        form.addRow('', test_row)
        self.tx_test_note = QLabel(tr('もう一度押すと停止。10秒でも自動停止します。送信停止後に保存してください。'))
        self.tx_test_note.setWordWrap(True); self.tx_test_note.setObjectName('helpText'); form.addRow('', self.tx_test_note)
        self.save_out_button = QPushButton(tr('音量設定を保存')); self.save_out_button.clicked.connect(self._save_audio_out)
        form.addRow('', self.save_out_button)

        note = QLabel(self.audio_error or tr('有効な音声デバイスを表示します。USB機器を追加した場合はPSRTTYを再起動してください。\n旧版で番号指定した機器は選び直してください。「自動」は各OSの既定の機器を使用します。'))
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
            QMessageBox.warning(self, tr('第二AudioOUTの設定'), str(exc))
            return
        dialog.exec()

    def _confirm_primary_audio_save(self):
        box = QMessageBox(self)
        box.setWindowTitle(tr('第二AudioOUTの設定'))
        box.setText(tr('第二AudioOUT設定を開くには、主AudioOUTの出力先と音量を保存する必要があります。保存して開きますか？'))
        box.setStandardButtons(QMessageBox.Save | QMessageBox.Cancel)
        box.button(QMessageBox.Save).setText(tr('保存して開く'))
        box.button(QMessageBox.Cancel).setText(tr('キャンセル'))
        box.setDefaultButton(QMessageBox.Cancel)
        return box.exec() == QMessageBox.Save

    def _save_primary_before_secondary(self):
        parent = self.parent()
        if self.tx_testing or (parent and parent.audio._tx_active):
            raise ValueError(tr('送信が止まってから保存してください。'))
        if [item['name'] for item in self.working_profiles] != [item['name'] for item in self.store.data['profiles']]:
            raise ValueError(tr('先に設定画面の［保存］でProfileの変更を保存し、設定画面を開き直してください。'))
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
            raise ValueError(tr('送信が止まってから保存してください。'))
        if [item['name'] for item in self.working_profiles] != [item['name'] for item in self.store.data['profiles']]:
            raise ValueError(tr('先に設定画面の［保存］でProfileの変更を保存し、設定画面を開き直してください。'))
        values = normalize_settings(values)
        if values['enabled'] and values['device'] == self.audio_out.currentData():
            raise ValueError(tr('第二AudioOUTには主AudioOUTと別の出力先を選択してください。'))
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
        warning = QLabel(tr("通常は初期値のままで使用してください。RTTY復調・AFSK送信の動作値を変更できます。"))
        warning.setWordWrap(True); warning.setObjectName("helpText")
        root.addWidget(warning)
        form = QFormLayout(); root.addLayout(form)

        adv = self.working["advanced"]
        self.rtty_baud = QDoubleSpinBox(); self.rtty_baud.setRange(30, 300); self.rtty_baud.setDecimals(2); self.rtty_baud.setValue(float(adv["rtty_baud"])); self.rtty_baud.setSuffix(" baud")
        self.shift = QSpinBox(); self.shift.setRange(50, 1000); self.shift.setValue(int(adv["shift_hz"])); self.shift.setSuffix(" Hz")
        self.mark = QSpinBox(); self.mark.setRange(300, 3500); self.mark.setValue(int(adv["mark_hz"])); self.mark.setSuffix(" Hz")
        self.space = QSpinBox(); self.space.setRange(300, 3500); self.space.setValue(int(adv["space_hz"])); self.space.setSuffix(" Hz")
        self.invert = QCheckBox(tr("Mark / Spaceを反転する")); self.invert.setChecked(bool(adv["invert"]))
        self.spec_width = QComboBox()
        for v in (500, 1000, 2000, 3000): self.spec_width.addItem(f"{v if v<1000 else v//1000 if v%1000==0 else v/1000} {'Hz' if v<1000 else 'kHz'}", v)
        self._select_data(self.spec_width, int(adv["spectrum_width_hz"]))
        self.tune_tol = QSpinBox(); self.tune_tol.setRange(20, 250); self.tune_tol.setValue(int(adv["auto_tune_tolerance_hz"])); self.tune_tol.setSuffix(" Hz")

        self.data_mode = QComboBox(); self.data_mode.addItems(["LSB-D", "USB-D"])
        self.data_mode.setCurrentText(adv.get("data_mode", "LSB-D"))
        self.data_mode.currentTextChanged.connect(self._mode_caption)
        self._mode_caption()
        form.addRow(tr("接続時DATAモード"), self.data_mode)
        form.addRow(tr("RTTY速度"), self.rtty_baud)
        form.addRow("Shift", self.shift)
        form.addRow("Mark", self.mark)
        form.addRow("Space", self.space)
        form.addRow(tr("極性"), self.invert)
        form.addRow(tr("スペクトラム表示幅"), self.spec_width)
        form.addRow(tr("AUTO TUNE許容幅"), self.tune_tol)

        def shift_changed(v):
            self.space.blockSignals(True); self.space.setValue(self.mark.value() + v); self.space.blockSignals(False)
        self.shift.valueChanged.connect(shift_changed)
        self.mark.valueChanged.connect(lambda v: shift_changed(self.shift.value()))
        self.space.valueChanged.connect(lambda v: self.shift.setValue(abs(v - self.mark.value())))

        reset = QPushButton(tr("高度な設定を初期値に戻す"))
        reset.clicked.connect(self._reset_advanced)
        root.addWidget(reset)
        root.addStretch(1)
        self.tabs.addTab(tab, tr("高度な設定"))

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
                      com_port=self.com.currentData() or 'AUTO', ptt=self.ptt.currentText(),
                      auto_data_mode=self.auto_mode.isChecked())
        values['cat_baud' if yaesu else 'civ_baud'] = self.baud.currentData() or 'AUTO'
        if yaesu: values['cat_stopbits'] = self.stopbits.currentData()
        return values

    def _test_controls_changed(self, *_):
        if not self.tx_testing and self.verified_values != self._radio_values():
            self.test_tx_button.setEnabled(False)
            if self.verified_values:
                self.tx_test_note.setText(tr('無線機設定を変更しました。接続テストを再実行してください。'))

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
        self.test_note.setText(tr('運用接続を確認しました。Audio OUTで試験送信できます。'))
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
        self.rx_meter.setValue(value)
        color = '#3769c3' if 40 <= value <= 70 else '#a59d92' if value < 25 else '#c96d13' if value <= 85 else '#c0392b'
        self.rx_meter.setStyleSheet(f'QProgressBar::chunk {{ background: {color}; }}')
        self.rx_meter.setFormat(f'{value}%　' + (tr('Good（音声レベルの目安）') if 40 <= value <= 70 else tr('音が小さいか無信号') if value < 25 else tr('信号受信中に調整')))

    def _save_audio_in(self):
        parent=self.parent()
        if self.profile_index != self.store.data['active_profile']:
            self.test_note.setText(tr('別のプロファイルです。画面下の［保存］で設定を保存してください。'))
            return
        old=self.store.data['audio']['input_device']
        self.store.data['audio'].update(input_device=self.audio_in.currentData() or 'AUTO', rx_gain=self.rx_gain.value()/100)
        self.working['audio'].update(self.store.data['audio'])
        self.store.save()
        if parent and old != self.store.data['audio']['input_device']: parent._restart_audio_input()
        self.test_note.setText(tr('Audio INの設定を保存しました。'))

    def _save_audio_out(self):
        if self.profile_index != self.store.data['active_profile']:
            self.tx_test_note.setText(tr('別のプロファイルです。画面下の［保存］で設定を保存してください。'))
            return
        if self.tx_testing or self.parent().audio._tx_active:
            self.tx_test_note.setText(tr('送信が止まってから保存してください。')); return
        self.store.data['audio'].update(output_device=self.audio_out.currentData() or 'AUTO', tx_gain=self.tx_gain.value()/100)
        self.working['audio'].update(self.store.data['audio'])
        self.store.save()
        self.tx_test_note.setText(tr('Audio OUTの設定を保存しました。'))

    def _refresh_audio_out_choices(self):
        selected = self.audio_out.currentData()
        self.audio_out.blockSignals(True)
        self.audio_out.clear()
        self._audio_choices(self.audio_out, 'output', selected)
        self.audio_out.blockSignals(False)
        self._update_audio_out_availability()

    def _matching_audio_out(self):
        selected = self.audio_out.currentData()
        if not isinstance(selected, dict) or tr('未接続／無効') not in self.audio_out.currentText():
            return []
        return [index for index in range(self.audio_out.count())
                if isinstance(self.audio_out.itemData(index), dict)
                and self.audio_out.itemData(index).get('name') == selected.get('name')
                and self.audio_out.itemData(index).get('kind') == 'output'
                and self.audio_out.itemData(index).get('backend') == selected.get('backend')
                and self.audio_out.itemData(index).get('id') != selected.get('id')]

    def _update_audio_out_availability(self, *_):
        stale = tr('未接続／無効') in self.audio_out.currentText()
        matches = self._matching_audio_out() if stale else []
        self.rebind_audio_out.setVisible(len(matches) == 1)
        self.audio_out_status.setVisible(stale)
        if stale:
            self.audio_out_status.setText(tr('保存済みの音声デバイスIDが現在は使えません。')
                + (tr('同名の有効な機器が見つかりました。ボタンで選び直してからテスト送信してください。') if len(matches) == 1 else
                   tr('音声デバイスを再検出し、一覧から送信先の機器を選び直してください。')))
        else:
            self.audio_out_status.setText('')

    def _rebind_audio_out(self):
        matches = self._matching_audio_out()
        if len(matches) == 1:
            self.audio_out.setCurrentIndex(matches[0])
            self.tx_test_note.setText(tr('有効なAudio OUTを選び直しました。テスト送信で確認し、停止後に音量設定を保存してください。'))

    def _show_alc(self, value):
        self.alc_value=value
        if value is None:
            self.alc_meter.setValue(0); self.alc_meter.setFormat(tr('ALC：取得できません'))
            self.alc_good.setText(tr('ALC調整目安：本体メーターを確認'))
            self.alc_good.setStyleSheet('color: #765d44;')
            self.alc_note.setText(tr('ALC情報を取得できません。テスト送信中は無線機本体のALCメーターを見て、動き始める手前まで音量を上げてください。'))
            self.alc_meter.setStyleSheet('')
            return
        self.alc_meter.setValue(min(120,value))
        self.alc_meter.setFormat(f'ALC {value} / 120')
        gain=self.tx_gain.value()
        good = self.alc_onset is not None and self.alc_onset-5 <= gain < self.alc_onset and value <= 1
        self.alc_good.setText(tr('ALC調整目安：Good') if good else tr('ALC調整目安：調整中'))
        self.alc_good.setStyleSheet('background: #208341; color: white; padding: 4px; font-weight: bold;' if good else 'color: #765d44;')
        color = '#208341' if good else '#c0392b' if value >= 10 else '#c98722'
        self.alc_meter.setStyleSheet(f'QProgressBar::chunk {{ background: {color}; }}; QProgressBar {{ border: 2px solid {color}; }}')
        self.alc_note.setText(tr('緑：ALC調整目安（動作開始点から少し下げた位置）') if good else
                              tr('ALCが動き始める手前に調整してください。緑は動作開始点を一度確認した後に表示します。'))

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
            self.tx_test_note.setText(tr('無線機タブで接続テストを再実行してください。')); return
        ctl=self.test_controller
        mode=self.verified_values['ptt']
        ptt={'CI-V':ctl.set_ptt,'CAT':ctl.set_ptt,'RTS':ctl.set_rts,'DTR':ctl.set_dtr}.get(mode)
        if not ptt:
            self.tx_test_note.setText(tr('PTT方式を確認してください。')); return
        adv=self.working['advanced']
        # RY alternation exercises both mark and space. The worker is cut off at 10 s.
        text='RY ' * 70
        try:
            sequencer=ExternalPTT(self._external_values(), ctl.status.port, parent.audio._tx_cancel)
        except ValueError as exc:
            self.tx_test_note.setText(str(exc)); return
        def on():
            return bool(self.test_controller is ctl and ctl.status.connected and sequencer.before_ptt() and ptt(True))
        def off():
            try: return ptt(False)
            finally: sequencer.after_ptt()
        ok,msg=parent.audio.send_text(text,self.audio_out.currentData(),adv['rtty_baud'],
            adv['mark_hz'],adv['space_hz'],adv['invert'],self.tx_gain.value()/100,
            on, off, lambda success,note:self.tx_test_finished.emit(success,note))
        if not ok:
            self.tx_test_note.setText(msg); return
        self.tx_testing=True; self.test_deadline=time.monotonic()+10
        self.test_tx_button.setText(tr('テスト送信を停止'))
        self.test_count_label.setText(tr('残り 10秒'))
        self.save_out_button.setEnabled(False)
        self.tx_test_note.setText(tr('実際に送信中です。無線機のALCと送信状態を確認してください。'))
        self.countdown.start()

    def _tick_test_tx(self):
        remaining=max(0,self.test_deadline-time.monotonic())
        self.test_count_label.setText(f"{tr('残り ')}{int(remaining + 0.999)}{tr('秒')}" if remaining else tr('停止中…'))
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
            self._show_alc(value)
        self.alc_job=BackgroundJob(self,ctl.read_alc,done)

    def _stop_test_tx(self):
        if not self.tx_testing: return
        self.countdown.stop()
        self.test_count_label.setText(tr('停止中…'))
        self.parent().audio.stop_tx()

    def _test_tx_finished(self, success, message):
        self.tx_testing=False; self.countdown.stop()
        self.test_tx_button.setText(tr('テスト音＋TX-PTT'))
        self.test_count_label.setText(tr('停止'))
        self.save_out_button.setEnabled(True)
        self.alc_meter.setValue(0); self.alc_meter.setFormat(tr('ALC：送信停止'))
        self.alc_good.setText(tr('ALC調整目安：送信停止'));self.alc_good.setStyleSheet('color: #765d44;')
        self.tx_test_note.setText(tr('送信を停止しました。音量設定を保存できます。') if success or message==tr('送信中止') else message)
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
                self.test_note.setText(tr('運用接続中の設定と画面の選択が異なります。設定を保存して再接続してください。'))
            return
        if self.tx_testing: return
        if self.test_controller:
            self._release_test_controller()
        values = self._radio_values()
        try:
            ctl = create_controller(values)
        except ValueError as exc:
            QMessageBox.warning(self, tr("接続テスト"), str(exc)); return
        self.test_controller = ctl
        self.test_uses_main = False
        self.test_pending = True
        self.test_timed_out = False
        self.verified_values = None
        self.alc_onset = None
        self._show_alc(None)
        self.test_tx_button.setEnabled(False)
        self.connect_button.setEnabled(False)
        self.test_note.setText(tr("接続確認中…"))
        advanced = dict(data_mode=self.data_mode.currentText())
        self.test_button.setEnabled(False); self.test_button.setText(tr("接続確認中…"))
        def work():
            return connect_configured(ctl, values, advanced)
        self.test_job = BackgroundJob(self, work, lambda st, err: self._test_done(st, err, values) if self.test_controller is ctl else None)
        def deadline():
            if self.test_controller is ctl and self.test_pending:
                self.test_timed_out = True
                ctl.cancel.set()
                self.test_note.setText(tr("中止処理中です。完了後に再試行してください。"))
                if self.isVisible():
                    QMessageBox.warning(self, tr("接続テスト"), tr("接続がタイムアウトしました"))
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
        self.test_note.setText(tr("接続テスト失敗") if failed else tr("接続テストに成功しました。Audio OUTを調整できます。運用を開始するには［接続］を押してください。"))
        self.test_button.setEnabled(True); self.test_button.setText(tr("接続テスト"))
        if not self.isVisible():
            return
        if timed_out:
            return
        if failed:
            QMessageBox.warning(self, tr("接続テスト"), str(error) if error else status.message if status else tr('応答なし'))
        else:
            QMessageBox.information(self, tr("接続テスト"), tr('接続テストに成功しました。Audio OUTで送信レベルを調整できます。\n{port} / {baud} bps\n周波数: {frequency:,} Hz').format(port=status.port, baud=status.baud, frequency=status.frequency_hz))
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
        self.test_note.setText(tr('接続テストを終了しました。継続して運用するには［接続］を押してください。'))

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
            self.test_note.setText(tr("接続テスト・送信テストの終了を待ってください。"))
            return
        self._release_test_controller()
        values = self._radio_values()
        try:
            if values["model"]:
                validate_radio(values)
        except ValueError as exc:
            QMessageBox.warning(self, tr("設定"), str(exc)); return
        try:
            validate_external(self._external_values(), values['com_port'])
        except ValueError as exc:
            QMessageBox.warning(self, tr("外部接続"), str(exc)); return
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
