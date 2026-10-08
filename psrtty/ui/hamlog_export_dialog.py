from ..i18n import tr
"""Reuse the established period/band/QSO selection for HAMLOG CSV."""
from pathlib import Path
from PySide6.QtWidgets import QCheckBox, QFileDialog, QLabel
from .adif_export_dialog import ADIFExportDialog
from ..hamlog_csv import export_hamlog


class HamlogExportDialog(ADIFExportDialog):
    def __init__(self, adif, store, parent=None):
        super().__init__(adif, store, parent)
        self.setWindowTitle(tr('ui.1549f66e50d1b3f7'))
        self.profile.hide(); self.profile_note.hide()
        for label in self.pages.widget(2).findChildren(QLabel):
            if 'ADIF' in label.text():
                label.setText(tr('ui.09cd37a8de26ab77'))
        layout = self.pages.widget(3).layout()
        self.include_station = QCheckBox(tr('ui.9364849de45a1174'))
        self.include_station.setChecked(True)
        layout.insertWidget(1, self.include_station)
        note = QLabel(tr('ui.44bffe3f594f8a03'))
        note.setWordWrap(True); layout.insertWidget(2, note)

    def _set_page(self, index):
        super()._set_page(index)
        if index == 3:
            self.next.setText(tr('ui.99720da1ac7480f6'))

    def go_next(self):
        if self.pages.currentIndex() != 3:
            super().go_next()
            if self.pages.currentIndex() == 3:
                self.summary.setText(self.summary.text().replace(tr('ui.415874df50b9566e'), tr('ui.1549f66e50d1b3f7')))
            return
        name = self.station.text().strip().upper().replace('/', '_') + '_hamlog.csv'
        path, _ = QFileDialog.getSaveFileName(self, tr('ui.3b24cf802b52c79d'), name, 'CSV (*.csv)')
        if not path:
            return
        try:
            export_hamlog(path, self.selected, protected=[q.source_path for q in self.records],
                          include_station=self.include_station.isChecked())
        except (OSError, ValueError) as exc:
            self.message.setText(tr(str(exc))); return
        self.saved_path = Path(path); self.saved.setText(f"{tr('ui.4b8bb41f0172e9c0')}{path}")
        self.message.clear(); self.open_folder.setEnabled(True)
