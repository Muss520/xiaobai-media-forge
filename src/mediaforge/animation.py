from dataclasses import replace
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from .models import target_size
from .paths import app_home,runtime_home, tool_path
from .probe import NO_WINDOW, probe
from .images import process_image, check_cancel
from .video import _stop_process


def video_to_animation(info, options, destination, cancel, progress, animation_fps=0):
    from .resolution import resolve_options
    options=resolve_options(info,options)
    width, height = target_size(info.width, info.height, options.width, options.height, False if options.resolved_size else options.aspect, False)
    fps = min(30, animation_fps or info.fps or 15)
    if info.duration <= 0 or width * height * info.duration * fps > 150_000_000:
        raise ValueError('动图预计超过 1.5 亿像素，请设置更小的画面尺寸')
    with TemporaryDirectory(prefix='live-animation-', dir=runtime_home() / 'temp') as folder:
        folder = Path(folder)
        intermediate = folder / 'animation.webp'
        progress_file = folder / 'progress.txt'
        args = [tool_path('ffmpeg'), '-v', 'error', '-nostdin', '-y', '-i', str(info.path),
                '-map', '0:V:0', '-an', '-vf', f'scale={width}:{height},fps={fps}',
                '-c:v', 'libwebp_anim', '-lossless', '1', '-loop', '0', '-progress',str(progress_file),'-nostats',str(intermediate)]
        check_cancel(cancel)
        with (folder / 'errors.txt').open('wb') as errors:
            process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=errors, creationflags=NO_WINDOW)
            try:
                while process.poll() is None:
                    check_cancel(cancel)
                    if progress_file.exists():
                        for line in reversed(progress_file.read_text(encoding='utf-8',errors='replace').splitlines()):
                            if line.startswith('out_time_us='):
                                try:
                                    progress(min(39,max(0,int(int(line.partition('=')[2])/1_000_000/info.duration*40))))
                                except ValueError:
                                    pass
                                break
                    try:
                        process.wait(timeout=.1)
                    except subprocess.TimeoutExpired:
                        pass
                if process.returncode:
                    raise ValueError('动态部分转换失败：' + (folder / 'errors.txt').read_text(encoding='utf-8', errors='replace')[-1000:])
            finally:
                _stop_process(process)
        progress(40)
        process_image(probe(intermediate), replace(options, animation='preserve'), destination,
                      cancel, lambda p: progress(40 + int(p * .6)))
        return destination
