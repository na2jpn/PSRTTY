from ..timebase import JST
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
        super().__init__(parent); self.record=record; self.result_record=None
        self.setWindowTitle('QSOログ編集'); self.resize(400,360)
        root=QVBoxLayout(self); form=QFormLayout(); root.addLayout(form); self.fields={}
        when=record.when_utc.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S') if record.when_utc else ''
        for name,label,value in [('when','日時（JST）',when),('call','CALL',record.call),
                ('freq','周波数（MHz）',record.freq_mhz),('rst_sent','RST-S',record.rst_sent),
                ('rst_rcvd','RST-R',record.rst_rcvd),('sent','SENT',record.sent),('rcvd','RCVD',record.rcvd)]:
            edit=QLineEdit(value); self.fields[name]=edit; form.addRow(label,edit)
        self.fields['when'].setPlaceholderText('2026-09-24 17:45 または秒付き')
        root.addWidget(QLabel('BANDは周波数から自動設定します。'))
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save); buttons.rejected.connect(self.reject); root.addWidget(buttons)

    def save(self):
        values={k:v.text().strip() for k,v in self.fields.items()}
        try:
            if not values['call']: raise ValueError('CALLを入力してください。')
            stamp=values['when']; fmt='%Y-%m-%d %H:%M:%S' if len(stamp)>16 else '%Y-%m-%d %H:%M'
            when=datetime.strptime(stamp,fmt).replace(tzinfo=JST).astimezone(timezone.utc)
            freq=None
            if values['freq']:
                number=Decimal(values['freq'])*1000000
                if not number.is_finite() or number!=number.to_integral_value() or not 0<number<15000000000:
                    raise ValueError('周波数をMHzで入力してください（小数点以下6桁まで）。')
                freq=int(number)
            self.result_record=replace(self.record,call=values['call'].upper(),when_utc=when,freq_hz=freq,
                **{k:values[k] for k in ('rst_sent','rst_rcvd','sent','rcvd')})
        except (ValueError,InvalidOperation) as exc:
            QMessageBox.warning(self,'入力の確認',f'日時・周波数・CALLを確認してください。\n{exc}'); return
        self.accept()


class QSOLogDialog(QDialog):
    changed=Signal()
    def __init__(self, adif, parent=None):
        super().__init__(parent); self.adif=adif; self.records=[]
        self.setWindowTitle('QSOログ'); self.resize(1080,520)
        root=QVBoxLayout(self); self.table=QTableWidget(0,8)
        self.table.setHorizontalHeaderLabels(['日時（JST）','CALL','BAND','FREQ（MHz）','RST-S','RST-R','SENT','RCVD'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self.edit_selected); root.addWidget(self.table)
        row=QHBoxLayout(); self.edit_button=QPushButton('編集'); self.delete_button=QPushButton('削除')
        self.edit_button.clicked.connect(self.edit_selected); self.delete_button.clicked.connect(self.delete_selected)
        row.addWidget(self.edit_button); row.addWidget(self.delete_button)
        refresh=QPushButton('更新'); refresh.clicked.connect(self.reload); row.addWidget(refresh); row.addStretch(1)
        close=QPushButton('閉じる'); close.clicked.connect(self.accept); row.addWidget(close); root.addLayout(row)
        self.note=QLabel('編集・削除前に元のADIFをlogdata/backupsへ保存します。'); root.addWidget(self.note)
        self.table.itemSelectionChanged.connect(self.selection_changed); self.reload()

    def reload(self):
        try: records=list(reversed(self.adif.load_recent(limit=None)))
        except (OSError,ValueError) as exc:
            QMessageBox.warning(self,'ログ読み込み失敗',str(exc)); return
        errors=getattr(self.adif,'read_errors',[])
        self.note.setText('読み込めないファイルがあります：'+' / '.join(errors) if errors else '編集・削除前に元のADIFをlogdata/backupsへ保存します。')
        self.note.setWordWrap(True)
        self.records=records; self.table.setRowCount(len(records))
        for row,q in enumerate(records):
            when=q.when_utc.astimezone(JST).strftime('%Y-%m-%d %H:%M') if q.when_utc else ''
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
        when=record.when_utc.astimezone(JST).strftime('%Y-%m-%d %H:%M') if record.when_utc else '日時不明'
        answer=QMessageBox.question(self,'QSOの削除',f'{when}  {record.call}  {band_text(record)}\nこのQSOを削除しますか？',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)
        if answer==QMessageBox.Yes: self.apply_change(record,None)

    def apply_change(self, original, replacement):
        try: self.adif.modify(original,replacement)
        except (OSError,ValueError,RuntimeError) as exc:
            QMessageBox.warning(self,'ログを変更できませんでした',str(exc)); return False
        self.reload(); self.changed.emit(); return True
