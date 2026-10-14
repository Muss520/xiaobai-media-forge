"""Offline author and support cards; payment code pixels remain untouched."""
from pathlib import Path
import shutil
from PySide6.QtCore import Qt,QSize,QEvent,QTimer,Slot
from PySide6.QtGui import QPixmap,QPainter
from PySide6.QtWidgets import (QApplication,QWidget,QFrame,QLabel,QPushButton,QVBoxLayout,
    QHBoxLayout,QGridLayout,QSizePolicy,QDialog,QFileDialog,QBoxLayout)
from .paths import resource_home
from .product import NAME,VERSION,AUTHOR,EMAIL


class CodePreview(QPushButton):
    def __init__(self,path,parent=None):
        super().__init__(parent)
        self.pixmap=QPixmap(str(path))
        self.setObjectName('qrPreview')
        self.setAccessibleName('收款二维码，点击放大查看')
        self.setToolTip('点击放大查看二维码')
        self.setMinimumSize(200,200)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Expanding)

    def sizeHint(self):return QSize(248,248)

    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self)
        # No smoothing, cropping, animation or decoration inside the code canvas.
        side=max(1,min(self.width(),self.height())-16)
        image=self.pixmap.scaled(side,side,Qt.KeepAspectRatio,Qt.FastTransformation)
        painter.drawPixmap((self.width()-image.width())//2,(self.height()-image.height())//2,image)


class SupportCard(QFrame):
    def __init__(self,title,asset,channel,parent=None):
        super().__init__(parent)
        self.image_path=resource_home()/'assets/support'/asset
        self.dialog=None
        self.setObjectName('supportCard')
        layout=QVBoxLayout(self);layout.setContentsMargins(16,16,16,16);layout.setSpacing(10)
        heading=QLabel(title);heading.setObjectName(channel+'Heading');layout.addWidget(heading)
        self.preview=CodePreview(self.image_path);self.preview.setMaximumHeight(300)
        self.preview.clicked.connect(self.open_large);layout.addWidget(self.preview)
        hint=QLabel('用'+('微信' if channel=='wechat' else '支付宝')+'扫一扫 · 自愿支持')
        hint.setObjectName('muted');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout()
        zoom=QPushButton('放大查看');zoom.clicked.connect(self.open_large)
        save=QPushButton('保存二维码');save.clicked.connect(self.save_code)
        row.addWidget(zoom);row.addWidget(save);layout.addLayout(row)
        self.message=QLabel();self.message.setWordWrap(True);self.message.hide();layout.addWidget(self.message)

    def open_large(self):
        if self.dialog is not None:
            self.dialog.showNormal();self.dialog.raise_();self.dialog.activateWindow();return
        dialog=QDialog(self,Qt.Window|Qt.WindowMaximizeButtonHint|Qt.WindowCloseButtonHint)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowTitle('二维码 · '+NAME)
        layout=QVBoxLayout(dialog);layout.setContentsMargins(20,20,20,20)
        code=CodePreview(self.image_path);code.setToolTip('原始二维码 · 保持完整白边')
        code.setAccessibleName('放大收款二维码');layout.addWidget(code,1)
        hint=QLabel('请确认收款对象后，自愿选择打赏金额。');hint.setWordWrap(True);layout.addWidget(hint)
        row=QHBoxLayout();save=QPushButton('保存二维码');save.clicked.connect(self.save_code)
        close=QPushButton('关闭');close.clicked.connect(dialog.close)
        row.addWidget(save);row.addStretch();row.addWidget(close);layout.addLayout(row)
        dialog.setMinimumSize(320,400);dialog.resize(520,620)
        rect=dialog.screen().availableGeometry();dialog.resize(min(dialog.width(),rect.width()-32),min(dialog.height(),rect.height()-32))
        self.dialog=dialog
        # Release on finished, while both widgets are alive. A destroyed lambda
        # can re-enter Python ownership while Qt tears down the parent card.
        dialog.finished.connect(self._clear_dialog)
        dialog.show()

    @Slot()
    def _clear_dialog(self):self.dialog=None

    def save_code(self):
        filename,_=QFileDialog.getSaveFileName(self,'保存二维码',self.image_path.name,'PNG 图片 (*.png)')
        if not filename:return
        path=Path(filename)
        if path.suffix.lower()!='.png':path=path.with_name(path.name+'.png')
        try:
            if path.resolve()!=self.image_path.resolve():shutil.copyfile(self.image_path,path)
            self.message.setText('已保存二维码');self.message.setObjectName('muted')
        except OSError as error:
            self.message.setText(f'保存失败：{error}');self.message.setObjectName('inlineError')
        self.message.setToolTip(str(path));self.message.show()


class AuthorPage(QWidget):
    def __init__(self,parent=None):
        super().__init__(parent)
        root=QVBoxLayout(self);root.setContentsMargins(12,12,20,16);root.setSpacing(16)
        intro=QFrame();intro.setObjectName('authorCard');row=QHBoxLayout(intro);self.intro_layout=row
        row.setContentsMargins(18,18,18,18);row.setSpacing(14)
        icon=QLabel();icon.setPixmap(QPixmap(str(resource_home()/'assets/xiaobai-logo.png')).scaled(64,64,Qt.KeepAspectRatio,Qt.FastTransformation))
        icon.setFixedSize(68,68);icon.setAlignment(Qt.AlignCenter);row.addWidget(icon,0,Qt.AlignTop)
        details=QVBoxLayout()
        name=QLabel(NAME+'  '+VERSION);name.setObjectName('authorTitle');name.setWordWrap(True);details.addWidget(name)
        self.author_label=QLabel('作者：'+AUTHOR);details.addWidget(self.author_label)
        email=QLabel(EMAIL);email.setWordWrap(True);email.setTextInteractionFlags(Qt.TextSelectableByMouse);details.addWidget(email)
        self.copy_button=QPushButton('复制邮箱');self.copy_button.clicked.connect(self.copy_email);details.addWidget(self.copy_button,0,Qt.AlignLeft)
        self.copy_status=QLabel();self.copy_status.setWordWrap(True);self.copy_status.setObjectName('muted');self.copy_status.hide();details.addWidget(self.copy_status)
        row.addLayout(details,1);root.addWidget(intro)
        thanks=QLabel('如果小白帮到了你，可以请作者喝杯茶。谢谢你的支持。')
        thanks.setWordWrap(True);thanks.setObjectName('muted');root.addWidget(thanks)
        self.cards_area=QWidget();self.grid=QGridLayout(self.cards_area)
        self.grid.setContentsMargins(0,0,0,0);self.grid.setSpacing(16)
        self.cards=[SupportCard('微信打赏','wechat.png','wechat'),SupportCard('支付宝打赏','alipay.png','alipay')]
        for index,card in enumerate(self.cards):self.grid.addWidget(card,index,0)
        self.columns=1;root.addWidget(self.cards_area);root.addStretch()
        self.copy_timer=QTimer(self);self.copy_timer.setSingleShot(True);self.copy_timer.timeout.connect(self.copy_status.hide)

    def copy_email(self):
        clipboard=QApplication.clipboard();clipboard.setText(EMAIL)
        okay=clipboard.text()==EMAIL
        self.copy_status.setText('邮箱已复制' if okay else '未能复制，请重试或选中邮箱手动复制')
        self.copy_status.show();self.copy_timer.start(2200)
        return okay

    def resizeEvent(self,event):
        super().resizeEvent(event);self.reflow()

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange):QTimer.singleShot(0,self.reflow)

    def reflow(self):
        if not hasattr(self,'cards'):return
        self.intro_layout.setDirection(QBoxLayout.TopToBottom if self.width()<560 else QBoxLayout.LeftToRight)
        width=max(card.minimumSizeHint().width() for card in self.cards)
        columns=2 if self.width()>=2*width+52 else 1
        if columns==self.columns:return
        self.columns=columns
        for index,card in enumerate(self.cards):
            self.grid.removeWidget(card);self.grid.addWidget(card,index//columns,index%columns)
        self.grid.setColumnStretch(0,1);self.grid.setColumnStretch(1,1 if columns==2 else 0)
