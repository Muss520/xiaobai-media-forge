import json
import subprocess
import os
import time
from fractions import Fraction
from pathlib import Path
from PIL import Image, ImageOps
from .models import MediaInfo, VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from .paths import tool_path
from .formats import register_images
register_images()

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def run_tool(args: list[str], timeout: float = 30, cancel=None, input_text=None) -> subprocess.CompletedProcess:
    from .images import check_cancel
    env = dict(os.environ, LC_ALL='C', LC_CTYPE='C', LANG='C')
    if cancel is None:
        return subprocess.run(args, capture_output=True, encoding='utf-8', errors='replace',
                              creationflags=NO_WINDOW, timeout=timeout, env=env, input=input_text)
    check_cancel(cancel)
    child = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             stdin=subprocess.PIPE if input_text is not None else None,
                             encoding='utf-8', errors='replace', creationflags=NO_WINDOW, env=env)
    deadline = time.monotonic() + timeout
    sent = False
    try:
        while True:
            check_cancel(cancel)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(args, timeout)
            try:
                out, err = child.communicate(input=None if sent else input_text, timeout=min(.15, remaining))
                return subprocess.CompletedProcess(args, child.returncode, out, err)
            except subprocess.TimeoutExpired:
                sent = True
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate()


def probe(path: Path) -> MediaInfo:
    path = Path(path).resolve()
    size = path.stat().st_size
    if path.suffix.lower() in IMAGE_EXTENSIONS or path.suffix.lower() == '.ico':
        with Image.open(path) as image:
            frames = getattr(image, 'n_frames', 1)
            if frames > 1 and image.format not in {'GIF', 'WEBP', 'PNG'}:
                raise ValueError('不支持多页图片，请先拆分页面后处理')
            if image.format == 'PNG' and image.info.get('default_image'):
                frames -= 1
            image.load()
            width, height = ImageOps.exif_transpose(image).size
            return MediaInfo(path, 'image', size, width, height, frames=frames,
                             bit_depth=16 if '16' in image.mode else 8, pixel_format=image.mode)
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError('不支持此文件类型，请添加常见视频或静态图片')
    result = run_tool([tool_path('ffprobe'), '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)])
    if result.returncode:
        raise ValueError('无法读取视频：' + result.stderr.strip()[-1000:])
    data = json.loads(result.stdout)
    video = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    if not video:
        raise ValueError('文件中没有可处理的主视频轨道')
    audio = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), {})
    duration = data.get('format', {}).get('duration') or video.get('duration') or 0
    width, height = int(video.get('width', 0)), int(video.get('height', 0))
    try:
        sar = Fraction(video.get('sample_aspect_ratio', '1:1').replace(':', '/'))
        if sar <= 0:
            sar = Fraction(1)
    except (ValueError, ZeroDivisionError):
        sar = Fraction(1)
    for side in video.get('side_data_list', []):
        if abs(float(side.get('rotation', 0))) % 180 == 90:
            width, height = height, width
            sar = 1 / sar
    try:
        fps = float(Fraction(video.get('avg_frame_rate', '0/1')))
    except (ValueError, ZeroDivisionError):
        fps = 0
    return MediaInfo(path, 'video', size, width, height, float(duration),
                     video.get('codec_name', ''), audio.get('codec_name', ''), sample_aspect_ratio=str(sar), fps=fps,
                     video_bitrate=int(video.get('bit_rate') or 0), audio_bitrate=int(audio.get('bit_rate') or 0),
                     pixel_format=video.get('pix_fmt',''), color_space=video.get('color_space',''),
                     color_transfer=video.get('color_transfer',''),
                     bit_depth=int(video.get('bits_per_raw_sample') or (10 if '10' in video.get('pix_fmt','') else 8)),
                     metadata={'format':data.get('format',{}).get('tags',{}),'video':video.get('tags',{}),'audio':audio.get('tags',{})})
