from dataclasses import replace
from pathlib import Path
import pytest


def test_resolution_is_per_file_and_no_upscale():
    from mediaforge.models import VideoOptions,ImageOptions,MediaInfo
    from mediaforge.resolution import resolve_options
    options=replace(VideoOptions(),resolution_preset='1080p')
    landscape=resolve_options(MediaInfo(Path('a.mp4'),'video',10,3840,2160),options)
    portrait=resolve_options(MediaInfo(Path('b.mp4'),'video',10,2160,3840),options)
    small=resolve_options(MediaInfo(Path('c.mp4'),'video',10,640,360),options)
    assert (landscape.width,landscape.height)==(1920,1080)
    assert (portrait.width,portrait.height)==(1080,1920)
    assert (small.width,small.height)==(640,360)


def test_quick_summary_is_not_a_form_label(qt_app):
    from mediaforge.simple import QuickForm
    from PySide6.QtWidgets import QFormLayout
    form=QuickForm(); form.set_kinds({'live'})
    panel=form.store.panels['live']; panel.image_panel.quality.setValue(68); form.store.capture()
    summary=form.rows['live'][6]
    owner=summary.parentWidget().layout()
    assert not isinstance(owner,QFormLayout) or owner.getWidgetPosition(summary)[1]!=QFormLayout.LabelRole
    assert hasattr(form,'resolution_controls')
    form.close()


def test_mov_semantic_edit_targets():
    from mediaforge.metadata_fields import resolve_field
    record={'Keys:Make':'Apple','Keys:GPSCoordinates':'31.7778 119.8782','Composite:GPSLatitude':31.7778}
    assert resolve_field('make',record,'.mov').tag=='Keys:Make'
    assert resolve_field('location',record,'.mov').tag=='Keys:GPSCoordinates'
    assert resolve_field('make',{},'.mkv').strategy=='sidecar'


def test_metadata_table_does_not_open_tiny_inline_editor(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from PySide6.QtWidgets import QAbstractItemView
    w=MainWindow(tmp_path/'settings.json'); w.hardware_enabled=False
    assert w.information_page.raw_table.editTriggers()==QAbstractItemView.NoEditTriggers
    assert hasattr(w.information_page,'edit_selected')
    w.close()

def test_mov_native_fields_and_quality(tmp_path):
    import threading
    from mediaforge.paths import tool_path
    from mediaforge.probe import run_tool
    from mediaforge.metadata import export_component,MetadataOptions,read_metadata,media_fingerprint
    source=tmp_path/'来源.mov'; destination=tmp_path/'编辑.mov'
    result=run_tool([tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i','testsrc2=size=96x64:duration=0.2','-c:v','libx264',str(source)])
    assert result.returncode==0,result.stderr
    original=source.read_bytes()
    edits=((0,'Keys:Make','Apple 小白'),(0,'Keys:Model','iPhone 15 Pro'),(0,'VideoKeys:LensModel','测试镜头'),(0,'Keys:GPSCoordinates','-31.777800, 119.878200, 12.50'),(0,'QuickTime:CreateDate','2026:10:06 03:13:18'))
    export_component(source,destination,MetadataOptions(edits=edits),0,threading.Event(),lambda p:None)
    values=read_metadata(destination)
    assert values['Keys:Make']=='Apple 小白'
    assert abs(values['Composite:GPSLatitude']+31.7778)<1e-5
    assert abs(values['Composite:GPSAltitude']-12.5)<0.01
    assert source.read_bytes()==original
    assert media_fingerprint(source)==media_fingerprint(destination)


def test_supplement_sidecar_roundtrip(tmp_path):
    import threading,json
    from PIL import Image
    from mediaforge.models import Job
    from mediaforge.metadata import MetadataOptions,process_metadata,read_metadata
    source=tmp_path/'原图.bmp'; out=tmp_path/'补充.bmp'
    Image.new('RGB',(24,16),'red').save(source)
    options=MetadataOptions(supplements=((0,'XMP-tiff:Make','测试设备','sidecar'),(0,'XMP-exif:GPSLatitude','-10.0','sidecar'),(0,'XMP-dc:Subject',json.dumps(['中文','旅行'],ensure_ascii=False),'sidecar')))
    outputs,_=process_metadata(Job(source),options,out,threading.Event(),lambda p:None)
    assert out.read_bytes()==source.read_bytes()
    assert len(outputs)==2
    data=read_metadata(outputs[1]); assert data['XMP-tiff:Make']=='测试设备'; assert data['XMP-dc:Subject']==['中文','旅行']

def test_resolution_is_idempotent_and_preview_matches_pixels(tmp_path):
    import threading
    from PIL import Image
    from mediaforge.models import ImageOptions
    from mediaforge.probe import probe
    from mediaforge.resolution import resolve_options
    from mediaforge.images import process_image
    photo=tmp_path/'竖图.jpg'; destination=tmp_path/'输出.png'
    Image.new('RGB',(601,803),'white').save(photo)
    source=probe(photo); once=resolve_options(source,ImageOptions(format='png',resolution_preset='480p'))
    assert resolve_options(source,once)==once
    process_image(source,once,destination,threading.Event(),lambda p:None)
    assert Image.open(destination).size==(once.width,once.height)


def test_cat_actions_keep_processing_priority(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False); c.window.hardware_enabled=False
    try:
        pet=c.pet; assert len(pet.frames)==len(pet.frame_anchors)
        pet.set_state('idle'); assert pet.frame_index==0
        pet.interact('stretch'); assert pet.action=='stretch'
        pet.set_state('working'); pet.interact('pet'); assert pet.action=='working'
        pet.set_state('receiving'); assert pet.frame_index in (3,4,5)
        c.set_motion(True); assert not pet.timer.isActive()
        pet.set_state('idle'); pet.interact(); assert pet.action=='pet' and not pet.timer.isActive()
    finally:c.request_exit()


def test_compact_table_and_summary_geometry(qt_app,tmp_path):
    from PySide6.QtTest import QTest
    from mediaforge.window import MainWindow
    from mediaforge.models import Job,MediaInfo
    w=MainWindow(tmp_path/'settings.json'); w.hardware_enabled=False
    try:
        w.resize(1080,760); w.show(); w.set_ui_mode('advanced',False); QTest.qWait(50)
        table=w.tables['video']
        assert table.isColumnHidden(5)
        assert table.horizontalHeader().length()<=table.viewport().width()+3
        assert w.details['video'].isHidden()
        job=Job(tmp_path/'测试文件.livp',info=MediaInfo(tmp_path/'测试文件.livp','live',100,3024,4032))
        w.jobs['live'].append(job); w.simple_page.set_step(1); w.set_ui_mode('simple',False)
        w.panels['live'].image_panel.quality.setValue(68); w.parameter_store.capture() if hasattr(w,'parameter_store') else w.simple_page.form.store.capture()
        QTest.qWait(30); form=w.simple_page.form; summary=form.rows['live'][6]
        assert summary.width()>form.width()/2
        form.more.setChecked(True); QTest.qWait(30)
        assert form.more.y()<form.advanced_bodies['live'].y()
    finally:w.close()

@pytest.mark.parametrize('rotated,small',[(False,False),(True,False),(False,True)])
def test_video_resolution_preview_equals_export(tmp_path,rotated,small):
    import threading
    from mediaforge.paths import tool_path
    from mediaforge.probe import run_tool,probe
    from mediaforge.models import VideoOptions
    from mediaforge.resolution import resolve_options
    from mediaforge.video import process_video
    source=tmp_path/'横屏.mp4'; size='320x180' if small else '1600x900'
    result=run_tool([tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i',f'testsrc2=size={size}:duration=0.12','-c:v','libx264','-preset','ultrafast',str(source)])
    assert result.returncode==0,result.stderr
    if rotated:
        target=tmp_path/'旋转.mov'
        result=run_tool([tool_path('ffmpeg'),'-v','error','-y','-display_rotation:v:0','90','-i',str(source),'-c','copy',str(target)])
        assert result.returncode==0,result.stderr
        source=target
    info=probe(source); options=VideoOptions(resolution_preset='720p',speed='ultrafast')
    effective=resolve_options(info,options); destination=tmp_path/'输出.mp4'
    process_video(info,effective,destination,threading.Event(),lambda p:None)
    actual=probe(destination)
    assert (actual.width,actual.height)==(effective.width,effective.height)
    assert (actual.width,actual.height)==((320,180) if small else (720,1280) if rotated else (1280,720))


def test_old_dimensions_remain_custom(qt_app):
    from mediaforge.options import VideoPanel,ImagePanel
    for cls in (VideoPanel,ImagePanel):
        panel=cls(); panel.restore({'width':640,'height':480})
        assert panel.snapshot().resolution_preset=='custom'
        assert panel.snapshot().width==640 and panel.snapshot().height==480
        panel.deleteLater()


def test_combined_live_suggestions_keep_safe_dimensions(tmp_path):
    from mediaforge.models import Job,LiveOptions,ImageOptions,MediaInfo
    from mediaforge.workflow import make_request
    from mediaforge.preflight import Finding,apply_suggestions
    path=tmp_path/'a.livp'; options=LiveOptions(mode='animation',format='gif',target_bytes=1000000)
    job=Job(path,info=MediaInfo(path,'live',100,4032,3024,duration=10,fps=30))
    request=make_request([job],{'live':options})
    resolved=replace(options,image=replace(options.image,width=4032,height=3024,resolved_size=True))
    safe=replace(resolved,image=replace(resolved.image,width=720,height=540),animation_fps=15)
    findings=[Finding(job.id,'安全尺寸','animation_budget',safe),Finding(job.id,'尺寸搜索','target_size',replace(resolved,image=replace(resolved.image,auto_resize=True)))]
    actual=apply_suggestions(request,findings).items[0].parameters
    assert (actual.image.width,actual.image.height)==(720,540)
    assert actual.image.auto_resize and actual.animation_fps==15


def test_mov_existing_gps_group_wins():
    from mediaforge.metadata_fields import resolve_field
    assert resolve_field('location',{'UserData:GPSCoordinates':'31 119'},'.mov').tag=='UserData:GPSCoordinates'

def test_professional_live_resolution_visible(qt_app):
    from mediaforge.options import LivePanel,select
    panel=LivePanel(); panel.set_ui_mode('advanced',False); panel.show()
    try:
        for mode in ('both','image','animation','preserve'):
            select(panel.mode,mode)
            assert panel.image_panel.resolution.isVisible(),mode
    finally:panel.close()


def test_pet_transparency_matches_current_frame(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from PySide6.QtGui import QRegion
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False); c.window.hardware_enabled=False
    try:
        c.pet.set_state('idle')
        assert c.pet.mask()==QRegion(c.pet.frames[c.pet.frame_index].mask())
    finally:c.request_exit()

def test_retry_keeps_each_orientation_and_output_folder(qt_app,tmp_path,monkeypatch):
    from mediaforge.controller import AppController
    from mediaforge.models import Job,MediaInfo,VideoOptions
    from mediaforge.workflow import make_request
    from PySide6.QtWidgets import QPushButton
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False); c.window.hardware_enabled=False
    try:
        a=Job(tmp_path/'a.mp4',info=MediaInfo(tmp_path/'a.mp4','video',100,3840,2160),status='失败')
        b=Job(tmp_path/'b.mp4',info=MediaInfo(tmp_path/'b.mp4','video',100,2160,3840),status='失败')
        request=make_request([a,b],{'video':VideoOptions(resolution_preset='1080p')},output=tmp_path/'指定目录',origin='advanced')
        captured=[]; monkeypatch.setattr(c,'enqueue',captured.append)
        c.show_result(request,0,2,0)
        next(w for w in c.feedback.findChildren(QPushButton) if w.text()=='按本次需求重试').click()
        assert [(i.parameters.width,i.parameters.height) for i in captured[0].items]==[(1920,1080),(1080,1920)]
        assert all(i.folder==tmp_path/'指定目录' for i in captured[0].items)
    finally:c.request_exit()

def test_raw_xmp_uses_attachment_for_non_embedded_format():
    from mediaforge.metadata_fields import resolve_tag
    target=resolve_tag('XMP-dc:Subject',{'XMP-dc:Subject':['旧关键词']},'.bmp',{'XMP-dc:Subject':'string+'})
    assert target.strategy=='sidecar' and target.kind=='list'

def test_metadata_editor_actions_stay_in_view(qt_app):
    from mediaforge.metadata_editor import MetadataEditor
    from mediaforge.metadata_fields import FieldTarget
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtCore import QPoint
    editor=MetadataEditor(FieldTarget('拍摄时间','Keys:CreationDate','native','date'),'2026:10:06 11:13:17+08:00')
    editor.setStyleSheet('QWidget {font-size:12pt;} QPushButton {padding:8px 12px;}')
    (editor.content_layout if hasattr(editor,'content_layout') else editor.layout()).insertWidget(3,QPushButton('改用 XMP 补充信息'))
    editor.resize(360,330); editor.show(); qt_app.processEvents()
    try:
        apply=next(b for b in editor.findChildren(QPushButton) if b.text()=='应用到待导出副本')
        assert apply.mapTo(editor,QPoint(0,0)).y()+apply.height()<=330
        assert editor.height()<=330
    finally:editor.close()

def test_gps_altitude_readback_mismatch_is_not_success(tmp_path,monkeypatch):
    import threading
    from PIL import Image
    from mediaforge import metadata
    source=tmp_path/'input.jpg'; destination=tmp_path/'output.jpg'
    Image.new('RGB',(12,12),'red').save(source)
    monkeypatch.setattr(metadata,'read_metadata',lambda *args:{'Keys:GPSCoordinates':'31 119 99'})
    monkeypatch.setattr(metadata,'run_exif',lambda *args:None)
    monkeypatch.setattr(metadata,'writable_catalog',lambda *args:{'Keys:GPSCoordinates':'?'})
    with pytest.raises(ValueError,match='核验失败'):
        metadata.export_component(source,destination,metadata.MetadataOptions(edits=((0,'Keys:GPSCoordinates','31, 119, 12.5'),)),0,threading.Event(),lambda p:None)
    assert not destination.exists()
