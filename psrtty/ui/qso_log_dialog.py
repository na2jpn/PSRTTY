from ..i18n import tr
from ..timebase import JST, display_zone, zone_name
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHeaderView, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QHBoxLayout, QPushButton, QFormLayout, QLineEdit,
    QDialogButtonBox, QMessageBox, QLabel)
from .formatting import band_text, frequency_text


class QSOEditDialog(QDialog):
    def __init__(self, record, parent=None):
        super().__init__(parent); self.zone_name=zone_name(parent); self.zone=display_zone(self.zone_name); self.record=record; self.result_record=None
        self.setWindowTitle(tr('ui.8f0b81fc33042aaa')); self.resize(400,360)
        root=QVBoxLayout(self); form=QFormLayout(); root.addLayout(form); self.fields={}
        when=record.when_utc.astimezone(self.zone).strftime('%Y-%m-%d %H:%M:%S') if record.when_utc else ''
        for name,label,value in [('when',tr('ui.7465f9bf63f15817').format(zone=self.zone_name),when),('call','CALL',record.call),
                ('freq',tr('ui.37978fb750aaba77'),record.freq_mhz),('rst_sent','RST-S',record.rst_sent),
                ('rst_rcvd','RST-R',record.rst_rcvd),('sent','SENT',record.sent),('rcvd','RCVD',record.rcvd)]:
            edit=QLineEdit(value); self.fields[name]=edit; form.addRow(label,edit)
        self.fields['when'].setPlaceholderText(tr('ui.1abf86e624e267c8'))
        root.addWidget(QLabel(tr('ui.d862b2a28bfd8c9e')))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def save(self):
        values={k:v.text().strip() for k,v in self.fields.items()}
        try:
            if not values['call']: raise ValueError(tr('ui.833150df3abe87bf'))
            stamp=values['when']; fmt='%Y-%m-%d %H:%M:%S' if len(stamp)>16 else '%Y-%m-%d %H:%M'
            when=datetime.strptime(stamp,fmt).replace(tzinfo=self.zone).astimezone(timezone.utc)
            freq=None
            if values['freq']:
                number=Decimal(values['freq'])*1000000
                if not number.is_finite() or number!=number.to_integral_value() or not 0<number<15000000000:
                    raise ValueError(tr('ui.56b663024f1d70ae'))
                freq=int(number)
            self.result_record=replace(self.record,call=values['call'].upper(),when_utc=when,freq_hz=freq,
                **{k:values[k] for k in ('rst_sent','rst_rcvd','sent','rcvd')})
        except (ValueError,InvalidOperation) as exc:
            QMessageBox.warning(self,tr('ui.1f24f703e7d1e117'),tr('ui.c47356d72f46fd52').format(exc)); return
        self.accept()


class QSOLogDialog(QDialog):
    changed=Signal()
    def __init__(self, adif, parent=None):
        super().__init__(parent); self.zone_name=zone_name(parent); self.zone=display_zone(self.zone_name); self.adif=adif; self.records=[]
        self.setWindowTitle(tr('ui.9bce269cb36c4072')); self.resize(1080,520)
        root=QVBoxLayout(self); self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels([tr('ui.7465f9bf63f15817').format(zone=self.zone_name),'CALL','BAND','FREQ（MHz）','RST-S','RST-R','SENT','RCVD'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_selected); root.addWidget(self.table)
        row=QHBoxLayout(); self.edit_button=QPushButton(tr('ui.11f9049ddab593ad')); self.delete_button=QPushButton(tr('ui.e9653dc3edcbc072'))
        self.edit_button.clicked.connect(self.edit_selected); self.delete_button.clicked.connect(self.delete_selected)
        row.addWidget(self.edit_button); row.addWidget(self.delete_button)
        refresh=QPushButton(tr('ui.3055a035f0eb7a8b')); refresh.clicked.connect(self.reload); row.addWidget(refresh); row.addStretch(1)
        close=QPushButton(tr('ui.f6c244f98893cd95')); close.clicked.connect(self.accept); row.addWidget(close); root.addLayout(row)
        self.note=QLabel(tr('ui.d70088ea89681a81')); root.addWidget(self.note)
        self.table.itemSelectionChanged.connect(self.selection_changed); self.reload()

    def reload(self):
        try: records=list(reversed(self.adif.load_recent(limit=None)))
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,tr('ui.d0da781eab4d3ece'),tr(str(exc))); return
        errors=getattr(self.adif,'read_errors',[])
        self.note.setText(tr('ui.41961539f83e93ce')+' / '.join(errors) if errors else tr('ui.d70088ea89681a81'))
        self.note.setWordWrap(True)
        self.records=records; self.table.setRowCount(len(records))
        for row,q in enumerate(records):
            when=q.when_utc.astimezone(self.zone).strftime('%Y-%m-%d %H:%M') if q.when_utc else ''
            vals=[when,q.call,band_text(q),frequency_text(q.freq_hz).removesuffix(' MHz') if q.freq_hz else '',q.rst_sent,q.rst_rcvd,q.sent,q.rcvd]
            for col,value in enumerate(vals): self.table.setItem(row,col,QTableWidgetItem(str(value)))
        self.table.clearSelection(); self.selection_changed()

    def selected(self):
        rows=self.table.selectionModel().selectedRows()
        return self.records[rows[0].row()] if rows else None

    def selection_changed(self):
        enabled=self.selected() is not None
        self.edit_button.setEnabled(enabled); self.delete_button.setEnabled(enabled)

    def edit_selected(self, *args):
        record=self.selected()
        if record is None: return
        dialog=QSOEditDialog(record,self)
        if dialog.exec()==QDialog.Accepted: self.apply_change(record,dialog.result_record)

    def delete_selected(self):
        record=self.selected()
        if record is None: return
        when=record.when_utc.astimezone(self.zone).strftime('%Y-%m-%d %H:%M') if record.when_utc else tr('ui.cc47fbd863afb5a0')
        answer=QMessageBox.question(self,tr('ui.8b6c8fd02ec13a8e'),tr('ui.34486ca000fd7e2f').format(when, record.call, band_text(record)),QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer==QMessageBox.Yes: self.apply_change(record,None)

    def apply_change(self, original, replacement):
        try: self.adif.modify(original,replacement)
        except (OSError,ValueError,RuntimeError) as exc:
            QMessageBox.warning(self,tr('ui.d30b0e0b3b109463'),tr(str(exc))); return False
        self.reload(); self.changed.emit(); return True
