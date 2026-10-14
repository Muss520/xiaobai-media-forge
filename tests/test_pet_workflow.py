import threading
import time
from dataclasses import replace
from pathlib import Path
from PIL import Image
from PySide6.QtTest import QTest


def test_request_groups_original_directories_and_name_validation(tmp_path):
    from mediaforge.workflow import make_request, validate_folder_name
    from mediaforge.models import Job, ImageOptions
    a, b = tmp_path / '甲', tmp_path / '乙'
    a.mkdir(); b.mkdir()
    jobs = [Job(a / 'one.png'), Job(a / 'two.png'), Job(b / 'one.png')]
    request = make_request(jobs, {'image': ImageOptions()}, folder_name='转换结果_测试')
    assert request.items[0].folder == request.items[1].folder
    assert request.items[2].folder.parent == b
    assert not request.items[0].folder.exists()
    for bad in ('../outside', 'CON', 'a/b', 'a\\b', 'name.', 'NUL.txt'):
        try:
            validate_folder_name(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(bad)


def test_mixed_request_failure_continues_and_original_unchanged(qt_app, tmp_path):
    from mediaforge.workflow import make_request
    from mediaforge.models import Job, ImageOptions
    from mediaforge.queue import BatchWorker
    good = tmp_path / '中文 图.png'
    Image.new('RGB', (80, 50), 'red').save(good)
    before = good.read_bytes()
    jobs = [Job(tmp_path / 'bad.png'), Job(good)]
    request = make_request(jobs, {'image': ImageOptions()}, folder_name='结果')
    worker = BatchWorker.from_request(request)
    worker.run()
    assert jobs[0].status == '失败'
    assert jobs[1].status == '完成'
    assert jobs[1].output.parent == tmp_path / '结果'
    assert good.read_bytes() == before


def test_controller_close_hides_and_explicit_exit(qt_app, tmp_path):
    from mediaforge.controller import AppController
    controller = AppController(qt_app, settings_path=tmp_path / 'settings.json', quit_application=False)
    controller.window.hardware_enabled = False
    controller.window.show()
    assert controller.pet.isVisible()
    controller.window.close()
    assert not controller.window.isVisible()
    assert not controller.exiting
    controller.show_window()
    assert controller.window.isVisible()
    controller.request_exit()
    QTest.qWait(100)
    assert controller.exiting
    assert not controller.pet.isVisible()


def test_separate_simple_layout_and_shared_options(qt_app, tmp_path):
    from mediaforge.window import MainWindow
    window = MainWindow(settings_path=tmp_path / 'settings.json')
    window.hardware_enabled = False
    assert window.view_stack.currentWidget() is window.simple_page
    window.set_ui_mode('advanced', False)
    window.panels['image'].quality.setValue(72)
    window.set_ui_mode('simple', False)
    QTest.qWait(25)
    assert window.parameter_store.snapshot('image').quality == 72
    assert window.view_stack.currentWidget() is window.simple_page
    assert window.panels['image'].snapshot().quality == 72
    window.close()


def test_pet_drop_confirmation_saves_beside_sources(qt_app, tmp_path):
    from mediaforge.controller import AppController
    from PySide6.QtCore import QMimeData, QUrl, Qt
    from PySide6.QtGui import QDropEvent
    controller = AppController(qt_app,settings_path=tmp_path / 'settings.json',quit_application=False)
    controller.window.hardware_enabled = False
    sources = []
    for name in ('甲','乙'):
        folder = tmp_path / name
        folder.mkdir()
        path = folder / '照片.png'
        Image.new('RGB',(80,60),'blue').save(path)
        sources.append(path)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in sources])
    controller.pet.dropEvent(QDropEvent(controller.pet.rect().center(),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier))
    for _ in range(150):
        QTest.qWait(20)
        if controller.dialog:
            break
    assert controller.dialog
    assert not any(path.parent.joinpath('转换结果').exists() for path in sources)
    controller.dialog.name.setText('转换结果')
    controller.dialog.confirm.click()
    for _ in range(600):
        QTest.qWait(20)
        time.sleep(.003)
        if not controller.active_worker and not controller.pending and not controller.checks:
            break
    jobs = controller.window.jobs['image']
    assert len(jobs)==2 and all(j.status=='完成' for j in jobs)
    assert {j.output.parent for j in jobs} == {p.parent/'转换结果' for p in sources}
    controller.window.close()
    assert controller.pet.isVisible()
    controller.request_exit()
    QTest.qWait(100)


def test_single_instance_reuses_primary(qt_app,tmp_path):
    from mediaforge.controller import SingleInstance
    primary = SingleInstance(tmp_path)
    count = []
    primary.activated.connect(lambda: count.append(True))
    secondary = SingleInstance(tmp_path)
    QTest.qWait(50)
    assert primary.primary and not secondary.primary and count
    primary.close()


def test_advanced_cancel_clears_pending_and_shutdown_blocks_new_work(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from mediaforge.workflow import make_request
    from mediaforge.models import Job,ImageOptions
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    job=Job(tmp_path/'queued.png',status='排队中')
    controller.pending.append(make_request([job],{'image':ImageOptions()}))
    controller.window.busy=True
    controller.window.refresh_controls()
    controller.window.cancel_all.click()
    assert not controller.pending and job.status=='已取消'
    controller.window.busy=False
    controller.request_exit()
    assert controller.window.closing


def test_sibling_output_ignores_unused_custom_directory(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    window=MainWindow(settings_path=tmp_path/'settings.json')
    window.hardware_enabled=False
    window.tabs.setCurrentIndex(1)
    window.jobs['image'].append(Job(tmp_path/'source.png'))
    window.sibling_output.setChecked(True)
    window.output.setText('')
    requests=[]
    window.execute_request=requests.append
    window.start_batch()
    assert len(requests)==1 and requests[0].items[0].folder.parent==tmp_path
    window.close()


def test_animated_static_requires_explicit_first_frame(qt_app,tmp_path):
    import pytest
    from mediaforge.simple import QuickDialog
    from mediaforge.models import Job
    from mediaforge.probe import probe
    path=tmp_path/'animated.gif'
    Image.new('RGB',(20,20),'red').save(path,save_all=True,append_images=[Image.new('RGB',(20,20),'blue')],duration=100)
    dialog=QuickDialog([Job(path,info=probe(path))],{})
    with pytest.raises(ValueError,match='首帧'):
        dialog.form.options()
    dialog.form.first_frame.setChecked(True)
    assert dialog.form.options()['image'].animation=='first'
    dialog.close()


def test_pet_failure_retry_keeps_its_original_parameters(qt_app,tmp_path):
    from PySide6.QtWidgets import QPushButton
    from mediaforge.controller import AppController
    from mediaforge.workflow import make_request
    from mediaforge.models import Job,ImageOptions
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    job=Job(tmp_path/'bad.png',status='失败',error='素材损坏')
    request=make_request([job],{'image':ImageOptions(quality=61)},origin='pet')
    controller.window.panels['image'].quality.setValue(99)
    captured=[]
    controller.enqueue=captured.append
    controller.show_result(request,0,1,0)
    button=next(b for b in controller.feedback.findChildren(QPushButton) if b.text()=='按本次需求重试')
    button.click()
    assert captured[0].items[0].parameters.quality==61
    controller.request_exit()
    QTest.qWait(50)


def test_queued_batches_snapshot_and_repeated_folder_names(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from mediaforge.workflow import make_request
    from mediaforge.models import Job,ImageOptions
    controller=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    controller.window.hardware_enabled=False
    path=tmp_path/'source.png'
    Image.effect_noise((500,400),40).convert('RGB').save(path)
    first,second=Job(path),Job(path)
    one=make_request([first],{'image':ImageOptions(quality=80)},'结果')
    two=make_request([second],{'image':ImageOptions(format='webp',quality=60)},'结果')
    controller.enqueue(one)
    controller.enqueue(two)
    controller.window.set_ui_mode('advanced',False)
    controller.window.set_ui_mode('simple',False)
    for _ in range(600):
        QTest.qWait(20)
        time.sleep(.003)
        if not controller.active_worker and not controller.pending:
            break
    assert first.status==second.status=='完成'
    assert first.output.parent != second.output.parent
    assert first.parameters.quality==80 and second.parameters.format=='webp'
    controller.request_exit()
    QTest.qWait(100)


def test_delayed_ui_progress_does_not_overwrite_worker_completion(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    window=MainWindow(settings_path=tmp_path/'settings.json')
    window.hardware_enabled=False
    path=tmp_path/'photo.png'
    Image.new('RGB',(10,10)).save(path)
    job=Job(path,status='完成',progress=100)
    window.jobs['image'].append(job)
    window.job_updated(job.id,'处理中',75,'',None,0)
    assert job.status=='完成' and job.progress==100
    window.close()
