import io
import subprocess
from PIL import Image, ImageOps
from PySide6.QtGui import QImage
from .formats import IMAGE_EXTENSIONS
from .paths import tool_path
from .probe import NO_WINDOW


def thumbnail(job):
    if job.path.suffix.lower() == '.livp' or job.inputs:
        from .live import components
        with components(job.path, job.inputs) as (image, movie):
            return image_thumbnail(image)
    if job.path.suffix.lower() in IMAGE_EXTENSIONS:
        return image_thumbnail(job.path)
    result = subprocess.run([tool_path('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(job.path),
                             '-map', '0:V:0', '-frames:v', '1', '-vf', 'scale=160:100:force_original_aspect_ratio=decrease',
                             '-f', 'image2pipe', '-c:v', 'png', '-'], capture_output=True, timeout=15, creationflags=NO_WINDOW)
    return QImage.fromData(result.stdout)


def image_thumbnail(path):
    with Image.open(path) as image:
        picture = ImageOps.exif_transpose(image).convert('RGBA')
        picture.thumbnail((160, 100))
        return QImage(picture.tobytes(), picture.width, picture.height, QImage.Format_RGBA8888).copy()
