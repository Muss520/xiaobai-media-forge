import threading
from pathlib import Path
from PIL import Image
import pytest


@pytest.mark.parametrize('format', ['jpg', 'png', 'webp', 'tiff'])
def test_metadata_retained_and_removed(tmp_path, format):
    from mediaforge.images import process_image
    from mediaforge.probe import probe
    from mediaforge.models import ImageOptions
    source = tmp_path / 'metadata.jpg'
    exif = Image.Exif()
    exif[315] = 'Test Photographer'
    Image.new('RGB', (48, 32), 'orange').save(source, exif=exif)
    preserved = tmp_path / f'preserved.{format}'
    stripped = tmp_path / f'stripped.{format}'
    process_image(probe(source), ImageOptions(format=format, metadata=True), preserved, threading.Event(), lambda p: None)
    process_image(probe(source), ImageOptions(format=format), stripped, threading.Event(), lambda p: None)
    with Image.open(preserved) as image:
        assert image.getexif().get(315) == 'Test Photographer'
    with Image.open(stripped) as image:
        assert not image.getexif().get(315)


def test_no_audio_input(tmp_path):
    from mediaforge.probe import probe, run_tool
    from mediaforge.paths import tool_path
    from mediaforge.video import process_video
    from mediaforge.models import VideoOptions
    source = tmp_path / 'silent.mp4'
    result = run_tool([tool_path('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                       'color=c=blue:s=128x96:d=0.3', '-c:v', 'libx264', str(source)])
    assert result.returncode == 0
    output = tmp_path / 'converted.mp4'
    process_video(probe(source), VideoOptions(), output, threading.Event(), lambda p: None)
    assert probe(output).audio_codec == ''


def test_animated_png_detected(tmp_path):
    from mediaforge.probe import probe
    source = tmp_path / 'animated.png'
    Image.new('RGB', (16, 16), 'red').save(source, save_all=True,
                        append_images=[Image.new('RGB', (16, 16), 'blue')], duration=100)
    assert probe(source).frames == 2


def test_queue_cancel_all_preserves_sources(qt_app, tmp_path):
    from mediaforge.models import Job, ImageOptions
    from mediaforge.queue import BatchWorker
    files = []
    for i in range(3):
        path = tmp_path / f'{i}.png'
        Image.new('RGB', (16, 16), 'red').save(path)
        files.append(path)
    worker = BatchWorker([Job(path) for path in files], ImageOptions(), tmp_path / 'output')
    worker.cancel(True)
    worker.start()
    assert worker.wait(5000)
    assert all(job.status == '已取消' for job in worker.jobs)
    assert all(path.exists() for path in files)
    assert not list((tmp_path / 'output').iterdir())


def test_unwritable_output_real_windows_permissions(tmp_path):
    import csv
    import subprocess
    from mediaforge.paths import check_output_directory
    path = tmp_path / 'locked'
    path.mkdir()
    identity = subprocess.run(['whoami', '/user', '/fo', 'csv', '/nh'], capture_output=True, text=True)
    if identity.returncode:
        pytest.skip('Windows identity unavailable for isolated ACL test')
    sid = next(csv.reader(identity.stdout.strip().splitlines()))[1]
    denied = subprocess.run(['icacls', str(path), '/deny', f'*{sid}:(W)'], capture_output=True)
    if denied.returncode:
        pytest.skip('Cannot apply temporary deny-write ACL')
    try:
        with pytest.raises((OSError, ValueError)):
            check_output_directory(path)
    finally:
        restored = subprocess.run(['icacls', str(path), '/remove:d', '*' + sid], capture_output=True)
        assert restored.returncode == 0, 'Temporary test ACL must be restored'
