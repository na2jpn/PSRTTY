"""Native Qt grid with responsive wrapping; no custom layout ownership."""
from PySide6.QtWidgets import QGridLayout,QWidget

class FlowLayout(QGridLayout):
    def __init__(self,parent=None):
        super().__init__(parent);self.widgets=[];self.columns=0
        self.setContentsMargins(0,0,0,0);self.setSpacing(6)
    def addWidget(self,widget):
        self.widgets.append(widget);super().addWidget(widget,0,len(self.widgets)-1)
    def addLayout(self,layout):
        widget=QWidget();widget.setLayout(layout);self.addWidget(widget)
    def addSpacing(self,size):pass
    def addStretch(self,*args):pass
    def reflow(self,width):
        visible=[w for w in self.widgets if not w.isHidden()]
        if not visible:return
        columns=1
        for candidate in range(len(visible),0,-1):
            widths=[0]*candidate
            for index,widget in enumerate(visible):
                widths[index%candidate]=max(widths[index%candidate],widget.sizeHint().width(),widget.minimumSizeHint().width(),widget.minimumWidth())
            if sum(widths)+self.spacing()*(candidate-1)<=width:
                columns=candidate;break
        signature=(columns,tuple(id(w) for w in visible))
        if self.columns==signature:return
        self.columns=signature
        for widget in self.widgets:self.removeWidget(widget)
        for index,widget in enumerate(visible):super().addWidget(widget,index//columns,index%columns)
        self.invalidate()
