from project_layout import DEV,PROJECT,RUN,DOCS,PORTABLE,RELEASE
"""Native Windows 3.3 UI checks; writes only isolated project test artifacts."""
import sys,json,tempfile,time,ctypes,logging
logging.basicConfig(level=logging.INFO)
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root/'src'))
from PySide6.QtWidgets import QApplication,QPushButton,QScrollArea
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from PIL import Image
from mediaforge.controller import AppController

app=QApplication([])
with tempfile.TemporaryDirectory(prefix='ui33-',dir=RUN/'temp') as folder:
    folder=Path(folder); c=AppController(app,folder/'settings.json',quit_application=False)
    c.window.hardware_enabled=False; c.preferences['sounds']=False
    errors=[]
    original_hook=sys.excepthook
    def exception_hook(*args):
        errors.append(str(args[1])); original_hook(*args)
    sys.excepthook=exception_hook
    try:
        w=c.window; w.show(); QTest.qWait(100)
        for i in range(15):
            w.set_ui_mode(('simple','advanced','information')[i%3]); w.tabs.setCurrentIndex(i%3); QTest.qWait(20)
        w.reduce_motion.setChecked(True)
        for kind in range(3):
            w.set_ui_mode('advanced',False); w.tabs.setCurrentIndex(kind); QTest.qWait(40)
            button=w.findChild(QPushButton,'add_'+w.kind)
            assert button.isVisible() and button.graphicsEffect() is None
        c.show_settings(); settings=c.settings_dialog
        for size in (12,20,14):settings.font_points.setValue(size); QTest.qWait(40)
        settings.spacing.setValue(24); settings.navigation_width.setValue(220); QTest.qWait(40)
        assert w.ui_preferences['font_points']==14 and w.tabs.tabBar().preferred_width==220
        settings.reset_page(0); settings.close()
        photo=folder/'拍摄信息 中文.jpg'; exif=Image.Exif(); exif[315]='Author'; exif[272]='Camera'; exif[274]=6
        Image.new('RGB',(60,40),'blue').save(photo,exif=exif)
        w.set_ui_mode('information',False); w.information_page.add_paths([photo])
        deadline=time.monotonic()+30
        while w.information_page.loaders and time.monotonic()<deadline:
            app.processEvents(); time.sleep(.02)
        page=w.information_page
        print('Information import:',[(j.status,j.error) for j in page.jobs],list(page.records),[t.isRunning() for t in page.loaders],page.raw_table.rowCount(),flush=True)
        assert page.records and page.raw_table.rowCount()>10
        page.record_edit(0,'IFD0:Artist','新作者')
        assert '新作者' in page.pending.text()
        page.reset_edits(); page.export_copy()
        while (c.active_worker or c.pending) and time.monotonic()<deadline:
            app.processEvents(); time.sleep(.02)
        assert page.last_output_job.status=='完成',page.last_output_job.error
        assert page.last_output_job.output.read_bytes()==photo.read_bytes()
        page.refresh_status(); app.processEvents()
        w.grab().save(str(DOCS/f'信息模式_DPI{round(w.devicePixelRatioF()*100)}.png'))
        w.set_ui_mode('simple',False); w.resize(700,540); QTest.qWait(80)
        assert w.simple_button.isVisible() and w.information_button.isVisible()
        c.pet.set_state('complete'); c.pet.settle_state(); assert c.pet.state=='idle'
        mask=c.pet.mask(); c.pet.mask_frozen=True; c.pet.set_state('receiving'); c.pet.tick(); assert c.pet.mask()==mask; c.pet.mask_frozen=False; c.pet.apply_mask()
        c.pet.ensure_topmost()
        assert not errors,errors
        result={'passed':True,'dpi':w.devicePixelRatioF(),'modes':True,'settings_ranges':True,'information_background_read_and_export':True,'stable_pet_mask':True,'errors':errors}
        report=DOCS/f'界面验收_DPI{round(w.devicePixelRatioF()*100)}.json'; report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result))
    finally:
        c.request_exit()
        for _ in range(100):
            QTest.qWait(20)
            if not any(t.isRunning() for t in [*c.loaders,*w.information_page.loaders]):break
