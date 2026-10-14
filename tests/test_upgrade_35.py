from pathlib import Path
import json
import pytest


def test_missing_date_not_filled_from_clock(qt_app):
    from mediaforge.metadata_editor import MetadataEditor
    from mediaforge.metadata_fields import FieldTarget
    editor=MetadataEditor(FieldTarget('拍摄时间','Keys:CreationDate','native','date'),None)
    try:assert editor.serialized()==''
    finally:editor.close()


def test_information_has_easy_tab_and_export_label(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    w=MainWindow(tmp_path/'settings.json'); w.hardware_enabled=False
    try:
        page=w.information_page
        assert [page.tabs.tabText(i) for i in range(page.tabs.count())]==['常用信息','小白更改信息','完整标签']
        assert page.export.text()=='导出修改版'
    finally:w.close()


def test_expanded_reuses_surface_and_restores(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    w=MainWindow(tmp_path/'settings.json'); w.hardware_enabled=False
    try:
        page=w.information_page; w.set_ui_mode('information',False); w.show()
        page.tabs.setCurrentIndex(1); page.open_expanded(); dialog=page.expanded_dialog
        assert dialog.isVisible() and dialog.isAncestorOf(page.surface)
        page.open_expanded(); assert page.expanded_dialog is dialog
        dialog.close(); qt_app.processEvents()
        assert page.isAncestorOf(page.surface) and page.tabs.currentIndex()==1
    finally:w.close()


def test_pet_manifest_has_explicit_frames():
    root=Path(__file__).parents[1]
    manifest=json.loads((root/'assets/xiaobai-states.json').read_text(encoding='utf-8'))
    assert all(0<=index<len(manifest['frames']) for sequence in manifest['actions'].values() for index in sequence)
    assert all('rect' in frame and 'anchor' in frame for frame in manifest['frames'])

def test_calendar_navigation_and_pick_preserve_time_and_zone(qt_app):
    from mediaforge.metadata_inputs import MetadataInput
    from PySide6.QtCore import QDate
    control=MetadataInput('date','2026:10:06 11:13:17+08:00')
    try:
        before=control.serialized();control.show_calendar();control.calendar_popup.calendar.showPreviousMonth()
        assert control.serialized()==before
        control.calendar_popup.choose(QDate(2025,12,31))
        assert control.serialized()=='2025:12:31 11:13:17+08:00'
        control.date.setText('2025-02-30 11:13:17')
        with pytest.raises(ValueError):control.serialized()
    finally:control.calendar_popup.close();control.close()


def test_quick_edit_restore_delete_and_draft_isolation(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        page=w.information_page;a=Job(tmp_path/'a.mov');b=Job(tmp_path/'b.mov')
        page.jobs=[a,b];page.records[a.id]=[{'Keys:Make':'Apple','Keys:CreationDate':'2026:10:06 11:13:17+08:00'}];page.records[b.id]=[{'Keys:Make':'Other'}]
        page.catalog={'Keys:Make':'?','Keys:CreationDate':'?'};page.files.addItems(['a.mov','b.mov']);page.populate()
        field=page.quick_form.fields['make'];field.input.text.setText('New Brand');field.edited()
        assert page.edits[a.id][0,'Keys:Make']=='New Brand'
        page.edit_field('make');assert page.editor.text.text()=='New Brand';page.close_editor()
        field.input.text.setText('');field.edited();assert not page.edits.get(a.id,{})
        field.delete_value();assert page.edits[a.id][0,'Keys:Make']==''
        field.restore_value();assert not page.edits[a.id]
        date=page.quick_form.fields['capture'];date.input.date.setText('invalid');date.edited()
        assert any(key[0]==a.id for key in page.drafts)
        page.files.setCurrentIndex(1);assert not page.edits.get(b.id)
        page.files.setCurrentIndex(0);assert page.quick_form.fields['capture'].input.date.text()=='invalid'
        page.quick_form.fields['capture'].restore_value();assert not any(key[0]==a.id for key in page.drafts)
    finally:w.close()


def test_supplement_requires_choice_and_restores_json_list(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        page=w.information_page;job=Job(tmp_path/'a.bmp');page.jobs=[job];page.records[job.id]=[{'File:FileType':'BMP'}];page.files.addItem('a.bmp');page.populate()
        field=page.quick_form.fields['make'];field.input.text.setText('My Camera');field.edited()
        assert not page.supplements.get(job.id)
        field.destination.setCurrentIndex(1)
        assert page.supplements[job.id][0,'XMP-tiff:Make','sidecar']=='My Camera'
        page.restore_field('make');assert not page.supplements[job.id]
        from mediaforge.metadata_inputs import MetadataInput
        control=MetadataInput('list','["中文", "旅行"]')
        assert json.loads(control.serialized())==['中文','旅行']
    finally:w.close()

def test_typed_gps_preserves_decimal_precision(qt_app):
    from mediaforge.metadata_inputs import MetadataInput
    from mediaforge.metadata_fields import parse_coordinates
    control=MetadataInput('gps','31.777800, 119.878200, 12.50')
    try:assert control.serialized()=='31.777800, 119.878200, 12.50'
    finally:control.close()
    assert parse_coordinates('1e-05, -1.2e+02')[:2]==(0.00001,-120.0)


def test_keyword_explicit_delete_is_verified(tmp_path):
    import threading
    from PIL import Image
    from mediaforge.metadata import export_component,read_metadata,MetadataOptions,media_fingerprint
    source=tmp_path/'原图.jpg';stage=tmp_path/'关键词.jpg';out=tmp_path/'删除.jpg'
    Image.new('RGB',(24,24),'blue').save(source)
    export_component(source,stage,MetadataOptions(edits=((0,'XMP-dc:Subject','["中文","旅行"]'),)),0,threading.Event(),lambda p:None)
    export_component(stage,out,MetadataOptions(edits=((0,'XMP-dc:Subject',''),)),0,threading.Event(),lambda p:None)
    assert 'XMP-dc:Subject' not in read_metadata(out)
    assert media_fingerprint(stage)==media_fingerprint(out)

def test_common_card_text_is_not_compressed(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    from PySide6.QtWidgets import QLabel,QPushButton
    from PySide6.QtTest import QTest
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        w.set_ui_mode('information',False);w.resize(980,640);w.show()
        page=w.information_page;job=Job(tmp_path/'a.mov');page.jobs=[job]
        page.records[job.id]=[{'Keys:CreationDate':'2026:10:06 11:13:17+08:00','Keys:Make':'Apple','Keys:Model':'iPhone 15 Pro','VideoKeys:LensModel':'iPhone 15 Pro back triple camera 6.765mm f/1.78','Keys:GPSCoordinates':'31.7778 119.8782 9.989'}]
        page.files.addItem('a.mov');page.populate();QTest.qWait(40)
        for i in range(page.common_layout.count()):
            card=page.common_layout.itemAt(i).widget()
            if not card:continue
            for label in card.findChildren(QLabel):assert label.height()>=label.fontMetrics().height(),(label.text(),label.height())
            for button in card.findChildren(QPushButton):assert button.height()>=button.sizeHint().height()
    finally:w.close()

def test_sprite_cells_have_transparent_padding_and_real_foot_stays(qt_app,tmp_path):
    from PIL import Image
    from mediaforge.controller import AppController
    from PySide6.QtCore import QPoint
    root=Path(__file__).parents[1];manifest=json.loads((root/'assets/xiaobai-states.json').read_text(encoding='utf-8'));sheet=Image.open(root/'assets'/manifest['image'])
    for frame in manifest['frames']:
        x,y,w,h=frame['rect'];box=sheet.crop((x,y,x+w,y+h)).getbbox()
        assert box and box[0]>0 and box[1]>0 and box[2]<w and box[3]<h
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.pet.move(300,250);c.pet.set_state('idle')
        visible_foot=c.pet.y()+c.pet.mask().boundingRect().bottom()+1
        for scale in (2,3,4,5,6):
            c.pet.set_scale(scale)
            assert abs(c.pet.y()+c.pet.mask().boundingRect().bottom()+1-visible_foot)<=1
    finally:c.request_exit()


def test_xmp_location_unchecking_altitude_removes_old_value(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    from mediaforge.metadata_fields import resolve_field
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        page=w.information_page;job=Job(tmp_path/'photo.jpg');page.jobs=[job]
        page.records[job.id]=[{'Composite:GPSLatitude':31.7778,'Composite:GPSLongitude':119.8782,'Composite:GPSAltitude':12.5}]
        page.files.addItem('photo.jpg');page.populate()
        target=resolve_field('location',page.record,'.jpg');context=(job.id,0,target.tag,target.strategy)
        assert page.quick_form.fields['location'].input.include_altitude.isChecked()
        for old_altitude in (12.5,90):
            page.supplements.setdefault(job.id,{})[0,'XMP-exif:GPSAltitude','xmp']=str(old_altitude)
            assert page.apply_editor(context,target,'31.777800, 119.878200')
            assert page.supplements[job.id][0,'XMP-exif:GPSAltitude','xmp']==''
            assert page.value_for_target('location',target)=='31.7778, 119.8782'
    finally:w.close()


def test_unadded_keyword_draft_survives_and_blocks_export(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    from PySide6.QtTest import QTest
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        page=w.information_page;a=Job(tmp_path/'a.jpg');b=Job(tmp_path/'b.jpg');page.jobs=[a,b]
        page.records[a.id]=[{'XMP-dc:Subject':['已有']}];page.records[b.id]=[{'File:FileType':'JPEG'}]
        page.files.addItems(['a.jpg','b.jpg']);page.populate()
        field=page.quick_form.fields['keywords'];field.destination.setCurrentIndex(1)
        QTest.keyClicks(field.input.entry,'unadded keyword')
        assert page.drafts[field.context()]['entry']=='unadded keyword'
        with pytest.raises(ValueError,match='添加'):field.input.serialized()
        page.files.setCurrentIndex(1);page.files.setCurrentIndex(0)
        field=page.quick_form.fields['keywords'];assert field.input.entry.text()=='unadded keyword'
        page.export_copy();assert '草稿' in page.hint.text() and not hasattr(page,'last_output_job')
        field.input.add_item()
        assert field.context() not in page.drafts
        assert json.loads(page.supplements[a.id][0,'XMP-dc:Subject','xmp'])==['已有','unadded keyword']
    finally:w.close()


def test_xmp_altitude_removed_on_verified_copy(tmp_path):
    import threading
    from PIL import Image
    from mediaforge.metadata import export_component,read_metadata,MetadataOptions,media_fingerprint
    source=tmp_path/'原图.jpg';stage=tmp_path/'含海拔.jpg';out=tmp_path/'无海拔.jpg';cancel=threading.Event()
    Image.new('RGB',(24,24),'white').save(source)
    before=source.read_bytes()
    export_component(source,stage,MetadataOptions(supplements=tuple((0,key,value,'xmp') for key,value in [('XMP-exif:GPSLatitude','31.7778'),('XMP-exif:GPSLongitude','119.8782'),('XMP-exif:GPSAltitude','12.5')])),0,cancel,lambda p:None)
    assert read_metadata(stage)['XMP-exif:GPSAltitude']==12.5
    export_component(stage,out,MetadataOptions(supplements=((0,'XMP-exif:GPSAltitude','','xmp'),)),0,cancel,lambda p:None)
    data=read_metadata(out)
    assert 'XMP-exif:GPSAltitude' not in data and data['XMP-exif:GPSLatitude']==31.7778
    assert media_fingerprint(source)==media_fingerprint(out) and source.read_bytes()==before


def test_unconfirmed_supplement_choice_does_not_become_consent_after_switch(qt_app,tmp_path):
    from mediaforge.window import MainWindow
    from mediaforge.models import Job
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        page=w.information_page;a=Job(tmp_path/'a.bmp');b=Job(tmp_path/'b.bmp');page.jobs=[a,b]
        page.records[a.id]=[{'File:FileType':'BMP'}];page.records[b.id]=[{'File:FileType':'BMP'}]
        page.files.addItems(['a.bmp','b.bmp']);page.populate()
        field=page.quick_form.fields['make'];field.input.text.setText('Unconfirmed Camera');field.edited()
        assert field.destination.currentData() is None
        page.files.setCurrentIndex(1);page.files.setCurrentIndex(0)
        field=page.quick_form.fields['make']
        assert field.destination.currentData() is None
        assert field.input.text.text()=='Unconfirmed Camera' and not page.supplements.get(a.id)
        page.edit_field('make');page.editor.text.setText('Editor draft');page.editor.changed();page.close_editor()
        page.files.setCurrentIndex(1);page.files.setCurrentIndex(0)
        field=page.quick_form.fields['make']
        assert field.destination.currentData() is None and field.input.text.text()=='Editor draft'
        field.destination.setCurrentIndex(1)
        assert page.supplements[a.id][0,'XMP-tiff:Make','sidecar']=='Editor draft'
    finally:w.close()
