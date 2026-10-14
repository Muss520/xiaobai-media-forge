"""Portable archive with stable folder prefix; excludes developer bytecode."""
import sys
import zipfile
from pathlib import Path

folder, destination = map(Path, sys.argv[1:3])
with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in sorted(folder.rglob('*')):
        relative=path.relative_to(folder)
        if path.is_file() and '__pycache__' not in path.parts and '.pytest_cache' not in path.parts and relative.parts[0] not in {'data','logs','temp','output'}:
            archive.write(path, path.relative_to(folder.parent))
print(f'ZIP: {destination.name} ({destination.stat().st_size / 1024 / 1024:.1f} MB)')
