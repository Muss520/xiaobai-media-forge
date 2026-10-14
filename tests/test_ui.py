from pathlib import Path
from PIL import Image
from PySide6.QtCore import QMimeData, QUrl, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtTest import QTest


def test_options_enforce_container_and_remux_rules(qt_app):
    from mediaforge.options import VideoPanel
    panel = VideoPanel()
    panel.format.setCurrentIndex(panel.format.findData('webm'))
    value = panel.snapshot()
    assert value.codec == 'vp9' and value.audio_codec == 'opus'
    panel.remux.setChecked(True)
    assert panel.snapshot().audio_codec == 'copy'
    assert not panel.width.isEnabled()
    panel.remux.setChecked(False)
    assert panel.width.isEnabled()


def test_window_add_process_and_remove(qt_app, tmp_path):
    from mediaforge.window import MainWindow
    path = tmp_path / '测试 中文.png'
    Image.new('RGB', (120, 80), 'red').save(path)
    window = MainWindow(settings_path=tmp_path / 'settings.json')
    window.hardware_enabled = False
    window.add_files([path])
    for _ in range(100):
        qt_app.processEvents()
        QTest.qWait(20)
        if window.jobs['image'][0].info and not window.inspectors:
            break
    assert window.jobs['image'][0].info.width == 120
    window.tabs.setCurrentIndex(1)
    window.output.setText(str(tmp_path / 'out'))
    window.start_batch()
    snapshot = window.worker.options
    window.set_ui_mode('advanced')
    window.set_ui_mode('simple')
    assert window.worker.options == snapshot
    assert not window.panels['image'].quality.isEnabled()
    for _ in range(200):
        qt_app.processEvents()
        QTest.qWait(20)
        if not window.busy:
            break
    assert window.jobs['image'][0].status == '完成'
    assert window.jobs['image'][0].output.exists()
    assert window.tables['image'].item(0, 5).text() == '完成'
    window.tables['image'].selectRow(0)
    window.remove_selected()
    assert not window.jobs['image']
    window.close()


def test_drop_event_routes_image(qt_app, tmp_path):
    from mediaforge.window import MainWindow
    path = tmp_path / 'drop.png'
    Image.new('RGB', (16, 16), 'blue').save(path)
    window = MainWindow(settings_path=tmp_path / 'settings.json')
    window.hardware_enabled = False
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(window.rect().center(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(event)
    assert len(window.jobs['image']) == 1
    for _ in range(100):
        qt_app.processEvents()
        QTest.qWait(10)
        if not window.inspectors:
            break
    window.close()
