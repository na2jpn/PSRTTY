from ..i18n import tr
"""Select QSO records and write a separate ADIF file without changing source logs."""

from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from PySide6.QtCore import Qt, QDateTime, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialog, QFileDialog, QFormLayout, QHBoxLayout,
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
        self.setWindowTitle(tr('ui.59b7b381dc3dba39'))
        self.resize(930, 620)
        root = QVBoxLayout(self)
        self.heading = QLabel()
        root.addWidget(self.heading)
        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)
        self.profile = QComboBox()
        for label, value in ((tr('ui.a2d08805378be7dc'), 'standard'), (tr('ui.f910fd885ff47cc0'), 'zlog'), ('zLog / JARL WW RTTY', 'zlog_jarl'), ('zLog / CQ WW RTTY', 'zlog_cqww')):
            self.profile.addItem(label, value)
        root.insertWidget(1, self.profile)
        self.profile_note = QLabel(tr('ui.ac8666939cee47ae'))
        self.profile_note.setWordWrap(True); root.insertWidget(2, self.profile_note)
        self._period_page()
        self._band_page()
        self._qso_page()
        self._confirm_page()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setStyleSheet('color: #b3261e;')
        root.addWidget(self.message)
        row = QHBoxLayout()
        self.back = QPushButton(tr('ui.8fc7f899161b2076')); self.back.clicked.connect(self.go_back); row.addWidget(self.back)
        row.addStretch()
        self.next = QPushButton(tr('ui.9eccdca31ee358be')); self.next.clicked.connect(self.go_next); row.addWidget(self.next)
        close = QPushButton(tr('ui.f6c244f98893cd95')); close.clicked.connect(self.reject); row.addWidget(close)
        root.addLayout(row)
        self._set_page(0)

    def _page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.pages.addWidget(page)
        return layout

    def _period_page(self):
        layout = self._page()
        layout.addWidget(QLabel(tr('ui.08fd81603d4e1b52')))
        form = QFormLayout()
        self.start = QDateTimeEdit(); self.end = QDateTimeEdit()
        now = datetime.now(self.display_zone)
        for control, value in ((self.start, now.replace(day=1, hour=0, minute=0, second=0)), (self.end, now)):
            control.setDisplayFormat('yyyy-MM-dd HH:mm')
            control.setCalendarPopup(True)
            control.setDateTime(QDateTime.fromString(value.strftime('%Y-%m-%d %H:%M'), 'yyyy-MM-dd HH:mm'))
        form.addRow(tr('ui.6ff7480186050ed9').format(zone=self.zone_name), self.start); form.addRow(tr('ui.f17b539eb4119371').format(zone=self.zone_name), self.end)
        self.station = QLineEdit(str(self.store.data.get('station_callsign', '')).strip().upper())
        form.addRow(tr('ui.3804e46344d52b7e'), self.station)
        layout.addLayout(form); layout.addStretch()

    def _band_page(self):
        layout = self._page()
        layout.addWidget(QLabel(tr('ui.cf47be8417340f46')))
        self.band_container = QWidget()
        self.band_layout = QVBoxLayout(self.band_container)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(self.band_container)
        layout.addWidget(scroll, 1)
        self.band_checks = {}

    def _qso_page(self):
        layout = self._page()
        layout.addWidget(QLabel(tr('ui.a3abc092efc1924d')))
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([tr('ui.d38a2a54cf74a633'), tr('ui.7465f9bf63f15817').format(zone=self.zone_name), tr('ui.80a9493aebeec321'), tr('ui.22edd69c9f0e6e6c'), tr('ui.2fd63b6fa8786d53'), 'MHz', tr('ui.f92454091c681d34')])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._update_count)
        layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        for label, checked in ((tr('ui.4cd31aa46c545a36'), True), (tr('ui.c90bb75fa377b91e'), False)):
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
        self.open_folder = QPushButton(tr('ui.8604f0acbccd3b83'))
        self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path.parent))) if self.saved_path else None)
        layout.addWidget(self.open_folder)
        layout.addStretch()

    def _set_page(self, index):
        self.pages.setCurrentIndex(index)
        self.heading.setText([tr('ui.9c760e3104bf7e0b'), tr('ui.6561edc60102bac4'), tr('ui.5285c2db1d4c7d2c'), tr('ui.b54f06bea9866677')][index])
        self.back.setEnabled(index > 0)
        self.next.setText(tr('ui.529a0d232f04dd50') if index == 3 else tr('ui.9eccdca31ee358be'))
        self.message.clear()

    def _bounds(self):
        def read(control):
            return datetime.strptime(control.dateTime().toString('yyyy-MM-dd HH:mm'), '%Y-%m-%d %H:%M').replace(tzinfo=self.display_zone).astimezone(timezone.utc)
        return read(self.start), read(self.end) + timedelta(minutes=1)

    def _prepare_bands(self):
        call = self.station.text().strip().upper()
        if not call:
            self.message.setText(tr('ui.b395032bd0f277e3')); return False
        start, end = self._bounds()
        if start >= end:
            self.message.setText(tr('ui.ad841ef61b9f1dfc')); return False
        try:
            self.records = self.adif.load_recent(limit=None)
        except Exception:
            self.message.setText(tr('ui.d1e33d96a9f6e09f')); return False
        if getattr(self.adif, 'read_errors', []):
            self.message.setText(tr('ui.3bfa0e7d5ae87e87')); return False
        self.filtered = [q for q in self.records if q.when_utc is not None and
                         start <= q.when_utc.astimezone(timezone.utc) < end and
                         q.station_callsign.upper() == call]
        counts = Counter(q.band for q in self.filtered if q.band)
        if not counts:
            self.message.setText(tr('ui.89626ca56f59b382')); return False
        for checkbox in self.band_checks.values():
            self.band_layout.removeWidget(checkbox); checkbox.deleteLater()
        self.band_checks.clear()
        for band, count in sorted(counts.items()):
            box = QCheckBox(f"{band}（{count}{tr('ui.98b4c196e911e8fb')}")
            self.band_checks[band] = box
            self.band_layout.addWidget(box)
        return True

    def _prepare_qsos(self):
        selected_bands = {band for band, box in self.band_checks.items() if box.isChecked()}
        if not selected_bands:
            self.message.setText(tr('ui.3379e27a3f5ceac9')); return False
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
        self.count.setText(f"{tr('ui.f2d7ce134ccf4f77')}{count}{tr('ui.4231871a947a5a78')}{self.table.rowCount()}{tr('ui.7c00255577088ec9')}")

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
                self.message.setText(tr('ui.024349172e8186f3')); return
            start, end = self._bounds()
            bands = ', '.join(sorted({q.band for q in self.selected}))
            self.summary.setText(tr('ui.b8464415fb19c869').format(call=self.station.text().strip().upper(), start=start.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M'), end=(end-timedelta(seconds=1)).astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M'), zone=self.zone_name, bands=bands, count=len(self.selected)))
            self.saved.clear(); self.saved_path = None; self.open_folder.setEnabled(False)
            self._set_page(3)
        else:
            name = self.station.text().strip().upper().replace('/', '_') + '_selected.adi'
            path, _ = QFileDialog.getSaveFileName(self, tr('ui.88d1e436abcab8f0'), name, 'ADIF (*.adi *.adif)')
            if not path: return
            try:
                export_adif(Path(path), self.selected, protected=[q.source_path for q in self.records], profile=self.profile.currentData())
            except (OSError, ValueError) as exc:
                self.message.setText(tr(str(exc))); return
            self.saved_path = Path(path)
            self.saved.setText(f"{tr('ui.4b8bb41f0172e9c0')}{path}")
            self.open_folder.setEnabled(True)
