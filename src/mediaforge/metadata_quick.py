"""Chinese inline metadata form; the page owns the shared drafts and export state."""
from PySide6.QtCore import Qt,QSignalBlocker
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,QFrame,QApplication,QLayout,QSizePolicy
from .metadata_fields import FIELDS,field_value,resolve_field
from .metadata_inputs import MetadataInput

class QuickMetadataField(QFrame):
    def __init__(self,page,name,parent=None):
        super().__init__(parent);self.page=page;self.name=name;self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum);self.setObjectName('quickMetadataField')
        self.layout=QVBoxLayout(self);self.layout.setContentsMargins(12,8,12,10);self.layout.setSpacing(6)
        category,label,kind,tags,xmp=FIELDS[name]; row=QHBoxLayout()
        caption=QLabel(label);row.addWidget(caption);row.addStretch()
        self.destination=QComboBox();self.destination.setMinimumWidth(150)
        primary=resolve_field(name,page.record,page.extension());alternate=resolve_field(name,page.record,page.extension(),True)
        if primary.strategy!='native':self.destination.addItem('选择补充信息方式…',None)
        self.destination.addItem('原生字段' if primary.strategy=='native' else 'XMP 补充' if primary.strategy=='xmp' else '同名 XMP 附件',primary)
        if (alternate.tag,alternate.strategy)!=(primary.tag,primary.strategy):self.destination.addItem('XMP 补充' if alternate.strategy=='xmp' else '同名 XMP 附件',alternate)
        row.addWidget(self.destination)
        self.restore=QPushButton('恢复');self.delete=QPushButton('删除');row.addWidget(self.restore);row.addWidget(self.delete);self.layout.addLayout(row)
        self.input=None;self.error=QLabel();self.error.setObjectName('inlineError');self.error.setWordWrap(True);self.error.hide()
        self.detail=QLabel();self.detail.setObjectName('muted');self.detail.setWordWrap(True)
        self.original=field_value(name,page.record)
        # Previously selected supplemental destinations remain selected within this material/component.
        for i in range(self.destination.count()):
            target=self.destination.itemData(i)
            draft=page.drafts.get((page.job.id,max(0,page.component.currentIndex()),target.tag,target.strategy),{}) if target else {}
            if target and page.has_pending_target(target) and draft.get('destination_confirmed',True):self.destination.setCurrentIndex(i);break
        self.rebuild_input();self.layout.addWidget(self.detail);self.layout.addWidget(self.error)
        self.destination.currentIndexChanged.connect(self.change_destination)
        self.restore.clicked.connect(self.restore_value);self.delete.clicked.connect(self.delete_value)
    def target(self):return self.destination.currentData() or resolve_field(self.name,self.page.record,self.page.extension())
    def context(self):
        target=self.target();return (self.page.job.id,max(0,self.page.component.currentIndex()),target.tag,target.strategy)
    def current_value(self):
        return self.page.value_for_target(self.name,self.target())
    def rebuild_input(self):
        if self.input:self.layout.removeWidget(self.input);self.input.deleteLater()
        target=self.target();value=self.current_value();draft=self.page.drafts.get(self.context())
        self.input=MetadataInput(target.kind,value,draft,not target.tag.startswith('QuickTime:'))
        self.layout.insertWidget(1,self.input);self.input.changed.connect(self.edited)
        self.setToolTip(target.tag)
    def change_destination(self,*args):
        old=self.input.raw_state() if self.input else None
        self.rebuild_input()
        if old and self.input.kind!='list' and 'text' in old:self.input.set_value(old['text'])
        self.detail.setText('原生字段会直接修改输出副本。' if self.target().strategy=='native' else '补充信息单独标注，不替代原生值；选定此方式后才会加入修改。')
        self.edited()
    def edited(self):
        context=self.context();target=self.target()
        self.page.drafts[context]=self.input.raw_state()|{'destination_confirmed':self.destination.currentData() is not None};self.page.draft_targets[context]=target
        if self.destination.currentData() is None:
            self.error.setText('请先选择 XMP 补充或附件方式。');self.error.show();self.page.update_pending();return
        try:
            value=self.input.serialized()
            if value in ('','[]'):
                self.page.restore_field(self.name,refresh=False)
                self.error.hide();self.page.update_views();return
            if self.page.apply_editor(context,target,value,origin='easy'):
                self.error.hide()
            else:self.error.setText(self.page.last_edit_error);self.error.show()
        except ValueError as error:self.error.setText(str(error));self.error.show();self.page.update_pending()
    def restore_value(self):
        self.page.restore_field(self.name)
        self.input.set_value(field_value(self.name,self.page.record));self.error.hide()
    def delete_value(self):
        if self.destination.currentData() is None:
            self.error.setText('请先选择要删除信息的写入位置。');self.error.show();return
        if self.page.apply_editor(self.context(),self.target(),'',origin='easy'):
            self.input.set_value(None);self.error.hide()
    def sync(self):
        focused=self.input.isAncestorOf(QApplication.focusWidget()) if QApplication.focusWidget() else False
        if not focused:self.input.set_value(self.current_value(),self.page.drafts.get(self.context()))
        target=self.target();self.restore.setEnabled(self.page.has_pending_target(target)); self.delete.setEnabled(target.tag in self.page.record or self.page.has_pending_target(target));self.detail.setText('原值：'+('无' if self.original is None else str(self.original))+' · '+('修改原生字段' if target.strategy=='native' else 'XMP 补充；原生值保留' if target.strategy=='xmp' else 'XMP 附件；媒体原生值保留'))

class QuickMetadataForm(QWidget):
    def __init__(self,page):
        super().__init__();self.page=page;self.context_key=None;self.fields={}
        self.layout=QVBoxLayout(self);self.layout.setContentsMargins(0,4,10,8);self.layout.setSpacing(8);self.layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
    def refresh(self):
        page=self.page;key=(page.job.id if page.job else None,max(0,page.component.currentIndex()),id(page.record))
        if key!=self.context_key:
            self.context_key=key;self.fields={}
            while self.layout.count():
                item=self.layout.takeAt(0)
                if item.widget():item.widget().hide(); item.widget().deleteLater()
            if not page.job or not page.record:
                self.layout.addWidget(QLabel('添加素材并读取完成后，可直接填写需要修改的信息。'));self.layout.addStretch();return
            note=QLabel('直接填写即加入修改；留空保留原值。需要删除信息时使用字段旁的“删除”。');note.setObjectName('muted');note.setWordWrap(True);self.layout.addWidget(note)
            for group in ('拍摄时间','设备与镜头','地点','作者'):
                title=QLabel('作者与说明' if group=='作者' else group);title.setObjectName('parameterHeading');self.layout.addWidget(title)
                for name,(category,*_) in FIELDS.items():
                    if category!=group:continue
                    field=QuickMetadataField(page,name);self.fields[name]=field;self.layout.addWidget(field)
            self.layout.addStretch()
        query=page.search.text().casefold()
        for name,field in self.fields.items():
            field.sync();field.setVisible(not query or query in (' '.join(map(str,FIELDS[name]))+' '+str(field.current_value())).casefold())
