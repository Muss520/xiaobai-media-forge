import logging
import queue
import subprocess
import threading
import time
from pathlib import Path
from dataclasses import replace
from .formats import VIDEO_FORMATS, AUDIO_FORMATS
from .images import Cancelled
from .models import MediaInfo, VideoOptions, target_size
from .paths import tool_path, temporary_output
from .probe import NO_WINDOW, probe, run_tool

CPU_ENCODERS = {'h264': 'libx264', 'hevc': 'libx265', 'vp9': 'libvpx-vp9', 'vp8': 'libvpx',
                'av1': 'libaom-av1', 'mpeg4': 'mpeg4', 'mpeg2': 'mpeg2video',
                'mpeg1': 'mpeg1video', 'wmv2': 'wmv2', 'flv1': 'flv'}
COPY_VIDEO = {'mp4': {'h264', 'hevc', 'mpeg4', 'av1'},
              'mov': {'h264', 'hevc', 'mpeg4', 'prores', 'mjpeg'},
              'webm': {'vp8', 'vp9', 'av1'}}
COPY_AUDIO = {'mp4': {'aac', 'mp3', 'ac3', 'eac3', 'alac'},
              'mov': {'aac', 'mp3', 'ac3', 'alac', 'pcm_s16le', 'pcm_s24le', 'pcm_s32le'},
              'webm': {'opus', 'vorbis'}}
for _fmt, _codecs in VIDEO_FORMATS.items():
    COPY_VIDEO.setdefault(_fmt, {{'mpeg2': 'mpeg2video', 'mpeg1': 'mpeg1video'}.get(c, c) for c in _codecs})
for _fmt, _codecs in AUDIO_FORMATS.items():
    COPY_AUDIO.setdefault(_fmt, set(_codecs))


def build_command(info: MediaInfo, o: VideoOptions, destination: Path) -> list[str]:
    from .resolution import resolve_options
    o=resolve_options(info,o)
    if o.format not in VIDEO_FORMATS:
        raise ValueError('不支持的视频输出容器')
    if info.path.resolve() == destination.resolve():
        raise ValueError('输出文件不能覆盖原文件')
    if min(o.width, o.height) < 0 or not 0 <= o.fps <= 240:
        raise ValueError('视频尺寸或帧率无效')
    args = [tool_path('ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-i', str(info.path), '-map', '0:V:0', '-map', '0:a:0?', '-sn', '-dn']
    if o.remux:
        if o.resolution_preset not in {'original','custom'}:
            raise ValueError('直接封装转换不能修改分辨率，请选择原尺寸或关闭直接封装')
        if o.target_bytes:
            raise ValueError('直接封装转换不能控制目标体积，请选择重新编码')
        if o.width or o.height or o.fps or o.sample_rate or o.channels:
            raise ValueError('直接封装转换不能修改尺寸、帧率、采样率或声道')
        if o.format != 'mkv' and info.video_codec not in COPY_VIDEO[o.format]:
            raise ValueError(f'{info.video_codec} 视频编码不兼容 {o.format.upper()}，请关闭直接封装转换')
        if o.audio_codec != 'copy':
            raise ValueError('直接封装转换必须保持原音频；如需修改或移除音频，请关闭此模式')
        if info.audio_codec and o.format != 'mkv' and info.audio_codec not in COPY_AUDIO[o.format]:
            raise ValueError(f'{info.audio_codec} 音频不兼容 {o.format.upper()}，请使用重新编码')
        args += ['-c', 'copy']
    else:
        if o.codec not in VIDEO_FORMATS[o.format]:
            raise ValueError(f'{o.codec} 不兼容 {o.format.upper()} 输出容器')
        if o.encoder not in {'cpu', 'nvenc', 'qsv', 'amf'} or (o.codec not in {'h264', 'hevc', 'av1'} and o.encoder != 'cpu'):
            raise ValueError('所选编码器不可用于当前视频编码')
        if o.mode not in {'quality', 'bitrate', 'size'} or not 0 <= o.quality <= (63 if o.codec in {'vp9', 'vp8', 'av1'} else 51):
            raise ValueError('视频质量模式或质量值无效')
        if not 1 <= o.bitrate <= 1000000 or o.speed not in {'ultrafast', 'fast', 'medium', 'slow', 'veryslow'}:
            raise ValueError('视频码率或编码速度无效')
        encoder = CPU_ENCODERS[o.codec] if o.encoder == 'cpu' else f'{o.codec}_{o.encoder}'
        allowed = {'yuv420p'} | ({'yuv420p10le'} if o.codec in {'hevc','vp9','av1'} and o.encoder == 'cpu' else set())
        if o.pixel_format not in allowed:
            raise ValueError('当前编码器不支持所选位深，请选择 8 位或 CPU HEVC/VP9/AV1')
        profiles = {'h264':{'auto','baseline','main','high'}, 'hevc':{'auto','main','main10'}}
        if o.profile not in profiles.get(o.codec, {'auto'}):
            raise ValueError('编码规格与视频编码不兼容')
        if o.codec == 'hevc' and o.profile != 'auto' and (o.profile == 'main10') != (o.pixel_format == 'yuv420p10le'):
            raise ValueError('HEVC main10 需选择 10 位，main 需选择 8 位')
        if not 0 <= o.keyframe_interval <= 10000:
            raise ValueError('关键帧间隔应为 0–10000 帧')
        args += ['-c:v', encoder, '-pix_fmt', o.pixel_format]
        if o.profile != 'auto':
            args += ['-profile:v', o.profile]
        if o.keyframe_interval:
            args += ['-g', str(o.keyframe_interval)]
        if o.mode in {'bitrate', 'size'}:
            args += ['-b:v', f'{o.bitrate}k']
        elif o.encoder == 'cpu':
            if o.codec in {'h264', 'hevc', 'vp9', 'vp8', 'av1'}:
                args += ['-crf', str(o.quality)]
            else:
                args += ['-q:v', str(max(2, min(31, round(o.quality / 51 * 29 + 2))))]
            if o.codec in {'vp9', 'vp8', 'av1'}:
                args += ['-b:v', '0']
        elif o.encoder == 'nvenc':
            args += ['-rc', 'vbr', '-cq', str(o.quality), '-b:v', '0']
        elif o.encoder == 'qsv':
            args += ['-global_quality', str(o.quality)]
        else:
            args += ['-rc', 'cqp', '-qp_i', str(o.quality), '-qp_p', str(o.quality)]
        if o.encoder == 'cpu' and o.codec in {'h264', 'hevc'}:
            args += ['-preset', o.speed]
        elif o.codec in {'vp9', 'vp8'}:
            args += ['-deadline', 'good', '-cpu-used', str({'ultrafast': 5, 'fast': 4, 'medium': 2, 'slow': 1, 'veryslow': 0}[o.speed])]
        elif o.encoder == 'cpu' and o.codec == 'av1':
            args += ['-cpu-used', str({'ultrafast': 8, 'fast': 6, 'medium': 4, 'slow': 2, 'veryslow': 0}[o.speed]), '-row-mt', '1']
        elif o.encoder == 'nvenc':
            args += ['-preset', {'ultrafast': 'p1', 'fast': 'p3', 'medium': 'p4', 'slow': 'p6', 'veryslow': 'p7'}[o.speed]]
        elif o.encoder == 'qsv':
            args += ['-preset', 'veryfast' if o.speed == 'ultrafast' else o.speed]
        elif o.encoder == 'amf':
            args += ['-quality', 'speed' if o.speed in {'ultrafast', 'fast'} else 'quality' if o.speed in {'slow', 'veryslow'} else 'balanced']
        width, height = target_size(info.width, info.height, o.width, o.height, False if o.resolved_size else o.aspect, o.upscale)
        width, height = max(2, width // 2 * 2), max(2, height // 2 * 2)
        sar = info.sample_aspect_ratio if o.aspect else '1/1'
        args += ['-vf', f'scale={width}:{height},setsar={sar}']
        if o.fps:
            args += ['-r', str(o.fps)]
        if o.audio_codec == 'none':
            args += ['-an']
        else:
            valid = {'aac', 'opus', 'mp3', 'pcm_s16le', 'copy', 'mp2', 'wmav2', 'ac3', 'vorbis'}
            if o.audio_codec not in valid:
                raise ValueError('不支持的音频编码')
            if o.audio_codec == 'copy':
                if o.sample_rate or o.channels:
                    raise ValueError('保持原音频时不能修改采样率或声道')
                if info.audio_codec and o.format != 'mkv' and info.audio_codec not in COPY_AUDIO[o.format]:
                    raise ValueError('原音频编码不兼容输出容器')
            elif o.audio_codec not in AUDIO_FORMATS[o.format]:
                raise ValueError(f'{o.audio_codec} 音频不兼容 {o.format.upper()} 容器')
            audio_encoder = {'opus': 'libopus', 'mp3': 'libmp3lame', 'vorbis': 'libvorbis'}.get(o.audio_codec, o.audio_codec)
            args += ['-c:a', audio_encoder]
            if o.audio_codec not in {'copy', 'pcm_s16le'}:
                if not 16 <= o.audio_bitrate <= 512:
                    raise ValueError('音频码率需为 16–512 kbps')
                args += ['-b:a', f'{o.audio_bitrate}k']
            if o.sample_rate:
                if o.sample_rate not in {8000, 16000, 22050, 24000, 32000, 44100, 48000, 96000}:
                    raise ValueError('音频采样率无效')
                if o.audio_codec == 'opus' and o.sample_rate not in {8000, 16000, 24000, 48000}:
                    raise ValueError('Opus 采样率请选择 8000、16000、24000 或 48000 Hz')
                args += ['-ar', str(o.sample_rate)]
            if o.channels:
                if o.channels not in {1, 2}:
                    raise ValueError('声道数请选择单声道或立体声')
                args += ['-ac', str(o.channels)]
    args += ['-map_metadata', '0' if o.metadata else '-1', '-map_chapters', '-1']
    if o.format in {'mp4', 'mov'}:
        args += ['-movflags', '+faststart']
        if not o.remux and o.codec == 'hevc':
            args += ['-tag:v', 'hvc1']
    args += ['-progress', 'pipe:1', '-nostats', str(destination)]
    return args


def _stop_process(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _process_once(info: MediaInfo, options: VideoOptions, destination: Path,
                  cancel: threading.Event, progress, extra=(), cwd=None) -> Path:
    temp = temporary_output(destination)
    command = build_command(info, options, temp)
    command[-1:-1] = list(extra)
    process = None
    lines = queue.Queue()
    errors = []
    readers = []
    def read_stdout(stream):
        try:
            for line in stream:
                lines.put(line.strip())
        finally:
            stream.close()
    def read_stderr(stream):
        try:
            for line in stream:
                errors.append(line.strip())
                if len(errors) > 100:
                    del errors[:50]
        finally:
            stream.close()
    try:
        if cancel.is_set():
            raise Cancelled('已取消')
        logging.info('转换 %s -> %s', info.path, destination)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', errors='replace', creationflags=NO_WINDOW, cwd=cwd)
        readers = [threading.Thread(target=read_stdout, args=(process.stdout,), daemon=True),
                   threading.Thread(target=read_stderr, args=(process.stderr,), daemon=True)]
        for reader in readers:
            reader.start()
        while process.poll() is None or not lines.empty():
            if cancel.is_set():
                raise Cancelled('已取消')
            try:
                line = lines.get(timeout=.1)
            except queue.Empty:
                continue
            if line.startswith('out_time_us=') and info.duration:
                try:
                    progress(min(98, int(float(line.split('=', 1)[1]) / 1e6 / info.duration * 100)))
                except ValueError:
                    pass
        for reader in readers:
            reader.join(timeout=2)
        if process.returncode:
            suffix = '。可选择 CPU 后重试' if options.encoder != 'cpu' else ''
            raise ValueError(('视频转换失败：' + '\n'.join(errors)[-2500:]) + suffix)
        if cancel.is_set():
            raise Cancelled('已取消')
        result = probe(temp)
        if not result.width or not result.height or temp.stat().st_size == 0:
            raise ValueError('视频输出验证失败')
        if cancel.is_set():
            raise Cancelled('已取消')
        temp.replace(destination)
        progress(100)
        return destination
    finally:
        if process:
            _stop_process(process)
        for reader in readers:
            reader.join(timeout=2)
        temp.unlink(missing_ok=True)


def target_bitrate(info, options):
    if info.duration <= 0 or options.target_bytes <= 0:
        raise ValueError('目标体积模式需要正数体积和有效视频时长')
    if options.remux:
        raise ValueError('直接封装转换不能控制目标体积')
    if info.audio_codec and options.audio_codec in {'copy', 'pcm_s16le'}:
        raise ValueError('目标体积模式请选择有损音频编码或移除音频，以便计算音频预算')
    audio = options.audio_bitrate * 1000 * info.duration / 8 if info.audio_codec and options.audio_codec != 'none' else 0
    overhead = max(4096, options.target_bytes * .04)
    bitrate = int((options.target_bytes - audio - overhead) * 8 / info.duration / 1000)
    if bitrate < 8:
        raise ValueError('目标体积过小，无法容纳音频、封装和有效视频；请提高上限或移除音频')
    return bitrate


def process_video(info: MediaInfo, options: VideoOptions, destination: Path,
                  cancel: threading.Event, progress) -> Path:
    if options.mode != 'size':
        return _process_once(info, options, destination, cancel, progress)
    from tempfile import TemporaryDirectory
    from .paths import app_home,runtime_home
    bitrate = target_bitrate(info, options)
    (runtime_home() / 'temp').mkdir(exist_ok=True)
    with TemporaryDirectory(prefix='video-size-', dir=runtime_home() / 'temp') as folder:
        folder = Path(folder)
        for attempt in range(3):
            if cancel.is_set():
                raise Cancelled('已取消')
            params = replace(options, mode='bitrate', bitrate=bitrate, target_bytes=0)
            result = folder / ('encoded.' + options.format)
            two_pass = options.encoder == 'cpu' and options.codec in {'h264', 'hevc', 'vp9', 'vp8', 'av1', 'mpeg4', 'mpeg2'}
            for stage in range(1, 3) if two_pass else (2,):
                extra = []
                if two_pass:
                    if options.codec == 'hevc':
                        extra = ['-x265-params', f'pass={stage}:stats=encoding.stats']
                    else:
                        extra = ['-pass', str(stage), '-passlogfile', 'encoding']
                _process_once(info, params, result, cancel,
                    lambda p, stage=stage: progress(min(98, int((stage - 1) * 48 + p * .48))), extra, str(folder))
            actual = result.stat().st_size
            if actual <= options.target_bytes:
                if cancel.is_set():
                    raise Cancelled('已取消')
                # Both paths are on the user's requested volume only when using this copy;
                # publish through an adjacent temporary file to support another output drive.
                import shutil
                temp = temporary_output(destination)
                try:
                    shutil.copyfile(result, temp)
                    if cancel.is_set():
                        raise Cancelled('已取消')
                    temp.replace(destination)
                finally:
                    temp.unlink(missing_ok=True)
                progress(100)
                return destination
            bitrate = max(8, int(bitrate * options.target_bytes / actual * .90))
        raise ValueError('三次编码后仍无法达到目标体积，请提高体积上限、降低尺寸或移除音频')


def detect_hardware(cancel: threading.Event | None = None) -> set[str]:
    available = set()
    for backend in ('nvenc', 'qsv', 'amf'):
        for codec in ('h264', 'hevc', 'av1'):
            if cancel and cancel.is_set():
                return available
            encoder = f'{codec}_{backend}'
            try:
                result = run_tool([tool_path('ffmpeg'), '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                                   'color=c=black:s=128x128:r=25:d=0.12', '-frames:v', '2',
                                   '-c:v', encoder, '-pix_fmt', 'yuv420p', '-f', 'null', '-'], timeout=8)
                if result.returncode == 0:
                    available.add(encoder)
            except (OSError, subprocess.TimeoutExpired):
                logging.info('硬件探测不可用：%s', encoder)
    return available
