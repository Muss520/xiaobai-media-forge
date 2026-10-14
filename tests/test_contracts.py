from pathlib import Path
import pytest


def test_settings_defaults():
    from mediaforge.models import VideoOptions, ImageOptions
    assert VideoOptions().format == 'mp4'
    assert VideoOptions().quality == 23
    assert ImageOptions().quality == 85


def test_resize_preserves_aspect_and_prevents_upscale():
    from mediaforge.models import target_size
    assert target_size(1920, 1080, 1280, 720, True, True) == (1280, 720)
    assert target_size(640, 360, 1920, 1080, True, False) == (640, 360)
    assert target_size(1920, 1080, 1000, 0, True, True) == (1000, 562)


def test_destination_never_overwrites(tmp_path):
    from mediaforge.paths import reserve_output
    source = tmp_path / '中文 name.jpg'
    source.write_bytes(b'original')
    first = reserve_output(source, tmp_path, 'jpg')
    first.write_bytes(b'output')
    second = reserve_output(source, tmp_path, 'jpg')
    assert first != source and second != first and second != source
    assert source.read_bytes() == b'original'


def test_video_command_maps_only_main_streams():
    from mediaforge.models import MediaInfo, VideoOptions
    from mediaforge.video import build_command
    info = MediaInfo(Path('中文 file.mp4'), 'video', 100, 1920, 1080, 3, 'h264', 'aac')
    args = build_command(info, VideoOptions(), Path('output.mp4'))
    assert args[args.index('-i') + 1] == '中文 file.mp4'
    assert '0:V:0' in args and '0:a:0?' in args
    assert args[args.index('-crf') + 1] == '23'


def test_remux_rejects_filters_and_incompatible_codecs():
    from mediaforge.models import MediaInfo, VideoOptions
    from mediaforge.video import build_command
    info = MediaInfo(Path('a.mkv'), 'video', 100, 100, 100, 3, 'vp9', 'opus')
    with pytest.raises(ValueError):
        build_command(info, VideoOptions(remux=True, format='mp4'), Path('b.mp4'))
    with pytest.raises(ValueError):
        build_command(info, VideoOptions(remux=True, format='webm', width=50), Path('b.webm'))


def test_transparent_jpeg_and_no_upscale(tmp_path):
    from PIL import Image
    from mediaforge.images import process_image
    from mediaforge.probe import probe
    from mediaforge.models import ImageOptions
    import threading
    source = tmp_path / 'transparent.png'
    Image.new('RGBA', (80, 40), (255, 0, 0, 0)).save(source)
    output = tmp_path / 'result.jpg'
    process_image(probe(source), ImageOptions(width=500, height=500), output, threading.Event(), lambda p: None)
    with Image.open(output) as image:
        assert image.size == (80, 40)
        assert min(image.getpixel((0, 0))) > 250


def test_reject_multipage_and_animated(tmp_path):
    from PIL import Image
    from mediaforge.probe import probe
    first = Image.new('RGB', (10, 10), 'red')
    second = Image.new('RGB', (10, 10), 'blue')
    path = tmp_path / 'multi.tiff'
    first.save(path, save_all=True, append_images=[second])
    with pytest.raises(ValueError, match='多页|动画'):
        probe(path)


def test_orientation_normalized(tmp_path):
    from PIL import Image
    from mediaforge.images import process_image
    from mediaforge.probe import probe
    from mediaforge.models import ImageOptions
    import threading
    source = tmp_path / 'rotate.jpg'
    image = Image.new('RGB', (80, 40), 'red')
    exif = Image.Exif()
    exif[274] = 6
    image.save(source, exif=exif)
    output = tmp_path / 'normal.png'
    process_image(probe(source), ImageOptions(format='png', metadata=True), output, threading.Event(), lambda p: None)
    with Image.open(output) as result:
        assert result.size == (40, 80)
        assert result.getexif().get(274, 1) == 1
