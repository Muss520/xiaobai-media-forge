import sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src'))
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from mediaforge.controller import AppController
from PIL import Image
app=QApplication([])
controller=AppController(app,settings_path=root/'tests/artifacts/pet-preview-settings.json',quit_application=False)
controller.window.hardware_enabled=False
controller.window.show()
QTest.qWait(100)
controller.window.grab().save(str(root/'docs/极简界面.png'))
controller.pet.grab().save(str(root/'docs/桌面小猫.png'))
controller.window.set_ui_mode('advanced',False)
QTest.qWait(100)
controller.window.grab().save(str(root/'docs/专业工作台.png'))
source=root/'tests/artifacts/宠物照片示例.png'
Image.new('RGB',(200,120),'#e9dfcc').save(source)
controller.import_files([source])
for _ in range(200):
 QTest.qWait(20)
 if controller.dialog:break
if controller.dialog:
 controller.dialog.grab().save(str(root/'docs/宠物需求气泡.png'))
controller.request_exit()
QTest.qWait(300)
print('Pet and independent workspace previews saved')
