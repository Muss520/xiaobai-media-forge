from pathlib import Path
import pytest


@pytest.mark.parametrize('codec', ['h264', 'hevc'])
def test_qsv_ultrafast_maps_to_supported_preset(codec):
    from mediaforge.video import build_command
    from mediaforge.models import MediaInfo, VideoOptions
    info = MediaInfo(Path('input.mp4'), 'video', 100, 128, 96, 1, 'h264', 'aac')
    args = build_command(info, VideoOptions(codec=codec, encoder='qsv', speed='ultrafast'), Path('result.mp4'))
    assert args[args.index('-preset') + 1] == 'veryfast'


def test_non_square_pixels_keep_display_aspect(tmp_path):
    import threading
    from mediaforge.probe import probe, run_tool
    from mediaforge.paths import tool_path
    from mediaforge.video import process_video
    from mediaforge.models import VideoOptions
    source = tmp_path / 'anamorphic.mp4'
    out = tmp_path / 'converted.mp4'
    created = run_tool([tool_path('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                       'color=s=320x240:d=0.3', '-vf', 'setsar=2/1', '-c:v', 'libx264', str(source)])
    assert created.returncode == 0
    process_video(probe(source), VideoOptions(), out, threading.Event(), lambda p: None)
    import json
    data = json.loads(run_tool([tool_path('ffprobe'), '-v', 'error', '-show_streams', '-of', 'json', str(out)]).stdout)
    assert data['streams'][0]['display_aspect_ratio'] == '8:3'


def test_remux_batch_incompatible_item_does_not_block_good_item(qt_app, tmp_path, monkeypatch):
    from mediaforge.window import MainWindow
    from mediaforge.probe import run_tool
    from mediaforge.paths import tool_path
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: 0)
    good, bad = tmp_path / 'good.mp4', tmp_path / 'bad.webm'
    for path, codec in [(good, 'libx264'), (bad, 'libvpx-vp9')]:
        assert run_tool([tool_path('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
                         'color=s=128x96:d=0.3', '-c:v', codec, str(path)]).returncode == 0
    window = MainWindow(settings_path=tmp_path / 'settings.json')
    window.hardware_enabled = False
    window.add_files([bad, good])
    for _ in range(300):
        qt_app.processEvents()
        QTest.qWait(10)
        if not window.inspectors:
            break
    window.output.setText(str(tmp_path / 'out'))
    window.panels['video'].remux.setChecked(True)
    window.start_batch()
    for _ in range(300):
        qt_app.processEvents()
        QTest.qWait(10)
        if not window.busy:
            break
    assert window.jobs['video'][0].status == '失败'
    assert window.jobs['video'][1].status == '完成'
    window.close()
