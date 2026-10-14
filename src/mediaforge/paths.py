from pathlib import Path
import os
import sys
import uuid


def find_home(home) -> Path:
    home=Path(home).resolve()
    for parent in (home,*list(home.parents)[:3]):
        if (parent/'project.marker').is_file():return parent
    return home


def app_home() -> Path:
    return find_home(Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2])


def resource_home() -> Path:
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[2]


def runtime_home(root=None) -> Path:
    root=Path(root) if root is not None else app_home()
    return root/'运行数据' if (root/'开发资料').is_dir() and (root/'project.marker').is_file() else root


def documents_home(root=None) -> Path:
    root=Path(root) if root is not None else app_home()
    return root/'文档' if runtime_home(root)!=root else root/'docs'


def setup_paths() -> Path:
    root = app_home()
    runtime=runtime_home(root)
    for name in ('data', 'logs', 'temp'):
        (runtime / name).mkdir(parents=True, exist_ok=True)
    (root/'output').mkdir(exist_ok=True)
    os.environ['TEMP'] = str(runtime / 'temp')
    os.environ['TMP'] = str(runtime / 'temp')
    import tempfile
    tempfile.tempdir = str(runtime / 'temp')
    return root


def tool_path(name: str) -> str:
    base = resource_home()
    path = base / 'tools' / f'{name}.exe'
    if not path.is_file():
        raise FileNotFoundError(f'缺少内置工具：{path.name}，请保持软件文件夹完整')
    return str(path)


def check_output_directory(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    check = folder / f'.write-check-{uuid.uuid4().hex}'
    try:
        with check.open('xb') as file:
            file.write(b'')
    except OSError as error:
        raise ValueError(f'输出目录不可写：{folder}') from error
    finally:
        check.unlink(missing_ok=True)


def reserve_output(source: Path, folder: Path, extension: str) -> Path:
    """Atomically reserve a new name; only this process owns its empty file."""
    from .formats import VIDEO_FORMATS, IMAGE_FORMATS
    if extension not in {*VIDEO_FORMATS, *IMAGE_FORMATS, 'livp'}:
        raise ValueError('不支持的输出格式')
    folder.mkdir(parents=True, exist_ok=True)
    counter = 0
    while True:
        suffix = '' if not counter else f'_{counter}'
        result = folder / f'{source.stem}_converted{suffix}.{extension}'
        try:
            with result.open('xb'):
                pass
            return result
        except FileExistsError:
            counter += 1


def temporary_output(destination: Path) -> Path:
    return destination.with_name(f'.{destination.stem}.{uuid.uuid4().hex}.partial{destination.suffix}')
