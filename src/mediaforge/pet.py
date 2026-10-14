"""Xiaobai: generated pixel artwork, interruptible gestures and real batch progress."""
import time
from PySide6.QtCore import Qt, QTimer, QPointF, QPoint, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPainterPathStroker, QPen, QColor, QRegion, QImage, QPixmap, QBitmap
from PySide6.QtWidgets import QWidget, QMenu, QVBoxLayout, QLabel


class DesktopCat(QWidget):
    filesDropped = Signal(object)
    activated = Signal()
    positionChanged = Signal()

    def __init__(self, controller):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus)
        self.controller = controller
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.resize(100,110)
        self.state = 'idle'
        self.reduced = False
        self.blink = False
        self.drag_origin = None
        self.mask_frozen=False
        from .paths import app_home,resource_home
        import sys
        from pathlib import Path
        import json
        base=resource_home()/'assets'
        manifest=json.loads((base/'xiaobai-states.json').read_text(encoding='utf-8'))
        from .companion import IdleScheduler
        self.idle_scheduler=IdleScheduler();self.action_specs=manifest.get('action_specs',{})
        self.idle_waiting=True;self.idle_next_action='blink';self.last_idle_voice=time.monotonic();self.last_hover=0.;self.interaction_count=0
        self.actions=manifest['actions']; self.actions['blink']=self.actions['idle']; self.action='idle'; self.action_step=0; self.idle_turn=0
        sheet=QImage(str(base/manifest['image']))
        if sheet.isNull():raise RuntimeError('缺少小白素材，请保持软件目录完整')
        self.base_frames=[]; self.frame_anchors=[]
        for frame in manifest['frames']:
            x,y,width,height=frame['rect']
            if width<=0 or height<=0 or x<0 or y<0 or x+width>sheet.width() or y+height>sheet.height():raise RuntimeError('小白帧边界无效')
            self.base_frames.append(QPixmap.fromImage(sheet.copy(x,y,width,height))); self.frame_anchors.append(frame['anchor'])
        self.frame_index=0
        self.set_scale(controller.preferences.get('scale',3),keep_position=False)
        self.progress_card=PetProgress(self,controller)
        self.progress_timer=QTimer(self)
        self.progress_timer.timeout.connect(self.update_progress)
        self.progress_timer.start(200)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.blink_timer=QTimer(self); self.blink_timer.setSingleShot(True); self.blink_timer.timeout.connect(self.unblink)
        self.state_reset=QTimer(self); self.state_reset.setSingleShot(True); self.state_reset.timeout.connect(self.settle_state)
        self.top_timer=QTimer(self); self.top_timer.timeout.connect(self.ensure_topmost); self.top_timer.start(2000)
        self.click_timer=QTimer(self); self.click_timer.setSingleShot(True); self.click_timer.timeout.connect(self.interact)
        self.hover_timer=QTimer(self);self.hover_timer.setSingleShot(True);self.hover_timer.timeout.connect(self.hover_reaction)
        self.business_resume=QTimer(self);self.business_resume.setSingleShot(True);self.business_resume.timeout.connect(self.unblink)
        self.reaction=QLabel(self,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus)
        self.reaction.setAttribute(Qt.WA_ShowWithoutActivating);self.reaction.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.reaction.setStyleSheet('QLabel { background:#fcfbf7;color:#625b4e;border:1px solid #c5beae;border-radius:6px;padding:5px 9px;font-size:12px; }')
        self.reaction_timer=QTimer(self);self.reaction_timer.setSingleShot(True);self.reaction_timer.timeout.connect(self.reaction.hide)
        self.drag_moved=False; self.double_clicked=False
        from .product import NAME
        self.setToolTip('我是小白 · 拖入文件开始转换 · 单击摸头 · 双击打开'+NAME)

    def apply_mask(self):
        if hasattr(self,'frames') and not self.mask_frozen:
            self.setMask(QRegion(self.frames[self.frame_index].mask()))

    def set_scale(self,scale,keep_position=True):
        scale=scale if type(scale) is int and 2<=scale<=6 else 3
        foot=self.foot_position()
        self.scale=scale
        self.resize(round(100*scale/3),round(110*scale/3))
        self.frames=[]
        for base,anchor in zip(self.base_frames,self.frame_anchors):
            pixels=base.scaled(base.width()*scale,base.height()*scale,Qt.IgnoreAspectRatio,Qt.FastTransformation)
            canvas=QPixmap(self.size()); canvas.fill(Qt.transparent)
            painter=QPainter(canvas)
            painter.drawPixmap(self.width()//2-anchor[0]*scale,self.height()-scale-anchor[1]*scale,pixels)
            painter.end(); self.frames.append(canvas)
        self.apply_mask(); self.update()
        if keep_position:
            self.move(foot.x()-self.width()//2,foot.y()-self.height()+scale)
            self.clamp_position()
        if hasattr(self,'progress_card'):
            self.update_progress()

    def foot_position(self):
        return QPoint(self.x()+self.width()//2,self.y()+self.height()-getattr(self,'scale',3))

    def tick(self):
        if self.reduced or not self.isVisible():self.timer.stop();return
        if self.idle_waiting:
            if not self.can_idle():self.timer.stop();return
            self.play_action(self.idle_next_action)
            if self.controller.preferences.get('idle_voice',False) and time.monotonic()-self.last_idle_voice>=60:
                self.last_idle_voice=time.monotonic();self.controller.sounds.play('meow')
            return
        self.action_step+=1
        sequence=self.actions[self.action]
        if self.action_step>=len(sequence):
            if self.state=='idle':
                self.unblink();return
            else:
                self.action_step=0; self.frame_index=sequence[0]
        else:self.frame_index=sequence[self.action_step]
        self.apply_mask(); self.update()

    def play_action(self,action):
        self.blink_timer.stop()
        self.idle_waiting=False
        if action not in self.actions:action='idle'
        self.action=action; self.action_step=0; self.frame_index=self.actions[action][0]
        self.timer.setInterval(self.action_specs.get(action,{}).get('frame_ms',450 if action in {'sleep','stretch'} else 180 if action=='receiving' else 240))
        if not self.reduced and self.isVisible():self.timer.start()
        else:self.timer.stop()
        if self.reduced:self.frame_index=self.actions[action][len(self.actions[action])//2]
        self.apply_mask(); self.update()

    def interact(self,action='pet'):
        # Companion gestures never replace a conversion or pending request.
        if self.state!='idle' or not self.controller.can_play() or self.controller.play_dialog:return
        self.state_reset.stop();self.interaction_count+=1
        from .companion import ACTION_LABELS
        self.play_action('joy' if action=='meow' else action)
        cue={'pet':'purr' if self.interaction_count%3==0 else 'pet_touch','rub':'rub','snack':'snack','meow':'meow','joy':'joy','sleep':'purr'}.get(action)
        if cue:self.controller.sounds.play(cue)
        self.show_reaction(ACTION_LABELS.get(action,'陪小白玩一会'))
        if self.reduced:
            self.timer.stop(); self.state_reset.start(900)

    def game_action(self,action):
        if self.state!='idle' or not self.controller.can_play() or not self.controller.play_dialog:return
        self.state_reset.stop();self.play_action(action)
        if self.reduced:self.state_reset.start(900)

    def can_idle(self):
        return self.state=='idle' and self.isVisible() and self.controller.can_play() and not self.controller.play_dialog

    def schedule_idle(self):
        self.timer.stop();self.idle_waiting=True
        if self.reduced or not self.can_idle():return
        action,seconds=self.idle_scheduler.next(self.controller.preferences.get('idle_activity','standard'))
        self.idle_next_action='blink' if action=='idle' else action;self.timer.start(seconds*1000)

    def show_reaction(self,text):
        if not self.isVisible():return
        self.reaction.setText(text);self.reaction.adjustSize();rect=self.screen().availableGeometry()
        x=max(rect.left(),min(self.x()+(self.width()-self.reaction.width())//2,rect.right()-self.reaction.width()+1))
        self.reaction.move(x,max(rect.top(),self.y()-self.reaction.height()-6));self.reaction.show();self.reaction_timer.start(1300)

    def enterEvent(self,event):
        super().enterEvent(event)
        if self.controller.preferences.get('hover_reactions',True):self.hover_timer.start(650)

    def leaveEvent(self,event):
        self.hover_timer.stop();super().leaveEvent(event)

    def hover_reaction(self):
        if self.drag_origin is not None or not self.can_idle() or time.monotonic()-self.last_hover<8:return
        self.last_hover=time.monotonic();self.play_action('ears' if self.interaction_count%2 else 'look')
        if self.reduced:self.show_reaction('小白在看你');self.state_reset.start(900)

    def unblink(self):
        self.blink=False
        if self.state=='idle':
            self.action='idle'; self.action_step=0; self.frame_index=0
            self.schedule_idle(); self.apply_mask(); self.update()
        else:self.play_action(self.state if self.state in self.actions else 'idle')
        if self.reduced:self.timer.stop()

    def set_state(self,state):
        self.blink_timer.stop(); self.state_reset.stop();self.business_resume.stop();self.click_timer.stop();self.hover_timer.stop()
        self.reaction.hide();self.reaction_timer.stop()
        self.state='working' if state=='receiving' and self.controller.active_worker else state
        if state!='idle':self.controller.stop_play()
        self.unblink()
        if state=='receiving' and self.controller.active_worker:self.play_action('receiving');self.business_resume.start(750)
        if state in {'complete','failed'}:self.state_reset.start(2600)

    def settle_state(self):
        self.set_state('working' if self.controller.active_worker else 'receiving' if self.controller.dialog or self.controller.loaders else 'idle')

    def ensure_topmost(self):
        import sys
        from PySide6.QtGui import QGuiApplication
        if sys.platform!='win32' or QGuiApplication.platformName()!='windows' or not self.isVisible():return
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32
        user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
        user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
        handle=int(self.winId())
        if not user.GetWindowLongPtrW(handle,-20)&8:
            user.SetWindowPos(handle,wintypes.HWND(-1),0,0,0,0,0x0013)

    def showEvent(self,event):
        super().showEvent(event)
        QTimer.singleShot(0,self.ensure_topmost)
        if hasattr(self,'timer'):self.unblink()

    def hideEvent(self,event):
        if hasattr(self,'timer'):
            for timer in (self.timer,self.hover_timer,self.click_timer,self.business_resume,self.reaction_timer):timer.stop()
            self.reaction.hide();self.controller.stop_play()
            if hasattr(self,'progress_card'):self.progress_card.hide()
        super().hideEvent(event)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.drawPixmap(0,0,self.frames[self.frame_index])

    def update_progress(self):
        # Readers can finish after the idle action timer stopped. Reuse the existing
        # status poll to resume scheduling once every busy gate has been released.
        if hasattr(self,'timer') and self.idle_waiting and not self.timer.isActive() and not self.reduced and self.can_idle():
            self.schedule_idle()
        worker=self.controller.active_worker
        card=self.progress_card
        if not worker or self.controller.exiting or not self.isVisible() or not self.controller.preferences.get('show_progress',True):
            card.hide()
            return
        jobs=worker.jobs
        if not jobs:return
        terminal={'完成','失败','已取消'}
        finished=sum(j.status in terminal for j in jobs)
        current=next((j for j in jobs if j.status not in terminal),jobs[-1])
        index=min(finished+1,len(jobs))
        total=sum(100 if j.status=='完成' else min(99,j.progress) for j in jobs)//len(jobs)
        card.label.setText(f'{index} / {len(jobs)} · '+(f'{total}%' if current.progress>0 or finished else '准备中')+(f' · 等待 {len(self.controller.pending)} 批' if self.controller.pending else ''))
        card.label.setToolTip(current.path.name)
        card.bar.motion.reduced=self.reduced
        if current.status not in terminal and current.progress==0:
            card.bar.setRange(0,0)
        else:
            card.bar.setRange(0,100)
            card.bar.set_progress(total,'失败' if current.status=='失败' else '已取消' if current.status=='已取消' else '完成' if finished==len(jobs) else '处理中')
        rect=self.screen().availableGeometry()
        x=max(rect.left(),min(self.x()-(card.width()-self.width())//2,rect.right()-card.width()+1))
        y=self.y()+self.height()+4
        if y+card.height()>rect.bottom():
            y=self.y()-card.height()-4
        card.move(x,max(rect.top(),y))
        card.show()

    def clamp_position(self):
        screens = __import__('PySide6.QtGui',fromlist=['QGuiApplication']).QGuiApplication.screens()
        screen = next((s for s in screens if s.availableGeometry().contains(self.geometry().center())), self.screen())
        rect = screen.availableGeometry()
        self.move(max(rect.left(),min(self.x(),rect.right()-self.width()+1)),max(rect.top(),min(self.y(),rect.bottom()-self.height()+1)))
        if hasattr(self.controller,'pet'):self.controller.reposition_cards()

    def mousePressEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.mask_frozen=True
            self.drag_origin=event.globalPosition().toPoint()-self.pos()
            self.press_position=event.globalPosition().toPoint(); self.drag_moved=False

    def mouseMoveEvent(self,event):
        from PySide6.QtWidgets import QApplication
        if self.drag_origin is not None and event.buttons() & Qt.LeftButton:
            if (event.globalPosition().toPoint()-self.press_position).manhattanLength()>=QApplication.startDragDistance():self.drag_moved=True
            if self.drag_moved:
                self.click_timer.stop(); self.move(event.globalPosition().toPoint()-self.drag_origin); self.clamp_position()

    def mouseReleaseEvent(self,event):
        from PySide6.QtWidgets import QApplication
        if event.button()!=Qt.LeftButton:return
        self.drag_origin=None
        self.mask_frozen=False; self.apply_mask()
        if self.drag_moved:self.positionChanged.emit()
        elif self.double_clicked:self.double_clicked=False
        else:self.click_timer.start(QApplication.doubleClickInterval())

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.LeftButton:
            self.click_timer.stop(); self.double_clicked=True; self.activated.emit()

    def contextMenuEvent(self,event):
        self.controller.menu().exec(event.globalPos())

    def dragEnterEvent(self,event):
        if event.mimeData().hasUrls() and not self.controller.exiting:
            self.mask_frozen=True
            event.acceptProposedAction()
            self.set_state('receiving')

    def dragLeaveEvent(self,event):
        self.mask_frozen=False
        self.set_state('working' if self.controller.active_worker else 'idle')
        event.accept()

    def dropEvent(self,event):
        self.mask_frozen=False; self.apply_mask()
        from pathlib import Path
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        self.filesDropped.emit(paths)
        event.acceptProposedAction()


class PetProgress(QWidget):
    def __init__(self,pet,controller):
        super().__init__(pet,Qt.Tool|Qt.FramelessWindowHint|Qt.WindowStaysOnTopHint|Qt.WindowDoesNotAcceptFocus)
        from .motion import SmoothProgress
        self.controller=controller
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(controller.window.styleSheet()+'QWidget#petProgress { background:#fcfbf7; border:1px solid #b9b2a2; border-radius:7px; }')
        self.setObjectName('petProgress')
        layout=QVBoxLayout(self)
        layout.setContentsMargins(10,5,10,7)
        layout.setSpacing(3)
        self.label=QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.bar=SmoothProgress()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        layout.addWidget(self.label)
        layout.addWidget(self.bar)
        self.setFixedSize(180,52)
        self.setToolTip('点击查看当前任务和等待批次')
    def mouseReleaseEvent(self,event):
        self.controller.show_tasks()
