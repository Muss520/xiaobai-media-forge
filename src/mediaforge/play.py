"""Small, local-only play sessions. No global hooks or media-state mutation."""
import math,time
from PySide6.QtCore import Qt,QTimer,QPointF,Signal
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import QDialog,QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QLayout


class PlaySession:
    def __init__(self,mode):
        self.mode=mode;self.score=0;self.elapsed=0.;self.active=False;self.paused=False;self.finished=False
        self.ball_elapsed=None;self.target=False

    @property
    def remaining(self):return max(0.,30-self.elapsed)

    @property
    def catchable(self):return self.ball_elapsed is not None and .6<=self.ball_elapsed<=1.15

    def start(self):
        self.score=0;self.elapsed=0.;self.active=True;self.paused=False;self.finished=False;self.ball_elapsed=None;self.target=False

    def pause(self):
        if self.active and not self.finished:self.paused=not self.paused

    def advance(self,seconds):
        if not self.active or self.paused or self.finished:return None
        self.elapsed+=max(0,seconds);event=None
        if self.mode=='ball':
            if self.ball_elapsed is not None:
                before=self.ball_elapsed;self.ball_elapsed+=max(0,seconds)
                if before<.45<=self.ball_elapsed:event='bounce'
                if self.ball_elapsed>1.4:self.ball_elapsed=None;event='miss'
            if self.elapsed>=30:self.elapsed=30;self.active=False;self.finished=True;return 'game_finish'
        return event

    def click(self):
        if not self.active or self.paused or self.finished:return None
        if self.mode=='wand':
            if self.target:self.score+=1;return 'catch'
            return 'miss'
        if self.ball_elapsed is None:self.ball_elapsed=0.;return 'throw'
        if self.catchable:self.score+=1;self.ball_elapsed=None;return 'catch'
        self.ball_elapsed=None;return 'miss'


class PlayCanvas(QWidget):
    clicked=Signal()
    moved=Signal()

    def __init__(self,dialog):
        super().__init__(dialog);self.dialog=dialog;self.pointer=QPointF(70,50)
        self.setMinimumSize(240,170);self.setMouseTracking(True);self.setObjectName('playCanvas')
        self.setAccessibleName('玩具互动区');self.setFocusPolicy(Qt.StrongFocus)

    def target_point(self):return QPointF(self.width()*.66,self.height()*.63)

    def update_target(self,point):
        self.pointer=QPointF(point)
        target=self.target_point();self.dialog.session.target=math.hypot(point.x()-target.x(),point.y()-target.y())<=38
        self.update()

    def mouseMoveEvent(self,event):self.update_target(event.position());self.moved.emit()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:self.update_target(event.position());self.clicked.emit()

    def keyPressEvent(self,event):
        if event.key() in (Qt.Key_Space,Qt.Key_Return):
            self.dialog.session.target=True;self.clicked.emit();event.accept()
        else:super().keyPressEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(),QColor('#fcfbf7'));target=self.target_point()
        session=self.dialog.session;ready=session.target if session.mode=='wand' else session.catchable
        painter.setPen(QPen(QColor('#958b76' if ready else '#d4cebf'),2,Qt.DashLine))
        painter.setBrush(QColor('#e9e3d5' if ready else '#f6f3eb'));painter.drawEllipse(target,38,38)
        if session.mode=='wand':
            point=self.pointer;painter.setPen(QPen(QColor('#625b4e'),2))
            painter.drawLine(QPointF(24,18),point);painter.setBrush(QColor('#b8af99'))
            painter.drawEllipse(point,8,14);painter.drawLine(point-QPointF(0,10),point+QPointF(0,10))
        else:
            elapsed=session.ball_elapsed
            phase=min(1,(elapsed or 0)/1.4)
            point=target if self.dialog.controller.pet.reduced or elapsed is None else QPointF(28+(target.x()-28)*phase,self.height()-26-math.sin(phase*math.pi)*max(40,self.height()-65))
            painter.setPen(QPen(QColor('#625b4e'),2));painter.setBrush(QColor('#c9bfa6'));painter.drawEllipse(point,12,12)
        painter.end()


class PlayDialog(QDialog):
    def __init__(self,controller,mode):
        super().__init__(controller.window,Qt.Tool|Qt.WindowStaysOnTopHint|Qt.WindowCloseButtonHint)
        self.controller=controller;self.session=PlaySession(mode);self.last_tick=time.monotonic();self.last_look=0
        self.setAttribute(Qt.WA_DeleteOnClose);self.setWindowTitle('小白游乐场 · '+('逗猫棒' if mode=='wand' else '抛接小球'))
        self.setStyleSheet(controller.window.styleSheet())
        root=QVBoxLayout(self);root.setContentsMargins(16,16,16,16);root.setSpacing(10);root.setSizeConstraint(QLayout.SetMinimumSize)
        title=QLabel('陪小白玩一会');title.setObjectName('sectionTitle');root.addWidget(title)
        self.help=QLabel('移动逗猫棒到虚线圈内，再点击让小白扑抓。也可按空格互动。' if mode=='wand' else '点击抛球，出现“现在接球”时再点一次；每轮30秒。')
        self.help.setWordWrap(True);root.addWidget(self.help)
        self.canvas=PlayCanvas(self);self.canvas.clicked.connect(self.play_click);self.canvas.moved.connect(self.look);root.addWidget(self.canvas,1)
        self.status=QLabel('点击开始，小白准备好啦');self.status.setWordWrap(True);root.addWidget(self.status)
        row=QHBoxLayout();self.start_button=QPushButton('开始');self.start_button.setObjectName('primary');self.start_button.clicked.connect(self.start)
        self.pause_button=QPushButton('暂停');self.pause_button.clicked.connect(self.pause)
        self.end_button=QPushButton('结束');self.end_button.clicked.connect(self.close)
        for button in (self.start_button,self.pause_button,self.end_button):row.addWidget(button)
        root.addLayout(row)
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick)
        self.resize(440,440);self.setMinimumWidth(320);self.refresh();self.fit_text();self.adjustSize();self.reposition()

    def fit_text(self):
        width=max(240,self.width()-32)
        self.help.setMinimumHeight(max(self.help.fontMetrics().height(),self.help.heightForWidth(width)))
        self.status.setMinimumHeight(max(self.status.fontMetrics().height()*2+4,self.status.heightForWidth(width)))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'status'):self.fit_text()

    def reposition(self):
        pet=self.controller.pet;rect=pet.screen().availableGeometry()
        x=pet.x()-self.width()-12
        if x<rect.left():x=pet.x()+pet.width()+12
        self.move(max(rect.left(),min(x,rect.right()-self.width()+1)),max(rect.top(),min(pet.y()+pet.height()-self.height(),rect.bottom()-self.height()+1)))

    def start(self):
        if not self.check_available():return
        self.session.start();self.last_tick=time.monotonic();self.timer.start(100 if self.controller.pet.reduced else 33);self.refresh()
        self.controller.pet.game_action('joy')

    def pause(self):
        if not self.check_available():return
        self.session.pause()
        if self.session.paused:self.timer.stop();self.controller.sounds.stop_group('game')
        elif self.session.active:self.last_tick=time.monotonic();self.timer.start(100 if self.controller.pet.reduced else 33)
        self.refresh()

    def look(self):
        if not self.check_available():return
        if self.session.active and not self.session.paused and time.monotonic()-self.last_look>.5:
            self.last_look=time.monotonic();self.controller.pet.game_action('look');self.controller.sounds.play('wand')

    def play_click(self):
        if not self.check_available():return
        self.react(self.session.click());self.refresh()

    def check_available(self):
        if self.controller.can_play() and self.controller.pet.isVisible() and self.controller.preferences.get('games_enabled',True):return True
        self.controller.stop_play(self)
        return False

    def react(self,event):
        if not event:return
        self.controller.sounds.play(event)
        self.controller.pet.game_action({'catch':'pounce' if self.session.mode=='wand' else 'catch','throw':'look','miss':'shy','game_finish':'joy','bounce':'ears'}.get(event,'look'))
        self.status.setText({'catch':'抓到啦！','throw':'小球抛出啦，等待接球提示…','miss':'差一点，再试一次','game_finish':'本轮结束，做得很棒','bounce':'小球弹起来啦'}.get(event,''))

    def tick(self):
        if not self.check_available():return
        now=time.monotonic();delta=now-self.last_tick;self.last_tick=now
        self.react(self.session.advance(delta))
        if self.session.finished:self.timer.stop()
        self.refresh()

    def refresh(self):
        session=self.session
        self.pause_button.setEnabled(session.active);self.pause_button.setText('继续' if session.paused else '暂停')
        self.start_button.setText('重玩' if session.active or session.finished else '开始')
        if session.active and not session.paused:
            prefix=f'剩余 {math.ceil(session.remaining)} 秒 · ' if session.mode=='ball' else ''
            self.status.setText(prefix+f'本轮 {session.score} 次'+(' · 现在接球！' if session.mode=='ball' and session.catchable else ' · 点击抛球' if session.mode=='ball' and session.ball_elapsed is None else ' · 移到圈内点击' if session.mode=='wand' else ' · 等待接球提示'))
        elif session.paused:self.status.setText(f'已暂停 · 本轮 {session.score} 次')
        elif session.finished:self.status.setText(f'本轮完成 · 接住 {session.score} 次')
        self.fit_text()
        self.canvas.update()

    def closeEvent(self,event):
        self.timer.stop();self.controller.sounds.stop_group('game');self.session.active=False
        super().closeEvent(event)
