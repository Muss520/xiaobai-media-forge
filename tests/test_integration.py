from pathlib import Path
from dataclasses import replace
import subprocess
import threading
import time
import pytest


@pytest.fixture
def clip(tmp_path):
    from mediaforge.paths import tool_path
    from mediaforge.probe import run_tool
    path = tmp_path / '视频 空格 & sample.mkv'
    result = run_tool([tool_path('ffmpeg'), '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i',
                       'testsrc2=s=320x240:r=24:d=1', '-f', 'lavfi', '-i',
                       'sine=frequency=440:sample_rate=44100:duration=1', '-c:v', 'libx264',
                       '-crf', '0', '-c:a', 'pcm_s16le', str(path)])
    assert result.returncode == 0, result.stderr
    return path


def test_video_real_transcode_and_remux(clip, tmp_path):
    from mediaforge.probe import probe, run_tool
    from mediaforge.paths import tool_path
    from mediaforge.video import process_video
    from mediaforge.models import VideoOptions
    info = probe(clip)
    out = tmp_path / '转换.mp4'
    values = []
    process_video(info, VideoOptions(width=160, fps=12), out, threading.Event(), values.append)
    output = probe(out)
    assert (output.width, output.height, output.video_codec, output.audio_codec) == (160, 120, 'h264', 'aac')
    assert output.size < info.size
    assert values[-1] == 100
    decoded = run_tool([tool_path('ffmpeg'), '-v', 'error', '-i', str(out), '-f', 'null', '-'])
    assert decoded.returncode == 0, decoded.stderr
    remux = tmp_path / '封装.mov'
    process_video(output, VideoOptions(format='mov', remux=True, audio_codec='copy'), remux, threading.Event(), lambda p: None)
    assert probe(remux).video_codec == 'h264'


@pytest.mark.parametrize('codec,format', [('hevc', 'mp4'), ('vp9', 'webm')])
def test_other_video_encoders(clip, tmp_path, codec, format):
    from mediaforge.video import process_video
    from mediaforge.probe import probe
    from mediaforge.models import VideoOptions
    out = tmp_path / f'result.{format}'
    process_video(probe(clip), VideoOptions(format=format, codec=codec, speed='fast',
                  audio_codec='opus' if format == 'webm' else 'aac'), out, threading.Event(), lambda p: None)
    assert probe(out).video_codec == codec


def test_video_cancel_cleans_partial(clip, tmp_path):
    from mediaforge.video import process_video
    from mediaforge.images import Cancelled
    from mediaforge.probe import probe
    from mediaforge.models import VideoOptions
    cancel = threading.Event()
    def progress(value):
        cancel.set()
    with pytest.raises(Cancelled):
        process_video(probe(clip), VideoOptions(width=1920, height=1440, speed='veryslow'),
                      tmp_path / 'cancel.mp4', cancel, progress)
    assert not list(tmp_path.glob('*.partial*'))
    assert not (tmp_path / 'cancel.mp4').exists()
    assert clip.exists()


@pytest.mark.parametrize('format', ['jpg', 'png', 'webp', 'bmp', 'tiff', 'ico'])
def test_all_image_outputs(tmp_path, format):
    from PIL import Image
    from mediaforge.images import process_image
    from mediaforge.models import ImageOptions
    from mediaforge.probe import probe
    path = tmp_path / '图像 & 中文.png'
    Image.new('RGBA', (96, 64), (10, 150, 200, 128)).save(path)
    out = tmp_path / f'result.{format}'
    process_image(probe(path), ImageOptions(format=format), out, threading.Event(), lambda p: None)
    with Image.open(out) as image:
        image.load()
        assert image.size == (96, 64)


def test_batch_continues_after_corrupt_input(tmp_path):
    from PySide6.QtCore import QCoreApplication
    from PIL import Image
    from mediaforge.models import Job, ImageOptions
    from mediaforge.queue import BatchWorker
    app = QCoreApplication.instance() or QCoreApplication([])
    bad = tmp_path / 'bad.png'
    bad.write_bytes(b'invalid')
    good = tmp_path / 'good.png'
    Image.new('RGB', (64, 32), 'blue').save(good)
    jobs = [Job(bad), Job(good)]
    worker = BatchWorker(jobs, ImageOptions(), tmp_path / 'out')
    worker.start()
    assert worker.wait(10000)
    assert jobs[0].status == '失败'
    assert jobs[1].status == '完成'
    assert jobs[1].output.exists()
    assert not list((tmp_path / 'out').glob('*.partial*'))


def test_output_directory_is_file(tmp_path):
    from mediaforge.paths import check_output_directory
    folder = tmp_path / 'not-directory'
    folder.write_text('file')
    with pytest.raises(OSError):
        check_output_directory(folder)


def test_audio_copy_rejects_changes(clip, tmp_path):
    from mediaforge.probe import probe
    from mediaforge.models import VideoOptions
    from mediaforge.video import build_command
    with pytest.raises(ValueError, match='采样率|声道'):
        build_command(probe(clip), VideoOptions(audio_codec='copy', channels=2), tmp_path / 'out.mp4')
