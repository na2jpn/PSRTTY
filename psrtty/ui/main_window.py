from __future__ import annotations
from ..timebase import JST

import os
import re
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
    QProgressBar, QPushButton, QSlider, QScrollArea, QSpinBox, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QFileDialog, QTextBrowser,
)

from ..adif import ADIFLog, QSORecord
from ..audio_engine import AudioEngine
from ..civ import CIVController, connect_configured
from ..radio import create_controller
from .background import BackgroundJob
from .window_state import restore_window, save_window
from ..config import ConfigStore
from ..logging_store import TranscriptLogger
from ..macros import expand_macro
from ..parser import normalize_call, parse_exchange
from ..macros import CQWW_TEMPLATE_NAME
from ..paths import ensure_runtime_dirs, resource_path
from .about_dialog import AboutDialog
from .macro_dialog import MacroDialog
from .qso_log_dialog import QSOLogDialog
from .settings_dialog import SettingsDialog
from .spectrum import SpectrumWidget
from .hint_group import HintGroupBox, HeaderControlGroupBox, FooterHintGroupBox
from .formatting import frequency_text
from .number_edit import NumberEdit
from .qso_datetime import QSODatetime


class AudioBridge(QObject):
    tx_finished = Signal(int, bool, str)
    char = Signal(object)
    level = Signal(float)
    spectrum = Signal(object, object)


class ReceiveCard(QFrame):
    clicked = Signal(str)

    def __init__(self, stamp: str, text: str, direction: str = "RX", font_size: int = 14, parent=None):
        super().__init__(parent)
        self.text_value = text
        self.setObjectName("txCard" if direction == "TX" else "rxCard")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self); lay.setContentsMargins(8, 3, 8, 3); lay.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        stamp_label=QLabel(stamp); stamp_label.setObjectName('cardTime')
        direction_label=QLabel(direction); direction_label.setObjectName('cardTX' if direction=='TX' else 'cardRX')
        for label in (stamp_label,direction_label,QLabel('|')):
            lay.addWidget(label,0,Qt.AlignTop)
        body=QLabel(text); body.setTextFormat(Qt.PlainText); body.setWordWrap(True)
        f=body.font(); f.setPointSize(font_size); body.setFont(f)
        body.setMinimumWidth(0); body.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
        lay.addWidget(body,1)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.text_value)
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, reset_window=False):
        super().__init__()
        self.reset_window = reset_window
        self.window_restored = False
        self.paths = ensure_runtime_dirs()
        self.store = ConfigStore()
        self.transcript = TranscriptLogger()
        self.adif = ADIFLog()
        self.qsos = self.adif.load_recent(limit=None, record_order=True)
        self.radio: CIVController | None = None
        self.current_freq_hz: int | None = None
        self.connecting = False
        self.polling = False
        self.poll_failures = 0
        self.connection_generation = 0
        self.help_windows = {}
        self.pending_auto_log = None
        self.qso_revision = 0
        self.control_window = None
        self.tx_sequence = 0
        self.active_tx_id = None
        self.pending_manual = None
        self.auto_cq_active = False
        self.auto_cq_inflight = None
        self.auto_cq_remaining = 0
        self.auto_cq_deadline = None
        self.auto_cq_timer = QTimer(self)
        self.auto_cq_timer.setInterval(100)
        self.auto_cq_timer.timeout.connect(self._auto_cq_tick)
        self.settings_window = None
        self.closing = False
        self.exit_backup_done = False
        self.audio_input_busy = False
        self.audio_input_requested = False
        self.call_locked = False
        self.rx_buffer = ""
        self.last_spectrum: tuple[np.ndarray, np.ndarray] | None = None

        self.bridge = AudioBridge()
        self.bridge.tx_finished.connect(lambda token, ok, msg: self._tx_finished(ok, msg, token))
        self.bridge.char.connect(self._rx_char)
        self.bridge.level.connect(self._rx_level)
        self.bridge.spectrum.connect(self._spectrum_data)
        sr = int(self.store.data["audio"]["sample_rate"])
        self.audio = AudioEngine(sr, lambda ch: self.bridge.char.emit((self.audio.decode_generation, ch)), self.bridge.level.emit, self.bridge.spectrum.emit)
        self._apply_audio_config()

        self.setWindowTitle("PSRTTY 0.83")
        self.setWindowIcon(QIcon(str(resource_path("assets/psrtty.png"))))
        self.resize(1280, 800)
        self.setMinimumSize(320, 240)
        self._build_menu()
        self._build_ui()
        self._apply_style()
        self._setup_shortcuts()
        self._load_config_to_ui()
        self._refresh_latest_qsos()
        self._set_radio_controls()

        self.rx_idle_timer = QTimer(self); self.rx_idle_timer.setSingleShot(True); self.rx_idle_timer.setInterval(750); self.rx_idle_timer.timeout.connect(self._finalize_rx_card)
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(1200); self.poll_timer.timeout.connect(self._poll_radio)
        QTimer.singleShot(0, self, self._restart_audio_input)

    def _build_menu(self):
        mb = self.menuBar()
        filem = mb.addMenu("ファイル")
        self._act(filem, "logdataフォルダーを開く", self._open_log_dir)
        self.transcript_action = self._act(filem, "", self._open_transcript)
        self.adif_action = self._act(filem, "", self._open_adif)
        filem.aboutToShow.connect(self._refresh_log_menu)
        self._refresh_log_menu()
        cab = self._act(filem, "Cabrillo出力", self._cabrillo_notice); cab.setEnabled(True)
        filem.addSeparator(); self._act(filem, "終了", self.close)

        edit = mb.addMenu("編集")
        self._act(edit, "マクロ編集", self._edit_macros)
        self._act(edit, "バックアップ設定", self._backup_settings)

        radio = mb.addMenu("無線機")
        self.connect_action = self._act(radio, "接続", self.connect_radio)
        self.disconnect_action = self._act(radio, "切断", self.disconnect_radio)
        self.redetect_action = self._act(radio, "再検出", self._redetect)
        radio.addSeparator(); self._act(radio, "基本・無線機・Audio設定", self._settings)

        view = mb.addMenu("表示")
        self._act(view, "QSOログ", self._show_qso_log)
        width = view.addMenu("スペクトラム表示幅")
        for hz, label in [(500,"500 Hz"),(1000,"1 kHz"),(2000,"2 kHz"),(3000,"3 kHz")]:
            a = self._act(width, label, lambda checked=False, v=hz: self._set_spectrum_width(v)); a.setCheckable(True); a.setData(hz)
        fontm = view.addMenu("受信カード文字サイズ")
        for size in (10,12,14,16,18): self._act(fontm, f"{size} pt", lambda checked=False, v=size: self._set_card_font(v))
        latest = view.addMenu("最新QSO表示件数")
        for count in (2,4,6,8,10): self._act(latest, str(count), lambda checked=False, v=count: self._set_latest_count(v))

        helpm = mb.addMenu("ヘルプ")
        self._act(helpm, "初期設定ガイド", self._guide_initial)
        self._act(helpm, "起動コマンドフラグについて", self._guide_flags)
        self.update_action = self._act(helpm, "PSRTTYのバージョンアップ", self._upgrade_zip)
        helpm.addSeparator(); self._act(helpm, "PSRTTYについて", self._about)

    @staticmethod
    def _act(menu: QMenu, text: str, slot):
        a = QAction(text, menu); a.triggered.connect(slot); menu.addAction(a); return a

    def _build_ui(self):
        central = QWidget()
        viewport = QScrollArea(); viewport.setWidgetResizable(True)
        viewport.setFrameShape(QFrame.NoFrame); viewport.setWidget(central)
        self.setCentralWidget(viewport)
        outer = QVBoxLayout(central); outer.setContentsMargins(10, 1, 10, 6); outer.setSpacing(4)
        accent = QFrame(); accent.setFixedHeight(4); accent.setObjectName("accentLine"); outer.addWidget(accent)

        status = QHBoxLayout()
        self.rig_status = QPushButton("未接続"); self.rig_status.setObjectName("rigStatus")
        self.rig_status.clicked.connect(self._toggle_connection)
        self.rig_status.setToolTip("クリックで設定済みの無線機に接続")
        self.freq_label = QLabel("---.--- MHz"); self.freq_label.setObjectName("freqLabel")
        status.addWidget(self.rig_status); status.addSpacing(18); status.addWidget(self.freq_label)
        self.scope_window = None
        self.control_button = QPushButton("コントロール")
        self.control_button.clicked.connect(self._show_control)
        status.addWidget(self.control_button)
        self.scope_button = QPushButton("クロススコープ")
        self.scope_button.setCheckable(True)
        self.scope_button.setToolTip("受信音のクロススコープを別ウィンドウで表示")
        self.scope_button.toggled.connect(self._toggle_scope)
        status.addWidget(self.scope_button); status.addStretch(1)
        self.audio_status = QLabel("Audio IN: 未設定")
        status.addWidget(self.audio_status)
        outer.addLayout(status)

        main = QHBoxLayout(); main.setSpacing(10); outer.addLayout(main, 1)
        left = QVBoxLayout(); left.setSpacing(4); main.addLayout(left, 1)
        right = QVBoxLayout(); right.setSpacing(4); right.setContentsMargins(2,0,0,0); main.addLayout(right, 0)

        spectrum_box = HintGroupBox("Audio Spectrum", "クリックで受信位置を調整")
        sv = QVBoxLayout(spectrum_box); sv.setContentsMargins(8,8,8,7)
        self.spectrum = SpectrumWidget(); self.spectrum.frequency_clicked.connect(self._spectrum_click); self.spectrum.tones_dragged.connect(self._set_tones); self.spectrum.tones_committed.connect(self.store.save); sv.addWidget(self.spectrum)
        controls = QHBoxLayout()
        self.tone_label = QLabel("Mark 2125 Hz   Center 2210 Hz   Space 2295 Hz")
        controls.addWidget(self.tone_label); controls.addStretch(1)
        controls.addWidget(QLabel("RX"))
        self.level = QProgressBar(); self.level.setRange(0,100); self.level.setTextVisible(False)
        self.level.setFixedSize(85, 20); self.level.setToolTip("USB Audioの受信音声レベル")
        controls.addWidget(self.level)
        controls.addWidget(QLabel('表示感度'))
        self.spectrum_gain=QSlider(Qt.Horizontal); self.spectrum_gain.setRange(-30,40); self.spectrum_gain.setFixedWidth(90)
        self.spectrum_gain.setValue(int(self.store.data['ui'].get('spectrum_gain_db',0)))
        self.spectrum.set_gain(self.spectrum_gain.value()); self.spectrum_gain.valueChanged.connect(self._spectrum_gain_changed)
        self.spectrum_gain.setToolTip('波形の表示だけを調整します。受信音量・デコードには影響しません。')
        controls.addWidget(self.spectrum_gain); sv.addLayout(controls)
        controls=QHBoxLayout(); controls.addWidget(QLabel('シフト幅'))
        self.shift_edit=QLineEdit(str(self.store.data['advanced']['shift_hz'])); self.shift_edit.setFixedWidth(86)
        self.shift_edit.setMaxLength(12); self.shift_edit.editingFinished.connect(self._shift_changed)
        self.shift_edit.setToolTip('10～2000 Hz。MARKを固定し、SPACEを移動します。')
        controls.addWidget(self.shift_edit); controls.addWidget(QLabel('Hz')); controls.addStretch(1)
        auto = QPushButton("AUTO TUNE"); auto.clicked.connect(self._auto_tune); controls.addWidget(auto)
        reset = QPushButton("幅RESET"); reset.clicked.connect(self._reset_170); controls.addWidget(reset)
        reset.setToolTip('MARK位置を保ってシフト幅を170 Hzに戻します。')
        position=QPushButton('位置RESET'); position.clicked.connect(self._reset_position); controls.addWidget(position)
        position.setToolTip('現在のシフト幅を保ってMARKを2125 Hzに戻します。')
        sv.addLayout(controls); left.addWidget(spectrum_box)

        self.decode_enabled=QCheckBox('デコード'); self.decode_enabled.setChecked(True)
        self.decode_enabled.setToolTip('OFFで文字のデコードと自動取得を停止。音声入力・スペクトラムは継続します。')
        self.decode_enabled.toggled.connect(self._set_decode_enabled)
        self.decode_sq = QComboBox()
        for level in range(11): self.decode_sq.addItem('OFF' if level == 0 else str(level), level)
        sq = max(0, min(10, int(self.store.data['ui'].get('decode_sq',4))))
        self.decode_sq.setCurrentIndex(sq); self.audio.set_decode_sq(sq)
        self.decode_sq.currentIndexChanged.connect(self._set_decode_sq)
        header = QWidget(); header_row = QHBoxLayout(header)
        header_row.setContentsMargins(4,0,4,0); header_row.setSpacing(5)
        header_row.addWidget(QLabel('SQ')); header_row.addWidget(self.decode_sq); header_row.addWidget(self.decode_enabled)
        cards_box = HeaderControlGroupBox("デコード", header)
        self.decode_group = cards_box
        cards_layout = QVBoxLayout(cards_box); cards_layout.setContentsMargins(5,max(12,header.sizeHint().height()),5,5)
        self.cards_scroll = QScrollArea(); self.cards_scroll.setWidgetResizable(True); self.cards_scroll.setMinimumHeight(120)
        self.cards_host = QWidget(); self.cards_layout = QVBoxLayout(self.cards_host); self.cards_layout.setAlignment(Qt.AlignTop); self.cards_layout.setSpacing(3)
        self.cards_scroll.setWidget(self.cards_host); cards_layout.addWidget(self.cards_scroll); left.addWidget(cards_box, 1)

        pending = QGroupBox("現在のQSO")
        grid = QGridLayout(pending); grid.setHorizontalSpacing(7); grid.setVerticalSpacing(4)
        self.auto_get = QCheckBox('自動取得')
        self.auto_get.setToolTip('受信文からCALL・RST-R・RCVDを取得します。各欄は手修正できます。')
        self.sent_fixed = QCheckBox('固定')
        self.sent_fixed.setToolTip('ON: SENTを保持。OFF: ログ追加成功時に数値を+1。数字以外は保持。送信だけでは増えません。')
        for i, title in enumerate(['CALL', 'RST-S', 'RST-R', 'SENT', 'RCVD']):
            header = QHBoxLayout(); header.addWidget(QLabel(title))
            if i == 0: header.addWidget(self.auto_get)
            if i == 3: header.addWidget(self.sent_fixed)
            header.addStretch(1); grid.addLayout(header, 0, i)
        self.q_call = QLineEdit(); self.q_call.setPlaceholderText('例: JX1XXX')
        self.his_call = self.q_call  # One CALL field; preserve internal/test API.
        self.q_call.textEdited.connect(self._his_call_edited)
        self.rst_s = QLineEdit('599'); self.rst_r = QLineEdit('599')
        self.sent = QLineEdit(self.store.data['qso']['sent']); self.rcvd = QLineEdit()
        self.sent_fixed.setChecked(self.store.data['qso']['sent_fixed'])
        fields=[self.q_call,self.rst_s,self.rst_r,self.sent,self.rcvd]
        for i,w in enumerate(fields): grid.addWidget(w,1,i)
        self.auto_log = QCheckBox("TU 73送出で自動ログ追加"); grid.addWidget(self.auto_log,2,0,1,2)
        self.q_datetime = QSODatetime()
        self.q_date = self.q_datetime.date; self.q_time = self.q_datetime.time
        grid.addWidget(self.q_datetime,2,2,1,2)
        for field in fields + [self.q_datetime]:
            field.textChanged.connect(self._qso_edited)
        add = QPushButton("↓ ログに追加"); add.setObjectName("logButton"); add.clicked.connect(self._add_qso); grid.addWidget(add,2,4)
        left.addWidget(pending)

        latest_box = self.latest_box = FooterHintGroupBox("最新QSO")
        lv = QVBoxLayout(latest_box)
        lv.setContentsMargins(9, 9, 9, 22)
        self.latest_panel = QWidget()
        tables_layout = QHBoxLayout(self.latest_panel)
        tables_layout.setContentsMargins(0,0,0,0); tables_layout.setSpacing(14)
        self.latest_table = QTableWidget(0,7)
        self.latest_right = QTableWidget(0,7)
        for table in (self.latest_table, self.latest_right):
            table.setHorizontalHeaderLabels(["No.","日時（JST）","CALL","RST-S","SENT","RST-R","RCVD"])
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.verticalHeader().setDefaultSectionSize(24)
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            table.setMinimumWidth(0)
            table.setToolTip("ダブルクリックでQSOログを開く")
            table.doubleClicked.connect(lambda *_: self._show_qso_log())
            tables_layout.addWidget(table,1)
        lv.addWidget(self.latest_panel); left.addWidget(latest_box)

        my = QGroupBox("自局")
        myl = QVBoxLayout(my); row=QHBoxLayout(); self.my_call=QLineEdit(); self.my_call.setPlaceholderText("自局コールサイン"); setb=QPushButton("SET"); setb.clicked.connect(self._set_my_call); row.addWidget(self.my_call,1); row.addWidget(setb); myl.addLayout(row); right.addWidget(my)

        auto_cq_box = QGroupBox('Auto CQ')
        cq = QVBoxLayout(auto_cq_box); cq.setContentsMargins(8, 6, 8, 6); cq.setSpacing(4)
        start_row = QHBoxLayout()
        self.auto_cq_button = QPushButton('Auto CQ開始')
        self.auto_cq_button.setMinimumHeight(44)
        self.auto_cq_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.auto_cq_button.clicked.connect(self._start_auto_cq)
        self.auto_cq_stop = QPushButton('STOP'); self.auto_cq_stop.setObjectName('stopButton')
        self.auto_cq_stop.clicked.connect(self._stop_tx)
        start_row.addWidget(self.auto_cq_button, 1); start_row.addWidget(self.auto_cq_stop)
        cq.addLayout(start_row)
        options = QHBoxLayout()
        self.cq_count = NumberEdit(10, self.store.data['auto_cq']['count'])
        self.cq_interval = NumberEdit(7, self.store.data['auto_cq']['interval_seconds'])
        options.addWidget(QLabel('回数')); options.addWidget(self.cq_count); options.addWidget(QLabel('回'))
        options.addStretch(1); options.addWidget(QLabel('間隔')); options.addWidget(self.cq_interval); options.addWidget(QLabel('秒'))
        self.cq_interval.setToolTip('送信終了・PTT解除後から次の送信までの受信待機時間')
        cq.addLayout(options); right.addWidget(auto_cq_box)

        self.offline_tx = QCheckBox('未接続でもMACROと手動送信可')
        self.offline_tx.setChecked(False)
        self.offline_tx.setToolTip('音声出力テスト用。未接続時はPTTを操作しません。Auto CQは接続必須です。')
        self.offline_tx.toggled.connect(self._offline_tx_changed)
        right.addWidget(self.offline_tx)

        macro_box = QGroupBox("TX MACRO")
        mv=QGridLayout(macro_box); self.macro_layout=mv; self.macro_buttons=[]; self.macro_previews=[]
        positions = [(0,0,1),(0,1,1),(1,0,2),(2,0,2),(4,0,1),(4,1,1),(5,0,1),(5,1,1),(6,0,2)]
        mv.setColumnStretch(0,1); mv.setColumnStretch(1,1)
        macro_box.setMinimumWidth(280)
        for i in range(9):
            b=QPushButton(); b.setMinimumWidth(110); b.setMinimumHeight(48)
            b.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            b.clicked.connect(lambda checked=False, idx=i: self._send_macro(idx))
            row,col,span=positions[i]; mv.addWidget(b,row,col,1,span); self.macro_buttons.append(b)
        separator = QFrame(); separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(3); mv.addWidget(separator,3,0,1,2)
        right.addWidget(macro_box,1)

        tx_box=QGroupBox("手動送信")
        tv=QVBoxLayout(tx_box); self.manual_tx=QLineEdit(); self.manual_tx.setPlaceholderText("自由送信テキスト")
        tv.addWidget(self.manual_tx); rr=QHBoxLayout(); send=QPushButton("TX"); self.send_button=send; send.clicked.connect(self._send_manual); stop=QPushButton("STOP"); stop.setObjectName("stopButton"); stop.clicked.connect(self._stop_tx); rr.addWidget(send); rr.addWidget(stop); tv.addLayout(rr); right.addWidget(tx_box)
        for field in [self.q_call, self.my_call, self.rst_s, self.rst_r, self.sent, self.rcvd]:
            field.textChanged.connect(self._refresh_macros)
        self.sent.textChanged.connect(self._remember_qso_options)
        self.sent_fixed.toggled.connect(self._remember_qso_options)
        self.auto_get.toggled.connect(lambda value: self.store.data['ui'].update(auto_get_call=value))
        self.auto_log.toggled.connect(lambda value: self.store.data['ui'].update(auto_log=value))
        self.cq_count.editingFinished.connect(self._remember_cq_options)
        self.cq_interval.editingFinished.connect(self._remember_cq_options)

    def _apply_style(self):
        self.setStyleSheet("""
        QMainWindow, QWidget { background: #fffaf3; color: #2f241b; }
        QMenuBar { background: #f5e6d2; padding: 0px; }
        QMenuBar::item { padding: 2px 8px; margin: 0px; }
        QMenuBar::item:selected, QMenu::item:selected { background: #f3c98d; }
        #accentLine { background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #a84e00, stop:.45 #e88919, stop:1 #ffd39b); border-radius: 2px; }
        QGroupBox { border: 1px solid #dfb276; border-radius: 6px; margin-top: 8px; padding-top: 8px; font-weight: 600; background: #fffdf9; }
        QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0 4px; color: #9c4d08; }
        QPushButton { background: #f3b35c; border: 1px solid #c96e0a; border-radius: 5px; padding: 6px 10px; font-weight: 600; }
        QPushButton:disabled { background: #e5ded5; color: #9a9084; border-color: #c8bfb3; }
        QPushButton:hover { background: #ffc978; }
        QPushButton:pressed { background: #df8b25; padding-top: 7px; }
        #logButton { background: #e58c20; color: white; font-size: 14px; min-height: 22px; }
        #stopButton { background: #d96a4d; color: white; }
        QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #cdb99f; border-radius: 4px; padding: 4px; }
        #rxCard { background: #fff1d9; border: 1px solid #e1a45d; border-radius: 6px; }
        #txCard { background: #f5b39d; border: 1px solid #c94c2b; border-radius: 6px; }
        #cardTime { color: #7f6a57; }
        #cardRX { color: #145c32; font-weight: 700; }
        #cardTX { color: #b00000; font-weight: 700; }
        #rxCard QLabel, #txCard QLabel { background: transparent; }
        #rigStatus { color: #a34e00; font-weight: 700; }
        #freqLabel { font-size: 18px; font-weight: 700; color: #7a3800; }
        #helpText { color: #725d49; background: #fff4e6; border-radius: 4px; padding: 6px; }
        QProgressBar { border: 1px solid #c8a87f; background: #f5eee5; border-radius: 3px; }
        QProgressBar::chunk { background: #e88919; }
        """)

    def _setup_shortcuts(self):
        self.shortcuts=[]
        for i in range(9):
            s=QShortcut(QKeySequence(f"F{i+1}"), self); s.activated.connect(lambda idx=i: self._send_macro(idx)); self.shortcuts.append(s)
        esc=QShortcut(QKeySequence("Esc"), self); esc.activated.connect(self._stop_tx); self.shortcuts.append(esc)

    def _load_config_to_ui(self):
        d=self.store.data
        self.my_call.setText(d.get("station_callsign", ""))
        self.auto_get.setChecked(bool(d["ui"]["auto_get_call"])); self.auto_log.setChecked(bool(d["ui"]["auto_log"]))
        self.spectrum.set_width(d["advanced"]["spectrum_width_hz"]); self._update_tone_ui(); self._refresh_macros()
        self.audio.set_rx_gain(d["audio"]["rx_gain"])

    def _apply_audio_config(self):
        a=self.store.data["advanced"]
        rx=self.store.data['ui'].get('rx_tones',[a['mark_hz'],a['space_hz']])
        self.audio.configure_decoder(a['rtty_baud'],rx[0],rx[1],a['invert'])
        self.audio.set_rx_gain(self.store.data["audio"]["rx_gain"])

    def _restart_audio_input(self):
        self.audio_input_requested = True
        if self.audio_input_busy: return
        self.audio_input_busy = True
        self.audio_input_requested = False
        selection = 'UNSET' if self.closing else deepcopy(self.store.data['audio']['input_device'])
        self.audio_status.setText('Audio IN: 停止中' if self.closing else 'Audio IN: 切替中…')
        def work():
            self.audio.stop_input()
            if selection == 'UNSET': return False, 'Audio IN: 未設定'
            return self.audio.start_input(selection)
        def done(result, error):
            self.audio_input_busy = False
            if self.audio_input_requested:
                self._restart_audio_input(); return
            ok, message = result if not error else (False, str(error))
            self.audio_status.setText('Audio IN: 入力中' if ok else ('Audio IN: 未設定' if selection == 'UNSET' else 'Audio IN: 入力できません'))
            self.audio_status.setToolTip(message)
            if not ok:
                self.level.setValue(0)
                self.last_spectrum = None
                self.spectrum.set_data(np.array([]), np.array([]))
                if selection != 'UNSET': self.statusBar().showMessage(message, 10000)
        self.audio_input_job = BackgroundJob(self, work, done)

    def _set_my_call(self):
        self.my_call.setText(normalize_call(self.my_call.text()))
        self.store.data["station_callsign"]=self.my_call.text(); self.store.save(); self._refresh_macros()

    def _his_call_edited(self, text):
        self.call_locked = bool(normalize_call(text))
        self._refresh_macros()

    def _refresh_macros(self):
        vals=self._macro_values()
        for i,m in enumerate(self.store.macros):
            preview=expand_macro(m.get("text",""), vals)
            shown=self.macro_buttons[i].fontMetrics().elidedText(" ".join(preview.split()), Qt.ElideRight, max(60, self.macro_buttons[i].width()-24))
            self.macro_buttons[i].setToolTip(preview)
            self.macro_buttons[i].setText(f"{m.get('key',f'F{i+1}')}  {m.get('name','')}\n{shown}")

        self._refresh_auto_cq_button()

    def _remember_qso_options(self, *_):
        self.store.data['qso'].update(sent=self.sent.text(), sent_fixed=self.sent_fixed.isChecked())

    def _remember_cq_options(self, *_):
        self.store.data['auto_cq'].update(count=self.cq_count.value(), interval_seconds=self.cq_interval.value())

    def _macro_values(self):
        return {"MYCALL":normalize_call(self.my_call.text()),"HISCALL":normalize_call(self.his_call.text()),"RSTS":self.rst_s.text().strip(),"RSTR":self.rst_r.text().strip(),"SENT":self.sent.text().strip(),"RCVD":self.rcvd.text().strip(), "MYQTH":self.store.data["station"]["qth"], "MYJCCJCG":self.store.data["station"]["jcc_jcg"], "MYTXT":self.store.data["station"]["text"]}

    def _set_decode_sq(self, index):
        level = self.decode_sq.itemData(index)
        self.audio.set_decode_sq(level)
        self.rx_idle_timer.stop(); self.rx_buffer = ''
        self.store.data['ui']['decode_sq'] = level
        self.store.save()

    def _set_decode_enabled(self, enabled):
        self.audio.set_decode_enabled(enabled)
        self.rx_idle_timer.stop(); self.rx_buffer=''

    def _rx_char(self, ch):
        if not self.decode_enabled.isChecked() or self.active_tx_id is not None: return
        if isinstance(ch, tuple):
            generation, ch=ch
            if generation != self.audio.decode_generation: return
        if ch in "\r\n":
            if self.rx_buffer.strip(): self._finalize_rx_card()
            return
        self.rx_buffer += ch
        if len(self.rx_buffer)>300: self._finalize_rx_card()
        else: self.rx_idle_timer.start()

    def _finalize_rx_card(self):
        text=" ".join(self.rx_buffer.split()); self.rx_buffer=""
        if not text or not self.decode_enabled.isChecked(): return
        self.transcript.append("RX " + text)
        self._add_card(text,"RX")
        self._consider_auto_extract(text)

    def _add_card(self,text,direction):
        card=ReceiveCard(datetime.now(JST).strftime("%H:%M:%S"),text,direction,int(self.store.data["ui"]["rx_card_font_size"])); card.clicked.connect(self._card_selected); self.cards_layout.addWidget(card)
        while self.cards_layout.count()>30:
            item=self.cards_layout.takeAt(0); w=item.widget();
            if w: w.deleteLater()
        QTimer.singleShot(20, lambda: self.cards_scroll.verticalScrollBar().setValue(self.cards_scroll.verticalScrollBar().maximum()))

    def _card_selected(self,text):
        parsed=parse_exchange(text,self.my_call.text(), cqww=self.store.data.get("macro_template") == CQWW_TEMPLATE_NAME)
        if parsed.callsign:
            self.his_call.setText(parsed.callsign); self.q_call.setText(parsed.callsign); self.call_locked=True
        if parsed.rst: self.rst_r.setText(parsed.rst)
        if parsed.exchange: self.rcvd.setText(parsed.exchange)
        self._refresh_macros()

    def _consider_auto_extract(self,text):
        if not self.auto_get.isChecked() or self.active_tx_id is not None: return
        parsed=parse_exchange(text,self.my_call.text(), cqww=self.store.data.get("macro_template") == CQWW_TEMPLATE_NAME)
        if parsed.callsign and not self.call_locked:
            self.his_call.setText(parsed.callsign); self.q_call.setText(parsed.callsign); self.call_locked=True
        # Once the current station is locked, still accept exchange only when the line contains it or our own call.
        current=normalize_call(self.his_call.text())
        upper=text.upper()
        own = normalize_call(self.my_call.text())
        relevant=(not current) or (current in upper) or (bool(own) and own in upper)
        if relevant:
            if parsed.rst: self.rst_r.setText(parsed.rst)
            if parsed.exchange: self.rcvd.setText(parsed.exchange)
        self._refresh_macros()

    def _connected(self):
        return bool(self.radio and self.radio.status.connected and not self.connecting)

    def _manual_tx_allowed(self):
        return not self.closing and not self.connecting and (self._connected() or self.offline_tx.isChecked())

    def _offline_tx_changed(self):
        if not self.offline_tx.isChecked() and not self._connected(): self._stop_tx()
        self._set_radio_controls()

    def _set_radio_controls(self):
        ready = self._connected()
        self.rig_status.setText('接続中…' if self.connecting else ('接続' if ready else '未接続'))
        self.rig_status.setEnabled(not self.connecting)
        self.rig_status.setStyleSheet('background: #a9def5; color: #075aa6;' if ready else 'background: #e1e9ee; color: #a34e00;')
        for button in self.macro_buttons + [self.send_button]:
            button.setEnabled(self._manual_tx_allowed())
        for shortcut in self.shortcuts[:9]:
            shortcut.setEnabled(self._manual_tx_allowed())
        self.auto_cq_button.setEnabled(ready and not self.auto_cq_active and self.active_tx_id is None)
        self.connect_action.setEnabled(not ready and not self.connecting)
        self.disconnect_action.setEnabled(ready or self.connecting)
        self.redetect_action.setEnabled(not self.connecting)
        if self.control_window: self.control_window.refresh_enabled()

    def _send_macro(self, idx: int):
        if not self._manual_tx_allowed():
            return
        m = self.store.macros[idx]
        text = expand_macro(m.get("text", ""), self._macro_values())
        if not text:
            self._stop_tx()
            self.statusBar().showMessage(f"{m.get('key')} は空です", 3000); return
        self._manual_request(text, macro=m.get("completes_qso") is True)

    def _send_manual(self):
        text = self.manual_tx.text().strip()
        if text: self._manual_request(text)

    def _manual_request(self, text, macro=False):
        was_auto = self.auto_cq_active
        self._cancel_auto_cq()
        if was_auto and self.active_tx_id is not None:
            self.pending_auto_log = None
            self.pending_manual = (text, macro)
            self.audio.stop_tx()
            return
        if self.control_window and self.control_window.busy:
            self.control_window.pending = self.control_window.target = self.control_window.feature_pending = None
            self.pending_manual = (text, macro)
            QTimer.singleShot(50, self, self._resume_manual)
            return
        if self._send_text(text):
            if re.search(r'(?<![A-Z0-9/])TU\s*73(?![A-Z0-9/])', text, re.I):
                self.pending_auto_log = (self._macro_values(), self.qso_revision, self.current_freq_hz)

    def _resume_manual(self):
        if not self.pending_manual or self.closing: return
        if self.control_window and self.control_window.busy:
            QTimer.singleShot(50, self, self._resume_manual)
            return
        queued, self.pending_manual = self.pending_manual, None
        self._manual_request(*queued)

    def _send_text(self, text):
        if not self._manual_tx_allowed():
            self.statusBar().showMessage("無線機を接続してから送信してください", 3000)
            return False
        if self.active_tx_id is not None or self.audio._tx_active:
            self.statusBar().showMessage('送信終了を待ってください', 2500)
            return False
        if self.control_window:
            self.control_window.pending = self.control_window.target = self.control_window.feature_pending = None
            if self.control_window.busy:
                self.statusBar().showMessage("無線機操作の完了を待って送信してください", 2500)
                return False
        a=self.store.data["advanced"]; au=self.store.data["audio"]
        ctl = self.radio
        mode = self.store.data["radio"]["ptt"]
        offline = not self._connected()
        ptt = None if offline else {"CI-V": ctl.set_ptt, "CAT": ctl.set_ptt, "RTS": ctl.set_rts, "DTR": ctl.set_dtr}.get(mode)
        def on():
            if offline: return not self.closing
            return bool(ptt and self.radio is ctl and self._connected() and ptt(True))
        def off():
            return True if offline else (ptt(False) if ptt else False)
        self.tx_sequence += 1
        token = self.tx_sequence
        self.active_tx_id = token
        self.rx_idle_timer.stop(); self.rx_buffer = ''
        try:
            ok,msg=self.audio.send_text(text,au["output_device"],a["rtty_baud"],a["mark_hz"],a["space_hz"],a["invert"],au["tx_gain"],on,off,lambda ok, msg: self.bridge.tx_finished.emit(token, ok, msg))
        except Exception as exc:
            ok, msg = False, f'送信開始失敗: {exc}' 
        if ok:
            self.pending_auto_log = None
            self.transcript.append("TX " + text); self._add_card(text,"TX")
        if not ok: self.active_tx_id = None
        self._set_radio_controls()
        self.statusBar().showMessage(msg,4000)
        return ok

    def _auto_log_notice(self, reason):
        message = '自動ログ未追加: ' + reason
        self.statusBar().showMessage(message, 10000)
        self.transcript.append(message)

    def _tx_finished(self, success, message, token=None):
        if token is not None and token != self.active_tx_id:
            return  # Ignore stale callbacks from a previous TX.
        self.audio.set_decode_enabled(self.decode_enabled.isChecked())
        self.rx_idle_timer.stop(); self.rx_buffer = ''
        finished_id, self.active_tx_id = self.active_tx_id, None
        pending, self.pending_auto_log = self.pending_auto_log, None
        if success and pending and pending == (self._macro_values(), self.qso_revision, self.current_freq_hz):
            if self.auto_log.isChecked():
                if self.q_call.text().strip(): self._add_qso()
                else: self._auto_log_notice('相手CALLが空欄')
        elif success and pending:
            if pending[2] != self.current_freq_hz: reason = '送信中に周波数が変わりました'
            else: reason = '送信中に交信入力が編集されました。内容を確認して手動で追加してください'
            self._auto_log_notice(reason)
        elif not success:
            self.statusBar().showMessage(message, 6000)
            self.transcript.append("TX中止 " + message)
        if self.auto_cq_active and self.auto_cq_inflight == finished_id:
            self.auto_cq_inflight = None
            if not success:
                self._cancel_auto_cq()
            else:
                self.auto_cq_remaining -= 1
                if self.auto_cq_remaining <= 0:
                    self._cancel_auto_cq()
                    self.statusBar().showMessage('Auto CQ完了', 4000)
                else:
                    self.auto_cq_deadline = time.monotonic() + self.cq_interval.value()
                    self.auto_cq_timer.start()
        queued, self.pending_manual = self.pending_manual, None
        if queued and self._manual_tx_allowed() and not self.closing and (success or message == '送信中止'):
            self._manual_request(*queued)
        self._refresh_auto_cq_button(); self._set_radio_controls()

    def _refresh_auto_cq_button(self):
        if not hasattr(self, 'auto_cq_button'): return
        preview = expand_macro(self.store.macros[0].get('text', ''), self._macro_values())
        self.auto_cq_button.setToolTip('F1を繰り返し送信します。\n' + preview)
        if self.auto_cq_active:
            seconds = max(0, int(self.auto_cq_deadline - time.monotonic() + .999)) if self.auto_cq_deadline else None
            detail = f'次まで {seconds} 秒' if seconds is not None else '送信中'
            self.auto_cq_button.setText(f'Auto CQ 残り{self.auto_cq_remaining}回\n{detail}')
        else:
            shown = self.auto_cq_button.fontMetrics().elidedText(" ".join(preview.split()), Qt.ElideRight, max(60, self.auto_cq_button.width()-20))
            self.auto_cq_button.setText('Auto CQ開始\n' + shown)

    def _start_auto_cq(self):
        if not self._connected() or self.auto_cq_active or self.active_tx_id is not None or self.audio._tx_active:
            return
        if not expand_macro(self.store.macros[0].get('text', ''), self._macro_values()):
            self.statusBar().showMessage('F1が空のためAuto CQを開始できません', 4000); return
        self.cq_count.normalize(); self.cq_interval.normalize(); self._remember_cq_options()
        self.auto_cq_active = True
        self.auto_cq_remaining = self.cq_count.value()
        self.cq_count.setEnabled(False); self.cq_interval.setEnabled(False)
        self._auto_cq_send()

    def _auto_cq_send(self):
        if not self.auto_cq_active: return
        if self.control_window and self.control_window.busy:
            QTimer.singleShot(50, self, self._auto_cq_send)
            return
        self.auto_cq_timer.stop(); self.auto_cq_deadline = None
        text = expand_macro(self.store.macros[0].get('text', ''), self._macro_values())
        if not text or not self._connected() or not self._send_text(text):
            self._cancel_auto_cq(); return
        self.auto_cq_inflight = self.active_tx_id
        self._refresh_auto_cq_button()

    def _auto_cq_tick(self):
        if not self.auto_cq_active or not self._connected():
            self._cancel_auto_cq(); return
        if self.auto_cq_deadline is not None and time.monotonic() >= self.auto_cq_deadline:
            self._auto_cq_send()
        self._refresh_auto_cq_button()

    def _cancel_auto_cq(self):
        self.auto_cq_active = False
        self.auto_cq_timer.stop(); self.auto_cq_deadline = None; self.auto_cq_inflight = None
        self.cq_count.setEnabled(True); self.cq_interval.setEnabled(True)
        self._refresh_auto_cq_button(); self._set_radio_controls()

    def _stop_tx(self):
        self._cancel_auto_cq()
        self.pending_manual = None
        self.pending_auto_log = None
        self.audio.stop_tx()
        self.statusBar().showMessage("送信停止",2500)

    def _ptt_on(self):
        if not self._connected():
            return False
        mode = self.store.data["radio"]["ptt"]
        if mode in ("CI-V", "CAT"): return self.radio.set_ptt(True)
        if mode == "RTS": return self.radio.set_rts(True)
        if mode == "DTR": return self.radio.set_dtr(True)
        return False

    def _ptt_off(self):
        if not (self.radio and self.radio.status.connected):
            return
        mode = self.store.data["radio"]["ptt"]
        if mode in ("CI-V", "CAT"): self.radio.set_ptt(False)
        elif mode == "RTS": self.radio.set_rts(False)
        elif mode == "DTR": self.radio.set_dtr(False)

    def _qso_edited(self):
        self.qso_revision += 1

    def _add_qso(self):
        call=normalize_call(self.q_call.text() or self.his_call.text())
        if not call:
            QMessageBox.warning(self,"ログに追加","相手コールサインがありません。"); return
        try:
            stamp = self.q_datetime.text().strip() if self.q_datetime.manual.isChecked() else ""
            when = datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=JST).astimezone(timezone.utc) if stamp else datetime.now(timezone.utc)
        except ValueError:
            QMessageBox.warning(self, "ログに追加", "日時を YYYY-MM-DD HH:MM で入力してください。")
            return
        q=QSORecord(call=call,rst_sent=self.rst_s.text().strip() or "599",rst_rcvd=self.rst_r.text().strip() or "599",sent=self.sent.text().strip(),rcvd=self.rcvd.text().strip(),station_callsign=normalize_call(self.my_call.text()),freq_hz=self.current_freq_hz,when_utc=when)
        try:
            path=self.adif.append(q)
        except Exception as exc:
            QMessageBox.warning(self, 'ログに追加', f'保存に失敗しました。入力は保持しています。\n{exc}')
            return
        self.pending_auto_log = None
        self.q_datetime.clear()
        self.qsos.append(q)
        backup = self.store.data.setdefault("backup", {})
        backup["pending_qsos"] = max(0, int(backup.get("pending_qsos", 0))) + 1
        if not self.sent_fixed.isChecked() and re.fullmatch(r'[0-9]+', q.sent):
            self.sent.setText(str(int(q.sent) + 1).zfill(len(q.sent)))
        self._remember_qso_options()
        settings_error = None
        try:
            self.store.save()
        except Exception as exc:
            settings_error = exc
        self.transcript.append(f"QSO {call} RSTS={q.rst_sent} SENT={q.sent} RSTR={q.rst_rcvd} RCVD={q.rcvd}")
        self.statusBar().showMessage(f"{call} を {path.name} に追加しました",4000)
        self._refresh_latest_qsos(); self.his_call.clear(); self.q_call.clear(); self.rcvd.clear(); self.call_locked=False; self._refresh_macros()
        if backup.get("every_enabled", False) and backup["pending_qsos"] >= max(1, int(backup.get("every_count", 30))):
            self._backup_logs()
        if settings_error is not None:
            QMessageBox.warning(self, '設定の保存', f'QSOはADIFへ保存済みです。再度追加する必要はありません。\nSENTなどの設定を保存できませんでした。\n{settings_error}')

    def _refresh_latest_qsos(self):
        count=int(self.store.data["ui"]["latest_qso_count"])
        total=len(self.qsos)
        self.latest_box.set_footer(f"ログ合計 {total}件")
        rows=list(reversed(self.qsos[-count:]))
        fm=self.latest_table.fontMetrics()
        widths=[max(30, fm.horizontalAdvance(str(total))+8),fm.horizontalAdvance('2026-09-24 23:59')+8,fm.horizontalAdvance('JH1HST/1')+8]
        widths += [max(36,fm.horizontalAdvance(label)+6) for label in ('RST-S','SENT','RST-R','RCVD')]
        columns=2 if self.latest_panel.width()-14-8>=2*sum(widths) else 1
        self.latest_right.setVisible(columns == 2)
        tables=(self.latest_table,self.latest_right)
        for table in tables:
            table.clearContents()
            table.setRowCount((len(rows)+columns-1)//columns)
            for c,width in enumerate(widths): table.setColumnWidth(c,width)
            height=table.horizontalHeader().sizeHint().height()+((count+columns-1)//columns)*24+4
            table.setFixedHeight(height)
        for i,q in enumerate(rows):
            stamp=q.when_utc.astimezone(JST).strftime("%Y-%m-%d %H:%M") if q.when_utc else ""
            for c,v in enumerate([total-i,stamp,q.call,q.rst_sent,q.sent,q.rst_rcvd,q.rcvd]):
                item=QTableWidgetItem(str(v)); item.setToolTip(str(v))
                tables[i%columns].setItem(i//columns,c,item)

    def _toggle_connection(self):
        if self.connecting: return
        if self._connected(): self.disconnect_radio()
        else: self.connect_radio()

    def connect_radio(self):
        if self.closing or self.connecting or self._connected() or (self.settings_window and self.settings_window.isVisible()):
            return
        cleanup = getattr(self, "cleanup_job", None)
        if cleanup and cleanup.thread.is_alive():
            self.statusBar().showMessage("切断処理中です。少し待って再接続してください", 3000)
            return
        if self.active_tx_id is not None or self.audio._tx_active:
            self.statusBar().showMessage('音声出力を停止してから接続してください', 3000); return
        values = deepcopy(self.store.data["radio"])
        advanced = deepcopy(self.store.data["advanced"])
        try:
            ctl = create_controller(values)
        except ValueError as exc:
            QMessageBox.warning(self, "無線機", str(exc)); return
        self.radio = ctl
        self.connecting = True
        generation = self.connection_generation
        self.rig_status.setText("接続確認中…（最大約10秒・切断で中止）")
        self._set_radio_controls()
        def done(status, error):
            if generation != self.connection_generation:
                return
            self.connecting = False
            if error or not status.connected:
                self.rig_status.setText("未接続")
                self.statusBar().showMessage(str(error) if error else status.message, 10000)
            else:
                self.rig_status.setText(f"{values['model']}  {status.port}  接続")
                self.current_freq_hz = status.frequency_hz
                self.poll_failures=0; self.rig_status.setToolTip(f"{values['model']}  {status.port}\nクリックで切断"); self._update_freq_label(); self.poll_timer.start()
                self.statusBar().showMessage('無線機に接続しました', 5000)
            self._set_radio_controls()
        self.connection_job = BackgroundJob(self, lambda: connect_configured(ctl, values, advanced), done)
        def deadline():
            if generation == self.connection_generation and self.connecting:
                self.disconnect_radio()
                self.statusBar().showMessage("接続がタイムアウトしました", 8000)
        QTimer.singleShot(10000, self, deadline)

    def disconnect_radio(self):
        self.connection_generation += 1
        self.poll_timer.stop(); self.poll_failures=0; self._stop_tx()
        ctl, self.radio = self.radio, None
        self.connecting = False
        if ctl:
            # Release PTT before closing serial; worker does not block the UI.
            ctl.cancel.set()
            mode = self.store.data["radio"]["ptt"]
            def cleanup():
                self.audio.wait_tx(2.0)
                if ctl.status.connected:
                    {"CI-V": ctl.set_ptt, "CAT": ctl.set_ptt, "RTS": ctl.set_rts, "DTR": ctl.set_dtr}.get(mode, ctl.set_ptt)(False)
                ctl.disconnect()
            self.cleanup_job = BackgroundJob(self, cleanup, lambda *_: None)
        self.rig_status.setText("未接続"); self.rig_status.setToolTip("クリックで設定済みの無線機に接続"); self.current_freq_hz=None; self._update_freq_label()
        self._set_radio_controls()

    def _redetect(self):
        self.disconnect_radio()
        # Cleanup owns the old port briefly; reconnect only once it has closed.
        def retry():
            if hasattr(self, "cleanup_job") and self.cleanup_job.thread.is_alive():
                QTimer.singleShot(100, retry)
            else:
                self.connect_radio()
        QTimer.singleShot(100, retry)

    def _poll_radio(self):
        if not self._connected() or self.polling or self.audio._tx_active or (self.control_window and self.control_window.busy):
            return
        ctl = self.radio
        generation = self.connection_generation
        self.polling = True
        def done(freq, error):
            self.polling = False
            if generation != self.connection_generation:
                return
            self._radio_observed(freq, error)
        self.poll_job = BackgroundJob(self, ctl.read_frequency, done)
    def _radio_observed(self, freq, error=None):
        if error or not freq:
            self.poll_failures += 1
            if self.poll_failures < 3:
                self.statusBar().showMessage(f'無線機の応答を再確認中（{self.poll_failures}/3）')
                return
            stamp=datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')
            reason=f'{stamp} 無線機の応答を3回連続で取得できなかったため切断しました'
            self.disconnect_radio()
            self.rig_status.setToolTip(reason)
            self.statusBar().showMessage(reason); self.transcript.append(reason)
        else:
            if self.poll_failures: self.statusBar().showMessage('無線機の応答が戻りました',4000)
            self.poll_failures=0
            self.current_freq_hz=freq; self._update_freq_label()

    def _update_freq_label(self):
        self.freq_label.setText(frequency_text(self.current_freq_hz))
        if self.control_window: self.control_window.observe_frequency(self.current_freq_hz)

    def _toggle_scope(self, visible):
        if visible:
            if self.scope_window is None:
                from .cross_scope import CrossScopeWindow
                self.scope_window = CrossScopeWindow(self.audio, self)
                self.scope_window.finished.connect(lambda _: self.scope_button.setChecked(False))
            self.scope_window.show()
            self.scope_window.raise_()
        elif self.scope_window is not None:
            self.scope_window.hide()

    def _show_control(self):
        from .control_window import ControlWindow
        if self.control_window is None:
            self.control_window = ControlWindow(self)
        self.control_window.reveal()

    def _rx_level(self,v): self.level.setValue(int(max(0,min(1,float(v)))*100))
    def _spectrum_data(self,f,p): self.last_spectrum=(np.asarray(f),np.asarray(p)); self.spectrum.set_data(self.last_spectrum[0],self.last_spectrum[1])

    def _auto_tune(self):
        if not self.last_spectrum:
            self.statusBar().showMessage("まだスペクトラムデータがありません",3000); return
        freqs,power=self.last_spectrum; a=self.store.data["advanced"]; shift=abs(self.spectrum.space_hz-self.spectrum.mark_hz); tol=float(a["auto_tune_tolerance_hz"])
        center=(self.spectrum.mark_hz+self.spectrum.space_hz)/2; width=float(a["spectrum_width_hz"]); mask=(freqs>=center-width/2)&(freqs<=center+width/2)
        f=freqs[mask]; p=power[mask]
        if len(f)<4: return
        # Find the strongest pair whose spacing is close to configured shift.
        top=np.argsort(p)[-min(40,len(p)):]
        best=None
        for i in top:
            for j in top:
                if j<=i: continue
                sep=abs(float(f[j]-f[i])); err=abs(sep-shift)
                if err<=tol:
                    score=float(p[i]+p[j])-err*0.15
                    if best is None or score>best[0]: best=(score,float(f[i]),float(f[j]))
        if not best:
            self.statusBar().showMessage(f"{shift:g} Hz付近の2ピークを確認できませんでした",3500); return
        mark,space=best[1],best[2]
        # Keep configured polarity; visual left/right assignment follows configured tone order.
        if self.spectrum.mark_hz>self.spectrum.space_hz: mark,space=space,mark
        self._set_tones(mark,space); self.statusBar().showMessage(f"AUTO TUNE: {mark:.0f} / {space:.0f} Hz",3000)

    def _spectrum_gain_changed(self, value):
        self.spectrum.set_gain(value)
        self.store.data['ui']['spectrum_gain_db']=value
        self.store.save()

    def _set_tones(self, mark, space, save=True):
        mark,space=float(mark),float(space)
        if not (100<=mark<=3900 and 100<=space<=3900): return False
        if not 10<=abs(space-mark)<=2000: return False
        a=self.store.data['advanced']
        self.store.data['ui']['rx_tones']=[mark,space]
        self.spectrum.set_tones(mark,space)
        self.audio.configure_decoder(a['rtty_baud'],mark,space,a['invert'])
        self._update_tone_ui(mark,space)
        if save and self.spectrum.drag is None: self.store.save()
        return True

    def _shift_changed(self):
        a=self.store.data['advanced']
        try:
            width=float(self.shift_edit.text())
            sign=1 if self.spectrum.space_hz>=self.spectrum.mark_hz else -1
            if not self._set_tones(self.spectrum.mark_hz,self.spectrum.mark_hz+sign*width): raise ValueError()
        except ValueError:
            self.shift_edit.setText(f'{abs(self.spectrum.space_hz-self.spectrum.mark_hz):g}')
            self.statusBar().showMessage('シフト幅は10～2000 Hz、MARK／SPACEは100～3900 Hzの範囲です。',5000)

    def _reset_170(self):
        sign=1 if self.spectrum.space_hz>=self.spectrum.mark_hz else -1
        if not self._set_tones(self.spectrum.mark_hz,self.spectrum.mark_hz+sign*170):
            self.statusBar().showMessage('幅170 Hzが範囲外です。先に位置RESETを押してください。',4000)

    def _reset_position(self):
        delta=self.spectrum.space_hz-self.spectrum.mark_hz
        if not self._set_tones(2125,2125+delta):
            self.statusBar().showMessage('この幅では標準位置に戻せません。先に幅RESETを押してください。',4000)

    def _spectrum_click(self,hz):
        delta=self.spectrum.space_hz-self.spectrum.mark_hz
        hz=max(100-min(0,delta),min(3900-max(0,delta),hz))
        self._set_tones(hz,hz+delta)

    def _update_tone_ui(self,mark=None,space=None):
        a=self.store.data['advanced']
        rx=self.store.data['ui'].get('rx_tones',[a['mark_hz'],a['space_hz']])
        mark=float(rx[0] if mark is None else mark); space=float(rx[1] if space is None else space)
        self.spectrum.set_tones(mark,space)
        self.tone_label.setText(f'Mark {mark:.0f} Hz   Center {(mark+space)/2:g} Hz   Space {space:.0f} Hz')
        if not self.shift_edit.hasFocus(): self.shift_edit.setText(f'{abs(space-mark):g}')

    def _settings(self):
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.raise_(); return
        self.disconnect_radio()
        self.store.data['station_callsign'] = normalize_call(self.my_call.text())
        old_tones=tuple(self.store.data['advanced'][k] for k in ('mark_hz','space_hz','shift_hz'))
        dlg = self.settings_window = SettingsDialog(self.store, self)
        dlg.setWindowModality(Qt.NonModal)
        def finished(result):
            if result:
                if old_tones!=tuple(self.store.data['advanced'][k] for k in ('mark_hz','space_hz','shift_hz')):
                    self.store.data['ui'].pop('rx_tones',None); self.store.save()
                # If the dialog CALL was untouched, keep concurrent main edits.
                if not dlg.basic_call_changed():
                    self.store.data['station_callsign'] = normalize_call(self.my_call.text())
                    self.store.save()
                self._apply_audio_config(); self._load_config_to_ui(); self._restart_audio_input()
                self.statusBar().showMessage("設定を保存しました。無線機を再接続してください", 4000)
                if dlg.connect_requested:
                    QTimer.singleShot(0, self, self._connect_after_settings)
            self.connect_action.setEnabled(True); self.redetect_action.setEnabled(True)
        dlg.finished.connect(finished)
        self.connect_action.setEnabled(False); self.redetect_action.setEnabled(False)
        dlg.show()
    def _connect_after_settings(self):
        if self.closing: return
        cleanup = getattr(self, "cleanup_job", None)
        if cleanup and cleanup.thread.is_alive():
            QTimer.singleShot(100, self, self._connect_after_settings)
        else:
            self.connect_radio()

    def _edit_macros(self):
        self._stop_tx()
        dlg=MacroDialog(self.store,self)
        if dlg.exec(): self._refresh_macros()
    def _show_qso_log(self):
        dlg=QSOLogDialog(self.adif,self)
        dlg.changed.connect(self._reload_qsos)
        dlg.exec()

    def _reload_qsos(self):
        self.qsos=self.adif.load_recent(limit=None, record_order=True)
        self._refresh_latest_qsos()
    def _about(self): AboutDialog(self).exec()

    def _set_spectrum_width(self,v): self.store.data["advanced"]["spectrum_width_hz"]=v; self.store.save(); self.spectrum.set_width(v)
    def _set_card_font(self,v): self.store.data["ui"]["rx_card_font_size"]=v; self.store.save(); self.statusBar().showMessage("新しいカードから文字サイズを反映します",2500)
    def _set_latest_count(self,v): self.store.data["ui"]["latest_qso_count"]=v; self.store.save(); self._refresh_latest_qsos()

    def _open_path(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists() and path.suffix: path.touch()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def _refresh_log_menu(self):
        self.transcript_action.setText("今日の生ログTXTを開く（JST基準）")
        self.adif_action.setText("今月のADIFを開く（UTC基準）")

    def _backup_settings(self):
        from .backup_dialog import BackupDialog
        BackupDialog(self.store, lambda: self._backup_logs(manual=True), self).exec()

    def _backup_logs(self, manual=False):
        from ..backup import create_log_backup
        try:
            path = create_log_backup(self.paths["logdata"])
        except Exception as exc:
            QMessageBox.warning(self, "ログバックアップ", f"バックアップに失敗しました。元のログは保持しています。\n{exc}")
            return False
        if path is None:
            if manual: QMessageBox.information(self, "ログバックアップ", "バックアップするログがありません。")
            return True
        self.store.data.setdefault("backup", {})["pending_qsos"] = 0
        try:
            self.store.save()
        except Exception as exc:
            QMessageBox.warning(self, "ログバックアップ", f"バックアップは保存済みです：{path}\n件数設定の保存に失敗しました：{exc}")
        self.statusBar().showMessage(f"バックアップを保存しました：{path.name}", 10000)
        if manual: QMessageBox.information(self, "ログバックアップ", f"バックアップを保存しました。\n{path}")
        return True

    def _open_log_dir(self): self._open_path(self.paths["logdata"])
    def _open_transcript(self): self._open_path(self.transcript.ensure_file())
    def _open_adif(self): self._open_path(self.adif.ensure_file())
    def _cabrillo_notice(self):
        from .cabrillo_dialog import CabrilloDialog
        CabrilloDialog(self.adif, self.store, self).exec()

    def showEvent(self, event):
        super().showEvent(event)
        if not self.window_restored:
            self.window_restored = True
            QTimer.singleShot(0, self, lambda: restore_window(self, self.store.data["ui"].get("window"), self.reset_window))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "macro_buttons"):
            QTimer.singleShot(0, self, self._refresh_macros)
            QTimer.singleShot(0, self, self._refresh_latest_qsos)

    def _guide_flags(self):
        self._show_help("起動コマンドフラグについて", "psrtty.exe --reset-window\n\n保存されたウィンドウ位置・サイズ・最大化状態を無視して起動します。\n標準サイズは1280×800です。画面が狭い場合は表示可能範囲に縮小し、中央へ戻します。\n通常起動では前回の位置・サイズ・最大化状態を復元し、画面外なら画面内へ戻します。\n終了時に現在の状態を保存します。無線機設定・マクロ・ログは初期化しません。")

    def _guide_initial(self):
        from .guide import GuideWindow
        title='初期設定ガイド'
        win=self.help_windows.get(title)
        if win is None:
            win=GuideWindow(self); self.help_windows[title]=win
        win.showNormal(); win.raise_(); win.activateWindow()

    def _guide_ft8(self):
        self._show_help('FT8環境からの設定方法', 'FT8で使用中のCOMとAudioをPSRTTYでも選びます。FT8ソフトは終了し、COM・Audioの競合を避けてください。\n\nAudio IN：無線機 → パソコン（USB Audio／LINE IN／マイク）\nAudio OUT：パソコン → 無線機（USB Audio／LINE OUT／スピーカー）\n\nWindowsでは有効なWASAPIデバイスを表示し、機器IDで保存します。旧版の番号指定は初回に選び直してください。未接続の機器を別の機器へ自動置換しません。INの「未設定」は入力を停止します。設定済みなら起動時から入力し、無線機の接続とは独立しています。「自動」はWindowsの既定デバイスです。USB機器を追加した場合はPSRTTYを再起動してください。\n\n接続時LSB-D自動切替は初期ONです。YaesuではDATA-LSB／DATA-Lに相当します。無線機側のDATA入力をUSBに設定してください。USB-Dは高度な設定で選択でき、YaesuではDATA-USB／DATA-Uに相当します。Mark/Spaceの極性も実機で確認してください。\n\nYaesu FT-991/A・FTX-1は試験用・実機未確認です。Enhanced COM、CAT速度・ストップビットを無線機と合わせ、CAT RTSをDISABLE（OFF）にしてください。')

    def _guide_tuning(self): self._show_help("RTTYチューニング","スペクトラムのMARK/SPACEガイドに2本のピークを合わせます。\nAUTO TUNEは設定されたShift（標準170 Hz）付近の2ピークを探します。\n幅RESETと位置RESETの両方で標準のMark 2125 / Space 2295 Hzへ戻せます。\nクリックでMARKを移動。MARK／SPACEの線は間隔を保ってドラッグできます。\nメイン画面のシフト幅で間隔を変更します。幅RESETは170 Hzへ、位置RESETはMARK 2125 Hzへ戻します。\n表示感度は波形の高さだけを調整します。")

    def _show_help(self, title, text):
        window = self.help_windows.get(title)
        if window is None:
            window = QWidget(None, Qt.Window)
            window.setWindowTitle(title); window.resize(570, 360)
            layout = QVBoxLayout(window); body = QTextBrowser(); body.setPlainText(text); layout.addWidget(body)
            self.help_windows[title] = window
        window.show(); window.raise_(); window.activateWindow()

    def _upgrade_zip(self):
        from ..updater import inspect_zip, prepare_update, launch_updater
        from .. import __version__
        if not getattr(sys, "frozen", False) or sys.platform != "win32":
            QMessageBox.information(self, "バージョンアップ", "ZIP更新はWindows EXE版で利用できます。ソース実行時は新しいソース一式を別フォルダーへ展開してください。"); return
        from .update_dialog import UpdateDialog
        if not UpdateDialog(self).exec(): return
        path, _ = QFileDialog.getOpenFileName(self, "PSRTTY配布ZIPを選択", "", "ZIP (*.zip)")
        if not path: return
        self.update_action.setEnabled(False)
        def checked(info, error):
            self.update_action.setEnabled(True)
            if error:
                QMessageBox.warning(self, "更新ZIP", str(error)); return
            if QMessageBox.question(self, "バージョンアップ", f"Ver{__version__} → Ver{info['version']}\n設定・ログ・varのデータを保持し、更新前バックアップを作成します。\n信頼できる配布元のZIPであることを確認してください。\nPSRTTYを終了して更新し、自動で再起動しますか？") != QMessageBox.Yes:
                return
            self.disconnect_radio()
            if self.settings_window: self.settings_window.close()
            self.setEnabled(False)
            def prepared(stage, err):
                if err:
                    self.setEnabled(True); QMessageBox.warning(self, "更新準備", str(err)); return
                try:
                    self.store.save()
                    launch_updater(stage, self.paths["root"])
                    self.close()
                except Exception as exc:
                    self.setEnabled(True); QMessageBox.warning(self, "更新開始", str(exc))
            self.update_job = BackgroundJob(self, lambda: prepare_update(Path(path), self.paths["root"], __version__), prepared)
        self.update_job = BackgroundJob(self, lambda: inspect_zip(Path(path), __version__, self.paths["root"]), checked)

    def closeEvent(self,event):
        self.q_datetime.timer.stop()
        if not self.closing:
            self.closing = True
            self.scope_button.setChecked(False)
            if self.scope_window: self.scope_window.close()
            for window in self.help_windows.values(): window.close()
            if self.control_window: self.control_window.close()
            if self.settings_window: self.settings_window.close()
            self.cq_count.normalize(); self.cq_interval.normalize(); self._remember_cq_options()
            self.store.data["ui"]["auto_get_call"] = self.auto_get.isChecked()
            self.store.data["ui"]["auto_log"] = self.auto_log.isChecked()
            self.store.data["station_callsign"] = normalize_call(self.my_call.text())
            self.store.data["ui"]["window"] = save_window(self)
            try:
                self.store.save()
            except Exception as exc:
                QMessageBox.warning(self, "終了時の設定保存", f"設定を保存できませんでした。ログバックアップと終了処理を続けます。\n{exc}")
            self.disconnect_radio()
            self._restart_audio_input()
        cleanup = getattr(self, "cleanup_job", None)
        if self.audio_input_busy or (cleanup and cleanup.thread.is_alive()) or self.audio._tx_active:
            event.ignore()
            QTimer.singleShot(50, self.close)
        else:
            if not self.exit_backup_done:
                self.exit_backup_done = True
                if self.store.data.get("backup", {}).get("on_exit", True):
                    self._backup_logs()
            event.accept()
