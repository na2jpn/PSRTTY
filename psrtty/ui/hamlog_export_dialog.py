from ..i18n import tr
"""Reuse the established period/band/QSO selection for HAMLOG CSV."""
from pathlib import Path
from PySide6.QtWidgets import QCheckBox, QFileDialog, QLabel
from .adif_export_dialog import ADIFExportDialog
from ..hamlog_csv import export_hamlog


class HamlogExportDialog(ADIFExportDialog):
    def __init__(self, adif, store, parent=None):
        super().__init__(adif, store, parent)
        self.setWindowTitle(tr('HAMLOG-CSV出力'))
        self.profile.hide(); self.profile_note.hide()
        for label in self.pages.widget(2).findChildren(QLabel):
            if 'ADIF' in label.text():
                label.setText(tr('CSVに含める交信にチェックを入れてください。元のログは変更しません。'))
        layout = self.pages.widget(3).layout()
        self.include_station = QCheckBox(tr('Remarks2に自局CALLを出力する'))
        self.include_station.setChecked(True)
        layout.insertWidget(1, self.include_station)
        note = QLabel(tr('HAMLOG V5形式・15項目・ヘッダーなし。日時はJST（時刻末尾J）です。\n'
                      'Remarks1：SENT／RCVD、Remarks2：MYCALL。未記録のCode・GL・QSL・名前・QTH・DXは空欄です。'))
        note.setWordWrap(True); layout.insertWidget(2, note)

    def _set_page(self, index):
        super()._set_page(index)
        if index == 3:
            self.next.setText(tr('HAMLOG-CSVに保存'))

    def go_next(self):
        if self.pages.currentIndex() != 3:
            super().go_next()
            if self.pages.currentIndex() == 3:
                self.summary.setText(self.summary.text().replace(tr('ADIF出力'), tr('HAMLOG-CSV出力')))
            return
        name = self.station.text().strip().upper().replace('/', '_') + '_hamlog.csv'
        path, _ = QFileDialog.getSaveFileName(self, tr('HAMLOG-CSVを保存'), name, 'CSV (*.csv)')
        if not path:
            return
        try:
            export_hamlog(path, self.selected, protected=[q.source_path for q in self.records],
                          include_station=self.include_station.isChecked())
        except (OSError, ValueError) as exc:
            self.message.setText(str(exc)); return
        self.saved_path = Path(path); self.saved.setText(f"{tr('保存しました：')}{path}")
        self.message.clear(); self.open_folder.setEnabled(True)
