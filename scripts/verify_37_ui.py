"""Native support cards, actual rendered QR codes, settings and branding checks."""
import sys,json,tempfile,hashlib
from pathlib import Path
from project_layout import DEV,RUN,DOCS,VERSION,NAME
PREFIX=VERSION.rsplit('.',1)[0]
from PySide6.QtWidgets import QApplication,QPushButton,QScrollArea,QLabel
from PySide6.QtTest import QTest
from PySide6.QtCore import QPoint
from PySide6.QtGui import QImage
from PIL import Image
import zxingcpp
from mediaforge.controller import AppController

app=QApplication([]);errors=[]
def exception(typ,error,trace):errors.append(str(error));sys.__excepthook__(typ,error,trace)
sys.excepthook=exception
manifest=json.loads((DEV/'assets/support/manifest.json').read_text(encoding='utf-8'))

def qr_payload(pixmap):
    image=pixmap.toImage().convertToFormat(QImage.Format_RGBA8888)
    source=Image.frombytes('RGBA',(image.width(),image.height()),image.bits().tobytes(),'raw','RGBA',image.bytesPerLine())
    return {hashlib.sha256(value.bytes).hexdigest() for value in zxingcpp.read_barcodes(source)}

with tempfile.TemporaryDirectory(dir=RUN/'temp',prefix='native37-') as folder:
    c=AppController(app,Path(folder)/'settings.json',quit_application=False);w=c.window;w.hardware_enabled=False;c.preferences['sounds']=False
    try:
        w.show();w.reduce_motion.setChecked(True)
        assert NAME in w.windowTitle()
        c.show_settings();s=c.settings_dialog;s.tabs.setCurrentIndex(s.page_index('author'))
        dpi=round(w.devicePixelRatioF()*100);checks=[]
        for font in (12,16,20):
            w.ui_preferences['font_points']=font;c.apply_appearance();QTest.qWait(120)
            for width in (480,1000):
                available=s.screen().availableGeometry();s.resize(min(width,available.width()-24),min(820,available.height()-24));QTest.qWait(100)
                scroll=s.tabs.currentWidget()
                assert not s.reset_button.isVisible()
                assert not scroll.horizontalScrollBar().isVisible()
                assert s.author_page.width()<=scroll.viewport().width(),('author overflow',font,width)
                for label in s.author_page.findChildren(QLabel):
                    if label.text() and not label.wordWrap():
                        assert label.width()>=label.fontMetrics().horizontalAdvance(label.text()),('author text clipped',font,width,label.text(),label.width())
                for index,card in enumerate(s.author_page.cards):
                    scroll.ensureWidgetVisible(card.preview);QTest.qWait(60)
                    code=card.preview
                    top=code.mapTo(scroll.viewport(),QPoint(0,0));bottom=code.mapTo(scroll.viewport(),QPoint(code.width(),code.height()))
                    assert top.x()>=0 and bottom.x()<=scroll.viewport().width(),('code horizontal bounds',font,width,index)
                    assert top.y()>=0 and bottom.y()<=scroll.viewport().height(),('code vertical bounds',font,width,index,top.y(),bottom.y(),scroll.viewport().height())
                    expected=manifest['codes'][index]['payload_sha256']
                    assert expected in qr_payload(s.grab()),('actual window QR unreadable',font,width,index)
                s.grab().save(str(DOCS/f'{PREFIX}_作者页_DPI{dpi}_{font}pt_{width}.png'))
                checks.append({'font':font,'width':width,'columns':s.author_page.columns,'screen_qr_decoded':True})
            # Other setting pages keep every control inside their scrolling viewport.
            for page in range(s.tabs.count()-1):
                s.tabs.setCurrentIndex(page);QTest.qWait(60)
                scroll=s.tabs.currentWidget()
                assert not scroll.horizontalScrollBar().isVisible(),('settings horizontal scroll',font,page)
            s.tabs.setCurrentIndex(s.page_index('author'))
        w.ui_preferences['font_points']=12;c.apply_appearance();QTest.qWait(80)
        card=s.author_page.cards[0];card.open_large();QTest.qWait(80)
        assert manifest['codes'][0]['payload_sha256'] in qr_payload(card.dialog.grab())
        card.dialog.grab().save(str(DOCS/f'{PREFIX}_二维码放大_DPI{dpi}.png'))
        card.dialog.close();app.processEvents()
        assert not errors,errors
        report={'passed':True,'version':VERSION,'dpi':dpi,'matrix':checks,'enlarged_code_decodes':True,'errors':errors,
                'phone_payment_app_scan':'not physically tested'}
        (DOCS/f'{PREFIX}_作者页原生验收_DPI{dpi}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report))
    finally:c.request_exit();app.processEvents()
