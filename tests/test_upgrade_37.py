from pathlib import Path
import json
import hashlib
import pytest


def test_product_brand_is_visible_and_mode_shortcuts_dispatch(qt_app,tmp_path,monkeypatch):
    from mediaforge.window import MainWindow
    from PySide6.QtGui import QShortcut
    w=MainWindow(tmp_path/'settings.json');w.hardware_enabled=False
    try:
        from mediaforge.product import DISPLAY_VERSION
        assert '小白媒体工坊' in w.windowTitle() and DISPLAY_VERSION in w.windowTitle()
        assert hasattr(w,'add_current_files')
        calls=[]
        monkeypatch.setattr(w,'choose_files',lambda:calls.append(w.ui_mode))
        monkeypatch.setattr(w.information_page,'choose_files',lambda:calls.append('information'))
        for mode in ('simple','advanced','information'):
            w.set_ui_mode(mode,False);w.add_current_files()
        assert calls==['simple','advanced','information']
        assert {'Ctrl+O','F1'} <= {s.key().toString() for s in w.findChildren(QShortcut)}
    finally:w.close()


def test_author_tab_copy_and_reset_isolation(qt_app,tmp_path):
    from mediaforge.controller import AppController
    from PySide6.QtTest import QTest
    c=AppController(qt_app,tmp_path/'settings.json',quit_application=False);c.window.hardware_enabled=False
    try:
        c.show_settings();s=c.settings_dialog
        author=s.page_index('author');assert author>=0 and s.tabs.tabText(author)=='作者与打赏'
        c.preferences['sound_volume']=37
        s.tabs.setCurrentIndex(author);QTest.qWait(20)
        assert not s.reset_button.isVisible()
        s.author_page.copy_email()
        assert qt_app.clipboard().text()=='2504542766@QQ.COM'
        before=json.dumps(c.preferences,sort_keys=True)
        s.reset_page('author')
        assert json.dumps(c.preferences,sort_keys=True)==before
        assert '沐' in s.author_page.author_label.text()
        assert s.author_page.cards[0].image_path.is_file()
    finally:c.request_exit()


def test_author_qr_resources_match_original_pixels():
    from PIL import Image
    base=Path(__file__).parents[1];manifest=base/'assets/support/manifest.json'
    assert manifest.exists(),'缺少二维码裁切与验证清单'
    for item in json.loads(manifest.read_text(encoding='utf-8'))['codes']:
        asset=base/'assets/support'/item['asset']
        assert hashlib.sha256(asset.read_bytes()).hexdigest()==item['asset_sha256']
        original=base.parent/'收款码'/item['original']
        if original.exists():
            assert hashlib.sha256(original.read_bytes()).hexdigest()==item['source_sha256']
            with Image.open(original) as source,Image.open(base/'assets/support'/item['asset']) as crop:
                assert crop.size==tuple(item['size'])
                pad=item['padding'];inner=crop.crop((pad,pad,crop.width-pad,crop.height-pad))
                assert inner.convert('RGB').tobytes()==source.convert('RGB').crop(item['box']).tobytes()


def test_navigation_reserves_height_for_large_wrapped_label(qt_app):
    from mediaforge.theme import SideTabs
    from PySide6.QtGui import QFont
    tabs=SideTabs();tabs.addTab('video');tabs.addTab('image');tabs.addTab('live')
    tabs.setFont(QFont('Microsoft YaHei UI',20));tabs.set_dimensions(150,60)
    assert tabs.tabSizeHint(2).height()>=tabs.fontMetrics().height()*2+24


def test_code_save_is_byte_identical_and_zoom_singleton(qt_app,tmp_path,monkeypatch):
    from mediaforge.support import SupportCard
    from PySide6.QtWidgets import QFileDialog
    from PySide6.QtTest import QTest
    card=SupportCard('微信打赏','wechat.png','wechat');card.show()
    target=tmp_path/'保存二维码.png'
    monkeypatch.setattr(QFileDialog,'getSaveFileName',lambda *a,**k:(str(target),'PNG'))
    try:
        card.save_code();assert target.read_bytes()==card.image_path.read_bytes()
        card.open_large();first=card.dialog;card.open_large();assert card.dialog is first
        first.close();QTest.qWait(10);assert card.dialog is None
        card.open_large();assert card.dialog is not None
    finally:
        if card.dialog:card.dialog.close()
        card.close()


@pytest.mark.parametrize('live',[False,True])
def test_metadata_failed_stage_creation_never_deletes_existing_directory(tmp_path,monkeypatch,live):
    import threading
    from mediaforge.metadata import process_metadata,MetadataOptions
    from mediaforge.models import Job
    source=tmp_path/'source.jpg';source.write_bytes(b'original')
    destination=tmp_path/('Live信息' if live else '信息副本.jpg')
    if live:destination.mkdir()
    else:destination.touch()
    # Simulate a collision for any staging name, without risking user data.
    existing=tmp_path/'existing-user-folder';existing.mkdir();sentinel=existing/'keep.txt';sentinel.write_bytes(b'keep')
    removed=[]
    monkeypatch.setattr(Path,'mkdir',lambda *a,**kw:(_ for _ in ()).throw(FileExistsError('occupied')))
    monkeypatch.setattr(Path,'exists',lambda p:True)
    monkeypatch.setattr('mediaforge.metadata.shutil.rmtree',lambda p:removed.append(p))
    options=MetadataOptions() if live else MetadataOptions(supplements=((0,'XMP-tiff:Make','camera','sidecar'),))
    job=Job(source,inputs=(source,tmp_path/'paired.mov')) if live else Job(source)
    with pytest.raises(FileExistsError):process_metadata(job,options,destination,threading.Event(),lambda p:None)
    assert not removed,'Cleanup must only delete a staging directory this task successfully created'
    assert sentinel.read_bytes()==b'keep'
