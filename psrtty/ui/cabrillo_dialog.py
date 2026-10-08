from ..i18n import tr
from ..timebase import display_zone
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
import traceback
import re
from PySide6.QtCore import Qt, QDateTime, QUrl
from PySide6.QtGui import QDesktopServices, QFontDatabase, QColor, QBrush
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QPushButton,
    QSizePolicy,QRadioButton,QButtonGroup,QStackedWidget,QLineEdit,QComboBox,QSpinBox,QDateTimeEdit,QTableWidget,
    QTableWidgetItem,QHeaderView,QAbstractItemView,QPlainTextEdit,QScrollArea,QMessageBox,QFileDialog,QCheckBox)
from ..paths import app_root
from ..paths import resource_path
from ..jarl_score import calculate, CONTINENTS, location_label
import csv
from ..adif import band_from_hz
from ..cabrillo import PROFILES,CONTESTS,HF_BANDS,BANDS,DEFAULT_LAYOUT,JST,period,build_cabrillo,save_cabrillo


class CabrilloDialog(QDialog):
    def __init__(self, adif, store, parent=None):
        super().__init__(parent)
        self.adif=adif;self.store=store;self.profile='generic';self.loaded_profile=None
        self.records=[];self.states={};self.visible=[];self.read_errors=[];self.body='';self.saved_path=None
        self.display_zone=display_zone(store.data['ui'].get('time_zone','JST'));self.fields={};self.profile_forms={};self.has_table=False
        self.setWindowTitle(tr('ui.bc8305cda034b7cc'));self.resize(1080,720)
        root=QVBoxLayout(self)
        self.heading=QLabel();root.addWidget(self.heading)
        self.pages=QStackedWidget();root.addWidget(self.pages,1)
        self._format_page();self._qso_page();self._optional_page()
        self._info_page();self._preview_page();self._cq_setup_page()
        self._jarl_category_page();self._jarl_site_page();self._jarl_score_page()
        self.cq_warning = QLabel();self.cq_warning.setWordWrap(True)
        self.cq_warning.setStyleSheet('color: #b3261e;')
        root.addWidget(self.cq_warning)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setStyleSheet('color: #b3261e;');root.addWidget(self.error)
        row=QHBoxLayout();self.back=QPushButton(tr('ui.8fc7f899161b2076'));self.back.clicked.connect(self.go_back);row.addWidget(self.back)
        row.addStretch();self.next=QPushButton(tr('ui.9eccdca31ee358be'));self.next.clicked.connect(self.go_next);row.addWidget(self.next)
        close=QPushButton(tr('ui.f6c244f98893cd95'));close.clicked.connect(self.reject);row.addWidget(close);root.addLayout(row)
        self._set_page(0)

    def _page(self):
        page=QWidget();layout=QVBoxLayout(page);self.pages.addWidget(page);return layout

    def _format_page(self):
        layout=self._page();layout.addWidget(QLabel(tr('ui.d8b7b12de55437d8')))
        self.formats=QButtonGroup(self)
        for i,(key,title) in enumerate(PROFILES.items()):
            button=QRadioButton(tr(title));button.setProperty('profile',key);self.formats.addButton(button,i);layout.addWidget(button)
        self.formats.button(0).setChecked(True)
        note=QLabel(tr('ui.49aa44b7fe7a797e'))
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch()

    def _qso_page(self):
        layout=self._page();row=QHBoxLayout()
        row.addWidget(QLabel(tr('ui.150df68b4eb7b80d')));self.year=QSpinBox();self.year.setRange(2000,2100);self.year.setValue(datetime.now().year);row.addWidget(self.year)
        self.dates=QPushButton(tr('ui.6d36f344c7569ded'));self.dates.clicked.connect(self.set_period);row.addWidget(self.dates)
        row.addWidget(QLabel(tr('ui.cbfc69d69f36741e')));self.zone=QComboBox();self.zone.addItems(['JST','UTC']);self.zone.setCurrentText(self.store.data['ui'].get('time_zone','JST'));self.zone.currentTextChanged.connect(self.change_zone);row.addWidget(self.zone);row.addStretch();layout.addLayout(row)
        self.year.valueChanged.connect(self.update_period_label);self.update_period_label()
        self.period_note=QLabel(tr('ui.1621ef317ef1e916'))
        self.period_note.setWordWrap(True);self.period_note.setStyleSheet('color: #1565c0;');layout.addWidget(self.period_note)
        row=QHBoxLayout();self.start=QDateTimeEdit();self.end=QDateTimeEdit()
        for edit in (self.start,self.end):
            edit.setDisplayFormat('yyyy-MM-dd HH:mm');edit.setCalendarPopup(True)
            edit.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        now=datetime.now(self.display_zone)
        self._display_datetime(self.start,now.replace(day=1,hour=0,minute=0,second=0,microsecond=0))
        self._display_datetime(self.end,now)
        self.start_label=QLabel(tr('ui.cc147e162c82bbc7'));self.end_label=QLabel(tr('ui.17737e53e7ff18bb'))
        row.addWidget(self.start_label);row.addWidget(self.start);row.addSpacing(12)
        row.addWidget(self.end_label);row.addWidget(self.end);row.addStretch();layout.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel(tr('ui.6f0d295e04c1972e')))
        self.call_filter=QLineEdit(store_call(self.store));self.call_filter.setPlaceholderText(tr('ui.51d855357f9048e6'));row.addWidget(self.call_filter)
        self.band_filter=QComboBox();self.band_filter.addItems(['ALL','80M','40M','20M','15M','10M','160M','6M','2M','70CM','23CM']);row.addWidget(self.band_filter)
        apply=QPushButton(tr('ui.aeeedd0389aec917'));apply.clicked.connect(self.apply_filter);row.addWidget(apply)
        reload=QPushButton(tr('ui.9ecfa373790f0d0d'));reload.clicked.connect(self.reload);row.addWidget(reload);layout.addLayout(row)
        self.filter_note=QLabel(tr('ui.9f501cac95e96d1a'))
        self.filter_note.setWordWrap(True);layout.addWidget(self.filter_note)
        self.table=QTableWidget(0,12)
        self.table.setHorizontalHeaderLabels([tr('ui.d38a2a54cf74a633'),tr('ui.11b74db9d1db6b92'),tr('ui.80a9493aebeec321'),tr('ui.22edd69c9f0e6e6c'),'MHz','RST-S','RST-R','SENT','RCVD',tr('ui.42dea55cf89acf48'),'X-QSO',tr('ui.70e39859279e3de1')])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True);self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self.update_count);self.table.itemChanged.connect(self.clear_cell_error);layout.addWidget(self.table,1)
        row=QHBoxLayout()
        for text,checked in [(tr('ui.4cd31aa46c545a36'),True),(tr('ui.c90bb75fa377b91e'),False)]:
            b=QPushButton(text);b.clicked.connect(lambda _=False,c=checked:self.check_all(c));row.addWidget(b)
        row.addWidget(QLabel(tr('ui.aeda22feacdfbc09')));self.bulk_tx=QComboBox();self.bulk_tx.addItems(['','0','1']);row.addWidget(self.bulk_tx)
        b=QPushButton(tr('ui.0d8619aae051ae34'));b.clicked.connect(self.set_tx);row.addWidget(b);row.addStretch();self.count=QLabel();row.addWidget(self.count);layout.addLayout(row)
        note=QLabel(tr('ui.d1ed958654c5f99e'))
        note.setWordWrap(True);layout.addWidget(note)

    def _info_page(self):
        layout=self._page();layout.addWidget(QLabel(tr('ui.51f6b46b95409aa9')))
        scroll=QScrollArea();scroll.setWidgetResizable(True);content=QWidget();self.form=QFormLayout(content);scroll.setWidget(content);layout.addWidget(scroll)
        self.optional_fields = {'NAME','EMAIL','ADDRESS','ADDRESS-CITY','ADDRESS-STATE-PROVINCE',
                                'ADDRESS-POSTALCODE','ADDRESS-COUNTRY','GRID-LOCATOR','CLUB',
                                'CLAIMED-SCORE','CERTIFICATE','OFFTIME','SOAPBOX'}
        def field(key,label,options=None,multi=False):
            if options is not None:
                w=QComboBox();w.addItems(options)
            elif multi:
                w=QPlainTextEdit();w.setMaximumHeight(85)
            else:w=QLineEdit()
            self.fields[key]=w
            lbl=QLabel(label.replace('＊','<span style="color:#b3261e">＊</span>'))
            (self.optional_form if key in self.optional_fields else self.form).addRow(lbl,w)
            return w
        field('CONTEST',tr('ui.b6f311ee8bcbd96c'))
        field('CALLSIGN',tr('ui.61200f9d5b48a62c')).setText(store_call(self.store))
        field('CATEGORY-OPERATOR',tr('ui.f292ce979ff23399'),['SINGLE-OP','MULTI-OP','CHECKLOG'])
        field('CATEGORY-POWER',tr('ui.fedb1be715b0cfeb'),['LOW','HIGH','QRP'])
        field('CATEGORY-BAND',tr('ui.7b150d82389ce089'),BANDS)
        field('CATEGORY-ASSISTED',tr('ui.d2b985d458bdd565'),['NON-ASSISTED','ASSISTED'])
        field('CATEGORY-TRANSMITTER',tr('ui.d8fed9c10102ddac'),['','ONE','TWO','UNLIMITED','LIMITED'])
        field('CATEGORY-STATION',tr('ui.657b24bbfeaffde6'),['FIXED','PORTABLE','MOBILE','EXPEDITION','DISTRIBUTED','ROVER','HQ','SCHOOL'])
        field('CATEGORY-OVERLAY',tr('ui.0d8b1804df96049b'),['','CLASSIC','ROOKIE','YOUTH','TB-WIRES','YL'])
        field('BIRTHDATE',tr('ui.0a0a50a2f5079f64')).setPlaceholderText('YYYY-MM-DD')
        field('LICENSE-DATE',tr('ui.54f1eaec00867735')).setPlaceholderText('YYYY-MM-DD')
        field('CATEGORY-TIME',tr('ui.cd54bb1b4326fe70'),['','6-HOURS','8-HOURS','12-HOURS','24-HOURS'])
        field('LOCATION',tr('ui.2c765fd9b9817e22')).setPlaceholderText(tr('ui.2b40df8562db95b0'))
        field('MY-CQ-ZONE',tr('ui.d4229323f0c544cc')).setPlaceholderText(tr('ui.cca5f11342459130'))
        self.portable=QCheckBox(tr('ui.3d146589f881f29d'));self.form.addRow(self.portable)
        field('OPERATORS',tr('ui.3042839b75a1a0ea')).setPlaceholderText(tr('ui.d8b07c103967a41e'))
        field('NAME',tr('ui.84ab7ac0a0a0a803'))
        field('EMAIL',tr('ui.a3e9b5ef79590f41'))
        field('ADDRESS',tr('ui.f9cf5f82872c75ec'),multi=True)
        field('ADDRESS-CITY',tr('ui.6a0dfaebd022528c'))
        field('ADDRESS-STATE-PROVINCE',tr('ui.a10f3d9d55d1e713'))
        field('ADDRESS-POSTALCODE',tr('ui.3ca3adecd92c7e20'))
        field('ADDRESS-COUNTRY',tr('ui.1bcfedecfe8cf60d'))
        field('GRID-LOCATOR',tr('ui.44404a3a53ee0dc9'))
        self.club_choices=QComboBox();self.club_choices.addItem(tr('ui.814123f09aaa574f'),'')
        try:
            with resource_path('psrtty/data/club_db.csv').open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    self.club_choices.addItem(f'{row["number"]}　{row["name"]}',row['number'])
        except OSError:pass
        self.club_choices.currentIndexChanged.connect(lambda *_:self.set_value('CLUB',self.club_choices.currentData() or ''))
        self.optional_form.addRow(tr('ui.85ac2ab658b386d6'),self.club_choices)
        field('CLUB',tr('ui.cf578442c3e0af44'))
        field('CLAIMED-SCORE',tr('ui.1deda8d7cfd95ea0')).setPlaceholderText(tr('ui.0b8cd2fb8de52d79'))
        field('CERTIFICATE',tr('ui.04f42f3b2d645865'),['','YES','NO'])
        field('OFFTIME',tr('ui.9abd9270f4824185'),multi=True).setPlaceholderText('2026-09-26 1200 2026-09-26 1300')
        field('SOAPBOX',tr('ui.c1fba8b4c9a7ffd1'),multi=True)
        field('LAYOUT',tr('ui.ff11a4877372a320'),multi=True).setPlainText(DEFAULT_LAYOUT)
        self.layout_help=QLabel(tr('ui.1997041111e310e6'));self.layout_help.setWordWrap(True);self.form.addRow(self.layout_help)
        self.fields['CATEGORY-OPERATOR'].currentTextChanged.connect(self.category_changed)
        self.fields['CATEGORY-OVERLAY'].currentTextChanged.connect(self.category_changed)

    def _preview_page(self):
        layout=self._page();self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.warnings=QPlainTextEdit();self.warnings.setReadOnly(True);self.warnings.setMaximumHeight(110);layout.addWidget(self.warnings)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.preview.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont));layout.addWidget(self.preview,1)
        self.saved=QLabel();self.saved.setWordWrap(True);layout.addWidget(self.saved)
        self.open_folder=QPushButton(tr('ui.8604f0acbccd3b83'));self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path.parent))) if self.saved_path else None);layout.addWidget(self.open_folder)
        self.submit_site=QPushButton(tr('ui.5cb105bf953bd58a'))
        self.submit_site.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://cqwwrtty.com/logcheck/')))
        self.submit_site.setVisible(False);self.submit_site.setEnabled(False);layout.addWidget(self.submit_site)
        self.jarl_oath=QCheckBox(tr('ui.c769d5fc0574712b'))
        self.jarl_oath.setVisible(False);layout.addWidget(self.jarl_oath)

    def _optional_page(self):
        layout=self._page()
        layout.addWidget(QLabel(tr('ui.a6cc0aa6690f07b1')))
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();self.optional_form=QFormLayout(content)
        scroll.setWidget(content);layout.addWidget(scroll)

    def _cq_setup_page(self):
        layout=self._page()
        layout.addWidget(QLabel(tr('ui.4c35eab3a29a1638')))
        form=QFormLayout();layout.addLayout(form)
        self.cq_region=QComboBox()
        for key in ('日本','米国・カナダ','その他'):
            self.cq_region.addItem(tr(key), key)
        form.addRow(tr('ui.028842a0dedf0890'),self.cq_region)
        self.cq_year=QSpinBox();self.cq_year.setRange(2000,2100);self.cq_year.setValue(datetime.now().year)
        form.addRow(tr('ui.150df68b4eb7b80d'),self.cq_year)
        self.cq_start=QDateTimeEdit();self.cq_end=QDateTimeEdit()
        for edit in (self.cq_start,self.cq_end):
            edit.setDisplayFormat('yyyy-MM-dd HH:mm');edit.setCalendarPopup(True)
        form.addRow(tr('ui.ab780f856fae629a'),self.cq_start);form.addRow(tr('ui.88b55ac33812fca4'),self.cq_end)
        self.cq_call=QLineEdit(store_call(self.store));form.addRow(tr('ui.923ba6a6e0800d46'),self.cq_call)
        self.cq_year.valueChanged.connect(self._cq_default_period)
        self._cq_default_period()
        layout.addStretch()

    def _jarl_category_page(self):
        layout=self._page();form=QFormLayout();layout.addLayout(form)
        self.jarl_operator=QComboBox();self.jarl_operator.addItems(['SINGLE-OP','MULTI-OP','CHECKLOG'])
        form.addRow(tr('ui.e0668e1b64b7749b'),self.jarl_operator)
        self.jarl_power=QComboBox();self.jarl_power.addItems(['LOW','QRP','HIGH'])
        form.addRow(tr('ui.5e86e7a0378b87a5'),self.jarl_power)
        self.jarl_watts=QSpinBox();self.jarl_watts.setRange(1,100000);self.jarl_watts.setValue(100)
        form.addRow(tr('ui.0c640aff965df052'),self.jarl_watts)
        n=QLabel(tr('ui.1e688128b82ab40c'))
        n.setWordWrap(True);layout.addWidget(n);layout.addStretch()

    def _jarl_site_page(self):
        layout=self._page();form=QFormLayout();layout.addLayout(form)
        self.jarl_location=QComboBox();self.jarl_location.addItems([tr('ui.8157afb2e2f1a09a'), tr('ui.0f5759bd0ea09415')])
        form.addRow(tr('ui.028842a0dedf0890'),self.jarl_location)
        self.jarl_continent=QComboBox();self.jarl_continent.addItems(CONTINENTS)
        self.jarl_continent.setCurrentText('AS');form.addRow(tr('ui.ca252b14d86a6bc2'),self.jarl_continent)
        self.jarl_entity=QLineEdit();self.jarl_entity.setPlaceholderText(tr('ui.da83225fab86a7a4'))
        form.addRow(tr('ui.350566ba5d225ef3'),self.jarl_entity)
        self.jarl_portable=QCheckBox(tr('ui.55ecafc2c2b520f7'))
        form.addRow(self.jarl_portable)
        self.jarl_prefecture=QLineEdit();self.jarl_prefecture.setPlaceholderText(tr('ui.8f60ec98a8be453b'))
        form.addRow(tr('ui.84faa62cd34fc6a8'),self.jarl_prefecture)
        n=QLabel(tr('ui.1a06c0eb92f7aa04'))
        n.setWordWrap(True);layout.addWidget(n);layout.addStretch()
        self.jarl_location.currentIndexChanged.connect(lambda *_:self._jarl_site_changed())
        self._jarl_site_changed()

    def _jarl_site_changed(self):
        overseas=self.jarl_location.currentIndex()==1
        self.jarl_continent.setEnabled(overseas);self.jarl_entity.setEnabled(overseas)
        self.jarl_portable.setEnabled(not overseas);self.jarl_prefecture.setEnabled(not overseas)

    def _jarl_score_page(self):
        layout=self._page()
        note=QLabel(tr('ui.615a45bbfb061fdc'))
        note.setWordWrap(True);layout.addWidget(note)
        self.jarl_unknown=QTableWidget(0,4)
        self.jarl_unknown.setHorizontalHeaderLabels([tr('ui.22edd69c9f0e6e6c'),tr('ui.a9ac3b6bc6004b98'),tr('ui.c9519f73a638c0c2'),tr('ui.d258ddb4f7e797be')])
        self.jarl_unknown.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.jarl_unknown,1)
        row=QHBoxLayout();calculate_button=QPushButton(tr('ui.c89a9eefcf380ded'));calculate_button.clicked.connect(self._jarl_recalculate)
        row.addWidget(calculate_button);self.jarl_result=QLabel();row.addWidget(self.jarl_result);row.addStretch();layout.addLayout(row)
        self.jarl_details=QPlainTextEdit();self.jarl_details.setReadOnly(True);layout.addWidget(self.jarl_details,1)

    def _jarl_overrides(self):
        overrides={}
        for row in range(self.jarl_unknown.rowCount()):
            call=self.jarl_unknown.item(row,0).text()
            entity=self.jarl_unknown.item(row,1).text().strip()
            continent=self.jarl_unknown.cellWidget(row,2).currentText()
            multiplier=self.jarl_unknown.item(row,3).text().strip().upper()
            if entity:overrides[call]={'entity':entity,'continent':continent,'multiplier':multiplier}
        return overrides

    def _jarl_recalculate(self):
        entries,errors=self.selected_entries()
        if errors:self.error.setText('\n'.join(errors[:8]));return None
        try:result=calculate(entries,'AS' if self.jarl_location.currentIndex()==0 else self.jarl_continent.currentText(),self._jarl_overrides())
        except ValueError as exc:self.error.setText(tr(str(exc)));return None
        previous=self._jarl_overrides()
        candidates=sorted(set(result['unknown'])|set(previous))
        self.jarl_unknown.setRowCount(len(candidates))
        for row,call in enumerate(candidates):
            self.jarl_unknown.setItem(row,0,QTableWidgetItem(call))
            self.jarl_unknown.item(row,0).setFlags(Qt.ItemIsEnabled)
            self.jarl_unknown.setItem(row,1,QTableWidgetItem(previous.get(call,{}).get('entity','')))
            continent=QComboBox();continent.addItems(CONTINENTS)
            continent.setCurrentText(previous.get(call,{}).get('continent','AS'))
            self.jarl_unknown.setCellWidget(row,2,continent)
            self.jarl_unknown.setItem(row,3,QTableWidgetItem(previous.get(call,{}).get('multiplier','')))
        self.jarl_result.setText(tr('ui.6dc885d97b5d12ed').format(result['points'], result['multipliers'], result['total']))
        overrides=self._jarl_overrides()
        self.jarl_details.setPlainText('\n'.join(
            tr('ui.e39609798f06712d').format(call, band, point if point is not None else tr('ui.713c6d0f3a904065'), tr(mult))
            + (f' / {label}' if (label:=location_label(call,overrides)) else '')
            for call,band,point,mult in result['details']))
        self.error.setText(tr('ui.6268062a5a3f3549') if result['unknown'] else '')
        return result

    def _cq_default_period(self,*args):
        start,end=period('cqww',self.cq_year.value())
        for edit,when in ((self.cq_start,start),(self.cq_end,end)):
            edit.setDateTime(QDateTime.fromString(when.strftime('%Y-%m-%d %H:%M'),'yyyy-MM-dd HH:mm'))

    def _cq_prepare_period(self):
        call=self.cq_call.text().strip().upper()
        if not call:
            self.error.setText(tr('ui.8108a3301bb9cf0b'));return False
        start=datetime.strptime(self.cq_start.dateTime().toString('yyyy-MM-dd HH:mm'),'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        end=datetime.strptime(self.cq_end.dateTime().toString('yyyy-MM-dd HH:mm'),'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        if start>end:
            self.error.setText(tr('ui.ad841ef61b9f1dfc'));return False
        self.year.setValue(self.cq_year.value())
        self._display_datetime(self.start,start);self._display_datetime(self.end,end)
        self.call_filter.setText('')  # Include other own calls so they can be warned about, not silently dropped.
        self.band_filter.setCurrentText('ALL')
        self.band_filter.setEnabled(False)
        self.call_filter.setEnabled(False)
        self.filter_note.setText(tr('ui.d13bfc4f3b19114e'))
        self.set_value('CALLSIGN',call)
        self.set_value('LOCATION','DX' if self.cq_region.currentData()!='米国・カナダ' else '')
        if self.cq_region.currentData()=='米国・カナダ':self.fields['LOCATION'].setPlaceholderText(tr('ui.378f78b21fc56cd6'))
        self.reload() if not self.records else self.apply_filter()
        if not self.visible:
            self.error.setText(tr('ui.19f1b76621c2affc'));return False
        return True

    def _display_datetime(self,edit,utc):
        text=utc.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M')
        edit.setDateTime(QDateTime.fromString(text,'yyyy-MM-dd HH:mm'))

    def _read_datetime(self,edit):
        value=datetime.strptime(edit.dateTime().toString('yyyy-MM-dd HH:mm'),'%Y-%m-%d %H:%M').replace(tzinfo=self.display_zone).astimezone(timezone.utc)
        return value.replace(second=59,microsecond=999999) if edit is self.end else value

    def change_zone(self,text):
        if not hasattr(self,'start'):return
        start,end=self._read_datetime(self.start),self._read_datetime(self.end)
        self.capture();old=self.display_zone;self.display_zone=JST if text=='JST' else timezone.utc
        # Display fields are converted without changing their underlying instant.
        for state in self.states.values():
            try:
                stamp=datetime.strptime(state['values'][0],'%Y-%m-%d %H:%M').replace(tzinfo=old)
                state['values'][0]=stamp.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M')
            except ValueError:pass
        self._display_datetime(self.start,start);self._display_datetime(self.end,end);self.render_table()

    def update_period_label(self,*args):
        self.dates.setText(tr('ui.1f4be2af97967fef').format(self.year.value()))

    def set_period(self):
        if self.profile=='generic':return
        start,end=period(self.profile,self.year.value());self._display_datetime(self.start,start);self._display_datetime(self.end,end)
        if hasattr(self,'error'):self.error.setText(tr('ui.d8b18d24637ed01c'))

    def reload(self):
        if self.records and QMessageBox.question(self,tr('ui.9ecfa373790f0d0d'),tr('ui.67c079d723da57d1'))!=QMessageBox.Yes:return
        try:
            self.records=self.adif.load_recent(limit=None)
            self.read_errors=list(getattr(self.adif,'read_errors',[]))
        except Exception as exc:
            self.record_diagnostic(tr('ui.f464e448b249316d'),exc)
            self.error.setText(tr('ui.95cb3aee48d9c6e5'));return
        self.states={}
        for i,q in enumerate(self.records):
            when=q.when_utc.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M') if q.when_utc else ''
            self.states[i]={'checked':True,'xqso':False,'values':[when,q.station_callsign,q.call,q.freq_mhz,q.rst_sent,q.rst_rcvd,q.sent,q.rcvd,'']}
        self.has_table=False;self.apply_filter()

    def capture(self):
        if not self.has_table:return
        for row,index in enumerate(self.visible):
            self.states[index]={'checked':self.table.item(row,0).checkState()==Qt.Checked,
                'values':[self.table.item(row,col).text() for col in range(1,10)],'xqso':self.table.item(row,10).checkState()==Qt.Checked}

    def apply_filter(self):
        self.capture();start,end=self._read_datetime(self.start),self._read_datetime(self.end)
        if start>end:self.error.setText(tr('ui.ad841ef61b9f1dfc'));return
        call=self.call_filter.text().strip().upper();band=self.band_filter.currentText()
        self.visible=[]
        for i,q in enumerate(self.records):
            vals=self.states[i]['values']
            try:when=self.row_datetime(i,vals[0])
            except ValueError:when=None
            if self.profile=='cqww' and when is None:continue
            if when is not None and not start<=when<=end:continue
            if call and vals[1].strip() and vals[1].strip().upper()!=call:continue
            try:
                if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',vals[3]):raise ValueError('invalid MHz')
                edited_band=band_from_hz(int(Decimal(vals[3])*1000000)).upper()
            except (ValueError,InvalidOperation,OverflowError): edited_band=''
            if band!='ALL' and edited_band and edited_band!=band:continue
            self.visible.append(i)
        self.render_table()
        if self.read_errors:self.record_diagnostic(tr('ui.4f99e53b59f1e0e2'),ValueError(' / '.join(map(str,self.read_errors))))
        self.error.setText(tr('ui.5f1d13ff392c71f0') if self.read_errors else '')
        self.applied_filter=(start,end,call,band)

    def render_table(self):
        self.table.blockSignals(True);self.table.setRowCount(len(self.visible))
        self.table.setHorizontalHeaderItem(1,QTableWidgetItem(tr('ui.a4acac41725e4132')+self.zone.currentText()+'）'))
        for row,index in enumerate(self.visible):
            state=self.states[index]
            for col,key in [(0,'checked'),(10,'xqso')]:
                item=QTableWidgetItem();item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if state[key] else Qt.Unchecked);self.table.setItem(row,col,item)
            for col,value in enumerate(state['values'],1):self.table.setItem(row,col,QTableWidgetItem(value))
            item=QTableWidgetItem('');item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable);self.table.setItem(row,11,item)
        self.table.blockSignals(False);self.has_table=True;self.update_count()

    def update_count(self,*args):
        selected=sum(self.table.item(r,0).checkState()==Qt.Checked for r in range(self.table.rowCount()) if self.table.item(r,0))
        self.count.setText(tr('ui.4d4abe28132d1830').format(tr('ui.f2d7ce134ccf4f77'), selected, len(self.visible), len(self.records), tr('ui.7c00255577088ec9')))

    def check_all(self,checked):
        for r in range(self.table.rowCount()):self.table.item(r,0).setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def set_tx(self):
        for row in {item.row() for item in self.table.selectedItems()}:self.table.item(row,9).setText(self.bulk_tx.currentText())

    def value(self,key):
        w=self.fields[key]
        return w.currentText() if isinstance(w,QComboBox) else w.toPlainText() if isinstance(w,QPlainTextEdit) else w.text()

    def set_value(self,key,value):
        w=self.fields[key]
        if isinstance(w,QComboBox):
            if w.findText(value)>=0:w.setCurrentText(value)
        elif isinstance(w,QPlainTextEdit):w.setPlainText(value)
        else:w.setText(value)

    def info(self):
        values={k:self.value(k).strip() for k in self.fields};values['JARL-PORTABLE']='YES' if self.portable.isChecked() else 'NO'
        if self.profile=='jarl':values['JARL-MAX-POWER']=str(self.jarl_watts.value())
        if self.profile=='cqww':values['CQ-REGION']='USVE' if self.cq_region.currentIndex()==1 else 'JA' if self.cq_region.currentIndex()==0 else 'OTHER'
        return values

    def category_changed(self,*args):
        if not hasattr(self,'portable'):return
        op=self.value('CATEGORY-OPERATOR');multi=op=='MULTI-OP'
        if self.profile=='jarl':self.set_value('CATEGORY-TRANSMITTER','UNLIMITED' if multi else 'ONE')
        for key in ('BIRTHDATE','LICENSE-DATE'):
            show=self.profile=='cqww' and self.value('CATEGORY-OVERLAY')==('YOUTH' if key=='BIRTHDATE' else 'ROOKIE')
            self.form.setRowVisible(self.fields[key],show)

    def configure_profile(self,key):
        if self.loaded_profile==key:return
        if self.loaded_profile:self.profile_forms[self.loaded_profile]=self.info()
        self.profile=key
        for k,options in [('CATEGORY-BAND',['ALL'] if key=='jarl' else HF_BANDS if key=='cqww' else BANDS),('CATEGORY-OVERLAY',['','YOUTH'] if key=='jarl' else ['','CLASSIC','ROOKIE','YOUTH'] if key=='cqww' else ['','CLASSIC','ROOKIE','YOUTH','TB-WIRES','YL']),('CATEGORY-TRANSMITTER',['','ONE','TWO','UNLIMITED'] if key!='generic' else ['','ONE','TWO','UNLIMITED','LIMITED'])]:
            w=self.fields[k];w.blockSignals(True);w.clear();w.addItems(options);w.blockSignals(False)
        for k in self.fields:
            if isinstance(self.fields[k],QComboBox):self.fields[k].setCurrentIndex(0)
            else:self.set_value(k,'')
        self.set_value('CALLSIGN',store_call(self.store));self.set_value('CONTEST',CONTESTS.get(key,''));self.set_value('LAYOUT',DEFAULT_LAYOUT)
        self.set_value('CATEGORY-TRANSMITTER','ONE');self.set_value('LOCATION','DX' if key=='cqww' else '')
        cached=self.profile_forms.get(key,self.store.data.get('cabrillo',{}).get(key,{}))
        for k,value in cached.items():
            if k in self.fields:self.set_value(k,value)
        self.portable.setChecked(cached.get('JARL-PORTABLE')=='YES')
        self.fields['CONTEST'].setReadOnly(key!='generic')
        if key!='generic':self.set_value('CONTEST',CONTESTS[key])
        self.form.setRowVisible(self.fields['LAYOUT'],key=='generic');self.layout_help.setVisible(key=='generic')
        self.form.setRowVisible(self.fields['CATEGORY-TIME'],key=='generic')
        self.form.setRowVisible(self.fields['MY-CQ-ZONE'],key=='cqww')
        if key!='generic':self.set_value('CATEGORY-TIME','')
        self.portable.setVisible(key=='jarl');self.dates.setEnabled(key!='generic');self.period_note.setVisible(key!='generic')
        if key!='cqww':
            self.band_filter.setEnabled(True);self.call_filter.setEnabled(True)
        self.loaded_profile=key;self.category_changed()
        if key!='generic':self.set_period()

    def record_diagnostic(self,context,exc):
        try:
            parent=self.parent()
            folder=Path(parent.paths['var']) if parent is not None and hasattr(parent,'paths') else app_root()/'var'
            folder.mkdir(parents=True,exist_ok=True)
            path=folder/f'cabrillo_{datetime.now():%Y%m%d}.log'
            with path.open('a',encoding='utf-8') as stream:
                stream.write(f'{datetime.now().isoformat()} | {context}\n')
                stream.write(''.join(traceback.format_exception(type(exc),exc,exc.__traceback__))+'\n')
        except Exception:
            pass  # A diagnostic write failure must not interrupt input correction.

    def row_datetime(self,index,text):
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}',text):
            raise ValueError(tr('ui.6e5c40e9547cb058'))
        when=datetime.strptime(text,'%Y-%m-%d %H:%M').replace(tzinfo=self.display_zone).astimezone(timezone.utc)
        original=self.records[index].when_utc
        if original is not None and original.astimezone(self.display_zone).strftime('%Y-%m-%d %H:%M')==text:
            return original.astimezone(timezone.utc)
        return when

    def clear_cell_error(self,item):
        if not 1<=item.column()<=9:return
        self.table.blockSignals(True)
        item.setBackground(QBrush());item.setToolTip('')
        status=self.table.item(item.row(),11)
        if status:status.setText('')
        self.table.blockSignals(False)

    def selected_entries(self):
        self.capture();entries=[];errors=[]
        self.table.blockSignals(True)
        try:
            for row,index in enumerate(self.visible):
                state=self.states[index]
                for col in range(1,10):
                    self.table.item(row,col).setBackground(QBrush());self.table.item(row,col).setToolTip('')
                self.table.item(row,11).setText('')
                if not state['checked']:continue
                vals=[v.strip() for v in state['values']];row_errors=[]
                def invalid(col,message):
                    row_errors.append(message)
                    item=self.table.item(row,col);item.setBackground(QColor('#ffe0e0'));item.setToolTip(message)
                when=None;freq=None
                if not vals[0]:invalid(1,tr('ui.8ef6081b619428c3'))
                else:
                    try:when=self.row_datetime(index,vals[0])
                    except ValueError as exc:
                        self.record_diagnostic(tr('ui.eab33514def2846f').format(row+1),exc)
                        invalid(1,tr('ui.397529171f1c0baa'))
                if when is not None and not self._read_datetime(self.start)<=when<=self._read_datetime(self.end):
                    invalid(1,tr('ui.4c289914e26c5676'))
                if not vals[3]:invalid(4,tr('ui.3f28f5d7185110d6'))
                else:
                    try:
                        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',vals[3]):raise InvalidOperation('MHz must use decimal digits')
                        freq=Decimal(vals[3])*1000000
                        if not freq.is_finite() or freq<=0 or freq!=freq.to_integral_value():
                            invalid(4,tr('ui.29a18512ebd30d32'))
                    except (InvalidOperation,ValueError) as exc:
                        self.record_diagnostic(tr('ui.06e567f5b36c501b').format(row+1),exc)
                        invalid(4,tr('ui.3d7dc2d50f5784e7'))
                if not row_errors:
                    q=replace(self.records[index],when_utc=when,station_callsign=vals[1].upper(),call=vals[2].upper(),freq_hz=int(freq),rst_sent=vals[4],rst_rcvd=vals[5],sent=vals[6],rcvd=vals[7])
                    if self.band_filter.currentText()!='ALL' and q.band.upper()!=self.band_filter.currentText():
                        invalid(4,tr('ui.d763b3433ff6c05a'))
                    if self.call_filter.text().strip() and q.station_callsign and q.station_callsign!=self.call_filter.text().strip().upper():
                        invalid(2,tr('ui.d788c2bbb3530b5f'))
                    if not row_errors:entries.append((q,{'txid':vals[8],'xqso':state['xqso']}))
                if row_errors:
                    message=tr('ui.d90e1b9dee81c557').format(row+1, vals[2])+' / '.join(row_errors)
                    errors.append(message);self.table.item(row,11).setText(' / '.join(row_errors))
        finally:self.table.blockSignals(False)
        return entries,errors

    def _set_page(self,index):
        titles={0:tr('ui.3e9ae7318b1960a7'),5:tr('ui.8b06584eb98ccd95'),1:tr('ui.3903ee0e478c869c'),
                6:tr('ui.c78189f2d97feed4'),7:tr('ui.b36e90a7f1730040'),8:tr('ui.e36c3cc8abd791cf'),
                3:tr('ui.2290819dad9f8a4e'),2:tr('ui.7c9dc1cc37bc4f4c'),4:tr('ui.6b10bc37f4f254a2')}
        self.pages.setCurrentIndex(index);self.heading.setText(titles[index])
        self.back.setEnabled(index!=0);self.next.setText(tr('ui.74a140953d6eb7a8') if index==4 else tr('ui.9eccdca31ee358be'));self.error.clear()
        self.cq_warning.setVisible(self.profile=='cqww' and bool(self.cq_warning.text()) and index in (3,2,4))
        self.submit_site.setVisible(self.profile=='cqww' and index==4)
        self.jarl_oath.setVisible(self.profile=='jarl' and index==4)

    def go_back(self):
        index=self.pages.currentIndex()
        if index:self._set_page({5:0,1:5 if self.profile=='cqww' else 0,
                                 6:1,7:6,8:7,3:8 if self.profile=='jarl' else 1,
                                 2:3,4:2}[index])

    def go_next(self):
        index=self.pages.currentIndex();self.error.clear()
        if index==0:
            self.configure_profile(self.formats.checkedButton().property('profile'))
            if self.profile=='cqww':self._set_page(5)
            else:
                self._set_page(1)
                if not self.records:self.reload()
                else:self.apply_filter()
        elif index==5:
            if self._cq_prepare_period():self._set_page(1)
        elif index==1:
            now_filter=(self._read_datetime(self.start),self._read_datetime(self.end),self.call_filter.text().strip().upper(),self.band_filter.currentText())
            if now_filter!=getattr(self,'applied_filter',None):
                self.error.setText(tr('ui.2b3b8bbab3d83a3b'));return
            entries,errors=self.selected_entries()
            if self.read_errors:errors=[tr('ui.a43750c649d9c3f2')]+errors
            if not entries and not errors:errors=[tr('ui.c5cc6c17ab4c4bd0')]
            if errors:self.error.setText('\n'.join(errors[:8]));return
            if self.profile=='jarl':
                self._set_page(6);return
            if self.profile=='cqww':
                zones={q.sent.split()[0] for q,_ in entries if q.sent.strip() and q.sent.split()[0].isdigit()}
                if len(zones)==1:self.set_value('MY-CQ-ZONE',next(iter(zones)))
                mixed=sorted({q.station_callsign or tr('ui.162a3bc0643b5614') for q,_ in entries if q.station_callsign.upper()!=self.value('CALLSIGN').upper()})
                self.cq_warning.setText(tr('ui.a199b992ccfccf48')+', '.join(mixed)+tr('ui.836d71f3ff1660e1') if mixed else '')
            self._set_page(3)
        elif index==6:
            power=self.jarl_power.currentText();watts=self.jarl_watts.value()
            if (power=='QRP' and watts>5 or power=='LOW' and watts>100 or
                power=='HIGH' and watts<=100 or self.jarl_operator.currentText()=='MULTI-OP' and power=='QRP'):
                self.error.setText(tr('ui.a56b122139d87d6a'));return
            self.set_value('CATEGORY-OPERATOR',self.jarl_operator.currentText())
            self.set_value('CATEGORY-POWER',power)
            self.set_value('CATEGORY-BAND','ALL')
            self._set_page(7)
        elif index==7:
            if self.jarl_location.currentIndex()==1 and not re.fullmatch('[A-Za-z0-9/]{1,12}',self.jarl_entity.text().strip()):
                self.error.setText(tr('ui.d07e3f86168c0348'));return
            if self.jarl_location.currentIndex()==0 and self.jarl_portable.isChecked() and not self.jarl_prefecture.text().strip():
                self.error.setText(tr('ui.8aa778b648b62696'));return
            self.portable.setChecked(self.jarl_portable.isChecked() and self.jarl_location.currentIndex()==0)
            self.set_value('LOCATION',self.jarl_prefecture.text().strip().upper() if self.portable.isChecked() else '')
            self._jarl_recalculate();self._set_page(8)
        elif index==8:
            result=self._jarl_recalculate()
            if not result or result['unknown']:return
            self.set_value('CLAIMED-SCORE',str(result['total']))
            self.jarl_score_result=result
            self._set_page(3)
        elif index==3:
            entries,errors=self.selected_entries();_,validation,_=build_cabrillo(self.profile,self.info(),entries);errors+=validation
            if errors:self.error.setText('\n'.join(errors[:8]));return
            self._set_page(2)
        elif index==2:
            if self.profile=='jarl':
                result=self._jarl_recalculate()
                if not result or result['unknown'] or result['total']!=getattr(self,'jarl_score_result',{}).get('total'):
                    self.error.setText(tr('ui.11925d0d19422481'));return
                self.set_value('CLAIMED-SCORE',str(result['total']))
            entries,errors=self.selected_entries();body,validation,warnings=build_cabrillo(self.profile,self.info(),entries);errors+=validation
            if errors:
                self.error.setText('\n'.join(errors[:8])+ (tr('ui.abc3a5a742edd511').format(len(errors) - 8, tr('ui.7c00255577088ec9')) if len(errors)>8 else ''));return
            self.body=body;self.preview.setPlainText(body);self.warnings.setPlainText('\n'.join(warnings) if warnings else tr('ui.00a959be68c82745'))
            self.summary.setText(tr('ui.6c6fb8f186ee50c7').format(tr(PROFILES[self.profile]), self.value('CALLSIGN'), self.value('CATEGORY-OPERATOR'), self.value('CATEGORY-POWER'), self.value('CATEGORY-BAND'), len(entries), sum((bool(e[1]['xqso']) for e in entries)), self._read_datetime(self.start), tr('ui.0ce5743f6e0d63e8'), self._read_datetime(self.end)))
            self.saved.clear();self.saved_path=None;self.open_folder.setEnabled(False);self.submit_site.setEnabled(False);self._set_page(4)
        else:self.save_file()

    def save_file(self):
        self.error.clear()
        if self.profile=='jarl' and not self.jarl_oath.isChecked():
            self.error.setText(tr('ui.bab1386cc9a6b8eb'));return
        name=self.value('CALLSIGN').replace('/','_')+'_'+self.value('CONTEST')+'.log'
        path,_=QFileDialog.getSaveFileName(self,tr('ui.3ea79fb0e752c2d4'),name,tr('ui.7a8c0d4dd4bce0fb'))
        if not path:return
        try:
            protected=[q.source_path for q in self.records if q.source_path]
            save_cabrillo(Path(path),self.body,protected)
        except Exception as exc:
            self.record_diagnostic(tr('ui.e764746723f2b822'),exc)
            self.error.setText(tr(str(exc)) if isinstance(exc,ValueError) else tr('ui.a9eaee8124b19bfe'));return
        self.saved_path=Path(path);self.saved.setText(f"{tr('ui.4b8bb41f0172e9c0')}{path}"+ (tr('ui.0e9d13ab680d1082') if self.profile=='cqww' else ''));self.open_folder.setEnabled(True)
        self.submit_site.setEnabled(self.profile=='cqww')
        old=deepcopy(self.store.data.get('cabrillo',{}));self.store.data.setdefault('cabrillo',{})[self.profile]=self.info()
        try:self.store.save()
        except Exception as exc:
            self.store.data['cabrillo']=old;self.record_diagnostic(tr('ui.bd18e99c8a6349a5'),exc)
            self.error.setText(tr('ui.9b976bfdaabb909b'))


def store_call(store):
    return str(store.data.get('station_callsign','')).strip().upper()
