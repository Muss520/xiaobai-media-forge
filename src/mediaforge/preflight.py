"""Read-only preparation; suggested changes are applied only after confirmation."""
from dataclasses import dataclass,replace
from pathlib import Path
import math,os,threading
from PySide6.QtCore import QThread,Signal
from .models import LiveOptions,ImageOptions,VideoOptions,target_size
from .workflow import BatchRequest
from .images import check_cancel


@dataclass(frozen=True)
class Finding:
    job_id: str
    message: str
    category: str
    suggested: object = None
    blocking: bool = False


def inspect_request(request,cancel,inspect_media=True):
    from .probe import probe
    from .live import components
    from .video import build_command
    findings=[]
    for item in request.items:
        check_cancel(cancel)
        job,options=item.job,item.parameters
        try:
            if inspect_media:
                parent=item.folder.parent if item.sibling else item.folder
                while not parent.exists() and parent!=parent.parent:
                    parent=parent.parent
                if not parent.is_dir() or not os.access(parent,os.W_OK):
                    raise ValueError('输出目录不可写，请修改目录权限或选择其他目录')
            info=job.info
            if isinstance(options,LiveOptions):
                if inspect_media:
                    with components(job.path,job.inputs,cancel) as (photo,movie):
                        picture,info=probe(photo),probe(movie)
                        from .resolution import resolve_live
                        options=resolve_live(options,picture,info)
                        if options.mode=='preserve':
                            from .live import verify_pair
                            verify_pair(photo,movie,cancel)
                    if (options.mode=='preserve' or options.mode=='both' and options.video_copy) and options.target_bytes and options.target_bytes<=info.size:
                        findings.append(Finding(job.id,'整组上限小于原始 MOV，无法原样保留视频。请提高或取消上限。','target_size',blocking=True))
                        continue
                if options.mode=='both' and not options.video_copy and info:
                    build_command(info,options.video,item.folder/('check.'+options.video.format))
                if options.mode=='animation' and info:
                    if info.duration<=0:
                        raise ValueError('无法读取动态视频时长，不能生成完整动图')
                    w,h=target_size(info.width,info.height,options.image.width,options.image.height,options.image.aspect,False)
                    fps=min(30,options.animation_fps or info.fps or 15)
                    if w*h*math.ceil(info.duration*fps)>120_000_000:
                        suggested_fps=min(15,fps)
                        factor=min(1,720/max(w,h),math.sqrt(120_000_000/(w*h*math.ceil(info.duration*suggested_fps))))
                        sw,sh=max(1,int(w*factor)),max(1,int(h*factor))
                        params=replace(options,image=replace(options.image,width=sw,height=sh),animation_fps=suggested_fps)
                        findings.append(Finding(job.id,f'完整动图 {w}×{h} / {fps:g} fps 超出安全预算。建议 {sw}×{sh} / {suggested_fps:g} fps，不截短内容。','animation_budget',params))
                image=options.image if options.mode in {'image','both','animation','preserve'} else None
                if image and options.target_bytes and not image.auto_resize:
                    params=replace(options,image=replace(image,auto_resize=True))
                    findings.append(Finding(job.id,'已设置体积上限，可能需要降低尺寸。确认后允许最多 16 轮逐级缩小；不改变格式。','target_size',params))
            elif isinstance(options,ImageOptions):
                info=probe(job.path) if inspect_media else info
                if info:
                    from .resolution import resolve_options
                    options=resolve_options(info,options)
                if options.target_bytes and not options.auto_resize:
                    lossless=options.format in {'png','apng','bmp','tiff','ico','gif'} or options.format=='webp' and options.lossless
                    wording='这是无损/固定调色板格式，降低质量不能保证达到体积上限。' if lossless else '有损质量搜索仍可能无法满足极小上限。'
                    findings.append(Finding(job.id,wording+'可提高/取消上限、修改格式，或确认允许最多 16 轮逐级缩小尺寸。','target_size',replace(options,auto_resize=True)))
                if info and info.frames>1 and options.animation=='preserve':
                    w,h=target_size(info.width,info.height,options.width,options.height,options.aspect,False)
                    if w*h*info.frames>120_000_000:
                        factor=min(1,720/max(w,h),math.sqrt(120_000_000/(w*h*info.frames)))
                        findings.append(Finding(job.id,'动画帧数较多；建议缩小画面，完整保留时序和循环。','animation_budget',replace(options,width=max(1,int(w*factor)),height=max(1,int(h*factor)))))
            elif isinstance(options,VideoOptions):
                info=probe(job.path) if inspect_media else info
                if info:
                    build_command(info,options,item.folder/('check.'+options.format))
                    if (info.bit_depth>8 or info.color_transfer in {'smpte2084','arib-std-b67'}) and not options.remux and options.pixel_format=='yuv420p':
                        findings.append(Finding(job.id,'源视频为高位深或 HDR；当前为 8 位输出，显示效果可能变化。请确认继续，或返回选择 CPU 10 位编码。','color_change'))
        except Exception as error:
            from .images import Cancelled
            if isinstance(error,Cancelled):
                raise
            findings.append(Finding(job.id,str(error),'input_or_parameters',blocking=True))
    return findings


def apply_suggestions(request,findings):
    items=[]
    for item in request.items:
        params=item.parameters
        for finding in findings:
            if finding.job_id!=item.job.id or not finding.suggested:
                continue
            proposed=finding.suggested
            fields=('width','height') if finding.category=='animation_budget' else ('auto_resize',) if finding.category=='target_size' else ()
            if isinstance(params,LiveOptions):
                changes={field:getattr(proposed.image,field) for field in fields}
                if 'width' in changes or 'height' in changes:changes['resolution_preset']='custom'; changes['resolved_size']=False
                fps=proposed.animation_fps if finding.category=='animation_budget' else params.animation_fps
                params=replace(params,image=replace(params.image,**changes),animation_fps=fps)
            else:
                changes={field:getattr(proposed,field) for field in fields}
                if 'width' in changes or 'height' in changes:changes['resolution_preset']='custom'; changes['resolved_size']=False
                params=replace(params,**changes)
        items.append(replace(item,parameters=params))
    return replace(request,items=tuple(items))


class PreflightWorker(QThread):
    ready=Signal(object)
    def __init__(self,request,parent=None):
        super().__init__(parent)
        self.request=request
        self.cancel_event=threading.Event()
    def run(self):
        try:
            findings=inspect_request(self.request,self.cancel_event)
            if not self.cancel_event.is_set():
                self.ready.emit(findings)
        except Exception:
            if not self.cancel_event.is_set():
                self.ready.emit([Finding(item.job.id,'预检查未完成，请重新尝试','preflight',blocking=True) for item in self.request.items])


def classify_error(message):
    if any(word in message for word in ('体积','预算','像素','上限')):
        return 'target_size'
    if any(word in message for word in ('权限','不可写','拒绝访问','Permission')):
        return 'permission'
    if any(word in message.lower() for word in ('nvenc','qsv','amf','硬件')):
        return 'hardware'
    if any(word in message for word in ('配对','元数据','关键帧')):
        return 'live_metadata'
    return 'input_or_parameters'


from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QScrollArea,QWidget
from PySide6.QtCore import Qt,QTimer


class RequestCheck(QDialog):
    def __init__(self,request,controller):
        super().__init__(controller.window,Qt.Tool|Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle('导出前检查')
        self.controller,self.request=controller,request
        self.setStyleSheet(controller.window.styleSheet())
        self.layout=QVBoxLayout(self)
        self.message=QLabel('正在检查素材、参数和输出位置…')
        self.message.setWordWrap(True)
        self.layout.addWidget(self.message)
        self.body=QWidget()
        self.body_layout=QVBoxLayout(self.body)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.body)
        self.layout.addWidget(scroll)
        self.apply=QPushButton('确认优化并开始')
        self.apply.setObjectName('primary')
        self.apply.clicked.connect(lambda:self.execute(True))
        self.strict=QPushButton('保持所选参数继续')
        self.strict.clicked.connect(lambda:self.execute(False))
        self.back=QPushButton('返回修改需求')
        self.back.clicked.connect(self.back_to_options)
        for button in (self.apply,self.strict):
            button.hide()
            self.layout.addWidget(button)
        self.layout.addWidget(self.back)
        self.resize(430,330)
        self.worker=PreflightWorker(request,self)
        self.findings=[]
        self.worker.ready.connect(self.ready)
        self.worker.start()

    def ready(self,findings):
        if self.controller.exiting or self.worker.cancel_event.is_set():
            return
        self.findings=findings
        if not findings:
            self.execute(False)
            return
        names={item.job.id:item.job.path.name for item in self.request.items}
        self.message.setText('这些项目需要注意；修改尺寸必须经过你的确认。')
        for finding in findings:
            text=QLabel(names[finding.job_id]+'：'+finding.message)
            text.setWordWrap(True)
            self.body_layout.addWidget(text)
        self.apply.setVisible(any(f.suggested for f in findings))
        self.strict.show()
        self.strict.setText('继续可处理项目，其余记录失败' if any(f.blocking for f in findings) else '保持参数继续（可能无法达标）')

    def execute(self,adapt):
        request=apply_suggestions(self.request,self.findings) if adapt else self.request
        errors={f.job_id:f.message for f in self.findings if f.blocking}
        request=replace(request,items=tuple(replace(item,preflight_error=errors.get(item.job.id,'')) for item in request.items))
        self.controller.enqueue(request)
        self.close()

    def back_to_options(self):
        if self.request.origin=='pet' and not self.controller.exiting:
            from .simple import QuickDialog
            from dataclasses import asdict
            dialog=QuickDialog([item.job for item in self.request.items],self.controller.preferences.get('quick',{}))
            dialog.name.setText(self.request.folder_name)
            for item in self.request.items:
                from .workflow import job_kind
                kind=job_kind(item.job)
                dialog.form.store.panels[kind].restore(asdict(item.requested_parameters or item.parameters))
            dialog.form.store.capture()
            dialog.confirmed.connect(self.controller.submit_request)
            dialog.setStyleSheet(self.controller.window.styleSheet())
            self.controller.return_dialogs.append(dialog)
            dialog.destroyed.connect(lambda:self.controller.return_dialogs.remove(dialog) if dialog in self.controller.return_dialogs else None)
            dialog.show()
        else:
            self.controller.window.simple_page.set_step(1)
            self.controller.show_window()
        self.close()

    def closeEvent(self,event):
        if self.worker.isRunning():
            self.worker.cancel_event.set()
            event.ignore()
            QTimer.singleShot(50,self.close)
        else:
            event.accept()
