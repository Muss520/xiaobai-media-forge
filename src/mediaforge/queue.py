import logging
import threading
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from .images import process_image, Cancelled
from .video import process_video, detect_hardware, build_command
from .models import Job, VideoOptions, LiveOptions
from .paths import reserve_output, check_output_directory
from .probe import probe


class BatchWorker(QThread):
    updated = Signal(str, str, int, str, object, int)
    summary = Signal(int, int, int)

    def __init__(self, jobs, options, output: Path):
        super().__init__()
        self.jobs = list(jobs)
        self.options = options
        self.output = Path(output)
        self.request = None
        self.cancel_all = threading.Event()
        self.cancel_current = threading.Event()
        self._lock = threading.Lock()
        self._active = False

    @classmethod
    def from_request(cls, request):
        if not request.items:
            raise ValueError('没有待处理文件')
        worker = cls([item.job for item in request.items], request.items[0].parameters, request.items[0].folder)
        worker.request = request
        return worker

    def prepare_folders(self):
        mapping = {}
        for item in self.request.items:
            if item.folder in mapping:
                continue
            folder = item.folder
            if item.sibling:
                i = 0
                while True:
                    candidate = folder if not i else folder.with_name(folder.name + f'_{i}')
                    try:
                        candidate.mkdir()
                        folder = candidate
                        break
                    except FileExistsError:
                        i += 1
                    except OSError as error:
                        mapping[item.folder] = error
                        break
            if item.folder not in mapping:
                mapping[item.folder] = folder
        return mapping

    def cancel(self, all_jobs=True):
        with self._lock:
            if all_jobs:
                self.cancel_all.set()
            if self._active:
                self.cancel_current.set()

    def notify(self, job):
        self.updated.emit(job.id, job.status, job.progress, job.error, job.output, job.output_size)

    def run(self):
        completed = failed = cancelled = 0
        folders = self.prepare_folders() if self.request else {}
        try:
            if not self.request:
                check_output_directory(self.output)
        except Exception as error:
            for job in self.jobs:
                job.status, job.error = '失败', str(error)
                self.notify(job)
            self.summary.emit(0, len(self.jobs), 0)
            return
        for index, job in enumerate(self.jobs):
            with self._lock:
                self.cancel_current.clear()
                self._active = True
                stopping = self.cancel_all.is_set()
            if stopping:
                job.status, job.error = '已取消', '批次已取消'
                cancelled += 1
                self.notify(job)
                with self._lock:
                    self._active = False
                continue
            destination = None
            job.progress, job.error, job.output_size, job.output = 0, '', 0, None
            try:
                job.status = '处理中'
                self.notify(job)
                if self.request:
                    item = self.request.items[index]
                    if item.preflight_error:
                        raise ValueError(item.preflight_error)
                    self.options = item.parameters
                    folder = folders[item.folder]
                    if isinstance(folder, Exception):
                        raise folder
                    self.output = folder
                    check_output_directory(self.output)
                job.parameters = self.options
                from .metadata import MetadataOptions,process_metadata
                if isinstance(self.options,MetadataOptions):
                    if job.inputs or job.path.suffix.lower()=='.livp':
                        count=0
                        while True:
                            destination=self.output/(job.path.stem+'_信息副本'+(f'_{count}' if count else ''))
                            try:destination.mkdir(); break
                            except FileExistsError:count+=1
                    else:
                        count=0
                        while True:
                            destination=self.output/(job.path.stem+'_信息副本'+(f'_{count}' if count else '')+job.path.suffix)
                            if self.options.supplements and destination.with_name(destination.name+'.xmp').exists():count+=1; continue
                            try:
                                with destination.open('xb'):pass
                                break
                            except FileExistsError:count+=1
                    def metadata_progress(value):
                        job.progress=value; self.notify(job)
                    job.outputs,job.metadata_report=process_metadata(job,self.options,destination,self.cancel_current,metadata_progress)
                    job.output,job.output_size,job.status,job.progress=destination,sum(p.stat().st_size for p in job.outputs),'完成',100
                    completed+=1
                    continue
                if isinstance(self.options, LiveOptions):
                    from .live import inspect_live, process_live
                    job.info = inspect_live(job.path, job.inputs, self.cancel_current)
                    if self.options.format == 'folder' or self.options.mode == 'both':
                        counter = 0
                        while True:
                            suffix = '' if not counter else f'_{counter}'
                            destination = self.output / (job.path.stem + ('_照片与视频' if self.options.mode=='both' else '_live') + suffix)
                            try:
                                destination.mkdir()
                                break
                            except FileExistsError:
                                counter += 1
                    else:
                        destination = reserve_output(job.path, self.output, self.options.format)
                    def live_progress(value):
                        job.progress = value
                        self.notify(job)
                    job.outputs = process_live(job, self.options, destination, self.cancel_current, live_progress)
                    job.output, job.output_size, job.status = destination, sum(p.stat().st_size for p in job.outputs), '完成'
                    completed += 1
                    continue
                job.info = probe(job.path)
                if (job.info.kind == 'video') != isinstance(self.options, VideoOptions):
                    raise ValueError('任务类型与所选参数不一致')
                destination = reserve_output(job.path, self.output, self.options.format)
                if isinstance(self.options, VideoOptions):
                    # Validate before launching a subprocess.
                    build_command(job.info, self.options, destination)
                def progress(value):
                    job.progress = value
                    self.notify(job)
                process = process_video if job.info.kind == 'video' else process_image
                process(job.info, self.options, destination, self.cancel_current, progress)
                job.outputs = (destination,)
                job.output, job.output_size, job.status = destination, destination.stat().st_size, '完成'
                completed += 1
            except Cancelled:
                job.status, job.error = '已取消', '任务已取消，可再次开始'
                cancelled += 1
                if destination:
                    if destination.is_dir():
                        destination.rmdir()
                    else:
                        destination.unlink(missing_ok=True)
            except Exception as error:
                logging.exception('处理失败：%s', job.path)
                job.status, job.error = '失败', str(error)
                from .preflight import classify_error
                job.error_category = classify_error(str(error))
                failed += 1
                if destination:
                    if destination.is_dir():
                        destination.rmdir()
                    else:
                        destination.unlink(missing_ok=True)
            finally:
                with self._lock:
                    self._active = False
                self.notify(job)
        if self.request:
            for folder in folders.values():
                if isinstance(folder, Path):
                    try:
                        if any(item.sibling for item in self.request.items if folders.get(item.folder) == folder):
                            folder.rmdir()  # Only empty folders created for this batch.
                    except OSError:
                        pass
        self.summary.emit(completed, failed, cancelled)


class Inspector(QThread):
    inspected = Signal(str, object, str)
    thumbnail = Signal(str, object)

    def __init__(self, jobs):
        super().__init__()
        self.jobs = list(jobs)
        self.cancel_event = threading.Event()

    def run(self):
        for job in self.jobs:
            if self.cancel_event.is_set():
                break
            try:
                if job.path.suffix.lower() == '.livp' or job.inputs:
                    from .live import inspect_live
                    info = inspect_live(job.path, job.inputs, self.cancel_event)
                else:
                    info = probe(job.path)
                self.inspected.emit(job.id, info, '')
                if not self.cancel_event.is_set():
                    try:
                        from .previews import thumbnail
                        self.thumbnail.emit(job.id, thumbnail(job))
                    except Exception:
                        logging.debug('缩略图不可用：%s', job.path, exc_info=True)
            except Exception as error:
                self.inspected.emit(job.id, None, str(error))


class HardwareDetector(QThread):
    detected = Signal(object)

    def __init__(self):
        super().__init__()
        self.cancel_event = threading.Event()

    def run(self):
        try:
            self.detected.emit(detect_hardware(self.cancel_event))
        except Exception:
            logging.exception('硬件编码器探测失败')
            self.detected.emit(set())


class PairMatcher(QThread):
    matched = Signal(object, object, str)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths
        self.cancel_event = threading.Event()

    def run(self):
        try:
            from .live import match_pairs
            pairs, remaining = match_pairs(self.paths, self.cancel_event)
            if not self.cancel_event.is_set():
                self.matched.emit(pairs, remaining, '')
        except Exception as error:
            if not self.cancel_event.is_set():
                self.matched.emit([], self.paths, str(error))
