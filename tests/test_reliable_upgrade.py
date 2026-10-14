import threading
from pathlib import Path
from PIL import Image
from PySide6.QtTest import QTest
import pytest


def test_wizard_steps_keep_state_and_list_items(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    window=MainWindow(settings_path=tmp_path/'settings.json')
    window.hardware_enabled=False
    page=window.simple_page
    assert page.step==0
    job=Job(tmp_path/'照片.png')
    window.jobs['image'].append(job)
    page.refresh()
    item=page.list.item(0)
    page.list.setCurrentItem(item)
    page.set_step(1)
    page.form.store.edit('image','format','png')
    page.set_step(0)
    page.refresh()
    assert page.list.item(0) is item
    assert window.panels['image'].snapshot().format=='png'
    window.close()


def test_live_both_without_pairing_metadata(tmp_path):
    from mediaforge.models import Job,LiveOptions
    from mediaforge.live import process_live
    from mediaforge.probe import run_tool,probe
    from mediaforge.paths import tool_path
    photo,movie=tmp_path/'photo.jpg',tmp_path/'movie.mov'
    Image.new('RGB',(100,80),'blue').save(photo)
    result=run_tool([tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i','color=blue:s=100x80:d=0.5','-c:v','libx264',str(movie)])
    assert result.returncode==0,result.stderr
    destination=tmp_path/'双文件'
    destination.mkdir()
    outputs=process_live(Job(photo,inputs=(photo,movie)),LiveOptions(mode='both',format='jpg'),destination,threading.Event(),lambda p:None)
    assert len(outputs)==2
    assert {p.stem for p in outputs}=={'photo'}
    assert next(p for p in outputs if p.suffix=='.mov').read_bytes()==movie.read_bytes()
    assert probe(next(p for p in outputs if p.suffix=='.jpg')).width==100


def test_preflight_adaptation_requires_explicit_confirmation(tmp_path):
    from mediaforge.preflight import inspect_request,apply_suggestions
    from mediaforge.workflow import make_request
    from mediaforge.models import Job,ImageOptions,LiveOptions,MediaInfo
    path=tmp_path/'animation.livp'
    job=Job(path,info=MediaInfo(path,'live',1000,4000,3000,duration=4,fps=30))
    request=make_request([job],{'live':LiveOptions(mode='animation',format='gif',image=ImageOptions(format='gif'))})
    findings=inspect_request(request,threading.Event(),inspect_media=False)
    assert findings and findings[0].suggested
    assert request.items[0].parameters.image.width==0
    adapted=apply_suggestions(request,findings)
    params=adapted.items[0].parameters
    assert max(params.image.width,params.image.height)<=720 and params.animation_fps<=15


def test_png_target_preflight_explains_lossless(tmp_path):
    from mediaforge.preflight import inspect_request
    from mediaforge.workflow import make_request
    from mediaforge.models import Job,ImageOptions
    from mediaforge.probe import probe
    path=tmp_path/'transparent.png'
    Image.effect_noise((100,80),40).convert('RGBA').save(path)
    job=Job(path,info=probe(path))
    findings=inspect_request(make_request([job],{'image':ImageOptions(format='png',target_bytes=200)}),threading.Event(),inspect_media=False)
    assert any('无损' in f.message and f.suggested for f in findings)


def test_equivalent_animation_frame_merge_is_valid(tmp_path):
    from mediaforge.images import process_image
    from mediaforge.models import ImageOptions
    from mediaforge.probe import probe
    a,b=Image.new('RGB',(40,30),'red'),Image.new('RGB',(40,30),'blue')
    source=tmp_path/'input.png'
    a.save(source,format='PNG',save_all=True,append_images=[b,b.copy()],duration=[100,100,200],loop=0,disposal=2)
    output=tmp_path/'output.webp'
    process_image(probe(source),ImageOptions(format='webp',lossless=True),output,threading.Event(),lambda p:None)
    with Image.open(output) as im:
        duration=0
        for i in range(im.n_frames):
            im.seek(i); im.load(); duration+=im.info['duration']
        assert duration==400 and im.info['loop']==0


def test_pet_progress_uses_current_batch_not_history(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from mediaforge.models import Job,ImageOptions
    from mediaforge.workflow import make_request
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    controller.window.jobs['image'].append(Job(tmp_path/'old.png',status='完成',progress=100))
    current=Job(tmp_path/'new.png',status='处理中',progress=35)
    request=make_request([current],{'image':ImageOptions()})
    class Worker:
        jobs=[current]
        def cancel(self,*args): pass
        def isRunning(self): return False
    controller.active_worker=Worker()
    controller.pet.reduced=True
    controller.pet.update_progress()
    assert controller.pet.progress_card.bar.value()==35
    assert '1 / 1' in controller.pet.progress_card.label.text()
    controller.active_worker=None
    controller.request_exit()


def test_pixel_pet_asset_mask(qt_app,tmp_path):
    from mediaforge.controller import AppController
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    assert len(controller.pet.frames)==len(controller.pet.frame_anchors)
    assert not controller.pet.mask().contains(controller.pet.rect().topLeft())
    controller.request_exit()


def test_combined_suggestions_do_not_restore_original_animation_size(tmp_path):
    from mediaforge.models import Job,LiveOptions,ImageOptions,MediaInfo
    from mediaforge.workflow import make_request
    from mediaforge.preflight import inspect_request,apply_suggestions
    path=tmp_path/'live.livp'
    options=LiveOptions(mode='animation',format='gif',target_bytes=1_000_000,animation_fps=30,image=ImageOptions(format='gif',width=1920,height=1080))
    request=make_request([Job(path,info=MediaInfo(path,'live',100,1920,1080,duration=10,fps=30))],{'live':options})
    findings=inspect_request(request,threading.Event(),inspect_media=False)
    adapted=apply_suggestions(request,findings).items[0].parameters
    assert max(adapted.image.width,adapted.image.height)<=720
    assert adapted.animation_fps==15 and adapted.image.auto_resize


def test_cancel_during_preflight_never_starts_conversion(qt_app,tmp_path,monkeypatch):
    import time
    import mediaforge.preflight as module
    from mediaforge.controller import AppController
    from mediaforge.models import Job,ImageOptions
    from mediaforge.workflow import make_request
    def slow(request,cancel,inspect_media=True):
        time.sleep(.2)
        return []
    monkeypatch.setattr(module,'inspect_request',slow)
    path=tmp_path/'source.png'
    Image.new('RGB',(30,30),'red').save(path)
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    controller.submit_request(make_request([Job(path)],{'image':ImageOptions()},'结果'))
    controller.cancel_all()
    for _ in range(30):
        QTest.qWait(20); time.sleep(.002)
    assert not controller.active_worker and not (tmp_path/'结果').exists()
    controller.request_exit()


def test_corrupted_visible_animation_frame_is_rejected(tmp_path,monkeypatch):
    from mediaforge.images import process_image
    from mediaforge.models import ImageOptions
    from mediaforge.probe import probe
    source=tmp_path/'source.png'
    a,b=Image.new('RGBA',(30,30),'red'),Image.new('RGBA',(30,30),'blue')
    a.save(source,save_all=True,append_images=[b],duration=[100,200],loop=0)
    save=Image.Image.save
    def corrupted(self,*args,**kwargs):
        if kwargs.get('save_all'):
            self=Image.new('RGBA',self.size,'green')
        return save(self,*args,**kwargs)
    monkeypatch.setattr(Image.Image,'save',corrupted)
    with pytest.raises(ValueError,match='画面'):
        process_image(probe(source),ImageOptions(format='apng'),tmp_path/'out.png',threading.Event(),lambda p:None)
    assert not (tmp_path/'out.png').exists()


def test_return_from_pet_preflight_preserves_folder_name(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from mediaforge.models import Job,ImageOptions
    from mediaforge.workflow import make_request
    path=tmp_path/'source.png'
    Image.new('RGB',(30,30),'red').save(path)
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    controller.submit_request(make_request([Job(path)],{'image':ImageOptions(target_bytes=100)},'我选的名字',origin='pet'))
    controller.checks[0].back_to_options()
    assert controller.return_dialogs[-1].name.text()=='我选的名字'
    controller.request_exit()
    QTest.qWait(150)


@pytest.mark.parametrize('reason',['size','cancel'])
def test_live_both_never_publishes_half_group(tmp_path,reason):
    from mediaforge.live import process_live
    from mediaforge.models import Job,LiveOptions
    from mediaforge.paths import tool_path
    from mediaforge.probe import run_tool
    from mediaforge.images import Cancelled
    photo,movie=tmp_path/'photo.jpg',tmp_path/'movie.mov'
    Image.new('RGB',(60,40),'red').save(photo)
    result=run_tool([tool_path('ffmpeg'),'-v','error','-y','-f','lavfi','-i','color=red:s=60x40:d=0.3','-c:v','libx264',str(movie)])
    assert result.returncode==0
    destination=tmp_path/'result'
    destination.mkdir()
    cancel=threading.Event()
    options=LiveOptions(mode='both',format='jpg',target_bytes=movie.stat().st_size-1 if reason=='size' else 0)
    def progress(value):
        if reason=='cancel': cancel.set()
    with pytest.raises(ValueError if reason=='size' else Cancelled):
        process_live(Job(photo,inputs=(photo,movie)),options,destination,cancel,progress)
    assert not list(destination.iterdir()) and not list(tmp_path.glob('*.partial'))
    assert photo.exists() and movie.exists()


def test_native_wizard_small_window_mixed_cards(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    window=MainWindow(settings_path=tmp_path/'settings.json')
    window.hardware_enabled=False
    window.resize(680,500)
    window.show()
    for kind,extension in [('image','png'),('video','mp4'),('live','livp')]:
        window.jobs[kind].append(Job(tmp_path/('很长的中文文件名称'*6+'.'+extension)))
    page=window.simple_page
    for step in (0,1,2,1,0):
        page.set_step(step)
        QTest.qWait(25)
        assert window.rect().contains(page.begin.mapTo(window,page.begin.rect().center()))
        assert page.form_scroll.isVisible()==(step==1)
        assert page.list.isVisible()==(step!=1)
    assert page.list.count()==3
    window.close()


def test_folded_advanced_preserves_visible_size_summary(qt_app,tmp_path):
    from mediaforge.simple import QuickDialog
    from mediaforge.models import Job
    dialog=QuickDialog([Job(tmp_path/'source.png')],{})
    dialog.form.store.edit('image','target_bytes',2000)
    assert not dialog.form.more.isChecked()
    assert '体积上限' in dialog.form.rows['image'][6].text()
    dialog.form.more.setChecked(True)
    dialog.form.more.setChecked(False)
    assert dialog.form.options()['image'].target_bytes==2000
    dialog.form.store.edit('image','target_bytes',0)
    assert dialog.form.options()['image'].target_bytes==0
    dialog.close()


def test_closed_pet_card_is_released_before_next_import(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from mediaforge.models import Job
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    controller.incoming.append([Job(tmp_path/'one.png')])
    controller.open_next_dialog()
    previous=controller.dialog
    previous.close()
    assert controller.dialog is None
    controller.incoming.append([Job(tmp_path/'two.png')])
    controller.open_next_dialog()
    latest=controller.dialog
    QTest.qWait(50)
    assert controller.dialog is latest and latest.jobs[0].path.name=='two.png'
    controller.request_exit()
