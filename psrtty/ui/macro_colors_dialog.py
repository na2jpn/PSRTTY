from copy import deepcopy
from PySide6.QtCore import Qt,QRegularExpression
from PySide6.QtGui import QColor,QRegularExpressionValidator
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QGridLayout,QLabel,QComboBox,
    QLineEdit,QPushButton,QColorDialog,QDialogButtonBox,QMessageBox,QScrollArea,QWidget)
from ..i18n import tr
from .questions import ask_question
from ..macro_colors import STANDARD,normalize,color

class MacroColorsDialog(QDialog):
    def __init__(self,store,parent=None):
        super().__init__(parent);self.store=store
        self.saved=normalize(store.data['ui'].get('macro_colors'));self.working=deepcopy(self.saved)
        self.index=self.saved['selected'];self.loading=False
        self.setWindowTitle(tr('colors.title'));self.resize(640,600)
        root=QVBoxLayout(self)
        self.preset=QComboBox();root.addWidget(self.preset)
        self.name_row=QWidget();row=QHBoxLayout(self.name_row);row.setContentsMargins(0,0,0,0)
        row.addWidget(QLabel(tr('colors.name')));self.name=QLineEdit();self.name.setMaxLength(30);row.addWidget(self.name);root.addWidget(self.name_row)
        self.note=QLabel(tr('colors.note'));self.note.setWordWrap(True);root.addWidget(self.note)
        panel=QWidget();grid=QGridLayout(panel);grid.setAlignment(Qt.AlignTop)
        grid.addWidget(QLabel(tr('colors.text')),0,1,1,2);grid.addWidget(QLabel(tr('colors.background')),0,3,1,2)
        self.edits=[];self.swatches=[]
        for i in range(9):
            grid.addWidget(QLabel(f'F{i+1}'),i+1,0);edits={};swatches={}
            for column,key in [(1,'text'),(3,'background')]:
                edit=QLineEdit();edit.setMaxLength(7);edit.setMinimumWidth(95)
                edit.setValidator(QRegularExpressionValidator(QRegularExpression('#[0-9a-fA-F]{0,6}'),edit))
                sample=QPushButton();sample.setFixedSize(48,28);sample.setAccessibleName(f'F{i+1} '+tr('colors.'+key))
                sample.clicked.connect(lambda checked=False,e=edit:self._pick(e))
                edit.textChanged.connect(lambda value,e=edit,b=sample:self._preview(e,b))
                grid.addWidget(edit,i+1,column);grid.addWidget(sample,i+1,column+1);edits[key]=edit;swatches[key]=sample
            self.edits.append(edits);self.swatches.append(swatches)
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(panel);root.addWidget(scroll,1)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Cancel|QDialogButtonBox.Save)
        self.buttons.button(QDialogButtonBox.Cancel).setText(tr('colors.cancel'));self.buttons.button(QDialogButtonBox.Save).setText(tr('colors.save'))
        self.buttons.rejected.connect(self.reject);self.buttons.accepted.connect(self._save);root.addWidget(self.buttons)
        self.name.textChanged.connect(self._rename)
        self._labels();self._load();self.preset.currentIndexChanged.connect(self._change)
    def _labels(self):
        self.preset.blockSignals(True);self.preset.clear();self.preset.addItem(tr('colors.standard'))
        for i,p in enumerate(self.working['presets'],1):
            self.preset.addItem(tr('colors.preset').format(number=i)+(f" ({p['name']})" if p['name'] else ''))
        self.preset.setCurrentIndex(self.index);self.preset.blockSignals(False)
    def _load(self):
        self.loading=True;editable=self.index>0
        self.name_row.setVisible(editable);self.name.setText(self.working['presets'][self.index-1]['name'] if editable else '')
        rows=self.working['presets'][self.index-1]['colors'] if editable else STANDARD
        for edits,samples,row in zip(self.edits,self.swatches,rows):
            for key,edit in edits.items():
                edit.setText(row[key]);edit.setReadOnly(not editable);samples[key].setEnabled(editable)
        self.loading=False
    def _rename(self,text):
        if self.loading or self.index==0:return
        self.working['presets'][self.index-1]['name']=text
        self._labels()
    def _preview(self,edit,sample):
        good=color(edit.text())
        edit.setStyleSheet('' if good else 'border: 1px solid #c00000;')
        if good:sample.setStyleSheet('background: '+edit.text()+'; border: 1px solid #777;')
    def _pick(self,edit):
        chosen=QColorDialog.getColor(QColor(edit.text()) if color(edit.text()) else QColor('#FFFFFF'),self,tr('colors.title'))
        if chosen.isValid():edit.setText(chosen.name().upper())
    def _current(self):
        return {'name':self.name.text(),'colors':[{k:e.text().upper() for k,e in row.items()} for row in self.edits]}
    def _dirty(self):
        return self.index>0 and self._current()!=self.saved['presets'][self.index-1]
    def _discard_ok(self):
        return ask_question(self,tr('colors.title'),tr('colors.discard'))==QMessageBox.Yes
    def _change(self,index):
        if self._dirty() and not self._discard_ok():
            self.preset.blockSignals(True);self.preset.setCurrentIndex(self.index);self.preset.blockSignals(False);return
        if self.index>0:self.working['presets'][self.index-1]=deepcopy(self.saved['presets'][self.index-1])
        self.index=index;self._labels();self._load()
    def _save(self):
        if self.index>0:
            if not all(color(e.text()) for row in self.edits for e in row.values()):
                QMessageBox.warning(self,tr('colors.title'),tr('colors.invalid'));return
            self.working['presets'][self.index-1]=self._current()
        self.working['selected']=self.index
        old=deepcopy(self.store.data['ui'].get('macro_colors'))
        try:self.store.data['ui']['macro_colors']=normalize(self.working);self.store.save()
        except Exception as exc:
            if old is None:self.store.data['ui'].pop('macro_colors',None)
            else:self.store.data['ui']['macro_colors']=old
            QMessageBox.warning(self,tr('colors.title'),str(exc));return
        self.saved=deepcopy(self.working);self.accept()
    def reject(self):
        if (self._dirty() or self.index!=self.saved['selected']) and not self._discard_ok():return
        super().reject()
