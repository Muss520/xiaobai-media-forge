"""Refresh final acceptance documentation/source, ZIP and checksum after a build."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
from project_layout import DEV,DOCS,PORTABLE,RELEASE,VERSION,ARCHIVE_NAME,EXE_NAME

assert VERSION=='3.8.0'
for name in ('成品启动验证.json','移动目录验证.json'):
    report=json.loads((DOCS/name).read_text(encoding='utf-8'))
    assert report['version']==VERSION and report['passed'] and report['exit_code']==0
    assert report['gameplay_and_cleanup'] and report['portable_media']['passed'] and report['desktop_workflow']['passed']
    assert (DOCS/name).stat().st_mtime>=(PORTABLE/EXE_NAME).stat().st_mtime

path=DOCS/'验收报告.md'
text=path.read_text(encoding='utf-8').replace('- 成品与移动目录最终验收执行中，结果另附。',
    '- 实际启动3.8 EXE和移动后的完整文件夹均通过，退出码0；移动后配置/日志/临时/默认输出均在自身目录。内置HEIF/AVIF、图片/视频目标体积、Live配对/原MOV字节一致/双文件转码、元数据原画质修改/清除，以及混合投喂/追加批次/重名归组/单实例/处理中关窗恢复均通过。\n'
    '- 两处EXE均通过小白新动作能力、五档缩放/透明边界、置顶、五页设置、两种游戏计分/暂停及任务介入清理检查；截图见成品声音设置.png、成品逗猫棒.png、成品抛接球.png。\n'
    '- 39个mediaforge模块冻结代码与最终源码一致，见3.8_冻结代码校验.json。ZIP/SHA256、随附源码/资源、实际成品二维码及原件哈希由3.8_交付校验.json记录。')
text=text.replace('最终构建重新执行。','最终构建已重新执行并通过。')
path.write_text(text,encoding='utf-8')
ledger=DOCS/'upgrade-3.8-progress.md'
with ledger.open('a',encoding='utf-8') as file:
    file.write('\nTask 5 complete: 193完整回归通过；100/150/200% DPI、12/16/20pt原生矩阵通过；实际EXE与移动目录媒体/后台/游戏验收通过。39模块冻结源码一致；最终同步文档/资源并重建ZIP/SHA256，交付清单单独记录。\n'
               'Ruling: 本项目无Git且已授权原地替换，不应用分支合并/PR菜单；保留实施记录与所有用户文件。剪贴板仅原生测试环境被Windows拒绝访问，保留明确未验证记录，不作为复制通过。\n')
source=PORTABLE/'源码'
for area in ('src','tests','scripts'):
    shutil.copytree(DEV/area,source/area,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','.pytest_cache'))
for item in DOCS.iterdir():
    if item.name=='3.8_交付校验.json':continue
    destination=source/'docs'/item.name
    if item.is_dir():shutil.copytree(item,destination,dirs_exist_ok=True)
    else:shutil.copy2(item,destination)
# Remove only this run's superseded scale-calibration screenshots/reports.
import re
for item in (source/'docs').iterdir():
    if item.is_file() and re.match(r'^3\.8_.*DPI(225|300)(_|\.)',item.name):item.unlink()
(source/'docs/3.8_交付校验.json').unlink(missing_ok=True)
for name in ('build.ps1','requirements.lock.txt','requirements-dev.lock.txt'):
    shutil.copy2(DEV/name,source/name)
for name in ('使用说明.txt','LICENSE.txt'):
    shutil.copy2(DOCS/name,PORTABLE/name);shutil.copy2(DOCS/name,source/name)
shutil.copytree(DOCS/'licenses',PORTABLE/'licenses',dirs_exist_ok=True)
shutil.copytree(DOCS/'licenses',source/'licenses',dirs_exist_ok=True)
subprocess.run([sys.executable,str(DEV/'scripts/verify_compiled_36.py')],check=True)
shutil.copy2(DOCS/'3.8_冻结代码校验.json',source/'docs/3.8_冻结代码校验.json')
archive=RELEASE/ARCHIVE_NAME
subprocess.run([sys.executable,str(DEV/'scripts/archive.py'),str(PORTABLE),str(archive)],check=True)
with archive.open('rb') as file:digest=hashlib.file_digest(file,'sha256').hexdigest()
archive.with_suffix('.sha256').write_text(digest+'  '+ARCHIVE_NAME+'\n',encoding='utf-8-sig')
subprocess.run([sys.executable,str(DEV/'scripts/verify_delivery_38.py')],check=True)
