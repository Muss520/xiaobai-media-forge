"""Verify the frozen program contains the current mediaforge source bytecode."""
import json
from types import CodeType
from PyInstaller.archive.readers import CArchiveReader
from project_layout import DEV, DOCS, PORTABLE,EXE_NAME,VERSION

def normalized(code):
    return code.replace(co_filename='', co_consts=tuple(
        normalized(value) if isinstance(value, CodeType) else value
        for value in code.co_consts))

pkg = CArchiveReader(str(PORTABLE/EXE_NAME))
pyz = pkg.open_embedded_archive(next(name for name, entry in pkg.toc.items() if entry[-1]=='z'))
checked=[]
for path in sorted((DEV/'src/mediaforge').rglob('*.py')):
    parts=list(path.relative_to(DEV/'src').with_suffix('').parts)
    if parts[-1]=='__init__': parts.pop()
    name='.'.join(parts)
    assert normalized(pyz.extract(name)) == normalized(compile(path.read_bytes(), str(path), 'exec')), name
    checked.append(name)
result={'passed':True,'version':VERSION,'modules':checked,'current_source_matches_frozen_code':True}
(DOCS/(VERSION.rsplit('.',1)[0]+'_冻结代码校验.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(f'Frozen code matches current source: {len(checked)} modules')
