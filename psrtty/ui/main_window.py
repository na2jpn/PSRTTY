from __future__ import annotations
from ..i18n import tr
from .. import __version__
from ..timebase import JST, display_zone

import os
import re
import sys
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QFont, QFontMetrics, QIcon, QKeySequence, QShortcut
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
from .window_state import restore_window, save_window, place_tool_window
from ..config import ConfigStore
from ..logging_store import TranscriptLogger
from ..macros import expand_macro
from ..parser import normalize_call, parse_exchange
from ..macros import CQWW_TEMPLATE_NAME
from ..paths import ensure_runtime_dirs, resource_path
from .about_dialog import AboutDialog
from .history_dialog import HistoryDialog
from .macro_dialog import MacroDialog
from .qso_log_dialog import QSOLogDialog
from .settings_dialog import SettingsDialog
from .spectrum import SpectrumWidget
from .hint_group import HintGroupBox, HeaderControlGroupBox, FooterHintGroupBox
from .formatting import frequency_text, band_mhz
from .number_edit import NumberEdit
from .qso_datetime import QSODatetime


class AudioBridge(QObject):
    tx_finished = Signal(int, bool, str)
    char = Signal(object)
    level = Signal(float)
    spectrum = Signal(object, object)
    sub_char = Signal(int, str)


class ReceiveCard(QFrame):
    clicked = Signal(str)

    def __init__(self, stamp: str, text: str, direction: str = "RX", font_size: int = 14, parent=None):
        super().__init__(parent)
        self.text_value = text
        self.when_utc = None
        self.setObjectName("txCard" if direction == "TX" else "rxCard")
        self.setCursor(Qt.PointingHandCursor)
        lay = QHBoxLayout(self); lay.setContentsMargins(8, 3, 8, 3); lay.setSpacing(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.stamp_label=stamp_label=QLabel(stamp); stamp_label.setObjectName('cardTime')
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
        from ..i18n import configure
        configure(self.store.data['ui'].get('language', 'ja'))
        from ..printer import PrinterSpool
        self.printer=PrinterSpool(self.store.data.get('printer'))
        from .integration_dialog import IntegrationController
        self.integration = IntegrationController(self)
        self.printer_window=None
        self.print_tx=None
        self.transcript = TranscriptLogger()
        self.adif = ADIFLog()
        self.qsos = self.adif.load_recent(limit=None, record_order=True)
        self.radio: CIVController | None = None
        self.current_freq_hz: int | None = None
        self.last_known_freq_hz: int | None = None
        self.connecting = False
        self.antenna_tuning = False
        self.polling = False
        self.poll_failures = 0
        self.connection_generation = 0
        self.help_windows = {}
        self.pending_auto_log = None
        self.qso_revision = 0
        self.control_window = None
        self.sub_window = None
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
        self.call_frequency = None
        self.rx_buffer = ""
        self.last_spectrum: tuple[np.ndarray, np.ndarray] | None = None

        self.bridge = AudioBridge()
        self.bridge.tx_finished.connect(lambda token, ok, msg: self._tx_finished(ok, msg, token))
        self.bridge.char.connect(self._rx_char)
        self.bridge.level.connect(self._rx_level)
        self.bridge.spectrum.connect(self._spectrum_data)
        self.bridge.sub_char.connect(self._sub_char)
        sr = int(self.store.data["audio"]["sample_rate"])
        self.audio = AudioEngine(sr, lambda ch: self.bridge.char.emit((self.audio.decode_generation, ch)), self.bridge.level.emit, self.bridge.spectrum.emit)
        self._apply_audio_config()

        self.setWindowTitle(f"PSRTTY {__version__}")
        from ..app_identity import application_icon
        self.setWindowIcon(application_icon())
        self.resize(1280, 800)
        self.setMinimumSize(320, 240)
        self._build_menu()
        self._build_ui()
        self._apply_style()
        self._setup_shortcuts()
        self._load_config_to_ui()
        self.printer_status=QLabel(); self.printer_status.setTextFormat(Qt.PlainText)
        self.statusBar().addPermanentWidget(self.printer_status)
        self.printer_timer=QTimer(self);self.printer_timer.setInterval(250)
        self.printer_timer.timeout.connect(self._refresh_printer_status);self.printer_timer.start()
        self.secondary_status = QLabel('')
        self.secondary_status.setWordWrap(True)
        self.secondary_status.setMaximumWidth(360)
        self.secondary_status.hide()
        self.statusBar().addPermanentWidget(self.secondary_status)
        self.printer_timer.timeout.connect(self._refresh_secondary_status)
        self._refresh_printer_status()
        self._refresh_latest_qsos()
        self._set_radio_controls()

        self.rx_idle_timer = QTimer(self); self.rx_idle_timer.setSingleShot(True); self.rx_idle_timer.setInterval(750); self.rx_idle_timer.timeout.connect(self._finalize_rx_card)
        self.poll_timer = QTimer(self); self.poll_timer.setInterval(1200); self.poll_timer.timeout.connect(self._poll_radio)
        self.track_timer = QTimer(self); self.track_timer.setInterval(450)
        self.track_timer.timeout.connect(self._auto_track_tick); self.track_timer.start()
        self.track_pause_until = 0.; self.track_candidate = None; self.track_confirm = 0
        QTimer.singleShot(0, self, self._restart_audio_input)

    def _build_menu(self):
        mb = self.menuBar()
        self.file_menu = filem = mb.addMenu(tr("ファイル"))
        self._act(filem, tr("logdataフォルダーを開く"), self._open_log_dir)
        self.transcript_action = self._act(filem, "", self._open_transcript)
        self.adif_action = self._act(filem, "", self._open_adif)
        filem.aboutToShow.connect(self._refresh_log_menu)
        self._refresh_log_menu()
        filem.addSeparator()
        self._act(filem, tr("ADIFファイル出力"), self._export_adif)
        cab = self._act(filem, tr("Cabrilloファイル出力"), self._cabrillo_notice); cab.setEnabled(True)
        self._act(filem, tr("HAMLOG-CSV出力"), self._export_hamlog)
        filem.addSeparator()
        self._build_printer_menu(filem)
        filem.addSeparator(); self._act(filem, tr("終了"), self.close)

        edit = mb.addMenu(tr("編集"))
        self._act(edit, tr("マクロ編集"), self._edit_macros)
        self._act(edit, tr("バックアップ設定"), self._backup_settings)

        radio = mb.addMenu(tr("無線機"))
        self.connect_action = self._act(radio, tr("接続"), self.connect_radio)
        self.disconnect_action = self._act(radio, tr("切断"), self.disconnect_radio)
        self.redetect_action = self._act(radio, tr("再検出"), self._redetect)
        radio.addSeparator(); self._act(radio, tr("基本・無線機・Audio設定"), self._settings)

        view = mb.addMenu(tr("表示"))
        self._act(view, tr("QSOログ"), self._show_qso_log)
        width = view.addMenu(tr("スペクトラム表示幅"))
        self.width_group = QActionGroup(self); self.width_group.setExclusive(True)
        for hz, label in [(500,"500 Hz"),(1000,"1 kHz"),(2000,"2 kHz"),(3000,"3 kHz")]:
            a = self._act(width, label, lambda checked=False, v=hz: self._set_spectrum_width(v)); a.setCheckable(True); a.setData(hz)
            self.width_group.addAction(a)
        fontm = view.addMenu(tr("受信カード文字サイズ"))
        self.font_group = QActionGroup(self); self.font_group.setExclusive(True)
        for size in (10,12,14,16,18):
            a = self._act(fontm, f"{size} pt", lambda checked=False, v=size: self._set_card_font(v))
            a.setCheckable(True); a.setData(size); self.font_group.addAction(a)
        latest = view.addMenu(tr("最新QSO表示件数"))
        self.latest_group = QActionGroup(self); self.latest_group.setExclusive(True)
        for count in (2,4,6,8,10):
            a = self._act(latest, str(count), lambda checked=False, v=count: self._set_latest_count(v))
            a.setCheckable(True); a.setData(count); self.latest_group.addAction(a)
        time_menu=view.addMenu(tr('時刻表記'))
        self.time_group=QActionGroup(self);self.time_group.setExclusive(True)
        for zone in ('JST','UTC'):
            action=self._act(time_menu,zone,lambda checked=False,z=zone:self._set_time_zone(z))
            action.setCheckable(True);action.setData(zone);self.time_group.addAction(action)
        self._sync_view_checks()
        view.aboutToShow.connect(self._sync_view_checks)
        view.addSeparator()
        self._act(view, tr("コントロール"), self._show_control)
        self._act(view, tr("クロススコープ"), lambda: self.scope_button.setChecked(True))
        view.addSeparator()
        sub_action=self._act(view, tr("サブデコ"), self._show_sub)
        sub_action.setToolTip(tr('A/Bの受信専用サブデコードウィンドウを表示します。送信・自動ログは行いません。'))

        integration = mb.addMenu(tr('連携'))
        self._act(integration, tr('HAMLOG連携設定'), self.integration.settings)
        self._act(integration, tr('zLog令和版連携設定'), self._zlog_settings)
        language = mb.addMenu('Language')
        self.language_group = QActionGroup(self); self.language_group.setExclusive(True)
        for code, label in (('ja', '日本語'), ('en', 'English')):
            a = self._act(language, label, lambda checked=False, v=code: self._set_language(v))
            a.setCheckable(True); a.setData(code); self.language_group.addAction(a)
            a.setChecked(self.store.data['ui'].get('language', 'ja') == code)

        helpm = mb.addMenu(tr("ヘルプ"))
        self._act(helpm, tr("初期設定ガイド"), self._guide_initial)
        self._act(helpm, tr("起動コマンドフラグについて"), self._guide_flags)
        self.update_action = self._act(helpm, tr("PSRTTYのバージョンアップ"), self._upgrade_zip)
        helpm.addSeparator()
        self._act(helpm, tr("PSRTTYの更新履歴"), self._history)
        self._act(helpm, tr("PSRTTYについて"), self._about)
        # Keep Python wrappers alive as well as Qt's menu-bar ownership.
        self.top_level_menus = (filem, edit, radio, view, integration, language, helpm)

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
        self.rig_status = QPushButton(tr("未接続")); self.rig_status.setObjectName("rigStatus")
        self.rig_status.clicked.connect(self._toggle_connection)
        self.rig_status.setToolTip(tr("クリックで設定済みの無線機に接続"))
        self.freq_label = QLabel("---.--- MHz"); self.freq_label.setObjectName("freqLabel")
        status.addWidget(self.rig_status); status.addSpacing(18); status.addWidget(self.freq_label)
        self.scope_window = None
        self.control_button = QPushButton(tr("コントロール"))
        self.control_button.clicked.connect(self._show_control)
        self.control_button.setToolTip(tr('無線機の周波数・モード・フィルターなどを別ウィンドウで操作します。'))
        status.addWidget(self.control_button)
        self.scope_button = QPushButton(tr("クロススコープ"))
        self.scope_button.setCheckable(True)
        self.scope_button.setToolTip(tr("受信音のクロススコープを別ウィンドウで表示"))
        self.scope_button.toggled.connect(self._toggle_scope)
        status.addWidget(self.scope_button)
        self.sub_button=QPushButton(tr('サブデコ'))
        self.sub_button.setToolTip(tr('別ウィンドウで周辺の2か所を受信専用でデコードします。'))
        self.sub_button.clicked.connect(self._show_sub)
        status.addWidget(self.sub_button)
        status.addSpacing(8)
        self.center_tuning = QLabel(tr('C同調 ---'))
        indicator_font = self.center_tuning.font()
        indicator_font.setBold(True)
        self.center_tuning.setFont(indicator_font)
        metrics = QFontMetrics(indicator_font)
        # Longest number plus one full-width character of breathing room,
        # and the existing stylesheet's 7px side padding and borders.
        self.center_tuning.setFixedWidth(
            metrics.horizontalAdvance(tr('C同調 +24.9 Hz'))
            + metrics.horizontalAdvance('あ') + 16)
        self.center_tuning.setAlignment(Qt.AlignCenter)
        self.center_tuning.setToolTip(tr('受信中のMARK/SPACEと設定位置の周波数差。判定できない場合は「---」を表示します。'))
        status.addWidget(self.center_tuning); status.addStretch(1)
        from ..tuning import CenterTuning
        self.center_meter = CenterTuning()
        self.center_timer = QTimer(self); self.center_timer.setInterval(333)
        self.center_timer.timeout.connect(self._refresh_center_tuning); self.center_timer.start()
        self.audio_status = QLabel(tr("Audio IN: 未設定"))
        self.profile_buttons = QGridLayout()
        self.profile_buttons.setSpacing(4)
        status.addLayout(self.profile_buttons)
        self._refresh_profile_buttons()
        outer.addLayout(status)

        main = QHBoxLayout(); main.setSpacing(10); outer.addLayout(main, 1)
        left = QVBoxLayout(); left.setSpacing(4); main.addLayout(left, 1)
        right = QVBoxLayout(); right.setSpacing(4); right.setContentsMargins(2,0,0,0); main.addLayout(right, 0)

        spectrum_box = HintGroupBox("Audio Spectrum", tr("クリックで受信位置を調整"))
        spectrum_box.setToolTip(tr('受信音の周波数を表示します。メインの位置とサブデコの位置を合わせて確認できます。'))
        sv = QVBoxLayout(spectrum_box); sv.setContentsMargins(8,8,8,7)
        self.spectrum = SpectrumWidget(); self.spectrum.frequency_clicked.connect(self._spectrum_click); self.spectrum.tones_dragged.connect(self._set_tones); self.spectrum.tones_committed.connect(self.store.save); sv.addWidget(self.spectrum)
        controls = QHBoxLayout()
        self.tone_label = QLabel(tr("Mark 2125 Hz   Center 2210 Hz   Space 2295 Hz"))
        controls.addWidget(self.tone_label); controls.addStretch(1)
        controls.addWidget(QLabel("RX"))
        self.level = QProgressBar(); self.level.setRange(0,100); self.level.setTextVisible(False)
        self.level.setFixedSize(85, 20); self.level.setToolTip(tr("USB Audioの受信音声レベル"))
        controls.addWidget(self.level)
        controls.addWidget(QLabel(tr('表示感度')))
        self.spectrum_gain=QSlider(Qt.Horizontal); self.spectrum_gain.setRange(-30,40); self.spectrum_gain.setFixedWidth(90)
        self.spectrum_gain.setValue(int(self.store.data['ui'].get('spectrum_gain_db',0)))
        self.spectrum.set_gain(self.spectrum_gain.value()); self.spectrum_gain.valueChanged.connect(self._spectrum_gain_changed)
        self.spectrum_gain.setToolTip(tr('波形の表示だけを調整します。受信音量・デコードには影響しません。'))
        controls.addWidget(self.spectrum_gain); sv.addLayout(controls)
        controls=QHBoxLayout(); controls.addWidget(QLabel(tr('シフト幅')))
        self.shift_edit=QLineEdit(str(self.store.data['advanced']['shift_hz'])); self.shift_edit.setFixedWidth(86)
        self.shift_edit.setMaxLength(12); self.shift_edit.editingFinished.connect(self._shift_changed)
        self.shift_edit.setToolTip(tr('10～2000 Hz。MARKを固定し、SPACEを移動します。'))
        controls.addWidget(self.shift_edit); controls.addWidget(QLabel('Hz')); controls.addStretch(1)
        self.auto_track=QCheckBox('AUTO TRACK');self.auto_track.setChecked(False)
        self.auto_track.setToolTip(tr('現在受信している局の小さな周波数ずれだけを追います。初期OFF。送信・手動調整中は停止します。'))
        controls.addWidget(self.auto_track)
        auto = QPushButton("AUTO TUNE"); auto.clicked.connect(self._auto_tune)
        auto.setToolTip(tr('現在のスペクトラムからMARK/SPACEの2ピークを一度だけ探して受信位置を合わせます。'))
        controls.addWidget(auto)
        reset = QPushButton(tr("幅RESET")); reset.clicked.connect(self._reset_170); controls.addWidget(reset)
        reset.setToolTip(tr('MARK位置を保ってシフト幅を170 Hzに戻します。'))
        position=QPushButton(tr('位置RESET')); position.clicked.connect(self._reset_position); controls.addWidget(position)
        position.setToolTip(tr('現在のシフト幅を保ってMARKを2125 Hzに戻します。'))
        sv.addLayout(controls); left.addWidget(spectrum_box)

        self.decode_enabled=QCheckBox(tr('デコード')); self.decode_enabled.setChecked(True)
        self.decode_enabled.setToolTip(tr('OFFで文字のデコードと自動取得を停止。音声入力・スペクトラムは継続します。'))
        self.decode_enabled.toggled.connect(self._set_decode_enabled)
        self.decode_sq = QComboBox()
        for level in range(11): self.decode_sq.addItem('OFF' if level == 0 else str(level), level)
        sq = max(0, min(10, int(self.store.data['ui'].get('decode_sq',4))))
        self.decode_sq.setCurrentIndex(sq); self.audio.set_decode_sq(sq)
        self.decode_sq.currentIndexChanged.connect(self._set_decode_sq)
        self.decode_ignore = QComboBox()
        for count in range(11): self.decode_ignore.addItem(str(count), count)
        self.decode_ignore.setCurrentIndex(self.store.data['ui'].get('decode_ignore_chars',0))
        self.decode_ignore.setToolTip(tr('指定字数以下の受信文を一覧に表示しません。0は除外なし。生ログとプリンターの設定は別です。'))
        self.decode_ignore.currentIndexChanged.connect(self._set_decode_ignore)
        header = QWidget(); header_row = QHBoxLayout(header)
        header_row.setContentsMargins(4,0,4,0); header_row.setSpacing(5)
        header_row.addWidget(QLabel(tr('SQ(スケルチ)'))); header_row.addWidget(self.decode_sq)
        header_row.addWidget(self.decode_enabled)
        header_row.addWidget(self.decode_ignore); header_row.addWidget(QLabel(tr('字以下は無視')))
        cards_box = HeaderControlGroupBox(tr("デコード"), header)
        self.decode_group = cards_box
        cards_layout = QVBoxLayout(cards_box); cards_layout.setContentsMargins(5,max(12,header.sizeHint().height()),5,5)
        self.cards_scroll = QScrollArea(); self.cards_scroll.setWidgetResizable(True); self.cards_scroll.setMinimumHeight(120)
        self.cards_host = QWidget(); self.cards_layout = QVBoxLayout(self.cards_host); self.cards_layout.setAlignment(Qt.AlignTop); self.cards_layout.setSpacing(3)
        self.cards_scroll.setWidget(self.cards_host); cards_layout.addWidget(self.cards_scroll); left.addWidget(cards_box, 1)

        pending = QGroupBox(tr("現在のQSO"))
        self.worked_label = QLabel(pending)
        title_width = pending.fontMetrics().horizontalAdvance(pending.title())
        self.worked_label.move(9 + 8 + title_width + 12, 0)
        grid = QGridLayout(pending); grid.setHorizontalSpacing(7); grid.setVerticalSpacing(4)
        self.auto_get = QCheckBox(tr('自動取得'))
        self.auto_get.setToolTip(tr('受信文からCALL・RST-R・RCVDを取得します。各欄は手修正できます。'))
        self.cq_only = QCheckBox(tr('CQのみ'))
        self.cq_only.setToolTip(tr('ONではCQを含む受信文からのみCALLを自動取得します。'))
        self.cq_only.setChecked(self.store.data['ui'].get('cq_only', True))
        self.cq_only.toggled.connect(lambda v: self.store.data['ui'].update(cq_only=v))
        self.sent_fixed = QCheckBox(tr('固定'))
        self.sent_fixed.setToolTip(tr('ON: SENTを保持。OFF: ログ追加成功時に数値を+1。数字以外は保持。送信だけでは増えません。'))
        for i, title in enumerate(['CALL', 'RST-S', 'RST-R', 'SENT', 'RCVD']):
            header = QHBoxLayout(); header.addWidget(QLabel(title))
            if i == 0: header.addWidget(self.auto_get); header.addWidget(self.cq_only)
            if i == 3: header.addWidget(self.sent_fixed)
            header.addStretch(1); grid.addLayout(header, 0, i)
        self.q_call = QLineEdit(); self.q_call.setPlaceholderText(tr('例: JX1XXX'))
        self.his_call = self.q_call  # One CALL field; preserve internal/test API.
        self.q_call.textEdited.connect(self._his_call_edited)
        self.q_call.textChanged.connect(self._call_changed)
        self.rst_s = QLineEdit('599'); self.rst_r = QLineEdit('599')
        self.sent = QLineEdit(self.store.data['qso']['sent']); self.rcvd = QLineEdit()
        self.sent_fixed.setChecked(self.store.data['qso']['sent_fixed'])
        fields=[self.q_call,self.rst_s,self.rst_r,self.sent,self.rcvd]
        for i,w in enumerate(fields): grid.addWidget(w,1,i)
        self.auto_log = QCheckBox(tr("TU 73送出で自動ログ追加"))
        self.auto_log.setToolTip(tr('送信が正常に完了し、交信欄が変わっていなければQSOをログへ追加します。'))
        self.clear_on_frequency = QCheckBox(tr('周波数変更でクリア'))
        self.clear_on_frequency.setChecked(self.store.data['ui'].get('clear_on_frequency', False))
        self.clear_on_frequency.setToolTip(tr('CALL取得・入力時の周波数から±20 Hz以上でCALL・RST-R・RCVDをクリア'))
        self.clear_on_frequency.toggled.connect(lambda v: self.store.data['ui'].update(clear_on_frequency=v))
        bottom = QHBoxLayout(); bottom.addWidget(self.auto_log); bottom.addWidget(self.clear_on_frequency)
        bottom.addStretch(1)
        self.q_datetime = QSODatetime(zone=self.store.data["ui"].get("time_zone","JST"))
        self.q_date = self.q_datetime.date; self.q_time = self.q_datetime.time
        bottom.addWidget(self.q_datetime)
        for field in fields + [self.q_datetime]:
            field.textChanged.connect(self._qso_edited)
        add = QPushButton(tr("↓ ログに追加")); add.setObjectName("logButton"); add.clicked.connect(self._add_qso)
        add.setToolTip(tr('交信欄の内容を確認してQSOログに追加します。'))
        bottom.addWidget(add); grid.addLayout(bottom,2,0,1,5)
        left.addWidget(pending)

        latest_box = self.latest_box = FooterHintGroupBox(tr("最新QSO"))
        lv = QVBoxLayout(latest_box)
        lv.setContentsMargins(9, 9, 9, 22)
        self.latest_panel = QWidget()
        tables_layout = QHBoxLayout(self.latest_panel)
        tables_layout.setContentsMargins(0,0,0,0); tables_layout.setSpacing(14)
        self.latest_table = QTableWidget(0,8)
        self.latest_right = QTableWidget(0,8)
        for table in (self.latest_table, self.latest_right):
            table.setHorizontalHeaderLabels(["No.",tr("日時（JST）"),"BAND","CALL","RST-S","SENT","RST-R","RCVD"])
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.verticalHeader().setDefaultSectionSize(24)
            table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            table.setMinimumWidth(0)
            table.setToolTip(tr("ダブルクリックでQSOログを開く"))
            table.doubleClicked.connect(lambda *_: self._show_qso_log())
            tables_layout.addWidget(table,1)
        lv.addWidget(self.latest_panel); left.addWidget(latest_box)

        my = QGroupBox(tr("自局"))
        myl = QVBoxLayout(my); row=QHBoxLayout(); self.my_call=QLineEdit(); self.my_call.setPlaceholderText(tr("自局コールサイン")); setb=QPushButton("SET"); setb.clicked.connect(self._set_my_call)
        setb.setToolTip(tr('入力した自局コールサインを保存します。'))
        row.addWidget(self.my_call,1); row.addWidget(setb); myl.addLayout(row); right.addWidget(my)

        auto_cq_box = QGroupBox('Auto CQ')
        cq = QVBoxLayout(auto_cq_box); cq.setContentsMargins(8, 6, 8, 6); cq.setSpacing(4)
        start_row = QHBoxLayout()
        self.auto_cq_button = QPushButton(tr('Auto CQ開始'))
        self.auto_cq_button.setMinimumHeight(44)
        self.auto_cq_button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        self.auto_cq_button.clicked.connect(self._start_auto_cq)
        self.auto_cq_stop = QPushButton('STOP'); self.auto_cq_stop.setObjectName('stopButton')
        self.auto_cq_stop.setToolTip(tr('Auto CQの繰り返し送信を停止します。'))
        self.auto_cq_stop.clicked.connect(self._stop_tx)
        start_row.addWidget(self.auto_cq_button, 1); start_row.addWidget(self.auto_cq_stop)
        cq.addLayout(start_row)
        options = QHBoxLayout()
        self.cq_count = NumberEdit(10, self.store.data['auto_cq']['count'])
        self.cq_interval = NumberEdit(7, self.store.data['auto_cq']['interval_seconds'])
        options.addWidget(QLabel(tr('回数'))); options.addWidget(self.cq_count); options.addWidget(QLabel(tr('回')))
        options.addStretch(1); options.addWidget(QLabel(tr('間隔'))); options.addWidget(self.cq_interval); options.addWidget(QLabel(tr('秒')))
        self.cq_interval.setToolTip(tr('送信終了・PTT解除後から次の送信までの受信待機時間'))
        cq.addLayout(options); right.addWidget(auto_cq_box)

        self.offline_tx = QCheckBox(tr('未接続でもMACROと手動送信可'))
        self.offline_tx.setChecked(False)
        self.offline_tx.setToolTip(tr('音声出力テスト用。未接続時はPTTを操作しません。Auto CQは接続必須です。'))
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

        tx_box=QGroupBox(tr("手動送信"))
        tv=QVBoxLayout(tx_box); self.manual_tx=QLineEdit(); self.manual_tx.setPlaceholderText(tr("自由送信テキスト"))
        tv.addWidget(self.manual_tx); rr=QHBoxLayout(); send=QPushButton("TX"); self.send_button=send; send.clicked.connect(self._send_manual); stop=QPushButton("STOP"); stop.setObjectName("stopButton"); stop.clicked.connect(self._stop_tx)
        send.setToolTip(tr('入力した文章をRTTYで送信します。')); stop.setToolTip(tr('現在の送信を停止します。'))
        rr.addWidget(send); rr.addWidget(stop); tv.addLayout(rr); right.addWidget(tx_box)
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

    def _refresh_secondary_status(self):
        notice = self.audio.secondary_notice
        self.secondary_status.setText(notice)
        self.secondary_status.setVisible(bool(notice))

    def _apply_audio_config(self):
        a=self.store.data["advanced"]
        rx=self.store.data['ui'].get('rx_tones',[a['mark_hz'],a['space_hz']])
        self.audio.configure_decoder(a['rtty_baud'],rx[0],rx[1],a['invert'])
        self.audio.set_rx_gain(self.store.data["audio"]["rx_gain"])
        self.audio.set_tx_gain(self.store.data["audio"]["tx_gain"])
        self.audio.configure_secondary(self.store.data['audio'].get('secondary'))

    def _refresh_profile_buttons(self, selected=None):
        while self.profile_buttons.count():
            item = self.profile_buttons.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        if selected is None: selected = self.store.data['active_profile']
        for i, profile in enumerate(self.store.data['profiles']):
            button = QPushButton(profile['name'])
            button.setFixedSize(108, 22)
            button.setToolTip(tr('{name} に切り替える').format(name=profile['name']))
            if i == selected:
                button.setStyleSheet('QPushButton { background: #e3f0ff; color: #1767cf; border: 2px solid #1767cf; font-weight: 700; padding: 2px; }')
            else:
                button.setStyleSheet('QPushButton { background: #e8e8e8; color: #454545; border: 2px solid #777777; font-weight: 700; padding: 2px; }')
            button.clicked.connect(lambda checked=False, index=i: self._switch_profile(index))
            self.profile_buttons.addWidget(button, i // 3, i % 3)

    def _switch_profile(self, index):
        old = self.store.data['active_profile']
        if index == old or self.closing: return
        if (self.active_tx_id is not None or self.audio._tx_active or self.antenna_tuning
            or self.auto_cq_active or self.connecting or
            (self.settings_window and self.settings_window.isVisible())):
            self.statusBar().showMessage(tr('送信・接続・設定の操作が終わってから切り替えてください'), 5000)
            return
        if getattr(self, '_profile_switch', None): return
        previous_connected = self._connected()
        self.store.data['station_callsign'] = normalize_call(self.my_call.text())
        self.disconnect_radio()
        self.store.activate_profile(index)
        self.last_known_freq_hz = None
        self._update_freq_label()
        self._apply_audio_config()
        self._load_config_to_ui()
        self._restart_audio_input()
        self._refresh_profile_buttons()
        if not previous_connected or not self.store.data['radio']['model']:
            self.statusBar().showMessage(tr('Profileを切り替えました。無線機は未接続です'), 5000)
            return
        self._profile_switch = True
        def after_cleanup():
            if not self._profile_switch or self.closing: return
            cleanup = getattr(self, 'cleanup_job', None)
            if cleanup and cleanup.thread.is_alive():
                QTimer.singleShot(100, self, after_cleanup)
            else:
                self.connect_radio()
        QTimer.singleShot(0, self, after_cleanup)

    def _profile_connect_failed(self, reason=''):
        if not getattr(self, '_profile_switch', None): return
        self._profile_switch = None
        self.disconnect_radio()
        self._refresh_profile_buttons()
        self.statusBar().showMessage(
            tr('Profileは切り替わりました。無線機は未接続です') + (f'：{reason}' if reason else ''), 10000)

    def _restart_audio_input(self):
        self.audio_input_requested = True
        if self.audio_input_busy: return
        self.audio_input_busy = True
        self.audio_input_requested = False
        selection = 'UNSET' if self.closing else deepcopy(self.store.data['audio']['input_device'])
        self.audio_status.setText(tr('Audio IN: 停止中') if self.closing else tr('Audio IN: 切替中…'))
        def work():
            self.audio.stop_input()
            if selection == 'UNSET': return False, tr('Audio IN: 未設定')
            return self.audio.start_input(selection)
        def done(result, error):
            self.audio_input_busy = False
            if self.audio_input_requested:
                self._restart_audio_input(); return
            ok, message = result if not error else (False, str(error))
            self.audio_status.setText(tr('Audio IN: 入力中') if ok else (tr('Audio IN: 未設定') if selection == 'UNSET' else tr('Audio IN: 入力できません')))
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
            from html import escape
            self.macro_buttons[i].setToolTip('<qt><div style="white-space:pre-wrap; max-width:480px">' + escape(preview).replace('\n', '<br>') + '</div></qt>')
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

    def _set_decode_ignore(self, index):
        old=self.store.data['ui'].get('decode_ignore_chars',0)
        self.store.data['ui']['decode_ignore_chars']=self.decode_ignore.itemData(index)
        try:self.store.save()
        except Exception as exc:
            self.store.data['ui']['decode_ignore_chars']=old
            self.decode_ignore.blockSignals(True);self.decode_ignore.setCurrentIndex(old);self.decode_ignore.blockSignals(False)
            self.statusBar().showMessage(tr('設定を保存できませんでした。')+' '+str(exc),8000)

    def _set_decode_enabled(self, enabled):
        self.audio.set_decode_enabled(enabled)
        self.rx_idle_timer.stop(); self.rx_buffer=''

    def _rx_char(self, ch):
        if not self.decode_enabled.isChecked() or self.active_tx_id is not None: return
        if isinstance(ch, tuple):
            generation, ch=ch
            if generation != self.audio.decode_generation: return
        if self.sub_window and self.sub_window.isVisible():self.sub_window.main_char(ch)
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
        self.printer.submit("RX",text,zone=self.store.data["ui"].get("time_zone","JST"))
        if len(text)<=self.store.data['ui'].get('decode_ignore_chars',0):return
        self._add_card(text,"RX")
        self._consider_auto_extract(text)

    def _add_card(self,text,direction):
        zone=self.store.data['ui'].get('time_zone','JST')
        when=datetime.now(timezone.utc)
        card=ReceiveCard(when.astimezone(display_zone(zone)).strftime("%H:%M:%S")+' '+zone,text,direction,int(self.store.data["ui"]["rx_card_font_size"]))
        card.when_utc=when;card.clicked.connect(self._card_selected);self.cards_layout.addWidget(card)
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
        allow_call = not self.cq_only.isChecked() or bool(re.search(r'\bCQ\b', text, re.I))
        if parsed.callsign and not self.call_locked and allow_call:
            self.q_call.setText(parsed.callsign); self.call_locked=True
        if parsed.rst: self.rst_r.setText(parsed.rst)
        if parsed.exchange: self.rcvd.setText(parsed.exchange)
        self._refresh_macros()

    def _call_changed(self, text):
        upper = text.upper()
        if text != upper:
            pos = self.q_call.cursorPosition()
            self.q_call.setText(upper); self.q_call.setCursorPosition(pos)
            return
        self.call_frequency = self.current_freq_hz if upper.strip() else None
        if not upper.strip(): self.call_locked = False
        self._refresh_worked()

    def _refresh_worked(self):
        if not hasattr(self, 'worked_label'): return
        from ..adif import band_from_hz, BANDS
        call = normalize_call(self.q_call.text())
        records = [q for q in self.qsos if normalize_call(q.call) == call] if call else []
        bands = {q.band for q in records if q.band}
        labels = dict(zip([b[2] for b in BANDS], ['0.135','0.472','1.8','3.5','7','10','14','18','21','24','28','50','144','430','1240','2300','5650','10000']))
        done = bool(band_from_hz(self.current_freq_hz) in bands)
        text = '' if not call else tr('初めての局です') if not records else call + ' ' + ' '.join(labels[b[2]]+'MHz' for b in BANDS if b[2] in bands) + tr(' 交信済み') + ('＊＊＊' if done else '')
        color = '#d00000' if done else '#008ba3' if records else '#39bce6'
        self.worked_label.setText(text)
        self.worked_label.setStyleSheet('background:#fffdf9; padding:0 4px; color:'+color)
        self.worked_label.setToolTip(text)
        self.worked_label.adjustSize(); self.worked_label.raise_()

    def _refresh_center_tuning(self):
        frame = getattr(self.audio, 'tuning_frame', None)
        value = self.center_meter.update(frame, self.audio.sample_rate)
        from ..tuning import tuning_display
        text, color = tuning_display(value)
        self.center_tuning.setText(text.replace('C同調 ',tr('C同調 '),1))
        self.center_tuning.setStyleSheet(
            'QLabel { color:'+color+'; background:#fffdf6; border:1px solid #c88432;'
            'border-radius:4px; padding:3px 7px; font-weight:bold; }')

    def _connected(self):
        return bool(self.radio and self.radio.status.connected and not self.connecting)

    def _manual_tx_allowed(self):
        return not self.antenna_tuning and not self.closing and not self.connecting and (self._connected() or self.offline_tx.isChecked())

    def _offline_tx_changed(self):
        if not self.offline_tx.isChecked() and not self._connected(): self._stop_tx()
        self._set_radio_controls()

    def _set_radio_controls(self):
        ready = self._connected()
        self.rig_status.setText(tr('接続中…') if self.connecting else (tr('接続') if ready else tr('未接続')))
        self.rig_status.setEnabled(not self.connecting)
        self.rig_status.setStyleSheet('background: #a9def5; color: #075aa6;' if ready else 'background: #e1e9ee; color: #a34e00;')
        for button in self.macro_buttons + [self.send_button]:
            button.setEnabled(self._manual_tx_allowed())
        for shortcut in self.shortcuts[:9]:
            shortcut.setEnabled(self._manual_tx_allowed())
        self.auto_cq_button.setEnabled(not self.antenna_tuning and ready and not self.auto_cq_active and self.active_tx_id is None)
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
            self.statusBar().showMessage(tr('{key} は空です').format(key=m.get('key')), 3000); return
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
            self.statusBar().showMessage(tr("無線機を接続してから送信してください"), 3000)
            return False
        if self.active_tx_id is not None or self.audio._tx_active:
            self.statusBar().showMessage(tr('送信終了を待ってください'), 2500)
            return False
        if self.control_window:
            self.control_window.pending = self.control_window.target = self.control_window.feature_pending = None
            if self.control_window.busy:
                self.statusBar().showMessage(tr("無線機操作の完了を待って送信してください"), 2500)
                return False
        a=self.store.data["advanced"]; au=self.store.data["audio"]
        ctl = self.radio
        from ..external_ptt import ExternalPTT
        mode = self.store.data["radio"]["ptt"]
        offline = not self._connected()
        ptt = None if offline else {"CI-V": ctl.set_ptt, "CAT": ctl.set_ptt, "RTS": ctl.set_rts, "DTR": ctl.set_dtr}.get(mode)
        try:
            sequencer = ExternalPTT(self.store.data['external'], ctl.status.port if not offline else '', self.audio._tx_cancel)
        except ValueError as exc:
            self.statusBar().showMessage(str(exc), 4000)
            return False
        def on():
            if offline: return not self.closing
            return bool(ptt and self.radio is ctl and self._connected() and sequencer.before_ptt() and ptt(True))
        def off():
            try: return True if offline else (ptt(False) if ptt else False)
            finally: sequencer.after_ptt()
        self.tx_sequence += 1
        token = self.tx_sequence
        self.active_tx_id = token
        self.rx_idle_timer.stop(); self.rx_buffer = ''
        try:
            ok,msg=self.audio.send_text(text,au["output_device"],a["rtty_baud"],a["mark_hz"],a["space_hz"],a["invert"],au["tx_gain"],on,off,lambda ok, msg: self.bridge.tx_finished.emit(token, ok, msg), allow_secondary_only=offline and self.offline_tx.isChecked())
        except Exception as exc:
            ok, msg = False, f"{tr('送信開始失敗: ')}{exc}" 
        if ok:
            self.print_tx=(token,text,datetime.now(timezone.utc),self.store.data['ui'].get('time_zone','JST'),self.printer.generation) if self.printer.snapshot()['enabled'] else None
            self.pending_auto_log = None
            self.transcript.append("TX " + text); self._add_card(text,"TX")
        if not ok: self.active_tx_id = None
        self._set_radio_controls()
        self.statusBar().showMessage(msg,4000)
        return ok

    def _auto_log_notice(self, reason):
        message = tr('自動ログ未追加: ') + reason
        self.statusBar().showMessage(message, 10000)
        self.transcript.append(message)

    def _tx_finished(self, success, message, token=None):
        if token is not None and token != self.active_tx_id:
            return  # Ignore stale callbacks from a previous TX.
        self.audio.set_decode_enabled(self.decode_enabled.isChecked())
        self.rx_idle_timer.stop(); self.rx_buffer = ''
        finished_id, self.active_tx_id = self.active_tx_id, None
        print_tx,self.print_tx=self.print_tx,None
        if success and print_tx and print_tx[0]==finished_id and print_tx[4]==self.printer.generation:
            self.printer.submit('TX',print_tx[1],print_tx[2],print_tx[3])
        pending, self.pending_auto_log = self.pending_auto_log, None
        if success and pending and pending == (self._macro_values(), self.qso_revision, self.current_freq_hz):
            if self.auto_log.isChecked():
                if self.q_call.text().strip(): self._add_qso()
                else: self._auto_log_notice(tr('相手CALLが空欄'))
        elif success and pending:
            if pending[2] != self.current_freq_hz: reason = tr('送信中に周波数が変わりました')
            else: reason = tr('送信中に交信入力が編集されました。内容を確認して手動で追加してください')
            self._auto_log_notice(reason)
        elif not success:
            self.statusBar().showMessage(message, 6000)
            self.transcript.append(tr("TX中止 ") + message)
        if self.auto_cq_active and self.auto_cq_inflight == finished_id:
            self.auto_cq_inflight = None
            if not success:
                self._cancel_auto_cq()
            else:
                self.auto_cq_remaining -= 1
                if self.auto_cq_remaining <= 0:
                    self._cancel_auto_cq()
                    self.statusBar().showMessage(tr('Auto CQ完了'), 4000)
                else:
                    self.auto_cq_deadline = time.monotonic() + self.cq_interval.value()
                    self.auto_cq_timer.start()
        queued, self.pending_manual = self.pending_manual, None
        if queued and self._manual_tx_allowed() and not self.closing and (success or message == tr('送信中止')):
            self._manual_request(*queued)
        self._refresh_auto_cq_button(); self._set_radio_controls()

    def _refresh_auto_cq_button(self):
        if not hasattr(self, 'auto_cq_button'): return
        preview = expand_macro(self.store.macros[0].get('text', ''), self._macro_values())
        self.auto_cq_button.setToolTip(tr('F1を繰り返し送信します。\n') + preview)
        if self.auto_cq_active:
            seconds = max(0, int(self.auto_cq_deadline - time.monotonic() + .999)) if self.auto_cq_deadline else None
            detail = tr('{0}{1} 秒').format(tr('次まで '), seconds) if seconds is not None else tr('送信中')
            self.auto_cq_button.setText(tr('{0}{1}回\n{2}').format(tr('Auto CQ 残り'), self.auto_cq_remaining, detail))
        else:
            shown = self.auto_cq_button.fontMetrics().elidedText(" ".join(preview.split()), Qt.ElideRight, max(60, self.auto_cq_button.width()-20))
            self.auto_cq_button.setText(tr('Auto CQ開始\n') + shown)

    def _start_auto_cq(self):
        if self.antenna_tuning or not self._connected() or self.auto_cq_active or self.active_tx_id is not None or self.audio._tx_active:
            return
        if not expand_macro(self.store.macros[0].get('text', ''), self._macro_values()):
            self.statusBar().showMessage(tr('F1が空のためAuto CQを開始できません'), 4000); return
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
        if self.control_window and hasattr(self.control_window, 'tuner_cancel'):
            self.control_window.tuner_cancel.set()
        self._cancel_auto_cq()
        self.pending_manual = None
        self.pending_auto_log = None
        self.audio.stop_tx()
        self.statusBar().showMessage(tr("送信停止"),2500)

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
            QMessageBox.warning(self,tr("ログに追加"),tr("相手コールサインがありません。")); return
        try:
            stamp = self.q_datetime.text().strip() if self.q_datetime.manual.isChecked() else ""
            when = datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=self.q_datetime.zone).astimezone(timezone.utc) if stamp else datetime.now(timezone.utc)
        except ValueError:
            QMessageBox.warning(self, tr("ログに追加"), tr("日時を YYYY-MM-DD HH:MM で入力してください。"))
            return
        q=QSORecord(call=call,rst_sent=self.rst_s.text().strip() or "599",rst_rcvd=self.rst_r.text().strip() or "599",sent=self.sent.text().strip(),rcvd=self.rcvd.text().strip(),station_callsign=normalize_call(self.my_call.text()),freq_hz=self.current_freq_hz or (self.last_known_freq_hz if not self._connected() else None),when_utc=when)
        try:
            path=self.adif.append(q)
        except Exception as exc:
            QMessageBox.warning(self, tr('ログに追加'), tr('保存に失敗しました。入力は保持しています。\n{0}').format(exc))
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
        self.statusBar().showMessage(tr('{call} を {file} に追加しました').format(call=call, file=path.name),4000)
        self._refresh_latest_qsos(); self.his_call.clear(); self.q_call.clear(); self.rcvd.clear(); self.call_locked=False; self._refresh_macros()
        if backup.get("every_enabled", False) and backup["pending_qsos"] >= max(1, int(backup.get("every_count", 30))):
            self._backup_logs()
        self.integration.record(q)
        if settings_error is not None:
            QMessageBox.warning(self, tr('設定の保存'), tr('QSOはADIFへ保存済みです。再度追加する必要はありません。\nSENTなどの設定を保存できませんでした。\n{0}').format(settings_error))

    def _refresh_latest_qsos(self):
        self._refresh_worked()
        count=int(self.store.data["ui"]["latest_qso_count"])
        total=len(self.qsos)
        self.latest_box.set_footer(f"{tr('ログ合計 ')}{total}{tr('件')}")
        rows=list(reversed(self.qsos[-count:]))
        fm=self.latest_table.fontMetrics()
        widths=[max(30, fm.horizontalAdvance(str(total))+8),fm.horizontalAdvance('2026-09-24 23:59')+8,max(38, fm.horizontalAdvance('BAND')+6),fm.horizontalAdvance('JH1HST/1')+8]
        widths += [max(36,fm.horizontalAdvance(label)+6) for label in ('RST-S','SENT','RST-R','RCVD')]
        # A table can elide a long value and show it in its tooltip. Using the
        # full preferred widths as the breakpoint hides the right table even
        # when two readable tables fit (notably with Windows font metrics).
        minimums=[30, 112, 38, 66, 38, 36, 38, 36]
        panel_width=self.latest_panel.width()
        columns=2 if panel_width >= 2*(sum(minimums)+8)+14 else 1
        if columns == 2:
            budget=(panel_width-14)//2-8
            compact=minimums[:]
            remaining=max(0, budget-sum(compact))
            for c in (1, 3, 0, 2, 4, 5, 6, 7):
                grow=min(remaining,max(0,widths[c]-compact[c]))
                compact[c]+=grow; remaining-=grow
            widths=compact
        self.latest_right.setVisible(columns == 2)
        tables=(self.latest_table,self.latest_right)
        for table in tables:
            table.setHorizontalHeaderItem(1,QTableWidgetItem(tr('日時（{zone}）').format(zone=self.store.data['ui'].get('time_zone','JST'))))
            table.clearContents()
            table.setRowCount((len(rows)+columns-1)//columns)
            for c,width in enumerate(widths): table.setColumnWidth(c,width)
            height=table.horizontalHeader().sizeHint().height()+((count+columns-1)//columns)*24+4
            table.setFixedHeight(height)
        for i,q in enumerate(rows):
            stamp=q.when_utc.astimezone(display_zone(self.store.data["ui"].get("time_zone","JST"))).strftime("%Y-%m-%d %H:%M") if q.when_utc else ""
            for c,v in enumerate([total-i,stamp,band_mhz(q),q.call,q.rst_sent,q.sent,q.rst_rcvd,q.rcvd]):
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
            self.statusBar().showMessage(tr("切断処理中です。少し待って再接続してください"), 3000)
            return
        if self.active_tx_id is not None or self.audio._tx_active:
            self.statusBar().showMessage(tr('音声出力を停止してから接続してください'), 3000); return
        values = deepcopy(self.store.data["radio"])
        advanced = deepcopy(self.store.data["advanced"])
        try:
            ctl = create_controller(values)
        except ValueError as exc:
            if getattr(self, '_profile_switch', None):
                self._profile_connect_failed(str(exc))
            else:
                QMessageBox.warning(self, tr("無線機"), str(exc))
            return
        self.radio = ctl
        self.connecting = True
        generation = self.connection_generation
        self.rig_status.setText(tr("接続確認中…（最大約10秒・切断で中止）"))
        self._set_radio_controls()
        def done(status, error):
            if generation != self.connection_generation:
                return
            self.connecting = False
            if error or not status.connected:
                self.rig_status.setText(tr("未接続"))
                self.statusBar().showMessage(str(error) if error else status.message, 10000)
                if getattr(self, '_profile_switch', None):
                    message = str(error) if error else status.message
                    QTimer.singleShot(0, self, lambda: self._profile_connect_failed(message))
            else:
                self.rig_status.setText(tr('{0}  {1}  接続').format(values['model'], status.port))
                self.current_freq_hz = status.frequency_hz
                if self.current_freq_hz: self.last_known_freq_hz = self.current_freq_hz
                self.poll_failures=0; self.rig_status.setToolTip(tr('{0}  {1}\nクリックで切断').format(values['model'], status.port)); self._update_freq_label(); self.poll_timer.start()
                self.statusBar().showMessage(tr('無線機に接続しました'), 5000)
                if getattr(self, '_profile_switch', None):
                    self._profile_switch = None
                    self._refresh_profile_buttons()
            self._set_radio_controls()
        self.connection_job = BackgroundJob(self, lambda: connect_configured(ctl, values, advanced), done)
        def deadline():
            if generation == self.connection_generation and self.connecting:
                self.disconnect_radio()
                self.statusBar().showMessage(tr("接続がタイムアウトしました"), 8000)
                if getattr(self, '_profile_switch', None): self._profile_connect_failed(tr('タイムアウト'))
        QTimer.singleShot(10000, self, deadline)

    def disconnect_radio(self):
        was_tuning = self.antenna_tuning
        self.antenna_tuning = False
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
                if was_tuning: ctl.stop_tuner()
                if ctl.status.connected:
                    {"CI-V": ctl.set_ptt, "CAT": ctl.set_ptt, "RTS": ctl.set_rts, "DTR": ctl.set_dtr}.get(mode, ctl.set_ptt)(False)
                ctl.disconnect()
            self.cleanup_job = BackgroundJob(self, cleanup, lambda *_: None)
        if self.current_freq_hz: self.last_known_freq_hz = self.current_freq_hz
        self.rig_status.setText(tr("未接続")); self.rig_status.setToolTip(tr("クリックで設定済みの無線機に接続")); self.current_freq_hz=None; self._update_freq_label()
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
                self.statusBar().showMessage(tr('無線機の応答を再確認中（{count}/3）').format(count=self.poll_failures))
                return
            stamp=datetime.now(JST).strftime('%Y-%m-%d %H:%M:%S')
            reason=tr('{stamp} 無線機の応答を3回連続で取得できなかったため切断しました').format(stamp=stamp)
            self.disconnect_radio()
            self.rig_status.setToolTip(reason)
            self.statusBar().showMessage(reason); self.transcript.append(reason)
        else:
            if self.poll_failures: self.statusBar().showMessage(tr('無線機の応答が戻りました'),4000)
            self.poll_failures=0
            self.current_freq_hz=freq; self.last_known_freq_hz=freq; self._update_freq_label()

    def _update_freq_label(self):
        if self.current_freq_hz and self.q_call.text().strip():
            if self.call_frequency is None: self.call_frequency = self.current_freq_hz
            elif self.clear_on_frequency.isChecked() and abs(self.current_freq_hz-self.call_frequency) >= 20:
                self.q_call.clear(); self.rst_r.setText('599'); self.rcvd.clear()
        self._refresh_worked()
        retained = not self._connected() and self.current_freq_hz is None and self.last_known_freq_hz is not None
        visible_freq = self.last_known_freq_hz if retained else self.current_freq_hz
        self.freq_label.setText(frequency_text(visible_freq))
        self.freq_label.setStyleSheet('color: #888888;' if retained else '')
        self.freq_label.setToolTip(tr('切断前に取得した周波数。未接続でのログ追加にも使用します。') if retained else '')
        if self.control_window: self.control_window.observe_frequency(self.current_freq_hz)

    def _toggle_scope(self, visible):
        if visible:
            if self.scope_window is None:
                from .cross_scope import CrossScopeWindow
                self.scope_window = CrossScopeWindow(self.audio, self)
                self.scope_window.finished.connect(lambda _: self.scope_button.setChecked(False))
            place_tool_window(self.scope_window,self,(330,365),(260,280),
                              self.store.data['ui'].get('scope_window'))
            self.scope_window.show()
            self.scope_window.raise_()
        elif self.scope_window is not None:
            self.store.data['ui']['scope_window']=save_window(self.scope_window)
            self.scope_window.hide()

    def _show_control(self):
        from .control_window import ControlWindow
        if self.control_window is None:
            self.control_window = ControlWindow(self)
        self.control_window.reveal()

    def _show_sub(self):
        if self.sub_window and self.sub_window.isVisible():
            self.sub_window.raise_();self.sub_window.activateWindow();return
        message=QMessageBox(self)
        message.setWindowTitle(tr('サブデコの使用について'))
        message.setIcon(QMessageBox.Information)
        message.setTextFormat(Qt.RichText)
        message.setText(tr('「CQ WW RTTY DXコンテスト」でサブデコを使って別の局を探す場合、'
                        '<span style="color:#b3261e;font-weight:bold">Single Operator Assisted</span>での参加が必要です。'
                        '<br><br>「JARL World Wide RTTYコンテスト」では、RTTYスキマーなどの使用が認められており、サブデコも使用できます。'
                        '<br><br>サブデコの推奨環境：4コア以上のCPU、メモリ8 GB以上。PCの負荷が高い場合は、'
                        'メインの受信を優先し、サブデコの探索や表示更新を自動的に抑えます。'))
        message.setStandardButtons(QMessageBox.Ok|QMessageBox.Cancel)
        message.button(QMessageBox.Ok).setText('OK')
        message.button(QMessageBox.Cancel).setText(tr('キャンセル'))
        if message.exec()!=QMessageBox.Ok:return
        if self.sub_window is None:
            from .sub_decode import SubDecodeWindow
            self.sub_window=SubDecodeWindow(self)
        place_tool_window(self.sub_window,self,(480,400),(400,300),
                          self.store.data['ui'].get('sub_window'))
        self.sub_window.show();self.sub_window.raise_();self.sub_window.activateWindow()

    def _sub_char(self,index,ch):
        if self.sub_window and self.sub_window.isVisible():self.sub_window.sub_char(index,ch)

    def _rx_level(self,v): self.level.setValue(int(max(0,min(1,float(v)))*100))
    def _spectrum_data(self,f,p): self.last_spectrum=(np.asarray(f),np.asarray(p)); self.spectrum.set_data(self.last_spectrum[0],self.last_spectrum[1])

    def _auto_track_tick(self):
        if (not self.auto_track.isChecked() or not self.last_spectrum or
            self.active_tx_id is not None or self.audio._tx_active or
            time.monotonic()<self.track_pause_until):
            self.track_confirm=0;return
        freqs,power=self.last_spectrum
        if len(freqs)<8:return
        mark=self.spectrum.mark_hz;space=self.spectrum.space_hz
        peaks=[]
        for tone in (mark,space):
            indices=np.flatnonzero(abs(freqs-tone)<=30)
            if len(indices)==0:return
            i=indices[np.argmax(power[indices])]
            peaks.append((float(freqs[i]),float(power[i])))
        if min(p[1] for p in peaks)<float(np.percentile(power,35))+8:
            self.track_confirm=0;return
        offsets=[peaks[0][0]-mark,peaks[1][0]-space]
        if abs(offsets[0]-offsets[1])>12:
            self.track_confirm=0;return
        delta=sum(offsets)/2
        if abs(delta)<3:
            self.track_confirm=0;return
        if self.track_candidate is not None and abs(delta-self.track_candidate)<8:
            self.track_confirm+=1
        else:self.track_candidate=delta;self.track_confirm=1
        if self.track_confirm>=3:
            delta=max(-12.,min(12.,delta))
            self._track_programmatic=True
            try:self._set_tones(mark+delta,space+delta,save=False)
            finally:self._track_programmatic=False
            self.track_confirm=0

    def _auto_tune(self):
        if not self.last_spectrum:
            self.statusBar().showMessage(tr("まだスペクトラムデータがありません"),3000); return
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
            self.statusBar().showMessage(tr('{shift:g} Hz付近の2ピークを確認できませんでした').format(shift=shift),3500); return
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
        if not getattr(self,'_track_programmatic',False):
            self.track_pause_until=time.monotonic()+2
            self.track_confirm=0
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
            self.statusBar().showMessage(tr('シフト幅は10～2000 Hz、MARK／SPACEは100～3900 Hzの範囲です。'),5000)

    def _reset_170(self):
        sign=1 if self.spectrum.space_hz>=self.spectrum.mark_hz else -1
        if not self._set_tones(self.spectrum.mark_hz,self.spectrum.mark_hz+sign*170):
            self.statusBar().showMessage(tr('幅170 Hzが範囲外です。先に位置RESETを押してください。'),4000)

    def _reset_position(self):
        delta=self.spectrum.space_hz-self.spectrum.mark_hz
        if not self._set_tones(2125,2125+delta):
            self.statusBar().showMessage(tr('この幅では標準位置に戻せません。先に幅RESETを押してください。'),4000)

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
        self.store.data['station_callsign'] = normalize_call(self.my_call.text())
        old_tones=tuple(self.store.data['advanced'][k] for k in ('mark_hz','space_hz','shift_hz'))
        dlg = self.settings_window = SettingsDialog(self.store, self)
        disconnected_on_save = {'value': False}
        def before_save():
            disconnected_on_save['value'] = self._connected()
            self.disconnect_radio()
        dlg.before_save.connect(before_save)
        dlg.setWindowModality(Qt.NonModal)
        def finished(result):
            if result:
                if old_tones!=tuple(self.store.data['advanced'][k] for k in ('mark_hz','space_hz','shift_hz')):
                    self.store.data['ui'].pop('rx_tones',None); self.store.save()
                self._refresh_profile_buttons()
                self._apply_audio_config(); self._load_config_to_ui(); self._restart_audio_input()
                self.statusBar().showMessage(tr("設定を保存しました。無線機を再接続してください"), 4000)
                if disconnected_on_save['value']:
                    QMessageBox.information(self, tr('設定'), tr('設定を有効にするため、接続を一旦切断しました。'))
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
        if dlg.exec():
            self._refresh_macros()
            qso = dict(self.store.data['qso'])
            # Avoid saving an intermediate combination through the main controls.
            self.sent.blockSignals(True)
            self.sent_fixed.blockSignals(True)
            try:
                self.sent.setText(qso['sent'])
                self.sent_fixed.setChecked(qso['sent_fixed'])
            finally:
                self.sent.blockSignals(False)
                self.sent_fixed.blockSignals(False)
    def _show_qso_log(self):
        dlg=QSOLogDialog(self.adif,self)
        dlg.changed.connect(self._reload_qsos)
        dlg.exec()

    def _reload_qsos(self):
        self.qsos=self.adif.load_recent(limit=None, record_order=True)
        self._refresh_latest_qsos()
    def _about(self): AboutDialog(self).exec()
    def _history(self): HistoryDialog(self).exec()

    def _set_spectrum_width(self,v): self.store.data["advanced"]["spectrum_width_hz"]=v; self.store.save(); self.spectrum.set_width(v)
    def _set_card_font(self,v): self.store.data["ui"]["rx_card_font_size"]=v; self.store.save(); self.statusBar().showMessage(tr("新しいカードから文字サイズを反映します"),2500)
    def _set_latest_count(self,v): self.store.data["ui"]["latest_qso_count"]=v; self.store.save(); self._refresh_latest_qsos()

    def _sync_view_checks(self):
        for group, value in ((self.width_group, self.store.data['advanced']['spectrum_width_hz']),
                             (self.font_group, self.store.data['ui']['rx_card_font_size']),
                             (self.latest_group, self.store.data['ui']['latest_qso_count']),
                             (self.time_group, self.store.data['ui'].get('time_zone','JST'))):
            for action in group.actions():
                action.setChecked(action.data() == value)

    def _set_language(self, code):
        self.store.data['ui']['language'] = code
        self.store.save()
        QMessageBox.information(self, 'Language', '表示言語は次回起動時に反映します。\nThe display language will change after restarting PSRTTY.')

    def _open_path(self,path:Path):
        path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists() and path.suffix: path.touch()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
    def _refresh_log_menu(self):
        self.transcript_action.setText(tr("今日の生ログTXTを開く（JST基準）"))
        self.adif_action.setText(tr("今月のADIFを開く（UTC基準）"))

    def _backup_settings(self):
        from .backup_dialog import BackupDialog
        BackupDialog(self.store, lambda: self._backup_logs(manual=True), self).exec()

    def _backup_logs(self, manual=False):
        from ..backup import create_log_backup
        try:
            path = create_log_backup(self.paths["logdata"])
        except Exception as exc:
            QMessageBox.warning(self, tr("ログバックアップ"), tr('バックアップに失敗しました。元のログは保持しています。\n{0}').format(exc))
            return False
        if path is None:
            if manual: QMessageBox.information(self, tr("ログバックアップ"), tr("バックアップするログがありません。"))
            return True
        self.store.data.setdefault("backup", {})["pending_qsos"] = 0
        try:
            self.store.save()
        except Exception as exc:
            QMessageBox.warning(self, tr("ログバックアップ"), tr('{0}{1}\n件数設定の保存に失敗しました：{2}').format(tr('バックアップは保存済みです：'), path, exc))
        self.statusBar().showMessage(f"{tr('バックアップを保存しました：')}{path.name}", 10000)
        if manual: QMessageBox.information(self, tr("ログバックアップ"), tr('バックアップを保存しました。\n{0}').format(path))
        return True

    def _open_log_dir(self): self._open_path(self.paths["logdata"])
    def _open_transcript(self): self._open_path(self.transcript.ensure_file())
    def _open_adif(self): self._open_path(self.adif.ensure_file())
    def _zlog_settings(self):
        from .integration_dialog import ZLogSettingsDialog
        ZLogSettingsDialog(self).exec()

    def _export_adif(self):
        from .adif_export_dialog import ADIFExportDialog
        ADIFExportDialog(self.adif, self.store, self).exec()
    def _export_hamlog(self):
        from .hamlog_export_dialog import HamlogExportDialog
        HamlogExportDialog(self.adif, self.store, self).exec()
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
        self._show_help(tr("起動コマンドフラグについて"), tr("psrtty.exe --reset-window\n\n保存されたウィンドウ位置・サイズ・最大化状態を無視して起動します。\n標準サイズは1280×800です。画面が狭い場合は表示可能範囲に縮小し、中央へ戻します。\n通常起動では前回の位置・サイズ・最大化状態を復元し、画面外なら画面内へ戻します。\n終了時に現在の状態を保存します。無線機設定・マクロ・ログは初期化しません。"))

    def _guide_initial(self):
        from .guide import GuideWindow
        title=tr('初期設定ガイド')
        win=self.help_windows.get(title)
        if win is None:
            win=GuideWindow(self); self.help_windows[title]=win
        win.showNormal(); win.raise_(); win.activateWindow()

    def _guide_ft8(self):
        self._show_help(tr('FT8環境からの設定方法'), tr('FT8で使用中のCOMとAudioをPSRTTYでも選びます。FT8ソフトは終了し、COM・Audioの競合を避けてください。\n\nAudio IN：無線機 → パソコン（USB Audio／LINE IN／マイク）\nAudio OUT：パソコン → 無線機（USB Audio／LINE OUT／スピーカー）\n\nWindowsでは有効なWASAPIデバイスを表示し、機器IDで保存します。旧版の番号指定は初回に選び直してください。未接続の機器を別の機器へ自動置換しません。INの「未設定」は入力を停止します。設定済みなら起動時から入力し、無線機の接続とは独立しています。「自動」はWindowsの既定デバイスです。USB機器を追加した場合はPSRTTYを再起動してください。\n\n接続時LSB-D自動切替は初期ONです。YaesuではDATA-LSB／DATA-Lに相当します。無線機側のDATA入力をUSBに設定してください。USB-Dは高度な設定で選択でき、YaesuではDATA-USB／DATA-Uに相当します。Mark/Spaceの極性も実機で確認してください。\n\nYaesu FT-991/A・FTX-1・FT-710・FTDX10・FTDX101D/MP・FTDX3000、Kenwood TS-590SG・TS-890S・TS-990SはHamlibで接続します。CATのCOMポートと速度を明示し、接続テストを行ってください。YaesuはEnhanced COM、CAT RTSをDISABLE（OFF）にしてください。'))

    def _guide_tuning(self): self._show_help(tr("RTTYチューニング"),tr("スペクトラムのMARK/SPACEガイドに2本のピークを合わせます。\nAUTO TUNEは設定されたShift（標準170 Hz）付近の2ピークを探します。\n幅RESETと位置RESETの両方で標準のMark 2125 / Space 2295 Hzへ戻せます。\nクリックでMARKを移動。MARK／SPACEの線は間隔を保ってドラッグできます。\nメイン画面のシフト幅で間隔を変更します。幅RESETは170 Hzへ、位置RESETはMARK 2125 Hzへ戻します。\n表示感度は波形の高さだけを調整します。"))

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
            QMessageBox.information(self, tr("バージョンアップ"), tr("ZIP更新はWindows EXE版で利用できます。ソース実行時は新しいソース一式を別フォルダーへ展開してください。")); return
        from .update_dialog import UpdateDialog
        if not UpdateDialog(self).exec(): return
        path, _ = QFileDialog.getOpenFileName(self, tr("PSRTTY配布ZIPを選択"), "", "ZIP (*.zip)")
        if not path: return
        self.update_action.setEnabled(False)
        def checked(info, error):
            self.update_action.setEnabled(True)
            if error:
                QMessageBox.warning(self, tr("更新ZIP"), str(error)); return
            if QMessageBox.question(self, tr("バージョンアップ"), tr('Ver{0} → Ver{1}\n設定・ログ・varのデータを保持し、更新前バックアップを作成します。\n信頼できる配布元のZIPであることを確認してください。\nPSRTTYを終了して更新し、自動で再起動しますか？').format(__version__, info['version'])) != QMessageBox.Yes:
                return
            self.disconnect_radio()
            if self.settings_window: self.settings_window.close()
            self.setEnabled(False)
            def prepared(stage, err):
                if err:
                    self.setEnabled(True); QMessageBox.warning(self, tr("更新準備"), str(err)); return
                try:
                    self.store.save()
                    launch_updater(stage, self.paths["root"])
                    self.close()
                except Exception as exc:
                    self.setEnabled(True); QMessageBox.warning(self, tr("更新開始"), str(exc))
            self.update_job = BackgroundJob(self, lambda: prepare_update(Path(path), self.paths["root"], __version__), prepared)
        self.update_job = BackgroundJob(self, lambda: inspect_zip(Path(path), __version__, self.paths["root"]), checked)

    def _set_time_zone(self, name):
        old=self.store.data['ui'].get('time_zone','JST')
        if name==old:return
        try:self.q_datetime.set_zone(name)
        except ValueError:
            self.statusBar().showMessage(tr('手動日時を正しく入力してから時刻表記を切り替えてください。'),8000)
            self._sync_view_checks();return
        self.store.data['ui']['time_zone']=name
        try:self.store.save()
        except Exception as exc:
            self.store.data['ui']['time_zone']=old;self.q_datetime.set_zone(old)
            self.statusBar().showMessage(tr('設定を保存できませんでした。')+' '+str(exc),8000)
            self._sync_view_checks();return
        for index in range(self.cards_layout.count()):
            card=self.cards_layout.itemAt(index).widget()
            if card and getattr(card,'when_utc',None):
                card.stamp_label.setText(card.when_utc.astimezone(display_zone(name)).strftime('%H:%M:%S')+' '+name)
        self._refresh_latest_qsos();self._sync_view_checks()

    def _build_printer_menu(self, file_menu):
        self.printer_menu=file_menu.addMenu(tr('RTTYプリンター'))
        self.printer_enable_action=self._act(self.printer_menu,tr('プリンター出力を有効にする'),self._printer_enable)
        self.printer_enable_action.setCheckable(True)
        self.printer_target_menu=self.printer_menu.addMenu(tr('印刷する内容'))
        self.printer_target_group=QActionGroup(self);self.printer_target_group.setExclusive(True)
        for code,label in [('RX','受信のみ（RX）'),('TX','送信のみ（TX）'),('RXTX','受信と送信（RX＋TX）')]:
            action=self._act(self.printer_target_menu,tr(label),lambda checked=False,c=code:self._printer_target(c))
            action.setCheckable(True);action.setData(code);self.printer_target_group.addAction(action)
        self._act(self.printer_menu,tr('プリンター設定…'),self._printer_settings)
        self.printer_menu.addSeparator()
        self.printer_test_action=self._act(self.printer_menu,tr('テスト印刷'),self._printer_test)
        self._act(self.printer_menu,tr('印刷待ちを消去'),self._printer_clear)

    def _printer_port_problem(self, settings):
        from ..printer import port_key
        port=port_key(settings['port'])
        if not port:return tr('プリンターのCOMポートを設定してください。')
        profiles=list(self.store.data.get('profiles',[]))+[self.store.data]
        for profile in profiles:
            radio=profile.get('radio',{});external=profile.get('external',{})
            if port==port_key(radio.get('com_port')) or port==port_key(external.get('com_port')):
                return tr('無線機・外部制御と別のCOMポートを選択してください。')
        radio=self.store.data['radio']
        if radio.get('model') and str(radio.get('com_port','AUTO')).upper()=='AUTO':
            return tr('プリンター使用時は無線機のCOMポートを自動ではなく指定してください。')
        if self.radio and port==port_key(getattr(self.radio.status,'port','')):
            return tr('無線機・外部制御と別のCOMポートを選択してください。')
        return ''

    def _printer_enable(self, checked):
        if checked:
            error=self._printer_port_problem(self.printer.settings)
            if error:self.printer.pause('config',error)
            elif not self.printer.enable(True):self.printer.pause('busy')
        else:self.printer.enable(False)
        self._refresh_printer_status()

    def _printer_target(self, code):
        old=self.store.data['printer']['target'];self.store.data['printer']['target']=code
        try:self.store.save()
        except Exception as exc:
            self.store.data['printer']['target']=old;self.printer.pause('config',str(exc))
        else:
            with self.printer.condition:self.printer.settings['target']=code
        self._refresh_printer_status()

    def _apply_printer_settings(self, values):
        state=self.printer.snapshot()
        if state['enabled'] or state['waiting']:return tr('出力をOFFにし、印刷停止を待ってから保存してください。')
        error=self._printer_port_problem(values)
        if error:return error
        old=dict(self.store.data['printer']);self.store.data['printer']=values
        try:self.store.save()
        except Exception as exc:
            self.store.data['printer']=old;return tr('設定を保存できませんでした。')+' '+str(exc)
        self.printer.configure(values);self._refresh_printer_status();return ''

    def _printer_settings(self):
        if self.printer_window is None:
            from .printer_dialog import PrinterDialog
            self.printer_window=PrinterDialog(self.store,self._apply_printer_settings,self)
            self.printer_window.finished.connect(lambda *_:setattr(self,'printer_window',None))
        self.printer_window.show();self.printer_window.raise_();self.printer_window.activateWindow()

    def _printer_test(self):
        error=self._printer_port_problem(self.printer.settings)
        if error:self.printer.pause('config',error)
        elif not self.printer.submit('TEST','PSRTTY PRINTER TEST 1234567890',zone=self.store.data['ui'].get('time_zone','JST'),test=True):
            # Keep existing fault / queue details; never interrupt a live print job.
            if not self.printer.snapshot()['problem']:self.printer.detail=tr('印刷待ちが空になってからテストしてください。')
        self._refresh_printer_status()

    def _printer_clear(self):
        self.printer.clear();self._refresh_printer_status()

    def _refresh_printer_status(self):
        state=self.printer.snapshot()
        if state['enabled']:
            error=self._printer_port_problem(self.printer.settings)
            if error:self.printer.pause('config',error);state=self.printer.snapshot()
        self.printer_enable_action.setChecked(state['enabled'])
        self.printer_enable_action.setText(tr('プリンター出力を無効にする' if state['enabled'] else 'プリンター出力を有効にする'))
        for action in self.printer_target_group.actions():action.setChecked(action.data()==self.store.data['printer']['target'])
        labels={'RX':'受信のみ（RX）','TX':'送信のみ（TX）','RXTX':'受信と送信（RX＋TX）'}
        problems={'full':'待ち上限・受付停止','error':'通信エラー・印刷停止','config':'設定を確認','busy':'停止処理中'}
        if state['problem']:
            template='プリンター：{status}／待ち{count}件' if state['problem']=='config' else 'プリンター停止：{status}／待ち{count}件'
            status=tr(problems.get(state['problem'],'設定を確認'))
        elif state['enabled']:
            template='プリンターが有効：{status}／待ち{count}件'
            status=tr(labels[self.store.data['printer']['target']])
        else:
            template='プリンター：{status}／待ち{count}件';status=tr('テスト印刷・停止処理中')
        self.printer_status.setText(tr(template).format(status=status,count=state['waiting']))
        self.printer_status.setVisible(bool(state['enabled'] or state['problem'] or state['waiting']))
        self.printer_status.setStyleSheet('color:#b3261e;' if state['problem'] else '')
        self.printer_status.setToolTip(tr('出力OFF・待ち消去では送出済みの印刷は取り消せない場合があります。')+'\n'+state['detail']+'\n'+tr('送出済み：{sent}件／受付漏れ・送出不明：{skipped}件').format(sent=state['sent'],skipped=state['skipped']))

    def closeEvent(self,event):
        if self.integration.busy:
            event.ignore()
            QTimer.singleShot(100, self.close)
            return
        if self.integration.dialog:
            self.integration.dialog.close()
        self.center_timer.stop()
        self.track_timer.stop()
        self.q_datetime.timer.stop()
        self.printer_timer.stop()
        self.printer.stop()
        if self.printer_window:self.printer_window.close()
        if not self.closing:
            self.closing = True
            self.scope_button.setChecked(False)
            if self.scope_window: self.scope_window.close()
            if self.sub_window:
                self.store.data['ui']['sub_window']=save_window(self.sub_window)
                self.sub_window.close()
            for window in self.help_windows.values(): window.close()
            if self.control_window:
                self.store.data['ui']['control_window']=save_window(self.control_window)
                self.control_window.close()
            if self.settings_window: self.settings_window.close()
            self.cq_count.normalize(); self.cq_interval.normalize(); self._remember_cq_options()
            self.store.data["ui"]["auto_get_call"] = self.auto_get.isChecked()
            self.store.data["ui"]["auto_log"] = self.auto_log.isChecked()
            self.store.data["station_callsign"] = normalize_call(self.my_call.text())
            self.store.data["ui"]["window"] = save_window(self)
            try:
                self.store.save()
            except Exception as exc:
                QMessageBox.warning(self, tr("終了時の設定保存"), tr('設定を保存できませんでした。ログバックアップと終了処理を続けます。\n{0}').format(exc))
            self.disconnect_radio()
            self._restart_audio_input()
        cleanup = getattr(self, "cleanup_job", None)
        if self.audio_input_busy or (cleanup and cleanup.thread.is_alive()) or self.audio._tx_active or self.printer.thread.is_alive():
            event.ignore()
            QTimer.singleShot(50, self.close)
        else:
            if not self.exit_backup_done:
                self.exit_backup_done = True
                if self.store.data.get("backup", {}).get("on_exit", True):
                    self._backup_logs()
            event.accept()
