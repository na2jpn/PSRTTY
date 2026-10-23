"""Small, sample-based stream-health history. Independent of RF activity."""
from collections import deque
import time
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ..i18n import tr


class IQHealth(QWidget):
    colors=('#20b7d1','#e89c36','#e74e59','#9099a4')

    def __init__(self):
        super().__init__();self.history=deque();self.metrics=QLabel(tr('ry.health_wait'))
        self.metrics.setWordWrap(True)
        self.plot=HealthPlot(self)
        layout=QVBoxLayout(self);layout.setContentsMargins(4,2,4,2);layout.setSpacing(2)
        layout.addWidget(self.metrics);layout.addWidget(self.plot,1)
        legend=QLabel('   '.join('<span style="color:'+color+'">■</span> '+tr(key) for color,key in zip(self.colors,('ry.health_processed','ry.health_pending','ry.health_lost','ry.health_absent'))))
        legend.setWordWrap(True);layout.addWidget(legend)

    def reset(self):
        self.history.clear();self.metrics.setText(tr('ry.health_wait'));self.plot.update()

    def feed(self,stats):
        now=time.monotonic();elapsed=max(.001,stats['interval'])
        incoming=stats['incoming'];processed=stats['processed_time'];lost=stats['lost_time']
        waiting=max(0.,incoming-processed-lost)
        # Each column represents one observation interval, not RF power or a
        # count of decoded stations. Lost durations use source sample positions.
        parts=[processed,waiting,lost,0.]
        if not any(parts):parts=[0.,0.,0.,1.]
        total=sum(parts);parts=[v/total for v in parts]
        self.history.append((now,parts,min(elapsed,1.)))
        while self.history and self.history[0][0]<now-10:self.history.popleft()
        self.metrics.setText(tr('ry.health_metrics').format(rate=stats['input_sps']/1e6,
            queue=stats['queue_ms'],loss=stats['loss_percent']))
        self.plot.update()


class HealthPlot(QWidget):
    def __init__(self,owner):
        super().__init__();self.owner=owner;self.setMinimumHeight(65)
        self.setAccessibleName(tr('ry.health_graph'))

    def paintEvent(self,event):
        p=QPainter(self);p.fillRect(self.rect(),self.palette().base());p.setPen(self.palette().text().color())
        fm=self.fontMetrics();left=fm.horizontalAdvance('100%')+8;top=3;bottom=self.height()-fm.height()-5
        width=max(1,self.width()-left-5);height=max(1,bottom-top);now=time.monotonic()
        for value in (0,100):p.drawText(QRectF(0,top+(1-value/100)*height-fm.height()/2,left-5,fm.height()),Qt.AlignRight|Qt.AlignVCenter,str(value)+'%')
        grid=self.palette().mid().color();p.setPen(QPen(grid,1));p.drawLine(left,bottom,self.width()-5,bottom)
        for stamp,parts,duration in self.owner.history:
            x=left+width*(1-(now-stamp)/10);bar=max(1,width*duration/10);y=bottom
            for part,color in zip(parts,self.owner.colors):
                h=height*part;y-=h
                if h:p.fillRect(QRectF(max(left,x-bar),y,min(bar,width),h),QColor(color))
        p.setPen(self.palette().text().color())
        p.drawText(left,self.height()-2,tr('ry.health_ago'))
        label=tr('ry.health_now');p.drawText(self.width()-5-fm.horizontalAdvance(label),self.height()-2,label)
