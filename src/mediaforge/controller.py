"""Desktop lifecycle and one sequential queue shared by window and cat."""
import hashlib
import threading
from collections import deque
from pathlib import Path
from PySide6.QtCore import QObject, QThread, Signal, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from .paths import runtime_home,resource_home
from .models import Job, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .workflow import job_kind
from .queue import BatchWorker


class ImportWorker(QThread):
    ready = Signal(object,object,str)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.cancel_event = threading.Event()

    def run(self):
        from .probe import probe
        from .live import match_pairs, inspect_live
        from .previews import thumbnail
        jobs, previews, skipped = [], {}, 0
        paths = list(dict.fromkeys(Path(p).absolute() for p in self.paths))
        accepted = []
        for path in paths:
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | {'.livp'}:
                accepted.append(path)
            else:
                skipped += 1
        pairs, remaining = [], accepted
        try:
            if any(p.suffix.lower()=='.mov' for p in accepted) and any(p.suffix.lower() in {'.heic','.jpg','.jpeg','.heif'} for p in accepted):
                pairs, remaining = match_pairs(accepted,self.cancel_event)
            jobs = [Job(photo,inputs=(photo,video)) for photo,video in pairs] + [Job(p) for p in remaining]
            for job in jobs:
                if self.cancel_event.is_set():
                    return
                try:
                    job.info = inspect_live(job.path,job.inputs,self.cancel_event) if job_kind(job)=='live' else probe(job.path)
                    job.status = '待处理'
                    try:
                        previews[job.id] = thumbnail(job)
                    except Exception:
                        pass
                except Exception as error:
                    job.status, job.error = '失败', str(error)
            if not self.cancel_event.is_set():
                self.ready.emit(jobs,previews,f'跳过 {skipped} 个非媒体文件/文件夹' if skipped else '')
        except Exception as error:
            if not self.cancel_event.is_set():
                self.ready.emit([],{},str(error))


class AppController(QObject):
    def __init__(self, app, settings_path=None, quit_application=True):
        super().__init__()
        from .window import MainWindow
        from .pet import DesktopCat
        self.app = app
        self.quit_application = quit_application
        app.setQuitOnLastWindowClosed(False)
        self.window = MainWindow(settings_path)
        self.window.controller = self
        from .preferences import normalize_desktop
        self.preferences = normalize_desktop(self.window.desktop_preferences)
        from .sounds import SoundBank
        self.sounds=SoundBank(self.preferences,self)
        self.settings_dialog=None
        self.exiting = False
        self.pending = deque()
        self.incoming = deque()
        self.loaders = []
        self.active_worker = None
        self.dialog = None
        self.feedback = None
        self.checks = []
        self.return_dialogs = []
        self.play_dialog=None
        self.pet = DesktopCat(self)
        self.pet.filesDropped.connect(self.import_files)
        self.pet.activated.connect(self.show_window)
        self.pet.positionChanged.connect(self.save_position)
        self.pet.reduced = self.window.reduce_motion.isChecked()
        self.window.reduce_motion.toggled.connect(self.set_motion)
        position = self.preferences.get('position')
        if isinstance(position,list) and len(position)==2 and all(isinstance(i,int) for i in position):
            self.pet.move(*position)
        else:
            rect = self.pet.screen().availableGeometry()
            self.pet.move(rect.right()-130,rect.bottom()-140)
        self.pet.clamp_position()
        if self.preferences.get('visible',True):
            self.pet.show()
        self.tray = QSystemTrayIcon(self.window.windowIcon() if not self.window.windowIcon().isNull() else QIcon(str(resource_home()/'assets/mediaforge.ico')),self)
        from .product import NAME
        self.tray.setToolTip(NAME+' · 关窗后台驻留，右键彻底退出')
        self.tray.setContextMenu(self.menu())
        self.tray.activated.connect(lambda reason: self.show_window() if reason == QSystemTrayIcon.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        def watch_screen(screen):
            screen.availableGeometryChanged.connect(lambda rect: self.pet.clamp_position())
            self.pet.clamp_position()
        for screen in self.app.screens():
            watch_screen(screen)
        self.app.screenAdded.connect(watch_screen)
        self.app.screenRemoved.connect(lambda screen: self.pet.clamp_position())

    def menu(self):
        menu = QMenu(self.window)
        menu.setStyleSheet(self.window.styleSheet())
        from .product import NAME
        menu.addAction('打开'+NAME,self.show_window)
        menu.addAction('查看任务',self.show_tasks)
        menu.addAction('设置',self.show_settings)
        gestures=menu.addMenu('和小白互动')
        for label,action in [('摸摸头','pet'),('蹭蹭手','rub'),('喂零食','snack'),('叫一声','meow'),('开心小跳','joy'),('摇尾巴','tail'),('伸个懒腰','stretch'),('休息一会','sleep')]:
            item=gestures.addAction(label,lambda checked=False,a=action:self.pet.interact(a));item.setEnabled(self.can_play() and self.play_dialog is None)
        play=menu.addMenu('小白游乐场')
        for label,mode in [('逗猫棒','wand'),('抛接小球 · 30秒','ball')]:
            item=play.addAction(label,lambda checked=False,m=mode:self.open_play(m));item.setEnabled(self.can_play() and self.pet.isVisible() and self.preferences.get('games_enabled',True))
        menu.addSeparator()
        toggle=menu.addAction('隐藏小白' if self.pet.isVisible() else '显示小白',self.toggle_pet)
        cancel=menu.addAction('取消所有处理',self.cancel_all)
        def update():
            toggle.setText('隐藏小白' if self.pet.isVisible() else '显示小白')
            cancel.setEnabled(bool(self.active_worker or self.pending or self.checks))
            for item in gestures.actions():item.setEnabled(self.can_play() and self.pet.isVisible() and self.play_dialog is None)
            for item in play.actions():item.setEnabled(self.can_play() and self.pet.isVisible() and self.preferences.get('games_enabled',True))
        menu.aboutToShow.connect(update)
        update()
        menu.addSeparator()
        menu.addAction('彻底退出',self.request_exit)
        return menu

    def can_play(self):
        return getattr(getattr(self,'pet',None),'state','idle')=='idle' and not (self.exiting or self.active_worker or self.window.busy or getattr(self.window,'preparing',False)
                    or self.dialog or self.loaders or self.window.inspectors or self.checks or self.pending or self.incoming
                    or getattr(getattr(self.window,'information_page',None),'loaders',[]))

    def open_play(self,mode='wand'):
        if not self.can_play() or not self.pet.isVisible() or not self.preferences.get('games_enabled',True):return
        if self.play_dialog:
            self.play_dialog.raise_();self.play_dialog.activateWindow();return
        from .play import PlayDialog
        self.pet.timer.stop();self.pet.state_reset.stop();self.pet.reaction.hide()
        dialog=PlayDialog(self,mode);self.play_dialog=dialog
        dialog.finished.connect(lambda result,d=dialog:self.stop_play(d))
        self.window.motion.watch_buttons(dialog);dialog.show();dialog.reposition()

    def stop_play(self,expected=None):
        dialog=self.play_dialog
        if expected is not None and expected is not dialog:return
        self.play_dialog=None
        if dialog:
            from shiboken6 import isValid
            if isValid(dialog):
                dialog.timer.stop()
                if dialog.isVisible():dialog.close()
            self.sounds.stop_group('game')
            if hasattr(self,'pet'):self.pet.unblink()

    def show_settings(self):
        if self.exiting:return
        from shiboken6 import isValid
        if self.settings_dialog is not None and isValid(self.settings_dialog):
            self.settings_dialog.sync(); self.settings_dialog.showNormal()
            self.settings_dialog.raise_(); self.settings_dialog.activateWindow(); return
        from .settings import SettingsDialog
        card=SettingsDialog(self); self.settings_dialog=card
        def closed(*args):
            if self.settings_dialog is card:self.settings_dialog=None
        card.finished.connect(closed); card.destroyed.connect(closed)
        self.window.motion.watch_buttons(card)
        card.show(); card.raise_(); card.activateWindow()

    def apply_appearance(self):
        self.window.apply_appearance()
        from shiboken6 import isValid
        cards=[self.settings_dialog,self.dialog,self.feedback,*self.return_dialogs,*self.checks]
        cards.append(self.play_dialog)
        for card in cards:
            if card is not None and isValid(card):card.setStyleSheet(self.window.styleSheet())
        # Keep compact progress independent of the chosen application font size.
        self.pet.progress_card.setStyleSheet(self.window.styleSheet()+'QWidget#petProgress { background:#fcfbf7; border:1px solid #b9b2a2; border-radius:7px; } QLabel { font-size:12px; }')
        if self.play_dialog:self.play_dialog.fit_text();self.play_dialog.reposition()

    def reposition_cards(self):
        from shiboken6 import isValid
        rect=self.pet.screen().availableGeometry()
        if self.play_dialog:self.play_dialog.reposition()
        for card in [self.dialog,self.feedback,*self.checks,*self.return_dialogs]:
            if card is not None and isValid(card) and card.isVisible():
                card.move(max(rect.left(),min(self.pet.x()-card.width()-10,rect.right()-card.width()+1)),
                          max(rect.top(),min(self.pet.y()+self.pet.height()-card.height(),rect.bottom()-card.height()+1)))
        self.pet.update_progress()

    def show_tasks(self):
        from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton
        from PySide6.QtCore import Qt
        card=QDialog(self.window,Qt.Tool|Qt.WindowStaysOnTopHint)
        card.setAttribute(Qt.WA_DeleteOnClose)
        card.setWindowTitle('小白任务')
        card.setStyleSheet(self.window.styleSheet())
        layout=QVBoxLayout(card)
        label=QLabel()
        label.setWordWrap(True)
        layout.addWidget(label)
        def refresh():
            worker=self.active_worker
            current=next((j for j in worker.jobs if j.status not in {'完成','失败','已取消'}),None) if worker else None
            label.setText(('当前：'+current.path.name+'\n'+current.status+f' {current.progress}%' if current else '当前没有正在处理的文件')+f'\n等待批次：{len(self.pending)}')
        timer=QTimer(card)
        timer.timeout.connect(refresh)
        timer.start(200)
        refresh()
        for text,callback in [('打开主界面',self.show_window),('取消所有处理',self.cancel_all),('收起',card.close)]:
            button=QPushButton(text)
            button.clicked.connect(callback)
            layout.addWidget(button)
        self.return_dialogs.append(card)
        card.destroyed.connect(lambda:self.return_dialogs.remove(card) if card in self.return_dialogs else None)
        card.resize(340,220)
        rect=self.pet.screen().availableGeometry()
        card.move(max(rect.left(),min(self.pet.x()-350,rect.right()-340)),max(rect.top(),min(self.pet.y()-230,rect.bottom()-220)))
        card.show()

    def show_window(self):
        if not self.exiting:
            self.window.showNormal()
            self.window.raise_()
            self.window.activateWindow()

    def toggle_pet(self):
        shown = not self.pet.isVisible()
        self.pet.setVisible(shown)
        self.preferences['visible'] = shown
        self.pet.update_progress()
        self.window.save_settings()
        if self.settings_dialog:self.settings_dialog.sync()

    def save_position(self):
        self.preferences['position'] = [self.pet.x(),self.pet.y()]
        self.window.save_settings()

    def set_motion(self,reduced):
        self.pet.reduced = reduced
        self.pet.unblink()
        if self.play_dialog:self.play_dialog.timer.setInterval(100 if reduced else 33)

    def import_files(self,paths):
        if self.exiting:
            return
        self.stop_play()
        self.pet.set_state('receiving')
        worker = ImportWorker(paths)
        self.loaders.append(worker)
        worker.ready.connect(self.imported)
        worker.finished.connect(lambda w=worker: self.loader_finished(w))
        worker.start()

    def loader_finished(self,worker):
        self.loaders.remove(worker)
        worker.deleteLater()

    def imported(self,jobs,previews,warning):
        if self.exiting:
            return
        from PySide6.QtGui import QPixmap
        for id,image in previews.items():
            self.window.thumbnails[id] = QIcon(QPixmap.fromImage(image))
        if jobs:
            self.sounds.play('receive')
            self.incoming.append(jobs)
            self.open_next_dialog()
        if warning or not jobs:
            self.tray.showMessage('小白提示',warning or '没有可转换的媒体文件')
        if not jobs:
            self.pet.set_state('working' if self.active_worker else 'idle')

    def open_next_dialog(self):
        if self.dialog is not None or not self.incoming or self.exiting:
            return
        from .simple import QuickDialog
        if self.feedback:
            self.feedback.close()
            self.feedback = None
        self.dialog = QuickDialog(self.incoming.popleft(),self.preferences.get('quick',{}))
        self.dialog.folder_prefix=self.preferences.get('folder_prefix','转换结果')
        self.dialog.setStyleSheet(self.window.styleSheet())
        self.dialog.confirmed.connect(self.confirm_quick)
        dialog=self.dialog
        dialog.finished.connect(lambda result,d=dialog:self.dialog_closed(d))
        dialog.destroyed.connect(lambda *args,d=dialog:self.dialog_closed(d))
        self.dialog.show()
        self.pet.set_state('receiving')
        self.window.motion.fade(self.dialog)
        rect = self.pet.screen().availableGeometry()
        self.dialog.move(max(rect.left(),min(self.pet.x()-self.dialog.width()-10,rect.right()-self.dialog.width())),max(rect.top(),min(self.pet.y()-self.dialog.height()+70,rect.bottom()-self.dialog.height())))

    def dialog_closed(self,dialog):
        if self.dialog is not dialog:
            return
        self.dialog = None
        QTimer.singleShot(0,self.open_next_dialog)
        self.pet.set_state('working' if self.active_worker else 'idle')

    def confirm_quick(self,request):
        form = self.dialog.form
        self.preferences['quick'] = {kind:{'format':panel.format.currentData(),'preset':panel.presets.currentData(),**({'mode':panel.mode.currentData(),'video_format':panel.video_output.currentData()} if kind=='live' else {})} for kind,panel in form.store.panels.items()}
        if self.settings_dialog:self.settings_dialog.sync_quick()
        self.window.save_settings()
        self.submit_request(request)

    def submit_request(self,request):
        if self.exiting:
            return
        self.stop_play()
        from .preflight import RequestCheck
        check=RequestCheck(request,self)
        self.checks.append(check)
        self.window.preparing=True
        self.window.refresh_controls()
        def finished():
            if check in self.checks:
                self.checks.remove(check)
            self.window.preparing=bool(self.checks)
            from shiboken6 import isValid
            if isValid(self.window) and isValid(self.window.simple_page):
                self.window.refresh_controls()
        check.destroyed.connect(finished)
        check.show()
        rect=self.pet.screen().availableGeometry()
        check.move(max(rect.left(),min(self.pet.x()-check.width()-10,rect.right()-check.width())),max(rect.top(),min(self.pet.y()-check.height(),rect.bottom()-check.height())))

    def enqueue(self,request):
        if self.exiting:
            return
        self.stop_play()
        for item in request.items:
            job = item.job
            if request.origin=='information':
                job.status,job.parameters='排队中',item.parameters
                continue
            kind = job_kind(job)
            if all(j.id != job.id for j in self.window.jobs[kind]):
                self.window.jobs[kind].append(job)
            job.status,job.parameters = '排队中',item.parameters
            self.window.render_job(kind,job)
        self.pending.append(request)
        self.run_next()

    def run_next(self):
        if self.active_worker or not self.pending or self.exiting:
            return
        self.active_worker = BatchWorker.from_request(self.pending.popleft())
        self.window.worker = self.active_worker
        self.window.busy = True
        if self.active_worker.request.origin!='information':self.window.simple_page.batch_jobs=list(self.active_worker.jobs)
        self.sounds.play('start')
        self.pet.set_state('working')
        self.active_worker.updated.connect(self.window.job_updated)
        self.active_worker.updated.connect(lambda *args:self.pet.update_progress())
        self.active_worker.summary.connect(self.summary)
        self.active_worker.finished.connect(self.finished)
        self.window.refresh_controls()
        self.active_worker.start()

    def summary(self,completed,failed,cancelled):
        self.window.batch_summary(completed,failed,cancelled)
        self.pet.set_state('failed' if failed else 'complete')
        self.sounds.play('failed' if failed else 'complete')
        from .product import NAME
        if self.preferences.get('notifications',True):self.tray.showMessage(NAME,f'完成 {completed}，失败 {failed}，取消 {cancelled} · 双击小猫查看结果')
        if self.preferences.get('open_results',False):
            from PySide6.QtCore import QUrl
            from PySide6.QtGui import QDesktopServices
            folders={j.output if j.output.is_dir() else j.output.parent for j in self.active_worker.jobs if j.status=='完成' and j.output}
            for folder in folders:QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        if not self.exiting and (self.active_worker.request.origin == 'pet' or failed):
            self.show_result(self.active_worker.request,completed,failed,cancelled)

    def show_result(self,request,completed,failed,cancelled):
        from PySide6.QtCore import Qt, QUrl
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
        from .workflow import make_request
        if self.feedback:
            self.feedback.close()
        card=QDialog(self.window,Qt.Tool|Qt.WindowStaysOnTopHint)
        card.setAttribute(Qt.WA_ShowWithoutActivating)
        card.setAttribute(Qt.WA_DeleteOnClose)
        card.destroyed.connect(lambda: setattr(self,'feedback',None) if self.feedback is card else None)
        card.setWindowTitle('小白处理结果')
        card.setStyleSheet(self.window.styleSheet())
        layout=QVBoxLayout(card)
        layout.addWidget(QLabel(f'完成 {completed} · 失败 {failed} · 取消 {cancelled}'))
        folders=list(dict.fromkeys(item.job.output if item.job.output.is_dir() else item.job.output.parent for item in request.items if item.job.status=='完成' and item.job.output))
        if folders:
            button=QPushButton('打开结果')
            button.setObjectName('primary')
            button.clicked.connect(lambda: [QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder))) for folder in folders])
            layout.addWidget(button)
        failed_jobs=[item.job for item in request.items if item.job.status=='失败']
        if failed_jobs:
            details=QLabel('\n'.join(f'{job.path.name}：{job.error}' for job in failed_jobs))
            details.setWordWrap(True)
            details.hide()
            detail_button=QPushButton('查看失败原因')
            detail_button.clicked.connect(lambda: details.setVisible(not details.isVisible()))
            layout.addWidget(detail_button)
            layout.addWidget(details)
            retry=QPushButton('按本次需求重试')
            def retry_failed():
                from .workflow import retry_request
                self.enqueue(retry_request(request,prefix=self.preferences.get('folder_prefix','转换结果')))
                card.close()
            retry.clicked.connect(retry_failed)
            layout.addWidget(retry)
            if any(job.error_category=='target_size' for job in failed_jobs):
                from dataclasses import replace
                retry_size=QPushButton('取消体积上限并重试')
                def without_size():
                    from .workflow import retry_request
                    from .models import VideoOptions,LiveOptions
                    def transform(value):
                        if isinstance(value,LiveOptions):
                            return replace(value,target_bytes=0,image=replace(value.image,target_bytes=0),video=replace(value.video,target_bytes=0,mode='quality'))
                        return replace(value,target_bytes=0,**({'mode':'quality'} if isinstance(value,VideoOptions) else {}))
                    self.submit_request(retry_request(request,transform,prefix=self.preferences.get('folder_prefix','转换结果')))
                    card.close()
                retry_size.clicked.connect(without_size)
                layout.addWidget(retry_size)
            from .models import VideoOptions,LiveOptions
            if any(isinstance(item.parameters,VideoOptions) and item.parameters.encoder!='cpu' or isinstance(item.parameters,LiveOptions) and item.parameters.mode=='video' and item.parameters.video.encoder!='cpu' for item in request.items if item.job in failed_jobs):
                cpu=QPushButton('改用 CPU 重试')
                def cpu_retry():
                    from dataclasses import replace
                    from .workflow import retry_request
                    def transform(value):
                        return replace(value,encoder='cpu') if isinstance(value,VideoOptions) else replace(value,video=replace(value.video,encoder='cpu')) if isinstance(value,LiveOptions) else value
                    self.submit_request(retry_request(request,transform,prefix=self.preferences.get('folder_prefix','转换结果')))
                    card.close()
                cpu.clicked.connect(cpu_retry)
                layout.addWidget(cpu)
        close=QPushButton('收起')
        close.clicked.connect(card.close)
        layout.addWidget(close)
        card.resize(300,140)
        rect=self.pet.screen().availableGeometry()
        card.move(max(rect.left(),min(self.pet.x()-310,rect.right()-300)),max(rect.top(),min(self.pet.y()-160,rect.bottom()-140)))
        self.feedback=card
        card.show()
        self.window.motion.fade(card)

    def finished(self):
        old = self.active_worker
        self.active_worker = None
        self.window.worker = None
        self.window.batch_finished()
        if old:
            old.deleteLater()
        self.run_next()

    def cancel_all(self):
        for check in list(self.checks):
            check.worker.cancel_event.set()
            check.close()
        for request in self.pending:
            for item in request.items:
                item.job.status,item.job.error = '已取消','排队任务已取消'
                if request.origin!='information':self.window.render_job(job_kind(item.job),item.job)
        self.pending.clear()
        if self.active_worker:
            self.active_worker.cancel(True)

    def request_exit(self):
        if not self.exiting:
            self.exiting = True
            self.stop_play();self.sounds.stop_all()
            self.window.closing = True
            self.window.refresh_controls()
            self.cancel_all()
            self.incoming.clear()
            if self.dialog:
                self.dialog.close()
            if self.feedback:
                self.feedback.close()
            for worker in self.loaders + self.window.inspectors:
                worker.cancel_event.set()
            self.window.information_page.stop()
            for check in self.checks:
                check.worker.cancel_event.set()
                check.close()
            for dialog in self.return_dialogs:
                dialog.close()
            if self.settings_dialog:
                self.settings_dialog.close()
            if self.window.detector:
                self.window.detector.cancel_event.set()
            for timer in self.pet.findChildren(QTimer):timer.stop()
            self.pet.hide()
            self.tray.hide()
        self.window.information_page.stop()
        threads = [self.active_worker,self.window.detector,*self.loaders,*self.window.inspectors,*self.window.information_page.loaders,*(check.worker for check in self.checks)]
        if any(w and w.isRunning() for w in threads):
            QTimer.singleShot(100,self.request_exit)
            return
        self.window.close()
        self.pet.close()
        if self.quit_application:
            self.app.quit()


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self,root,parent=None):
        super().__init__(parent)
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtCore import QLockFile
        self.name = 'MediaForge_' + hashlib.sha256(str(Path(root).resolve()).lower().encode()).hexdigest()[:24]
        self.server = QLocalServer(self)
        lock_folder = runtime_home(root) / 'data'
        lock_folder.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(lock_folder / 'instance.lock'))
        self.primary = self.lock.tryLock(0)
        socket = QLocalSocket(self)
        if not self.primary:
            socket.connectToServer(self.name)
            if not socket.waitForConnected(3000):
                raise RuntimeError('软件正在启动或退出，请稍后再次打开')
            socket.write(b'activate')
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
        else:
            QLocalServer.removeServer(self.name)
            if not self.server.listen(self.name):
                raise RuntimeError('无法建立软件单实例通信')
            self.server.newConnection.connect(self.connection)

    def close(self):
        self.server.close()
        if self.primary:
            self.lock.unlock()

    def connection(self):
        socket = self.server.nextPendingConnection()
        self.activated.emit()
        socket.disconnectFromServer()
        socket.deleteLater()
