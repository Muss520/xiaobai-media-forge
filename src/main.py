import logging
from logging.handlers import RotatingFileHandler
import sys
from mediaforge.paths import setup_paths,runtime_home,resource_home
from mediaforge.product import NAME,VERSION


def main():
    root = setup_paths()
    handler = RotatingFileHandler(runtime_home() / 'logs' / 'mediaforge.log', maxBytes=2_000_000,
                                  backupCount=3, encoding='utf-8')
    logging.basicConfig(handlers=[handler], level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    logging.info('加载桌面组件')
    from PySide6.QtWidgets import QApplication, QMessageBox
    from PySide6.QtGui import QFont, QIcon
    from mediaforge.window import MainWindow
    app = QApplication(sys.argv)
    logging.info('桌面组件已就绪')
    app.setApplicationName(NAME)
    app.setOrganizationName('MediaForge')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    try:
        icon = resource_home() / 'assets' / 'mediaforge.ico'
        if not icon.exists():
            from pathlib import Path
            icon = Path(getattr(sys, '_MEIPASS', root)) / 'assets' / 'mediaforge.ico'
        if icon.exists():
            app.setWindowIcon(QIcon(str(icon)))
        def exception_hook(kind, value, traceback):
            logging.error('未处理异常', exc_info=(kind, value, traceback))
            QMessageBox.critical(None, '程序错误', f'{value}\n详细记录已保存到软件日志。')
        sys.excepthook = exception_hook
        from mediaforge.controller import AppController, SingleInstance
        diagnostic='--verify-startup' in sys.argv
        instance = SingleInstance(root)
        if not instance.primary and not diagnostic:
            return 0
        controller = AppController(app,settings_path=runtime_home()/'data'/'diagnostic-settings.json' if diagnostic else None)
        if instance:instance.activated.connect(controller.show_window)
        window = controller.window
        window.show()
        logging.info('%s %s 启动；工作目录=%s',NAME,VERSION,root)
        if '--verify-startup' in sys.argv:
            from mediaforge.diagnostics import schedule_startup_check
            schedule_startup_check(app, window)
        result = app.exec()
        if instance:instance.close()
        logging.info('软件已退出')
        return result
    except Exception as error:
        QMessageBox.critical(None, '无法启动', f'{error}\n请将完整软件文件夹放在可写入的位置。')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
