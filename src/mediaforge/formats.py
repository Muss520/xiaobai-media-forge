"""One capability table shared by widgets, validation and output naming."""
VIDEO_FORMATS = {
    'mp4': ('h264', 'hevc', 'av1', 'mpeg4'),
    'mov': ('h264', 'hevc', 'mpeg4'),
    'mkv': ('h264', 'hevc', 'vp9', 'vp8', 'av1', 'mpeg4', 'mpeg2', 'wmv2'),
    'webm': ('vp9', 'vp8', 'av1'),
    'avi': ('mpeg4', 'h264'), 'ts': ('h264', 'hevc', 'mpeg2'),
    'mpeg': ('mpeg2', 'mpeg1'), 'wmv': ('wmv2',), 'flv': ('h264', 'flv1'),
}
AUDIO_FORMATS = {
    'mp4': ('aac', 'mp3', 'ac3'), 'mov': ('aac', 'mp3', 'pcm_s16le'),
    'mkv': ('aac', 'opus', 'mp3', 'pcm_s16le', 'mp2', 'ac3', 'wmav2'),
    'webm': ('opus', 'vorbis'), 'avi': ('mp3', 'pcm_s16le'),
    'ts': ('aac', 'mp2', 'ac3'), 'mpeg': ('mp2',), 'wmv': ('wmav2',), 'flv': ('aac', 'mp3'),
}
IMAGE_FORMATS = ('jpg', 'png', 'webp', 'bmp', 'tiff', 'ico', 'heic', 'avif', 'gif', 'apng')
ANIMATED_FORMATS = {'gif', 'webp', 'apng', 'png'}
VIDEO_EXTENSIONS = {'.' + x for x in ('mp4', 'mov', 'mkv', 'avi', 'webm', 'wmv', 'flv', 'm4v',
    'ts', 'mts', 'm2ts', 'mpeg', 'mpg', '3gp', 'ogv')}
IMAGE_EXTENSIONS = {'.' + x for x in ('jpg', 'jpeg', 'png', 'webp', 'bmp', 'tif', 'tiff',
    'ico', 'heic', 'heif', 'avif', 'gif', 'apng')}
CODEC_LABELS = {'h264': 'H.264 · 通用', 'hevc': 'H.265 / HEVC', 'av1': 'AV1 · 高压缩',
    'vp9': 'VP9', 'vp8': 'VP8', 'mpeg4': 'MPEG-4', 'mpeg2': 'MPEG-2',
    'mpeg1': 'MPEG-1', 'wmv2': 'WMV2', 'flv1': 'FLV1'}


def register_images():
    import pillow_heif
    pillow_heif.register_heif_opener()
