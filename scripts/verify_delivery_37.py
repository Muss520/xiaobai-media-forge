"""Current 3.7 release, original-file and real-rendered payment QR acceptance."""
import hashlib,json,zipfile
from pathlib import Path
from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE,VERSION,NAME,EXE_NAME,ARCHIVE_NAME,LAUNCHER_NAME

def digest(path):
    with Path(path).open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()

archive=RELEASE/ARCHIVE_NAME
expected=archive.with_suffix('.sha256').read_text(encoding='utf-8-sig').split()[0]
assert digest(archive)==expected
exe=PORTABLE/EXE_NAME
for name in ('成品启动验证.json','移动目录验证.json'):
    path=DOCS/name;report=json.loads(path.read_text(encoding='utf-8-sig'))
    assert report['passed'] and report['exit_code']==0 and report['version']==VERSION
    assert Path(report['executable']).name==EXE_NAME
    if name=='成品启动验证.json':assert Path(report['executable']).resolve()==exe.resolve()
    assert all(report[key] for key in ('product_brand','author_support_page','payment_code_assets','author_email_copy'))
    assert path.stat().st_mtime>=exe.stat().st_mtime
for dpi in (100,150,200):
    report=json.loads((DOCS/f'3.7_作者页原生验收_DPI{dpi}.json').read_text(encoding='utf-8'))
    assert report['passed'] and len(report['matrix'])==6
    report=json.loads((DOCS/f'3.6_原生界面验收_DPI{dpi}.json').read_text(encoding='utf-8'))
    assert report['passed'] and report['fonts']==[12,16,20]
for original in json.loads((DOCS/'3.7_原件保留清单.json').read_text(encoding='utf-8')):
    assert digest(original['path'])==original['sha256'],original['path']
from PIL import Image
import zxingcpp
codes=json.loads((DEV/'assets/support/manifest.json').read_text(encoding='utf-8'))['codes']
for code in codes:
    assert digest(DEV/'assets/support'/code['asset'])==digest(PORTABLE/'_internal/assets/support'/code['asset'])==code['asset_sha256']
    path=DOCS/('成品收款码_'+Path(code['asset']).stem+'.png')
    with Image.open(path) as image:
        payloads={hashlib.sha256(value.bytes).hexdigest() for value in zxingcpp.read_barcodes(image)}
    assert code['payload_sha256'] in payloads,('packaged window code unreadable',path)
with Image.open(DOCS/'成品放大二维码.png') as image:
    assert codes[0]['payload_sha256'] in {hashlib.sha256(value.bytes).hexdigest() for value in zxingcpp.read_barcodes(image)}
from PyInstaller.archive.readers import CArchiveReader
pkg=CArchiveReader(str(exe));pyz=pkg.open_embedded_archive(next(key for key,value in pkg.toc.items() if value[-1]=='z'))
assert not any(key.startswith('zxing') for key in pyz.toc),'Development-only QR decoder bundled unexpectedly'
import pefile
pe=pefile.PE(str(exe));properties={}
for infos in pe.FileInfo:
    for info in infos:
        for table in getattr(info,'StringTable',[]):properties.update(table.entries)
assert properties[b'ProductName'].decode('utf-8')==NAME
assert properties[b'FileDescription'].decode('utf-8')==NAME
assert properties[b'ProductVersion'].decode('utf-8')==VERSION
assert properties[b'OriginalFilename'].decode('utf-8')==EXE_NAME
assert properties[b'CompanyName'].decode('utf-8')=='沐'
pe.close()
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert hashlib.sha256(z.read('MediaForge/'+EXE_NAME)).hexdigest()==digest(exe)
    for area in ('src','scripts','tests'):
        for path in (DEV/area).rglob('*.py'):
            relative=path.relative_to(DEV)
            assert path.read_bytes()==(PORTABLE/'源码'/relative).read_bytes()==z.read('MediaForge/源码/'+relative.as_posix()),relative
    for name in ('build.ps1','requirements.lock.txt','requirements-dev.lock.txt'):
        assert z.read('MediaForge/源码/'+name)==(DEV/name).read_bytes()
    assert z.read('MediaForge/源码/docs/验收报告.md')==(DOCS/'验收报告.md').read_bytes()
    assert not any(path.startswith(('MediaForge/data/','MediaForge/logs/','MediaForge/temp/','MediaForge/output/')) for path in z.namelist())
    assert 'MediaForge/媒体工坊.exe' not in z.namelist()
    assert not any('zxing' in path.lower() and path.lower().endswith(('.pyd','.dll')) for path in z.namelist())
launcher=(PROJECT/LAUNCHER_NAME).read_bytes()
assert b'\r\n' in launcher and EXE_NAME.encode('utf-8') in launcher
assert not (PORTABLE/'媒体工坊.exe').exists()
result={'passed':True,'version':VERSION,'name':NAME,'zip_bytes':archive.stat().st_size,'zip_sha256':expected,
        'exe_sha256':digest(exe),'zip_crc':True,'source_matches_bundle':True,'fresh_native_and_relocation_reports':True,
        'original_settings_media_outputs_qr_preserved':True,'packaged_screen_codes_match_originals':True,
        'qr_decoder_not_bundled':True,'legacy_executable_absent':True,'phone_payment_scan':'not physically tested'}
result['windows_product_properties']=True
(DOCS/'3.7_交付校验.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
