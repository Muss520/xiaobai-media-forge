"""Immutable execution plans and shared parameter state, independent of views."""
from dataclasses import dataclass, asdict, replace
from datetime import datetime
from pathlib import Path
import re
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import QWidget
from .models import Job, VideoOptions, ImageOptions, LiveOptions, VIDEO_EXTENSIONS


def job_kind(job):
    return 'live' if job.inputs or job.path.suffix.lower() == '.livp' else 'video' if job.path.suffix.lower() in VIDEO_EXTENSIONS else 'image'


def validate_folder_name(name):
    if not name or name in {'.', '..'} or name[-1] in ' .' or re.search(r'[<>:"/\\|?*\x00-\x1f]', name):
        raise ValueError('文件夹名称不能包含路径、特殊符号或末尾空格/句点')
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *(f'COM{i}' for i in range(1,10)), *(f'LPT{i}' for i in range(1,10))}:
        raise ValueError('这是 Windows 保留名称，请换一个文件夹名称')
    if len(name) > 100:
        raise ValueError('文件夹名称最多 100 个字符')
    return name


@dataclass(frozen=True)
class WorkItem:
    job: Job
    parameters: object
    folder: Path
    sibling: bool = True
    preflight_error: str = ''
    requested_parameters: object = None


@dataclass(frozen=True)
class BatchRequest:
    items: tuple[WorkItem, ...]
    origin: str = 'simple'
    folder_name: str = ''


def make_request(jobs, options, folder_name='', output=None, origin='simple',prefix='转换结果'):
    name = validate_folder_name(folder_name or validate_folder_name(prefix)+datetime.now().strftime('_%Y%m%d_%H%M%S'))
    folders = {}
    items = []
    for job in jobs:
        parent = (job.inputs[0] if job.inputs else job.path).absolute().parent
        if parent not in folders:
            folder = Path(output) if output is not None else parent / name
            if output is None:
                i = 1
                while folder.exists():
                    folder = parent / f'{name}_{i}'
                    i += 1
            folders[parent] = folder
        value=options[job_kind(job)]
        requested=value
        if job.info and isinstance(value,(ImageOptions,VideoOptions)):
            from .resolution import resolve_options
            value=resolve_options(job.info,value)
        items.append(WorkItem(job, value, folders[parent], output is None,requested_parameters=requested))
    return BatchRequest(tuple(items), origin, folder_name)


def retry_request(request,transform=lambda value:value,prefix='转换结果'):
    """Keep per-file frozen settings and the original save policy on every retry."""
    name=validate_folder_name(request.folder_name or validate_folder_name(prefix)+datetime.now().strftime('_%Y%m%d_%H%M%S'))
    folders={}; items=[]
    for item in request.items:
        if item.job.status!='失败':continue
        folder=item.folder
        if item.sibling:
            if folder not in folders:
                candidate=folder.parent/name; number=1
                while candidate.exists():
                    candidate=folder.parent/f'{name}_{number}'; number+=1
                folders[folder]=candidate
            folder=folders[folder]
        requested=transform(item.requested_parameters) if item.requested_parameters is not None else None
        items.append(replace(item,parameters=transform(item.parameters),folder=folder,preflight_error='',requested_parameters=requested))
    return replace(request,items=tuple(items))


class ParameterStore(QObject):
    changed = Signal(str)

    def __init__(self, panels, parent=None):
        super().__init__(parent)
        self.panels = panels
        self.values = {kind: panel.snapshot() for kind, panel in panels.items()}
        self.updating = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.capture)
        for panel in panels.values():
            for widget in panel.findChildren(QWidget):
                for signal in ('valueChanged', 'currentIndexChanged', 'toggled'):
                    if hasattr(widget, signal):
                        getattr(widget, signal).connect(self.schedule)

    def schedule(self, *args):
        if not self.updating:
            self.timer.start(0)

    def capture(self):
        for kind, panel in self.panels.items():
            value = panel.snapshot()
            if value != self.values[kind]:
                self.values[kind] = value
                self.changed.emit(kind)

    def snapshot(self, kind):
        self.capture()
        return self.values[kind]

    def edit(self, kind, field, value):
        from .options import select
        panel = self.panels[kind]
        self.updating = True
        try:
            parts=field.split('.')
            owner=getattr(panel,parts[0]+'_panel') if len(parts)>1 else panel
            widget = getattr(owner, parts[-1])
            if hasattr(widget,'setValue'):
                widget.setValue(value)
            elif hasattr(widget,'setChecked'):
                widget.setChecked(value)
            else:
                select(widget, value)
                if field == 'presets':
                    panel.apply_preset()
            panel.refresh_summary()
        finally:
            self.updating = False
        self.capture()
        self.changed.emit(kind)
