import threading
from pathlib import Path
import pytest
from PIL import Image
from mediaforge.models import ImageOptions, VideoOptions, MediaInfo
from mediaforge.images import process_image
from mediaforge.probe import probe
from mediaforge.video import build_command


def test_new_video_containers():
    info = MediaInfo(Path('source.mp4'), 'video', 1000, 160, 120, 2, 'h264')
    for fmt, codec, audio in [('avi', 'mpeg4', 'mp3'), ('ts', 'h264', 'aac'),
                              ('mpeg', 'mpeg2', 'mp2'), ('wmv', 'wmv2', 'wmav2'),
                              ('flv', 'h264', 'aac'), ('webm', 'av1', 'opus')]:
        args = build_command(info, VideoOptions(format=fmt, codec=codec, audio_codec=audio), Path('out.' + fmt))
        assert '-c:v' in args


def test_image_target_bytes(tmp_path):
    source = tmp_path / 'noise.png'
    Image.effect_noise((400, 300), 80).convert('RGB').save(source)
    target = tmp_path / 'out.jpg'
    process_image(probe(source), ImageOptions(target_bytes=18000), target, threading.Event(), lambda p: None)
    assert 0 < target.stat().st_size <= 18000
    assert Image.open(target).size == (400, 300)


def test_animation_preserved_and_static_requires_choice(tmp_path):
    source = tmp_path / 'animated.gif'
    Image.new('RGB', (40, 30), 'red').save(source, save_all=True,
        append_images=[Image.new('RGB', (40, 30), 'blue')], duration=[100, 200], loop=2)
    info = probe(source)
    assert info.frames == 2
    result = tmp_path / 'out.webp'
    process_image(info, ImageOptions(format='webp'), result, threading.Event(), lambda p: None)
    with Image.open(result) as image:
        assert image.n_frames == 2 and image.info['loop'] == 3
    with pytest.raises(ValueError, match='静态|帧'):
        process_image(info, ImageOptions(), tmp_path / 'out.jpg', threading.Event(), lambda p: None)


def test_lossless_target_impossible_does_not_publish(tmp_path):
    source = tmp_path / 'noise.png'
    Image.effect_noise((100, 100), 80).save(source)
    target = tmp_path / 'out.png'
    with pytest.raises(ValueError, match='体积|目标'):
        process_image(probe(source), ImageOptions(format='png', target_bytes=20), target, threading.Event(), lambda p: None)
    assert not target.exists()


def test_video_target_real_encode_and_impossible_budget(tmp_path):
    from mediaforge.paths import tool_path
    from mediaforge.probe import run_tool
    from mediaforge.video import process_video
    source = tmp_path / 'source.mp4'
    result = run_tool([tool_path('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=s=160x120:r=24:d=2', '-c:v', 'libx264', '-crf', '0', str(source)])
    assert result.returncode == 0, result.stderr
    info = probe(source)
    dest = tmp_path / 'target.mp4'
    process_video(info, VideoOptions(mode='size', target_bytes=30000), dest, threading.Event(), lambda p: None)
    assert 0 < dest.stat().st_size <= 30000
    assert probe(dest).video_codec == 'h264'
    with pytest.raises(ValueError, match='体积|目标'):
        process_video(info, VideoOptions(mode='size', target_bytes=10), tmp_path / 'impossible.mp4',
                      threading.Event(), lambda p: None)
    assert not (tmp_path / 'impossible.mp4').exists()


def test_livp_missing_and_unsafe_members(tmp_path):
    import zipfile
    from mediaforge import live
    bad = tmp_path / 'unsafe.livp'
    with zipfile.ZipFile(bad, 'w') as z:
        z.writestr('../escape.jpg', b'invalid')
        z.writestr('clip.mov', b'invalid')
    with pytest.raises(ValueError, match='路径|安全'):
        live.inspect_live(bad)
    missing = tmp_path / 'missing.livp'
    with zipfile.ZipFile(missing, 'w') as z:
        z.writestr('image.jpg', b'invalid')
    with pytest.raises(ValueError, match='配对|视频|MOV'):
        live.inspect_live(missing)
    assert not (tmp_path.parent / 'escape.jpg').exists()


def test_core_controls_visible_and_live_page(qt_app, tmp_path):
    from mediaforge.window import MainWindow
    window = MainWindow(settings_path=tmp_path / 'settings.json')
    window.hardware_enabled = False
    panel = window.panels['video']
    assert not panel.width.parentWidget().isHidden()
    assert panel.mode.findData('size') >= 0
    assert 'live' in window.jobs
    window.close()


@pytest.mark.parametrize('fmt', ['heic', 'avif', 'gif', 'apng'])
def test_extended_static_image_outputs(tmp_path, fmt):
    source = tmp_path / 'source.png'
    Image.new('RGB', (80, 60), 'orange').save(source)
    output = tmp_path / ('out.' + fmt)
    process_image(probe(source), ImageOptions(format=fmt), output, threading.Event(), lambda p: None)
    assert probe(output).width == 80


def test_real_live_photo_preserve_and_ordinary(tmp_path):
    import zipfile
    from mediaforge.live import process_live, inspect_live, verify_pair
    from mediaforge.models import LiveOptions, Job
    root = Path(__file__).parent / 'artifacts' / 'live-reference'
    photo, movie = root / 'keyPhoto.heic', root / 'pairedVideo.mov'
    assert photo.is_file() and movie.is_file(), '真实 Live Photo 验收素材应保存在项目中'
    package = tmp_path / '原始 Live.livp'
    with zipfile.ZipFile(package, 'w') as z:
        z.write(photo, 'photo.heic')
        z.write(movie, 'photo.mov')
    assert inspect_live(package).kind == 'live'
    job = Job(package)
    output = tmp_path / '保留 Live.livp'
    process_live(job, LiveOptions(image=ImageOptions(width=320)), output, threading.Event(), lambda p: None)
    with zipfile.ZipFile(output) as z:
        assert z.read('photo.mov') == movie.read_bytes()
        z.extractall(tmp_path / 'validated')
    assert verify_pair(tmp_path / 'validated/photo.jpg', tmp_path / 'validated/photo.mov')
    assert probe(tmp_path / 'validated/photo.jpg').width == 320
    video = tmp_path / '普通.mp4'
    process_live(job, LiveOptions(mode='video', format='mp4'), video, threading.Event(), lambda p: None)
    assert probe(video).video_codec == 'h264'


def test_live_animation_and_folder(tmp_path):
    from mediaforge.live import process_live
    from mediaforge.models import LiveOptions, Job
    root = Path(__file__).parent / 'artifacts' / 'live-reference'
    job = Job(root / 'keyPhoto.heic', inputs=(root / 'keyPhoto.heic', root / 'pairedVideo.mov'))
    folder = tmp_path / 'pair'
    folder.mkdir()
    outputs = process_live(job, LiveOptions(format='folder'), folder, threading.Event(), lambda p: None)
    assert len(outputs) == 2 and all(p.exists() for p in outputs)
    gif = tmp_path / 'dynamic.gif'
    process_live(job, LiveOptions(mode='animation', format='gif', image=ImageOptions(format='gif', width=160)),
                 gif, threading.Event(), lambda p: None)
    assert probe(gif).frames > 1


@pytest.mark.parametrize('fmt,codec,audio', [('avi','mpeg4','mp3'), ('ts','h264','aac'),
    ('mpeg','mpeg2','mp2'), ('wmv','wmv2','wmav2'), ('flv','h264','aac'),
    ('webm','vp8','opus'), ('webm','av1','opus'), ('mp4','av1','aac')])
def test_new_formats_real_encode(tmp_path, fmt, codec, audio):
    from mediaforge.probe import run_tool
    from mediaforge.paths import tool_path
    from mediaforge.video import process_video
    source = tmp_path / 'source.mp4'
    r = run_tool([tool_path('ffmpeg'), '-v', 'error', '-y', '-f', 'lavfi', '-i',
        'testsrc2=s=160x120:r=24:d=0.5', '-f', 'lavfi', '-i', 'sine=duration=0.5:sample_rate=44100',
        '-c:v','libx264','-c:a','aac',str(source)])
    assert r.returncode == 0, r.stderr
    out = tmp_path / ('out.' + fmt)
    process_video(probe(source), VideoOptions(format=fmt, codec=codec, audio_codec=audio, speed='fast'),
                  out, threading.Event(), lambda p: None)
    actual = probe(out)
    assert actual.width == 160
    expected = {'mpeg2': 'mpeg2video', 'vp8': 'vp8'}.get(codec, codec)
    assert actual.video_codec == expected
    r = run_tool([tool_path('ffmpeg'), '-v','error','-i',str(out),'-f','null','-'])
    assert r.returncode == 0, r.stderr


def test_live_video_ui_matches_format(qt_app):
    from mediaforge.options import LivePanel, select
    panel = LivePanel()
    select(panel.mode, 'video')
    select(panel.format, 'wmv')
    assert panel.video_panel.format.currentData() == 'wmv'
    assert panel.snapshot().video.codec == 'wmv2'


def test_live_heic_export_and_cancel_cleanup(tmp_path):
    from mediaforge.live import process_live, verify_pair
    from mediaforge.models import LiveOptions, Job
    from mediaforge.images import Cancelled
    root = Path(__file__).parent / 'artifacts' / 'live-reference'
    job = Job(root / 'keyPhoto.heic', inputs=(root / 'keyPhoto.heic', root / 'pairedVideo.mov'))
    folder = tmp_path / 'heic-pair'
    folder.mkdir()
    process_live(job, LiveOptions(format='folder', image=ImageOptions(format='heic', width=160)),
                 folder, threading.Event(), lambda p: None)
    assert verify_pair(folder / 'photo.heic', folder / 'photo.mov')
    cancel = threading.Event()
    with pytest.raises(Cancelled):
        process_live(job, LiveOptions(), tmp_path / 'cancel.livp', cancel,
                     lambda p: cancel.set() if p >= 20 else None)
    assert not (tmp_path / 'cancel.livp').exists()
    assert not list(tmp_path.glob('*.partial*'))


def test_animated_output_timing_and_explicit_frame(tmp_path):
    source = tmp_path / 'source.gif'
    Image.new('RGB',(20,20),'red').save(source,save_all=True,
        append_images=[Image.new('RGB',(20,20),'blue')],duration=[100,200],loop=3)
    out = tmp_path / 'out.apng'
    process_image(probe(source), ImageOptions(format='apng'), out, threading.Event(), lambda p: None)
    with Image.open(out) as im:
        assert im.n_frames == 2 and im.info['loop'] == 4
        assert im.info['duration'] == 100
        im.seek(1)
        assert im.info['duration'] == 200
    still = tmp_path / 'blue.png'
    process_image(probe(source), ImageOptions(format='png', animation='frame', frame_index=1),
                  still, threading.Event(), lambda p: None)
    with Image.open(still) as im:
        assert im.getpixel((0,0))[:3] == (0,0,255)


def test_live_only_one_target_size_control(qt_app):
    from mediaforge.options import LivePanel, select
    panel = LivePanel()
    select(panel.mode, 'image')
    assert panel.image_panel.target_bytes.isHidden()
    select(panel.mode, 'video')
    assert panel.video_panel.target_bytes.isHidden()
    panel.target_bytes.setValue(1024 * 1024)
    assert panel.snapshot().video.target_bytes == 1024 * 1024


def test_gif_without_loop_stays_single_play(tmp_path):
    source = tmp_path / 'once.gif'
    Image.new('RGB',(20,20),'red').save(source,save_all=True,
        append_images=[Image.new('RGB',(20,20),'blue')],duration=100)
    result = tmp_path / 'out.webp'
    process_image(probe(source), ImageOptions(format='webp'), result, threading.Event(), lambda p: None)
    with Image.open(result) as im:
        assert im.info['loop'] == 1


def test_apng_poster_not_in_animation(tmp_path):
    source = tmp_path / 'poster.png'
    Image.new('RGB',(20,20),'green').save(source, save_all=True, default_image=True,
        append_images=[Image.new('RGB',(20,20),'red'),Image.new('RGB',(20,20),'blue')],
        duration=[100,200],loop=1)
    result = tmp_path / 'out.webp'
    assert probe(source).frames == 2
    process_image(probe(source), ImageOptions(format='webp'), result, threading.Event(), lambda p: None)
    with Image.open(result) as im:
        assert im.n_frames == 2
        assert im.convert('RGB').getpixel((0,0))[0] > 240


def test_mpeg2_remux_compatibility():
    info = MediaInfo(Path('source.mpeg'),'video',1000,160,120,2,'mpeg2video','mp2')
    command = build_command(info, VideoOptions(format='ts',remux=True,audio_codec='copy'),Path('out.ts'))
    assert command[command.index('-c')+1] == 'copy'


def test_live_unpack_cancelled_before_decode(tmp_path):
    from mediaforge.live import components
    from mediaforge.images import Cancelled
    import zipfile
    source = tmp_path / 'cancel.livp'
    with zipfile.ZipFile(source,'w') as z:
        z.writestr('photo.jpg',b'invalid')
        z.writestr('video.mov',b'invalid')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        with components(source,cancel=cancel):
            pass


def test_live_unicode_paths_read_and_write(tmp_path):
    from mediaforge.live import process_live, verify_pair
    from mediaforge.models import LiveOptions, Job
    import shutil
    root = Path(__file__).parent / 'artifacts/live-reference'
    folder = tmp_path / '中文配对 空格'
    folder.mkdir()
    photo, movie = folder/'照片.heic', folder/'动态.mov'
    shutil.copyfile(root/'keyPhoto.heic', photo)
    shutil.copyfile(root/'pairedVideo.mov', movie)
    assert verify_pair(photo,movie)
    job = Job(photo,inputs=(photo,movie))
    process_live(job,LiveOptions(),tmp_path/'中文结果.livp',threading.Event(),lambda p: None)
