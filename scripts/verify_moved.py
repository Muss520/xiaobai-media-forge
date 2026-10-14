from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE
"""Verify the complete portable folder without locating the project marker."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[1]
with TemporaryDirectory(prefix='portable-move-', dir=RUN / 'temp') as scratch:
    moved = Path(scratch) / 'MediaForge'
    assert moved.resolve().is_relative_to((RUN / 'temp').resolve())
    shutil.copytree(PORTABLE, moved)
    subprocess.run([sys.executable, str(root / 'scripts' / 'verify_portable.py'), '--folder', str(moved)], check=True)
    result = json.loads((moved / 'docs' / '成品启动验证.json').read_text(encoding='utf-8'))
    settings = json.loads((moved / 'data' / 'diagnostic-settings.json').read_text(encoding='utf-8'))
    assert Path(settings['output']).resolve() == (moved / 'output').resolve()
    assert (moved / 'logs' / 'mediaforge.log').exists()
    assert (moved / 'temp').is_dir()
    assert Path(result['runtime_home']).resolve()==moved.resolve()
    result['local_config_logs_temp'] = True
    (DOCS / '移动目录验证.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print('Relocation and local configuration verification passed')
