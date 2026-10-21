"""Independent vertical RTTY band maps. All network/DSP work stays off Qt."""
import queue
import time
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QUrl
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap, QDesktopServices
from PySide6.QtWidgets import (QDialog,QWidget,QVBoxLayout,QHBoxLayout,QGridLayout,
    QLabel,QPushButton,QCheckBox,QScrollArea,QSplitter,QComboBox,QLineEdit,
    QDoubleSpinBox,QFormLayout,QFileDialog,QStackedWidget,QPlainTextEdit)
from ..i18n import tr
from ..diagnostics import event
from ..paths import resource_path, app_root
from ..card_entity import entity_name
from ..ry_ja import ja_rtty,ja_band,ja_pair
from ..ry_spots import BANDS,Spot,SpotCache,age_color,band_for,short_frequency
from .window_state import independent_tool_window,place_tool_window,save_window


class BandCanvas(QWidget):
    tune=Signal(int)
    selected=Signal(object)
    manual=Signal(float)

    def __init__(self, band=14):
        super().__init__();self.band=band;self.spots=[];self.hits=[];self.message=''
        self.range=None;self.spectrum=None;self.skimmer=False
        self.setMinimumSize(180,100)

    def set_rows(self,rows,now=None):
        now=time.time() if now is None else now
        values=[(s,age_color(now-s.stamp) or '#727272') for s in sorted(rows,key=lambda s:s.hz)]
        if values!=self.spots:
            self.spots=values
            self.setMinimumHeight(max(100,len(values)*(self.fontMetrics().height()+5)+50))
            self.update()

    def limits(self):
        if self.range:return self.range
        # Show the RTTY part at useful magnification; expand for real reports.
        defaults={1.8:(1.800,1.850),3.5:(3.55,3.65),5:(5.30,5.40),7:(7.025,7.125),
          10:(10.10,10.15),14:(14.06,14.15),18:(18.07,18.12),21:(21.06,21.15),
          24:(24.89,24.94),28:(28.06,28.20),50:(50.0,50.5),144:(144.0,144.5),430:(430,431),1200:(1293,1296)}
        lo,hi=defaults.get(self.band,(self.band,self.band+1))
        if self.spots:lo=min(lo,(min(s.hz for s,c in self.spots)-1000)/1e6);hi=max(hi,(max(s.hz for s,c in self.spots)+1000)/1e6)
        return lo*1e6,hi*1e6

    def y_for(self,hz):
        lo,hi=self.limits();return 30+(hz-lo)/max(1,hi-lo)*(self.height()-52)

    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(),QColor('#fffdf8'));p.setPen(QColor('#554b3e'))
        p.drawText(8,20,f'{self.band:g} MHz' if self.band else '—')
        self.hits=[]
        if self.message:
            p.drawText(self.rect().adjusted(12,30,-12,-12),Qt.AlignCenter|Qt.TextWordWrap,self.message);return
        lo,hi=self.limits()
        labels=[f'{(lo+(hi-lo)*i/4)/1e6:.3f}'.rstrip('0').rstrip('.') for i in range(5)]
        axis=max(65,max(self.fontMetrics().horizontalAdvance(t) for t in labels)+12)
        p.setPen(QPen(QColor('#7c8da7'),1));p.drawLine(axis,30,axis,self.height()-22)
        for i,label in enumerate(labels):
            hz=lo+(hi-lo)*i/4;y=int(self.y_for(hz));p.drawLine(axis-4,y,axis+4,y)
            p.drawText(QRectF(2,y-self.fontMetrics().height()/2,axis-10,self.fontMetrics().height()),Qt.AlignRight|Qt.AlignVCenter,label)
        if self.spectrum:
            import numpy as np
            freqs,db=self.spectrum
            if len(db):
                floor=float(np.percentile(db,25));p.setPen(QPen(QColor('#aa9a80'),1))
                for hz,value in zip(freqs[::2],db[::2]):
                    if lo<=hz<=hi:
                        y=int(self.y_for(hz));width=int(max(0,min(.8,(value-floor)/60))*(self.width()-axis))
                        p.drawLine(axis,y,axis+width,y)
        height=self.fontMetrics().height()+5;last=28
        positions=[]
        for spot,color in self.spots:
            target=self.y_for(spot.hz);y=max(last+height,target);positions.append(y);last=y
        if positions and positions[-1]>self.height()-15:
            positions[-1]=self.height()-15
            for i in range(len(positions)-2,-1,-1):positions[i]=min(positions[i],positions[i+1]-height)
        for (spot,color),y in zip(self.spots,positions):
            p.setPen(QPen(QColor(color),1));target=self.y_for(spot.hz)
            p.drawLine(axis,int(target),axis+16,int(y-4))
            name=entity_name(spot.call) if spot.call else ''
            text=f'{short_frequency(spot.hz)}  {spot.call}  {name}'
            rect=QRectF(axis+19,y-height+3,max(1,self.width()-axis-22),height)
            text=self.fontMetrics().elidedText(text,Qt.ElideRight,int(rect.width()))
            p.drawText(rect,Qt.AlignVCenter,text);self.hits.append((rect,spot))

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            for rect,spot in self.hits:
                if rect.contains(event.position()):self.selected.emit(spot);return
            if self.skimmer:
                lo,hi=self.limits();hz=lo+(event.position().y()-30)/max(1,self.height()-52)*(hi-lo)
                self.manual.emit(hz)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:
            for rect,spot in self.hits:
                if rect.contains(event.position()):self.selected.emit(spot);self.tune.emit(spot.hz);event.accept();return


def scroll_canvas(canvas):
    scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(canvas)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);return scroll


class RYWindow(QDialog):
    key=''
    def __init__(self,main,title):
        super().__init__(None,Qt.Window);self.main=main;independent_tool_window(self,main)
        self.setWindowTitle(title);self.resize(1050,650);self.setMinimumSize(600,400)
        self.root=QVBoxLayout(self);self.root.setSpacing(6)
        self.explanation=QLabel(tr('ry.tune_help'));self.explanation.setWordWrap(True)
        self.detail=QLabel();self.detail.setWordWrap(True);self.detail.setTextFormat(Qt.PlainText)

    def ja_checkbox(self,key):
        box=QCheckBox('JA-BAND ONLY');box.setChecked(self.main.store.data['ui'].get(key,True))
        box.setToolTip(tr('ry.ja_help'))
        def changed(checked):
            self.main.store.data['ui'][key]=checked;self.main.store.save()
            if hasattr(self,'layout_bands'):self.layout_bands()
            if getattr(self,'worker',None):
                with self.worker.lock:self.worker.engine.ja_only=checked
            self.refresh()
        box.toggled.connect(changed)
        return box

    def mode_checkbox(self):
        box=QCheckBox(tr('ry.mode_link'));box.setChecked(self.main.store.data['ui'].get('ry_mode_link',True))
        box.setToolTip(tr('ry.mode_help'));self.mode_link=box
        def changed(checked):
            old=self.main.store.data['ui'].get('ry_mode_link',True)
            self.main.store.data['ui']['ry_mode_link']=checked
            try:self.main.store.save()
            except Exception as exc:
                self.main.store.data['ui']['ry_mode_link']=old
                box.blockSignals(True);box.setChecked(old);box.blockSignals(False)
                event('settings','RY mode linkage save failed',error=exc)
                self.main.statusBar().showMessage(tr('ry.error').format(error=exc),10000);return
            for key in ('ry_skimmer_window','ry_radar_window'):
                window=getattr(self.main,key,None)
                if window is not None and hasattr(window,'mode_link'):
                    other=window.mode_link;other.blockSignals(True);other.setChecked(checked);other.blockSignals(False)
        box.toggled.connect(changed);return box

    def reveal(self):
        place_tool_window(self,self.main,(1050,650),(600,400),self.main.store.data['ui'].get(self.key))
        self.show();self.raise_();self.activateWindow()

    def hook(self,canvas):
        canvas.tune.connect(self.main._ry_tune);canvas.selected.connect(self.select)

    def select(self,spot):
        self.detail.setText(f'{spot.hz/1e6:.6f} MHz  {spot.call}  {entity_name(spot.call)}  '
            f'{spot.source}  {spot.reporter}  {time.strftime("%H:%M:%S UTC",time.gmtime(spot.stamp))}\n{spot.text or spot.comment}')

    def closeEvent(self,event):
        if hasattr(self,'timer'):self.timer.stop()
        self.main.store.data['ui'][self.key]=save_window(self)
        super().closeEvent(event)

    def showEvent(self,event):
        if hasattr(self,'timer'):self.timer.start()
        super().showEvent(event)

    def hideEvent(self,event):
        if hasattr(self,'timer'):self.timer.stop()
        super().hideEvent(event)


class RadarWindow(RYWindow):
    key='ry_radar_window'
    def __init__(self,main):
        super().__init__(main,tr('ry.radar'));self.cache=SpotCache();self.feeds=None;self.statuses={};self.last_received={};self.active_band=None;self.rotation=None
        row=QHBoxLayout();self.start=QPushButton(tr('ry.start'));self.start.clicked.connect(self.start_feeds)
        self.stop=QPushButton(tr('ry.stop'));self.stop.clicked.connect(self.stop_feeds);self.stop.setEnabled(False)
        row.addWidget(self.start);row.addWidget(self.stop);self.ja_only=self.ja_checkbox('ry_radar_ja_only');row.addWidget(self.ja_only);row.addWidget(self.mode_checkbox());row.addStretch()
        self.root.addLayout(row)
        bands=QGridLayout();self.bands=bands;self.band_buttons={}
        selected=main.store.data['ui'].get('ry_radar_bands',[3.5,7,14,21,28])
        for i,(band,lo,hi) in enumerate(BANDS):
            b=QPushButton(f'{band:g}');b.setCheckable(True);b.setChecked(band in selected)
            b.setMaximumWidth(58);b.toggled.connect(self.layout_bands);bands.addWidget(b,i//8,i%8);self.band_buttons[band]=b
        self.root.addLayout(bands)
        self.root.addWidget(self.explanation)
        self.split=QSplitter();self.left=BandCanvas();self.hook(self.left);self.split.addWidget(scroll_canvas(self.left))
        self.right=QWidget();self.grid=QGridLayout(self.right);self.grid.setContentsMargins(0,0,0,0)
        self.split.addWidget(self.right);self.split.setStretchFactor(0,1);self.split.setStretchFactor(1,2);self.split.setSizes([340,680])
        self.root.addWidget(self.split,1);self.root.addWidget(self.detail)
        self.legend=QLabel(tr('ry.age_legend'));self.legend.setWordWrap(True);self.root.addWidget(self.legend)
        self.status=QLabel(tr('ry.sources_note'));self.status.setWordWrap(True);self.root.addWidget(self.status)
        self.status.setTextFormat(Qt.PlainText)
        self.panels={};self.timer=QTimer(self);self.timer.setInterval(500);self.timer.timeout.connect(self.refresh)
        self.timer.start();self.layout_bands()

    def start_feeds(self):
        from ..ry_radar import RadarFeeds,load_sources
        from ..parser import CALL_RE
        call=self.main.my_call.text().strip().upper()
        if not CALL_RE.fullmatch(call):self.status.setText(tr('ry.call_required'));return
        try:
            config=load_sources();self.statuses={};self.rotation=None;self.last_received={}
            self.feeds=RadarFeeds(config,call);self.feeds.start()
            self.start.setEnabled(False);self.stop.setEnabled(True)
        except Exception as e:self.status.setText(tr('ry.error').format(error=e))

    def stop_feeds(self):
        if self.feeds:self.feeds.stop();self.feeds=None
        self.start.setEnabled(True);self.stop.setEnabled(False);self.status.setText(tr('ry.stopped'))

    def layout_bands(self):
        if not hasattr(self,'grid'):return
        selected=[band for band,b in self.band_buttons.items() if b.isChecked()]
        self.main.store.data['ui']['ry_radar_bands']=selected
        desired=[b for b in selected if b!=self.active_band and (not self.ja_only.isChecked() or ja_band(b))]
        visible_index=0
        for band,button in self.band_buttons.items():
            self.bands.removeWidget(button)
            visible=not self.ja_only.isChecked() or ja_band(band)
            if visible:
                self.bands.addWidget(button,visible_index//8,visible_index%8);visible_index+=1
            button.setEnabled(band!=self.active_band)
            button.setVisible(not self.ja_only.isChecked() or ja_band(band))
        for panel in self.panels.values():self.grid.removeWidget(panel);panel.hide()
        columns=1 if len(desired)<=2 else 2 if len(desired)<=6 else 3
        for i,band in enumerate(desired):
            if band not in self.panels:
                canvas=BandCanvas(band);self.hook(canvas);self.panels[band]=scroll_canvas(canvas)
            panel=self.panels[band];self.grid.addWidget(panel,i//columns,i%columns);panel.show()
        # Clear old stretches when switching between different grid shapes.
        for i in range(self.grid.rowCount()):self.grid.setRowStretch(i,1 if i<(len(desired)+columns-1)//columns else 0)
        for i in range(self.grid.columnCount()):self.grid.setColumnStretch(i,1 if i<columns else 0)

    def refresh(self):
        now=time.time();self.cache.expire(now)
        if self.feeds:
            for _ in range(300):
                try:event=self.feeds.events.get_nowait()
                except queue.Empty:break
                if event[0]=='spot':
                    self.cache.put(event[1],now)
                    self.last_received[event[1].source]=now
                elif event[0]=='rotation':self.rotation=event[1:]
                else:
                    _,name,state,error=event
                    if state!='closed' or self.statuses.get(name,('', ''))[0]!='error':self.statuses[name]=(state,error)
            parts=[]
            if self.rotation:
                name,index,total=self.rotation;parts.append(tr('ry.rotation').format(index=index,total=total,name=name))
            for name,(state,error) in self.statuses.items():
                text=tr('ry.retry_error').format(error=error) if state=='error' else tr('ry.'+state)
                parts.append(f'{name}: '+text+(' / '+time.strftime('%H:%M:%S UTC',time.gmtime(self.last_received[name])) if name in self.last_received else ''))
            self.status.setText(' | '.join(parts))
        freq=self.main.current_freq_hz if self.main._connected() else None
        band=band_for(freq)
        if band!=self.active_band:self.active_band=band;self.layout_bands()
        self.left.band=band;self.left.message='' if band else tr('ry.connect_rig') if not self.main._connected() else tr('ry.no_frequency')
        self.left.set_rows([s for s in self.cache.rows.values() if s.band==band and (not self.ja_only.isChecked() or ja_rtty(s.hz))],now);self.left.update()
        for band,panel in self.panels.items():panel.widget().set_rows([s for s in self.cache.rows.values() if s.band==band and (not self.ja_only.isChecked() or ja_rtty(s.hz))],now)

    def closeEvent(self,event):
        self.stop_feeds();super().closeEvent(event)


class SkimmerSetup(QDialog):
    def __init__(self,main):
        super().__init__(main);self.main=main;self.setWindowTitle(tr('ry.skimmer'));self.resize(720,600)
        self.root=QVBoxLayout(self);self.pages=QStackedWidget();self.root.addWidget(self.pages)
        first=QWidget();v=QVBoxLayout(first)
        from .. import i18n
        if i18n.LANGUAGE=='ja':
            class ChoicePicture(QLabel):
                chosen=Signal(str)
                def mouseReleaseEvent(self,event):
                    if event.button()==Qt.LeftButton:self.chosen.emit('extio' if event.position().x()<self.width()/2 else 'rtl')
            picture=ChoicePicture();picture.setAlignment(Qt.AlignCenter);picture.setCursor(Qt.PointingHandCursor);picture.chosen.connect(self.choose)
            picture.setPixmap(QPixmap(str(resource_path('assets/ry_skimmer.png'))).scaledToWidth(660,Qt.SmoothTransformation));v.addWidget(picture)
        else:
            diagram=QLabel('IC-7610 / IC-7760  →  USB  →  PC\n\nSDR ANT  →  RTL-SDR  →  USB  →  PC')
            diagram.setAlignment(Qt.AlignCenter);diagram.setMinimumHeight(140);diagram.setStyleSheet('font-size:17px; background:#fff3df; padding:12px');v.addWidget(diagram)
        for method,label in [('extio','ry.icom_choice'),('rtl','ry.rtl_choice')]:
            b=QPushButton(tr(label));b.clicked.connect(lambda checked=False,m=method:self.choose(m));v.addWidget(b)
        cable=QLabel(tr('ry.cable_note'));cable.setWordWrap(True);v.addWidget(cable)
        note=QLabel(tr('ry.input_note'));note.setWordWrap(True);v.addWidget(note);v.addStretch()
        self.pages.addWidget(first)
        self.settings=QWidget();form=QFormLayout(self.settings);self.form=form
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.method_label=QLabel();form.addRow(self.method_label)
        self.model=QComboBox();self.model.addItems(['IC-7610','IC-7760']);form.addRow(tr('ry.iq_model'),self.model)
        self.links=QHBoxLayout();self.download=QPushButton(tr('ry.download'));self.download.clicked.connect(self.open_download)
        self.dll_folder=QPushButton(tr('ry.dll_folder'));self.dll_folder.clicked.connect(self.choose_dll_folder)
        self.links.addWidget(self.download);self.links.addWidget(self.dll_folder);form.addRow(self.links)
        self.hint=QLabel();self.hint.setWordWrap(True);self.hint.setTextFormat(Qt.PlainText);form.addRow(self.hint)
        self.candidates=QComboBox();self.candidates.currentIndexChanged.connect(self.pick_dll);form.addRow(tr('ry.dll_candidates'),self.candidates)
        self.model.currentIndexChanged.connect(self.update_hints)
        file_row=QHBoxLayout();self.dll=QLineEdit();browse=QPushButton('…');browse.clicked.connect(self.browse)
        file_row.addWidget(self.dll);file_row.addWidget(browse);form.addRow(tr('ry.dll'),file_row)
        devices=QHBoxLayout();self.device=QComboBox();self.scan=QPushButton(tr('ry.find_devices'));self.scan.clicked.connect(self.find_devices)
        devices.addWidget(self.device);devices.addWidget(self.scan);self.devices_row=devices;form.addRow(tr('ry.device'),devices)
        self.direct=QComboBox()
        for text,value in [('ry.tuner',0),('ry.direct_i',1),('ry.direct_q',2)]:self.direct.addItem(tr(text),value)
        form.addRow(tr('ry.hf_input'),self.direct)
        self.center=QDoubleSpinBox();self.center.setDecimals(6);self.center.setRange(.1,1300);self.center.setSuffix(' MHz');form.addRow(tr('ry.center'),self.center)
        self.span=QComboBox()
        for width in (10,20,40):self.span.addItem(f'{width} kHz',width*1000)
        form.addRow(tr('ry.span'),self.span)
        self.reverse=QCheckBox(tr('ry.reverse'));form.addRow(self.reverse)
        self.range_note=QLabel(tr('ry.range_help'));self.range_note.setWordWrap(True);form.addRow(self.range_note)
        self.note=QLabel(tr('ry.driver_note'));self.note.setWordWrap(True);form.addRow(self.note)
        self.note.setTextFormat(Qt.PlainText)
        self.footer=QWidget();buttons=QHBoxLayout(self.footer);buttons.setContentsMargins(0,0,0,0);back=QPushButton(tr('ry.back'));back.clicked.connect(lambda:self.pages.setCurrentIndex(0));self.go=QPushButton(tr('ry.start'));self.go.clicked.connect(self.accept_options)
        buttons.addWidget(back);buttons.addStretch();buttons.addWidget(self.go);self.root.addWidget(self.footer);self.footer.hide()
        self.pages.currentChanged.connect(lambda index:self.footer.setVisible(index==1))
        settings_scroll=QScrollArea();settings_scroll.setWidgetResizable(True);settings_scroll.setWidget(self.settings)
        self.pages.addWidget(settings_scroll);self.options=None;self.rtl=None

    def choose(self,method):
        self.method=method;self.options=None
        options=self.main.store.data['ui'].get('ry_skimmer_inputs',{}).get(method,{})
        self.model.setCurrentText(options.get('model','IC-7610'));self.candidates.clear()
        self.form.setRowVisible(self.model,method=='extio')
        self.form.setRowVisible(self.devices_row,method=='rtl');self.form.setRowVisible(self.direct,method=='rtl')
        self.update_hints()
        self.method_label.setText(tr('ry.icom_choice' if method=='extio' else 'ry.rtl_choice'))
        self.dll.setText(options.get('dll',''));self.device.clear();serial=options.get('serial','')
        if serial:self.device.addItem(serial,serial)
        self.center.setValue(options.get('center',(self.main.current_freq_hz or 14090000)/1e6))
        self.span.setCurrentIndex(max(0,self.span.findData(options.get('span',20000))))
        self.direct.setCurrentIndex(max(0,self.direct.findData(options.get('direct',0))))
        self.reverse.setChecked(options.get('reverse',False));self.device.setEnabled(method=='rtl');self.scan.setEnabled(method=='rtl');self.direct.setEnabled(method=='rtl')
        self.pages.setCurrentIndex(1)

    def update_hints(self):
        if not hasattr(self,'method'):return
        key='icom_7610_help' if self.model.currentText()=='IC-7610' else 'icom_7760_help'
        self.hint.setText(tr('ry.'+key) if self.method=='extio' else tr('ry.rtl_help'))
        self.note.setText(tr('ry.driver_note'))

    def open_download(self):
        url=('https://www.icomjapan.com/support/firmware_driver/'+('1956/' if self.model.currentText()=='IC-7610' else '4190/')) if self.method=='extio' else 'https://www.rtl-sdr.com/rtl-sdr-quick-start-guide/'
        QDesktopServices.openUrl(QUrl(url))

    def choose_dll_folder(self):
        directory=QFileDialog.getExistingDirectory(self,tr('ry.dll_folder'),str(Path(self.dll.text()).parent) if self.dll.text() else str(Path.home()))
        if not directory:return
        self.candidates.clear()
        # Search only the chosen folder and two child levels, never the whole disk.
        base=Path(directory);found=[]
        for pattern in ('*.dll','*/*.dll','*/*/*.dll','*.DLL','*/*.DLL','*/*/*.DLL'):
            for f in base.glob(pattern):
                name=f.name.lower()
                if (name.startswith('extio') if self.method=='extio' else name in ('rtlsdr.dll','librtlsdr.dll')):found.append(f)
        for f in sorted(set(found))[:100]:self.candidates.addItem(str(f),str(f))
        if not found:self.show_error(tr('ry.no_dll'))

    def pick_dll(self):
        if self.candidates.currentData():self.dll.setText(self.candidates.currentData())

    def browse(self):
        name,_=QFileDialog.getOpenFileName(self,tr('ry.dll'),self.dll.text(),'DLL (*.dll);;All (*)')
        if name:self.dll.setText(name)

    def find_devices(self):
        from ..ry_iq import RTLInput
        from .background import BackgroundJob
        self.scan.setEnabled(False);self.go.setEnabled(False)
        def done(result,error):
            self.scan.setEnabled(True);self.go.setEnabled(True)
            if error:self.show_error(error);return
            self.rtl,rows=result;self.device.clear()
            for index,serial,product in rows:self.device.addItem(f'{product} / {serial}',serial)
            if not rows:self.show_error(tr('ry.no_device'))
        # Capture GUI values before dispatching work.
        dll=self.dll.text()
        def work():
            obj=RTLInput(dll,'',0,None,None);return obj,obj.devices()
        self.job=BackgroundJob(self,work,done)

    def show_error(self,error):
        self.note.setStyleSheet('color:#c62828;');self.note.setText(tr('ry.error').format(error=error))
        event('ry_skimmer','Input settings failed',error=error)

    def accept_options(self):
        from copy import deepcopy
        before=deepcopy(self.main.store.data['ui'].get('ry_skimmer_inputs',{}))
        try:
            event('ry_skimmer','Input settings validation')
            if not Path(self.dll.text()).is_file():raise ValueError(tr('ry.no_dll'))
            if self.method=='rtl' and not self.device.currentData():raise ValueError(tr('ry.no_device'))
            from ..ry_iq import pe_bits
            bits=pe_bits(self.dll.text())
            event('ry_skimmer','DLL '+self.dll.text()+' '+str(bits)+' bit')
            if self.method=='extio':
                bridge=app_root()/f'lib/iq/psrtty-extio{bits}.exe'
                if not bridge.is_file():raise FileNotFoundError(tr('ry.bridge_missing').format(path=bridge))
            options=dict(model=self.model.currentText(),method=self.method,dll=self.dll.text(),serial=self.device.currentData(),center=self.center.value(),span=self.span.currentData(),reverse=self.reverse.isChecked(),direct=self.direct.currentData())
            self.main.store.data['ui'].setdefault('ry_skimmer_inputs',{})[self.method]=dict(options)
            self.main.store.save()
            self.options=options;event('ry_skimmer','Input settings saved');self.accept()
        except Exception as exc:
            self.main.store.data['ui']['ry_skimmer_inputs']=before;self.options=None;self.show_error(exc)


class SkimmerWindow(RYWindow):
    key='ry_skimmer_window'
    def __init__(self,main):
        super().__init__(main,tr('ry.skimmer'));self.worker=None;self.input=None;self.options=None;self.mailbox=queue.Queue(maxsize=100);self.generation=0
        self.spectrum_queue=queue.Queue(maxsize=1);self.rows={};self.last_samples=0;self.last_data=time.monotonic();self.failure='';self.first_iq=False
        row=QHBoxLayout();self.setup=QPushButton(tr('ry.input_settings'));self.setup.clicked.connect(self.configure)
        self.start=QPushButton(tr('ry.start'));self.start.clicked.connect(self.start_input)
        self.stop=QPushButton(tr('ry.stop'));self.stop.clicked.connect(self.stop_input);self.stop.setEnabled(False)
        for button in (self.setup,self.start,self.stop):row.addWidget(button)
        self.ja_only=self.ja_checkbox('ry_skimmer_ja_only');row.addWidget(self.ja_only);row.addWidget(self.mode_checkbox())
        row.addStretch();self.root.addLayout(row);self.root.addWidget(self.explanation)
        reference=QLabel(tr('ry.mark_reference'));reference.setWordWrap(True);self.root.addWidget(reference)
        self.canvas=BandCanvas();self.canvas.skimmer=True;self.hook(self.canvas);self.canvas.manual.connect(self.manual)
        self.canvas.tune.disconnect(self.main._ry_tune);self.canvas.tune.connect(self.tune_mark)
        self.root.addWidget(scroll_canvas(self.canvas),1)
        self.output=QPlainTextEdit();self.output.setReadOnly(True);self.output.document().setMaximumBlockCount(300);self.output.setMaximumHeight(140);self.root.addWidget(self.output)
        self.root.addWidget(self.detail);self.status=QLabel(tr('ry.skimmer_help'));self.status.setWordWrap(True);self.root.addWidget(self.status)
        self.status.setTextFormat(Qt.PlainText)
        self.timer=QTimer(self);self.timer.setInterval(250);self.timer.timeout.connect(self.refresh);self.timer.start()

    def configure(self):
        dialog=SkimmerSetup(self.main)
        if dialog.exec()==QDialog.Accepted:
            self.options=dialog.options
            self.reveal()
            QTimer.singleShot(0,self,self.start_input)

    def post(self,*args):
        try:self.mailbox.put_nowait(args)
        except queue.Full:
            if args and args[0]=='error':
                event('ry_skimmer','Input error',error=args[1])
                try:self.mailbox.get_nowait()
                except queue.Empty:pass
                try:self.mailbox.put_nowait(args)
                except queue.Full:pass

    def spectrum(self,*args):
        try:self.spectrum_queue.get_nowait()
        except queue.Empty:pass
        try:self.spectrum_queue.put_nowait(args)
        except queue.Full:pass

    def fail(self,error):
        event('ry_skimmer','Receive failed',error=error)
        self.failure=str(error);self.stop_input()
        self.status.setStyleSheet('color:#c62828;')
        self.status.setText(tr('ry.error').format(error=error)+'\n'+tr('ry.log_hint'))

    def start_input(self):
        try:self._start_input()
        except Exception as exc:self.fail(exc)

    def _start_input(self):
        if not self.options:self.configure();return
        if self.options['method']=='extio' and (self.main.active_tx_id is not None or self.main.audio._tx_active):
            self.fail(tr('ui.30cf2a7b6ef59827'));return
        from ..ry_iq import ExtIOInput,RTLInput
        from ..ry_skimmer import SkimmerWorker
        from .background import BackgroundJob
        if self.input is not None:
            self.status.setText(tr('ry.receiving') if self.first_iq else tr('ry.wait_iq'));return
        self.failure='';self.first_iq=False;self.status.setStyleSheet('')
        event('ry_skimmer','Start requested')
        o=dict(self.options);center=round(o['center']*1e6);self.rows={};self.canvas.set_rows([])
        self.generation+=1;generation=self.generation
        while not self.mailbox.empty():self.mailbox.get_nowait()
        self.worker=SkimmerWorker(on_text=lambda *args:self.post('text',*args) if generation==self.generation else None,
            on_spectrum=lambda *args:self.spectrum(*args) if generation==self.generation else None,
            span=o['span'],mark_high=not o['reverse'],ja_only=self.ja_only.isChecked())
        self.worker.start();worker=self.worker
        error=lambda text:self.post('error',text) if generation==self.generation else None
        if o['method']=='extio':source=ExtIOInput(o['dll'],center,worker.offer,error)
        else:source=RTLInput(o['dll'],o['serial'],center,worker.offer,error,o['direct'])
        self.input=source;self.setup.setEnabled(False);self.start.setEnabled(False);self.stop.setEnabled(False)
        self.canvas.band=band_for(center) or round(center/1e6,3);self.canvas.range=(center-o['span']/2,center+o['span']/2)
        self.last_samples=0;self.last_data=time.monotonic();self.status.setText(tr('ry.connecting'))
        def done(result,err):
            if self.input is not source:
                source.stop();return
            self.stop.setEnabled(True)
            if err:self.fail(err)
            elif not self.first_iq:self.status.setText(tr('ry.wait_iq'))
        self.job=BackgroundJob(self,source.start,done)

    def stop_input(self):
        self.generation+=1
        source,self.input=self.input,None
        worker,self.worker=self.worker,None
        for obj in (source,worker):
            if obj is not None:
                try:obj.stop()
                except Exception as exc:event('ry_skimmer','Stop failed',error=exc)
        self.setup.setEnabled(True);self.start.setEnabled(True);self.stop.setEnabled(False)
        event('ry_skimmer','Input stopped')
        if not self.failure:self.status.setText(tr('ry.stopped'))

    def manual(self,hz):
        if self.worker:self.worker.manual(hz)

    def tune_mark(self,hz):
        from ..ry_skimmer import dial_for_mark
        m=self.main
        hz=dial_for_mark(hz,m.store.data['radio'].get('tx_method','afsk'),
            m.store.data['advanced'].get('data_mode','LSB-D'),m.spectrum.mark_hz)
        m._ry_tune(hz)

    def refresh(self):
        now=time.time()
        for _ in range(100):
            try:event=self.mailbox.get_nowait()
            except queue.Empty:break
            if event[0]=='error':self.fail(event[1]);continue
            _,hz,call,text,recent=event
            if self.ja_only.isChecked() and not ja_pair(hz,not (self.options or {}).get('reverse',False)):continue
            self.rows[round(hz/50)]=Spot(call,round(hz),now,'IQ',text=recent)
            self.output.appendPlainText(f'{hz/1e6:.6f}  {call}  {text}')
        self.rows={k:s for k,s in self.rows.items() if now-s.stamp<120}
        self.canvas.set_rows([s for s in self.rows.values() if not self.ja_only.isChecked() or ja_pair(s.hz,not (self.options or {}).get('reverse',False))],now)
        try:
            freqs,db,center,span=self.spectrum_queue.get_nowait()
            self.canvas.spectrum=(freqs,db);self.canvas.range=(center-span/2,center+span/2)
            self.canvas.band=band_for(center) or round(center/1e6,3);self.canvas.update()
        except queue.Empty:pass
        if self.worker:
            if self.worker.error:self.post('error',self.worker.error);return
            if self.worker.samples!=self.last_samples:
                if not self.first_iq:
                    from ..diagnostics import event as record_event
                    record_event('ry_skimmer','First IQ received; samples='+str(self.worker.samples))
                    self.first_iq=True
                self.last_samples=self.worker.samples;self.last_data=time.monotonic()
                self.status.setText(tr('ry.receiving')+f' / {len(self.worker.engine.channels)} RTTY / '+tr('ry.dropped').format(count=self.worker.dropped))
            elif time.monotonic()-self.last_data>15:self.fail(tr('ry.no_iq'))

    def closeEvent(self,event):
        self.stop_input();super().closeEvent(event)
