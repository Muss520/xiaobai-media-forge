from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE
"""Native input distinctions for Xiaobai, isolated from the user's settings."""
import sys,json,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt,QPoint,QMimeData,QUrl
from PySide6.QtGui import QDragEnterEvent,QDragLeaveEvent
from mediaforge.controller import AppController
app=QApplication([])
with tempfile.TemporaryDirectory(dir=RUN/'temp',prefix='pet-input34-') as directory:
    c=AppController(app,Path(directory)/'settings.json',quit_application=False); c.window.hardware_enabled=False; pet=c.pet
    try:
        pet.show(); pet.set_state('idle'); c.set_motion(True)
        point=QPoint(pet.width()//2,pet.height()//2); activations=[]; pet.activated.connect(lambda:activations.append(True))
        QTest.mouseClick(pet,Qt.LeftButton,pos=point)
        assert pet.action=='idle'
        QTest.qWait(app.doubleClickInterval()+30)
        assert pet.action=='pet'
        pet.set_state('idle')
        QTest.mouseClick(pet,Qt.LeftButton,pos=point)
        QTest.mouseDClick(pet,Qt.LeftButton,pos=point); QTest.mouseRelease(pet,Qt.LeftButton,pos=point)
        QTest.qWait(app.doubleClickInterval()+30)
        assert len(activations)==1 and pet.action=='idle'
        pet.set_state('working'); QTest.mouseClick(pet,Qt.LeftButton,pos=point); QTest.qWait(app.doubleClickInterval()+30)
        assert pet.action=='working'
        mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(Path(directory)/'test.jpg'))])
        event=QDragEnterEvent(point,Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
        pet.set_state('idle'); oldmask=pet.mask(); pet.dragEnterEvent(event)
        pet.tick(); assert event.isAccepted() and pet.mask_frozen and pet.mask()==oldmask
        pet.dragLeaveEvent(QDragLeaveEvent()); assert not pet.mask_frozen
        result={'passed':True,'single_click_delayed':True,'double_click_not_petting':True,'busy_click_keeps_working':True,'drag_enter_mask_frozen':True}
        (root/'docs/3.4_小白原生输入.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(result))
    finally:c.request_exit()
