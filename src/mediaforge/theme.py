def sketch_mark():
    import sys
    from pathlib import Path
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import Qt
    from .paths import app_home,resource_home
    return QPixmap(str(resource_home()/'assets/mediaforge.png')).scaled(68,68,Qt.KeepAspectRatio,Qt.FastTransformation)


def setup_fonts():
    import sys
    from pathlib import Path
    from PySide6.QtGui import QFontDatabase
    from .paths import app_home,resource_home
    base = resource_home()
    font = base / 'assets' / 'NotoSansCJKsc-Regular.otf'
    if font.exists():
        QFontDatabase.addApplicationFont(str(font))


from PySide6.QtWidgets import QTabBar
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont


class SideTabs(QTabBar):
    def tabSizeHint(self, index):
        width=getattr(self,'preferred_width',120)
        lines=2 if index==2 and width-12<=145 else 1
        return QSize(width,max(getattr(self,'preferred_height',70),self.fontMetrics().height()*lines+24))

    def set_dimensions(self,width,height):
        self.preferred_width=width; self.preferred_height=height
        self.setMinimumWidth(width); self.updateGeometry(); self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        for i in range(self.count()):
            rect = self.tabRect(i).adjusted(0, 4, -12, -4)
            selected = i == self.currentIndex()
            if selected:
                painter.fillRect(rect, QColor('#eae6da'))
                painter.setPen(QPen(QColor('#514e43'), 2))
                painter.drawLine(rect.left(), rect.top() + 12, rect.left() + 1, rect.bottom() - 12)
            painter.setPen(QColor('#454239' if selected else '#999386'))
            font = painter.font()
            painter.setFont(font)
            painter.drawText(rect.adjusted(12, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft,
                             ['01  视频', '02  图片', '03  Live Photo' if rect.width()>145 else '03  Live\n      Photo'][i])
        painter.end()


STYLE = '''
QWidget { background: #f7f5ef; color: #34332f; font-family: "Noto Sans CJK SC", "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; }
QMainWindow { background: #f7f5ef; }
QLabel#brand { font-size: 30px; font-weight: 600; color: #302f2b; }
QLabel#tagline, QLabel#muted { color: #89867e; }
QLabel#tagline { font-size: 12px; }
QLabel#taskDetails { background: #f0ede3; border: 1px solid #ded8ca; border-radius: 8px; padding: 10px 14px; color: #716b5d; line-height: 1.6; }
QLabel#sectionTitle { font-size: 17px; font-weight: 500; }
QLabel#badge { background: transparent; color: #65635c; border: 1px solid #bbb7ac; border-radius: 3px; padding: 6px 12px; }
QLabel#dropHint { background: #faf9f5; border: 1px dashed #b0a793; border-radius: 10px; padding: 14px; color: #77746b; font-size: 15px; }
QPushButton, QToolButton { background: #faf9f5; border: 1px solid #c5beae; border-radius: 6px; padding: 8px 12px; }
QPushButton:hover, QToolButton:hover { background: #eeece4; border-color: #646159; }
QPushButton:pressed { background: #e4e1d7; }
QPushButton:disabled { background: #f7f5ef; color: #c3bfb5; border-color: #dedbd2; }
QPushButton#primary { background: #3c3b35; color: #faf9f5; border: 1px solid #3c3b35; min-width: 110px; }
QPushButton#primary:hover { background: #55534b; }
QPushButton#primary:disabled { background: #d6d2c8; color: #faf9f5; border-color: #d6d2c8; }
QPushButton#danger { color: #797269; }
QToolButton#advancedToggle { text-align: left; background: transparent; border: none; border-bottom: 1px solid #d5d1c7; border-radius: 0; padding: 12px 0; color: #6f6b61; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #fcfbf7; border: 1px solid #d4cebf; border-radius: 5px; padding: 5px 8px; min-height: 24px; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus { border-color: #5b584f; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled { color: #b8b4a9; border-color: #dfdcd3; }
QComboBox QAbstractItemView { background: #fcfbf7; selection-background-color: #e7e3d8; selection-color: #34332f; border: 1px solid #c1bcaf; }
QGroupBox { background: #faf8f1; border: 1px solid #ded8cb; border-radius: 8px; margin-top: 12px; padding-top: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 13px; padding: 0 5px; color: #777268; }
QCheckBox { spacing: 7px; }
QCheckBox::indicator { width: 15px; height: 15px; border: 1px solid #aaa496; border-radius: 2px; background: #fcfbf7; }
QCheckBox::indicator:checked { background: #6b675c; border: 1px solid #6b675c; }
QCheckBox::indicator:disabled { background: #e4e0d6; border-color: #d3cec2; }
QTabWidget::pane { border: none; padding-top: 12px; }
QTabBar::tab { background: transparent; border-bottom: 1px solid #d4cfc2; padding: 12px 26px; color: #a09a8c; font-size: 15px; }
QTabBar::tab:selected { color: #35332d; border-bottom: 2px solid #5e594d; }
QTabBar::tab:hover { color: #5d574b; }
QTableWidget { background: #fcfbf7; alternate-background-color: #f7f5ee; border: 1px solid #ded8cb; border-radius: 8px; gridline-color: #e6e1d5; selection-background-color: #e7e2d6; selection-color: #34332f; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #e8e4da; }
QHeaderView::section { background: #efede4; color: #827b6b; padding: 11px 6px; border: none; border-bottom: 1px solid #d7d1c3; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: #f7f5ef; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #c6c0b1; border-radius: 2px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #f7f5ef; height: 7px; }
QScrollBar::handle:horizontal { background: #c6c0b1; border-radius: 2px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QProgressBar { background: #e8e3d6; color: #34332f; border: none; border-radius: 2px; text-align: center; min-height: 8px; }
QProgressBar::chunk { background: #c9c2b2; border-radius: 2px; }
QToolTip { background: #faf8f1; color: #34332f; border: 1px solid #b9b1a1; padding: 6px; }
QSplitter::handle { background: #ded8ca; width: 1px; }
QMenu { background: #fcfbf7; border: 1px solid #beb5a4; }
QMenu::item:selected { background: #e6dfd1; }
'''

STYLE += """
QLabel#simpleDrop { color: #686153; background: #fbfaf6; border: 1px dashed #b2a996; border-radius: 16px; padding: 16px; font-size: 18px; }
QListWidget#simpleFiles { background: transparent; border: none; }
QListWidget#simpleFiles { color: #34332f; selection-background-color: #e5e0d3; selection-color: #242320; outline: none; }
QListWidget#simpleFiles::item:selected { color: #242320; background: #e5e0d3; border-radius: 6px; }
QListWidget#simpleFiles::item { padding: 12px 8px; border-bottom: 1px solid #e5e0d3; }
QDialog { background: #f7f5ef; }
QPushButton#modeButton { min-width: 84px; }
QPushButton#modeButton:checked { background: #454239; color: #fffdf7; border-color: #454239; }
QLabel#customSummary { background: #ede9de; border-left: 2px solid #817867; padding: 12px; color: #625a4e; }
QLabel#inlineError { color: #a14e39; }
QLabel#taskDetail { color: #686153; }
QLabel#taskDetail[error="true"] { color: #a14e39; }
QLabel#wizardSteps { color: #625b4e; padding: 8px 0; }
QLabel#dropHint[receiving="true"] { background: #e7e1d1; border: 2px dashed #817867; }
"""

STYLE += 'QLabel#simpleDrop[receiving="true"] { background: #e9e3d5; border: 2px dashed #817867; }'


def presentation_style(preferences):
    import sys
    from pathlib import Path
    from .paths import app_home,resource_home
    base=resource_home()/'assets'
    down=(base/'chevron-down.svg').as_posix()
    up=(base/'chevron-up.svg').as_posix()
    check=(base/'check.svg').as_posix()
    left=(base/'chevron-left.svg').as_posix();right=(base/'chevron-right.svg').as_posix()
    size=preferences.get('font_points',12)
    compact=preferences.get('density')=='compact'
    padding=6 if compact else 8
    return STYLE+f'''
QWidget {{ font-size:{size}pt; }}
QLabel {{ background:transparent; }}
QPushButton, QToolButton {{ padding:{padding}px 12px; }}
QComboBox {{ padding-right:28px; }}
QComboBox::drop-down {{ subcontrol-origin:border; subcontrol-position:top right; width:26px; border:none; background:transparent; }}
QComboBox::down-arrow {{ image:url("{down}"); width:14px; height:14px; }}
QSpinBox, QDoubleSpinBox {{ padding-right:28px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button {{ subcontrol-origin:border; subcontrol-position:top right; width:24px; height:18px; border:none; background:transparent; }}
QSpinBox::down-button, QDoubleSpinBox::down-button {{ subcontrol-origin:border; subcontrol-position:bottom right; width:24px; height:18px; border:none; background:transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image:url("{up}"); width:12px; height:12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image:url("{down}"); width:12px; height:12px; }}
QSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {{ background:#eae6da; }}
QCheckBox::indicator:checked {{ image:url("{check}"); }}
QTabBar QToolButton {{ padding:0; width:22px; border:none; background:#f7f5ef; border-radius:0; }}
QTabBar QToolButton::left-arrow {{ image:url("{left}"); width:14px; height:14px; }}
QTabBar QToolButton::right-arrow {{ image:url("{right}"); width:14px; height:14px; }}
QSlider::groove:horizontal {{ height:4px; background:#ded8ca; border-radius:2px; }}
QSlider::sub-page:horizontal {{ background:#686153; border-radius:2px; }}
QSlider::handle:horizontal {{ width:16px; margin:-6px 0; background:#fcfbf7; border:1px solid #686153; border-radius:8px; }}
QSlider::handle:horizontal:hover {{ background:#eae6da; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QGroupBox {{ border:none; border-top:1px solid #ded8cb; border-radius:0; background:transparent; margin-top:16px; padding-top:16px; }}
QGroupBox::title {{ background:#f7f5ef; subcontrol-origin:margin; left:0; padding:0 6px 0 0; color:#625b4e; }}
QMenu {{ padding:6px; border-radius:8px; }}
QMenu::item {{ padding:9px 22px 9px 12px; min-height:22px; border-radius:4px; }}
QMenu::item:selected {{ background:#eae5d9; color:#34332f; }}
QMenu::item:disabled {{ color:#aaa496; }}
QMenu::separator {{ height:1px; background:#ded8cb; margin:5px 8px; }}
QTableWidget {{ border-radius:0; }}
QSplitter::handle {{ background:transparent; width:8px; }}
QSplitter::handle:hover {{ background:#e4dfd3; }}
'''

STYLE += """
QFrame#authorCard, QFrame#supportCard { background:#fcfbf7; border:1px solid #ded8ca; border-radius:10px; }
QFrame#authorCard QLabel, QFrame#supportCard QLabel { border:none; background:transparent; }
QLabel#authorTitle { font-weight:600; }
QLabel#wechatHeading { color:#258056; font-weight:600; }
QLabel#alipayHeading { color:#326cad; font-weight:600; }
QPushButton#qrPreview { background:white; padding:0; border:1px solid #e1dccf; border-radius:6px; }
QPushButton#qrPreview:hover { border-color:#9a927e; }
QPushButton:focus, QToolButton:focus { border:1px solid #6f6757; }
QPushButton#primary:focus { border:2px solid #9b9078; }
QTabBar::tab:focus { color:#34332f; }
QGroupBox#parameterSection { border:none; background:transparent; margin:0; padding:0; }
QLabel#parameterHeading { color:#625b4e; font-weight:500; border-bottom:1px solid #ded8cb; padding:8px 0; }
QFrame#informationCard { background:#fcfbf7; border:1px solid #e1dccf; border-radius:8px; }
QFrame#informationCard QLabel { border:none; background:transparent; }
QFrame#taskSummaryCard { background:#f0ede3; border:1px solid #ded8ca; border-radius:8px; }
QFrame#taskSummaryCard QLabel { background:transparent; border:none; padding:0; color:#716b5d; }
QPushButton#compactAction { padding:3px 8px; min-width:0; }
QScrollBar:vertical { width:10px; background:transparent; margin:3px 1px; }
QScrollBar::handle:vertical { background:#c8c2b5; border:2px solid #f7f5ef; border-radius:5px; min-height:34px; }
QScrollBar::handle:vertical:hover { background:#938b7a; }
QTableWidget:focus { outline:none; }
QTableWidget::item:focus { border:none; }
"""
