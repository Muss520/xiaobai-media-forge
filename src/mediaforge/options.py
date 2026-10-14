from dataclasses import asdict, replace
from .motion import Motion
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QGroupBox, QComboBox,
                               QSpinBox, QDoubleSpinBox, QCheckBox, QLabel, QPushButton,
                               QColorDialog, QToolButton,QSizePolicy)
from PySide6.QtGui import QColor, QValidator
from PySide6.QtCore import QLocale,QSize,QEvent
from .models import VideoOptions, ImageOptions, LiveOptions
from .formats import VIDEO_FORMATS, AUDIO_FORMATS, IMAGE_FORMATS, CODEC_LABELS
from PySide6.QtWidgets import QHBoxLayout
from .widgets import WrappedCheckBox as QCheckBox
from .resolution import RESOLUTIONS


class ParameterSection(QGroupBox):
    def __init__(self,title):
        super().__init__()
        self.section_title=title
        self.setObjectName('parameterSection')
    def title(self):return self.section_title


class OptionalNumber(QDoubleSpinBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self.setMinimumWidth(80);self.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    def textFromValue(self,value):
        locale=QLocale(self.locale()); locale.setNumberOptions(locale.numberOptions()|QLocale.OmitGroupSeparator)
        text=locale.toString(value,'f',self.decimals())
        return text.rstrip('0').rstrip(locale.decimalPoint()) if self.decimals() else text
    def validate(self, text, position):
        if not text.strip():
            return QValidator.Acceptable, text, position
        return super().validate(text, position)

    def valueFromText(self, text):
        return 0. if not text.strip() else super().valueFromText(text)


class UnitValue(QWidget):
    def __init__(self, units, value=0):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.number = OptionalNumber()
        self.number.setDecimals(7)
        self.number.setRange(0, 1000000)
        self.number.setMinimumWidth(80)
        self.number.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
        self.unit = combo(units)
        self.unit.setFixedWidth(78)
        layout.addWidget(self.number, 1)
        layout.addWidget(self.unit)
        self.setValue(value)

    def value(self):
        return round(self.number.value() * self.unit.currentData())

    def changeEvent(self,event):
        super().changeEvent(event)
        if event.type() in (QEvent.FontChange,QEvent.StyleChange) and hasattr(self,'unit'):
            self.unit.setFixedWidth(max(78,self.unit.fontMetrics().horizontalAdvance('Mbps')+38))

    def setValue(self, value):
        self.number.setValue(value / self.unit.currentData())


def byte_value():
    widget = UnitValue([('MB', 1024 * 1024), ('KB', 1024)])
    widget.number.setSpecialValueText('不限制')
    widget.number.setToolTip('填写每个任务的体积上限；清空或设为 0 表示不限制。')
    return widget


def hide_field(widget):
    form = widget.parentWidget().layout()
    label = form.labelForField(widget) if isinstance(form, QFormLayout) else None
    if label:
        label.hide()
    widget.hide()


def combo(items):
    widget = QComboBox()
    for label, value in items:
        widget.addItem(label, value)
    widget.setMinimumHeight(32)
    widget.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
    widget.setMinimumContentsLength(7)
    widget.setMinimumWidth(80);widget.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    return widget


def spin(low, high, value, suffix=''):
    widget = QSpinBox()
    widget.setRange(low, high)
    widget.setValue(value)
    widget.setSuffix(suffix)
    widget.setMinimumHeight(32)
    widget.setMinimumWidth(80);widget.setSizePolicy(QSizePolicy.Ignored,QSizePolicy.Fixed)
    return widget


def select(widget, value):
    index = widget.findData(value)
    if index >= 0:
        widget.setCurrentIndex(index)


class OptionPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(8, 0, 12, 0)
        self.layout.setSpacing(12)
        self.ui_mode = "simple"
        self.motion = Motion(self)
        self._restoring = False
        heading = QLabel('输出设置')
        heading.setObjectName('sectionTitle')
        self.heading = heading
        self.layout.addWidget(heading)
        self.presets = combo([('均衡 · 推荐', 'balanced'), ('高清 · 优先画质', 'high'), ('体积优先 · 更小文件', 'small')])
        self.layout.addWidget(self.presets)
        self.base = self.group('格式')
        self.toggle = QToolButton()
        self.toggle.setText('＋ 展开高级参数')
        self.toggle.setCheckable(True)
        self.toggle.setChecked(False)
        self.toggle.setObjectName('advancedToggle')
        self.layout.addWidget(self.toggle)
        self.advanced = QWidget()
        self.advanced_layout = QVBoxLayout(self.advanced)
        self.advanced_layout.setContentsMargins(0, 0, 0, 0)
        self.advanced_layout.setSpacing(12)
        self.layout.addWidget(self.advanced)
        self.advanced.setVisible(False)
        self.toggle.toggled.connect(self.advanced.setVisible)
        self.toggle.toggled.connect(lambda checked: self.toggle.setText('－ 收起高级参数' if checked else '＋ 展开高级参数'))
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setObjectName('muted')
        self.layout.addWidget(self.note)
        self.custom_summary = QLabel()
        self.custom_summary.setWordWrap(True)
        self.custom_summary.setObjectName('customSummary')
        self.restore_preset = QPushButton('恢复当前预设')
        self.restore_preset.clicked.connect(self.apply_preset)
        self.layout.insertWidget(self.layout.indexOf(self.note), self.custom_summary)
        self.layout.insertWidget(self.layout.indexOf(self.note), self.restore_preset)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.setObjectName('inlineError')
        self.layout.addWidget(self.error_label)
        self.layout.addStretch()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        for form in self.findChildren(QFormLayout):
            owner=form.parentWidget()
            form.setRowWrapPolicy(QFormLayout.WrapAllRows if owner.width()<470 else QFormLayout.WrapLongRows)

    def minimumSizeHint(self):return QSize(240,super().minimumSizeHint().height())

    def group(self, title, advanced=False):
        group = ParameterSection(title)
        form = QFormLayout(group)
        form.setSpacing(10)
        form.setContentsMargins(6, 8, 10, 12)
        heading=QLabel(title); heading.setObjectName('parameterHeading')
        form.addRow(heading)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        if advanced:
            self.advanced_layout.addWidget(group)
        elif hasattr(self, 'toggle'):
            self.layout.insertWidget(self.layout.indexOf(self.toggle), group)
        else:
            self.layout.addWidget(group)
        return form

    def move_field(self, widget, destination, label):
        form = widget.parentWidget().layout()
        row = form.takeRow(widget)
        if row.labelItem and row.labelItem.widget():
            row.labelItem.widget().deleteLater()
        destination.addRow(label, widget)

    def setup_modes(self):
        self.toggle.hide()
        # Move each existing control once; snapshots continue reading the same widgets.
        if isinstance(self, VideoPanel):
            encoding = self.group('视频编码', True)
            for name, label in [('codec', '视频编码'), ('encoder', '编码设备'), ('remux', ''),('pixel_format','输出位深'),('profile','编码规格'),('keyframe_interval','关键帧间隔'),('metadata','')]:
                self.move_field(getattr(self, name), encoding, label)
        if not isinstance(self, LivePanel):
            self.move_field(self.resolution,self.base,'分辨率')
            self.move_field(self.target_bytes, self.base, '体积上限')
            for group in self.findChildren(QGroupBox):
                if group is not self.base.parentWidget() and group.parentWidget() is self:
                    self.advanced_layout.addWidget(group)
            order = (['视频编码', '画质与体积', '画面尺寸与帧率', '音频']
                     if isinstance(self, VideoPanel) else ['质量与体积', '图片尺寸', '动图与选帧', '透明背景与元数据'])
            groups = {self.advanced_layout.itemAt(i).widget().title(): self.advanced_layout.itemAt(i).widget()
                      for i in range(self.advanced_layout.count())}
            for title in order:
                self.advanced_layout.removeWidget(groups[title])
                self.advanced_layout.addWidget(groups[title])
        self.set_ui_mode('simple', False)
        for widget in self.findChildren(QWidget):
            for signal in ('valueChanged', 'currentIndexChanged', 'toggled'):
                if hasattr(widget, signal):
                    getattr(widget, signal).connect(self.refresh_summary)
        self.refresh_summary()

    def set_ui_mode(self, mode, animate=True):
        self.ui_mode = mode
        expanded = mode == 'advanced'
        self.note.setVisible(expanded)
        if not animate or self.motion.reduced or not self.isVisible():
            reduced = self.motion.reduced
            self.motion.set_reduced(True)
            self.advanced.setMaximumHeight(16777215)
            self.advanced.setVisible(expanded)
            self.motion.set_reduced(reduced)
        else:
            height = self.advanced.height() if self.advanced.isVisible() else 0
            self.advanced.setMaximumHeight(height)
            self.advanced.show()
            target = self.advanced.sizeHint().height() if expanded else 0
            def finish():
                self.advanced.setVisible(expanded)
                self.advanced.setMaximumHeight(16777215)
            self.motion.animate(self.advanced, b'maximumHeight', target, finish)
            if expanded:
                self.motion.fade(self.advanced)
        self.refresh_summary()

    def preset_values(self):
        preset = self.presets.currentData()
        if isinstance(self, VideoPanel):
            fmt = self.format.currentData()
            return VideoOptions(format=fmt, codec=VIDEO_FORMATS[fmt][0], audio_codec=AUDIO_FORMATS[fmt][0],
                quality={'high':18, 'balanced':23, 'small':30}[preset],
                bitrate={'high':6000, 'balanced':2500, 'small':1000}[preset],
                speed='slow' if preset == 'small' else 'medium',
                width=1280 if preset == 'small' else 0, height=720 if preset == 'small' else 0,
                audio_bitrate=96 if preset == 'small' else 128,resolution_preset='720p' if preset=='small' else 'original')
        if isinstance(self, ImagePanel):
            return ImageOptions(format=self.format.currentData(), quality={'high':95,'balanced':85,'small':65}[preset],
                png_level=9 if preset == 'small' else 6,
                width=1600 if preset == 'small' else 0, height=1600 if preset == 'small' else 0,resolution_preset='custom' if preset=='small' else 'original')
        return None

    def refresh_summary(self, *args, value_override=None):
        if self._restoring or not hasattr(self, 'format') or self.format.currentData() is None:
            return
        if isinstance(self, VideoPanel) and any(widget.currentData() is None for widget in
                (self.codec, self.encoder, self.mode, self.speed, self.audio_codec)):
            return
        value = value_override if value_override is not None else self.snapshot()
        if isinstance(self, LivePanel):
            self.image_panel.refresh_summary(value_override=value.image)
            self.video_panel.refresh_summary(value_override=value.video)
            for panel in (self.image_panel, self.video_panel):
                panel.note.hide()
                panel.custom_summary.hide()
                panel.restore_preset.hide()
            custom = self.video_panel.is_custom if value.mode == 'video' else self.image_panel.is_custom
            if value.mode == 'video':
                summary = '视频：' + self.video_panel.summary_text
            else:
                summary = '照片：' + self.image_panel.summary_text
                if value.mode == 'preserve':
                    summary += '\n动态视频：MOV 原样保留'
        else:
            actual, expected = asdict(value), asdict(self.preset_values())
            for key in ('target_bytes',):
                actual.pop(key, None); expected.pop(key, None)
            if getattr(self, 'embedded_live', False):
                for key in ('animation', 'frame_index'):
                    actual.pop(key, None); expected.pop(key, None)
            if actual.get('mode') == 'size':
                actual['mode'] = 'quality'
            custom = actual != expected
            size = next((label for label,key in RESOLUTIONS if key==value.resolution_preset), '自定义') if value.resolution_preset not in {'custom','original'} else f'{value.width or "原宽"} × {value.height or "原高"}'
            if isinstance(self, VideoPanel):
                control = (f'码率 {value.bitrate} kbps' if value.mode == 'bitrate' else f'质量 {value.quality}')
                summary = f'{value.codec.upper()} · {control} · {size} · {value.audio_codec.upper()} {value.audio_bitrate} kbps'
                if value.remux:
                    summary = '直接封装 · 视频和音频原样复制'
                else:
                    summary += f' · {value.encoder.upper()} · {value.speed} · {value.fps or "原"} fps'
            else:
                summary = f'质量 {value.quality} · {size} · ' + ('保留元数据' if value.metadata else '清除元数据')
                if value.lossless:
                    summary += ' · WebP 无损'
                if value.animation != 'preserve':
                    summary += f' · 选帧 {value.frame_index if value.animation == "frame" else 0}'
                if value.auto_resize:
                    summary += ' · 允许自动缩小'
                if value.format in {'png', 'apng'}:
                    summary += f' · PNG 压缩级别 {value.png_level}'
                if value.upscale:
                    summary += ' · 允许放大'
                if value.format in {'jpg', 'bmp'} and value.background != '#ffffff':
                    summary += f' · 背景 {value.background.upper()}'
            if not value.aspect:
                summary += ' · 不保持比例'
            self.summary_text = summary
        self.is_custom = custom
        self.custom_summary.setText(('自定义参数已生效\n' if custom else '当前预设\n') + summary)
        self.custom_summary.setVisible(custom or self.ui_mode == 'advanced')
        self.restore_preset.setVisible(custom)



class VideoPanel(OptionPanel):
    def __init__(self):
        super().__init__()
        self.available_hardware = set()
        self.format = combo([(x.upper(), x) for x in VIDEO_FORMATS])
        self.codec = combo([('H.264 · 广泛兼容', 'h264'), ('H.265 / HEVC · 高压缩率', 'hevc')])
        self.encoder = combo([('CPU · 稳定兼容', 'cpu')])
        self.remux = QCheckBox('直接封装转换（不重新编码）')
        self.remux.setToolTip('复制主视频和首条音轨；不能改尺寸、帧率或音频。编码需兼容目标容器。')
        self.base.addRow('输出容器', self.format)
        self.base.addRow('视频编码', self.codec)
        self.base.addRow('编码设备', self.encoder)
        self.base.addRow(self.remux)
        quality = self.group('画质与体积')
        self.mode = combo([('质量优先', 'quality'), ('指定平均码率', 'bitrate'), ('目标文件体积 · 每个文件', 'size')])
        self.quality = spin(0, 51, 23)
        self.quality.setToolTip('数值越低画质越好、体积通常越大。不同编码器的数值并不完全等价。')
        self.bitrate = UnitValue([('kbps', 1), ('Mbps', 1000)], 2500)
        self.target_bytes = byte_value()
        self.speed = combo([('极快', 'ultrafast'), ('快速', 'fast'), ('均衡 medium', 'medium'), ('慢速', 'slow'), ('很慢', 'veryslow')])
        select(self.speed, 'medium')
        quality.addRow('控制模式', self.mode)
        quality.addRow('质量值（越低越清晰）', self.quality)
        quality.addRow('视频码率', self.bitrate)
        quality.addRow('体积上限', self.target_bytes)
        quality.addRow('编码速度', self.speed)
        dimensions = self.group('画面尺寸与帧率')
        self.width = spin(0, 16384, 0, ' px')
        self.height = spin(0, 16384, 0, ' px')
        self.width.setSpecialValueText('保持原宽度 / 自动')
        self.height.setSpecialValueText('保持原高度 / 自动')
        self.aspect = QCheckBox('保持宽高比（按边界适配）')
        self.aspect.setChecked(True)
        self.fps = OptionalNumber()
        self.fps.setRange(0, 240)
        self.fps.setDecimals(3)
        self.fps.setSpecialValueText('保持原帧率')
        self.fps.setSuffix(' fps')
        dimensions.addRow('最大宽度', self.width)
        dimensions.addRow('最大高度', self.height)
        dimensions.addRow(self.aspect)
        dimensions.addRow('帧率', self.fps)
        self.resolution = combo(RESOLUTIONS)
        self.resolution.currentIndexChanged.connect(lambda: self.set_resolution())
        dimensions.insertRow(0, '快捷尺寸', self.resolution)
        self.upscale=QCheckBox('允许放大低分辨率视频')
        dimensions.addRow(self.upscale)
        for widget in (self.width,self.height):widget.valueChanged.connect(self.dimensions_edited)
        audio = self.group('音频', True)
        self.audio_codec = combo([('AAC · 推荐', 'aac'), ('Opus', 'opus'), ('MP3', 'mp3'),
                                  ('PCM · 无损', 'pcm_s16le'), ('保持原音频', 'copy'), ('移除音频', 'none')])
        self.audio_bitrate = spin(16, 512, 128, ' kbps')
        self.sample_rate = combo([('保持原采样率', 0)] + [(f'{rate} Hz', rate) for rate in (8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000)])
        self.channels = combo([('保持原声道', 0), ('单声道', 1), ('立体声', 2)])
        audio.addRow('音频编码', self.audio_codec)
        audio.addRow('音频码率', self.audio_bitrate)
        audio.addRow('采样率', self.sample_rate)
        audio.addRow('声道', self.channels)
        self.pixel_format = combo([('8 位 · 兼容优先', 'yuv420p'), ('10 位 · CPU HEVC/VP9/AV1', 'yuv420p10le')])
        self.profile = combo([('自动', 'auto')])
        self.keyframe_interval = spin(0,10000,0,' 帧')
        self.keyframe_interval.setSpecialValueText('由编码器决定')
        self.metadata = QCheckBox('保留可复制的媒体元数据（可能含位置）')
        audio.addRow('输出位深',self.pixel_format)
        audio.addRow('编码规格',self.profile)
        audio.addRow('关键帧间隔',self.keyframe_interval)
        audio.addRow(self.metadata)
        self.codec.currentIndexChanged.connect(self.refresh_profiles)
        self.encoder.currentIndexChanged.connect(self.refresh_profiles)
        self.note.setText('处理主视频与首条音轨。宽高为 0 时保持源尺寸，编码尺寸会对齐为偶数。压缩后体积取决于内容和参数。')
        self.format.currentIndexChanged.connect(self.format_changed)
        self.codec.currentIndexChanged.connect(self.refresh_encoders)
        self.remux.toggled.connect(self.controls_changed)
        self.mode.currentIndexChanged.connect(self.controls_changed)
        self.mode.currentIndexChanged.connect(self.control_mode_changed)
        self.audio_codec.currentIndexChanged.connect(self.controls_changed)
        self.presets.currentIndexChanged.connect(self.apply_preset)
        self.format_changed()
        self.target_bytes.number.valueChanged.connect(self.target_changed)
        self.target_bytes.unit.currentIndexChanged.connect(self.target_changed)
        self.setup_modes()

    def refresh_profiles(self,*args):
        if not hasattr(self,'profile'):return
        previous=self.profile.currentData()
        self.profile.clear()
        for value in {'h264':['auto','baseline','main','high'],'hevc':['auto','main','main10']}.get(self.codec.currentData(),['auto']):
            self.profile.addItem('自动' if value=='auto' else value,value)
        select(self.profile,previous)
        supported=self.codec.currentData() in {'hevc','vp9','av1'} and self.encoder.currentData()=='cpu'
        self.pixel_format.model().item(1).setEnabled(supported)
        if not supported:select(self.pixel_format,'yuv420p')

    def target_changed(self, *args):
        if not self._restoring:
            select(self.mode, 'size' if self.target_bytes.value() else 'quality')
            if not self.target_bytes.value():
                self.quality.setValue({'high':18, 'balanced':23, 'small':30}[self.presets.currentData()])

    def control_mode_changed(self, *args):
        if not self._restoring and self.mode.currentData() != 'size' and self.target_bytes.value():
            self._restoring = True
            self.target_bytes.setValue(0)
            self._restoring = False

    def set_resolution(self):
        if self._restoring:return
        if self.resolution.currentData()!='custom':
            from PySide6.QtCore import QSignalBlocker
            guards=[QSignalBlocker(self.width),QSignalBlocker(self.height)]
            self.width.setValue(0); self.height.setValue(0)
            self.upscale.setChecked(False)
            self.aspect.setChecked(True)
        self.refresh_summary()

    def dimensions_edited(self,*args):
        if not self._restoring:select(self.resolution,'custom')

    def format_changed(self):
        previous = self.codec.currentData()
        self.codec.blockSignals(True)
        self.codec.clear()
        for codec in VIDEO_FORMATS[self.format.currentData()]:
            self.codec.addItem(CODEC_LABELS[codec], codec)
        select(self.codec, previous)
        previous_audio = self.audio_codec.currentData()
        self.audio_codec.clear()
        for codec in AUDIO_FORMATS[self.format.currentData()]:
            self.audio_codec.addItem(codec.upper(), codec)
        self.audio_codec.addItem('保持原音频', 'copy')
        self.audio_codec.addItem('移除音频', 'none')
        select(self.audio_codec, previous_audio)
        self.codec.blockSignals(False)
        self.quality.setMaximum(63 if self.codec.currentData() in {'vp9', 'vp8', 'av1'} else 51)
        self.refresh_encoders()
        self.refresh_profiles()
        self.controls_changed()

    def refresh_encoders(self):
        previous = self.encoder.currentData()
        self.encoder.blockSignals(True)
        self.encoder.clear()
        self.encoder.addItem('CPU · 稳定兼容', 'cpu')
        for backend, label in [('nvenc', 'NVIDIA NVENC'), ('qsv', 'Intel Quick Sync'), ('amf', 'AMD AMF')]:
            if f'{self.codec.currentData()}_{backend}' in self.available_hardware:
                self.encoder.addItem(label + ' · 已验证', backend)
        select(self.encoder, previous)
        self.encoder.blockSignals(False)
        if hasattr(self, 'is_custom'):
            self.refresh_summary()

    def set_hardware(self, available):
        self.available_hardware = set(available)
        self.refresh_encoders()

    def controls_changed(self):
        copying = self.remux.isChecked()
        for widget in (self.codec, self.encoder, self.mode, self.speed, self.width, self.height,
                       self.aspect, self.fps, self.audio_codec):
            widget.setEnabled(not copying)
        quality = self.mode.currentData() == 'quality'
        self.quality.setEnabled(not copying and quality)
        self.bitrate.setEnabled(not copying and self.mode.currentData() == 'bitrate')
        self.target_bytes.setEnabled(not copying)
        audio = self.audio_codec.currentData()
        self.audio_bitrate.setEnabled(not copying and audio not in {'none', 'copy', 'pcm_s16le'})
        self.sample_rate.setEnabled(not copying and audio not in {'copy', 'none'})
        self.channels.setEnabled(not copying and audio not in {'copy', 'none'})

    def apply_preset(self):
        self.restore(asdict(self.preset_values()))
        self.refresh_summary()

    def snapshot(self):
        copying = self.remux.isChecked()
        audio = self.audio_codec.currentData()
        return VideoOptions(format=self.format.currentData(), codec=self.codec.currentData(),
                            encoder=self.encoder.currentData(), mode=self.mode.currentData(),
                            quality=self.quality.value(), bitrate=self.bitrate.value(), speed=self.speed.currentData(),
                            width=0 if copying else self.width.value(), height=0 if copying else self.height.value(),
                            aspect=self.aspect.isChecked(), fps=0 if copying else self.fps.value(),
                            audio_codec='copy' if copying else audio, audio_bitrate=self.audio_bitrate.value(),
                            sample_rate=0 if copying or audio in {'copy', 'none'} else self.sample_rate.currentData(),
                            channels=0 if copying or audio in {'copy', 'none'} else self.channels.currentData(), remux=copying,
                            target_bytes=self.target_bytes.value() if not copying and self.mode.currentData() == 'size' else 0,
                            pixel_format=self.pixel_format.currentData(),profile=self.profile.currentData(),
                            keyframe_interval=0 if copying else self.keyframe_interval.value(), metadata=self.metadata.isChecked(),
                            resolution_preset='original' if copying else self.resolution.currentData(),upscale=self.upscale.isChecked())

    def restore(self, values):
        self._restoring = True
        for name in ('format', 'codec', 'encoder', 'mode', 'speed', 'audio_codec', 'sample_rate', 'channels','pixel_format','profile'):
            if name in values:
                select(getattr(self, name), values[name])
        for name in ('quality', 'bitrate', 'width', 'height', 'fps', 'audio_bitrate', 'target_bytes','keyframe_interval'):
            if name in values:
                getattr(self, name).setValue(values[name])
        for name in ('aspect', 'remux','metadata'):
            if name in values:
                getattr(self, name).setChecked(bool(values[name]))
        select(self.resolution,values.get('resolution_preset','custom' if values.get('width') or values.get('height') else 'original'))
        self.upscale.setChecked(values.get('upscale',bool('resolution_preset' not in values and (values.get('width') or values.get('height')))))
        self.controls_changed()
        self._restoring = False
        self.refresh_summary()


class ImagePanel(OptionPanel):
    def __init__(self):
        super().__init__()
        self.format = combo([(x.upper(), x) for x in IMAGE_FORMATS])
        self.base.addRow('输出格式', self.format)
        quality = self.group('质量与体积')
        self.quality = spin(1, 100, 85)
        self.png_level = spin(0, 9, 6)
        self.lossless = QCheckBox('WebP 无损模式')
        quality.addRow('质量（越高越清晰）', self.quality)
        quality.addRow('PNG 压缩级别', self.png_level)
        quality.addRow(self.lossless)
        self.target_bytes = byte_value()
        self.auto_resize = QCheckBox('目标过小时允许自动缩小尺寸')
        quality.addRow('体积上限 · 0 不限制', self.target_bytes)
        quality.addRow(self.auto_resize)
        dimensions = self.group('图片尺寸')
        self.width = spin(0, 32768, 0, ' px')
        self.height = spin(0, 32768, 0, ' px')
        self.width.setSpecialValueText('保持原宽度 / 自动')
        self.height.setSpecialValueText('保持原高度 / 自动')
        self.aspect = QCheckBox('保持宽高比')
        self.aspect.setChecked(True)
        self.upscale = QCheckBox('允许放大原图')
        dimensions.addRow('最大宽度', self.width)
        dimensions.addRow('最大高度', self.height)
        dimensions.addRow(self.aspect)
        dimensions.addRow(self.upscale)
        self.resolution=combo(RESOLUTIONS)
        dimensions.insertRow(0,'快捷尺寸',self.resolution)
        self.resolution.currentIndexChanged.connect(self.set_resolution)
        for widget in (self.width,self.height):widget.valueChanged.connect(self.dimensions_edited)
        animation = self.group('动图与选帧')
        self.animation = combo([('保留全部动画帧', 'preserve'), ('导出首帧为静态图片', 'first'), ('导出指定帧', 'frame')])
        self.frame_index = spin(0, 100000, 0)
        animation.addRow('处理方式', self.animation)
        animation.addRow('帧序号 · 从 0 开始', self.frame_index)
        other = self.group('透明背景与元数据', True)
        self.background = QPushButton('#FFFFFF · 白色')
        self.background_value = '#ffffff'
        self.background.clicked.connect(self.choose_background)
        self.metadata = QCheckBox('保留 EXIF 和 ICC（格式支持时）')
        self.metadata.setToolTip('保留元数据可能包含拍摄地点等信息；照片方向始终自动校正。')
        other.addRow('JPEG / BMP 背景', self.background)
        other.addRow(self.metadata)
        self.note.setText('支持 HEIC / AVIF 和动图。转静态格式时明确选帧。PNG 为无损压缩，体积无法保证缩小。照片方向自动校正。')
        self.format.currentIndexChanged.connect(self.controls_changed)
        self.lossless.toggled.connect(self.controls_changed)
        self.presets.currentIndexChanged.connect(self.apply_preset)
        self.controls_changed()
        self.setup_modes()

    def controls_changed(self):
        format = self.format.currentData()
        self.quality.setEnabled(format in {'jpg', 'heic', 'avif'} or (format == 'webp' and not self.lossless.isChecked()))
        self.png_level.setEnabled(format in {'png', 'apng'})
        self.lossless.setEnabled(format == 'webp')
        self.background.setEnabled(format in {'jpg', 'bmp'})
        self.metadata.setEnabled(format in {'jpg', 'png', 'webp', 'tiff', 'heic', 'avif'})

    def set_resolution(self,*args):VideoPanel.set_resolution(self)
    def dimensions_edited(self,*args):VideoPanel.dimensions_edited(self)

    def apply_preset(self):
        self.restore(asdict(self.preset_values()))
        self.refresh_summary()

    def choose_background(self):
        color = QColorDialog.getColor(QColor(self.background_value), self, '选择透明区域背景色')
        if color.isValid():
            self.background_value = color.name()
            self.background.setText(color.name().upper())
            self.refresh_summary()

    def snapshot(self):
        return ImageOptions(format=self.format.currentData(), quality=self.quality.value(),
                            png_level=self.png_level.value(), lossless=self.lossless.isChecked(),
                            width=self.width.value(), height=self.height.value(), aspect=self.aspect.isChecked(),
                            upscale=self.upscale.isChecked(), metadata=self.metadata.isChecked(), background=self.background_value,
                            target_bytes=self.target_bytes.value(), auto_resize=self.auto_resize.isChecked(),
                            animation=self.animation.currentData(), frame_index=self.frame_index.value(),resolution_preset=self.resolution.currentData())

    def restore(self, values):
        self._restoring = True
        select(self.format, values.get('format', 'jpg'))
        select(self.animation, values.get('animation', 'preserve'))
        for name in ('quality', 'png_level', 'width', 'height', 'target_bytes', 'frame_index'):
            if name in values:
                getattr(self, name).setValue(values[name])
        for name in ('lossless', 'aspect', 'upscale', 'metadata', 'auto_resize'):
            if name in values:
                getattr(self, name).setChecked(bool(values[name]))
        select(self.resolution,values.get('resolution_preset','custom' if values.get('width') or values.get('height') else 'original'))
        color = QColor(values.get('background', '#ffffff'))
        if color.isValid():
            self.background_value = color.name()
            self.background.setText(color.name().upper())
        self.controls_changed()
        self._restoring = False
        self.refresh_summary()


class LivePanel(OptionPanel):
    def __init__(self):
        super().__init__()
        self.format_memory={'photo':'png','video':'mp4','preserve':'livp','animation':'gif'}
        self._active_format_key=None
        self.mode = combo([('保留 Live · MOV 原样保留', 'preserve'), ('导出静态照片', 'image'),
                           ('导出普通视频', 'video'), ('导出动图', 'animation'), ('照片＋视频', 'both')])
        self.format = combo([('LIVP · 配对包', 'livp'), ('配对文件夹', 'folder')])
        self.base.addRow('导出方式', self.mode)
        self.base.addRow('输出格式', self.format)
        self.video_output=combo([('原始 MOV · 不转码','original_mov')]+[(f.upper()+(' · 转码' if f=='mov' else ''),f) for f in VIDEO_FORMATS])
        self.base.addRow('视频格式',self.video_output)
        self.target_bytes = byte_value()
        self.base.addRow('体积上限', self.target_bytes)
        self.animation_fps = QDoubleSpinBox()
        self.animation_fps.setRange(0,30)
        self.animation_fps.setSpecialValueText('保持源帧率')
        self.base.addRow('动图帧率',self.animation_fps)
        self.image_panel = ImagePanel()
        self.image_panel.embedded_live = True
        self.video_panel = VideoPanel()
        self.video_copy = QCheckBox('保持原始视频 · MOV 字节不变')
        self.video_copy.setChecked(True)
        self.base.addRow(self.video_copy)
        self.video_copy.toggled.connect(self.copy_changed)
        self.video_output.currentIndexChanged.connect(self.video_output_changed)
        self.video_panel.format.currentIndexChanged.connect(self.copy_changed)
        self.video_panel.format.setEnabled(False)
        hide_field(self.image_panel.target_bytes)
        hide_field(self.video_panel.target_bytes)
        hide_field(self.video_panel.format)
        self.advanced_layout.addWidget(self.image_panel)
        self.advanced_layout.addWidget(self.video_panel)
        for panel in (self.image_panel, self.video_panel):
            panel.heading.hide()
            panel.presets.hide()
            panel.note.hide()
            panel.custom_summary.hide()
            panel.restore_preset.hide()
            panel.set_ui_mode('advanced', False)
            panel.custom_summary.hide()
            panel.restore_preset.hide()
        self.presets.currentIndexChanged.connect(self.apply_preset)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        self.format.currentIndexChanged.connect(self.sync_format)
        self.target_bytes.number.valueChanged.connect(self.target_changed)
        self.target_bytes.unit.currentIndexChanged.connect(self.target_changed)
        self.video_panel.target_bytes.number.valueChanged.connect(self.video_target_changed)
        # A Live Photo already has explicit static/video/animation export choices.
        # General image frame selection would be overridden by that export contract.
        self.image_panel.animation.parentWidget().hide()
        self.note.setText('导入 .livp 或添加照片＋MOV。保留 Live 时转换照片，动态 MOV 原样保留；配对元数据始终保留。')
        self.toggle.hide()
        self.mode_changed()
        self.setup_modes()
        select(self.mode,'both')
        select(self.format,'png')

    def copy_changed(self,*args):
        from PySide6.QtCore import QSignalBlocker
        both=self.mode.currentData()=='both'
        self.video_copy.hide()
        self.base.setRowVisible(self.video_output,both)
        guard=QSignalBlocker(self.video_output)
        select(self.video_output,'original_mov' if self.video_copy.isChecked() else self.video_panel.format.currentData())
        self.video_panel.setVisible(self.mode.currentData()=='video' or both)
        self.video_panel.setEnabled(not both or not self.video_copy.isChecked())
        self.video_panel.format.setEnabled(both and not self.video_copy.isChecked())
        self.video_panel.format.hide()
        label=self.video_panel.base.labelForField(self.video_panel.format)
        if label:label.hide()

    def video_output_changed(self,*args):
        value=self.video_output.currentData()
        self.video_copy.setChecked(value=='original_mov')
        if value in VIDEO_FORMATS:
            self.format_memory['video']=value
            select(self.video_panel.format,value)
        self.copy_changed()

    def target_changed(self, *args):
        if not self._restoring and self.mode.currentData() == 'video':
            self.video_panel.target_bytes.setValue(self.target_bytes.value())

    def video_target_changed(self, *args):
        if not self._restoring and self.mode.currentData() == 'video':
            self.target_bytes.setValue(self.video_panel.target_bytes.value())

    def apply_preset(self):
        for panel in (self.image_panel, self.video_panel):
            select(panel.presets, self.presets.currentData())
            panel.apply_preset()
        self.target_bytes.setValue(0)
        self.refresh_summary()

    def sync_format(self):
        fmt = self.format.currentData()
        if fmt is None:
            return
        mode = self.mode.currentData()
        key='photo' if mode in {'both','image'} else mode
        self.format_memory[key]=fmt
        if mode == 'video':
            select(self.video_panel.format, fmt)
            self.video_panel.format.setEnabled(False)
        elif mode in {'image', 'animation', 'both'}:
            select(self.image_panel.format, fmt)


    def mode_changed(self):
        from PySide6.QtCore import QSignalBlocker
        mode = self.mode.currentData()
        if self._active_format_key and self.format.currentData():self.format_memory[self._active_format_key]=self.format.currentData()
        key='photo' if mode in {'both','image'} else mode
        self._active_format_key=key
        guard=QSignalBlocker(self.format)
        self.format.clear()
        formats = ['livp', 'folder'] if mode == 'preserve' else list(VIDEO_FORMATS) if mode == 'video' else ['gif', 'webp', 'apng'] if mode == 'animation' else list(IMAGE_FORMATS)
        for fmt in formats:
            self.format.addItem('配对文件夹' if fmt == 'folder' else fmt.upper(), fmt)
        select(self.format,self.format_memory.get(key))
        del guard
        self.image_panel.setVisible(mode != 'video')
        self.animation_fps.setVisible(mode=='animation')
        self.base.labelForField(self.animation_fps).setVisible(mode=='animation')
        self.video_panel.setVisible(mode == 'video')
        self.base.labelForField(self.format).setText('Live 封装' if mode=='preserve' else '视频格式' if mode=='video' else '动图格式' if mode=='animation' else '照片格式')
        self.image_panel.base.parentWidget().setVisible(mode != 'video')
        if mode == 'video' and self.target_bytes.value():
            self.target_changed()
        self.image_panel.target_bytes.setEnabled(mode not in {'preserve','both'})
        self.image_panel.format.setEnabled(mode == 'preserve')
        self.image_panel.format.setVisible(mode == 'preserve')
        label = self.image_panel.base.labelForField(self.image_panel.format)
        if label:
            label.setVisible(mode == 'preserve')
        self.image_panel.format.clear()
        for fmt in (['jpg', 'heic'] if mode == 'preserve' else IMAGE_FORMATS):
            self.image_panel.format.addItem(fmt.upper(), fmt)
        self.sync_format()
        self.copy_changed()

    def snapshot(self):
        from dataclasses import replace
        mode, fmt = self.mode.currentData(), self.format.currentData()
        image, video = self.image_panel.snapshot(), self.video_panel.snapshot()
        if mode in {'image', 'animation', 'both'}:
            image = replace(image, format=fmt, target_bytes=self.target_bytes.value(), animation='preserve' if mode == 'animation' else 'first')
        if mode == 'video':
            video = replace(video, format=fmt)
            if video.codec not in VIDEO_FORMATS[fmt]:
                video = replace(video, codec=VIDEO_FORMATS[fmt][0], audio_codec=AUDIO_FORMATS[fmt][0])
            if self.target_bytes.value():
                video = replace(video, mode='size', target_bytes=self.target_bytes.value())
        return LiveOptions(mode=mode, format=fmt, image=image, video=video, target_bytes=self.target_bytes.value(),animation_fps=self.animation_fps.value(),video_copy=self.video_copy.isChecked())

    def restore(self, values):
        self._restoring = True
        select(self.mode, values.get('mode', 'both'))
        select(self.format, values.get('format', 'png'))
        self.video_copy.setChecked(values.get('video_copy',True))
        self.image_panel.restore(values.get('image', {}))
        self.video_panel.restore(values.get('video', {}))
        self.target_bytes.setValue(values.get('target_bytes', 0))
        self.animation_fps.setValue(values.get('animation_fps',0))
        self._restoring = False
        memory=values.get('format_memory',{})
        if isinstance(memory,dict):
            for key,allowed in [('photo',IMAGE_FORMATS),('video',VIDEO_FORMATS),('preserve',('livp','folder')),('animation',('gif','webp','apng'))]:
                if memory.get(key) in allowed:self.format_memory[key]=memory[key]
        self.sync_format();self.copy_changed()
        self.target_changed()
        self.refresh_summary()
