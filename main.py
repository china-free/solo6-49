import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from config.config_manager import AppConfig
from core.monitor_manager import MonitorManager
from core.wallpaper_setter import WallpaperSetter
from core.cache_manager import WallpaperCache, WallpaperHistory
from core.scheduler import WallpaperScheduler
from ui.main_window import MainWindow
from ui.system_tray import SystemTrayIcon


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    app.setApplicationName("壁纸自动切换器")
    app.setQuitOnLastWindowClosed(False)

    config = AppConfig.load()
    monitor_manager = MonitorManager()
    cache = WallpaperCache()
    wallpaper_setter = WallpaperSetter(monitor_manager, cache=cache)
    history = WallpaperHistory()
    scheduler = WallpaperScheduler(config, monitor_manager, wallpaper_setter, cache, history)

    window = MainWindow(config, scheduler, monitor_manager, history)
    tray = SystemTrayIcon(config, scheduler)

    def on_show_window():
        window.show()
        window.raise_()
        window.activateWindow()
        tray.update_status()

    def on_quit():
        reply = QMessageBox.question(
            None, "退出",
            "确定要退出壁纸自动切换器吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            scheduler.stop()
            tray.hide()
            app.quit()

    def on_next_from_tray():
        if config.per_monitor_wallpaper:
            primary = monitor_manager.get_primary_monitor()
            mid = primary.monitor_id if primary else None
            scheduler.switch_next(mid)
        else:
            scheduler.switch_next()
        tray.update_status()
        window._update_countdown() if hasattr(window, '_update_countdown') else None

    tray.show_window_requested.connect(on_show_window)
    tray.quit_requested.connect(on_quit)
    tray.next_wallpaper_requested.connect(on_next_from_tray)

    scheduler.wallpaper_changed.connect(lambda _: tray.update_status())

    tray.show()
    window.show()

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.warning(
            None, "警告",
            "当前系统不支持系统托盘，部分功能可能受限。"
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
