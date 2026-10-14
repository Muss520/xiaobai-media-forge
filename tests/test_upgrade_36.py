from pathlib import Path
import pytest


def test_live_video_format_is_primary_and_preserves_photo(qt_app):
    from mediaforge.options import LivePanel,select
    panel=LivePanel();panel.set_ui_mode('advanced',False)
    try:
        assert hasattr(panel,'video_output')
        assert panel.base.labelForField(panel.video_output).text()=='视频格式'
        select(panel.format,'png');select(panel.video_output,'mkv')
        assert panel.snapshot().format=='png' and panel.snapshot().video.format=='mkv' and not panel.snapshot().video_copy
        select(panel.mode,'image');select(panel.mode,'both')
        assert panel.snapshot().format=='png' and panel.video_output.currentData()=='mkv'
        select(panel.video_output,'original_mov')
        assert panel.snapshot().video_copy and not panel.video_panel.isEnabled()
    finally:panel.close()


def test_quick_live_video_format_visible_without_advanced(qt_app):
    from mediaforge.simple import QuickForm
    from mediaforge.options import select
    form=QuickForm();form.set_kinds({'live'});form.show()
    try:
        assert hasattr(form,'live_video_output')
        assert form.live_video_output.isVisible() and not form.more.isChecked()
        select(form.live_video_output,'mp4')
        value=form.store.snapshot('live')
        assert value.format=='png' and value.video.format=='mp4' and not value.video_copy
    finally:form.close()


def test_resource_and_runtime_paths_are_independent(tmp_path,monkeypatch):
    import mediaforge.paths as paths
    project=tmp_path/'整理目录';dev=project/'开发资料';dev.mkdir(parents=True);(project/'project.marker').touch()
    monkeypatch.setattr(paths,'app_home',lambda:project)
    assert hasattr(paths,'runtime_home') and hasattr(paths,'resource_home')
    assert paths.runtime_home()==project/'运行数据'
    assert paths.documents_home()==project/'文档'


def test_detail_card_has_complete_view_and_fits_text(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job,MediaInfo
    from PySide6.QtTest import QTest
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        w.set_ui_mode('advanced',False);w.resize(980,640);w.show()
        path=tmp_path/('超长中文文件名'*12+'.mp4')
        job=Job(path,info=MediaInfo(path,kind='video',size=1000000,width=1920,height=1080,duration=3,fps=30,video_codec='h264'))
        w.jobs['video'].append(job);w.render_job('video',job);w.tables['video'].selectRow(0);QTest.qWait(30)
        card=w.details['video']
        assert hasattr(card,'open_details') and hasattr(card,'original') and hasattr(card,'output')
        assert card.original.height()>=card.original.fontMetrics().height()
        assert '音频设置' in card.text() and '质量' in card.text()
        card.open_details();dialog=card.dialog;assert dialog.isVisible()
        card.open_details();assert card.dialog is dialog
        dialog.close()
    finally:w.close()


@pytest.mark.parametrize('container',['mp4','mov','mkv'])
def test_live_both_explicit_video_container_is_decodable(tmp_path,container):
    import threading
    from mediaforge.models import Job,LiveOptions,ImageOptions,VideoOptions
    from mediaforge.live import process_live
    from mediaforge.probe import probe
    reference=Path(__file__).parent/'artifacts/live-reference'
    photo,movie=reference/'keyPhoto.heic',reference/'pairedVideo.mov'
    original=movie.read_bytes();out=tmp_path/container;out.mkdir()
    options=LiveOptions(mode='both',format='png',video_copy=False,image=ImageOptions(width=128,height=128),video=VideoOptions(format=container,width=128,height=128,fps=12))
    outputs=process_live(Job(photo,inputs=(photo,movie)),options,out,threading.Event(),lambda p:None)
    video=probe(out/('photo.'+container))
    assert len(outputs)==2 and video.video_codec=='h264' and max(video.width,video.height)<=128
    assert probe(out/'photo.png').width>0 and movie.read_bytes()==original


def test_live_format_memory_survives_restart(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.options import select
    config=tmp_path/'settings.json';w=MainWindow(config);w.hardware_enabled=False
    panel=w.panels['live'];select(panel.format,'webp');select(panel.video_output,'mkv');select(panel.mode,'video');select(panel.format,'mov');select(panel.mode,'both')
    assert panel.format.currentData()=='webp'
    w.save_settings();w.close()
    again=MainWindow(config);again.hardware_enabled=False
    try:
        live=again.panels['live'];assert live.format.currentData()=='webp' and live.video_output.currentData()=='mov'
        select(live.mode,'video');assert live.format.currentData()=='mov'
    finally:again.close()


def test_settings_does_not_forget_pet_video_format(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.preferences['quick']['live']['video_format']='mkv';c.show_settings()
        c.settings_dialog.apply_quick()
        assert c.preferences['quick']['live']['video_format']=='mkv'
    finally:c.request_exit()


def test_full_manual_uses_documents_directory(qt_app,tmp_path,monkeypatch):
    from mediaforge.window import MainWindow
    from mediaforge.paths import documents_home
    from PySide6.QtGui import QDesktopServices
    opened=[];monkeypatch.setattr(QDesktopServices,'openUrl',lambda url:opened.append(Path(url.toLocalFile())))
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:w.show_help();assert opened==[documents_home()/'使用说明.txt']
    finally:w.close()


def test_report_locations_follow_actual_executable_home(tmp_path):
    from mediaforge.paths import find_home,runtime_home,documents_home
    project=tmp_path/'项目';project.mkdir();(project/'project.marker').touch();(project/'开发资料').mkdir()
    installed=project/'软件程序/MediaForge'
    assert find_home(installed)==project and runtime_home(find_home(installed))==project/'运行数据'
    assert documents_home(find_home(installed))==project/'文档'
    standalone=tmp_path/'独立源码包';built=standalone/'成品/MediaForge'
    assert find_home(built)==built and documents_home(find_home(built))==built/'docs'
