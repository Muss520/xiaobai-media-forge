"""Final release consistency and preserved-data checks for classified 3.6."""
from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE
from pathlib import Path
import json,hashlib,zipfile
def digest(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
archive=RELEASE/'MediaForge-Windows-x64.zip';expected=(RELEASE/'MediaForge-Windows-x64.sha256').read_text(encoding='utf-8-sig').split()[0]
assert digest(archive)==expected
exe=PORTABLE/'媒体工坊.exe'
for name in ('成品启动验证.json','移动目录验证.json'):
    path=DOCS/name;result=json.loads(path.read_text(encoding='utf-8-sig'))
    assert result['passed'] and result['exit_code']==0 and result['version']=='3.6.0',result
    assert path.stat().st_mtime>=exe.stat().st_mtime
for dpi in (100,150,200):
    result=json.loads((DOCS/f'3.6_原生界面验收_DPI{dpi}.json').read_text(encoding='utf-8'))
    assert result['passed'] and result['fonts']==[12,16,20]
manifest=json.loads((DOCS/'3.6_迁移清单.json').read_text(encoding='utf-8-sig'))
settings=next(record for record in manifest['files'] if record['source']=='data\\settings.json')
assert digest(PROJECT/settings['target']).upper()==settings['sha256']
for output in manifest['outputs']:assert digest(output['path']).upper()==output['sha256']
for name in ('xiaobai-logo.png','xiaobai-frames.png','xiaobai-states.json','mediaforge.ico'):
    assert digest(DEV/'assets'/name)==digest(PORTABLE/'_internal/assets'/name)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert hashlib.sha256(z.read('MediaForge/媒体工坊.exe')).hexdigest()==digest(exe)
    for area in ('src','scripts','tests'):
        for path in (DEV/area).rglob('*.py'):
            relative=path.relative_to(DEV)
            assert digest(path)==digest(PORTABLE/'源码'/relative),relative
            assert z.read('MediaForge/源码/'+relative.as_posix())==path.read_bytes(),relative
    assert z.read('MediaForge/源码/docs/验收报告.md')==(DOCS/'验收报告.md').read_bytes()
    assert z.read('MediaForge/源码/build.ps1')==(DEV/'build.ps1').read_bytes()
    assert not any(name.startswith(('MediaForge/data/','MediaForge/logs/','MediaForge/temp/','MediaForge/output/')) for name in z.namelist())
result={'passed':True,'version':'3.6.0','zip_bytes':archive.stat().st_size,'zip_sha256':expected,'exe_sha256':digest(exe),'zip_crc':True,'source_matches_bundle':True,'fresh_native_and_relocation_reports':True,'original_settings_preserved':True,'original_outputs_preserved':True}
(DOCS/'3.6_交付校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
