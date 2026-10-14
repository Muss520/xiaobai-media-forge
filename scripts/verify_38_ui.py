"""Windows-native companion/play/settings lifecycle and actual bounds acceptance."""
import sys,json,tempfile,time
from pathlib import Path
from dataclasses import asdict
from project_layout import DEV,RUN,DOCS,VERSION
from PySide6.QtWidgets import QApplication,QPushButton
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPoint,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDragLeaveEvent
from mediaforge.controller import AppController

app=QApplication([]);errors=[]
def exception(typ,error,trace):errors.append(str(error));sys.__excepthook__(typ,error,trace)
sys.excepthook=exception
with tempfile.TemporaryDirectory(dir=RUN/'temp',prefix='native38-') as directory:
    c=AppController(app,Path(directory)/'settings.json',quit_application=False);w=c.window;w.hardware_enabled=False;c.preferences['sounds']=False;pet=c.pet
    try:
        w.show();pet.move(200,200);pet.set_state('idle');c.set_motion(False)
        dpi=round(pet.devicePixelRatioF()*100)
        for scale in range(2,7):
            foot=pet.foot_position();pet.set_scale(scale);assert pet.foot_position()==foot
            for sequence in pet.actions.values():
                for index in sequence:
                    image=pet.frames[index].toImage()
                    assert not image.pixelColor(0,0).alpha()
                    assert not any(image.pixelColor(x,image.height()-1).alpha() for x in range(image.width()))
        pet.set_scale(3);pet.set_state('idle');pet.idle_next_action='wash';pet.tick();assert pet.action=='wash'
        for _ in pet.actions['wash']:pet.tick()
        assert pet.idle_waiting and 10000<=pet.timer.interval()<=25000
        for name in ('rub','snack','joy','shy','meow'):
            pet.interact(name);assert pet.state=='idle';pet.unblink()
        pet.last_hover=0;pet.hover_reaction();assert pet.action in {'look','ears'}
        point=QPoint(pet.width()//2,pet.height()//2);activations=[];pet.activated.connect(lambda:activations.append(True))
        c.set_motion(True);pet.set_state('idle')
        QTest.mouseClick(pet,Qt.LeftButton,pos=point);QTest.qWait(app.doubleClickInterval()+30);assert pet.action=='pet'
        pet.set_state('idle');QTest.mouseDClick(pet,Qt.LeftButton,pos=point);QTest.mouseRelease(pet,Qt.LeftButton,pos=point)
        QTest.qWait(app.doubleClickInterval()+30);assert len(activations)==1 and pet.action=='idle'
        snapshots={kind:asdict(panel.snapshot()) for kind,panel in w.panels.items()}
        c.show_settings();settings=c.settings_dialog;matrix=[]
        for font in (12,16,20):
            w.ui_preferences['font_points']=font;c.apply_appearance();QTest.qWait(80)
            available=pet.screen().availableGeometry();settings.resize(480,min(800,available.height()-32))
            for page_id in ('appearance','pet','sound','usage','author'):
                settings.tabs.setCurrentIndex(settings.page_index(page_id));QTest.qWait(35)
                scroll=settings.tabs.currentWidget()
                assert scroll.widget().width()<=scroll.viewport().width(),('settings overflow',font,page_id,scroll.widget().width(),scroll.viewport().width())
                assert not scroll.horizontalScrollBar().isVisible()
                assert settings.reset_button.isVisible()==(page_id!='author')
            settings.tabs.setCurrentIndex(settings.page_index('sound'));QTest.qWait(40)
            settings.grab().save(str(DOCS/f'3.8_声音设置_DPI{dpi}_{font}pt.png'))
            for reduced in (False,True):
                c.set_motion(reduced)
                for mode in ('wand','ball'):
                    c.open_play(mode);dialog=c.play_dialog;assert dialog and dialog.isVisible();dialog.start();QTest.qWait(40)
                    for button in (dialog.start_button,dialog.pause_button,dialog.end_button):
                        assert button.height()>=button.fontMetrics().height()+6,('game button height',font,mode)
                        assert button.width()>=button.fontMetrics().horizontalAdvance(button.text())+16,('game button width',font,mode)
                    assert dialog.canvas.height()>=170
                    assert dialog.help.height()>=dialog.help.heightForWidth(dialog.help.width()),('game instructions clipped',font,mode)
                    assert dialog.status.height()>=dialog.status.fontMetrics().height()*2,('game status clipped',font,mode)
                    dialog.pause();assert not dialog.timer.isActive();dialog.pause();assert dialog.timer.isActive()
                    if mode=='wand':
                        p=dialog.canvas.target_point().toPoint();QTest.mouseClick(dialog.canvas,Qt.LeftButton,pos=p);assert dialog.session.score==1
                    else:
                        dialog.play_click();dialog.session.advance(.75);dialog.play_click();assert dialog.session.score==1
                        dialog.session.elapsed=29.9;dialog.last_tick=time.monotonic()-.2;dialog.tick();assert dialog.session.finished and not dialog.timer.isActive()
                    dialog.grab().save(str(DOCS/(f'3.8_游乐场_{mode}_DPI{dpi}_{font}pt_'+('静态' if reduced else '动画')+'.png')))
                    dialog.close();app.processEvents();assert c.play_dialog is None
                    matrix.append({'font':font,'mode':mode,'reduced':reduced,'passed':True})
        assert snapshots=={kind:asdict(panel.snapshot()) for kind,panel in w.panels.items()}
        w.ui_preferences['font_points']=12;c.apply_appearance();settings.close();app.processEvents();c.open_play('wand');c.play_dialog.start()
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(Path(directory)/'原文件.jpg'))])
        event=QDragEnterEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        pet.dragEnterEvent(event);assert event.isAccepted() and c.play_dialog is None and pet.mask_frozen
        pet.dragLeaveEvent(QDragLeaveEvent());assert not pet.mask_frozen
        c.open_play('ball');pet.set_state('working');assert c.play_dialog is None
        pet.interact('snack');assert pet.state=='working' and pet.action=='working'
        pet.set_state('idle');pet.hide();assert not pet.timer.isActive();pet.show()
        assert not errors,errors
        report={'passed':True,'version':VERSION,'dpi':dpi,'matrix':matrix,'settings_pages':5,'all_frame_scales':True,
            'click_double_click':True,'drag_preempts_game':True,'busy_interaction_blocked':True,'media_parameters_unchanged':True,'errors':errors}
        (DOCS/f'3.8_宠物游玩原生验收_DPI{dpi}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:c.request_exit();app.processEvents()
