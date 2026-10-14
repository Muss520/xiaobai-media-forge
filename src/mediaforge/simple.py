"""A small request form and a genuinely separate simple workspace."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QUrl, QSignalBlocker
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QListWidget, QListWidgetItem, QCheckBox, QLineEdit, QScrollArea, QDialog, QToolButton, QSizePolicy)
from .options import combo, byte_value, select, spin, OptionalNumber, UnitValue, VideoPanel, ImagePanel, LivePanel
from .workflow import ParameterStore, job_kind
from .models import human_size
from .motion import SmoothProgress
from .formats import ANIMATED_FORMATS
from .resolution import RESOLUTIONS,resolve_options


class DropArea(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class QuickForm(QWidget):
    def __init__(self, store=None, parent=None):
        super().__init__(parent)
        self.owned_panels = None
        if store is None:
            self.owned_panels = {'video': VideoPanel(), 'image': ImagePanel(), 'live': LivePanel()}
            for panel in self.owned_panels.values():
                panel.setParent(self)
                panel.hide()
            store = ParameterStore(self.owned_panels, self)
        self.store = store
        self.media_jobs = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(10)
        self.layout.setAlignment(Qt.AlignTop)
        self.rows = {}
        self.kinds = set()
        self.advanced_controls={}
        self.advanced_bodies={}
        self.resolution_controls={}
        for kind, label in [('video','视频'),('image','图片'),('live','Live Photo')]:
            section = QWidget()
            form = QFormLayout(section)
            form.setContentsMargins(0, 0, 0, 0)
            form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            section.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
            mode = combo([('照片＋视频','both'),('保留 Live','preserve'),('静态照片','image'),('普通视频','video'),('动图','animation')]) if kind == 'live' else None
            fmt = combo([])
            preset = combo([('均衡 · 推荐','balanced'),('高清','high'),('体积优先','small')])
            target = byte_value()
            target.hide()
            form.addRow(label + '格式', fmt)
            if mode:
                form.insertRow(0, '导出方式', mode)
                mode.currentIndexChanged.connect(lambda index, k=kind, w=mode: self.store.edit(k, 'mode', w.currentData()) if w.currentData() is not None else None)
                from .formats import VIDEO_FORMATS
                self.live_video_output=combo([('原始 MOV · 不转码','original_mov')]+[(f.upper()+(' · 转码' if f=='mov' else ''),f) for f in VIDEO_FORMATS])
                form.insertRow(2,'视频格式',self.live_video_output)
                self.live_video_output.currentIndexChanged.connect(lambda:self.store.edit('live','video_output',self.live_video_output.currentData()))
            form.addRow('需求', preset)
            
            custom = QLabel()
            custom.setWordWrap(True)
            custom.setObjectName('muted')
            reset = QPushButton('恢复预设')
            reset.clicked.connect(lambda checked=False, k=kind: self.store.edit(k,'presets',self.store.panels[k].presets.currentData()))
            summary_box=QWidget()
            summary_layout=QHBoxLayout(summary_box); summary_layout.setContentsMargins(0,6,0,6)
            summary_layout.addWidget(custom,1); summary_layout.addWidget(reset,0,Qt.AlignTop)
            reset.setMaximumWidth(125)
            form.addRow(summary_box)
            self.rows[kind] = (section, form, fmt, preset, target, mode, custom, reset)
            fmt.currentIndexChanged.connect(lambda index, k=kind, w=fmt: self.store.edit(k,'format',w.currentData()) if w.currentData() is not None else None)
            preset.currentIndexChanged.connect(lambda index, k=kind, w=preset: self.store.edit(k,'presets',w.currentData()))
            target.number.valueChanged.connect(lambda value, k=kind, w=target: self.store.edit(k,'target_bytes',w.value()))
            target.unit.currentIndexChanged.connect(lambda index, k=kind, w=target: self.store.edit(k,'target_bytes',w.value()))
            self.layout.addWidget(section)
            section.hide()
            advanced=QWidget()
            advanced_form=QFormLayout(advanced)
            advanced_form.setContentsMargins(0,6,0,6)
            advanced_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
            advanced.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Maximum)
            advanced_form.addRow('体积上限',target)
            advanced_form.labelForField(target).hide()
            fields=[('width','最大宽度',spin(0,16384,0)),('height','最大高度',spin(0,16384,0)),('quality','质量',spin(0,100 if kind!='video' else 63,85 if kind!='video' else 23))]
            if kind=='live':
                fields=[('image.'+name,label,widget) for name,label,widget in fields]
                fields += [('video.width','视频最大宽度',spin(0,16384,0)),('video.height','视频最大高度',spin(0,16384,0))]
            if kind in {'video','live'}:
                prefix='video.' if kind=='live' else ''
                fps=OptionalNumber(); fps.setRange(0,240); fps.setDecimals(3); fps.setSpecialValueText('保持原帧率')
                fields += [(prefix+'mode','视频控制',combo([('质量优先','quality'),('平均码率','bitrate'),('目标体积','size')])),
                           (prefix+'bitrate','视频码率',UnitValue([('kbps',1),('Mbps',1000)],2500)),(prefix+'fps','视频帧率',fps)]
                if kind=='live':fields.append(('video.quality','视频质量',spin(0,63,23)))
            resolution_fields=[('image.resolution','照片分辨率'),('video.resolution','视频分辨率')] if kind=='live' else [('resolution','分辨率')]
            for name,label in reversed(resolution_fields):
                control=combo(RESOLUTIONS); fields.insert(0,(name,label,control))
                self.resolution_controls[kind,name]=control
            for name,label,widget in fields:
                if name.endswith(('width','height')):widget.setSpecialValueText('保持原尺寸 / 自动')
                self.advanced_controls[kind,name]=widget
                advanced_form.addRow(label,widget)
                if isinstance(widget,UnitValue):
                    widget.number.valueChanged.connect(lambda v,k=kind,n=name,w=widget:self.store.edit(k,n,w.value()))
                    widget.unit.currentIndexChanged.connect(lambda v,k=kind,n=name,w=widget:self.store.edit(k,n,w.value()))
                elif hasattr(widget,'currentData'):
                    widget.currentIndexChanged.connect(lambda v,k=kind,n=name,w=widget:self.store.edit(k,n,w.currentData()) if w.currentData() is not None else None)
                elif isinstance(widget,QCheckBox):
                    widget.toggled.connect(lambda v,k=kind,n=name:self.store.edit(k,n,v))
                else:
                    widget.valueChanged.connect(lambda v,k=kind,n=name:self.store.edit(k,n,v))
            self.advanced_bodies[kind]=advanced
            advanced.hide()
        self.more = QToolButton()
        self.more.setText('＋ 高级选项')
        self.more.setCheckable(True)
        self.more.setObjectName('advancedToggle')
        self.more.toggled.connect(self.show_targets)
        self.layout.addWidget(self.more)
        for body in self.advanced_bodies.values():self.layout.addWidget(body)
        self.source_info=QLabel()
        self.source_info.setWordWrap(True)
        self.source_info.setObjectName('taskDetails')
        self.source_info.hide()
        self.layout.addWidget(self.source_info)
        self.first_frame = QCheckBox('动图转静态图片：只保留首帧')
        self.first_frame.toggled.connect(lambda checked: self.store.edit('image','animation','first' if checked else 'preserve'))
        self.first_frame.hide()
        self.layout.addWidget(self.first_frame)
        self.store.changed.connect(self.sync)
        self.sync()

    def sync(self, *args):
        for kind, row in self.rows.items():
            section, form, fmt, preset, target, mode, custom, reset = row
            panel = self.store.panels[kind]
            guards = [QSignalBlocker(w) for w in (fmt,preset,target.number,target.unit) + ((mode,) if mode else ())]
            fmt.clear()
            for index in range(panel.format.count()):
                fmt.addItem(panel.format.itemText(index), panel.format.itemData(index))
            select(fmt, panel.format.currentData())
            select(preset, panel.presets.currentData())
            target.setValue(panel.target_bytes.value())
            if mode:
                select(mode, panel.mode.currentData())
                form.labelForField(fmt).setText('Live 封装' if panel.mode.currentData()=='preserve' else '视频格式' if panel.mode.currentData()=='video' else '动图格式' if panel.mode.currentData()=='animation' else '照片格式')
                video_guard=QSignalBlocker(self.live_video_output)
                select(self.live_video_output,panel.video_output.currentData())
                form.setRowVisible(self.live_video_output,panel.mode.currentData()=='both')
                del video_guard
            panel.refresh_summary()
            summary = panel.custom_summary.text().partition('\n')[2].replace('\n', ' · ')
            limit=panel.target_bytes.value()
            custom.setText(('自定义已生效 · '+summary[:100] if panel.is_custom else '') + (f' · 体积上限 {human_size(limit)}' if limit else ''))
            custom.setToolTip(summary)
            custom.setVisible(panel.is_custom or bool(limit))
            reset.setVisible(panel.is_custom)
            form.setRowVisible(custom.parentWidget(),panel.is_custom or bool(limit))
            del guards
        for (kind,name),widget in self.advanced_controls.items():
            panel=self.store.panels[kind]
            parts=name.split('.')
            owner=getattr(panel,parts[0]+'_panel') if len(parts)>1 else panel
            source=getattr(owner,parts[-1])
            guards=[QSignalBlocker(widget)]
            if isinstance(widget,UnitValue):
                guards += [QSignalBlocker(widget.number),QSignalBlocker(widget.unit)]
                widget.setValue(source.value())
            elif hasattr(widget,'currentData'):select(widget,source.currentData())
            elif isinstance(widget,QCheckBox):widget.setChecked(source.isChecked())
            else:widget.setValue(source.value())
            widget.setEnabled(source.isEnabled())
            if kind=='live':
                live_mode=panel.mode.currentData()
                visible=(name=='video_copy' and live_mode=='both') or (name.startswith('video.') and live_mode in {'video','both'}) or (name.startswith('image.') and live_mode!='video')
                self.advanced_bodies[kind].layout().setRowVisible(widget,visible)
                if name.startswith('video.'):widget.setEnabled(source.isEnabled() and (live_mode!='both' or not panel.video_copy.isChecked()))
                if name.startswith('video.') and live_mode=='both' and panel.video_copy.isChecked():widget.setToolTip('先取消“保持原始 MOV”，再设置视频转码参数。')
            del guards
        self.refresh_source_info()
        value = self.store.values['image']
        needs_frame = any(job_kind(j)=='image' and j.info and j.info.frames>1 for j in self.media_jobs) and value.format not in ANIMATED_FORMATS
        self.first_frame.setVisible(needs_frame)
        guard = QSignalBlocker(self.first_frame)
        self.first_frame.setChecked(value.animation == 'first')
        del guard

    def set_jobs(self, jobs):
        self.media_jobs = jobs
        self.set_kinds({job_kind(job) for job in jobs})
        self.sync()

    def set_kinds(self, kinds):
        self.kinds = set(kinds)
        for kind, row in self.rows.items():
            row[0].setVisible(kind in self.kinds)
            self.advanced_bodies[kind].setVisible(kind in self.kinds and self.more.isChecked())
        self.setVisible(bool(self.kinds))

    def show_targets(self, shown):
        self.more.setText('－ 收起高级选项' if shown else '＋ 高级选项')
        for section, form, fmt, preset, target, mode, custom, reset in self.rows.values():
            target.setVisible(shown)
            self.advanced_bodies[next(k for k,r in self.rows.items() if r[4] is target)].layout().labelForField(target).setVisible(shown)
        for kind,body in self.advanced_bodies.items():body.setVisible(shown and kind in self.kinds)
        self.source_info.setVisible(shown and bool(self.media_jobs))

    def refresh_source_info(self):
        lines=[]
        for job in self.media_jobs:
            info=job.info
            if not info:continue
            kind=job_kind(job); options=self.store.values[kind]
            live_options=options if kind=='live' else None
            if kind=='live':options=options.video if options.mode=='video' else options.image
            raw=f'{human_size(info.size)} · {info.width} × {info.height}'
            if info.kind=='video':
                raw+=f' · {info.video_codec} · {info.fps:g} fps · 视频 {info.video_bitrate//1000 if info.video_bitrate else "未知"} kbps · 音频 {info.audio_bitrate//1000 if info.audio_bitrate else "未知"} kbps'
            preview_info=info
            if live_options and live_options.mode in {'video','animation'}:
                from dataclasses import replace
                preview_info=replace(info,kind='video',width=int(info.metadata.get('video_width',info.width)),height=int(info.metadata.get('video_height',info.height)),sample_aspect_ratio=info.metadata.get('video_sar','1/1'))
            effective=resolve_options(preview_info,options)
            if getattr(options,'remux',False):
                from dataclasses import replace
                effective=replace(effective,width=info.width,height=info.height)
            out=f'{options.format.upper()} · {effective.width} × {effective.height}'
            if hasattr(options,'codec'):out+='（视频按偶数对齐）'
            if hasattr(options,'mode'):out+=f' · {options.bitrate} kbps（设定）' if options.mode=='bitrate' else f' · 质量 {options.quality}'
            if hasattr(options,'fps'):
                out+=f' · {options.fps or info.fps:g} fps · 音频 '+('原样' if options.audio_codec=='copy' else '移除' if options.audio_codec=='none' else f'{options.audio_bitrate} kbps')
            target=live_options.target_bytes if live_options else options.target_bytes
            estimate=human_size(target)+'（上限）' if target else human_size(round((options.bitrate+options.audio_bitrate)*1000*info.duration/8*1.04))+'（估算）' if hasattr(options,'mode') and options.mode=='bitrate' and info.duration else '处理后核验；质量模式无法精确预估'
            out+=' · 预计体积：'+estimate
            if live_options and live_options.mode in {'both','video','preserve','animation'}:
                video=live_options.video; details=info.metadata
                from dataclasses import replace
                component=replace(info,kind="video",width=int(details.get("video_width",info.width)),height=int(details.get("video_height",info.height)),sample_aspect_ratio=details.get("video_sar","1/1"))
                video=resolve_options(component,video)
                raw+=f'\n原始视频：{details.get("video_width","未知")} × {details.get("video_height","未知")} · {human_size(details.get("video_size",0))} · {info.fps:g} fps · 视频 {info.video_bitrate//1000 if info.video_bitrate else "未知"} kbps · 音频 {info.audio_bitrate//1000 if info.audio_bitrate else "未知"} kbps'
                out+='\n视频输出：'+('原始 MOV · 尺寸、帧率、音频和码率不变' if live_options.mode=='preserve' or live_options.mode=='both' and live_options.video_copy else f'{video.format.upper()} · {video.width or details.get("video_width","原宽")} × {video.height or details.get("video_height","原高")} · {video.fps or info.fps:g} fps · '+(f'{video.bitrate} kbps（设定）' if video.mode=='bitrate' else f'质量 {video.quality}')+f' · 音频 {video.audio_codec.upper()} {video.audio_bitrate} kbps')
            lines.append(f'{job.path.name}\n原始：{raw}\n输出：{out}')
        self.source_info.setText('\n\n'.join(lines))

    def options(self):
        values = {kind: self.store.snapshot(kind) for kind in self.kinds}
        image = values.get('image')
        if image and image.format not in ANIMATED_FORMATS and image.animation == 'preserve' and any(job_kind(j)=='image' and j.info and j.info.frames>1 for j in self.media_jobs):
            self.first_frame.setFocus()
            raise ValueError('动图转静态图片需要确认只保留首帧，或选择 GIF / WebP / APNG。')
        return values


class SimplePage(QWidget):
    def __init__(self, window, store):
        super().__init__()
        self.window=window
        self.step=0
        self.batch_jobs=[]
        layout=QVBoxLayout(self)
        layout.setContentsMargins(24,8,24,16)
        layout.setSpacing(14)
        self.steps=QLabel()
        self.steps.setObjectName('wizardSteps')
        layout.addWidget(self.steps)
        self.result_summary=QLabel()
        self.result_summary.setObjectName('sectionTitle')
        layout.addWidget(self.result_summary)
        self.drop=DropArea('把文件放在这里\n或点击添加')
        self.drop.setObjectName('simpleDrop')
        self.drop.setAlignment(Qt.AlignCenter)
        self.drop.setMinimumHeight(120)
        self.drop.clicked.connect(window.choose_files)
        layout.addWidget(self.drop)
        self.list=QListWidget()
        self.list.setObjectName('simpleFiles')
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setIconSize(__import__('PySide6.QtCore',fromlist=['QSize']).QSize(48,48))
        self.list.setMinimumHeight(90)
        self.list.itemClicked.connect(self.show_detail)
        layout.addWidget(self.list,1)
        self.form=QuickForm(store)
        self.form_scroll=QScrollArea()
        self.form_scroll.setWidgetResizable(True)
        self.form_scroll.setWidget(self.form)
        layout.addWidget(self.form_scroll,1)
        self.folder_name=QLineEdit()
        self.folder_name.setPlaceholderText('结果文件夹名称（留空按日期自动命名）')
        layout.addWidget(self.folder_name)
        self.save_hint=QLabel('结果放在原文件旁的新文件夹 · 原文件保留')
        self.save_hint.setObjectName('muted')
        self.save_hint.setWordWrap(True)
        layout.addWidget(self.save_hint)
        self.detail=QLabel()
        self.detail.setWordWrap(True)
        self.detail.setMaximumHeight(72)
        self.detail.setObjectName('taskDetail')
        layout.addWidget(self.detail)
        self.progress=SmoothProgress()
        self.progress.setFixedHeight(16)
        layout.addWidget(self.progress)
        self.result_space=QWidget()
        layout.addWidget(self.result_space,1)
        actions=QHBoxLayout()
        self.back=QPushButton('上一步')
        self.back.clicked.connect(lambda:self.set_step(max(0,self.step-1)))
        self.remove=QPushButton('移除选中')
        self.remove.clicked.connect(self.remove_selected)
        self.retry=QPushButton('重试失败')
        self.retry.clicked.connect(lambda:self.start(True))
        self.cancel=QPushButton('取消处理')
        self.cancel.clicked.connect(lambda:window.controller.cancel_all() if getattr(window,'controller',None) else window.worker.cancel(True))
        self.open=QPushButton('打开结果')
        self.open.clicked.connect(self.open_results)
        self.begin=QPushButton('下一步：选择需求')
        self.begin.setObjectName('primary')
        self.begin.clicked.connect(self.next)
        for button in (self.back,self.remove,self.retry,self.cancel,self.open):
            actions.addWidget(button)
        actions.addStretch()
        actions.addWidget(self.begin)
        layout.addLayout(actions)
        self.refresh()

    def jobs(self):
        return [job for group in self.window.jobs.values() for job in group]

    def set_step(self,step):
        if self.window.busy and step!=2:
            return
        self.step=step
        self.detail.clear()
        self.refresh()
        self.window.motion.fade(self.list if step!=1 else self.form_scroll)

    def next(self):
        if self.step==0:
            self.set_step(1)
        elif self.step==1:
            self.start()
        else:
            self.set_step(0)

    def refresh(self):
        jobs=self.jobs()
        existing={self.list.item(i).data(Qt.UserRole):self.list.item(i) for i in range(self.list.count())}
        wanted={job.id for job in jobs}
        for id,item in list(existing.items()):
            if id not in wanted:
                self.list.takeItem(self.list.row(item))
        for job in jobs:
            item=existing.get(job.id)
            if item is None:
                item=QListWidgetItem()
                item.setData(Qt.UserRole,job.id)
                self.list.addItem(item)
            text=f'{job.path.name}   ·   {job.status}'
            if job.status=='完成':
                text+='   '+human_size(job.output_size)
            item.setText(text)
            item.setIcon(self.window.thumbnails.get(job.id,QIcon()))
            item.setToolTip(job.error or str(job.path))
        locked=self.window.busy or getattr(self.window,'preparing',False) or self.window.closing
        if self.window.busy:
            self.step=2
        self.steps.setText('  →  '.join(('● ' if i==self.step else '')+text for i,text in enumerate(('1 添加文件','2 选择需求','3 处理结果'))))
        pending=[j for j in jobs if j.status not in {'完成','处理中','排队中'}]
        self.form.set_jobs(pending)
        self.form.setEnabled(not locked)
        self.form_scroll.setVisible(self.step==1)
        self.folder_name.setVisible(self.step==1)
        self.folder_name.setEnabled(not locked)
        self.drop.setVisible(self.step==0)
        self.drop.setText(f'＋ 继续添加文件 · 已添加 {len(jobs)} 份' if jobs else '把文件放在这里\n或点击添加')
        self.drop.setMinimumHeight(54 if jobs else 120)
        self.list.setVisible(self.step!=1)
        self.result_summary.setVisible(self.step==2)
        self.result_summary.setText(f'本批次：完成 {sum(j.status=="完成" for j in self.batch_jobs)} · 失败 {sum(j.status=="失败" for j in self.batch_jobs)} · 共 {len(self.batch_jobs)} 项')
        self.list.setMaximumHeight(min(320,max(90,len(jobs)*72)) if self.step==2 else 16777215)
        self.result_space.setVisible(self.step==2)
        self.back.setVisible(self.step==1)
        self.back.setEnabled(not locked)
        self.remove.setVisible(self.step==0 and bool(jobs) and not locked)
        self.retry.setVisible(self.step==2 and any(j.status=='失败' for j in jobs) and not locked)
        self.cancel.setVisible(self.window.busy)
        self.open.setVisible(self.step==2 and any(j.status=='完成' for j in jobs))
        self.begin.setVisible(not self.window.busy)
        self.begin.setText(('下一步：选择需求','开始转换','添加新文件')[self.step])
        self.begin.setEnabled(not locked and not self.window.inspectors and (bool(pending) if self.step!=2 else True))
        self.progress.setVisible(self.step==2 and bool(self.batch_jobs))
        if self.batch_jobs:
            terminal={'完成','失败','已取消'}
            value=sum(100 if j.status in terminal else min(99,j.progress) for j in self.batch_jobs)//len(self.batch_jobs)
            status='完成' if all(j.status=='完成' for j in self.batch_jobs) else '失败' if all(j.status in terminal for j in self.batch_jobs) else '处理中'
            self.progress.motion.reduced=self.window.reduce_motion.isChecked()
            self.progress.set_progress(value,status)

    def start(self,retry=False):
        from .workflow import make_request
        jobs=[j for j in self.jobs() if j.status=='失败' or not retry and j.status not in {'完成','排队中','处理中'}]
        if not jobs or self.window.busy or self.window.inspectors:
            return
        try:
            request=make_request(jobs,self.form.options(),self.folder_name.text().strip(),prefix=getattr(getattr(self.window,'controller',None),'preferences',{}).get('folder_prefix','转换结果'))
            self.batch_jobs=jobs
            controller=getattr(self.window,'controller',None)
            if controller:
                controller.submit_request(request)
            else:
                self.window.execute_request(request)
            self.set_step(2)
        except Exception as error:
            self.detail.setText(str(error))
            self.detail.setProperty('error',True)
            self.detail.style().polish(self.detail)

    def show_detail(self,item):
        job=next(j for j in self.jobs() if j.id==item.data(Qt.UserRole))
        text=job.error or str(job.output or job.path)
        self.detail.setText(text)
        self.detail.setToolTip(text)
        self.detail.setProperty('error',bool(job.error))
        self.detail.style().unpolish(self.detail)
        self.detail.style().polish(self.detail)

    def remove_selected(self):
        ids={item.data(Qt.UserRole) for item in self.list.selectedItems()}
        for kind in self.window.jobs:
            self.window.jobs[kind]=[j for j in self.window.jobs[kind] if j.id not in ids]
            table=self.window.tables[kind]
            for row in range(table.rowCount()-1,-1,-1):
                if table.item(row,0).data(Qt.UserRole) in ids:
                    table.removeRow(row)
        self.refresh()

    def open_results(self):
        folders=list(dict.fromkeys(job.output if job.output.is_dir() else job.output.parent for job in self.jobs() if job.output and job.status=='完成'))
        for folder in folders:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


class QuickDialog(QDialog):
    confirmed = Signal(object)

    def __init__(self, jobs, preferences, parent=None):
        super().__init__(parent, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle('小白收到文件啦')
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.jobs = jobs
        outer = QVBoxLayout(self)
        title = QLabel(f'收到 {len(jobs)} 份影像，想怎么处理？')
        title.setObjectName('sectionTitle')
        title.setWordWrap(True)
        outer.addWidget(title)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.form = QuickForm()
        for kind, panel in self.form.store.panels.items():
            values = preferences.get(kind,{})
            if kind == 'live':
                self.form.store.edit(kind,'mode',values.get('mode','both'))
                self.form.store.edit(kind,'video_output',values.get('video_format','original_mov'))
            self.form.store.edit(kind,'format',values.get('format',{'video':'mp4','image':'jpg','live':'png'}[kind]))
            self.form.store.edit(kind,'presets',values.get('preset','balanced'))
        self.form.set_jobs(jobs)
        layout.addWidget(self.form)
        hint = QLabel('保存到原文件旁的「转换结果_日期时间」文件夹。\n不同原目录分别归组，不覆盖原文件。')
        hint.setWordWrap(True)
        hint.setObjectName('muted')
        layout.addWidget(hint)
        self.name = QLineEdit()
        self.name.setPlaceholderText('自定义结果文件夹名称（可留空）')
        layout.addWidget(self.name)
        self.error = QLabel()
        self.error.setObjectName('inlineError')
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.confirm = QPushButton('确认，开始转换')
        self.confirm.setObjectName('primary')
        self.confirm.clicked.connect(self.submit)
        outer.addWidget(self.confirm)
        self.setMinimumWidth(350)
        self.resize(370, min(390+100*(len(self.form.kinds)-1),self.screen().availableGeometry().height()-60))

    def submit(self):
        from .workflow import make_request
        try:
            request = make_request(self.jobs,self.form.options(),self.name.text().strip(),origin='pet',prefix=getattr(self,'folder_prefix','转换结果'))
            self.confirm.setEnabled(False)
            self.confirmed.emit(request)
            self.close()
        except Exception as error:
            self.error.setText(str(error))
