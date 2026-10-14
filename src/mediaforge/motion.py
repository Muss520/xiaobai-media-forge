"""Interruptible, parent-owned Qt transitions. No animation drives task state."""
from PySide6.QtCore import QPropertyAnimation, QVariantAnimation, QEasingCurve, QEvent, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QProgressBar, QGraphicsOpacityEffect, QPushButton, QLabel
from shiboken6 import isValid


class Motion(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.reduced = False
        self.animations = {}

    def animate(self, widget, property_name, end, finish=None):
        key = (widget, property_name)
        old = self.animations.pop(key, None)
        if old:
            old.stop()
            old.deleteLater()
        if self.reduced:
            widget.setProperty(property_name.decode(), end)
            if finish:
                finish()
            return
        animation = QPropertyAnimation(widget, property_name, self)
        animation.setDuration(180)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.setStartValue(widget.property(property_name.decode()))
        animation.setEndValue(end)
        self.animations[key] = animation

        def done():
            if self.animations.get(key) is animation:
                self.animations.pop(key)
                if finish:
                    finish()
            animation.deleteLater()
        animation.finished.connect(done)
        animation.start()

    def set_reduced(self, reduced):
        self.reduced = reduced
        if reduced:
            # Finish to the latest requested state, including collapse cleanup.
            for animation in list(self.animations.values()):
                animation.setCurrentTime(animation.duration())

    def fade(self, widget):
        # Never rasterize a whole interactive page: nested effects can leave
        # child controls blank after native Windows repaint/hover transitions.
        if not isinstance(widget, QLabel):
            return
        if self.reduced:
            return
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
        effect.setOpacity(.55)
        self.animate(effect, b'opacity', 1.)

    def watch_buttons(self, root):
        for button in root.findChildren(QPushButton):
            button.installEventFilter(self)
            if not button.property('motionWatched'):
                button.setProperty('motionWatched',True)
                button.destroyed.connect(lambda *args,b=button:self.cancel_target(b))

    def cancel_target(self,target):
        for key in list(self.animations):
            if key[0] is target:
                animation=self.animations.pop(key)
                if isValid(animation):
                    animation.stop(); animation.deleteLater()

    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and event.type() in (QEvent.Enter, QEvent.Leave) and obj.isEnabled():
            key=(obj,b'hover')
            old=self.animations.pop(key,None)
            if old:
                old.stop(); old.deleteLater()
            primary=obj.objectName()=='primary' or obj.isCheckable() and obj.isChecked()
            normal=QColor('#3c3b35' if primary else '#faf9f5')
            hover=QColor('#55534b' if primary else '#eeece4')
            target=hover if event.type()==QEvent.Enter else normal
            if self.reduced:
                obj.setStyleSheet('' if event.type()==QEvent.Leave else f'background-color:{target.name()};')
            else:
                animation=QVariantAnimation(self)
                animation.setDuration(180); animation.setEasingCurve(QEasingCurve.OutCubic)
                animation.setStartValue(obj.property('hoverColor') or normal)
                animation.setEndValue(target)
                def update(color):
                    if not isValid(obj):return
                    obj.setProperty('hoverColor',color)
                    obj.setStyleSheet(f'background-color:{color.name()};')
                animation.valueChanged.connect(update)
                def done():
                    if self.animations.get(key) is animation:
                        self.animations.pop(key,None)
                        if isValid(obj):obj.setStyleSheet('')
                    animation.deleteLater()
                animation.finished.connect(done)
                self.animations[key]=animation
                animation.start()
        elif isinstance(obj,QPushButton) and event.type()==QEvent.EnabledChange:
            old=self.animations.pop((obj,b'hover'),None)
            if old:
                old.stop(); old.deleteLater()
            obj.setStyleSheet('')
        return False


class SmoothProgress(QProgressBar):
    def __init__(self):
        super().__init__()
        self.motion = Motion(self)
        self.setRange(0, 100)
        self.setValue(0)

    def set_progress(self, value, status):
        value = min(100 if status == '完成' else 99, max(0, value))
        if status in {'完成', '失败', '取消', '已取消', '待处理', '待读取'}:
            reduced = self.motion.reduced
            self.motion.set_reduced(True)
            self.setValue(value)
            self.motion.reduced = reduced
        else:
            self.motion.animate(self, b'value', value)


class TaskProgress(SmoothProgress):
    """One centered status/progress column; no cell widget pinned to the top."""
    def __init__(self):
        super().__init__(); self.status='待处理'
    def set_progress(self,value,status):
        self.status=status; self.setToolTip(status)
        super().set_progress(value,status); self.update()
    def paintEvent(self,event):
        from PySide6.QtGui import QPainter,QColor
        from PySide6.QtCore import QRectF,Qt
        painter=QPainter(self); painter.setRenderHint(QPainter.Antialiasing)
        width=max(4,self.width()-20);text_height=self.fontMetrics().height()+4; top=max(2,(self.height()-text_height-14)/2)
        rect=QRectF(10,top,width,6)
        painter.setPen(Qt.NoPen); painter.setBrush(QColor('#e7e2d6')); painter.drawRoundedRect(rect,3,3)
        painter.setBrush(QColor('#8d9c86' if self.status=='完成' else '#b77b69' if self.status=='失败' else '#9a9381'))
        fill=QRectF(rect); fill.setWidth(width*self.value()/100); painter.drawRoundedRect(fill,3,3)
        painter.setPen(QColor('#676155')); painter.drawText(QRectF(4,top+10,self.width()-8,text_height),Qt.AlignCenter,f'{self.status} · {self.value()}%')
