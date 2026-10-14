"""Recover cached wheels for a clean, offline rebuild of the relocated venv."""
from pathlib import Path
from zipfile import ZipFile,is_zipfile
import shutil
from packaging.tags import sys_tags,parse_tag
from packaging.utils import canonicalize_name
root=Path(__file__).resolve().parents[1];destination=root/'downloads/wheels';destination.mkdir(parents=True,exist_ok=True)
supported=set(sys_tags());found={}
for body in (root/'downloads/pip-cache').rglob('*.body'):
    if not is_zipfile(body):continue
    with ZipFile(body) as archive:
        wheel=next((name for name in archive.namelist() if name.endswith('.dist-info/WHEEL')),None)
        if not wheel:continue
        tags=[line[5:] for line in archive.read(wheel).decode().splitlines() if line.startswith('Tag: ')]
        compatible=next((tag for tag in tags if parse_tag(tag)&supported),None)
        if not compatible:continue
        stem=wheel.partition('.dist-info/')[0];name,version=stem.rsplit('-',1)
        filename=stem+'-'+compatible+'.whl';target=destination/filename
        if not target.exists():shutil.copyfile(body,target)
        found[canonicalize_name(name)]=version
missing=[]
for requirement in (root/'requirements.lock.txt').read_text().splitlines():
    if '==' not in requirement:continue
    name,version=requirement.split('==')
    if found.get(canonicalize_name(name))!=version:missing.append(requirement)
assert not missing,missing
print(f'Offline wheels ready for {len(found)} packages')
