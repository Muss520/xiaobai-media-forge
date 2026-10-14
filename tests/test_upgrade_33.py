from dataclasses import replace
from pathlib import Path
import pytest
from mediaforge.models import MediaInfo, VideoOptions, LiveOptions


def test_video_professional_parameters():
    from mediaforge.video import build_command
    info = MediaInfo(Path('source.mp4'), 'video', 10000, 1920, 1080)
    options = replace(VideoOptions(codec='hevc'), pixel_format='yuv420p10le', profile='main10', keyframe_interval=48, metadata=True)
    args = build_command(info, options, Path('output.mp4'))
    assert args[args.index('-pix_fmt')+1] == 'yuv420p10le'
    assert args[args.index('-g')+1] == '48'
    assert args[args.index('-map_metadata')+1] == '0'


def test_live_explicit_copy_contract():
    assert LiveOptions().video_copy is True


def test_metadata_validation():
    from mediaforge.metadata import validate_edit
    assert validate_edit('EXIF:Artist', '摄影师') == '摄影师'
    with pytest.raises(ValueError):
        validate_edit('File:ImageWidth', '42')
    with pytest.raises(ValueError):
        validate_edit('EXIF:GPSLatitude', '100')


def test_quick_advanced_does_not_clear_limit(qt_app):
    from mediaforge.simple import QuickForm
    form=QuickForm()
    form.set_kinds({'video','live'})
    form.store.edit('video','target_bytes',1048576)
    form.more.setChecked(True)
    form.more.setChecked(False)
    assert form.store.snapshot('video').target_bytes == 1048576
    assert '高级' in form.more.text()
    form.close()


def test_cat_terminal_state_returns_to_idle(qt_app,tmp_path):
    from mediaforge.controller import AppController
    controller=AppController(qt_app,tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    controller.pet.set_state('complete')
    assert controller.pet.state_reset.isActive()
    controller.pet.settle_state()
    assert controller.pet.state=='idle'
    controller.request_exit()


def test_metadata_original_quality_export(tmp_path):
    import threading
    from PIL import Image
    from mediaforge.metadata import export_component,MetadataOptions,read_metadata,media_fingerprint
    source=tmp_path/'原始照片.jpg'; out=tmp_path/'副本.jpg'
    exif=Image.Exif(); exif[315]='Alice'; exif[274]=6
    Image.new('RGB',(32,24),'red').save(source,exif=exif)
    before=source.read_bytes()
    report=export_component(source,out,MetadataOptions(clear=True),0,threading.Event(),lambda p:None)
    assert source.read_bytes()==before
    assert media_fingerprint(source,threading.Event())==media_fingerprint(out,threading.Event())
    values=read_metadata(out)
    assert not any(k.endswith(':Artist') for k in values)
    assert any(k.endswith(':Orientation') and v==6 for k,v in values.items())
    assert report['original_quality_verified']


def test_metadata_edit_and_lists_are_verified(tmp_path):
    import threading,json
    from PIL import Image
    from mediaforge.metadata import export_component,MetadataOptions,read_metadata
    source=tmp_path/'照片.jpg'; out=tmp_path/'编辑.jpg'
    Image.new('RGB',(24,24),'blue').save(source)
    value=MetadataOptions(edits=((0,'IFD0:Artist','中文作者'),(0,'XMP-dc:Subject',json.dumps(['旅行','天空'],ensure_ascii=False))))
    export_component(source,out,value,0,threading.Event(),lambda p:None)
    data=read_metadata(out)
    assert data['IFD0:Artist']=='中文作者'
    assert data['XMP-dc:Subject']==['旅行','天空']


def test_live_both_transcode_and_metadata_copy(tmp_path):
    import threading
    from PIL import Image
    from mediaforge.models import Job,ImageOptions
    from mediaforge.paths import tool_path
    from mediaforge.probe import run_tool,probe
    from mediaforge.live import process_live
    from mediaforge.metadata import process_metadata,MetadataOptions
    source=tmp_path/'照片.jpg'; movie=tmp_path/'影像.mov'
    Image.new('RGB',(80,60),'green').save(source)
    args=[tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i','testsrc2=size=160x120:duration=0.6','-c:v','libx264',str(movie)]
    result=run_tool(args); assert not result.returncode,result.stderr
    job=Job(source,inputs=(source,movie))
    output=tmp_path/'转码'; output.mkdir()
    options=LiveOptions(mode='both',format='png',video_copy=False,video=VideoOptions(format='mp4',width=80,height=60))
    outputs=process_live(job,options,output,threading.Event(),lambda p:None)
    assert {p.suffix for p in outputs}=={'.png','.mp4'}
    assert probe(output/'photo.mp4').width==80
    copied=tmp_path/'原画质'; copied.mkdir()
    files,reports=process_metadata(job,MetadataOptions(),copied,threading.Event(),lambda p:None)
    assert (copied/'photo.mov').read_bytes()==movie.read_bytes()
    assert (copied/'photo.jpg').read_bytes()==source.read_bytes()
    assert len(reports)==2


def test_three_modes_and_live_label(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    window=MainWindow(tmp_path/'settings.json'); window.hardware_enabled=False
    assert window.simple_button.text()=='小白模式'
    assert window.advanced_button.text()=='专业模式'
    window.set_ui_mode('information',False)
    assert window.view_stack.currentWidget() is window.information_page
    form=window.simple_page.form
    panel=window.panels['live']
    assert panel.snapshot().mode=='both' and panel.snapshot().format=='png'
    form.set_kinds({'live'})
    assert form.rows['live'][1].labelForField(form.rows['live'][2]).text()=='照片格式'
    window.close()


def test_information_clear_is_per_file(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    window=MainWindow(tmp_path/'settings.json'); window.hardware_enabled=False
    page=window.information_page
    page.jobs=[Job(tmp_path/'a.jpg'),Job(tmp_path/'b.jpg')]
    page.files.addItems(['a.jpg','b.jpg'])
    page.clear.setChecked(True)
    page.files.setCurrentIndex(1)
    assert not page.clear.isChecked()
    page.files.setCurrentIndex(0)
    assert page.clear.isChecked()
    window.close()


def test_information_retry_keeps_origin(qt_app,tmp_path,monkeypatch):
    from mediaforge.controller import AppController
    from mediaforge.metadata import MetadataOptions
    from mediaforge.models import Job
    from mediaforge.workflow import make_request
    from PySide6.QtWidgets import QPushButton
    controller=AppController(qt_app,tmp_path/'settings.json',quit_application=False); controller.window.hardware_enabled=False
    job=Job(tmp_path/'broken.jpg',status='失败',error='损坏')
    request=make_request([job],{'image':MetadataOptions(clear=True)},origin='information')
    collected=[]; monkeypatch.setattr(controller,'enqueue',collected.append)
    controller.show_result(request,0,1,0)
    button=next(b for b in controller.feedback.findChildren(QPushButton) if b.text()=='按本次需求重试')
    button.click()
    assert collected[0].origin=='information'
    controller.request_exit()


def test_png_clear_preserves_gamma(tmp_path):
    import threading,struct
    from PIL import Image,PngImagePlugin
    from mediaforge.metadata import export_component,MetadataOptions,read_metadata,can_edit,writable_catalog
    source=tmp_path/'gamma.png'; out=tmp_path/'clear.png'
    data=PngImagePlugin.PngInfo(); data.add(b'gAMA',struct.pack('>I',45455)); data.add_text('Comment','private')
    Image.new('RGBA',(32,24),(20,30,40,100)).save(source,pnginfo=data)
    export_component(source,out,MetadataOptions(clear=True),0,threading.Event(),lambda p:None)
    assert read_metadata(source)['PNG:Gamma']==read_metadata(out)['PNG:Gamma']
    catalog=writable_catalog()
    assert not can_edit('PNG:Gamma',catalog)
    assert not can_edit('IFD0:RowsPerStrip',catalog)
