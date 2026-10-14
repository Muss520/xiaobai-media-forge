"""Metadata-only transactions. All writes target copies, never original media."""
from dataclasses import dataclass,replace
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
from .paths import tool_path, app_home, temporary_output
from .live import run_exif, components, copy_cancelled
from .images import check_cancel

READONLY_GROUPS={'File','System','Composite','ExifTool'}
STRUCTURAL={'ImageWidth','ImageHeight','ExifImageWidth','ExifImageHeight','BitsPerSample','Compression','PhotometricInterpretation','SamplesPerPixel','StripOffsets','StripByteCounts','TileOffsets','TileByteCounts','JpgFromRaw','ThumbnailImage','PreviewImage','ICC_Profile','Orientation','Rotation','ColorSpace','ContentIdentifier','StillImageTime','LivePhotoVideoIndex','RowsPerStrip','PlanarConfiguration','YCbCrSubSampling','YCbCrCoefficients','YCbCrPositioning','WhitePoint','PrimaryChromaticities','Gamma','SRGBRendering','PixelAspectRatio','ColorPrimaries','TransferCharacteristics','MatrixCoefficients','ColorTemperature','RedMatrixColumn','GreenMatrixColumn','BlueMatrixColumn'}
CATALOG=None
CLASSIFICATIONS={}
ESSENTIAL={'Orientation','Rotation','ColorSpace','Gamma','WhitePoint','PrimaryChromaticities','SRGBRendering','ColorPrimaries','TransferCharacteristics','MatrixCoefficients','PixelAspectRatio'}
COMMON={'DateTimeOriginal':'拍摄时间','CreateDate':'创建时间','Make':'设备品牌','Model':'设备型号','LensModel':'镜头型号','FocalLength':'焦距','FNumber':'光圈','ExposureTime':'曝光时间','ISO':'感光度','GPSLatitude':'纬度','GPSLongitude':'经度','GPSLatitudeRef':'纬度方向','GPSLongitudeRef':'经度方向','Artist':'作者','Copyright':'版权','ImageDescription':'描述','Title':'标题','Comment':'备注'}

@dataclass(frozen=True)
class MetadataOptions:
    clear: bool = False
    edits: tuple = ()  # (component index, group:tag, normalized value)
    supplements: tuple = ()  # (component index, XMP tag, value, 'xmp'/'sidecar')


def writable_catalog(cancel=None):
    global CATALOG
    if CATALOG is None:
        result=run_exif([tool_path('exiftool'),'-listx'],cancel)
        root=ET.fromstring(result.stdout)
        catalog={}
        for table in root.findall('table'):
            for tag in table.findall('tag'):
                if tag.get('writable')=='true':
                    group=tag.get('g1') or table.get('g1') or table.get('g0')
                    if group:
                        dtype=tag.get('type','string')
                        if tag.get('list'):dtype+='+'
                        catalog[group+':'+tag.get('name','')]=dtype
                        CLASSIFICATIONS[group+':'+tag.get('name','')]=tag.get('g2') or table.get('g2')
        CATALOG=catalog
    return CATALOG


def can_edit(key,catalog):
    group,_,name=key.partition(':')
    descriptive=CLASSIFICATIONS.get(key) in {'Camera','Time','Location','Author','Document'} or name in COMMON or name in {'Subject','Creator','Keywords','Description','UserComment','Rating','Label','Rights','Headline','Caption-Abstract','Credit','Source'}
    from .metadata_fields import NATIVE_TEXT
    return (descriptive and key in catalog and catalog[key] not in {'undef','binary','?'} or key in NATIVE_TEXT and key in catalog) and not group.startswith('ICC') and group not in READONLY_GROUPS and name not in STRUCTURAL and not name.startswith(('Thumbnail','Preview','Movie','Media','Track','Video','Audio','ColorMatrix','Calibration','BlackLevel','WhiteLevel') if key not in NATIVE_TEXT else ('Thumbnail','Preview'))


def validate_edit(key,value):
    if not re.fullmatch(r'[A-Za-z0-9_-]+:[A-Za-z0-9_-]+',key):
        raise ValueError('请选择有效的元数据标签')
    group,_,name=key.partition(':')
    if group in READONLY_GROUPS or name in STRUCTURAL:
        raise ValueError('该字段是技术或显示必要信息，只读')
    value=str(value)
    if '\n' in value or '\r' in value or '\x00' in value or len(value)>8192:
        raise ValueError('字段值过长或包含不支持的换行/空字符')
    if name in {'GPSLatitude','GPSLongitude'} and value:
        limit=90 if name=='GPSLatitude' else 180
        try:number=float(value)
        except ValueError:raise ValueError('GPS 必须为十进制度数')
        if not -limit<=number<=limit:raise ValueError('GPS 超出合法范围')
    if name in {'GPSLatitudeRef','GPSLongitudeRef'} and value.upper() not in ({'N','S'} if name.endswith('LatitudeRef') else {'E','W'}):
        raise ValueError('纬度方向为 N/S，经度方向为 E/W')
    if name in {'DateTimeOriginal','CreateDate','ModifyDate'} and value:
        from datetime import datetime
        try:datetime.fromisoformat(value.replace(':','-',2))
        except ValueError:raise ValueError('时间请填写 YYYY:MM:DD HH:MM:SS，可附时区')
    if name in {'FocalLength','FNumber','ISO','ExposureTime'} and value:
        from fractions import Fraction
        try:
            if Fraction(value)<=0:raise ValueError()
        except (ValueError,ZeroDivisionError):raise ValueError('此数值需为正数，可使用分数如 1/100')
    return value


def read_metadata(path,cancel=None):
    result=run_exif([tool_path('exiftool'),'-j','-n','-a','-G1','-s','-ee','-charset','filename=UTF8',str(path)],cancel)
    values=json.loads(result.stdout)[0]
    if any(key.endswith(':Error') for key in values):raise ValueError('无法读取素材元数据')
    return {key:value for key,value in values.items() if ':' in key}


def media_fingerprint(path,cancel=None):
    """Check decoded image pixels or copied compressed A/V packets, not file bytes."""
    from .models import IMAGE_EXTENSIONS
    if cancel is None:
        import threading
        cancel=threading.Event()
    digest=hashlib.sha256()
    if Path(path).suffix.lower() in IMAGE_EXTENSIONS:
        from PIL import Image
        with Image.open(path) as im:
            digest.update(str(im.getexif().get(274,1)).encode())
            digest.update(im.info.get('icc_profile') or b'')
            for index in range(getattr(im,'n_frames',1)):
                check_cancel(cancel)
                im.seek(index)
                rgba=im.convert('RGBA')
                digest.update(str(rgba.size).encode()); digest.update(rgba.tobytes())
                digest.update(str(im.info.get('duration',0)).encode())
            digest.update(str(im.info.get('loop',0)).encode())
    else:
        from .probe import run_tool
        result=run_tool([tool_path('ffmpeg'),'-v','error','-i',str(path),'-map','0:v?','-map','0:a?','-c','copy','-f','framemd5','-'],timeout=300,cancel=cancel)
        if result.returncode:raise ValueError('无法验证原画质媒体内容：'+result.stderr[-500:])
        # Packet timing, stream identity and hashes must all remain unchanged.
        for line in result.stdout.splitlines():
            if line and not line.startswith('#'):
                digest.update(','.join(part.strip() for part in line.split(',')).encode())
    return digest.hexdigest()


def export_component(source,destination,options,index,cancel,progress):
    if Path(source).resolve()==Path(destination).resolve():raise ValueError('输出不能覆盖原文件')
    temp=temporary_output(destination)
    try:
        before=read_metadata(source,cancel)
        copy_cancelled(source,temp,cancel,lambda p:progress(int(p*.3)))
        all_edits=options.edits+tuple((component,key,value) for component,key,value,strategy in options.supplements if strategy=='xmp')
        edits=[(key,validate_edit(key,value)) for component,key,value in all_edits if component==index]
        if options.clear or edits:
            original_fingerprint=media_fingerprint(source,cancel)
            args=[tool_path('exiftool'),'-overwrite_original','-charset','filename=UTF8']
            if options.clear:
                args += ['-all=','-TagsFromFile',str(source),'-ICC_Profile']+['-'+key for key in before if key.partition(':')[2] in ESSENTIAL]
            catalog=writable_catalog(cancel) if edits else {}
            for key,value in edits:
                if not can_edit(key,catalog):raise ValueError('此标签不支持安全写入：'+key)
                dtype=catalog[key]
                if value=='':
                    args.append('-'+key+'='); continue
                if value and dtype.startswith(('int','float','double','rational')) and not dtype.endswith('+') and not key.partition(':')[2].endswith(('Date','Time','Original')):
                    from fractions import Fraction
                    try:Fraction(value)
                    except (ValueError,ZeroDivisionError):raise ValueError('数字字段需填写有效数字或分数：'+key)
                if dtype.endswith('+') or isinstance(before.get(key),list) or key in {'XMP-dc:Subject','XMP-dc:Creator','IPTC:Keywords'}:
                    try:items=json.loads(value)
                    except ValueError:raise ValueError('多值字段需填写 JSON 数组')
                    if not isinstance(items,list) or not all(isinstance(v,(str,int,float)) for v in items):raise ValueError('多值字段需填写简单值数组')
                    args.append('-'+key+'=')
                    args.extend('-'+key+'+='+validate_edit(key,v) for v in items)
                else:args.append('-'+key+'='+value)
            args.append(str(temp)); run_exif(args,cancel)
            progress(65)
            if media_fingerprint(temp,cancel)!=original_fingerprint:
                raise ValueError('元数据操作改变了媒体内容，已停止发布；可转到转换模式处理')
        after=read_metadata(temp,cancel)
        if options.clear:
            for key,value in before.items():
                if key.partition(':')[2] in ESSENTIAL and after.get(key)!=value:
                    raise ValueError('清除改变了显示必要信息：'+key+'；未发布输出')
        for key,value in edits:
            actual=after.get(key)
            if value=='' and actual is None:continue
            if str(actual)!=value:
                from fractions import Fraction
                try:
                    import math
                    equivalent=math.isclose(float(Fraction(str(actual))),float(Fraction(value)),rel_tol=1e-6,abs_tol=1e-8)
                except (ValueError,TypeError):
                    try:equivalent=isinstance(actual,list) and json.loads(value)==actual
                    except ValueError:equivalent=False
                if not equivalent and key.endswith(':GPSCoordinates'):
                    from .metadata_fields import parse_coordinates
                    try:
                        expected_coordinates=parse_coordinates(value); actual_coordinates=parse_coordinates(actual)
                        equivalent=all(a is None and b is None or a is not None and b is not None and abs(a-b)<1e-5
                                       for a,b in zip(expected_coordinates,actual_coordinates))
                    except ValueError:pass
                if not equivalent:raise ValueError(f'字段写入核验失败：{key}；读回 {actual}')
        retained=[key for key in before if key in after and key.partition(':')[0] not in READONLY_GROUPS]
        report={'removed':[key for key in before if key not in after], 'retained':retained,
                'edited':[key for key,_ in edits],'original_quality_verified':True,
                'supplemented':[key for component,key,value,strategy in options.supplements if component==index],
                'notice':'已清除工具支持的字段；保留显示必要和不可清除的信息，请查看保留清单。' if options.clear else '原画质副本；未重新编码。'}
        check_cancel(cancel); temp.replace(destination); progress(99)
        return report
    finally:temp.unlink(missing_ok=True)


def write_sidecar(path,edits,cancel):
    # Starting from an empty XMP document avoids copying unrelated private tags.
    path.write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta>',encoding='utf-8')
    args=[tool_path('exiftool'),'-overwrite_original','-charset','filename=UTF8']
    for key,value in edits:
        if not key.startswith('XMP-') or not can_edit(key,writable_catalog(cancel)):raise ValueError('不支持的 XMP 补充字段：'+key)
        value=validate_edit(key,value)
        if value=='':args.append('-'+key+'='); continue
        if key in {'XMP-dc:Subject','XMP-dc:Creator'}:
            values=json.loads(value)
            if not isinstance(values,list):raise ValueError('列表字段需使用列表编辑器')
            args += ['-'+key+'=']+['-'+key+'+='+validate_edit(key,v) for v in values]
        else:args.append('-'+key+'='+value)
    args.append(str(path)); run_exif(args,cancel)
    actual=read_metadata(path,cancel)
    for key,value in edits:
        expected=None if value=='' else json.loads(value) if key in {'XMP-dc:Subject','XMP-dc:Creator'} else value
        result=actual.get(key)
        if not equivalent_value(key,result,expected):raise ValueError('XMP 附件读回核验失败：'+key)


def equivalent_value(key,actual,expected):
    if actual==expected or str(actual)==str(expected):return True
    if isinstance(expected,list):return actual==expected
    from fractions import Fraction
    import math
    try:return math.isclose(float(Fraction(str(actual))),float(Fraction(str(expected))),rel_tol=1e-6,abs_tol=1e-8)
    except (ValueError,TypeError,ZeroDivisionError):return False


def sidecar_edits(options,index):
    return [(key,value) for component,key,value,strategy in options.supplements if component==index and strategy=='sidecar']


def process_metadata(job,options,destination,cancel,progress):
    if job.inputs or job.path.suffix.lower()=='.livp':
        stage=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex+'.partial')
        # Cleanup is owned only after exclusive creation succeeds.
        stage.mkdir()
        try:
            with components(job.path,job.inputs,cancel) as sources:
                reports=[]; outputs=[]
                for index,source in enumerate(sources):
                    output=stage/('photo'+source.suffix.lower())
                    reports.append(export_component(source,output,options,index,cancel,lambda p,i=index:progress(i*45+int(p*.45))))
                    outputs.append(output.name)
                    if sidecar_edits(options,index):
                        sidecar=output.with_name(output.name+'.xmp')
                        write_sidecar(sidecar,sidecar_edits(options,index),cancel); outputs.append(sidecar.name)
                (stage/'信息处理报告.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
            check_cancel(cancel); destination.rmdir(); stage.replace(destination)
            return tuple(destination/name for name in outputs),reports
        finally:
            if stage.exists():shutil.rmtree(stage)
    if sidecar_edits(options,0):
        stage=destination.with_name('.'+destination.name+'.'+uuid.uuid4().hex+'.metadata-stage')
        stage.mkdir()
        published=None
        try:
            staged=stage/destination.name
            report=export_component(job.path,staged,options,0,cancel,progress)
            companion=stage/(destination.name+'.xmp')
            write_sidecar(companion,sidecar_edits(options,0),cancel)
            check_cancel(cancel)
            final_sidecar=destination.with_name(companion.name)
            with final_sidecar.open('xb'):pass
            published=final_sidecar
            companion.replace(final_sidecar)
            check_cancel(cancel); staged.replace(destination)
            return (destination,final_sidecar),[report]
        except BaseException:
            if published:published.unlink(missing_ok=True)
            raise
        finally:
            if stage.exists():shutil.rmtree(stage)
    report=export_component(job.path,destination,options,0,cancel,progress)
    return (destination,),[report]
