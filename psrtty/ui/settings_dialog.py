from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSlider,
    QSpinBox, QTabWidget, QVBoxLayout, QWidget, QGroupBox, QLineEdit, QPlainTextEdit,
)

from ..audio_engine import AudioEngine
from ..civ import CIVController, connect_configured
from ..radio import create_controller, validate_radio
from ..yaesu import YAESU_MODELS
from .background import BackgroundJob
from ..config import DEFAULT_CONFIG, RIG_MODELS


class SettingsDialog(QDialog):
    def __init__(self, config_store, parent=None):
        super().__init__(parent)
        self.test_controller = None
        self.connect_requested = False
        self.store = config_store
        self.working = deepcopy(config_store.data)
        self.setWindowTitle("PSRTTY 設定")
        self.resize(660, 600)

        root = QVBoxLayout(self)
        intro = QLabel(
            "FT8で使っているCOMポート・音声デバイスを選択してください。\n"
            "ICOMに加え、Yaesuの2系統に試験対応しています（実機未確認）。"
        )
        intro.setWordWrap(True)
        intro.setObjectName("helpText")
        root.addWidget(intro)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._build_basic_tab()
        self._build_radio_tab()
        self._build_audio_tab()
        self._build_advanced_tab()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_basic_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        self.my_call = QLineEdit(self.working.get('station_callsign', ''))
        self.my_call.setPlaceholderText('例: JX1XXX')
        station = self.working['station']
        self.my_qth = QLineEdit(station['qth'])
        self.my_qth.setPlaceholderText('送信用の地名（英字）')
        self.my_jcc_jcg = QLineEdit(station['jcc_jcg'])
        self.my_jcc_jcg.setPlaceholderText('JCC/JCGコード')
        self.my_text = QPlainTextEdit(station['text'])
        self.my_text.setPlaceholderText('名前・設備紹介など、追加で送る英文を自由入力')
        form.addRow('自局コールサイン {MYCALL}', self.my_call)
        form.addRow('自局運用場所 {MYQTH}', self.my_qth)
        form.addRow('JCC/JCG {MYJCCJCG}', self.my_jcc_jcg)
        form.addRow('追加送信文 {MYTXT}', self.my_text)
        note = QLabel('自局コールサインはメイン画面と共用です。Saveで反映します。\n通常交信では QTH {MYQTH} {MYJCCJCG} の順に送ります。\n追加送信文は複数行・空欄も使用できます。送信文は英数字で入力してください。')
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        self.tabs.addTab(tab, '基本設定')

    def _build_radio_tab(self):
        tab = QWidget(); form = QFormLayout(tab)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.rig = QComboBox(); self.rig.addItem('選択してください', '')
        for model in RIG_MODELS: self.rig.addItem(model, model)
        for model, label in YAESU_MODELS.items(): self.rig.addItem(label, model)
        self._select_data(self.rig, self.working['radio']['model'])
        form.addRow('無線機', self.rig)
        self.com = QComboBox(); self.com.addItem('自動', 'AUTO')
        for port, name in CIVController.port_choices(): self.com.addItem(name, port)
        target = self.working['radio']['com_port']
        if self.com.findData(target) < 0:
            self.com.addItem(f'{target}（未接続）', target)
        self._select_data(self.com, target)
        form.addRow('COMポート', self.com)
        self.port_note = QLabel(); self.port_note.setWordWrap(True); self.port_note.setObjectName('helpText')
        form.addRow('', self.port_note)
        self.specific = QGroupBox('無線機固有の設定')
        self.specific_form = f = QFormLayout(self.specific)
        f.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.civ_addr = QComboBox(); self.civ_addr.setEditable(True)
        self.civ_addr.addItems([f'{v:02X}' for v in sorted(set(RIG_MODELS.values())) if v])
        self.civ_addr.setCurrentText(self.working['radio']['civ_address'])
        self.address_label = QLabel('CI-Vアドレス'); f.addRow(self.address_label, self.civ_addr)
        self.address_note = QLabel('機種選択時に標準値を入力します。無線機側で変更した場合は手修正できます。')
        self.address_note.setWordWrap(True); self.address_note.setObjectName('helpText'); f.addRow(self.address_note)
        self.ptt = QComboBox(); f.addRow('PTT方式', self.ptt)
        self.baud = QComboBox(); self.baud_label = QLabel(); f.addRow(self.baud_label, self.baud)
        self.stopbits = QComboBox(); self.stopbits.addItem('1', 1); self.stopbits.addItem('2', 2)
        self.stopbits_label = QLabel('ストップビット'); f.addRow(self.stopbits_label, self.stopbits)
        self.auto_mode = QCheckBox(); self.auto_mode.setChecked(self.working['radio'].get('auto_data_mode', True))
        f.addRow(self.auto_mode)
        self.cat_note = QLabel('試験用・実機未確認。DATA入力はUSBに設定してください。\nFT-991/AはVFO A、FTX-1はMAIN側で運用します。')
        self.cat_note.setWordWrap(True); self.cat_note.setObjectName('helpText'); f.addRow(self.cat_note)
        form.addRow(self.specific)
        self.test_button = QPushButton('接続テスト'); self.test_button.clicked.connect(self._test_radio)
        form.addRow('', self.test_button)
        self.test_note = QLabel(); self.test_note.setWordWrap(True); form.addRow(self.test_note)
        self.connect_button = QPushButton("接続")
        self.connect_button.clicked.connect(self._connect_saved)
        form.addRow("", self.connect_button)
        self.rig.currentIndexChanged.connect(self._rig_changed)
        self._rig_changed(initial=True)
        self.tabs.addTab(tab, '無線機')

    def _rig_changed(self, *_, initial=False):
        model = self.rig.currentData() or ''
        yaesu = model in YAESU_MODELS
        self.specific.setEnabled(bool(model)); self.test_button.setEnabled(bool(model))
        self.connect_button.setEnabled(bool(model))
        for widget in (self.address_label, self.civ_addr, self.address_note): widget.setVisible(not yaesu)
        for widget in (self.stopbits_label, self.stopbits, self.cat_note): widget.setVisible(yaesu)
        if not initial and not yaesu:
            addr = RIG_MODELS.get(model, 0)
            self.civ_addr.setCurrentText(f'{addr:02X}' if addr else '')
        self.ptt.clear(); self.ptt.addItems(['CAT'] if yaesu else ['CI-V', 'RTS', 'DTR'])
        saved = self.working['radio']
        if initial: self.ptt.setCurrentText(saved.get('ptt', 'CAT' if yaesu else 'CI-V'))
        self.baud.clear(); self.baud.addItem('自動', 'AUTO')
        speeds = [115200, 38400, 19200, 9600, 4800] if yaesu else [115200, 57600, 38400, 19200, 9600, 4800]
        for speed in speeds: self.baud.addItem(str(speed), str(speed))
        self._select_data(self.baud, saved.get('cat_baud' if yaesu else 'civ_baud', 'AUTO'))
        self.baud_label.setText('CAT速度' if yaesu else 'CI-V速度')
        bits = saved.get('cat_stopbits') if initial else None
        self._select_data(self.stopbits, bits or (1 if model == 'FTX-1' else 2))
        self.port_note.setText('YaesuはEnhanced COMを選択してください。「自動」ではCAT応答を確認して探します。' if yaesu else '通常は「自動」でCI-V応答を確認して接続します。')
        self._mode_caption()

    def _mode_caption(self, *_):
        mode = self.data_mode.currentText() if hasattr(self, 'data_mode') else self.working['advanced'].get('data_mode', 'LSB-D')
        if self.rig.currentData() in YAESU_MODELS:
            mode = ('DATA-L' if mode == 'LSB-D' else 'DATA-U') if self.rig.currentData() == 'FTX-1' else ('DATA-LSB' if mode == 'LSB-D' else 'DATA-USB')
        self.auto_mode.setText(f'接続時に {mode} へ自動切替')

    def _audio_choices(self, combo, kind, selected):
        if kind == 'input': combo.addItem('未設定', 'UNSET')
        combo.addItem('自動', 'AUTO')
        try:
            for choice, label in AudioEngine.devices(kind):
                combo.addItem(label, choice)
                if isinstance(choice, dict) and isinstance(selected, dict) and all(choice.get(k) == selected.get(k) for k in ('backend', 'id', 'kind')):
                    selected = choice
        except Exception as exc:
            self.audio_error = str(exc)
        if combo.findData(selected) < 0:
            if isinstance(selected, dict):
                label = selected.get('name', '') + '（未接続／無効）'
            else:
                label = f'旧設定 [{selected}]（選び直してください）'
            combo.addItem(label, selected)
        self._select_data(combo, selected)

    def _build_audio_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)
        self.audio_in = QComboBox()
        self.audio_error = ''
        self._audio_choices(self.audio_in, 'input', self.working['audio']['input_device'])
        form.addRow("Audio IN", self.audio_in)
        n1 = QLabel("受信用：無線機 → パソコン\n未設定では入力しません。設定済みなら無線機未接続でも入力します。\n受信音が入る録音デバイス（USB Audio／LINE IN／マイク入力など）を選んでください。")
        n1.setWordWrap(True); n1.setObjectName("helpText"); form.addRow("", n1)

        self.rx_gain = QSlider(Qt.Horizontal)
        self.rx_gain.setRange(10, 300)
        self.rx_gain.setValue(int(float(self.working["audio"]["rx_gain"]) * 100))
        self.rx_label = QLabel()
        self.rx_gain.valueChanged.connect(lambda v: self.rx_label.setText(f"{v}%"))
        self.rx_label.setText(f"{self.rx_gain.value()}%")
        row = QHBoxLayout(); row.addWidget(self.rx_gain, 1); row.addWidget(self.rx_label)
        form.addRow("受信レベル", row)
        n2 = QLabel("※ソフト内部の受信ゲインです。メイン画面のRXメーターを見て、振り切れない範囲に調整します。")
        n2.setWordWrap(True); n2.setObjectName("helpText"); form.addRow("", n2)

        self.audio_out = QComboBox()
        self._audio_choices(self.audio_out, 'output', self.working['audio']['output_device'])
        form.addRow("Audio OUT", self.audio_out)
        n3 = QLabel("送信用：パソコン → 無線機\n送信音を送る再生デバイス（USB Audio／LINE OUT／スピーカー出力など）を選んでください。")
        n3.setWordWrap(True); n3.setObjectName("helpText"); form.addRow("", n3)

        self.tx_gain = QSlider(Qt.Horizontal)
        self.tx_gain.setRange(1, 90)
        self.tx_gain.setValue(int(float(self.working["audio"]["tx_gain"]) * 100))
        self.tx_label = QLabel()
        self.tx_gain.valueChanged.connect(lambda v: self.tx_label.setText(f"{v}%"))
        self.tx_label.setText(f"{self.tx_gain.value()}%")
        row2 = QHBoxLayout(); row2.addWidget(self.tx_gain, 1); row2.addWidget(self.tx_label)
        form.addRow("送信レベル", row2)
        n4 = QLabel("※RTTY AFSK送信用です。低めから開始し、無線機のALCが大きく振れない範囲で調整してください。")
        n4.setWordWrap(True); n4.setObjectName("helpText"); form.addRow("", n4)

        note = QLabel(self.audio_error or '有効な音声デバイスを表示します。USB機器を追加した場合はPSRTTYを再起動してください。\n旧版で番号指定した機器は選び直してください。「自動」はWindowsの既定の機器を使用します。')
        note.setWordWrap(True); note.setObjectName('helpText'); form.addRow(note)
        self.tabs.addTab(tab, "Audio")

    def _build_advanced_tab(self):
        tab = QWidget()
        root = QVBoxLayout(tab)
        warning = QLabel("通常は初期値のままで使用してください。RTTY復調・AFSK送信の動作値を変更できます。")
        warning.setWordWrap(True); warning.setObjectName("helpText")
        root.addWidget(warning)
        form = QFormLayout(); root.addLayout(form)

        adv = self.working["advanced"]
        self.rtty_baud = QDoubleSpinBox(); self.rtty_baud.setRange(30, 300); self.rtty_baud.setDecimals(2); self.rtty_baud.setValue(float(adv["rtty_baud"])); self.rtty_baud.setSuffix(" baud")
        self.shift = QSpinBox(); self.shift.setRange(50, 1000); self.shift.setValue(int(adv["shift_hz"])); self.shift.setSuffix(" Hz")
        self.mark = QSpinBox(); self.mark.setRange(300, 3500); self.mark.setValue(int(adv["mark_hz"])); self.mark.setSuffix(" Hz")
        self.space = QSpinBox(); self.space.setRange(300, 3500); self.space.setValue(int(adv["space_hz"])); self.space.setSuffix(" Hz")
        self.invert = QCheckBox("Mark / Spaceを反転する"); self.invert.setChecked(bool(adv["invert"]))
        self.spec_width = QComboBox()
        for v in (500, 1000, 2000, 3000): self.spec_width.addItem(f"{v if v<1000 else v//1000 if v%1000==0 else v/1000} {'Hz' if v<1000 else 'kHz'}", v)
        self._select_data(self.spec_width, int(adv["spectrum_width_hz"]))
        self.tune_tol = QSpinBox(); self.tune_tol.setRange(20, 250); self.tune_tol.setValue(int(adv["auto_tune_tolerance_hz"])); self.tune_tol.setSuffix(" Hz")

        self.data_mode = QComboBox(); self.data_mode.addItems(["LSB-D", "USB-D"])
        self.data_mode.setCurrentText(adv.get("data_mode", "LSB-D"))
        self.data_mode.currentTextChanged.connect(self._mode_caption)
        self._mode_caption()
        form.addRow("接続時DATAモード", self.data_mode)
        form.addRow("RTTY速度", self.rtty_baud)
        form.addRow("Shift", self.shift)
        form.addRow("Mark", self.mark)
        form.addRow("Space", self.space)
        form.addRow("極性", self.invert)
        form.addRow("スペクトラム表示幅", self.spec_width)
        form.addRow("AUTO TUNE許容幅", self.tune_tol)

        def shift_changed(v):
            self.space.blockSignals(True); self.space.setValue(self.mark.value() + v); self.space.blockSignals(False)
        self.shift.valueChanged.connect(shift_changed)
        self.mark.valueChanged.connect(lambda v: shift_changed(self.shift.value()))
        self.space.valueChanged.connect(lambda v: self.shift.setValue(abs(v - self.mark.value())))

        reset = QPushButton("高度な設定を初期値に戻す")
        reset.clicked.connect(self._reset_advanced)
        root.addWidget(reset)
        root.addStretch(1)
        self.tabs.addTab(tab, "高度な設定")

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
        yaesu = self.rig.currentData() in YAESU_MODELS
        values.update(model=self.rig.currentData() or '', civ_address=self.civ_addr.currentText().strip().upper(),
                      com_port=self.com.currentData() or 'AUTO', ptt=self.ptt.currentText(),
                      auto_data_mode=self.auto_mode.isChecked())
        values['cat_baud' if yaesu else 'civ_baud'] = self.baud.currentData() or 'AUTO'
        if yaesu: values['cat_stopbits'] = self.stopbits.currentData()
        return values

    def _test_radio(self):
        if self.test_controller:
            return
        values = self._radio_values()
        try:
            ctl = create_controller(values)
        except ValueError as exc:
            QMessageBox.warning(self, "接続テスト", str(exc)); return
        self.test_controller = ctl
        self.connect_button.setEnabled(False)
        self.test_note.setText("接続確認中…")
        advanced = dict(data_mode=self.data_mode.currentText())
        self.test_button.setEnabled(False); self.test_button.setText("接続確認中…")
        def work():
            try:
                return connect_configured(ctl, values, advanced)
            finally:
                ctl.disconnect()
        self.test_job = BackgroundJob(self, work, lambda st, err: self._test_done(st, err) if self.test_controller is ctl else None)
        def deadline():
            if self.test_controller is ctl:
                ctl.cancel.set()
                self.test_note.setText("中止処理中です。完了後に再試行してください。")
                self.test_button.setEnabled(True); self.test_button.setText("接続テスト")
                QMessageBox.warning(self, "接続テスト", "接続がタイムアウトしました")
        QTimer.singleShot(10000, self, deadline)

    def _test_done(self, status, error):
        self.test_controller = None
        self.connect_button.setEnabled(bool(self.rig.currentData()))
        self.test_note.setText("接続テスト失敗" if error or not status.connected else "接続テストに成功しました。運用を開始するには［接続］を押してください。")
        self.test_button.setEnabled(True); self.test_button.setText("接続テスト")
        if not self.isVisible():
            return
        if error or not status.connected:
            QMessageBox.warning(self, "接続テスト", str(error) if error else status.message)
        else:
            QMessageBox.information(self, "接続テスト", f"接続テストに成功しました。運用を開始するには［接続］を押してください。\n{status.port} / {status.baud} bps\n周波数: {status.frequency_hz:,} Hz")

    def done(self, result):
        if self.test_controller:
            self.test_controller.cancel.set()
            self.test_controller = None
        super().done(result)

    def basic_call_changed(self):
        return self.my_call.text() != self.working.get('station_callsign', '')

    def _connect_saved(self):
        if self.test_controller: return
        self.connect_requested = True
        self._save()
        if self.result() != QDialog.Accepted: self.connect_requested = False

    def _save(self):
        if self.test_controller:
            self.test_note.setText("接続テストの終了を待ってください。")
            return
        values = self._radio_values()
        try:
            if values["model"]:
                validate_radio(values)
        except ValueError as exc:
            QMessageBox.warning(self, "設定", str(exc)); return
        self.working["radio"].update(values)
        self.working["audio"].update({
            "input_device": self.audio_in.currentData() or "AUTO",
            "output_device": self.audio_out.currentData() or "AUTO",
            "rx_gain": self.rx_gain.value() / 100.0,
            "tx_gain": self.tx_gain.value() / 100.0,
        })
        self.working["advanced"].update({
            "data_mode": self.data_mode.currentText(),
            "rtty_baud": self.rtty_baud.value(),
            "shift_hz": self.shift.value(),
            "mark_hz": self.mark.value(),
            "space_hz": self.space.value(),
            "invert": self.invert.isChecked(),
            "spectrum_width_hz": self.spec_width.currentData(),
            "auto_tune_tolerance_hz": self.tune_tol.value(),
        })
        # Main-window QSO fields remain usable while settings are open.
        for section in ('radio', 'audio', 'advanced'):
            self.store.data[section] = self.working[section]
        from ..parser import normalize_call
        # Preserve a main-window CALL edit when this field was not edited.
        if self.basic_call_changed():
            self.store.data['station_callsign'] = normalize_call(self.my_call.text())
        self.store.data['station'].update(qth=self.my_qth.text().strip(),
                                        jcc_jcg=self.my_jcc_jcg.text().strip(),
                                        text=self.my_text.toPlainText().strip())
        self.store.save()
        self.accept()
