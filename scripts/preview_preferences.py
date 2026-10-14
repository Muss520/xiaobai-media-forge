"""Capture UI previews using disposable preferences and explicit shutdown."""
import os,sys,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from mediaforge.controller import AppController
app=QApplication.instance() or QApplication([])
with tempfile.TemporaryDirectory(prefix='settings-preview-',dir=root/'temp') as scratch:
    c=AppController(app,settings_path=Path(scratch)/'settings.json',quit_application=False)
    c.window.hardware_enabled=False
    try:
        c.window.show(); c.window.set_ui_mode('advanced',False); c.window.resize(1280,820)
        QTest.qWait(250)
        c.window.grab().save(str(root/'docs/设置升级工作台.png'))
        c.show_settings(); QTest.qWait(100)
        c.settings_dialog.grab().save(str(root/'docs/设置界面.png'))
        c.settings_dialog.tabs.setCurrentIndex(1); QTest.qWait(100)
        c.settings_dialog.grab().save(str(root/'docs/小猫大小设置.png'))
    finally:
        c.request_exit(); QTest.qWait(150)
