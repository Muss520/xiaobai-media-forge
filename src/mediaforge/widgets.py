"""Controls that adapt to narrow parameter columns without horizontal overflow."""
from PySide6.QtCore import Qt,QSize,QRect
from PySide6.QtWidgets import QCheckBox as QtCheckBox,QStyle,QStyleOptionButton,QSizePolicy
from PySide6.QtGui import QPainter,QPalette


class WrappedCheckBox(QtCheckBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
    def minimumSizeHint(self):return QSize(80,self.fontMetrics().height()+8)
    def sizeHint(self):
        width=max(100,min(320,self.fontMetrics().horizontalAdvance(self.text())+32))
        return QSize(width,self.heightForWidth(width))
    def hasHeightForWidth(self):return True
    def heightForWidth(self,width):
        return max(28,self.fontMetrics().boundingRect(QRect(0,0,max(40,width-28),1000),Qt.TextWordWrap,self.text()).height()+8)
    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.setMinimumHeight(self.heightForWidth(self.width()))
    def paintEvent(self,event):
        painter=QPainter(self); option=QStyleOptionButton(); self.initStyleOption(option); option.text=''
        self.style().drawControl(QStyle.CE_CheckBox,option,painter,self)
        painter.setPen(self.palette().color(self.foregroundRole()) if self.isEnabled() else self.palette().color(QPalette.Disabled,self.foregroundRole()))
        painter.drawText(self.rect().adjusted(26,2,0,-2),Qt.AlignVCenter|Qt.TextWordWrap,self.text())
