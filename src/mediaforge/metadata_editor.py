"""Explicit editor; shares typed inputs and drafts with the easy metadata form."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QHBoxLayout,QCheckBox,QScrollArea
from .metadata_inputs import MetadataInput

class MetadataEditor(QWidget):
    applied=Signal(object,str)
    draftChanged=Signal(object)
    closed=Signal()
    def __init__(self,target,value,draft=None,parent=None):
        super().__init__(parent); self.target=target; self.original=value
        outer=QVBoxLayout(self); outer.setContentsMargins(10,8,10,8); outer.setSpacing(8)
        content=QWidget(); layout=QVBoxLayout(content); layout.setContentsMargins(2,2,10,6); layout.setSpacing(10); self.content_layout=layout
        self.content_scroll=QScrollArea(); self.content_scroll.setWidgetResizable(True); self.content_scroll.setMinimumHeight(40)
        self.content_scroll.setWidget(content); outer.addWidget(self.content_scroll,1)
        heading=QLabel('编辑 · '+target.label); heading.setObjectName('sectionTitle'); layout.addWidget(heading)
        original=QLabel('原值：'+('无' if value is None else '、'.join(map(str,value)) if isinstance(value,list) else str(value)));original.setWordWrap(True);layout.addWidget(original)
        destination=QLabel(('写入原生字段：' if target.strategy=='native' else '补充信息写入：' if target.strategy=='xmp' else '写入同名 XMP 附件：')+target.tag);destination.setWordWrap(True);layout.addWidget(destination)
        self.input=MetadataInput(target.kind,value,draft,not target.tag.startswith('QuickTime:')); layout.addWidget(self.input)
        for name in ('text','date','zone','latitude','longitude','altitude','include_altitude','values','entry','calendar_popup'):
            if hasattr(self.input,name):setattr(self,name,getattr(self.input,name))
        self.input.changed.connect(self.changed)
        self.error=QLabel();self.error.setWordWrap(True);self.error.setObjectName('inlineError');layout.addWidget(self.error)
        self.consent=QCheckBox('我选择补充信息；原生值不会因此被替换');self.consent.setVisible(target.strategy in {'xmp','sidecar'});layout.addWidget(self.consent)
        self.consent.toggled.connect(self.changed)
        row=QHBoxLayout();reset=QPushButton('撤销草稿');close=QPushButton('收起');delete=QPushButton('删除此字段')
        reset.clicked.connect(self.revert);close.clicked.connect(self.closed);delete.clicked.connect(self.delete_value)
        row.addWidget(reset);row.addWidget(delete);row.addWidget(close);outer.addLayout(row)
        apply=QPushButton('应用到待导出副本');apply.setObjectName('primary');apply.clicked.connect(self.commit);outer.addWidget(apply);layout.addStretch()
        if target.kind=='date' and value is not None:
            try:self.serialized()
            except ValueError:self.error.setText('原时间无法解析，请填写有效日期；不会自动替换为当前时间。')
    def serialized(self):return self.input.serialized()
    def changed(self,*args):self.draftChanged.emit(self.input.raw_state()|{'destination_confirmed':self.target.strategy=='native' or self.consent.isChecked()})
    def revert(self):self.draftChanged.emit('__RESET_DRAFT__');self.closed.emit()
    def consent_valid(self):
        if self.target.strategy in {'xmp','sidecar'} and not self.consent.isChecked():raise ValueError('请先确认选择补充信息写入位置')
    def commit(self):
        try:
            self.consent_valid();value=self.serialized()
            if value in ('','[]'):raise ValueError('未填写新值；如需删除，请使用“删除此字段”。')
            self.applied.emit(self.target,value)
        except ValueError as error:self.error.setText(str(error))
    def delete_value(self):
        try:self.consent_valid();self.applied.emit(self.target,'')
        except ValueError as error:self.error.setText(str(error))
