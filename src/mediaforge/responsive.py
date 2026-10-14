"""Keep action text readable when the professional workspace gets narrow."""
from PySide6.QtWidgets import QWidget,QGridLayout,QSizePolicy,QLayout
from PySide6.QtCore import QEvent,QTimer

class ActionToolbar(QWidget):
    def __init__(self,buttons):
        super().__init__();self.buttons=buttons;self.columns=0
        self.grid=QGridLayout(self);self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(8)
        self.grid.setSizeConstraint(QLayout.SetMinimumSize)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)
        self.reflow()
    def reflow(self):
        required=sum(button.sizeHint().width() for button in self.buttons)+8*(len(self.buttons)-1)
        columns=4 if self.width()>=required else 2
        if columns==self.columns:return
        self.columns=columns
        for button in self.buttons:self.grid.removeWidget(button)
        for i,button in enumerate(self.buttons):self.grid.addWidget(button,i//columns,i%columns)
        for i in range(4):self.grid.setColumnStretch(i,1 if i<columns else 0)
    def resizeEvent(self,event):super().resizeEvent(event);self.reflow()
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange):QTimer.singleShot(0,self.reflow)
