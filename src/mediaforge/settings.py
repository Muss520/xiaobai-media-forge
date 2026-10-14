from .paths import runtime_home
"""One nonmodal settings window with immediate, durable preferences."""
from pathlib import Path
from PySide6.QtCore import Qt,QSignalBlocker,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QTabWidget,QWidget,
    QScrollArea,QFormLayout,QLabel,QPushButton,QCheckBox,QSlider,QLineEdit,QFileDialog)
from .options import combo,select,spin
from .preferences import normalize_ui
from .product import NAME
from .widgets import WrappedCheckBox as QCheckBox


class SettingsDialog(QDialog):
    def __init__(self,controller):
        super().__init__(controller.window,Qt.Window)
        self.controller=controller; self.window=controller.window; self._syncing=True
        self.setWindowTitle('设置 · '+NAME)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setStyleSheet(self.window.styleSheet())
        root=QVBoxLayout(self); root.setContentsMargins(22,18,22,18); root.setSpacing(14)
        title=QLabel('让工坊更合你的习惯'); title.setObjectName('sectionTitle'); root.addWidget(title)
        self.tabs=QTabWidget(); root.addWidget(self.tabs,1)
        appearance=self.page('界面','appearance')
        self.density=combo([('舒适 · 更多留白','comfortable'),('紧凑 · 显示更多内容','compact')])
        self.text_size=combo([('较小','small'),('标准','standard'),('较大','large')])
        self.navigation=combo([('窄','narrow'),('标准','standard'),('宽','wide')])
        for label,widget in [('布局密度',self.density),('文字大小',self.text_size),('导航宽度',self.navigation)]:
            appearance.addRow(label,widget); widget.currentIndexChanged.connect(self.apply_ui)
        self.font_points=spin(12,20,12,' pt')
        self.spacing=spin(6,24,12,' px')
        self.navigation_width=spin(110,220,150,' px')
        for label,widget in [('自定义文字',self.font_points),('表单间距',self.spacing),('自定义导航宽度',self.navigation_width)]:
            appearance.addRow(label,widget); widget.valueChanged.connect(self.apply_ui)
        self.density.currentIndexChanged.connect(lambda:self.apply_scale_preset('density'))
        self.text_size.currentIndexChanged.connect(lambda:self.apply_scale_preset('text'))
        self.navigation.currentIndexChanged.connect(lambda:self.apply_scale_preset('navigation'))
        self.detailed_columns=QCheckBox('任务表显示尺寸、格式和详细压缩结果')
        appearance.addRow(self.detailed_columns); self.detailed_columns.toggled.connect(self.apply_ui)
        self.motion=QCheckBox('减少动画'); appearance.addRow('',self.motion)
        self.motion.toggled.connect(self.apply_ui)
        reset_split=QPushButton('重置工作台左右比例')
        reset_split.clicked.connect(self.reset_splitters); appearance.addRow('',reset_split)
        appearance.addRow(QLabel('每次启动进入小白模式；转换参数在小白和专业模式共享。'))
        pet=self.page('小白','pet')
        self.cat_visible=QCheckBox('显示桌面小白'); pet.addRow('',self.cat_visible)
        size_widget=QWidget(); size_layout=QVBoxLayout(size_widget); size_layout.setContentsMargins(0,0,0,0)
        self.cat_size=QSlider(Qt.Horizontal); self.cat_size.setRange(2,6)
        self.cat_size.setTickPosition(QSlider.TicksBelow); self.cat_size.setTickInterval(1)
        self.size_label=QLabel(); size_layout.addWidget(self.cat_size); size_layout.addWidget(self.size_label)
        pet.addRow('小白大小',size_widget)
        self.progress=QCheckBox('在小白旁显示转换进度'); pet.addRow('',self.progress)
        self.cat_visible.toggled.connect(self.apply_pet); self.cat_size.valueChanged.connect(self.apply_pet)
        self.progress.toggled.connect(self.apply_pet)
        position=QPushButton('把小白放回屏幕右下角'); position.clicked.connect(self.reset_position)
        pet.addRow('',position)
        pet.addRow(QLabel('像素整数倍缩放，保持轮廓清晰；透明区域不拦截鼠标。'))
        self.activity=combo([('安静 · 20–40秒','quiet'),('标准 · 10–25秒','standard'),('活泼 · 5–15秒','lively')]);pet.addRow('待机活跃程度',self.activity)
        self.hover_reactions=QCheckBox('鼠标停留时抬头或抖耳');pet.addRow(self.hover_reactions)
        self.games_enabled=QCheckBox('开启小白游乐场');pet.addRow(self.games_enabled)
        for widget in (self.hover_reactions,self.games_enabled):widget.toggled.connect(self.apply_companion)
        self.activity.currentIndexChanged.connect(self.apply_companion)
        from .companion import ACTION_LABELS
        preview_row=QWidget();preview_layout=QHBoxLayout(preview_row);preview_layout.setContentsMargins(0,0,0,0)
        self.action_preview=combo([(label,name) for name,label in ACTION_LABELS.items() if name not in {'idle','pounce','catch'}])
        preview_action=QPushButton('在桌面预览');preview_action.clicked.connect(self.preview_pet)
        preview_layout.addWidget(self.action_preview,1);preview_layout.addWidget(preview_action);pet.addRow('动作预览',preview_row)
        instructions=QLabel('单击摸头，双击打开主界面，按住拖动位置。\n右键可喂零食、蹭蹭、叫一声或进入逗猫棒/抛接球。转换和投喂时小白会先工作。')
        instructions.setWordWrap(True);pet.addRow(instructions)
        sound=self.page('声音','sound')
        self.sounds=QCheckBox('开启声音'); sound.addRow(self.sounds); self.sounds.toggled.connect(self.apply_feedback)
        volume_row=QWidget(); volume_layout=QHBoxLayout(volume_row);volume_layout.setContentsMargins(0,0,0,0)
        self.volume=QSlider(Qt.Horizontal); self.volume.setRange(0,100);self.volume.setAccessibleName('音效音量')
        self.volume_label=QLabel();self.volume_label.setMinimumWidth(64);self.volume_label.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
        volume_layout.addWidget(self.volume,1);volume_layout.addWidget(self.volume_label)
        sound.addRow('总音量',volume_row); self.volume.valueChanged.connect(self.apply_feedback)
        self.group_controls={}
        for key,label,cue in [('conversion','转换提示','complete'),('pet','宠物互动','pet_touch'),('game','游戏音效','catch')]:
            box=QWidget();column=QVBoxLayout(box);column.setContentsMargins(0,0,0,0);column.setSpacing(6)
            enabled=QCheckBox(label);column.addWidget(enabled)
            row=QHBoxLayout();slider=QSlider(Qt.Horizontal);slider.setRange(0,100);slider.setAccessibleName(label+'相对音量')
            value=QLabel();value.setMinimumWidth(64);value.setAlignment(Qt.AlignRight|Qt.AlignVCenter)
            row.addWidget(slider,1);row.addWidget(value);column.addLayout(row)
            preview=QPushButton('试听'+label);preview.clicked.connect(lambda checked=False,cue=cue:controller.sounds.play(cue,preview=True));column.addWidget(preview)
            self.group_controls[key]=(enabled,slider,value);sound.addRow(box)
            enabled.toggled.connect(self.apply_feedback);slider.valueChanged.connect(self.apply_feedback)
        self.cat_voice=QCheckBox('允许轻喵和呼噜');self.idle_voice=QCheckBox('允许待机偶尔发声 · 至少间隔60秒')
        sound.addRow(self.cat_voice);sound.addRow(self.idle_voice)
        self.cat_voice.toggled.connect(self.apply_feedback);self.idle_voice.toggled.connect(self.apply_feedback)
        meow_preview=QPushButton('试听小白的轻喵');meow_preview.clicked.connect(lambda:controller.sounds.play('meow',preview=True));sound.addRow(meow_preview)
        note=QLabel('分类音量相对于总音量。静音即时停止；转换完成/失败提示优先。猫叫间隔至少8秒，待机默认安静。');note.setWordWrap(True);sound.addRow(note)
        usage=self.page('保存与使用','usage')
        self.sibling=QCheckBox('专业模式：原文件旁新建结果文件夹'); usage.addRow('',self.sibling)
        self.prefix=QLineEdit(); usage.addRow('结果文件夹前缀',self.prefix); self.prefix.editingFinished.connect(self.apply_usage)
        self.notifications=QCheckBox('完成后显示通知'); self.auto_open=QCheckBox('完成后自动打开结果文件夹')
        for widget in (self.notifications,self.auto_open):usage.addRow(widget); widget.toggled.connect(self.apply_feedback)
        out=QWidget(); out_layout=QHBoxLayout(out); out_layout.setContentsMargins(0,0,0,0)
        self.output=QLineEdit(); choose=QPushButton('选择')
        choose.clicked.connect(self.choose_directory); out_layout.addWidget(self.output,1); out_layout.addWidget(choose)
        usage.addRow('指定输出目录',out)
        self.sibling.toggled.connect(self.apply_usage); self.output.editingFinished.connect(self.apply_usage)
        self.quick={}
        from .options import VideoPanel,ImagePanel,LivePanel
        for kind,label,klass in [('video','视频',VideoPanel),('image','图片',ImagePanel),('live','Live Photo',LivePanel)]:
            source=klass(); source.setParent(self); source.hide()
            fmt=combo([(source.format.itemText(i),source.format.itemData(i)) for i in range(source.format.count())])
            preset=combo([('均衡','balanced'),('高清','high'),('体积优先','small')])
            usage.addRow('小白 '+label+' 格式',fmt); usage.addRow('小白 '+label+' 预设',preset)
            mode=None
            if kind=='live':
                mode=combo([(source.mode.itemText(i),source.mode.itemData(i)) for i in range(source.mode.count())])
                mode.currentIndexChanged.connect(lambda:self.refresh_live_formats())
                usage.addRow('小白 Live 导出方式',mode)
            self.quick[kind]=(fmt,preset,mode,source)
            fmt.currentIndexChanged.connect(self.apply_quick); preset.currentIndexChanged.connect(self.apply_quick)
        info=QLabel('小白模式与桌面小白始终默认按原目录归组。\n关窗后继续后台运行；右键小白或托盘可彻底退出。')
        info.setWordWrap(True); usage.addRow(info)
        for label,path in [('打开配置目录',self.window.settings_path.parent),('打开日志目录',runtime_home()/'logs')]:
            button=QPushButton(label); button.clicked.connect(lambda checked=False,p=path:QDesktopServices.openUrl(QUrl.fromLocalFile(str(p))))
            usage.addRow('',button)
        quit_button=QPushButton('彻底退出软件'); quit_button.clicked.connect(controller.request_exit); usage.addRow('',quit_button)
        from .support import AuthorPage
        self.author_page=AuthorPage()
        author_scroll=QScrollArea();author_scroll.setWidgetResizable(True);author_scroll.setWidget(self.author_page)
        author_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);author_scroll.setProperty('settingsPage','author')
        self.tabs.addTab(author_scroll,'作者与打赏')
        footer=QVBoxLayout(); self.save_status=QLabel('设置即时生效并保存'); self.save_status.setWordWrap(True)
        footer.addWidget(self.save_status)
        self.reset_button=QPushButton('恢复本页默认'); self.reset_button.clicked.connect(lambda:self.reset_page(self.tabs.currentIndex()))
        done=QPushButton('完成'); done.setObjectName('primary'); done.clicked.connect(self.close)
        buttons=QHBoxLayout();buttons.addStretch();buttons.addWidget(self.reset_button);buttons.addWidget(done)
        footer.addLayout(buttons);root.addLayout(footer)
        self.tabs.currentChanged.connect(self.page_changed)
        self.resize(800,740); self.setMinimumSize(480,400)
        self.sync(); self._syncing=False
        self.window.reduce_motion.toggled.connect(self.reflect_motion)
        self.window.sibling_output.toggled.connect(self.reflect_sibling)
        self.window.output.textChanged.connect(self.output.setText)

    def page(self,title,page_id):
        body=QWidget(); form=QFormLayout(body); form.setContentsMargins(16,18,16,18); form.setSpacing(14)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows); form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        scroll=QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(body)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff);scroll.setProperty('settingsPage',page_id)
        for label in body.findChildren(QLabel):label.setWordWrap(True)
        self.tabs.addTab(scroll,title); return form

    def page_changed(self,*args):
        author=self.tabs.currentWidget().property('settingsPage')=='author'
        self.reset_button.setVisible(not author)
        self.save_status.setText('感谢你陪小白一起成长' if author else '设置即时生效并保存')

    def page_index(self,page_id):
        return next((i for i in range(self.tabs.count()) if self.tabs.widget(i).property('settingsPage')==page_id),-1)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.update_forms()

    def changeEvent(self,event):
        super().changeEvent(event)
        from PySide6.QtCore import QEvent,QTimer
        if event.type() in (QEvent.FontChange,QEvent.StyleChange):QTimer.singleShot(0,self.update_forms)

    def update_forms(self):
        if not hasattr(self,'tabs'):return
        for index in range(self.tabs.count()):
            scroll=self.tabs.widget(index)
            form=scroll.widget().layout()
            if not isinstance(form,QFormLayout):continue
            wrap=scroll.viewport().width()<680 or self.fontMetrics().height()>26
            form.setRowWrapPolicy(QFormLayout.WrapAllRows if wrap else QFormLayout.WrapLongRows)
            for row in range(form.rowCount()):
                item=form.itemAt(row,QFormLayout.LabelRole)
                label=item.widget() if item else None
                if isinstance(label,QLabel):label.setWordWrap(True)
            for label in scroll.widget().findChildren(QLabel):label.setWordWrap(True)

    def sync(self):
        self._syncing=True
        for key,widget in [('density',self.density),('text_size',self.text_size),('navigation',self.navigation)]:
            select(widget,self.window.ui_preferences[key])
        self.motion.setChecked(self.window.reduce_motion.isChecked())
        for key in ('font_points','spacing','navigation_width'):getattr(self,key).setValue(self.window.ui_preferences[key])
        self.detailed_columns.setChecked(self.window.ui_preferences.get('detailed_columns',False))
        prefs=self.controller.preferences
        self.prefix.setText(prefs.get('folder_prefix','转换结果'))
        self.sounds.setChecked(prefs.get('sounds',True)); self.volume.setValue(prefs.get('sound_volume',20)); self.volume_label.setText(f'{self.volume.value()}%')
        for key,(enabled,slider,label) in self.group_controls.items():
            group=prefs['sound_groups'][key];enabled.setChecked(group['enabled']);slider.setValue(group['volume']);label.setText(f"{group['volume']}%")
        self.cat_voice.setChecked(prefs.get('cat_voice',True));self.idle_voice.setChecked(prefs.get('idle_voice',False))
        select(self.activity,prefs.get('idle_activity','standard'))
        self.hover_reactions.setChecked(prefs.get('hover_reactions',True));self.games_enabled.setChecked(prefs.get('games_enabled',True))
        self.notifications.setChecked(prefs.get('notifications',True)); self.auto_open.setChecked(prefs.get('open_results',False))
        self.cat_visible.setChecked(self.controller.preferences.get('visible',True))
        self.cat_size.setValue(self.controller.pet.scale); self.update_size_label()
        self.progress.setChecked(self.controller.preferences.get('show_progress',True))
        self.sibling.setChecked(self.window.sibling_output.isChecked()); self.output.setText(self.window.output.text())
        self.output.setToolTip(self.output.text())
        self.sync_quick()
        self._syncing=False

    def sync_quick(self):
        previous=self._syncing; self._syncing=True
        defaults={'video':'mp4','image':'jpg','live':'png'}
        for kind,(fmt,preset,mode,source) in self.quick.items():
            saved=self.controller.preferences.get('quick',{}).get(kind,{})
            if not isinstance(saved,dict): saved={}
            if mode:
                select(mode,saved.get('mode','both'))
                self.refresh_live_formats(save=False)
            select(fmt,saved.get('format',defaults[kind])); select(preset,saved.get('preset','balanced'))
        self._syncing=previous

    def reflect_motion(self,value):
        guard=QSignalBlocker(self.motion); self.motion.setChecked(value)

    def reflect_sibling(self,value):
        guard=QSignalBlocker(self.sibling); self.sibling.setChecked(value)

    def update_size_label(self):
        scale=self.cat_size.value()
        self.size_label.setText(f'{scale}× 像素 · {round(100*scale/3)} × {round(110*scale/3)} · 默认 3×')

    def save(self):
        okay=self.window.save_settings()
        self.save_status.setText('设置已保存' if okay else '保存失败：请检查软件目录的写入权限')
        self.save_status.setObjectName('muted' if okay else 'inlineError')
        self.save_status.style().unpolish(self.save_status); self.save_status.style().polish(self.save_status)

    def apply_ui(self,*args):
        if self._syncing:return
        self.window.ui_preferences.update(density=self.density.currentData(),text_size=self.text_size.currentData(),navigation=self.navigation.currentData())
        for key in ('font_points','spacing','navigation_width'):self.window.ui_preferences[key]=getattr(self,key).value()
        self.window.ui_preferences['detailed_columns']=self.detailed_columns.isChecked()
        self.window.reduce_motion.setChecked(self.motion.isChecked())
        self.controller.apply_appearance(); self.save()

    def apply_scale_preset(self,kind):
        if self._syncing:return
        if kind=='density':self.spacing.setValue(6 if self.density.currentData()=='compact' else 16)
        elif kind=='text':self.font_points.setValue({'small':12,'standard':14,'large':18}[self.text_size.currentData()])
        else:self.navigation_width.setValue({'narrow':110,'standard':150,'wide':220}[self.navigation.currentData()])

    def apply_feedback(self,*args):
        if self._syncing:return
        self.controller.preferences.update(sounds=self.sounds.isChecked(),sound_volume=self.volume.value(),notifications=self.notifications.isChecked(),open_results=self.auto_open.isChecked())
        self.controller.preferences['sound_groups']={key:{'enabled':enabled.isChecked(),'volume':slider.value()} for key,(enabled,slider,label) in self.group_controls.items()}
        self.controller.preferences.update(cat_voice=self.cat_voice.isChecked(),idle_voice=self.idle_voice.isChecked())
        for enabled,slider,label in self.group_controls.values():label.setText(f'{slider.value()}%')
        self.controller.sounds.apply_preferences()
        self.volume_label.setText(f'{self.volume.value()}%'); self.save()

    def apply_companion(self,*args):
        if self._syncing:return
        self.controller.preferences.update(idle_activity=self.activity.currentData(),hover_reactions=self.hover_reactions.isChecked(),games_enabled=self.games_enabled.isChecked())
        if not self.games_enabled.isChecked():self.controller.stop_play()
        self.controller.pet.hover_timer.stop();self.controller.pet.unblink();self.save()

    def preview_pet(self):
        if not self.controller.pet.isVisible():self.save_status.setText('请先开启“显示桌面小白”再预览');return
        if not self.controller.can_play() or self.controller.play_dialog:self.save_status.setText('小白正在忙，空闲后再预览动作');return
        self.controller.pet.interact(self.action_preview.currentData())

    def apply_pet(self,*args):
        if self._syncing:return
        prefs=self.controller.preferences
        prefs.update(scale=self.cat_size.value(),visible=self.cat_visible.isChecked(),show_progress=self.progress.isChecked())
        self.controller.pet.set_scale(self.cat_size.value())
        self.controller.pet.setVisible(self.cat_visible.isChecked())
        self.controller.pet.update_progress(); self.controller.reposition_cards()
        self.update_size_label(); self.controller.save_position(); self.save()

    def refresh_live_formats(self,save=True):
        if 'live' not in self.quick:return
        fmt,preset,mode,source=self.quick['live']; previous=fmt.currentData()
        select(source.mode,mode.currentData())
        guard=QSignalBlocker(fmt); fmt.clear()
        for i in range(source.format.count()): fmt.addItem(source.format.itemText(i),source.format.itemData(i))
        select(fmt,previous); del guard
        if save:self.apply_quick()

    def apply_usage(self,*args):
        if self._syncing:return
        from .workflow import validate_folder_name
        try:self.controller.preferences['folder_prefix']=validate_folder_name(self.prefix.text().strip())
        except ValueError as error:self.save_status.setText(str(error)); return
        self.window.sibling_output.setChecked(self.sibling.isChecked())
        self.window.output.setText(self.output.text()); self.output.setToolTip(self.output.text())
        self.save()

    def apply_quick(self,*args):
        if self._syncing:return
        previous=self.controller.preferences.get('quick',{})
        self.controller.preferences['quick']={kind:{**previous.get(kind,{}),'format':fmt.currentData(),'preset':preset.currentData(),**({'mode':mode.currentData()} if mode else {})} for kind,(fmt,preset,mode,source) in self.quick.items()}
        self.save()

    def choose_directory(self):
        selected=QFileDialog.getExistingDirectory(self,'选择输出目录',self.output.text())
        if selected:self.output.setText(selected); self.apply_usage()

    def reset_splitters(self):
        self.window.ui_preferences['splitters']={}
        self.window.apply_splitters(); self.save()

    def reset_position(self):
        pet=self.controller.pet; rect=pet.screen().availableGeometry()
        pet.move(rect.right()-pet.width()-30,rect.bottom()-pet.height()-30)
        pet.clamp_position(); self.controller.save_position(); self.controller.reposition_cards()

    def reset_page(self,page):
        if isinstance(page,int):page=self.tabs.widget(page).property('settingsPage') if 0<=page<self.tabs.count() else None
        if page=='appearance':
            self.window.ui_preferences=normalize_ui({}); self.window.reduce_motion.setChecked(False)
            self.window.apply_splitters(); self.controller.apply_appearance()
        elif page=='pet':
            self.controller.preferences.update(scale=3,visible=True,show_progress=True,idle_activity='standard',hover_reactions=True,games_enabled=True)
            self.controller.pet.set_scale(3); self.controller.pet.show(); self.reset_position()
            self.controller.pet.unblink()
        elif page=='sound':
            self.controller.preferences.update(sounds=True,sound_volume=20,cat_voice=True,idle_voice=False,
                sound_groups={key:{'enabled':True,'volume':100} for key in ('conversion','pet','game')})
            self.controller.sounds.apply_preferences()
        elif page=='usage':
            self.window.sibling_output.setChecked(False); self.window.output.setText(str(self.window.home/'output'))
            self.controller.preferences['quick']={}
            self.controller.preferences.update(notifications=True,open_results=False,folder_prefix='转换结果')
        else:return
        self.sync(); self.save()

    def closeEvent(self,event):
        self.apply_usage()
        super().closeEvent(event)
