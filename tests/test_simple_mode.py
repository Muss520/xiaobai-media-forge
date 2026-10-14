from dataclasses import asdict
from PySide6.QtTest import QTest


def test_mode_preserves_custom_parameters_and_resets_preset(qt_app, tmp_path):
    from mediaforge.window import MainWindow
    window = MainWindow(settings_path=tmp_path / 'settings.json')
    window.hardware_enabled = False
    assert window.ui_mode == 'simple'
    for panel in window.panels.values():
        assert panel.advanced.isHidden()
    window.set_ui_mode('advanced')
    panel = window.panels['video']
    panel.width.setValue(960)
    panel.quality.setValue(19)
    panel.format.setCurrentIndex(panel.format.findData('mkv'))
    before = panel.snapshot()
    window.set_ui_mode('simple')
    assert panel.snapshot() == before
    assert '自定义参数已生效' in panel.custom_summary.text()
    panel.restore_preset.click()
    assert panel.snapshot().width == 0
    assert panel.snapshot().quality == 23
    assert panel.snapshot().format == 'mkv'
    window.close()


def test_target_size_shared_and_clear_restores_quality(qt_app):
    from mediaforge.options import VideoPanel
    panel = VideoPanel()
    panel.target_bytes.setValue(3 * 1024 * 1024)
    assert panel.snapshot().mode == 'size'
    panel.set_ui_mode('advanced', False)
    assert panel.snapshot().target_bytes == 3 * 1024 * 1024
    panel.target_bytes.setValue(0)
    assert panel.snapshot().mode == 'quality'
    panel.target_bytes.setValue(2 * 1024 * 1024)
    panel.target_bytes.number.lineEdit().setText('')
    panel.target_bytes.number.interpretText()
    assert panel.snapshot().mode == 'quality'
    assert panel.snapshot().target_bytes == 0


def test_mode_default_motion_persisted_and_busy_snapshot(qt_app, tmp_path):
    from mediaforge.window import MainWindow
    config = tmp_path / 'settings.json'
    window = MainWindow(settings_path=config)
    window.hardware_enabled = False
    window.set_ui_mode('advanced')
    window.reduce_motion.setChecked(True)
    window.panels['image'].quality.setValue(76)
    snapshot = asdict(window.panels['image'].snapshot())
    window.busy = True
    window.refresh_controls()
    for mode in ('simple', 'advanced', 'simple', 'advanced'):
        window.set_ui_mode(mode)
    assert asdict(window.panels['image'].snapshot()) == snapshot
    assert not window.panels['image'].quality.isEnabled()
    window.busy = False
    window.close()
    reopened = MainWindow(settings_path=config)
    reopened.hardware_enabled = False
    assert reopened.ui_mode == 'simple'
    assert reopened.reduce_motion.isChecked()
    assert reopened.panels['image'].quality.value() == 76
    reopened.close()


def test_progress_never_finishes_before_validation(qt_app):
    from mediaforge.motion import SmoothProgress
    from PySide6.QtTest import QSignalSpy
    bar = SmoothProgress()
    bar.set_progress(100, '处理中')
    finished = QSignalSpy(bar.motion.animations[bar, b'value'].finished)
    assert bar.value() < 100
    assert finished.wait(2000)
    assert bar.value() == 99
    bar.set_progress(100, '完成')
    assert bar.value() == 100
    bar.set_progress(42, '处理中')
    bar.set_progress(42, '取消')
    QTest.qWait(230)
    assert bar.value() == 42


def test_live_single_controls_and_preserved_photo_settings(qt_app):
    from mediaforge.options import LivePanel
    panel = LivePanel()
    panel.set_ui_mode('advanced', False)
    panel.image_panel.quality.setValue(71)
    panel.target_bytes.setValue(2 * 1024 * 1024)
    before = panel.snapshot()
    panel.set_ui_mode('simple', False)
    assert panel.snapshot() == before
    assert panel.image_panel.presets.isHidden()
    assert panel.video_panel.presets.isHidden()
    assert panel.image_panel.target_bytes.isHidden()
    panel.apply_preset()
    assert panel.snapshot().image.quality == 85
    assert panel.snapshot().target_bytes == 0


def test_live_target_clear_restores_selected_preset(qt_app):
    from mediaforge.options import LivePanel, select
    panel = LivePanel()
    select(panel.mode, 'video')
    panel.video_panel.quality.setValue(19)
    panel.target_bytes.setValue(3 * 1024 * 1024)
    assert panel.snapshot().video.mode == 'size'
    panel.target_bytes.setValue(0)
    assert panel.snapshot().video.mode == 'quality'
    assert panel.snapshot().video.quality == 23


def test_live_summary_uses_effective_active_options(qt_app):
    from mediaforge.options import LivePanel, select
    panel = LivePanel()
    select(panel.mode, 'image')
    panel.image_panel.quality.setValue(74)
    select(panel.image_panel.animation, 'frame')
    panel.image_panel.frame_index.setValue(3)
    panel.refresh_summary()
    assert '选帧 3' not in panel.custom_summary.text()
    assert '视频：' not in panel.custom_summary.text()
    assert '质量 74' in panel.custom_summary.text()
    assert panel.image_panel.animation.parentWidget().isHidden()


def test_native_rapid_switch_layout_and_drop_feedback(qt_app, tmp_path):
    from PySide6.QtCore import Qt, QMimeData, QUrl, QPoint
    from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent
    from mediaforge.window import MainWindow
    window = MainWindow(settings_path=tmp_path / 'ui.json')
    window.hardware_enabled = False
    window.resize(980, 640)
    window.show()
    QTest.qWait(30)
    for tab in range(3):
        window.tabs.setCurrentIndex(tab)
        for mode in ('advanced', 'simple', 'advanced', 'simple'):
            window.set_ui_mode(mode)
            QTest.qWait(12)
        QTest.qWait(230)
        assert window.panels[window.kind].advanced.isHidden()
        assert window.view_stack.currentWidget() is window.simple_page
        window.set_ui_mode('advanced', False)
        QTest.qWait(30)
        assert window.panels[window.kind].format.visibleRegion().boundingRect().width() >= 60
        assert window.tables[window.kind].viewport().height() >= 60
    window.set_ui_mode('advanced')
    window.reduce_motion.setChecked(True)
    assert not window.panels['live'].advanced.isHidden()
    assert window.panels['live'].advanced.maximumHeight() == 16777215
    assert window.start.geometry().right() <= window.centralWidget().width()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / 'test.png'))])
    event = QDragEnterEvent(QPoint(200, 200), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(event)
    assert window.drop_hints['live'].property('receiving')
    window.dragLeaveEvent(QDragLeaveEvent())
    assert not window.drop_hints['live'].property('receiving')
    QTest.mouseMove(window.advanced_button)
    window.close()
