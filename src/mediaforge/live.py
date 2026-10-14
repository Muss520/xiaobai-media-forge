"""Live Photo pairing and transactional exports. Paired MOV is never modified."""
from contextlib import contextmanager
from dataclasses import replace
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from tempfile import TemporaryDirectory
import uuid
import zipfile
from .models import MediaInfo, LiveOptions, ImageOptions
from .paths import app_home,runtime_home, tool_path, temporary_output
from .probe import probe, run_tool
from .images import process_image, check_cancel
from .video import process_video

MAX_PACKAGE_BYTES = 2 * 1024**3


def run_exif(args, cancel=None):
    # The Windows launcher converts argv to the active ANSI codepage. UTF-8
    # arguments via stdin preserve Chinese, emoji and all other Unicode paths.
    if any('\n' in str(a) or '\r' in str(a) for a in args[1:]):
        raise ValueError('元数据参数包含无效换行')
    result = run_tool([args[0], '-@', '-'], timeout=60, cancel=cancel,
                      input_text='\n'.join(str(a) for a in args[1:]) + '\n')
    if result.returncode:
        raise ValueError('Live 元数据处理失败：' + result.stderr[-1000:])
    return result


def exif_data(paths, cancel=None):
    args = [tool_path('exiftool'), '-j', '-n', '-ee', '-charset', 'filename=UTF8',
            '-ContentIdentifier', '-LivePhotoVideoIndex', '-StillImageTime', '-Make', '-Model']
    result = run_exif(args + [str(p) for p in paths], cancel)
    if result.returncode:
        raise ValueError('无法读取 Live 配对元数据：' + result.stderr[-800:])
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError('Live 元数据读取未返回有效结果：' + result.stderr[-800:]) from error
    if len(records) != len(paths) or any('Error' in r for r in records):
        raise ValueError('部分 Live 文件无法读取元数据')
    return records


def verify_pair(image, movie, cancel=None):
    records = exif_data([image, movie], cancel)
    ids = [r.get('ContentIdentifier') for r in records]
    if len(ids) != 2 or not all(ids) or ids[0] != ids[1]:
        raise ValueError('照片与 MOV 缺少有效配对标识或标识不一致，不能保留 Live；可选择普通格式导出')
    # Missing timed metadata is not fabricated from filenames or an arbitrary frame.
    if 'StillImageTime' not in records[1]:
        raise ValueError('MOV 缺少 Live 关键帧标记，不能确认为完整 Live Photo')
    return ids[0]


@contextmanager
def components(path, inputs=(), cancel=None):
    if cancel is not None:
        check_cancel(cancel)
    path = Path(path)
    if path.suffix.lower() != '.livp':
        files = [Path(p) for p in (inputs or (path,))]
        images = [p for p in files if p.suffix.lower() in {'.heic', '.heif', '.jpg', '.jpeg'}]
        movies = [p for p in files if p.suffix.lower() == '.mov']
        if len(images) != 1 or len(movies) != 1:
            raise ValueError('Live 配对需要一张 HEIC/JPEG 照片和一个 MOV 视频')
        yield images[0], movies[0]
        return
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ValueError('LIVP 不是可读取的 ZIP 配对包') from error
    with archive:
        members = archive.infolist()
        if len(members) > 64 or sum(m.file_size for m in members) > MAX_PACKAGE_BYTES:
            raise ValueError('LIVP 解包超过安全限制（64 项 / 2 GB）')
        for m in members:
            parts = PurePosixPath(m.filename.replace('\\', '/'))
            if (parts.is_absolute() or '..' in parts.parts or ':' in m.filename or '\x00' in m.filename
                    or (m.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('LIVP 包含不安全路径或链接')
            if m.flag_bits & 1:
                raise ValueError('不支持加密的 LIVP')
            if m.file_size > max(1, m.compress_size) * 1000:
                raise ValueError('LIVP 压缩比例超过安全限制')
        images = [m for m in members if Path(m.filename).suffix.lower() in {'.heic', '.heif', '.jpg', '.jpeg'}]
        movies = [m for m in members if Path(m.filename).suffix.lower() == '.mov']
        if len(images) != 1 or len(movies) != 1:
            raise ValueError('LIVP 必须包含一张照片与一个 MOV 配对视频；缺失或多个配对请拆分后导入')
        root = runtime_home() / 'temp'
        root.mkdir(exist_ok=True)
        with TemporaryDirectory(prefix='live-import-', dir=root) as folder:
            paths = []
            # Fixed safe names; never extract a user-controlled archive path.
            for member, name in ((images[0], 'photo'), (movies[0], 'video')):
                out = Path(folder) / (name + Path(member.filename).suffix.lower())
                with archive.open(member) as source, out.open('xb') as target:
                    while chunk := source.read(1024 * 1024):
                        if cancel is not None:
                            check_cancel(cancel)
                        target.write(chunk)
                paths.append(out)
            yield tuple(paths)


def inspect_live(path, inputs=(), cancel=None):
    with components(path, inputs, cancel) as (image, movie):
        picture, video = probe(image), probe(movie)
        # Ordinary exports remain possible for packages that lack Apple's metadata.
        size = Path(path).stat().st_size if Path(path).suffix.lower() == '.livp' else picture.size + video.size
        return replace(picture, path=Path(path), kind='live', size=size, duration=video.duration,
                       video_codec=video.video_codec, audio_codec=video.audio_codec, fps=video.fps,
                       video_bitrate=video.video_bitrate,audio_bitrate=video.audio_bitrate,
                       metadata={'photo_size':picture.size,'video_size':video.size,'video_width':video.width,'video_height':video.height,'video_sar':video.sample_aspect_ratio})


def copy_cancelled(source, destination, cancel, progress=None):
    size=source.stat().st_size
    copied=0
    with Path(source).open('rb') as src, Path(destination).open('wb') as dst:
        while chunk := src.read(1024 * 1024):
            check_cancel(cancel)
            dst.write(chunk)
            copied+=len(chunk)
            if progress:
                progress(int(copied/max(1,size)*100))


def process_live(job, options: LiveOptions, destination, cancel, progress):
    from .animation import video_to_animation
    root = runtime_home() / 'temp'
    with components(job.path, job.inputs, cancel) as (image, movie), TemporaryDirectory(prefix='live-export-', dir=root) as folder:
        from .resolution import resolve_live
        options=resolve_live(options,probe(image),probe(movie))
        check_cancel(cancel)
        if options.mode == 'both':
            stage = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.partial')
            try:
                stage.mkdir()
                picture, video = probe(image), probe(movie)
                allowance = options.target_bytes - video.size if options.target_bytes and options.video_copy else 0
                if options.target_bytes and options.video_copy and allowance <= 0:
                    raise ValueError('整组体积上限无法容纳原始 MOV，请提高或取消上限')
                params = replace(options.image,format=options.format,target_bytes=allowance,animation='first')
                photo_out, movie_out = stage / ('photo.' + options.format), stage / ('photo.mov' if options.video_copy else 'photo.' + options.video.format)
                process_image(picture,params,photo_out,cancel,lambda p:progress(int(p*.6)))
                if options.video_copy:
                    copy_cancelled(movie,movie_out,cancel,lambda p:progress(60+int(p*.3)))
                else:
                    remaining = options.target_bytes - photo_out.stat().st_size if options.target_bytes else 0
                    if options.target_bytes and remaining <= 0:
                        raise ValueError('照片已占满整组体积上限，请提高上限或调整照片参数')
                    video_params = replace(options.video, target_bytes=remaining, mode='size' if remaining else options.video.mode)
                    process_video(video, video_params, movie_out, cancel, lambda p:progress(60+int(p*.3)))
                import hashlib
                def digest(path):
                    value=hashlib.sha256()
                    with path.open('rb') as stream:
                        while chunk:=stream.read(1024*1024):
                            check_cancel(cancel)
                            value.update(chunk)
                    return value.digest()
                if options.video_copy and digest(movie)!=digest(movie_out):
                    raise ValueError('原始 MOV 复制验证失败')
                probe(movie_out)
                probe(photo_out)
                if options.target_bytes and photo_out.stat().st_size+movie_out.stat().st_size>options.target_bytes:
                    raise ValueError('照片与原始 MOV 合计超过体积上限')
                check_cancel(cancel)
                destination.rmdir()
                stage.replace(destination)
                progress(100)
                return (destination/photo_out.name,destination/movie_out.name)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
        if options.mode == 'image':
            process_image(probe(image), options.image, destination, cancel, progress)
            return (destination,)
        if options.mode == 'video':
            process_video(probe(movie), options.video, destination, cancel, progress)
            return (destination,)
        if options.mode == 'animation':
            video_to_animation(probe(movie), options.image, destination, cancel, progress, options.animation_fps)
            return (destination,)
        if options.mode != 'preserve' or options.image.format not in {'jpg', 'heic'}:
            raise ValueError('保留 Live 的照片格式请选择 JPEG 或 HEIC')
        identifier = verify_pair(image, movie, cancel)
        folder = Path(folder)
        output_image = folder / ('photo.' + options.image.format)
        output_video = folder / 'photo.mov'
        # Keep only necessary MakerNotes if user disabled other metadata.
        params = replace(options.image, target_bytes=0, animation='first')
        process_image(probe(image), params, output_image, cancel, lambda p: progress(int(p * .35)))
        copy_args = [tool_path('exiftool'), '-overwrite_original', '-charset', 'filename=UTF8',
                     '-TagsFromFile', str(image), '-MakerNotes', '-Make', '-Model', str(output_image)]
        result = run_exif(copy_args, cancel)
        if result.returncode:
            raise ValueError('Live 配对元数据写入失败：' + result.stderr[-800:])
        check_cancel(cancel)
        copy_cancelled(movie, output_video, cancel)
        verify_pair(output_image, output_video, cancel)
        if exif_data([output_image], cancel)[0].get('ContentIdentifier') != identifier:
            raise ValueError('输出 Live 配对标识验证失败')
        progress(70)
        combined = output_image.stat().st_size + output_video.stat().st_size
        if options.target_bytes and combined > options.target_bytes:
            # Reserve a conservative metadata/package budget, then recompress only the still.
            allowance = options.target_bytes - output_video.stat().st_size - 8192
            if allowance <= 0:
                raise ValueError('目标体积无法容纳原样保留的 MOV 视频，请提高上限或导出普通视频')
            process_image(probe(image), replace(params, target_bytes=allowance), output_image, cancel, lambda p: progress(70 + int(p * .1)))
            result = run_exif(copy_args, cancel)
            if result.returncode:
                raise ValueError('Live 配对元数据写入失败')
            verify_pair(output_image, output_video, cancel)
        if options.format == 'folder':
            if options.target_bytes and sum(p.stat().st_size for p in (output_image, output_video)) > options.target_bytes:
                raise ValueError('保留配对元数据后超过目标体积，请提高上限')
            # Create staging beside destination to keep rename on the same volume.
            stage = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.partial')
            try:
                stage.mkdir()
                for source in (output_image, output_video):
                    copy_cancelled(source, stage / source.name, cancel)
                check_cancel(cancel)
                destination.rmdir()  # This empty directory was exclusively reserved by our worker.
                stage.replace(destination)
            finally:
                if stage.exists():
                    shutil.rmtree(stage)
            progress(100)
            return tuple(destination / p.name for p in (output_image, output_video))
        temp = temporary_output(destination)
        try:
            with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_STORED) as archive:
                for source in (output_image, output_video):
                    check_cancel(cancel)
                    with source.open('rb') as src, archive.open(source.name, 'w') as dst:
                        while chunk := src.read(1024 * 1024):
                            check_cancel(cancel)
                            dst.write(chunk)
            if options.target_bytes and temp.stat().st_size > options.target_bytes:
                raise ValueError('LIVP 封装后超过目标体积，请提高上限')
            check_cancel(cancel)
            temp.replace(destination)
        finally:
            temp.unlink(missing_ok=True)
        progress(100)
        return (destination,)


def match_pairs(paths, cancel=None):
    photos = [Path(p) for p in paths if Path(p).suffix.lower() in {'.heic', '.heif', '.jpg', '.jpeg'}]
    movies = [Path(p) for p in paths if Path(p).suffix.lower() == '.mov']
    if not photos or not movies:
        return [], list(paths)
    records = exif_data(photos + movies, cancel)
    by_path = {Path(r['SourceFile']).resolve(): r.get('ContentIdentifier') for r in records}
    pairs, used = [], set()
    for photo in photos:
        identifier = by_path.get(photo.resolve())
        candidates = [m for m in movies if identifier and by_path.get(m.resolve()) == identifier and m not in used]
        if len(candidates) == 1:
            pairs.append((photo, candidates[0]))
            used.update((photo, candidates[0]))
    return pairs, [p for p in paths if Path(p) not in used]
