from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE
"""Read-only final checks of the portable payload and its ZIP/SHA256."""
import json,hashlib,zipfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]; folder=root/'成品/MediaForge'
def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
archive=root/'MediaForge-Windows-x64.zip'; expected=(root/'MediaForge-Windows-x64.sha256').read_text(encoding='utf-8-sig').split()[0]
assert digest(archive)==expected
exe=folder/'媒体工坊.exe'
for name in ('成品启动验证.json','移动目录验证.json'):
    report=DOCS/name
    result=json.loads(report.read_text(encoding='utf-8'))
    assert result['passed'] and result['exit_code']==0,result
    assert report.stat().st_mtime>=exe.stat().st_mtime,'stale report'
for name in ['3.4_原生界面验收_DPI100.json','3.4_原生界面验收_DPI150.json','3.4_原生界面验收_DPI200.json','3.4_用户MOV信息写入.json','3.4_小白原生输入.json']:
    assert json.loads((DOCS/name).read_text(encoding='utf-8'))['passed']
for name in ('xiaobai-logo.png','xiaobai-atlas.png','xiaobai-states.json','mediaforge.ico'):
    assert digest(root/'assets'/name)==digest(folder/'_internal/assets'/name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert hashlib.sha256(z.read('MediaForge/媒体工坊.exe')).hexdigest()==digest(exe)
    for path in (root/'src').rglob('*.py'):
        relative=path.relative_to(root/'src')
        assert digest(path)==digest(folder/'源码/src'/relative),relative
        assert z.read('MediaForge/源码/src/'+relative.as_posix())==path.read_bytes(),relative
    assert z.read('MediaForge/源码/docs/验收报告.md')==(root/'docs/验收报告.md').read_bytes()
result={'passed':True,'version':'3.4.0','zip_bytes':archive.stat().st_size,'zip_sha256':expected,'exe_sha256':digest(exe),'zip_crc':True,'source_matches_bundle':True,'fresh_native_and_relocation_reports':True}
(root/'docs/3.4_交付校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
