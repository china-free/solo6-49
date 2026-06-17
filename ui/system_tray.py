import sys
from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QAction
from PySide6.QtCore import Qt, Signal

from core.scheduler import WallpaperScheduler
from config.config_manager import AppConfig


class SystemTrayIcon(QSystemTrayIcon):
    quit_requested = Signal()
    show_window_requested = Signal()
    next_wallpaper_requested = Signal()

    def __init__(
        self,
        config: AppConfig,
        scheduler: WallpaperScheduler,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._scheduler = scheduler
        self._create_icon()
        self._create_menu()
        self.setToolTip("壁纸自动切换器")
        self.activated.connect(self._on_activated)

    def _create_icon(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#2196F3"))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(4, 4, 56, 56, 12, 12)
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawRect(14, 18, 14, 10)
        painter.drawRect(32, 18, 14, 10)
        painter.drawRect(14, 32, 32, 10)
        painter.setPen(QColor("#FFFFFF"))
        font = QFont()
        font.setBold(True)
        font.setPointSize(10)
        painter.setFont(font)
        painter.end()
        self.setIcon(QIcon(pixmap))

    def _create_menu(self):
        menu = QMenu()
        act_show = QAction("显示主窗口", self)
        act_show.triggered.connect(self.show_window_requested.emit)
        menu.addAction(act_show)

        menu.addSeparator()

        self.act_toggle = QAction("暂停自动切换", self)
        self.act_toggle.triggered.connect(self._on_toggle_scheduler)
        menu.addAction(self.act_toggle)
        self._update_toggle_text()

        act_next = QAction("立即切换下一张", self)
        act_next.triggered.connect(self.next_wallpaper_requested.emit)
        menu.addAction(act_next)

        menu.addSeparator()

        interval_menu = QMenu("切换间隔", menu)
        for label, minutes in [("5 分钟", 5), ("30 分钟", 30), ("1 小时", 60), ("1 天", 1440)]:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self._config.switch_interval_minutes == minutes)
            act.triggered.connect(lambda _, m=minutes, a=act: self._on_interval(m, a))
            interval_menu.addAction(act)
        menu.addMenu(interval_menu)

        mode_menu = QMenu("切换模式", menu)
        mode_map = [("顺序", "sequential"), ("随机", "random"), ("按修改时间", "mtime")]
        for label, mode in mode_map:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(self._config.switch_mode == mode)
            act.triggered.connect(lambda _, m=mode, a=act: self._on_mode(m, a))
            mode_menu.addAction(act)
        menu.addMenu(mode_menu)

        menu.addSeparator()

        act_quit = QAction("退出", self)
        act_quit.triggered.connect(self.quit_requested.emit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)

    def _update_toggle_text(self):
        if self._scheduler.is_running():
            self.act_toggle.setText("⏸️ 暂停自动切换")
        else:
            self.act_toggle.setText("▶️ 启动自动切换")

    def _on_toggle_scheduler(self):
        if self._scheduler.is_running():
            self._scheduler.stop()
        else:
            self._scheduler.start()
        self._update_toggle_text()

    def _on_interval(self, minutes: int, action: QAction):
        for act in action.parent().actions():
            if isinstance(act, QAction):
                act.setChecked(act is action)
        self._config.switch_interval_minutes = minutes
        self._config.save()
        self._scheduler.refresh_settings()

    def _on_mode(self, mode: str, action: QAction):
        for act in action.parent().actions():
            if isinstance(act, QAction):
                act.setChecked(act is action)
        self._config.switch_mode = mode
        self._config.save()
        self._scheduler.rebuild_browse()

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self.show_window_requested.emit()
        elif reason == QSystemTrayIcon.DoubleClick:
            self.show_window_requested.emit()

    def update_status(self):
        self._update_toggle_text()
