import json
import logging
from dataclasses import asdict
from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QColor, QIcon, QPixmap, QImage
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
                               QScrollArea, QSplitter, QLineEdit, QProgressBar, QMessageBox,
                               QAbstractItemView, QMenu, QFrame, QCheckBox, QStackedWidget,QLayout)
from .models import Job, human_size, IMAGE_EXTENSIONS, VIDEO_EXTENSIONS
from .options import VideoPanel, ImagePanel, LivePanel
from .paths import setup_paths, check_output_directory,runtime_home,documents_home
from .queue import BatchWorker, Inspector, HardwareDetector, PairMatcher
from .theme import STYLE, setup_fonts, sketch_mark, SideTabs
from .video import build_command
from .motion import Motion, SmoothProgress
from .workflow import ParameterStore
from .simple import SimplePage
from .product import NAME,DISPLAY_VERSION


class MainWindow(QMainWindow):
    def __init__(self, settings_path=None):
        super().__init__()
        setup_fonts()
        self.home = setup_paths()
        self.settings_path = Path(settings_path) if settings_path else runtime_home() / 'data' / 'settings.json'
        self.jobs = {'video': [], 'image': [], 'live': []}
        self.ui_mode = "simple"
        self.motion = Motion(self)
        self.drop_hints = {}
        self.details = {}
        self.task_scrollers={}
        self.thumbnails = {}
        self.tables = {}
        self.panels = {}
        self.desktop_preferences = {}
        from .preferences import normalize_ui
        self.ui_preferences=normalize_ui({})
        self.splitters={}
        self._applying_splitters=False
        self.inspectors = []
        self.worker = None
        self.detector = None
        self.busy = False
        self.hardware_enabled = True
        self.closing = False
        self.setWindowTitle(NAME+' '+DISPLAY_VERSION+' · 转换 / 媒体信息')
        available = self.screen().availableGeometry()
        self.resize(max(980, min(1480, available.width() - 40)),
                    max(640, min(940, available.height() - 40)))
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)
        container = QWidget()
        self.setCentralWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(sketch_mark())
        mark.setFixedSize(76, 76)
        mark.setAlignment(Qt.AlignCenter)
        header.addWidget(mark)
        titles = QVBoxLayout()
        brand = QLabel(NAME)
        brand.setObjectName('brand')
        subtitle = QLabel('MEDIAFORGE  /  把每一份影像，轻轻收好。')
        subtitle.setObjectName('tagline')
        titles.addWidget(brand)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()
        badge = QLabel('本地离线处理')
        badge.setObjectName('badge')
        badge.setMinimumHeight(32)
        badge.setAlignment(Qt.AlignCenter)
        header.addWidget(badge,0,Qt.AlignVCenter)
        self.help_button = QPushButton('使用说明')
        self.help_button.clicked.connect(self.show_help)
        header.addWidget(self.help_button)
        self.settings_button=QPushButton('设置')
        self.settings_button.clicked.connect(lambda:self.controller.show_settings() if getattr(self,'controller',None) else None)
        header.addWidget(self.settings_button)
        layout.addLayout(header)
        mode_row = QHBoxLayout()
        self.simple_button = QPushButton('小白模式')
        self.advanced_button = QPushButton('专业模式')
        self.information_button = QPushButton('信息模式')
        for button, mode in ((self.simple_button, 'simple'), (self.advanced_button, 'advanced'),(self.information_button,'information')):
            button.setCheckable(True)
            button.setObjectName('modeButton')
            button.clicked.connect(lambda checked=False, mode=mode: self.set_ui_mode(mode))
            mode_row.addWidget(button)
        from .task_details import ElidedLabel
        self.mode_hint = ElidedLabel()
        self.mode_hint.setText('选格式、选预设，即可开始。体积上限可留空。')
        self.mode_hint.setObjectName('muted')
        mode_row.addWidget(self.mode_hint, 1)
        self.reduce_motion = QCheckBox('减少动画')
        self.reduce_motion.toggled.connect(self.set_reduced_motion)
        mode_row.addWidget(self.reduce_motion)
        layout.addLayout(mode_row)
        self.view_stack = QStackedWidget()
        layout.addWidget(self.view_stack, 1)
        self.advanced_page = QWidget()
        layout = QVBoxLayout(self.advanced_page)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('mediaTabs')
        self.tabs.setTabBar(SideTabs())
        self.tabs.setTabPosition(QTabWidget.West)
        self.tabs.addTab(self.make_page('video'), '视频处理')
        self.tabs.addTab(self.make_page('image'), '图片处理')
        self.tabs.addTab(self.make_page('live'), 'Live Photo')
        self.tabs.currentChanged.connect(self.mode_changed)
        layout.addWidget(self.tabs, 1)
        destination = QHBoxLayout()
        self.sibling_output = QCheckBox('原目录归组')
        self.sibling_output.setToolTip('在原文件旁新建结果文件夹；关闭时使用指定目录。')
        destination.addWidget(self.sibling_output)
        destination.addWidget(QLabel('输出目录'))
        self.output = QLineEdit(str(self.home / 'output'))
        self.output.setMinimumHeight(30)
        destination.addWidget(self.output, 1)
        self.browse = QPushButton('选择目录')
        self.browse.clicked.connect(self.choose_output)
        destination.addWidget(self.browse)
        self.open_folder = QPushButton('打开输出文件夹')
        self.open_folder.clicked.connect(self.open_output)
        destination.addWidget(self.open_folder)
        layout.addLayout(destination)
        self.output_error = QLabel()
        self.output_error.setObjectName('inlineError')
        self.output_error.hide()
        layout.addWidget(self.output_error)
        self.output.textChanged.connect(lambda: self.output_error.hide())
        self.output.textChanged.connect(self.output.setToolTip)
        footer = QHBoxLayout()
        status_column = QVBoxLayout()
        self.status = QLabel('添加文件，设置参数，然后开始处理。原文件始终保留。')
        self.status.setWordWrap(True)
        self.hardware_status = QLabel('硬件编码器：准备检测 · CPU 始终可用')
        self.hardware_status.setObjectName('muted')
        status_column.addWidget(self.status)
        self.feedback = QLabel()
        self.feedback.setObjectName('muted')
        self.feedback.hide()
        status_column.addWidget(self.feedback)
        self.feedback_timer = QTimer(self)
        self.feedback_timer.setSingleShot(True)
        self.feedback_timer.timeout.connect(self.hide_feedback)
        status_column.addWidget(self.hardware_status)
        footer.addLayout(status_column, 1)
        self.cancel_current = QPushButton('取消当前')
        self.cancel_current.setObjectName('danger')
        self.cancel_current.clicked.connect(lambda: self.worker.cancel(False) if self.busy else None)
        self.cancel_all = QPushButton('取消全部')
        self.cancel_all.setObjectName('danger')
        self.cancel_all.clicked.connect(lambda: self.controller.cancel_all() if getattr(self, 'controller', None) else self.worker.cancel(True) if self.busy else None)
        self.start = QPushButton('开始处理')
        self.start.setObjectName('primary')
        self.start.clicked.connect(lambda: self.start_batch())
        footer.addWidget(self.cancel_current)
        footer.addWidget(self.cancel_all)
        footer.addWidget(self.start)
        layout.addLayout(footer)
        self.load_settings()
        self.parameter_store = ParameterStore(self.panels, self)
        self.simple_page = SimplePage(self, self.parameter_store)
        self.view_stack.addWidget(self.simple_page)
        self.view_stack.addWidget(self.advanced_page)
        from .information import InformationPage
        self.information_page=InformationPage(self)
        self.view_stack.addWidget(self.information_page)
        self.set_ui_mode("simple", False)
        self.motion.watch_buttons(self)
        self.apply_appearance()
        QTimer.singleShot(0,self.apply_splitters)
        self.refresh_controls()
        from PySide6.QtGui import QShortcut,QKeySequence
        self.add_shortcut=QShortcut(QKeySequence('Ctrl+O'),self)
        self.add_shortcut.activated.connect(self.add_current_files)
        self.help_shortcut=QShortcut(QKeySequence('F1'),self)
        self.help_shortcut.activated.connect(self.show_help)
        self.help_button.setToolTip('打开完整使用说明（F1）')
        QTimer.singleShot(700, self.start_hardware_detection)

    @property
    def kind(self):
        return ('video', 'image', 'live')[self.tabs.currentIndex()]

    def make_page(self, kind):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 18, 0)
        left_layout.setSpacing(8)
        left_layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        descriptions = {'video': 'MP4 / MOV / MKV / AVI / TS / MPEG / WebM / WMV / FLV',
                        'image': 'JPEG / PNG / HEIC / AVIF / WebP / GIF / APNG / TIFF',
                        'live': '导入 .livp，或添加 HEIC / JPEG ＋ MOV 配对文件'}
        hint = QLabel('＋  拖入文件，让影像轻一点\n' + descriptions[kind])
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName('dropHint')
        self.drop_hints[kind] = hint
        left_layout.addWidget(hint)
        toolbar = QHBoxLayout()
        add = QPushButton('＋ 添加文件')
        add.setObjectName('add_' + kind)
        add.clicked.connect(self.choose_files)
        remove = QPushButton('移除选中')
        remove.setObjectName('remove_' + kind)
        remove.clicked.connect(self.remove_selected)
        clear = QPushButton('清空列表')
        clear.setObjectName('clear_' + kind)
        clear.clicked.connect(self.clear_jobs)
        retry = QPushButton('重试失败')
        retry.setObjectName('retry_' + kind)
        retry.clicked.connect(lambda: self.start_batch(retry_only=True))
        from .responsive import ActionToolbar
        left_layout.addWidget(ActionToolbar([add,remove,clear,retry]))
        if kind == 'live':
            pair_button = QPushButton('手动配对照片与 MOV')
            pair_button.setObjectName('pair_live')
            pair_button.clicked.connect(self.choose_pair)
            pair_row=QHBoxLayout(); pair_row.addWidget(pair_button); pair_row.addStretch()
            left_layout.addLayout(pair_row)
        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(['文件名称', '原始大小', '分辨率', '输出格式', '进度 / 状态', '状态', '压缩结果'])
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(48)
        table.setIconSize(__import__('PySide6.QtCore', fromlist=['QSize']).QSize(60, 42))
        table.verticalHeader().setDefaultSectionSize(66)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        table.setColumnWidth(0,200)
        header.setMinimumSectionSize(80)
        for col in range(1, 7):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
            table.setColumnWidth(col,{1:85,2:110,3:80,4:100,5:80,6:140}[col])
        table.setWordWrap(False)
        table.setTextElideMode(Qt.ElideMiddle)
        table.setMinimumWidth(360)
        table.setMinimumHeight(120)
        table.itemSelectionChanged.connect(lambda kind=kind: self.selection_changed(kind))
        table.cellDoubleClicked.connect(lambda row, col, kind=kind: self.show_job(kind, row))
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda pos, kind=kind: self.context_menu(kind, pos))
        self.tables[kind] = table
        table.viewport().installEventFilter(self)
        left_layout.addWidget(table, 1)
        from .task_details import TaskDetails
        detail = TaskDetails()
        detail.hide()
        self.details[kind] = detail
        left_layout.addWidget(detail)
        note = QLabel('双击已完成任务可打开成品；双击失败任务查看原因。相同文件名自动编号。')
        note.setObjectName('muted')
        note.setWordWrap(True)
        left_layout.addWidget(note)
        note.hide();table.setToolTip(note.text())
        task_scroll=QScrollArea();task_scroll.setWidgetResizable(True);task_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        task_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded);task_scroll.setWidget(left);task_scroll.setMinimumWidth(360)
        self.task_scrollers[kind]=task_scroll;splitter.addWidget(task_scroll)
        panel = VideoPanel() if kind == 'video' else ImagePanel() if kind == 'image' else LivePanel()
        panel.format.currentIndexChanged.connect(lambda: self.update_formats(kind))
        self.panels[kind] = panel
        for widget in panel.findChildren(QWidget):
            for signal in ('valueChanged', 'currentIndexChanged', 'toggled'):
                if hasattr(widget, signal):
                    getattr(widget, signal).connect(lambda *args, kind=kind: self.selection_changed(kind))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setViewportMargins(0,0,8,0)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(330)
        splitter.addWidget(scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([860, 420])
        splitter.setChildrenCollapsible(False)
        self.splitters[kind]=splitter
        splitter.splitterMoved.connect(lambda pos,index,k=kind:self.remember_splitter(k))
        layout.addWidget(splitter)
        return page

    def choose_files(self):
        filter = '媒体文件 (' + ' '.join('*' + x for x in sorted(VIDEO_EXTENSIONS | IMAGE_EXTENSIONS | {'.livp'})) + ')'
        files, _ = QFileDialog.getOpenFileNames(self, '添加媒体文件', str(self.home), filter + ';;所有文件 (*)')
        self.add_files([Path(file) for file in files])

    def add_current_files(self):
        if self.ui_mode=='information':self.information_page.choose_files()
        elif not self.busy and not self.closing and not getattr(self,'preparing',False):self.choose_files()

    def eventFilter(self,obj,event):
        from PySide6.QtCore import QEvent
        if event.type()==QEvent.Resize:
            for table in self.tables.values():
                if obj is table.viewport():
                    other=sum(table.columnWidth(col) for col in range(1,7) if not table.isColumnHidden(col))
                    table.setColumnWidth(0,max(160,table.viewport().width()-other-2))
        return super().eventFilter(obj,event)

    def add_files(self, files, paired=False):
        if self.busy or self.closing:
            return
        if getattr(self,'controller',None):self.controller.stop_play()
        new = []
        skipped = 0
        files = [Path(p).resolve() for p in files]
        if not paired and any(p.suffix.lower() == '.mov' for p in files) and any(p.suffix.lower() in {'.heic', '.heif', '.jpg', '.jpeg'} for p in files):
            matcher = PairMatcher(files)
            matcher.matched.connect(self.pairs_matched)
            matcher.finished.connect(lambda worker=matcher: self.inspector_finished(worker))
            self.inspectors.append(matcher)
            matcher.start()
            self.status.setText('正在后台识别 Live Photo 配对信息…')
            self.refresh_controls()
            return
        for path in files:
            path = Path(path).resolve()
            suffix = path.suffix.lower()
            kind = 'live' if suffix == '.livp' else 'video' if suffix in VIDEO_EXTENSIONS else 'image' if suffix in IMAGE_EXTENSIONS else None
            if not kind or not path.is_file():
                skipped += 1
                continue
            if any(job.path == path for job in self.jobs[kind]):
                skipped += 1
                continue
            job = Job(path, status='待读取')
            self.jobs[kind].append(job)
            new.append(job)
            self.render_job(kind, job)
        if new:
            kinds = {self.find_job(job.id)[0] for job in new}
            if len(kinds) == 1:
                self.tabs.setCurrentIndex(('video', 'image', 'live').index(next(iter(kinds))))
            inspector = Inspector(new)
            inspector.inspected.connect(self.inspected)
            inspector.thumbnail.connect(self.thumbnail_ready)
            inspector.finished.connect(lambda worker=inspector: self.inspector_finished(worker))
            self.inspectors.append(inspector)
            inspector.start()
        self.status.setText(f'已添加 {len(new)} 个任务' + (f'，跳过 {skipped} 个重复或不支持的文件' if skipped else '') + '。')
        self.refresh_controls()

    def pairs_matched(self, pairs, remaining, error):
        if self.closing:
            return
        new = []
        for image, movie in pairs:
            if any(j.inputs == (image, movie) for j in self.jobs['live']):
                continue
            job = Job(image, inputs=(image, movie), status='待读取')
            self.jobs['live'].append(job)
            new.append(job)
            self.render_job('live', job)
        if new:
            inspector = Inspector(new)
            inspector.inspected.connect(self.inspected)
            inspector.thumbnail.connect(self.thumbnail_ready)
            inspector.finished.connect(lambda worker=inspector: self.inspector_finished(worker))
            self.inspectors.append(inspector)
            inspector.start()
            self.tabs.setCurrentIndex(2)
        self.add_files(remaining, paired=True)
        self.status.setText(f'识别到 {len(new)} 组 Live Photo。' + ('自动配对失败：' + error if error else '未配对素材可用手动配对按钮添加。'))

    def find_job(self, id):
        for kind, jobs in self.jobs.items():
            for job in jobs:
                if job.id == id:
                    return kind, job
        return None, None

    def choose_pair(self):
        if self.busy:
            return
        image, _ = QFileDialog.getOpenFileName(self, '选择 Live 静态照片', str(self.home), '照片 (*.heic *.heif *.jpg *.jpeg)')
        if not image:
            return
        movie, _ = QFileDialog.getOpenFileName(self, '选择对应 MOV 动态视频', str(Path(image).parent), '动态视频 (*.mov)')
        if not movie:
            return
        inputs = (Path(image).resolve(), Path(movie).resolve())
        if any(j.inputs == inputs for j in self.jobs['live']):
            self.status.setText('这组 Live 配对已经在列表中。')
            return
        job = Job(inputs[0], inputs=inputs, status='待读取')
        self.jobs['live'].append(job)
        self.render_job('live', job)
        inspector = Inspector([job])
        inspector.inspected.connect(self.inspected)
        inspector.thumbnail.connect(self.thumbnail_ready)
        inspector.finished.connect(lambda worker=inspector: self.inspector_finished(worker))
        self.inspectors.append(inspector)
        self.tabs.setCurrentIndex(2)
        inspector.start()
        self.refresh_controls()

    def selection_changed(self, kind):
        if kind not in self.panels:
            return
        rows = self.tables[kind].selectionModel().selectedRows()
        self.details[kind].setVisible(bool(rows))
        if not rows:
            self.details[kind].setText('选中一个任务，查看素材信息、输出参数和预计体积。')
            return
        job = self.jobs[kind][rows[0].row()]
        info = job.info
        if not info:
            self.details[kind].setText(job.path.name + '\n' + (job.error or '正在读取素材信息…'))
            return
        options = job.parameters if job.parameters and job.status in {'处理中', '完成'} else self.panels[kind].snapshot()
        if not hasattr(options,'format'):options=self.panels[kind].snapshot()
        lines = [job.path.name, f'{info.width} × {info.height}  /  {human_size(info.size)}']
        if info.duration:
            lines[-1] += f'  /  {info.duration:.2f} 秒  /  {info.fps:.2f} fps'
        if info.frames > 1:
            lines[-1] += f'  /  {info.frames} 帧'
        if info.video_codec:
            lines.append(f'原始视频：{info.video_codec} · {info.video_bitrate//1000 if info.video_bitrate else "未知"} kbps；音频 {info.audio_bitrate//1000 if info.audio_bitrate else "未知"} kbps')
        if info.bit_depth>8 or info.color_transfer in {'smpte2084','arib-std-b67'}:
            lines.append(f'源：{info.bit_depth} 位 / {info.color_transfer or "色彩信息未知"}；请确认输出位深和显示变化。')
        from .resolution import resolve_options
        if kind in {'video','image'}:
            effective=resolve_options(info,options)
            if getattr(options,'remux',False):
                from dataclasses import replace
                effective=replace(effective,width=info.width,height=info.height)
            lines.append(f'输出：{options.format.upper()} · 预计 {effective.width} × {effective.height}'+('（偶数对齐）' if kind=='video' else ''))
        else:
            from dataclasses import replace
            component=replace(info,kind='video',width=int(info.metadata.get('video_width',info.width)),height=int(info.metadata.get('video_height',info.height)),sample_aspect_ratio=info.metadata.get('video_sar','1/1'))
            target_info=component if options.mode in {'video','animation'} else info
            setting=options.video if options.mode=='video' else options.image
            effective=resolve_options(target_info,setting)
            lines.append(f'输出：{options.format.upper()} · 预计 {effective.width} × {effective.height}')
            if options.mode in {'both','preserve'}:
                video=resolve_options(component,options.video)
                lines.append('视频：原始 MOV，尺寸与码率不变' if options.mode=='preserve' or options.video_copy else f'视频：{options.video.format.upper()} · 预计 {video.width} × {video.height}')
        target = getattr(options, 'target_bytes', 0)
        if target:
            lines[-1] += '  /  体积上限 ' + human_size(target)
        elif kind == 'video' and options.mode == 'bitrate':
            audio = options.audio_bitrate if info.audio_codec and options.audio_codec not in {'none', 'copy'} else 0
            if options.audio_codec == 'copy' and info.audio_codec:
                lines[-1] += '  /  ' + str(options.bitrate) + ' kbps；原音频体积待测'
            else:
                expected = int((options.bitrate + audio) * 1000 * info.duration / 8 * 1.04)
                lines[-1] += f'  /  {options.bitrate} kbps  /  预计约 {human_size(expected)}'
        else:
            lines[-1] += '  /  最终体积取决于素材和编码参数'
        if job.status == '完成':
            lines.append('已导出：' + human_size(job.output_size) + '  ·  ' + str(job.output))
        elif job.error:
            lines.append(job.error)
        from .task_details import parameter_details
        lines.extend(parameter_details(options))
        self.details[kind].setText('\n'.join(lines))

    def inspected(self, id, info, error):
        kind, job = self.find_job(id)
        if job:
            job.info, job.error = info, error
            job.status = '失败' if error else '待处理'
            self.render_job(kind, job)
            self.selection_changed(kind)

    def thumbnail_ready(self, id, image):
        kind, job = self.find_job(id)
        if job and not image.isNull():
            self.thumbnails[id] = QIcon(QPixmap.fromImage(image))
            self.render_job(kind, job)

    def inspector_finished(self, worker):
        if worker in self.inspectors:
            self.inspectors.remove(worker)
        worker.deleteLater()
        self.refresh_controls()

    def render_job(self, kind, job):
        table = self.tables[kind]
        row = next((row for row in range(table.rowCount())
                    if table.item(row, 0) and table.item(row, 0).data(Qt.UserRole) == job.id), None)
        if row is None:
            row = table.rowCount()
            table.insertRow(row)
            for col in range(7):
                table.setItem(row, col, QTableWidgetItem())
            table.item(row, 0).setData(Qt.UserRole, job.id)
            from .motion import TaskProgress
            bar = TaskProgress()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFormat('%p%')
            table.setCellWidget(row, 4, bar)
            self.motion.fade(self.drop_hints[kind])
        source_size = job.info.size if job.info else (job.path.stat().st_size if job.path.exists() else 0)
        result = '—'
        if job.status == '完成' and source_size:
            difference = (1 - job.output_size / source_size) * 100
            result = human_size(job.output_size) + (f' · 减少 {difference:.1f}%' if difference >= 0 else f' · 增大 {-difference:.1f}%')
        values = [job.path.name, human_size(source_size),
                  f'{job.info.width} × {job.info.height}' if job.info else '—',
                  ('文件夹' if job.output and job.output.is_dir() else job.output.suffix[1:] if job.output else self.panels[kind].format.currentData()).upper(),
                  '', job.status, result]
        for col, value in enumerate(values):
            if col != 4:
                table.item(row, col).setText(value)
        table.item(row, 0).setToolTip(str(job.path))
        table.item(row, 0).setIcon(self.thumbnails.get(job.id, QIcon(sketch_mark())))
        table.item(row, 5).setToolTip(job.error or job.status)
        table.item(row, 6).setToolTip(str(job.output) if job.output else '')
        bar = table.cellWidget(row, 4)
        bar.motion.reduced = self.reduce_motion.isChecked()
        bar.set_progress(job.progress, job.status)
        color = '#514e45' if job.status == '完成' else '#9b5e4e' if job.status == '失败' else '#8a8273'
        table.item(row, 5).setForeground(QColor(color))
        if hasattr(self, "simple_page"):
            self.simple_page.refresh()

    def update_formats(self, kind):
        if not self.busy:
            for job in self.jobs[kind]:
                self.render_job(kind, job)
            self.selection_changed(kind)

    def remove_selected(self):
        if self.busy:
            return
        table = self.tables[self.kind]
        ids = {table.item(index.row(), 0).data(Qt.UserRole) for index in table.selectionModel().selectedRows()}
        self.jobs[self.kind] = [job for job in self.jobs[self.kind] if job.id not in ids]
        for row in range(table.rowCount() - 1, -1, -1):
            if table.item(row, 0).data(Qt.UserRole) in ids:
                table.removeRow(row)
        self.refresh_controls()

    def clear_jobs(self):
        if not self.busy:
            self.jobs[self.kind].clear()
            self.tables[self.kind].setRowCount(0)
            self.refresh_controls()

    def execute_request(self, request):
        if self.busy:
            return
        self.busy = True
        self.worker = BatchWorker.from_request(request)
        self.worker.updated.connect(self.job_updated)
        self.worker.summary.connect(self.batch_summary)
        self.worker.finished.connect(self.batch_finished)
        self.worker.start()
        self.status.setText('正在转换 · 参数已固定，结果保存到原文件旁')
        self.refresh_controls()

    def start_batch(self, retry_only=False):
        if self.busy or self.inspectors or self.closing:
            return
        pending = [job for job in self.jobs[self.kind]
                   if (job.status == '失败' if retry_only else job.status != '完成')]
        if not pending:
            self.status.setText('没有待处理任务。已完成任务不会重复执行。')
            return
        try:
            folder = None
            if not self.sibling_output.isChecked():
                output_text = self.output.text().strip()
                if not output_text:
                    raise ValueError('请选择输出目录')
                folder = Path(output_text).resolve()
                check_output_directory(folder)
            options = self.panels[self.kind].snapshot()
        except Exception as error:
            self.output_error.setText('输出目录：' + str(error))
            self.output_error.show()
            self.output.setFocus()
            return
        panel = self.panels[self.kind]
        panel.error_label.clear()
        video = options.video if self.kind == 'live' and options.mode == 'video' else options if self.kind == 'video' else None
        if video and ((video.mode == 'size' and video.target_bytes <= 0) or (video.mode == 'bitrate' and video.bitrate <= 0)):
            panel.error_label.setText('请输入大于 0 的体积上限或视频码率。')
            self.set_ui_mode('advanced')
            control = panel.video_panel.bitrate.number if self.kind == 'live' else panel.bitrate.number if video.mode == 'bitrate' else panel.target_bytes.number
            control.setFocus()
            return
        self.save_settings()
        controller = getattr(self, 'controller', None)
        if controller or self.sibling_output.isChecked():
            from .workflow import make_request
            request = make_request(pending, {self.kind: options}, output=None if self.sibling_output.isChecked() else folder, origin='advanced',prefix=getattr(controller,'preferences',{}).get('folder_prefix','转换结果'))
            if controller:
                controller.submit_request(request)
            else:
                self.execute_request(request)
            return
        self.busy = True
        self.worker = BatchWorker(pending, options, folder)
        self.worker.updated.connect(self.job_updated)
        self.worker.summary.connect(self.batch_summary)
        self.worker.finished.connect(self.batch_finished)
        self.worker.start()
        self.status.setText(f'正在处理 {len(pending)} 个文件 · 本批次参数已固定')
        self.refresh_controls()

    def job_updated(self, id, status, progress, error, output, output_size):
        kind, job = self.find_job(id)
        if job:
            # Worker owns the task state. Queued progress notifications can be
            # older than its latest verified result; never write them back.
            self.render_job(kind, job)

            self.selection_changed(kind)

    def batch_summary(self, completed, failed, cancelled):
        self.status.setText(f'处理结束：完成 {completed} 个，失败 {failed} 个，取消 {cancelled} 个。')
        self.feedback_timer.stop()
        self.feedback.setText('本批次已结束 · 双击任务查看结果')
        self.feedback.show()
        self.motion.fade(self.feedback)
        self.feedback_timer.start(2200)

    def hide_feedback(self):
        effect = self.feedback.graphicsEffect()
        if effect:
            self.motion.animate(effect, b'opacity', 0., self.feedback.hide)
        else:
            self.feedback.hide()

    def batch_finished(self):
        self.busy = False
        self.refresh_controls()

    def refresh_controls(self):
        if hasattr(self, 'simple_page'):
            self.simple_page.refresh()
        for kind, hint in self.drop_hints.items():
            count = len(self.jobs[kind])
            hint.setText(f'已添加 {count} 个任务 · 可继续拖入文件' if count else '＋ 拖入文件，或点击「添加文件」\n选择格式与预设，再开始处理')
        unlocked = not self.busy and not self.closing and not getattr(self,'preparing',False)
        self.tabs.tabBar().setEnabled(unlocked)
        for kind in ('video', 'image', 'live'):
            self.panels[kind].setEnabled(unlocked)
            for action in ('add', 'remove', 'clear', 'retry'):
                self.findChild(QPushButton, action + '_' + kind).setEnabled(unlocked and (not self.inspectors or action == 'add'))
        self.findChild(QPushButton, 'pair_live').setEnabled(unlocked)
        self.output.setEnabled(unlocked)
        self.browse.setEnabled(unlocked)
        self.start.setEnabled(unlocked and not self.inspectors and bool(self.jobs[self.kind]))
        self.cancel_current.setEnabled(self.busy and not self.closing)
        self.cancel_all.setEnabled(self.busy and not self.closing)
        self.cancel_current.setVisible(self.busy)
        self.cancel_all.setVisible(self.busy)
        self.sibling_output.setEnabled(unlocked)

    def mode_changed(self):
        if hasattr(self, 'start'):
            self.refresh_controls()
            self.motion.fade(self.drop_hints[self.kind])

    def choose_output(self):
        folder = QFileDialog.getExistingDirectory(self, '选择输出目录', self.output.text())
        if folder:
            self.output.setText(folder)

    def open_output(self):
        try:
            folder = Path(self.output.text()).resolve()
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        except OSError as error:
            QMessageBox.warning(self, '无法打开目录', str(error))

    def show_job(self, kind, row):
        job = self.jobs[kind][row]
        if job.output and job.output.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(job.output)))
        elif job.error:
            QMessageBox.information(self, '任务详情', job.error)

    def context_menu(self, kind, pos):
        table = self.tables[kind]
        row = table.rowAt(pos.y())
        if row < 0:
            return
        menu = QMenu(self)
        menu.addAction('打开结果 / 查看原因', lambda: self.show_job(kind, row))
        menu.addAction('打开原文件所在目录', lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.jobs[kind][row].path.parent))))
        menu.exec(table.viewport().mapToGlobal(pos))

    def start_hardware_detection(self):
        if not self.hardware_enabled or self.closing:
            return
        self.detector = HardwareDetector()
        self.detector.detected.connect(self.hardware_detected)
        self.detector.start()
        self.hardware_status.setText('硬件编码器：后台实际编码检测中 · CPU 始终可用')

    def hardware_detected(self, available):
        self.panels['video'].set_hardware(available)
        self.panels['live'].video_panel.set_hardware(available)
        labels = sorted(available)
        self.hardware_status.setText('硬件编码器：' + (' / '.join(labels) if labels else '未检测到可用硬件编码器') + ' · CPU 可用')

    def dragEnterEvent(self, event):
        if not self.busy and event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.set_drop_highlight(True)

    def dragLeaveEvent(self, event):
        self.set_drop_highlight(False)
        event.accept()

    def dropEvent(self, event):
        self.set_drop_highlight(False)
        if self.ui_mode=='information':
            self.information_page.add_paths([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()
            return
        if not self.busy:
            self.add_files([Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()])
            event.acceptProposedAction()

    def set_drop_highlight(self, active):
        for hint in self.drop_hints.values():
            hint.setProperty('receiving', active)
            hint.style().unpolish(hint)
            hint.style().polish(hint)
        self.motion.fade(self.drop_hints[self.kind])
        if hasattr(self, 'simple_page'):
            hint = self.simple_page.drop
            hint.setProperty('receiving',active)
            hint.style().unpolish(hint)
            hint.style().polish(hint)
            self.motion.fade(hint)

    def set_ui_mode(self, mode, animate=True):
        if mode not in ('simple', 'advanced','information'):
            return
        self.ui_mode = mode
        if hasattr(self, 'simple_page'):
            self.view_stack.setCurrentWidget(self.simple_page if mode == 'simple' else self.advanced_page if mode=='advanced' else self.information_page)
            self.setMinimumSize(680, 500) if mode == 'simple' else self.setMinimumSize(980, 640)
            if mode == 'simple' and not self.isVisible():
                available = self.screen().availableGeometry()
                self.resize(min(820, available.width()-40), min(700, available.height()-40))
            self.simple_page.form.sync()
        self.simple_button.setChecked(mode == 'simple')
        self.advanced_button.setChecked(mode == 'advanced')
        self.information_button.setChecked(mode=='information')
        self.mode_hint.setText('选格式、选预设，即可开始。' if mode == 'simple' else '完整参数 · 切回小白模式仍会保留设置' if mode=='advanced' else '查看与编辑元数据 · 原画质副本')
        for panel in self.panels.values():
            panel.set_ui_mode('advanced' if mode=='information' else mode, animate)
        if animate:
            self.motion.fade(self.mode_hint)
            if hasattr(self,'view_stack'):
                self.motion.fade(self.view_stack.currentWidget())

    def set_reduced_motion(self, reduced):
        self.motion.set_reduced(reduced)
        for panel in self.panels.values():
            panel.motion.set_reduced(reduced)
            panel.set_ui_mode(self.ui_mode, False)
        for table in self.tables.values():
            for row in range(table.rowCount()):
                table.cellWidget(row, 4).motion.set_reduced(reduced)
        if reduced:
            for effect in self.findChildren(__import__('PySide6.QtWidgets', fromlist=['QGraphicsOpacityEffect']).QGraphicsOpacityEffect):
                effect.setOpacity(1.)

    def load_settings(self):
        try:
            data = json.loads(self.settings_path.read_text(encoding='utf-8'))
            if isinstance(data.get('output'), str):
                self.output.setText(data['output'])
            from .preferences import normalize_ui,normalize_desktop
            self.desktop_preferences = normalize_desktop(data.get('desktop', {}))
            self.ui_preferences=normalize_ui(data.get('ui',{}))
            self.sibling_output.setChecked(bool(data.get('sibling_output', False)))
            raw_ui=data.get('ui') if isinstance(data.get('ui'),dict) else {}
            presets=raw_ui.get('presets') if isinstance(raw_ui.get('presets'),dict) else {}
            reduced=raw_ui.get('reduce_motion',False)
            self.reduce_motion.setChecked(reduced if type(reduced) is bool else False)
            for kind in ('video', 'image', 'live'):
                panel = self.panels[kind]
                preset = presets.get(kind, 'balanced')
                panel.presets.setCurrentIndex(max(0, panel.presets.findData(preset)))
                panel.restore(data.get(kind, {}))
                panel.refresh_summary()
        except FileNotFoundError:
            pass
        except Exception:
            logging.warning('配置损坏，恢复默认设置', exc_info=True)

    def save_settings(self):
        try:
            data = {'version': 5, 'desktop': getattr(getattr(self, 'controller', None), 'preferences', getattr(self, 'desktop_preferences', {})), 'sibling_output': self.sibling_output.isChecked(), 'ui': {**self.ui_preferences,'reduce_motion': self.reduce_motion.isChecked(), 'presets': {kind: panel.presets.currentData() for kind, panel in self.panels.items()}}, 'output': self.output.text(), **{kind: asdict(self.panels[kind].snapshot()) for kind in ('video', 'image', 'live')}}
            data['live']['format_memory']=dict(self.panels['live'].format_memory)
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.settings_path.with_suffix('.json.tmp')
            temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            temp.replace(self.settings_path)
            return True
        except OSError:
            logging.exception('无法保存配置')
            self.status.setText('配置保存失败，请检查软件文件夹的写入权限。')
            return False

    def apply_appearance(self):
        from .theme import presentation_style
        from PySide6.QtWidgets import QFormLayout
        self.setStyleSheet(presentation_style(self.ui_preferences))
        compact=self.ui_preferences['density']=='compact'
        self.tabs.tabBar().set_dimensions(self.ui_preferences.get('navigation_width',150),60 if compact else 78)
        for table in self.tables.values():
            table.verticalHeader().setDefaultSectionSize(max(52 if compact else 66,table.fontMetrics().height()+32))
            for col in (2,3,5,6):table.setColumnHidden(col,not self.ui_preferences.get('detailed_columns',False))
            table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Interactive if self.ui_preferences.get('detailed_columns',False) else QHeaderView.Stretch)
            table.horizontalHeader().setMinimumSectionSize(80)
            table.setColumnWidth(0,200)
            table.setColumnWidth(4,max(135,table.fontMetrics().horizontalAdvance('待处理 · 100%')+28))
            table.setColumnWidth(1,max(90,table.fontMetrics().horizontalAdvance('原始大小')+24))
            other=sum(table.columnWidth(col) for col in range(1,7) if not table.isColumnHidden(col))
            table.setColumnWidth(0,max(160,table.viewport().width()-other-2))
        for form in self.findChildren(QFormLayout):
            form.setVerticalSpacing(self.ui_preferences.get('spacing',12))
            for row in range(form.rowCount()):
                item=form.itemAt(row,QFormLayout.LabelRole)
                label=item.widget() if item else None
                if isinstance(label,QLabel):
                    label.setWordWrap(True); label.setMaximumWidth(16777215 if form.rowWrapPolicy()==QFormLayout.WrapAllRows else 145); label.setMinimumWidth(0 if form.rowWrapPolicy()==QFormLayout.WrapAllRows else 90)
        for widget in self.findChildren(__import__('PySide6.QtWidgets',fromlist=['QCheckBox']).QCheckBox):
            if hasattr(widget,'heightForWidth') and widget.__class__.__name__=='WrappedCheckBox':widget.updateGeometry()
        self.output.setToolTip(self.output.text())

    def apply_splitters(self):
        self._applying_splitters=True
        for kind,splitter in self.splitters.items():
            ratio=self.ui_preferences['splitters'].get(kind,.67)
            total=max(800,sum(splitter.sizes()))
            splitter.setSizes([round(total*ratio),round(total*(1-ratio))])
        self._applying_splitters=False

    def remember_splitter(self,kind):
        if self._applying_splitters:return
        sizes=self.splitters[kind].sizes()
        if sum(sizes):
            self.ui_preferences['splitters'][kind]=max(.25,min(.8,sizes[0]/sum(sizes)))
            self.save_settings()

    def show_help(self):
        path = documents_home() / '使用说明.txt'
        if not path.exists():
            path = Path(__import__('sys').executable).parent / '使用说明.txt'
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(self, '使用说明', '添加或拖入文件 → 选择输出格式和参数 → 开始处理。\n原文件保留。失败任务双击查看原因。\n硬件编码故障时选择 CPU 后重试。')

    def closeEvent(self, event):
        controller = getattr(self, 'controller', None)
        if controller and not controller.exiting:
            self.save_settings()
            self.hide()
            if controller.preferences.get('visible',True):
                controller.pet.show()
            event.ignore()
            return
        self.closing = True
        if hasattr(self,'information_page'):self.information_page.stop()
        if self.busy:
            self.worker.cancel(True)
        for inspector in self.inspectors:
            inspector.cancel_event.set()
        if self.detector:
            self.detector.cancel_event.set()
        threads = [*self.inspectors, self.worker, self.detector,*getattr(getattr(self,'information_page',None),'loaders',[])]
        if any(thread and thread.isRunning() for thread in threads):
            self.status.setText('正在停止后台任务并清理临时文件…')
            self.refresh_controls()
            event.ignore()
            QTimer.singleShot(150, self.close)
        else:
            self.save_settings()
            event.accept()
