from dataclasses import dataclass, field
from pathlib import Path
import math

from .formats import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    kind: str
    size: int
    width: int
    height: int
    duration: float = 0
    video_codec: str = ''
    audio_codec: str = ''
    frames: int = 1
    sample_aspect_ratio: str = '1/1'
    fps: float = 0
    video_bitrate: int = 0
    audio_bitrate: int = 0
    pixel_format: str = ''
    color_space: str = ''
    color_transfer: str = ''
    bit_depth: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class VideoOptions:
    format: str = 'mp4'
    codec: str = 'h264'
    encoder: str = 'cpu'
    mode: str = 'quality'
    quality: int = 23
    bitrate: int = 2500
    speed: str = 'medium'
    width: int = 0
    height: int = 0
    aspect: bool = True
    fps: float = 0
    audio_codec: str = 'aac'
    audio_bitrate: int = 128
    sample_rate: int = 0
    channels: int = 0
    remux: bool = False
    target_bytes: int = 0
    pixel_format: str = 'yuv420p'
    profile: str = 'auto'
    keyframe_interval: int = 0
    metadata: bool = False
    resolution_preset: str = 'original'
    resolved_size: bool = False
    upscale: bool = False


@dataclass(frozen=True)
class ImageOptions:
    format: str = 'jpg'
    quality: int = 85
    png_level: int = 6
    lossless: bool = False
    width: int = 0
    height: int = 0
    aspect: bool = True
    upscale: bool = False
    metadata: bool = False
    background: str = '#ffffff'
    target_bytes: int = 0
    auto_resize: bool = False
    animation: str = 'preserve'
    frame_index: int = 0
    resolution_preset: str = 'original'
    resolved_size: bool = False


@dataclass(frozen=True)
class LiveOptions:
    mode: str = 'preserve'
    format: str = 'livp'
    image: ImageOptions = field(default_factory=ImageOptions)
    video: VideoOptions = field(default_factory=VideoOptions)
    target_bytes: int = 0
    animation_fps: float = 0
    video_copy: bool = True


@dataclass
class Job:
    path: Path
    info: MediaInfo | None = None
    output: Path | None = None
    status: str = '等待处理'
    progress: int = 0
    error: str = ''
    output_size: int = 0
    id: str = field(default_factory=lambda: __import__('uuid').uuid4().hex)
    inputs: tuple[Path, ...] = ()
    outputs: tuple[Path, ...] = ()
    parameters: object = None
    error_category: str = ''
    metadata_report: list = field(default_factory=list)


def target_size(w: int, h: int, width: int, height: int, aspect: bool, upscale: bool) -> tuple[int, int]:
    if w <= 0 or h <= 0 or width < 0 or height < 0:
        raise ValueError('图片或视频尺寸无效')
    if not width and not height:
        return w, h
    if aspect:
        scales = ([width / w] if width else []) + ([height / h] if height else [])
        factor = min(scales)
        if not upscale:
            factor = min(1, factor)
        return max(1, math.floor(w * factor)), max(1, math.floor(h * factor))
    tw, th = width or w, height or h
    return (tw, th) if upscale else (min(w, tw), min(h, th))


def human_size(size: int) -> str:
    value = float(size)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}'
        value /= 1024
    return str(size)
