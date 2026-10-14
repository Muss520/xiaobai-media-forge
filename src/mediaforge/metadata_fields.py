"""Human-facing fields and explicit native / embedded XMP / sidecar destinations."""
from dataclasses import dataclass
from datetime import datetime
import json
import re

MOV={'.mov','.mp4','.m4v','.3gp'}
EMBEDDED=MOV|{'.jpg','.jpeg','.png','.tif','.tiff','.heic','.heif','.avif','.webp'}
FIELDS={
 'capture':('拍摄时间','拍摄时间','date',('ExifIFD:DateTimeOriginal','Keys:CreationDate','QuickTime:CreateDate','XMP-exif:DateTimeOriginal'),'XMP-exif:DateTimeOriginal'),
 'make':('设备与镜头','设备品牌','text',('Keys:Make','IFD0:Make','XMP-tiff:Make'),'XMP-tiff:Make'),
 'model':('设备与镜头','设备型号','text',('Keys:Model','IFD0:Model','XMP-tiff:Model'),'XMP-tiff:Model'),
 'lens':('设备与镜头','镜头型号','text',('VideoKeys:LensModel','Keys:LensModel','ExifIFD:LensModel','XMP-exifEX:LensModel'),'XMP-exifEX:LensModel'),
 'focal':('设备与镜头','焦距','number',('ExifIFD:FocalLength','XMP-exif:FocalLength'),'XMP-exif:FocalLength'),
 'aperture':('设备与镜头','光圈','number',('ExifIFD:FNumber','XMP-exif:FNumber'),'XMP-exif:FNumber'),
 'exposure':('拍摄时间','曝光时间','number',('ExifIFD:ExposureTime','XMP-exif:ExposureTime'),'XMP-exif:ExposureTime'),
 'iso':('拍摄时间','感光度','number',('ExifIFD:ISO',),'XMP-exif:ISOSpeedRatings'),
 'location':('地点','拍摄坐标','gps',('Keys:GPSCoordinates','UserData:GPSCoordinates','Composite:GPSPosition'),'XMP-exif:GPSLatitude'),
 'author':('作者','作者','text',('IFD0:Artist','Keys:Author','XMP-dc:Creator'),'XMP-dc:Creator'),
 'description':('作者','说明','text',('IFD0:ImageDescription','Keys:Description','XMP-dc:Description'),'XMP-dc:Description'),
 'keywords':('作者','关键词','list',('XMP-dc:Subject','IPTC:Keywords'),'XMP-dc:Subject'),
 'copyright':('作者','版权','text',('IFD0:Copyright','XMP-dc:Rights'),'XMP-dc:Rights'),
}
NATIVE_TEXT={'Keys:Make','Keys:Model','Keys:Author','Keys:Description','VideoKeys:LensModel','Keys:LensModel','Keys:CreationDate','Keys:GPSCoordinates','UserData:GPSCoordinates'}

@dataclass(frozen=True)
class FieldTarget:
    label: str
    tag: str
    strategy: str  # native, xmp, sidecar, readonly
    kind: str='text'
    reason: str=''


def field_value(name,record):
    if name=='location':
        for key in ('Keys:GPSCoordinates','UserData:GPSCoordinates'):
            if key in record:return record[key]
    if name=='location' and 'Composite:GPSLatitude' in record and 'Composite:GPSLongitude' in record:
        return f'{record["Composite:GPSLatitude"]}, {record["Composite:GPSLongitude"]}'+(f', {record["Composite:GPSAltitude"]}' if record.get('Composite:GPSAltitude') is not None else '')
    for tag in FIELDS[name][3]:
        if tag in record:return record[tag]
    return None


def resolve_field(name,record,extension,supplement=False):
    _,label,kind,tags,xmp=FIELDS[name]
    extension=extension.lower()
    existing=next((tag for tag in tags if tag in record and not tag.startswith(('Composite:','XMP-'))),None)
    if name=='location' and extension in MOV and existing is None:existing='Keys:GPSCoordinates'
    if not supplement and existing and extension in EMBEDDED:
        return FieldTarget(label,existing,'native',kind,'将修改副本中的原生字段')
    if not supplement and extension in {'.jpg','.jpeg','.tif','.tiff','.heic','.heif','.avif','.png'} and name in {'make','model','capture','focal','aperture','exposure','iso','author','copyright','description','lens'}:
        image_tags={'make':'IFD0:Make','model':'IFD0:Model','capture':'ExifIFD:DateTimeOriginal','focal':'ExifIFD:FocalLength','aperture':'ExifIFD:FNumber','exposure':'ExifIFD:ExposureTime','iso':'ExifIFD:ISO','author':'IFD0:Artist','copyright':'IFD0:Copyright','description':'IFD0:ImageDescription','lens':'ExifIFD:LensModel'}
        return FieldTarget(label,image_tags[name],'native',kind,'写入副本的原生 EXIF 字段')
    return FieldTarget(label,xmp,'xmp' if extension in EMBEDDED else 'sidecar',
                       'list' if name=='keywords' or name=='author' else kind,
                       '补充信息单独标注，不替代原生字段；请明确选择后应用')


def resolve_tag(key,record,extension,catalog):
    from .metadata import can_edit
    extension=extension.lower()
    if key.startswith('XMP-') and can_edit(key,catalog):
        label=next((label for _,label,_,tags,xmp in FIELDS.values() if key in tags or key==xmp),key)
        kind='list' if isinstance(record.get(key),list) or catalog[key].endswith('+') else 'date' if key.partition(':')[2].endswith(('Date','Time','Original')) else 'text'
        return FieldTarget(label,key,'xmp' if extension in EMBEDDED else 'sidecar',kind,
                           '补充信息单独标注；此格式不支持内嵌时写入同名 XMP 附件')
    if key.startswith('Composite:GPS'):
        return resolve_field('location',record,extension)
    for name,(_,label,kind,tags,xmp) in FIELDS.items():
        if key in tags:
            if key in NATIVE_TEXT and extension in MOV:return FieldTarget(label,key,'native',kind)
            if can_edit(key,catalog) and extension in EMBEDDED:return FieldTarget(label,key,'native','list' if isinstance(record.get(key),list) else kind)
            return resolve_field(name,record,extension,True)
    return FieldTarget(key,key,'native' if can_edit(key,catalog) else 'readonly','list' if isinstance(record.get(key),list) else 'text',
                       '' if can_edit(key,catalog) else '技术、显示或配对字段只读，或当前格式不支持安全写入')


def parse_coordinates(value):
    numbers=re.findall(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?',str(value))
    if len(numbers)<2:raise ValueError('请填写经纬度，例如 31.7778, 119.8782')
    lat,lon=map(float,numbers[:2]); altitude=float(numbers[2]) if len(numbers)>2 else None
    if not -90<=lat<=90 or not -180<=lon<=180:raise ValueError('经纬度超出范围')
    return lat,lon,altitude


def display_value(name,value):
    if value is None:return '无'
    if value=='':return '待删除'
    if isinstance(value,list):return '、'.join(map(str,value))
    text=str(value)
    if name=='capture':
        text=text.replace(':','-',2)
        return text+(' · 时区未提供' if not re.search(r'(?:Z|[+-]\d\d:\d\d)$',text) else '')
    if name=='focal':return text+' mm'
    if name=='aperture':return 'f/'+text
    if name=='exposure':
        try:
            n=float(value)
            return (f'1/{round(1/n)}' if 0<n<1 else text)+' 秒'
        except ValueError:pass
    if name=='iso':return 'ISO '+text
    if name=='location':
        try:
            lat,lon,altitude=parse_coordinates(value)
            return f'{abs(lat):.6f}° {"N" if lat>=0 else "S"}，{abs(lon):.6f}° {"E" if lon>=0 else "W"}'+(f' · {altitude:g} m' if altitude is not None else '')
        except ValueError:pass
    return text
