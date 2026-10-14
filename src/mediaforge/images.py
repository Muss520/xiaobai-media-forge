import threading
from pathlib import Path
from PIL import Image, ImageOps, ImageColor
from .models import ImageOptions, MediaInfo, target_size
from .paths import temporary_output
from .formats import IMAGE_FORMATS, ANIMATED_FORMATS, register_images
register_images()


class Cancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set():
        raise Cancelled('已取消')


def process_image(info: MediaInfo, options: ImageOptions, destination: Path,
                  cancel: threading.Event, progress) -> Path:
    from .resolution import resolve_options
    options=resolve_options(info,options)
    if info.path.resolve() == destination.resolve():
        raise ValueError('输出文件不能覆盖原文件')
    if options.format not in IMAGE_FORMATS:
        raise ValueError('不支持的图片输出格式')
    if not 1 <= options.quality <= 100 or not 0 <= options.png_level <= 9 or options.target_bytes < 0:
        raise ValueError('图片质量、压缩级别或目标体积无效')
    temp = temporary_output(destination)
    frames, durations = [], []
    try:
        check_cancel(cancel)
        with Image.open(info.path) as original:
            count = getattr(original, 'n_frames', 1)
            if count > 1 and original.format not in {'GIF', 'WEBP', 'PNG'}:
                raise ValueError('不支持多页图片')
            animated = count > 1 and options.animation == 'preserve'
            if animated and options.format not in ANIMATED_FORMATS:
                raise ValueError('动图转静态格式请明确选择首帧或指定帧')
            if options.animation not in {'preserve', 'first', 'frame'}:
                raise ValueError('动画处理方式无效')
            poster = bool(original.info.get('default_image')) and original.format == 'PNG'
            indexes = range(1 if poster else 0, count) if animated else [options.frame_index if options.animation == 'frame' else 0]
            if not animated and not 0 <= indexes[0] < count:
                raise ValueError(f'指定帧超出范围：本文件共 {count} 帧（从 0 开始）')
            # Bound decoded pixel storage rather than allowing an animation to exhaust memory.
            decoded_size = target_size(original.width,original.height,options.width,options.height,False if options.resolved_size else options.aspect,options.upscale)
            if decoded_size[0] * decoded_size[1] * len(indexes) > 150_000_000:
                raise ValueError('动画解码超过 1.5 亿像素，请先缩短或拆分素材')
            # GIF stores extra repeats; APNG/WebP store total plays. Zero means infinite.
            if original.format == 'GIF':
                raw_loop = original.info.get('loop')
                plays = 1 if raw_loop is None else 0 if raw_loop == 0 else raw_loop + 1
            else:
                plays = original.info.get('loop', 1)
            exif = None
            icc = original.info.get('icc_profile')
            for index in indexes:
                check_cancel(cancel)
                original.seek(index)
                frame = ImageOps.exif_transpose(original)
                frame.load()
                if exif is None:
                    exif = frame.getexif()
                size = target_size(*frame.size, options.width, options.height, False if options.resolved_size else options.aspect, options.upscale)
                if options.format == 'ico':
                    size = target_size(*size, 256, 256, True, False)
                if frame.size != size:
                    frame = frame.resize(size, Image.Resampling.LANCZOS)
                if options.format in {'jpg', 'bmp'}:
                    rgba = frame.convert('RGBA')
                    frame = Image.new('RGB', size, ImageColor.getrgb(options.background))
                    frame.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    frame = frame.convert('RGBA' if 'A' in frame.getbands() or animated else 'RGB')
                frame.info.clear()
                frames.append(frame.copy())
                durations.append(original.info.get('duration', 100))
            progress(15)
        def encode(quality):
            check_cancel(cancel)
            kwargs = {}
            fmt = options.format
            if options.metadata and fmt in {'jpg', 'png', 'webp', 'tiff', 'heic', 'avif'}:
                exif.pop(274, None)
                for tag, value in ((40962, frames[0].width), (40963, frames[0].height)):
                    if tag in exif:
                        exif[tag] = value
                if exif:
                    kwargs['exif'] = exif.tobytes()
                if icc:
                    kwargs['icc_profile'] = icc
            if fmt == 'jpg':
                kwargs.update(quality=quality, optimize=True, progressive=True)
            elif fmt in {'png', 'apng'}:
                kwargs['compress_level'] = options.png_level
            elif fmt in {'webp', 'heic', 'avif'}:
                kwargs['quality'] = quality
                if fmt == 'webp':
                    kwargs.update(lossless=options.lossless, method=6)
            elif fmt == 'tiff':
                kwargs['compression'] = 'tiff_deflate'
            elif fmt == 'ico':
                kwargs['sizes'] = [frames[0].size]
            if animated:
                kwargs.update(save_all=True, append_images=frames[1:], duration=durations)
                if fmt == 'gif':
                    # Carry GIF's 10 ms rounding across frames instead of
                    # shortening every 15 fps frame from 67 ms to 60 ms.
                    elapsed=written=0
                    gif_durations=[]
                    for duration in durations:
                        elapsed+=max(1,int(duration))
                        end=max(written+10,round(elapsed/10)*10)
                        gif_durations.append(end-written)
                        written=end
                    kwargs['duration']=gif_durations
                    kwargs.update(disposal=2, optimize=False)
                    if plays != 1:
                        kwargs['loop'] = 0 if plays == 0 else plays - 1
                else:
                    kwargs['loop'] = plays
            frames[0].save(temp, format={'jpg': 'JPEG', 'heic': 'HEIF', 'apng': 'PNG'}.get(fmt, fmt.upper()), **kwargs)
            check_cancel(cancel)
            return temp.stat().st_size
        lossy = options.format in {'jpg', 'heic', 'avif'} or (options.format == 'webp' and not options.lossless)
        attempts = 0
        while True:
            attempts += 1
            size_bytes = encode(options.quality)
            if not options.target_bytes or size_bytes <= options.target_bytes:
                break
            if lossy:
                lo, hi, best = 1, options.quality - 1, None
                while lo <= hi:
                    q = (lo + hi) // 2
                    size_bytes = encode(q)
                    progress(min(85, 20 + q // 2))
                    if size_bytes <= options.target_bytes:
                        best, lo = q, q + 1
                    else:
                        hi = q - 1
                if best is not None:
                    encode(best)
                    break
            if not options.auto_resize or attempts >= 16 or min(frames[0].size) <= 8:
                raise ValueError('无法达到目标体积；请提高体积上限、选择有损格式或允许自动缩小尺寸')
            frames = [f.resize((max(1, int(f.width * .8)), max(1, int(f.height * .8))),
                               Image.Resampling.LANCZOS) for f in frames]
            progress(min(85, 20 + attempts * 4))
        progress(90)
        with Image.open(temp) as result:
            if result.size != frames[0].size:
                raise ValueError('图片输出尺寸验证失败')
            if animated:
                groups=[]
                for frame,duration in zip(frames,durations):
                    duration=max(1,int(duration))
                    fingerprint=frame.tobytes()
                    if groups and groups[-1][0]==fingerprint:
                        groups[-1][2]+=duration
                    else:
                        groups.append([fingerprint,frame,duration])
                count=getattr(result,'n_frames',1)
                references=list(zip(frames,durations)) if count==len(frames) else [(g[1],g[2]) for g in groups]
                if count!=len(references):
                    raise ValueError('动图播放内容验证失败：输出丢失了不同的画面')
                actual_plays=result.info.get('loop',1)
                if result.format=='GIF':
                    raw=result.info.get('loop')
                    actual_plays=1 if raw is None else 0 if raw==0 else raw+1
                if actual_plays!=plays:
                    raise ValueError('动图循环信息验证失败')
                from PIL import ImageChops,ImageStat
                actual_duration=0
                for i,(expected,expected_duration) in enumerate(references):
                    check_cancel(cancel)
                    result.seek(i)
                    result.load()
                    actual_duration+=result.info.get('duration',100)
                    tolerance=10 if result.format=='GIF' else 2
                    if abs(result.info.get('duration',100)-expected_duration)>tolerance:
                        raise ValueError('动图帧时序验证失败')
                    left,right=expected.convert('RGBA'),result.convert('RGBA')
                    difference=ImageChops.difference(left,right)
                    if options.format in {'png','apng'} or options.format=='webp' and options.lossless:
                        # RGB values in fully transparent pixels do not affect playback.
                        background=Image.new('RGBA',left.size,'white')
                        if ImageChops.difference(Image.alpha_composite(background,left).convert('RGB'),Image.alpha_composite(background,right).convert('RGB')).getbbox():
                            raise ValueError('动图画面验证失败')
                    elif max(ImageStat.Stat(difference).mean)>80:
                        raise ValueError('动图画面差异超出编码容差')
                if abs(actual_duration-sum(max(1,int(d)) for d in durations))>(10 if result.format=='GIF' else 2):
                    raise ValueError('动图总时长验证失败，请使用时序精度更高的 WebP/APNG')
            for i in range(getattr(result, 'n_frames', 1)):
                check_cancel(cancel)
                result.seek(i)
                result.load()
        if options.target_bytes and temp.stat().st_size > options.target_bytes:
            raise ValueError('图片输出超过目标体积')
        check_cancel(cancel)
        temp.replace(destination)
        progress(100)
        return destination
    finally:
        temp.unlink(missing_ok=True)
        for frame in frames:
            frame.close()
