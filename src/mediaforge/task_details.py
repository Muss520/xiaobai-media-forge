"""Compact task summary with a single reusable full-detail window."""
from PySide6.QtCore import Qt,QEvent
from PySide6.QtWidgets import QFrame,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QDialog,QTextBrowser,QSizePolicy,QLayout

def parameter_details(value,title='输出参数'):
    from dataclasses import asdict,is_dataclass
    if not is_dataclass(value):return []
    names={'format':'格式','mode':'控制方式','quality':'质量','codec':'视频编码','encoder':'编码设备','speed':'编码速度','bitrate':'平均码率 kbps','width':'宽度边界 px','height':'高度边界 px','fps':'帧率 fps','aspect':'保持比例','upscale':'允许放大','target_bytes':'体积上限 bytes','audio_codec':'音频设置','audio_bitrate':'音频码率 kbps','sample_rate':'采样率 Hz','channels':'声道','pixel_format':'像素格式','profile':'编码规格','keyframe_interval':'关键帧间隔','metadata':'保留元数据','remux':'直接封装','resolution_preset':'分辨率预设','png_level':'PNG压缩级别','lossless':'无损','background':'透明背景色','animation':'帧处理','frame_index':'指定帧','auto_resize':'允许自动缩小','animation_fps':'动图帧率'}
    lines=['',title]
    for key,item in asdict(value).items():
        if key in {'image','video'}:
            if key=='video' and (getattr(value,'mode','')=='preserve' or getattr(value,'video_copy',False) and getattr(value,'mode','')=='both'):
                lines.append('视频设置：原始MOV字节复制，编码/分辨率/码率均不改变');continue
            if key=='image' and getattr(value,'mode','')=='video':continue
            if key=='video' and getattr(value,'mode','') in {'image','animation'}:continue
            lines.extend(parameter_details(getattr(value,key),'照片设置' if key=='image' else '视频设置'))
        elif key in names:lines.append(names[key]+'：'+('是' if item is True else '否' if item is False else str(item)))
    return lines

class ElidedLabel(QLabel):
    def __init__(self):
        super().__init__();self.full_text='';self.setMinimumWidth(0);self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Preferred)
    def setText(self,text):
        self.full_text=text;self.setToolTip(text);self.update_elision()
    def update_elision(self):super().setText(self.fontMetrics().elidedText(self.full_text,Qt.ElideMiddle,max(20,self.contentsRect().width())))
    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange):self.setMinimumHeight(self.fontMetrics().height()+2);self.update_elision()
    def resizeEvent(self,event):super().resizeEvent(event);self.update_elision()

class TaskDetails(QFrame):
    def __init__(self):
        super().__init__();self.setObjectName('taskSummaryCard');self.dialog=None;self.full_text=''
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Minimum)
        layout=QVBoxLayout(self);layout.setContentsMargins(12,8,12,8);layout.setSpacing(5)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        top=QHBoxLayout();self.title=ElidedLabel();top.addWidget(self.title,1)
        more=QPushButton('查看完整详情');more.setObjectName('compactAction');more.clicked.connect(self.open_details);top.addWidget(more);layout.addLayout(top)
        self.original=ElidedLabel();self.output=ElidedLabel();layout.addWidget(self.original);layout.addWidget(self.output)
    def setText(self,text):
        self.full_text=text;lines=text.splitlines();self.title.setText(lines[0] if lines else '')
        self.original.setText('原始素材  ·  '+(lines[1] if len(lines)>1 else '未知'))
        outputs=[line for line in lines[2:] if line.startswith(('输出：','视频：','已导出：'))]
        outputs=[line.removeprefix('输出：').partition('  /  最终体积')[0] for line in outputs]
        self.output.setText('本次输出  ·  '+('；'.join(outputs) if outputs else '读取中'))
        if self.dialog:self.browser.setPlainText(text)
        self.updateGeometry()
    def text(self):return self.full_text
    def open_details(self):
        if self.dialog:self.dialog.showNormal() if self.dialog.isMinimized() else self.dialog.show();self.dialog.raise_();self.dialog.activateWindow();return
        dialog=QDialog(self.window(),Qt.Window|Qt.WindowMaximizeButtonHint|Qt.WindowCloseButtonHint);self.dialog=dialog
        dialog.setWindowTitle('任务完整详情');dialog.setAttribute(Qt.WA_DeleteOnClose)
        layout=QVBoxLayout(dialog);self.browser=QTextBrowser();self.browser.setPlainText(self.full_text);layout.addWidget(self.browser)
        close=QPushButton('完成');close.clicked.connect(dialog.close);layout.addWidget(close,0,Qt.AlignRight)
        dialog.finished.connect(lambda:self.release_dialog())
        available=self.screen().availableGeometry();dialog.resize(min(840,available.width()-40),min(650,available.height()-60));dialog.show()
    def release_dialog(self):self.dialog=None
