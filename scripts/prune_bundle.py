"""Exclude unused PDF plugins and ICU that shadows Windows' built-in ICU API.

QtCore uses unversioned Windows ICU exports. ICU found through the build host's
Node PATH exposes _78 suffixed symbols instead, causing QtWidgets import failure.
The app has no PDF feature; its Qt PDF image plugin and private dependencies
must not drag incompatible ICU into the executable's DLL search directory.
"""
from pathlib import Path
import sys

folder = Path(sys.argv[1]).resolve()
names = {'icuuc.dll', 'icuin.dll', 'icudt78.dll', 'qt6pdf.dll', 'qpdf.dll'}
for path in folder.rglob('*'):
    if path.is_file() and path.name.lower() in names:
        if not path.resolve().is_relative_to(folder):
            raise ValueError('Bundle cleanup path escaped the build folder')
        path.unlink()
        print('Excluded unused dependency:', path.name)
