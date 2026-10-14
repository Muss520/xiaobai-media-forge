"""Information overview and explicit editors; original media is never modified."""
import threading
import json
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QTimer,QUrl,QSignalBlocker,Slot,QEvent
from PySide6.QtGui import QDesktopServices,QPixmap
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QLineEdit,
    QTableWidget,QTableWidgetItem,QHeaderView,QTabWidget,QCheckBox,QFileDialog,QMessageBox,
    QAbstractItemView,QScrollArea,QFrame,QSplitter,QDialog,QLayout,QSizePolicy)
from .metadata import COMMON,read_metadata,writable_catalog,can_edit,validate_edit,MetadataOptions
from .metadata_fields import FIELDS,field_value,display_value,resolve_field,resolve_tag,parse_coordinates
from .models import Job,human_size
from .widgets import WrappedCheckBox


class MetadataReader(QThread):
    ready=Signal(object,object,str)
    def __init__(self,job):
        super().__init__(); self.job=job; self.cancel_event=threading.Event()
    def run(self):
        try:
            import logging
            logging.info('信息读取开始：%s',self.job.path)
            from .live import components
            if self.job.inputs or self.job.path.suffix.lower()=='.livp':
                with components(self.job.path,self.job.inputs,self.cancel_event) as paths:
                    records=[read_metadata(path,self.cancel_event) for path in paths]
            else:records=[read_metadata(self.job.path,self.cancel_event)]
            logging.info('素材标签已读取，加载可写字段能力')
            catalog=writable_catalog(self.cancel_event)
            logging.info('信息读取完成：%s 个组件 / %s 可写字段',len(records),len(catalog))
            if not self.cancel_event.is_set():self.ready.emit(records,catalog,'')
        except Exception as error:
            if not self.cancel_event.is_set():self.ready.emit([],{},str(error))


class InformationPage(QWidget):
    def __init__(self,window):
        super().__init__()
        self.window=window; self.jobs=[]; self.records={}; self.catalog={}; self.edits={}; self.supplements={}
        self.draft_targets={}; self.last_edit_error=""; self.expanded_dialog=None
        self.clear_states={}; self.loaders=[]; self.drafts={}; self.previews={}; self.editor=None; self.editor_dialog=None
        self.root=QVBoxLayout(self); self.root.setContentsMargins(0,0,0,0)
        self.surface=QWidget(); self.root.addWidget(self.surface)
        self.expanded_placeholder=QPushButton('信息已在放大窗口中打开 · 点击查看'); self.expanded_placeholder.clicked.connect(self.open_expanded); self.expanded_placeholder.hide(); self.root.addWidget(self.expanded_placeholder)
        root=QVBoxLayout(self.surface); root.setContentsMargins(12,4,12,10); root.setSpacing(7)
        top=QHBoxLayout(); self.thumbnail=QLabel(); self.thumbnail.setFixedSize(56,56); self.thumbnail.setAlignment(Qt.AlignCenter); top.addWidget(self.thumbnail)
        titles=QVBoxLayout(); row=QHBoxLayout()
        add=QPushButton('＋ 添加素材'); add.clicked.connect(self.choose_files); row.addWidget(add)
        self.files=QComboBox(); self.files.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); self.files.setMinimumContentsLength(14); self.files.currentIndexChanged.connect(self.choose_job); row.addWidget(self.files,1)
        self.component=QComboBox(); self.component.currentIndexChanged.connect(self.change_component); row.addWidget(self.component)
        titles.addLayout(row); self.overview_label=QLabel('添加素材，查看信息并导出原画质副本'); self.overview_label.setObjectName('muted'); self.overview_label.setWordWrap(True); titles.addWidget(self.overview_label)
        top.addLayout(titles,1); root.addLayout(top)
        searchrow=QHBoxLayout(); self.search=QLineEdit(); self.search.setPlaceholderText('搜索设备、拍摄时间、地点或原始标签…'); self.search.textChanged.connect(self.filter_rows); searchrow.addWidget(self.search,1)
        self.missing=QCheckBox('显示缺失项'); self.missing.toggled.connect(self.populate); searchrow.addWidget(self.missing)
        self.expand=QPushButton('放大查看'); self.expand.clicked.connect(self.open_expanded); searchrow.addWidget(self.expand); root.addLayout(searchrow)
        self.splitter=QSplitter(Qt.Horizontal); root.addWidget(self.splitter,1)
        self.tabs=QTabWidget(); self.splitter.addWidget(self.tabs)
        self.common_body=QWidget(); self.common_layout=QVBoxLayout(self.common_body); self.common_layout.setContentsMargins(0,4,10,8); self.common_layout.setSpacing(10); self.common_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.common_scroll=QScrollArea(); self.common_scroll.setWidgetResizable(True); self.common_scroll.setWidget(self.common_body); self.common_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.tabs.addTab(self.common_scroll,'常用信息')
        from .metadata_quick import QuickMetadataForm
        self.quick_form=QuickMetadataForm(self); self.quick_scroll=QScrollArea(); self.quick_scroll.setWidgetResizable(True); self.quick_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.quick_scroll.setWidget(self.quick_form)
        self.tabs.addTab(self.quick_scroll,'小白更改信息')
        self.common_scroll.viewport().installEventFilter(self)
        raw=QWidget(); raw_layout=QVBoxLayout(raw); raw_layout.setContentsMargins(0,4,0,0)
        self.raw_table=QTableWidget(0,3); self.raw_table.setHorizontalHeaderLabels(['原始标签','值','操作'])
        self.raw_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive); self.raw_table.setColumnWidth(0,240)
        self.raw_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.Stretch); self.raw_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents)
        self.raw_table.verticalHeader().hide(); self.raw_table.verticalHeader().setDefaultSectionSize(42)
        self.raw_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.raw_table.setWordWrap(False); self.raw_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.raw_table.setSelectionMode(QAbstractItemView.SingleSelection); raw_layout.addWidget(self.raw_table,1)
        raw_actions=QHBoxLayout(); self.edit_button=QPushButton('编辑所选字段'); self.edit_button.clicked.connect(self.edit_selected); raw_actions.addWidget(self.edit_button)
        self.copy_button=QPushButton('复制值'); self.copy_button.clicked.connect(self.copy_selected); raw_actions.addWidget(self.copy_button); raw_actions.addStretch(); raw_layout.addLayout(raw_actions)
        self.raw_table.cellDoubleClicked.connect(lambda *args:self.edit_selected()); self.tabs.addTab(raw,'完整标签')
        self.editor_host=QScrollArea(); self.editor_host.setWidgetResizable(True); self.editor_host.setMinimumWidth(330); self.editor_host.setMaximumWidth(460); self.editor_host.hide(); self.splitter.addWidget(self.editor_host)
        self.pending=QLabel('没有待修改项'); self.pending.setObjectName('taskDetails'); self.pending.setWordWrap(True); self.pending.setMaximumHeight(72); self.pending.installEventFilter(self); root.addWidget(self.pending)
        self.clear=WrappedCheckBox('清除可移除信息 · 保留方向和色彩；Live 清除后为普通照片＋视频'); self.clear.toggled.connect(self.clear_changed); root.addWidget(self.clear)
        self.hint=QLabel('编辑只应用于输出副本，原文件保留'); self.hint.setObjectName('muted'); self.hint.setWordWrap(True); root.addWidget(self.hint)
        bottom=QHBoxLayout()
        self.reset=QPushButton('撤销修改'); self.reset.clicked.connect(self.reset_edits); bottom.addWidget(self.reset)
        self.convert=QPushButton('压缩 / 换格式'); self.convert.clicked.connect(self.route_conversion); bottom.addWidget(self.convert)
        self.result=QPushButton('打开结果'); self.result.clicked.connect(self.show_result); bottom.addWidget(self.result); bottom.addStretch()
        self.export=QPushButton('导出修改版'); self.export.setObjectName('primary'); self.export.clicked.connect(self.export_copy); bottom.addWidget(self.export); root.addLayout(bottom)
        self.timer=QTimer(self); self.timer.timeout.connect(self.refresh_status); self.timer.start(200); self.populate()

    @property
    def job(self):
        i=self.files.currentIndex(); return self.jobs[i] if 0<=i<len(self.jobs) else None

    @property
    def record(self):
        records=self.records.get(self.job.id,[]) if self.job else []
        i=max(0,self.component.currentIndex()); return records[i] if i<len(records) else {}

    def extension(self):
        if not self.job:return ''
        if self.job.inputs:return self.job.inputs[max(0,self.component.currentIndex())].suffix.lower()
        if self.job.path.suffix.lower()=='.livp':
            extension=self.record.get('File:FileTypeExtension')
            return '.'+str(extension).lower() if extension else '.jpg' if self.component.currentIndex()==0 else '.mov'
        return self.job.path.suffix.lower()

    def choose_files(self):
        paths,_=QFileDialog.getOpenFileNames(self,'添加素材查看信息','','媒体文件 (*.*)')
        if paths:self.add_paths([Path(p) for p in paths])

    def add_paths(self,paths):
        if self.window.closing:return
        if getattr(self.window,'controller',None):self.window.controller.stop_play()
        from .controller import ImportWorker
        worker=ImportWorker(paths); self.loaders.append(worker); self.hint.setText('正在后台读取素材…')
        worker.ready.connect(self.imported,Qt.QueuedConnection); worker.finished.connect(self.reader_finished,Qt.QueuedConnection); worker.start()

    @Slot(object,object,str)
    def imported(self,jobs,previews,warning):
        if self.window.closing:return
        self.previews.update(previews)
        for job in jobs:
            if any(j.path==job.path and j.inputs==job.inputs for j in self.jobs):continue
            self.jobs.append(job); self.files.addItem(job.path.name)
            reader=MetadataReader(job); self.loaders.append(reader); reader.ready.connect(self.metadata_ready,Qt.QueuedConnection); reader.finished.connect(self.reader_finished,Qt.QueuedConnection); reader.start()
        if warning:self.hint.setText(warning)

    @Slot(object,object,str)
    def metadata_ready(self,records,catalog,error):self.loaded(self.sender().job,records,catalog,error)
    @Slot()
    def reader_finished(self):self.release(self.sender())
    def release(self,worker):
        if worker in self.loaders:self.loaders.remove(worker)
        worker.deleteLater()
        if not self.loaders and self.hint.text().startswith('正在后台读取'):
            self.hint.setText('读取完成 · 可直接更改信息，导出时保留原格式和原画质')

    def loaded(self,job,records,catalog,error):
        if self.window.closing:return
        self.records[job.id]=records; self.catalog.update(catalog)
        if error:job.error=error; self.hint.setText(error)
        elif self.job is job:self.hint.setText('读取完成 · 可直接更改信息，导出时保留原格式和原画质')
        if self.job is job:self.choose_job(); self.refresh_status()

    def choose_job(self,*args):
        self.close_editor()
        guard=QSignalBlocker(self.clear); self.clear.setChecked(self.clear_states.get(self.job.id,False) if self.job else False); del guard
        self.component.blockSignals(True); self.component.clear()
        records=self.records.get(self.job.id,[]) if self.job else []
        for i in range(len(records)):self.component.addItem(('照片' if i==0 else '视频') if len(records)>1 else '视频' if self.job.info and self.job.info.kind=='video' else '图片',i)
        self.component.blockSignals(False)
        if self.job:
            self.files.setToolTip(str(self.job.path)); info=self.job.info
            self.overview_label.setText((self.job.path.suffix[1:].upper()+f' · {human_size(info.size)} · {info.width} × {info.height}'+(f' · {info.duration:.2f} 秒' if info.duration else '')) if info else '正在读取素材信息…')
            image=self.previews.get(self.job.id)
            if image is not None:self.thumbnail.setPixmap(QPixmap.fromImage(image).scaled(56,56,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            else:self.thumbnail.setPixmap(self.window.windowIcon().pixmap(48,48))
        self.populate()

    def change_component(self,*args):
        self.close_editor()
        self.populate()

    def effective_record(self):
        record=dict(self.record); index=max(0,self.component.currentIndex())
        if self.job:
            for (component,tag),value in self.edits.get(self.job.id,{}).items():
                if component==index:
                    if value and (tag in {'XMP-dc:Subject','XMP-dc:Creator','IPTC:Keywords'}):
                        try:record[tag]=json.loads(value)
                        except ValueError:record[tag]=value
                    else:record[tag]=value
        return record

    def populate(self,*args):
        self.populate_raw(); self.update_pending(); self.filter_rows()

    def populate_common(self):
        scroll=self.common_scroll.verticalScrollBar().value()
        while self.common_layout.count():
            item=self.common_layout.takeAt(0)
            if item.widget():item.widget().hide(); item.widget().deleteLater()
        record=self.effective_record(); query=self.search.text().casefold(); any_rows=False
        for group in ('拍摄时间','设备与镜头','地点','作者'):
            frame=QFrame(); frame.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum); frame.setObjectName('informationCard'); layout=QVBoxLayout(frame); layout.setContentsMargins(12,6,12,8); layout.setSpacing(6)
            frame.installEventFilter(self)
            heading=QLabel(group); heading.setObjectName('parameterHeading'); heading.installEventFilter(self); layout.addWidget(heading); count=0
            for name,(category,label,kind,tags,xmp) in FIELDS.items():
                if category!=group:continue
                value=field_value(name,record)
                if value is None and not self.missing.isChecked():continue
                text=display_value(name,value)
                if query and query not in (label+' '+text+' '+' '.join(tags)).casefold():continue
                row=QHBoxLayout(); caption=QLabel(label); caption.setMinimumWidth(82); caption.setMaximumWidth(130); row.addWidget(caption)
                display=QLabel(text); display.setWordWrap(True); display.setTextInteractionFlags(Qt.TextSelectableByMouse); row.addWidget(display,1)
                edit=QPushButton('编辑' if value is not None else '添加'); edit.setMaximumWidth(74); edit.clicked.connect(lambda checked=False,n=name:self.edit_field(n)); row.addWidget(edit,0,Qt.AlignTop); layout.addLayout(row)
                supplements=self.supplements.get(self.job.id,{}) if self.job else {}
                extra=[(tag,v,strategy) for (component,tag,strategy),v in supplements.items() if component==max(0,self.component.currentIndex()) and (tag==xmp or name=='location' and tag.startswith('XMP-exif:GPS'))]
                for tag,v,strategy in extra:
                    note=QLabel(('附件补充值：' if strategy=='sidecar' else 'XMP 补充值：')+str(v)+' · '+tag)
                    note.setObjectName('muted'); note.setWordWrap(True); layout.addWidget(note)
                count+=1; any_rows=True
            if count:self.common_layout.addWidget(frame)
            else:frame.deleteLater()
        if not any_rows:
            label=QLabel('尚无可显示的常用信息。可打开“显示缺失项”添加，或查看完整标签。'); label.setWordWrap(True); self.common_layout.addWidget(label)
        self.common_layout.addStretch(); self.common_scroll.verticalScrollBar().setValue(scroll)

    def populate_raw(self):
        table=self.raw_table; selected=table.item(table.currentRow(),0); selected_key=selected.data(Qt.UserRole) if selected else None
        scroll=table.verticalScrollBar().value(); record=self.effective_record(); index=max(0,self.component.currentIndex())
        if self.job:
            for (component,tag,strategy),value in self.supplements.get(self.job.id,{}).items():
                if component==index:record[tag]=value
        table.setRowCount(len(record))
        for row,(key,value) in enumerate(record.items()):
            target=resolve_tag(key,self.record,self.extension(),self.catalog)
            for col,text in enumerate((key,json.dumps(value,ensure_ascii=False) if isinstance(value,(list,dict)) else str(value),'只读' if target.strategy=='readonly' else '编辑')):
                item=QTableWidgetItem(text); item.setData(Qt.UserRole,key); item.setToolTip(str(value) if col==1 else target.reason or key); item.setFlags(item.flags() & ~Qt.ItemIsEditable); table.setItem(row,col,item)
            if key==selected_key:table.setCurrentCell(row,0)
        table.verticalScrollBar().setValue(scroll)

    def filter_rows(self,*args):
        query=self.search.text().casefold(); table=self.raw_table
        for row in range(table.rowCount()):table.setRowHidden(row,query not in ' '.join(table.item(row,col).text() for col in range(3)).casefold())
        self.populate_common(); self.quick_form.refresh()

    def edit_field(self,name):
        if not self.job:return
        target=resolve_field(name,self.record,self.extension())
        field=self.quick_form.fields.get(name)
        if field and field.destination.currentData() is not None and self.has_pending_target(field.target()):target=field.target()
        self.open_editor(target,self.value_for_target(name,target),name)

    def edit_selected(self):
        item=self.raw_table.item(self.raw_table.currentRow(),0)
        if not item:return
        key=item.data(Qt.UserRole); target=resolve_tag(key,self.record,self.extension(),self.catalog)
        if target.strategy=='readonly':self.hint.setText(target.reason); return
        value=field_value('location',self.effective_record()) if key.startswith('Composite:GPS') else self.effective_record().get(key)
        semantic=next((name for name,(_,_,_,tags,xmp) in FIELDS.items() if key in tags or key==xmp),None)
        if key.startswith('Composite:GPS'):semantic='location'
        self.open_editor(target,value,semantic)

    def copy_selected(self):
        item=self.raw_table.item(self.raw_table.currentRow(),1)
        if item:__import__('PySide6.QtWidgets',fromlist=['QApplication']).QApplication.clipboard().setText(item.text())

    def open_editor(self,target,value,semantic=None):
        from .metadata_editor import MetadataEditor
        self.close_editor(); index=max(0,self.component.currentIndex()); context=(self.job.id,index,target.tag,target.strategy)
        self.draft_targets[context]=target
        editor=MetadataEditor(target,value,self.drafts.get(context)); self.editor=editor; self.edit_context=context
        if semantic:
            alternate=resolve_field(semantic,self.record,self.extension(),True)
            if alternate.tag!=target.tag or alternate.strategy!=target.strategy:
                from PySide6.QtWidgets import QPushButton
                button=QPushButton('改用 XMP 附件' if alternate.strategy=='sidecar' else '改用 XMP 补充信息')
                editor.content_layout.insertWidget(3,button)
                button.clicked.connect(lambda:self.open_editor(alternate,value,semantic))
        def draft(value):
            if value=='__RESET_DRAFT__':self.drafts.pop(context,None)
            else:self.drafts[context]=value
            self.update_pending()
        editor.draftChanged.connect(draft); editor.applied.connect(lambda target,value:self.apply_editor(context,target,value)); editor.closed.connect(self.close_editor)
        if self.surface.width()>=1100:
            self.editor_host.setWidget(editor); self.editor_host.show(); self.splitter.setSizes([max(550,self.width()-380),360])
        else:
            dialog=QDialog(self.window,Qt.Tool); dialog.setWindowTitle('编辑信息 · '+target.label); dialog.setStyleSheet(self.window.styleSheet()); dialog.setAttribute(Qt.WA_DeleteOnClose)
            layout=QVBoxLayout(dialog); scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(editor); layout.addWidget(scroll)
            dialog.resize(min(620,self.screen().availableGeometry().width()-40),min(560,self.screen().availableGeometry().height()-60)); self.editor_dialog=dialog
            def closed():
                if self.editor_dialog is dialog:self.editor_dialog=None; self.editor=None
            dialog.finished.connect(closed); dialog.show()

    def close_editor(self):
        if self.editor_dialog:
            dialog=self.editor_dialog; self.editor_dialog=None; dialog.close()
        if self.editor_host.widget():
            widget=self.editor_host.takeWidget(); widget.deleteLater()
        self.editor_host.hide(); self.editor=None

    def apply_editor(self,context,target,value,origin='editor'):
        job_id,index,_,_=context
        try:
            entries=[(target.tag,value)]
            if target.kind=='gps' and target.tag.startswith('XMP-'):
                if value:
                    lat,lon,altitude=parse_coordinates(value)
                    entries=[('XMP-exif:GPSLatitude',str(lat)),('XMP-exif:GPSLongitude',str(lon)),('XMP-exif:GPSAltitude','' if altitude is None else str(altitude))]
                else:entries=[('XMP-exif:GPSLatitude',''),('XMP-exif:GPSLongitude',''),('XMP-exif:GPSAltitude','')]
            elif value and target.tag in {'XMP-dc:Creator','XMP-dc:Subject'} and target.kind!='list':entries=[(target.tag,json.dumps([value] if value else [],ensure_ascii=False))]
            for key,entry in entries:validate_edit(key,entry)
            if target.strategy=='native':
                for key,entry in entries:
                    if not can_edit(key,self.catalog):raise ValueError('该标签不支持直接修改，可选择 XMP 补充信息')
                for key,entry in entries:self.edits.setdefault(job_id,{})[index,key]=entry
            else:
                for key,entry in entries:self.supplements.setdefault(job_id,{})[index,key,target.strategy]=entry
            self.hint.setText('已加入待修改项，导出后会重新读取核验'); self.drafts.pop(context,None)
            self.last_edit_error=''; self.populate(); return True
        except ValueError as error:
            if self.editor and origin=='editor':self.editor.error.setText(str(error))
            self.last_edit_error=str(error); self.hint.setText(str(error)); return False

    def update_views(self):
        self.populate()

    def value_for_target(self,name,target):
        if not self.job:return None
        index=max(0,self.component.currentIndex())
        if target.strategy=='native':
            edits=self.edits.get(self.job.id,{})
            if (index,target.tag) in edits:return edits[index,target.tag]
        else:
            values=self.supplements.get(self.job.id,{})
            if target.kind=='gps':
                latitude=values.get((index,'XMP-exif:GPSLatitude',target.strategy))
                longitude=values.get((index,'XMP-exif:GPSLongitude',target.strategy))
                if latitude is not None and longitude is not None:
                    altitude=values.get((index,'XMP-exif:GPSAltitude',target.strategy))
                    return f'{latitude}, {longitude}'+(f', {altitude}' if altitude not in (None,'') else '') if latitude and longitude else ''
            if (index,target.tag,target.strategy) in values:return values[index,target.tag,target.strategy]
        return field_value(name,self.effective_record())

    def has_pending_target(self,target):
        if not self.job:return False
        index=max(0,self.component.currentIndex())
        return ((index,target.tag) in self.edits.get(self.job.id,{}) or
                (index,target.tag,target.strategy) in self.supplements.get(self.job.id,{}) or
                (self.job.id,index,target.tag,target.strategy) in self.drafts)

    def restore_field(self,name,refresh=True):
        if not self.job:return
        index=max(0,self.component.currentIndex()); tags=set(FIELDS[name][3])|{FIELDS[name][4]}
        if name=='location':tags|={'XMP-exif:GPSLatitude','XMP-exif:GPSLongitude','XMP-exif:GPSAltitude'}
        edits=self.edits.get(self.job.id,{}); supplements=self.supplements.get(self.job.id,{})
        for key in list(edits):
            if key[0]==index and key[1] in tags:edits.pop(key)
        for key in list(supplements):
            if key[0]==index and key[1] in tags:supplements.pop(key)
        for key in list(self.drafts):
            if key[0]==self.job.id and key[1]==index and key[2] in tags:self.drafts.pop(key)
        if refresh:self.populate()

    def eventFilter(self,watched,event):
        if event.type()==QEvent.MouseButtonDblClick and event.button()==Qt.LeftButton:
            if watched is self.common_scroll.viewport() or watched is self.pending or watched.objectName() in {'informationCard','parameterHeading'}:
                self.open_expanded(); return True
        return super().eventFilter(watched,event)

    def open_expanded(self):
        if self.expanded_dialog:
            self.expanded_dialog.showNormal() if self.expanded_dialog.isMinimized() else self.expanded_dialog.show()
            self.expanded_dialog.raise_(); self.expanded_dialog.activateWindow(); return
        self.close_editor()
        context=(self.job.id if self.job else None,self.component.currentIndex())
        view=(self.tabs.currentIndex(),self.common_scroll.verticalScrollBar().value(),self.quick_scroll.verticalScrollBar().value(),self.raw_table.verticalScrollBar().value())
        dialog=QDialog(self.window,Qt.Window|Qt.WindowMaximizeButtonHint|Qt.WindowCloseButtonHint)
        dialog.setWindowTitle('媒体信息 · 放大查看与编辑'); dialog.setStyleSheet(self.window.styleSheet())
        dialog.setAttribute(Qt.WA_DeleteOnClose); layout=QVBoxLayout(dialog); layout.setContentsMargins(12,8,12,10)
        self.root.removeWidget(self.surface); layout.addWidget(self.surface); self.expanded_placeholder.show()
        self.expanded_dialog=dialog
        def restore(*args):
            self.close_editor(); layout.removeWidget(self.surface); self.surface.setParent(self); self.root.insertWidget(0,self.surface);self.surface.show()
            self.expanded_placeholder.hide(); self.expanded_dialog=None
            if context==(self.job.id if self.job else None,self.component.currentIndex()):
                self.tabs.setCurrentIndex(view[0])
                def scroll_back():
                    for bar,value in zip((self.common_scroll.verticalScrollBar(),self.quick_scroll.verticalScrollBar(),self.raw_table.verticalScrollBar()),view[1:]):bar.setValue(value)
                QTimer.singleShot(0,scroll_back)
        dialog.finished.connect(restore)
        available=self.screen().availableGeometry(); dialog.resize(min(1180,available.width()-40),min(850,available.height()-60));dialog.show()

    def record_edit(self,index,key,value):
        if not self.job:return
        if not can_edit(key,self.catalog):raise ValueError('该字段不支持安全写入')
        self.edits.setdefault(self.job.id,{})[index,key]=validate_edit(key,value); self.update_pending()

    def reset_edits(self):
        if self.job:
            self.edits.pop(self.job.id,None); self.supplements.pop(self.job.id,None)
            self.drafts={key:value for key,value in self.drafts.items() if key[0]!=self.job.id}
        self.clear.setChecked(False); self.close_editor(); self.populate()

    def clear_changed(self,value):
        if self.job:self.clear_states[self.job.id]=value
        self.update_pending()

    def update_pending(self,*args):
        entries=self.edits.get(self.job.id,{}) if self.job else {}; supplements=self.supplements.get(self.job.id,{}) if self.job else {}
        records=self.records.get(self.job.id,[]) if self.job else []
        def readable(value):
            if value in (None,''):return '无'
            if isinstance(value,list):return '、'.join(map(str,value))
            if isinstance(value,str) and value.startswith('['):
                try:return '、'.join(map(str,json.loads(value)))
                except ValueError:pass
            return str(value)
        parts=[f'{COMMON.get(key.partition(":")[2],key)}：{readable(records[index].get(key) if index<len(records) else None)} → {readable(value) if value else "删除"}' for (index,key),value in entries.items()]
        parts += [f'{"XMP附件" if strategy=="sidecar" else "XMP补充"}：{key} → {value}' for (_,key,strategy),value in supplements.items()]
        text=('清除可移除信息；Live 将导出普通照片＋视频。 ' if self.clear.isChecked() else '')+('待修改 '+str(len(parts))+' 项：'+'；'.join(parts) if parts else '没有待修改项')
        draft_count=sum(key[0]==self.job.id for key in self.drafts) if self.job else 0
        if draft_count:text+=f' · 未应用/未完成草稿 {draft_count} 项'
        line_height=self.pending.fontMetrics().height()
        self.pending.setStyleSheet('padding:5px 10px;');self.pending.setMinimumHeight(line_height+12)
        self.pending.setMaximumHeight(line_height*3+14 if parts or draft_count else line_height+12)
        self.pending.setText(text[:230]+('…' if len(text)>230 else '')); self.pending.setToolTip(text)

    def export_copy(self):
        job=self.job
        if not job or not self.records.get(job.id):return
        if any(key[0]==job.id for key in self.drafts):
            self.hint.setText('仍有未应用或未完成的草稿，请先填写有效值、应用或恢复原值，再导出。'); return
        edits=self.edits.get(job.id,{}); supplements=self.supplements.get(job.id,{})
        if self.clear.isChecked() or edits or supplements:
            if QMessageBox.question(self,'确认信息处理',self.pending.toolTip()+'\n\n仅修改输出副本，不修改原件；附件会与副本一同保存。')!=QMessageBox.Yes:return
        from .workflow import make_request,job_kind
        copy_job=Job(job.path,info=job.info,inputs=job.inputs); self.last_output_job=copy_job
        value=MetadataOptions(self.clear.isChecked(),tuple((i,key,v) for (i,key),v in edits.items()),tuple((i,key,v,strategy) for (i,key,strategy),v in supplements.items()))
        request=make_request([copy_job],{job_kind(copy_job):value},origin='information',prefix=getattr(getattr(self.window,'controller',None),'preferences',{}).get('folder_prefix','转换结果'))
        if getattr(self.window,'controller',None):self.window.controller.enqueue(request)
        else:self.window.execute_request(request)

    def refresh_status(self):
        job=getattr(self,'last_output_job',None)
        if job and self.job and job.path==self.job.path and job.status not in {'完成','失败','已取消'}:self.hint.setText(f'{job.path.name} · {job.status} · {job.progress}%')
        self.export.setEnabled(bool(self.job and self.records.get(self.job.id)) and not self.window.busy and not self.window.closing)
        self.result.setEnabled(bool(job and (job.output or job.error)))

    def show_result(self):
        job=getattr(self,'last_output_job',None)
        if not job:return
        if job.output:QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.output if job.output.is_dir() else job.output.parent)))
        if job.metadata_report:QMessageBox.information(self,'信息处理报告',json.dumps(job.metadata_report,ensure_ascii=False,indent=2))
        elif job.error:QMessageBox.information(self,'处理原因',job.error)

    def route_conversion(self):
        if not self.job:return
        from PySide6.QtWidgets import QMenu
        menu=QMenu(self)
        def route(mode):
            self.window.set_ui_mode(mode); self.window.add_files(list(self.job.inputs or (self.job.path,)))
        menu.addAction('转到小白模式',lambda:route('simple')); menu.addAction('转到专业模式',lambda:route('advanced')); menu.exec(self.convert.mapToGlobal(self.convert.rect().bottomLeft()))

    def stop(self):
        if self.expanded_dialog:self.expanded_dialog.close()
        self.close_editor()
        for worker in self.loaders:worker.cancel_event.set()
