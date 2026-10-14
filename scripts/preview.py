"""Generate a review screenshot by driving the real Qt interface."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
from pathlib import Path
root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'src'))
from PIL import Image, ImageDraw
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from mediaforge.window import MainWindow

app = QApplication([])
folder = root / 'tests' / 'artifacts'
folder.mkdir(parents=True, exist_ok=True)
sample = folder / '透明图标 示例.png'
image = Image.new('RGBA', (960, 640), (12, 33, 60, 0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((100, 100, 860, 540), radius=20, fill='#f7f5ef', outline='#625e53', width=4)
draw.line([(320, 220), (320, 420), (600, 320), (320, 220)], fill='#625e53', width=5)
image.save(sample)
window = MainWindow(settings_path=folder / 'preview-settings.json')
window.hardware_enabled = False
window.show()
window.add_files([sample])
for _ in range(200):
    app.processEvents()
    QTest.qWait(10)
    if not window.inspectors:
        break
window.output.setText(str(folder / '输出'))
window.panels['image'].width.setValue(640)
window.panels['image'].height.setValue(480)
window.start_batch()
for _ in range(500):
    app.processEvents()
    QTest.qWait(10)
    if not window.busy:
        break
window.grab().save(str(root / 'docs' / '界面预览.png'))
window.tabs.setCurrentIndex(0)
window.set_ui_mode('advanced', False)
QTest.qWait(30)
window.grab().save(str(root / 'docs' / '视频参数预览.png'))
window.tabs.setCurrentIndex(2)
window.set_ui_mode('simple', False)
QTest.qWait(30)
window.grab().save(str(root / 'docs' / 'Live简单模式.png'))
window.close()
print('Screenshots saved in docs')
