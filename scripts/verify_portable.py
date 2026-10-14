from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE,EXE_NAME
"""Run startup diagnostics using the native Windows Qt plugin."""
import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
sys.path.insert(0,str(DEV/'src'))
from mediaforge.paths import find_home,runtime_home,documents_home

root = Path(__file__).resolve().parents[1]
exe = PORTABLE / EXE_NAME
if '--folder' in sys.argv:
    exe = Path(sys.argv[sys.argv.index('--folder') + 1]).resolve() / EXE_NAME
env = dict(os.environ, TEMP=str(RUN / 'temp'), TMP=str(RUN / 'temp'))
env.pop('QT_QPA_PLATFORM', None)
env.pop('PYTHONPATH', None)
env.pop('PYTHONHOME', None)
system_root = env.get('SystemRoot', r'C:\Windows')
env['PATH'] = str(Path(system_root) / 'System32') + os.pathsep + system_root
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
command = [str(exe)] if '--source' not in sys.argv else [str(root / '.venv' / 'Scripts' / 'python.exe'), str(root / 'src' / 'main.py')]
home = PROJECT if '--source' in sys.argv else find_home(exe.parent)
report = documents_home(home) / '成品启动验证.json'
settings = runtime_home(home) / 'data' / 'settings.json'
original_settings = settings.read_bytes() if settings.exists() else None
report.unlink(missing_ok=True)
process = subprocess.Popen(command + ['--verify-startup', '--verify-media'], cwd=RUN / 'temp', env=env, startupinfo=startup)
try:
    process.wait(timeout=90)
    if process.returncode:
        raise RuntimeError(f'Nonzero application exit {process.returncode}')
    result = json.loads(report.read_text(encoding='utf-8'))
    result['exit_code'] = process.returncode
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    assert result['passed'], result
    if '--folder' not in sys.argv and report.parent!=DOCS:
        DOCS.mkdir(parents=True,exist_ok=True)
        for name in ('成品启动验证.json','成品界面.png','成品小猫设置.png','成品信息模式.png','成品作者与打赏.png','成品放大二维码.png','成品收款码_wechat.png','成品收款码_alipay.png','成品声音设置.png','成品逗猫棒.png','成品抛接球.png'):
            shutil.copyfile(report.parent/name,DOCS/name)
finally:
    if process.poll() is None:
        process.kill()
        process.wait()
    if original_settings is not None:
        settings.write_bytes(original_settings)
print(json.dumps(result, ensure_ascii=True))
