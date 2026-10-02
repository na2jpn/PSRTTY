from ..i18n import tr
"""Select QSO records and write a separate ADIF file without changing source logs."""

from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QDateTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QDateTimeEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from ..adif import export_adif
from ..timebase import display_zone

JST = timezone(timedelta(hours=9))


class ADIFExportDialog(QDialog):
    def __init__(self, adif, store, parent=None):
        super().__init__(parent)
        self.adif, self.store = adif, store
        self.zone_name=store.data["ui"].get("time_zone","JST")
        self.display_zone=display_zone(self.zone_name)
        self.records = []
        self.filtered = []
        self.selected = []
        self.saved_path = None
        self.setWindowTitle(tr('ADIFファイル出力'))
        self.resize(930, 620)
        root = QVBoxLayout(self)
        self.heading = QLabel()
        root.addWidget(self.heading)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self._period_page()
        self._band_page()
        self._qso_page()
        self._confirm_page()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet('color: #b3261e;')
        root.addWidget(self.message)
        row = QHBoxLayout()
        self.back = QPushButton(tr('戻る')); self.back.clicked.connect(self.go_back); row.addWidget(self.back)
        row.addStretch()
        self.next = QPushButton(tr('次へ')); self.next.clicked.connect(self.go_next); row.addWidget(self.next)
        close = QPushButton(tr('閉じる')); close.clicked.connect(self.reject); row.addWidget(close)
        root.addLayout(row)
        self._set_page(0)

    def _page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.pages.addWidget(page)
        return layout

    def _period_page(self):
        layout = self._page()
        layout.addWidget(QLabel(tr('抽出する交信期間と、運用した自局コールサインを指定してください。')))
        form = QFormLayout()
        self.start = QDateTimeEdit(); self.end = QDateTimeEdit()
        now = datetime.now(self.display_zone)
        for control, value in ((self.start, now.replace(day=1, hour=0, minute=0, second=0)), (self.end, now)):
            control.setDisplayFormat('yyyy-MM-dd HH:mm')
            control.setCalendarPopup(True)
            control.setDateTime(QDateTime.fromString(value.strftime('%Y-%m-%d %H:%M'), 'yyyy-MM-dd HH:mm'))
        form.addRow(tr('開始（{zone}）').format(zone=self.zone_name), self.start); form.addRow(tr('終了（{zone}、指定分を含む）').format(zone=self.zone_name), self.end)
        self.station = QLineEdit(str(self.store.data.get('station_callsign', '')).strip().upper())
        form.addRow(tr('運用自局コールサイン'), self.station)
        layout.addLayout(form); layout.addStretch()

    def _band_page(self):
        layout = self._page()
        layout.addWidget(QLabel(tr('対象の期間・自局コールのログにあるバンドから選択してください。')))
        self.band_container = QWidget()
        self.band_layout = QVBoxLayout(self.band_container)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.band_container)
        layout.addWidget(scroll, 1)
        self.band_checks = {}

    def _qso_page(self):
        layout = self._page()
        layout.addWidget(QLabel(tr('ADIFに含める交信にチェックを入れてください。元のログは変更しません。')))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([tr('出力'), tr('日時（{zone}）').format(zone=self.zone_name), tr('自局CALL'), tr('相手CALL'), tr('バンド'), 'MHz', tr('受信番号')])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._update_count)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        for label, checked in ((tr('全選択'), True), (tr('全解除'), False)):
            button = QPushButton(label)
            button.clicked.connect(lambda _=False, value=checked: self._check_all(value))
            row.addWidget(button)
        row.addStretch()
        self.count = QLabel(); row.addWidget(self.count)
        layout.addLayout(row)

    def _confirm_page(self):
        layout = self._page()
        self.summary = QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.saved = QLabel(); self.saved.setWordWrap(True); layout.addWidget(self.saved)
        self.open_folder = QPushButton(tr('保存先フォルダーを開く'))
        self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path.parent))) if self.saved_path else None)
        layout.addWidget(self.open_folder)
        layout.addStretch()

    def _set_page(self, index):
        self.pages.setCurrentIndex(index)
        self.heading.setText([tr('① 期間・自局コール'), tr('② バンド選択'), tr('③ 対象交信の選択'), tr('④ 確認・保存')][index])
        self.back.setEnabled(index > 0)
        self.next.setText(tr('ADIFファイルに保存') if index == 3 else tr('次へ'))
        self.message.clear()

    def _bounds(self):
        def read(control):
            return datetime.strptime(control.dateTime().toString('yyyy-MM-dd HH:mm'), '%Y-%m-%d %H:%M').replace(tzinfo=self.display_zone).astimezone(timezone.utc)
        return read(self.start), read(self.end) + timedelta(minutes=1)

    def _prepare_bands(self):
        call = self.station.text().strip().upper()
        if not call:
            self.message.setText(tr('運用自局コールサインを入力してください。')); return False
        start, end = self._bounds()
        if start >= end:
            self.message.setText(tr('開始日時は終了日時以前にしてください。')); return False
        try:
            self.records = self.adif.load_recent(limit=None)
        except Exception:
            self.message.setText(tr('ADIFログを読み込めませんでした。')); return False
        if getattr(self.adif, 'read_errors', []):
            self.message.setText(tr('読み込めないADIFログがあります。ログファイルを確認してください。')); return False
        self.filtered = [q for q in self.records if q.when_utc is not None and
                         start <= q.when_utc.astimezone(timezone.utc) < end and
                         q.station_callsign.upper() == call]
        counts = Counter(q.band for q in self.filtered if q.band)
        if not counts:
            self.message.setText(tr('指定した期間と自局コールに該当する交信がありません。')); return False
        for checkbox in self.band_checks.values():
            self.band_layout.removeWidget(checkbox); checkbox.deleteLater()
        self.band_checks.clear()
        for band, count in sorted(counts.items()):
            box = QCheckBox(f"{band}（{count}{tr('件）')}")
            self.band_checks[band] = box
            self.band_layout.addWidget(box)
        return True

    def _prepare_qsos(self):
        selected_bands = {band for band, box in self.band_checks.items() if box.isChecked()}
        if not selected_bands:
            self.message.setText(tr('バンドを1つ以上選択してください。')); return False
        self.candidates = [q for q in self.filtered if q.band in selected_bands]
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.candidates))
        for row, q in enumerate(self.candidates):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsUserCheckable)
            check.setCheckState(Qt.Checked)
            self.table.setItem(row, 0, check)
            when = q.when_utc.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M')
            for col, value in enumerate((when, q.station_callsign, q.call, q.band, q.freq_mhz, q.rcvd), 1):
                item = QTableWidgetItem(value); item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self._update_count()
        return True

    def _update_count(self, *_):
        count = sum(self.table.item(row, 0).checkState() == Qt.Checked for row in range(self.table.rowCount()) if self.table.item(row, 0))
        self.count.setText(f"{tr('選択 ')}{count}{tr('件 / 対象 ')}{self.table.rowCount()}{tr('件')}")

    def _check_all(self, checked):
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def go_back(self):
        if self.pages.currentIndex() > 0:
            self._set_page(self.pages.currentIndex() - 1)

    def go_next(self):
        index = self.pages.currentIndex()
        self.message.clear()
        if index == 0:
            if self._prepare_bands(): self._set_page(1)
        elif index == 1:
            if self._prepare_qsos(): self._set_page(2)
        elif index == 2:
            self.selected = [q for row, q in enumerate(self.candidates) if self.table.item(row, 0).checkState() == Qt.Checked]
            if not self.selected:
                self.message.setText(tr('交信を1件以上選択してください。')); return
            start, end = self._bounds()
            bands = ', '.join(sorted({q.band for q in self.selected}))
            self.summary.setText(tr('運用自局コール：{call}\n期間：{start} ～ {end} {zone}\nバンド：{bands}\nADIF出力：{count}件').format(call=self.station.text().strip().upper(), start=start.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M'), end=(end-timedelta(seconds=1)).astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M'), zone=self.zone_name, bands=bands, count=len(self.selected)))
            self.saved.clear(); self.saved_path = None; self.open_folder.setEnabled(False)
            self._set_page(3)
        else:
            name = self.station.text().strip().upper().replace('/', '_') + '_selected.adi'
            path, _ = QFileDialog.getSaveFileName(self, tr('ADIFを保存'), name, 'ADIF (*.adi *.adif)')
            if not path: return
            try:
                export_adif(Path(path), self.selected, protected=[q.source_path for q in self.records])
            except (OSError, ValueError) as exc:
                self.message.setText(str(exc)); return
            self.saved_path = Path(path)
            self.saved.setText(f"{tr('保存しました：')}{path}")
            self.open_folder.setEnabled(True)
