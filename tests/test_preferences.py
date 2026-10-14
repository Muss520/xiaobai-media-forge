import json
import sys
import pytest
from PySide6.QtCore import QEvent, QPoint
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton


def test_page_and_button_effects_do_not_nest(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    w=MainWindow(settings_path=tmp_path/'settings.json'); w.hardware_enabled=False
    w.show(); w.set_ui_mode('advanced'); QTest.qWait(210)
    button=w.findChild(QPushButton,'add_video')
    qt_app.sendEvent(button,QEvent(QEvent.Enter)); QTest.qWait(200)
    assert w.advanced_page.graphicsEffect() is None
    assert button.graphicsEffect() is None
    assert button.isVisible() and button.isEnabled()
    w.close()


def test_settings_singleton_and_persistence(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    c.window.hardware_enabled=False
    try:
        c.show_settings(); first=c.settings_dialog; c.show_settings()
        assert c.settings_dialog is first
        first.density.setCurrentIndex(1); first.text_size.setCurrentIndex(2)
        first.cat_size.setValue(5)
        assert c.pet.scale==5
        data=json.loads((tmp_path/'settings.json').read_text(encoding='utf-8'))
        assert data['ui']['density']=='compact' and data['ui']['text_size']=='large'
        assert data['desktop']['scale']==5
        first.reset_page(0)
        assert c.pet.scale==5
        assert c.window.ui_preferences['density']=='comfortable'
    finally:
        c.request_exit(); QTest.qWait(100)


def test_cat_resize_keeps_foot_and_transparent_mask(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False)
    c.window.hardware_enabled=False
    try:
        c.pet.move(300,200)
        foot=c.pet.foot_position()
        for scale in (2,3,4,5,6):
            c.pet.set_scale(scale)
            assert c.pet.scale==scale and len(c.pet.frames)==len(c.pet.frame_anchors)
            assert abs(c.pet.x()+c.pet.width()//2-foot.x())<=1
            assert c.pet.foot_position().y()==foot.y()
            assert not c.pet.mask().contains(QPoint(0,0))
    finally:
        c.request_exit(); QTest.qWait(100)


def test_optional_number_has_no_redundant_zeroes(qt_app):
    from mediaforge.options import OptionalNumber
    spin=OptionalNumber(); spin.setRange(0,1000000); spin.setDecimals(3)
    spin.setValue(2500)
    assert spin.text()=='2500'
    spin.setValue(2.125)
    assert spin.text()=='2.125'


def test_old_config_migrates_and_preferences_restart(qt_app,tmp_path):
    from mediaforge.controller import AppController
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'version':4,'output':str(tmp_path/'原输出'),'image':{'format':'png','quality':72},'desktop':{'scale':99,'position':[150,150]},'ui':{'text_size':'bad','density':None,'splitters':{'video':'bad'}}}),encoding='utf-8')
    c=AppController(qt_app,settings_path=path,quit_application=False); c.window.hardware_enabled=False
    try:
        assert c.pet.scale==3 and c.window.ui_mode=='simple'
        assert c.window.panels['image'].snapshot().quality==72
        c.window.ui_preferences.update(density='compact',text_size='large')
        c.preferences['scale']=4; c.window.save_settings()
    finally:c.request_exit(); QTest.qWait(100)
    c2=AppController(qt_app,settings_path=path,quit_application=False); c2.window.hardware_enabled=False
    try:
        assert c2.pet.scale==4 and c2.window.ui_mode=='simple'
        assert c2.window.ui_preferences['density']=='compact'
        assert c2.window.panels['image'].snapshot().quality==72
        assert c2.window.output.text()==str(tmp_path/'原输出')
    finally:c2.request_exit(); QTest.qWait(100)


def test_settings_dont_mutate_frozen_batch_and_keep_live_formats(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from mediaforge.models import Job
    from mediaforge.workflow import make_request
    c=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False); c.window.hardware_enabled=False
    try:
        job=Job(tmp_path/'photo.png')
        request=make_request([job],{'image':c.window.panels['image'].snapshot()})
        params=request.items[0].parameters; output=request.items[0].folder
        c.show_settings(); card=c.settings_dialog
        card.output.setText(str(tmp_path/'以后输出')); card.apply_usage()
        card.motion.setChecked(True); card.cat_size.setValue(6)
        fmt,preset,mode,source=card.quick['live']
        mode.setCurrentIndex(mode.findData('both'))
        assert fmt.findData('jpg')>=0 and fmt.findData('livp')==-1
        assert request.items[0].parameters==params and request.items[0].folder==output
        image_before=c.window.panels['image'].snapshot()
        card.reset_page('usage')
        assert c.window.panels['image'].snapshot()==image_before
        assert c.pet.scale==6 and c.window.reduce_motion.isChecked()
    finally:c.request_exit(); QTest.qWait(100)


def test_continuous_switch_hover_disabled_controls_remain_visible(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    w=MainWindow(settings_path=tmp_path/'settings.json'); w.hardware_enabled=False
    w.show()
    for i in range(12):
        w.set_ui_mode('advanced'); w.tabs.setCurrentIndex(i%3)
        for action in ('add','remove','clear','retry'):
            button=w.findChild(QPushButton,action+'_'+w.kind)
            qt_app.sendEvent(button,QEvent(QEvent.Enter)); qt_app.sendEvent(button,QEvent(QEvent.Leave))
            assert button.isVisible() and button.graphicsEffect() is None
        w.set_ui_mode('simple')
    w.set_reduced_motion(True); w.set_ui_mode('advanced'); QTest.qWait(50)
    w.busy=True; w.refresh_controls()
    assert w.findChild(QPushButton,'add_live').isVisible()
    assert not w.findChild(QPushButton,'add_live').isEnabled()
    w.busy=False; w.close()


@pytest.mark.parametrize('destroy_root',[False,True])
def test_hover_target_destroyed_stops_callbacks(qt_app,destroy_root):
    from PySide6.QtWidgets import QWidget
    from shiboken6 import delete,isValid
    from mediaforge.motion import Motion
    root=QWidget(); motion=Motion(root); button=QPushButton('关闭测试',root)
    motion.watch_buttons(root)
    errors=[]; previous=sys.excepthook
    sys.excepthook=lambda *args:errors.append(args)
    try:
        qt_app.sendEvent(button,QEvent(QEvent.Enter)); delete(root if destroy_root else button); QTest.qWait(220)
        assert not errors
        assert not motion.animations
    finally:
        sys.excepthook=previous
        if isValid(root):root.close()


@pytest.mark.parametrize('ui',[None,{'presets':False,'reduce_motion':'invalid'}])
def test_invalid_ui_does_not_discard_media_parameters(qt_app,tmp_path,ui):
    from mediaforge.window import MainWindow
    path=tmp_path/'settings.json'
    path.write_text(json.dumps({'ui':ui,'image':{'quality':72,'format':'png'}}),encoding='utf-8')
    window=MainWindow(settings_path=path); window.hardware_enabled=False
    assert window.panels['image'].snapshot().quality==72
    assert not window.reduce_motion.isChecked()
    window.close()


def test_invalid_pet_quick_preferences_recover(qt_app):
    from mediaforge.preferences import normalize_desktop
    from mediaforge.simple import QuickDialog
    prefs=normalize_desktop({'quick':{'image':None,'live':{'mode':'bad','format':'bad','preset':'bad'}}})
    dialog=QuickDialog([],prefs['quick'])
    assert dialog.form.store.panels['live'].snapshot().mode=='both'
    assert dialog.form.store.panels['live'].snapshot().format=='png'
    dialog.close()


def test_settings_reflect_other_entries_without_overwriting(qt_app,tmp_path):
    from mediaforge.controller import AppController
    c=AppController(qt_app,settings_path=tmp_path/'settings.json',quit_application=False); c.window.hardware_enabled=False
    try:
        c.show_settings(); card=c.settings_dialog
        c.window.reduce_motion.setChecked(True)
        c.window.output.setText(str(tmp_path/'新目录'))
        c.window.sibling_output.setChecked(True)
        assert card.motion.isChecked()
        assert card.output.text()==str(tmp_path/'新目录') and card.sibling.isChecked()
        c.preferences['quick']['image']['format']='png'
        card.close(); QTest.qWait(30)
        assert c.preferences['quick']['image']['format']=='png'
        assert c.window.output.text()==str(tmp_path/'新目录')
    finally:c.request_exit(); QTest.qWait(100)
