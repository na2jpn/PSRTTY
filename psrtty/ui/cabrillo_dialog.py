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
from ..jarl_score import calculate, CONTINENTS
import csv
from ..adif import band_from_hz
from ..cabrillo import PROFILES,CONTESTS,HF_BANDS,BANDS,DEFAULT_LAYOUT,JST,period,build_cabrillo,save_cabrillo


class CabrilloDialog(QDialog):
    def __init__(self, adif, store, parent=None):
        super().__init__(parent)
        self.adif=adif;self.store=store;self.profile='generic';self.loaded_profile=None
        self.records=[];self.states={};self.visible=[];self.read_errors=[];self.body='';self.saved_path=None
        self.display_zone=JST;self.fields={};self.profile_forms={};self.has_table=False
        self.setWindowTitle('Cabrilloファイル出力');self.resize(1080,720)
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
        row=QHBoxLayout();self.back=QPushButton('戻る');self.back.clicked.connect(self.go_back);row.addWidget(self.back)
        row.addStretch();self.next=QPushButton('次へ');self.next.clicked.connect(self.go_next);row.addWidget(self.next)
        close=QPushButton('閉じる');close.clicked.connect(self.reject);row.addWidget(close);root.addLayout(row)
        self._set_page(0)

    def _page(self):
        page=QWidget();layout=QVBoxLayout(page);self.pages.addWidget(page);return layout

    def _format_page(self):
        layout=self._page();layout.addWidget(QLabel('出力する形式を選んでください。'))
        self.formats=QButtonGroup(self)
        for i,(key,title) in enumerate(PROFILES.items()):
            button=QRadioButton(title);button.setProperty('profile',key);self.formats.addButton(button,i);layout.addWidget(button)
        self.formats.button(0).setChecked(True)
        note=QLabel('専用形式は大会の交換番号と参加部門に対応します。\n汎用形式は大会識別名・QSOの並びを指定できます。提出先の形式と照合してください。\n\n出力用の編集は元のADIFに反映しません。ファイルの作成までを行います。')
        note.setWordWrap(True);layout.addWidget(note);layout.addStretch()

    def _qso_page(self):
        layout=self._page();row=QHBoxLayout()
        row.addWidget(QLabel('開催年'));self.year=QSpinBox();self.year.setRange(2000,2100);self.year.setValue(datetime.now().year);row.addWidget(self.year)
        self.dates=QPushButton('大会期間を入力');self.dates.clicked.connect(self.set_period);row.addWidget(self.dates)
        row.addWidget(QLabel('日時表示'));self.zone=QComboBox();self.zone.addItems(['JST','UTC']);self.zone.currentTextChanged.connect(self.change_zone);row.addWidget(self.zone);row.addStretch();layout.addLayout(row)
        self.year.valueChanged.connect(self.update_period_label);self.update_period_label()
        self.period_note=QLabel('大会期間は現在の開催ルールから自動計算しています。公式日程を確認し、異なる場合は開始・終了を修正してください。')
        self.period_note.setWordWrap(True);self.period_note.setStyleSheet('color: #1565c0;');layout.addWidget(self.period_note)
        row=QHBoxLayout();self.start=QDateTimeEdit();self.end=QDateTimeEdit()
        for edit in (self.start,self.end):
            edit.setDisplayFormat('yyyy-MM-dd HH:mm');edit.setCalendarPopup(True)
            edit.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        now=datetime.now(self.display_zone)
        self._display_datetime(self.start,now.replace(day=1,hour=0,minute=0,second=0,microsecond=0))
        self._display_datetime(self.end,now)
        self.start_label=QLabel('開始');self.end_label=QLabel('終了（含む）')
        row.addWidget(self.start_label);row.addWidget(self.start);row.addSpacing(12)
        row.addWidget(self.end_label);row.addWidget(self.end);row.addStretch();layout.addLayout(row)
        row=QHBoxLayout();row.addWidget(QLabel('自局CALL抽出'))
        self.call_filter=QLineEdit(store_call(self.store));self.call_filter.setPlaceholderText('空欄＝全自局');row.addWidget(self.call_filter)
        self.band_filter=QComboBox();self.band_filter.addItems(['ALL','80M','40M','20M','15M','10M','160M','6M','2M','70CM','23CM']);row.addWidget(self.band_filter)
        apply=QPushButton('抽出');apply.clicked.connect(self.apply_filter);row.addWidget(apply)
        reload=QPushButton('ADIF再読込');reload.clicked.connect(self.reload);row.addWidget(reload);layout.addLayout(row)
        self.filter_note=QLabel('日時のないQSO・自局CALL空欄も確認用に表示します。修正は出力用コピーだけに適用します。')
        self.filter_note.setWordWrap(True);layout.addWidget(self.filter_note)
        self.table=QTableWidget(0,12)
        self.table.setHorizontalHeaderLabels(['出力','日時','自局CALL','相手CALL','MHz','RST-S','RST-R','SENT','RCVD','TX番号','X-QSO','状態'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True);self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self.update_count);self.table.itemChanged.connect(self.clear_cell_error);layout.addWidget(self.table,1)
        row=QHBoxLayout()
        for text,checked in [('全選択',True),('全解除',False)]:
            b=QPushButton(text);b.clicked.connect(lambda _=False,c=checked:self.check_all(c));row.addWidget(b)
        row.addWidget(QLabel('選択行のTX番号'));self.bulk_tx=QComboBox();self.bulk_tx.addItems(['','0','1']);row.addWidget(self.bulk_tx)
        b=QPushButton('設定');b.clicked.connect(self.set_tx);row.addWidget(b);row.addStretch();self.count=QLabel();row.addWidget(self.count);layout.addLayout(row)
        note=QLabel('TX番号：MULTI-ONE/TWOで使用。X-QSO：採点対象外として出力。SENT/RCVD例：CQ WW「25」「05 MA」、JARL「01」。')
        note.setWordWrap(True);layout.addWidget(note)

    def _info_page(self):
        layout=self._page();layout.addWidget(QLabel('赤い＊は必須。条件付き項目は該当時に入力。文字は半角英数字（氏名・住所はローマ字）です。'))
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
        field('CONTEST','大会識別名 CONTEST ＊')
        field('CALLSIGN','提出する自局CALL ＊').setText(store_call(self.store))
        field('CATEGORY-OPERATOR','参加部門 ＊',['SINGLE-OP','MULTI-OP','CHECKLOG'])
        field('CATEGORY-POWER','出力区分 ＊',['LOW','HIGH','QRP'])
        field('CATEGORY-BAND','参加バンド ＊',BANDS)
        field('CATEGORY-ASSISTED','アシステッド区分',['NON-ASSISTED','ASSISTED'])
        field('CATEGORY-TRANSMITTER','送信機区分（マルチオペ必須）',['','ONE','TWO','UNLIMITED','LIMITED'])
        field('CATEGORY-STATION','運用形態',['FIXED','PORTABLE','MOBILE','EXPEDITION','DISTRIBUTED','ROVER','HQ','SCHOOL'])
        field('CATEGORY-OVERLAY','オーバーレイ',['','CLASSIC','ROOKIE','YOUTH','TB-WIRES','YL'])
        field('BIRTHDATE','YOUTH：生年月日（CQ WW必須）').setPlaceholderText('YYYY-MM-DD')
        field('LICENSE-DATE','ROOKIE：初免許年月日（CQ WW必須）').setPlaceholderText('YYYY-MM-DD')
        field('CATEGORY-TIME','運用時間部門（汎用のみ）',['','6-HOURS','8-HOURS','12-HOURS','24-HOURS'])
        field('LOCATION','運用地 LOCATION（CQ WW必須）').setPlaceholderText('CQ WW：DX または州/地域 ／ JARL移動：都道府県をローマ字')
        field('MY-CQ-ZONE','自局CQゾーン（CQ WW）').setPlaceholderText('SENTから読み取った値を確認してください。')
        self.portable=QCheckBox('JARL：常置場所と異なる場所で運用（LOCATION必須）');self.form.addRow(self.portable)
        field('OPERATORS','運用者一覧（マルチオペ必須）').setPlaceholderText('JH1HST JQ7FIU ／ JARLは無資格者のローマ字氏名も可')
        field('NAME','氏名 NAME（推奨）')
        field('EMAIL','連絡先 EMAIL（推奨）')
        field('ADDRESS','住所 ADDRESS（推奨・45文字×6行まで）',multi=True)
        field('ADDRESS-CITY','市区町村（任意）')
        field('ADDRESS-STATE-PROVINCE','都道府県・州（任意）')
        field('ADDRESS-POSTALCODE','郵便番号（任意）')
        field('ADDRESS-COUNTRY','国名（CQ WWの米国外郵送先は必要）')
        field('GRID-LOCATOR','グリッド（任意）')
        self.club_choices=QComboBox();self.club_choices.addItem('登録クラブを選択しない','')
        try:
            with resource_path('psrtty/data/club_db.csv').open(encoding='utf-8-sig',newline='') as stream:
                for row in csv.DictReader(stream):
                    self.club_choices.addItem(f'{row["number"]}　{row["name"]}',row['number'])
        except OSError:pass
        self.club_choices.currentIndexChanged.connect(lambda *_:self.set_value('CLUB',self.club_choices.currentData() or ''))
        self.optional_form.addRow('JARL登録クラブ（選択時は登録番号）',self.club_choices)
        field('CLUB','CLUB 登録番号（必要時）')
        field('CLAIMED-SCORE','申告得点（任意・整数）').setPlaceholderText('自動計算はしません。空欄なら省略。')
        field('CERTIFICATE','紙の賞状希望（任意・主催者の対応による）',['','YES','NO'])
        field('OFFTIME','休止時間（任意・UTC）',multi=True).setPlaceholderText('2026-09-26 1200 2026-09-26 1300')
        field('SOAPBOX','コメント（任意）',multi=True)
        field('LAYOUT','汎用QSOの並び ＊',multi=True).setPlainText(DEFAULT_LAYOUT)
        self.layout_help=QLabel('置換項目：{FREQ} {MODE} {DATE} {TIME} {MYCALL} {RSTS} {SENT} {HISCALL} {RSTR} {RCVD} {TXID}\nQSO:は自動で付きます。TXID以外は必須。指定した並びで出力します。');self.layout_help.setWordWrap(True);self.form.addRow(self.layout_help)
        self.fields['CATEGORY-OPERATOR'].currentTextChanged.connect(self.category_changed)
        self.fields['CATEGORY-OVERLAY'].currentTextChanged.connect(self.category_changed)

    def _preview_page(self):
        layout=self._page();self.summary=QLabel();self.summary.setWordWrap(True);layout.addWidget(self.summary)
        self.warnings=QPlainTextEdit();self.warnings.setReadOnly(True);self.warnings.setMaximumHeight(110);layout.addWidget(self.warnings)
        self.preview=QPlainTextEdit();self.preview.setReadOnly(True);self.preview.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.preview.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont));layout.addWidget(self.preview,1)
        self.saved=QLabel();self.saved.setWordWrap(True);layout.addWidget(self.saved)
        self.open_folder=QPushButton('保存先フォルダーを開く');self.open_folder.setEnabled(False)
        self.open_folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.saved_path.parent))) if self.saved_path else None);layout.addWidget(self.open_folder)
        self.submit_site=QPushButton('CQ WW RTTY公式提出ページを開く')
        self.submit_site.clicked.connect(lambda:QDesktopServices.openUrl(QUrl('https://cqwwrtty.com/logcheck/')))
        self.submit_site.setVisible(False);self.submit_site.setEnabled(False);layout.addWidget(self.submit_site)
        self.jarl_oath=QCheckBox('JARL World Wide RTTYの規約と提出内容を確認し、提出に伴う宣誓に同意します')
        self.jarl_oath.setVisible(False);layout.addWidget(self.jarl_oath)

    def _optional_page(self):
        layout=self._page()
        layout.addWidget(QLabel('任意の提出情報を入力してください。CQ WW用は半角英数字・記号のみ使用できます。'))
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();self.optional_form=QFormLayout(content)
        scroll.setWidget(content);layout.addWidget(scroll)

    def _cq_setup_page(self):
        layout=self._page()
        layout.addWidget(QLabel('CQ WW RTTYの運用地・期間・提出する自局コールを指定してください。'))
        form=QFormLayout();layout.addLayout(form)
        self.cq_region=QComboBox();self.cq_region.addItems(['日本','米国・カナダ','その他'])
        form.addRow('運用地',self.cq_region)
        self.cq_year=QSpinBox();self.cq_year.setRange(2000,2100);self.cq_year.setValue(datetime.now().year)
        form.addRow('開催年',self.cq_year)
        self.cq_start=QDateTimeEdit();self.cq_end=QDateTimeEdit()
        for edit in (self.cq_start,self.cq_end):
            edit.setDisplayFormat('yyyy-MM-dd HH:mm');edit.setCalendarPopup(True)
        form.addRow('開始（UTC）',self.cq_start);form.addRow('終了（UTC、指定分を含む）',self.cq_end)
        self.cq_call=QLineEdit(store_call(self.store));form.addRow('提出する自局CALL',self.cq_call)
        self.cq_year.valueChanged.connect(self._cq_default_period)
        self._cq_default_period()
        layout.addStretch()

    def _jarl_category_page(self):
        layout=self._page();form=QFormLayout();layout.addLayout(form)
        self.jarl_operator=QComboBox();self.jarl_operator.addItems(['SINGLE-OP','MULTI-OP','CHECKLOG'])
        form.addRow('参加部門',self.jarl_operator)
        self.jarl_power=QComboBox();self.jarl_power.addItems(['LOW','QRP','HIGH'])
        form.addRow('出力部門',self.jarl_power)
        self.jarl_watts=QSpinBox();self.jarl_watts.setRange(1,100000);self.jarl_watts.setValue(100)
        form.addRow('最大出力（W）',self.jarl_watts)
        n=QLabel('シングルオペ：運用とログ記録を一人で行い、同時送信は1波まで。'
                 'マルチオペ：最大5バンドで同時運用でき、各バンド1波まで。\n'
                 'QRP：5W以下／ローパワー：100W以下／ハイパワー：100Wを超える出力（免許の範囲内）。')
        n.setWordWrap(True);layout.addWidget(n);layout.addStretch()

    def _jarl_site_page(self):
        layout=self._page();form=QFormLayout();layout.addLayout(form)
        self.jarl_location=QComboBox();self.jarl_location.addItems(['日本国内','海外'])
        form.addRow('運用地',self.jarl_location)
        self.jarl_continent=QComboBox();self.jarl_continent.addItems(CONTINENTS)
        self.jarl_continent.setCurrentText('AS');form.addRow('海外運用の大陸',self.jarl_continent)
        self.jarl_entity=QLineEdit();self.jarl_entity.setPlaceholderText('例：HL、K、VK')
        form.addRow('海外運用のエンティティ',self.jarl_entity)
        self.jarl_portable=QCheckBox('常置場所と異なる場所で運用')
        form.addRow(self.jarl_portable)
        self.jarl_prefecture=QLineEdit();self.jarl_prefecture.setPlaceholderText('例：SAITAMA')
        form.addRow('移動運用地の都道府県（ローマ字）',self.jarl_prefecture)
        n=QLabel('日本国内運用はアジア州として計算します。小笠原・南鳥島のJD1は交信相手の実際の運用地を確認して指定します。')
        n.setWordWrap(True);layout.addWidget(n);layout.addStretch()
        self.jarl_location.currentIndexChanged.connect(lambda *_:self._jarl_site_changed())
        self._jarl_site_changed()

    def _jarl_site_changed(self):
        overseas=self.jarl_location.currentIndex()==1
        self.jarl_continent.setEnabled(overseas);self.jarl_entity.setEnabled(overseas)
        self.jarl_portable.setEnabled(not overseas);self.jarl_prefecture.setEnabled(not overseas)

    def _jarl_score_page(self):
        layout=self._page()
        note=QLabel('大陸・エンティティを特定できない交信は、実際の運用地を確認して手動指定してください。'
                    'マルチは通常エンティティ名、JA/W/VE/VKの本土ならコールエリア（例：JA3、VK0）を入力します。'
                    'JD1は小笠原 JD/o・AS、南鳥島 JD/m・OCです。/MMは2点でマルチなしです。')
        note.setWordWrap(True);layout.addWidget(note)
        self.jarl_unknown=QTableWidget(0,4)
        self.jarl_unknown.setHorizontalHeaderLabels(['相手CALL','エンティティ','大陸','マルチ'])
        self.jarl_unknown.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.jarl_unknown,1)
        row=QHBoxLayout();calculate_button=QPushButton('得点を計算');calculate_button.clicked.connect(self._jarl_recalculate)
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
        except ValueError as exc:self.error.setText(str(exc));return None
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
        self.jarl_result.setText(f"得点 {result['points']} × マルチ {result['multipliers']} ＝ {result['total']} 点")
        self.jarl_details.setPlainText('\n'.join(f'{call} {band}：{point if point is not None else "未判定"}点 / {mult}'
                         for call,band,point,mult in result['details']))
        self.error.setText('未判定局の運用地を入力して再計算してください。' if result['unknown'] else '')
        return result

    def _cq_default_period(self,*args):
        start,end=period('cqww',self.cq_year.value())
        for edit,when in ((self.cq_start,start),(self.cq_end,end)):
            edit.setDateTime(QDateTime.fromString(when.strftime('%Y-%m-%d %H:%M'),'yyyy-MM-dd HH:mm'))

    def _cq_prepare_period(self):
        call=self.cq_call.text().strip().upper()
        if not call:
            self.error.setText('提出する自局CALLを入力してください。');return False
        start=datetime.strptime(self.cq_start.dateTime().toString('yyyy-MM-dd HH:mm'),'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        end=datetime.strptime(self.cq_end.dateTime().toString('yyyy-MM-dd HH:mm'),'%Y-%m-%d %H:%M').replace(tzinfo=timezone.utc)
        if start>end:
            self.error.setText('開始日時は終了日時以前にしてください。');return False
        self.year.setValue(self.cq_year.value())
        self._display_datetime(self.start,start);self._display_datetime(self.end,end)
        self.call_filter.setText('')  # Include other own calls so they can be warned about, not silently dropped.
        self.band_filter.setCurrentText('ALL')
        self.band_filter.setEnabled(False)
        self.call_filter.setEnabled(False)
        self.filter_note.setText('CQ WWは指定期間の全バンド・全自局CALLを表示します。異なる自局CALLは次の画面で警告します。')
        self.set_value('CALLSIGN',call)
        self.set_value('LOCATION','DX' if self.cq_region.currentText()!='米国・カナダ' else '')
        if self.cq_region.currentText()=='米国・カナダ':self.fields['LOCATION'].setPlaceholderText('州・地域略号（例：MA、ON）')
        self.reload() if not self.records else self.apply_filter()
        if not self.visible:
            self.error.setText('指定期間に対象交信がありません。期間を確認してください。');return False
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
        self.dates.setText(f'{self.year.value()}年の大会期間を入力')

    def set_period(self):
        if self.profile=='generic':return
        start,end=period(self.profile,self.year.value());self._display_datetime(self.start,start);self._display_datetime(self.end,end)
        if hasattr(self,'error'):self.error.setText('期間を変更しました。［抽出］で一覧に反映してください。')

    def reload(self):
        if self.records and QMessageBox.question(self,'ADIF再読込','出力用の編集と選択を破棄して、ADIFを読み直しますか？')!=QMessageBox.Yes:return
        try:
            self.records=self.adif.load_recent(limit=None)
            self.read_errors=list(getattr(self.adif,'read_errors',[]))
        except Exception as exc:
            self.record_diagnostic('ADIF読込',exc)
            self.error.setText('ADIFを読み込めませんでした。ログフォルダーとファイルを確認して、再読込してください。');return
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
        if start>end:self.error.setText('開始日時は終了日時以前にしてください。');return
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
        if self.read_errors:self.record_diagnostic('ADIF読込詳細',ValueError(' / '.join(map(str,self.read_errors))))
        self.error.setText('読み込めないADIFがあります。ログファイルを確認して再読込してください。' if self.read_errors else '')
        self.applied_filter=(start,end,call,band)

    def render_table(self):
        self.table.blockSignals(True);self.table.setRowCount(len(self.visible))
        self.table.setHorizontalHeaderItem(1,QTableWidgetItem('日時（'+self.zone.currentText()+'）'))
        for row,index in enumerate(self.visible):
            state=self.states[index]
            for col,key in [(0,'checked'),(10,'xqso')]:
                item=QTableWidgetItem();item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable|Qt.ItemIsUserCheckable);item.setCheckState(Qt.Checked if state[key] else Qt.Unchecked);self.table.setItem(row,col,item)
            for col,value in enumerate(state['values'],1):self.table.setItem(row,col,QTableWidgetItem(value))
            item=QTableWidgetItem('');item.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable);self.table.setItem(row,11,item)
        self.table.blockSignals(False);self.has_table=True;self.update_count()

    def update_count(self,*args):
        selected=sum(self.table.item(r,0).checkState()==Qt.Checked for r in range(self.table.rowCount()) if self.table.item(r,0))
        self.count.setText(f'選択 {selected}件 / 表示 {len(self.visible)}件 / 読込 {len(self.records)}件')

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
            raise ValueError('日時の入力形式')
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
                if not vals[0]:invalid(1,'日時を入力してください。例：2026-09-26 09:00')
                else:
                    try:when=self.row_datetime(index,vals[0])
                    except ValueError as exc:
                        self.record_diagnostic(f'一覧 {row+1}行 日時',exc)
                        invalid(1,'日時を確認してください。例：2026-09-26 09:00')
                if when is not None and not self._read_datetime(self.start)<=when<=self._read_datetime(self.end):
                    invalid(1,'日時が抽出期間外です。開始・終了を修正して再抽出してください。')
                if not vals[3]:invalid(4,'周波数を入力してください。例：14.085')
                else:
                    try:
                        if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)?',vals[3]):raise InvalidOperation('MHz must use decimal digits')
                        freq=Decimal(vals[3])*1000000
                        if not freq.is_finite() or freq<=0 or freq!=freq.to_integral_value():
                            invalid(4,'周波数は0より大きいMHz値を、小数点以下6桁以内で入力してください。例：14.085')
                    except (InvalidOperation,ValueError) as exc:
                        self.record_diagnostic(f'一覧 {row+1}行 周波数',exc)
                        invalid(4,'周波数は半角数字で入力してください。例：14.085')
                if not row_errors:
                    q=replace(self.records[index],when_utc=when,station_callsign=vals[1].upper(),call=vals[2].upper(),freq_hz=int(freq),rst_sent=vals[4],rst_rcvd=vals[5],sent=vals[6],rcvd=vals[7])
                    if self.band_filter.currentText()!='ALL' and q.band.upper()!=self.band_filter.currentText():
                        invalid(4,'周波数が抽出バンドと異なります。再抽出してください。')
                    if self.call_filter.text().strip() and q.station_callsign and q.station_callsign!=self.call_filter.text().strip().upper():
                        invalid(2,'自局CALLが抽出条件と異なります。再抽出してください。')
                    if not row_errors:entries.append((q,{'txid':vals[8],'xqso':state['xqso']}))
                if row_errors:
                    message=f'一覧 {row+1}行 [{vals[2]}]：'+' / '.join(row_errors)
                    errors.append(message);self.table.item(row,11).setText(' / '.join(row_errors))
        finally:self.table.blockSignals(False)
        return entries,errors

    def _set_page(self,index):
        titles={0:'① 出力形式',5:'② CQ WW運用地・期間',1:'対象QSOの選択・出力用編集',
                6:'JARL 参加部門・最大出力',7:'JARL 運用地',8:'JARL 得点確認',
                3:'必須項目',2:'任意項目',4:'確認・保存'}
        self.pages.setCurrentIndex(index);self.heading.setText(titles[index])
        self.back.setEnabled(index!=0);self.next.setText('ファイルに保存' if index==4 else '次へ');self.error.clear()
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
                self.error.setText('抽出条件を変更しています。［抽出］を押して一覧を確認してください。');return
            entries,errors=self.selected_entries()
            if self.read_errors:errors=['読み込みエラーのあるADIFを確認し、再読込してください。']+errors
            if not entries and not errors:errors=['出力するQSOを選択してください。']
            if errors:self.error.setText('\n'.join(errors[:8]));return
            if self.profile=='jarl':
                self._set_page(6);return
            if self.profile=='cqww':
                zones={q.sent.split()[0] for q,_ in entries if q.sent.strip() and q.sent.split()[0].isdigit()}
                if len(zones)==1:self.set_value('MY-CQ-ZONE',next(iter(zones)))
                mixed=sorted({q.station_callsign or '空欄' for q,_ in entries if q.station_callsign.upper()!=self.value('CALLSIGN').upper()})
                self.cq_warning.setText('注意：選択した交信に異なる自局CALLが含まれます：'+', '.join(mixed)+'。提出CALLと対象を確認してください。' if mixed else '')
            self._set_page(3)
        elif index==6:
            power=self.jarl_power.currentText();watts=self.jarl_watts.value()
            if (power=='QRP' and watts>5 or power=='LOW' and watts>100 or
                power=='HIGH' and watts<=100 or self.jarl_operator.currentText()=='MULTI-OP' and power=='QRP'):
                self.error.setText('出力部門と最大出力（W）、マルチオペの区分を確認してください。');return
            self.set_value('CATEGORY-OPERATOR',self.jarl_operator.currentText())
            self.set_value('CATEGORY-POWER',power)
            self.set_value('CATEGORY-BAND','ALL')
            self._set_page(7)
        elif index==7:
            if self.jarl_location.currentIndex()==1 and not re.fullmatch('[A-Za-z0-9/]{1,12}',self.jarl_entity.text().strip()):
                self.error.setText('海外の運用エンティティを入力してください。');return
            if self.jarl_location.currentIndex()==0 and self.jarl_portable.isChecked() and not self.jarl_prefecture.text().strip():
                self.error.setText('移動運用地の都道府県をローマ字で入力してください。');return
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
                    self.error.setText('JARLの得点確認に戻って計算結果を確定してください。');return
                self.set_value('CLAIMED-SCORE',str(result['total']))
            entries,errors=self.selected_entries();body,validation,warnings=build_cabrillo(self.profile,self.info(),entries);errors+=validation
            if errors:
                self.error.setText('\n'.join(errors[:8])+ (f'\nほか{len(errors)-8}件' if len(errors)>8 else ''));return
            self.body=body;self.preview.setPlainText(body);self.warnings.setPlainText('\n'.join(warnings) if warnings else '確認事項なし')
            self.summary.setText(f'{PROFILES[self.profile]} ／ {self.value("CALLSIGN")} ／ {self.value("CATEGORY-OPERATOR")}・{self.value("CATEGORY-POWER")}・{self.value("CATEGORY-BAND")}\n出力 {len(entries)}件（X-QSO {sum(bool(e[1]["xqso"]) for e in entries)}件を含む）／日時はUTC、モードはRY\n期間：{self._read_datetime(self.start):%Y-%m-%d %H:%M} ～ {self._read_datetime(self.end):%Y-%m-%d %H:%M} UTC')
            self.saved.clear();self.saved_path=None;self.open_folder.setEnabled(False);self.submit_site.setEnabled(False);self._set_page(4)
        else:self.save_file()

    def save_file(self):
        self.error.clear()
        if self.profile=='jarl' and not self.jarl_oath.isChecked():
            self.error.setText('JARLの規約と提出内容を確認し、宣誓に同意してください。');return
        name=self.value('CALLSIGN').replace('/','_')+'_'+self.value('CONTEST')+'.log'
        path,_=QFileDialog.getSaveFileName(self,'Cabrilloを保存',name,'Cabrillo (*.log);;テキスト (*.txt)')
        if not path:return
        try:
            protected=[q.source_path for q in self.records if q.source_path]
            save_cabrillo(Path(path),self.body,protected)
        except Exception as exc:
            self.record_diagnostic('Cabrillo保存',exc)
            self.error.setText(str(exc) if isinstance(exc,ValueError) else '保存できませんでした。書き込み権限や空き容量、ファイルが開かれていないかを確認し、保存先を変更して再試行してください。');return
        self.saved_path=Path(path);self.saved.setText(f'保存しました：{path}'+ ('\n出力したファイルをCQ WW RTTY公式提出フォームから送信してください。' if self.profile=='cqww' else ''));self.open_folder.setEnabled(True)
        self.submit_site.setEnabled(self.profile=='cqww')
        old=deepcopy(self.store.data.get('cabrillo',{}));self.store.data.setdefault('cabrillo',{})[self.profile]=self.info()
        try:self.store.save()
        except Exception as exc:
            self.store.data['cabrillo']=old;self.record_diagnostic('提出情報保存',exc)
            self.error.setText('Cabrilloファイルは保存済みです。次回用の提出情報だけ保存できませんでした。設定フォルダーの書き込み権限や空き容量を確認してください。')


def store_call(store):
    return str(store.data.get('station_callsign','')).strip().upper()
