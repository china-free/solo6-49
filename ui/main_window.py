import os
from typing import Optional, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QLabel, QFileDialog, QMessageBox, QListWidgetItem, QSplitter,
    QScrollArea, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt, QSize, QTimer, Signal
from PySide6.QtGui import QPixmap, QImage, QIcon

from PIL import Image

from config.config_manager import AppConfig, VALID_MODES, VALID_MODES_MAP
from core.scheduler import WallpaperScheduler
from core.monitor_manager import MonitorManager
from core.cache_manager import WallpaperHistory


THUMB_SIZE = 80


class ThumbnailButton(QPushButton):
    def __init__(self, file_path: str, index: int, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.index = index
        self.setFixedSize(THUMB_SIZE + 8, THUMB_SIZE + 24)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(self._default_style())
        self.setToolTip(os.path.basename(file_path))

    def set_current(self, is_current: bool, is_applied: bool):
        if is_applied:
            self.setStyleSheet(self._applied_style())
        elif is_current:
            self.setStyleSheet(self._current_style())
        else:
            self.setStyleSheet(self._default_style())

    def _base_style(self):
        return """
            QPushButton {
                border: 2px solid transparent;
                border-radius: 6px;
                padding: 2px;
                background-color: #f8f8f8;
            }
        """

    def _default_style(self):
        return self._base_style() + """
            QPushButton { border: 2px solid #e0e0e0; }
            QPushButton:hover { border: 2px solid #90caf9; background-color: #e3f2fd; }
        """

    def _current_style(self):
        return self._base_style() + """
            QPushButton { border: 3px solid #2196f3; background-color: #bbdefb; }
        """

    def _applied_style(self):
        return self._base_style() + """
            QPushButton { border: 3px solid #4caf50; background-color: #c8e6c9; }
        """


class FilmstripWidget(QWidget):
    thumb_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thumbnails: List[ThumbnailButton] = []
        self._scroll_area = QScrollArea(self)
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFixedHeight(THUMB_SIZE + 40)
        self._scroll_area.setStyleSheet("QScrollArea { border: 1px solid #ddd; border-radius: 6px; }")

        self._container = QWidget()
        self._container_layout = QHBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 2, 4, 2)
        self._container_layout.setSpacing(4)
        self._container_layout.addStretch()
        self._scroll_area.setWidget(self._container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll_area)

    def rebuild(self, sequence: List[str], current_idx: int, applied_path: Optional[str]):
        for btn in self._thumbnails:
            self._container_layout.removeWidget(btn)
            btn.deleteLater()
        self._thumbnails.clear()

        stretch_item = self._container_layout.takeAt(0)

        for i, path in enumerate(sequence):
            btn = ThumbnailButton(path, i, self)
            self._load_thumb(btn, path)
            is_current = (i == current_idx)
            is_applied = (applied_path and os.path.abspath(path) == os.path.abspath(applied_path))
            btn.set_current(is_current, is_applied)
            btn.clicked.connect(lambda _, idx=i: self.thumb_clicked.emit(idx))
            self._container_layout.insertWidget(i, btn)
            self._thumbnails.append(btn)

        self._container_layout.addStretch()

        QTimer.singleShot(50, lambda: self._scroll_to_index(current_idx))

    def update_highlight(self, current_idx: int, applied_path: Optional[str]):
        for btn in self._thumbnails:
            is_current = (btn.index == current_idx)
            is_applied = (applied_path and os.path.abspath(btn.file_path) == os.path.abspath(applied_path))
            btn.set_current(is_current, is_applied)

    def _scroll_to_index(self, idx: int):
        if 0 <= idx < len(self._thumbnails):
            btn = self._thumbnails[idx]
            self._scroll_area.ensureWidgetVisible(btn, THUMB_SIZE, 0)

    def _load_thumb(self, btn: ThumbnailButton, path: str):
        try:
            img = Image.open(path)
            img.thumbnail((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg.copy()).scaled(
                THUMB_SIZE, THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            btn.setIcon(QIcon(pixmap))
            btn.setIconSize(QSize(THUMB_SIZE, THUMB_SIZE))
            btn.setText("")
        except Exception:
            btn.setText(os.path.basename(path)[:6])


class MainWindow(QWidget):
    def __init__(
        self,
        config: AppConfig,
        scheduler: WallpaperScheduler,
        monitor_manager: MonitorManager,
        history: WallpaperHistory,
    ):
        super().__init__()
        self._config = config
        self._scheduler = scheduler
        self._monitor_manager = monitor_manager
        self._history = history
        self._selected_monitor_id: Optional[str] = None
        self._init_ui()
        self._refresh_folder_list()
        self._refresh_preview()
        self._connect_signals()
        self.setWindowTitle("壁纸自动切换器")
        self.resize(1100, 780)

    def _init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_center_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([220, 600, 200])
        main_layout.addWidget(splitter)

    def _build_left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("📁 壁纸来源文件夹")
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 4px;
            }
            QListWidget::item {
                padding: 6px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #e0e8ff;
            }
        """)
        layout.addWidget(self.folder_list, 1)

        btn_layout = QHBoxLayout()
        self.btn_add_folder = QPushButton("➕ 添加")
        self.btn_add_folder.setStyleSheet(self._btn_style())
        self.btn_remove_folder = QPushButton("🗑️ 移除")
        self.btn_remove_folder.setStyleSheet(self._btn_style("#f44336", "#d32f2f"))
        btn_layout.addWidget(self.btn_add_folder)
        btn_layout.addWidget(self.btn_remove_folder)
        layout.addLayout(btn_layout)

        self.lbl_pool_size = QLabel(f"共 {self._scheduler.get_pool_size()} 张壁纸")
        self.lbl_pool_size.setStyleSheet("color: #666; padding: 4px;")
        layout.addWidget(self.lbl_pool_size)

        sep = QLabel("—" * 30)
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet("color: #ccc; padding: 8px 0;")
        layout.addWidget(sep)

        history_title = QLabel("📜 切换历史（最近）")
        history_title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(history_title)

        self.history_list = QListWidget()
        self.history_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 4px;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 4px;
                border-bottom: 1px solid #f0f0f0;
            }
        """)
        layout.addWidget(self.history_list, 1)

        btn_clear_history = QPushButton("清空历史")
        btn_clear_history.setStyleSheet(self._btn_style("#9e9e9e", "#757575"))
        btn_clear_history.clicked.connect(self._clear_history)
        layout.addWidget(btn_clear_history)

        return panel

    def _build_center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.addWidget(QLabel("🖼️ 壁纸预览"))
        header.addStretch()
        layout.addLayout(header)

        monitor_bar = QHBoxLayout()
        monitor_bar.addWidget(QLabel("显示器："))
        self.monitor_combo = QPushButton()
        self.monitor_combo.setStyleSheet(self._btn_style("#4caf50", "#388e3c"))
        monitor_bar.addWidget(self.monitor_combo)
        monitor_bar.addStretch()
        self.lbl_monitor_info = QLabel("")
        self.lbl_monitor_info.setStyleSheet("color: #666; font-size: 11px;")
        monitor_bar.addWidget(self.lbl_monitor_info)
        layout.addLayout(monitor_bar)
        self._update_monitor_combo()

        self.preview_label = QLabel("请添加壁纸文件夹后开始")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setMinimumSize(480, 300)
        self.preview_label.setStyleSheet("""
            QLabel {
                border: 2px dashed #ccc;
                border-radius: 12px;
                background-color: #fafafa;
                color: #999;
                font-size: 14px;
                padding: 20px;
            }
        """)
        self.preview_label.setScaledContents(False)
        layout.addWidget(self.preview_label, 1)

        self.lbl_current_path = QLabel("")
        self.lbl_current_path.setStyleSheet("color: #666; font-size: 11px; padding: 4px;")
        self.lbl_current_path.setWordWrap(True)
        layout.addWidget(self.lbl_current_path)

        position_bar = QHBoxLayout()
        self.lbl_position = QLabel("0 / 0")
        self.lbl_position.setStyleSheet("color: #1976d2; font-size: 12px; font-weight: bold; padding: 2px 8px;")
        position_bar.addWidget(self.lbl_position)
        self.lbl_mode_hint = QLabel("")
        self.lbl_mode_hint.setStyleSheet("color: #999; font-size: 11px; padding: 2px;")
        position_bar.addWidget(self.lbl_mode_hint)
        position_bar.addStretch()
        layout.addLayout(position_bar)

        self.filmstrip = FilmstripWidget()
        layout.addWidget(self.filmstrip)

        ctrl_layout = QHBoxLayout()
        ctrl_layout.setSpacing(8)

        self.btn_prev = QPushButton("⏮️ 上一张")
        self.btn_prev.setStyleSheet(self._btn_style("#2196f3", "#1976d2"))
        self.btn_next = QPushButton("下一张 ⏭️")
        self.btn_next.setStyleSheet(self._btn_style("#4caf50", "#388e3c"))
        self.btn_skip = QPushButton("⏩ 跳过并应用")
        self.btn_skip.setStyleSheet(self._btn_style("#9c27b0", "#7b1fa2"))
        self.btn_apply = QPushButton("✔️ 应用当前预览")
        self.btn_apply.setStyleSheet(self._btn_style("#ff9800", "#f57c00"))

        for btn in [self.btn_prev, self.btn_next, self.btn_skip, self.btn_apply]:
            btn.setMinimumHeight(38)
            ctrl_layout.addWidget(btn)
        layout.addLayout(ctrl_layout)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel("⚙️ 设置")
        title.setStyleSheet("font-size: 14px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        layout.addWidget(QLabel("切换间隔："))
        self.interval_buttons = []
        intervals = [("5 分钟", 5), ("30 分钟", 30), ("1 小时", 60), ("1 天", 1440)]
        current_minutes = self._config.switch_interval_minutes
        for label, minutes in intervals:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.minutes = minutes
            if minutes == current_minutes:
                btn.setChecked(True)
            btn.setStyleSheet(self._interval_btn_style())
            btn.clicked.connect(lambda _, m=minutes, b=btn: self._on_interval_changed(m, b))
            self.interval_buttons.append(btn)
            layout.addWidget(btn)

        layout.addSpacing(8)
        layout.addWidget(QLabel("切换模式："))
        self.mode_buttons = []
        modes = [("顺序", "sequential"), ("随机", "random"), ("按修改时间", "mtime")]
        current_mode = self._config.switch_mode
        for label, mode in modes:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.mode = mode
            if mode == current_mode:
                btn.setChecked(True)
            btn.setStyleSheet(self._interval_btn_style())
            btn.clicked.connect(lambda _, m=mode, b=btn: self._on_mode_changed(m, b))
            self.mode_buttons.append(btn)
            layout.addWidget(btn)

        layout.addSpacing(8)
        layout.addWidget(QLabel("运行控制："))

        self.chk_per_monitor = QPushButton(
            "🖥️ 多显示器独立壁纸：" + ("开启" if self._config.per_monitor_wallpaper else "关闭")
        )
        self.chk_per_monitor.setCheckable(True)
        self.chk_per_monitor.setChecked(self._config.per_monitor_wallpaper)
        self.chk_per_monitor.setStyleSheet(self._interval_btn_style())
        self.chk_per_monitor.clicked.connect(self._on_per_monitor_toggle)
        layout.addWidget(self.chk_per_monitor)

        self.btn_toggle_run = QPushButton("▶️ 启动自动切换")
        self.btn_toggle_run.setStyleSheet(self._btn_style("#4caf50", "#388e3c"))
        self.btn_toggle_run.setMinimumHeight(45)
        layout.addWidget(self.btn_toggle_run)

        self.lbl_status = QLabel("状态：未启动")
        self.lbl_status.setStyleSheet("color: #f44336; padding: 4px; font-weight: bold;")
        self.lbl_countdown = QLabel("")
        self.lbl_countdown.setStyleSheet("color: #666; padding: 2px; font-size: 11px;")
        layout.addWidget(self.lbl_status)
        layout.addWidget(self.lbl_countdown)

        layout.addStretch()

        btn_clear_cache = QPushButton("🗑️ 清空缓存")
        btn_clear_cache.setStyleSheet(self._btn_style("#9e9e9e", "#757575"))
        btn_clear_cache.clicked.connect(self._clear_cache)
        layout.addWidget(btn_clear_cache)

        return panel

    def _btn_style(self, bg: str = "#2196f3", hover: str = "#1976d2") -> str:
        return f"""
            QPushButton {{
                background-color: {bg};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
            QPushButton:pressed {{
                padding-top: 9px;
            }}
            QPushButton:disabled {{
                background-color: #bbb;
            }}
        """

    def _interval_btn_style(self) -> str:
        return """
            QPushButton {
                background-color: #f5f5f5;
                color: #333;
                border: 1px solid #ddd;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
                text-align: left;
            }
            QPushButton:hover {
                background-color: #e8e8e8;
            }
            QPushButton:checked {
                background-color: #e3f2fd;
                color: #1976d2;
                border: 2px solid #2196f3;
                font-weight: bold;
            }
        """

    def _connect_signals(self):
        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_remove_folder.clicked.connect(self._remove_folder)
        self.btn_next.clicked.connect(lambda: self._on_browse(forward=True))
        self.btn_prev.clicked.connect(lambda: self._on_browse(forward=False))
        self.btn_skip.clicked.connect(self._on_skip)
        self.btn_apply.clicked.connect(self._on_apply_selected)
        self.btn_toggle_run.clicked.connect(self._toggle_scheduler)
        self.monitor_combo.clicked.connect(self._show_monitor_menu)
        self._scheduler.wallpaper_changed.connect(self._on_wallpaper_changed)
        self._scheduler.preview_changed.connect(self._on_preview_changed)
        self._scheduler.browse_sequence_changed.connect(self._on_browse_sequence_changed)
        self._scheduler.schedule_updated.connect(self._on_schedule_updated)
        self.history_list.itemDoubleClicked.connect(self._on_history_double_clicked)
        self.history_list.itemClicked.connect(self._on_history_clicked)
        self.filmstrip.thumb_clicked.connect(self._on_thumb_clicked)

    def _update_monitor_combo(self):
        monitors = self._monitor_manager.get_monitors()
        if not monitors:
            self.monitor_combo.setText("未检测到显示器")
            return
        if self._selected_monitor_id is None:
            primary = self._monitor_manager.get_primary_monitor()
            self._selected_monitor_id = primary.monitor_id if primary else monitors[0].monitor_id
        current = self._monitor_manager.get_monitor_by_id(self._selected_monitor_id)
        if current:
            mark = "⭐ " if current.is_primary else ""
            self.monitor_combo.setText(f"{mark}显示器 {int(current.monitor_id)+1} ({current.width}x{current.height})")
            self.lbl_monitor_info.setText(f"{current.device_name} | 位置({current.left},{current.top})")
        else:
            self._selected_monitor_id = monitors[0].monitor_id
            self._update_monitor_combo()

    def _show_monitor_menu(self):
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        monitors = self._monitor_manager.get_monitors(True)
        for m in monitors:
            mark = " ⭐ 主显示器" if m.is_primary else ""
            action = menu.addAction(f"显示器 {int(m.monitor_id)+1} — {m.width}x{m.height}{mark}")
            action.triggered.connect(lambda _, mid=m.monitor_id: self._select_monitor(mid))
        menu.exec(self.monitor_combo.mapToGlobal(self.monitor_combo.rect().bottomLeft()))

    def _select_monitor(self, monitor_id: str):
        self._selected_monitor_id = monitor_id
        self._update_monitor_combo()
        self._refresh_preview()
        self._refresh_filmstrip()
        self._refresh_history()

    def _refresh_folder_list(self):
        self.folder_list.clear()
        for folder in self._config.source_folders:
            item = QListWidgetItem(f"📂 {folder}")
            item.setData(Qt.UserRole, folder)
            item.setToolTip(folder)
            self.folder_list.addItem(item)
        self.lbl_pool_size.setText(f"共 {self._scheduler.get_pool_size()} 张壁纸")

    def _refresh_preview(self):
        mid = self._selected_monitor_id
        if mid is None:
            monitors = self._monitor_manager.get_monitors()
            if monitors:
                mid = monitors[0].monitor_id
        current = None
        if mid is not None:
            current = self._scheduler.get_preview_wallpaper(mid)
        if not current or not os.path.exists(current):
            current = self._scheduler.get_current_wallpaper(mid) if mid else None
        if not current or not os.path.exists(current):
            pool = self._scheduler.get_pool()
            if pool:
                current = pool[0]
            else:
                self.preview_label.setText("请添加壁纸文件夹后开始")
                self.preview_label.setPixmap(QPixmap())
                self.lbl_current_path.setText("")
                self._update_position_label()
                return
        self._render_preview(current)
        self._update_position_label()

    def _update_position_label(self):
        mid = self._selected_monitor_id or "0"
        pos = self._scheduler.get_browse_position(mid) + 1
        total = self._scheduler.get_browse_total(mid)
        self.lbl_position.setText(f"{pos} / {total}")
        mode_labels = {"sequential": "顺序模式", "random": "随机模式", "mtime": "按修改时间"}
        mode = self._config.switch_mode
        self.lbl_mode_hint.setText(f"({mode_labels.get(mode, mode)})")

    def _render_preview(self, file_path: str):
        if not file_path or not os.path.exists(file_path):
            self.preview_label.setText("无预览")
            self.preview_label.setPixmap(QPixmap())
            self.lbl_current_path.setText(file_path or "")
            return
        try:
            img = Image.open(file_path)
            img.thumbnail((700, 450), Image.LANCZOS)
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            data = img.tobytes("raw", "RGB")
            qimg = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg.copy())
            self.preview_label.setPixmap(pixmap)
            self.preview_label.setText("")
            mid = self._selected_monitor_id
            tag = ""
            if mid is not None:
                cur = self._scheduler.get_current_wallpaper(mid)
                if cur and os.path.abspath(cur) == os.path.abspath(file_path):
                    tag = "  [当前桌面]"
                else:
                    tag = "  [预览中 - 尚未应用]"
            self.lbl_current_path.setText(f"📄 {file_path}{tag}")
        except Exception as e:
            self.preview_label.setText(f"无法加载预览：\n{file_path}\n{e}")
            self.preview_label.setPixmap(QPixmap())
            self.lbl_current_path.setText(file_path)

    def _refresh_filmstrip(self):
        mid = self._selected_monitor_id or "0"
        seq = self._scheduler.get_browse_sequence(mid)
        pos = self._scheduler.get_browse_position(mid)
        applied = self._scheduler.get_current_wallpaper(mid)
        self.filmstrip.rebuild(seq, pos, applied)

    def _refresh_history(self):
        self.history_list.clear()
        items = self._history.get_history(self._selected_monitor_id)
        for rec in items[:30]:
            from datetime import datetime
            try:
                t = datetime.fromisoformat(rec["time"]).strftime("%H:%M:%S")
            except Exception:
                t = rec["time"]
            path = rec["path"]
            name = os.path.basename(path)
            item = QListWidgetItem(f"[{t}] {name}")
            item.setData(Qt.UserRole, path)
            item.setToolTip(path)
            self.history_list.addItem(item)

    def _add_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "选择壁纸文件夹", "")
        if folder:
            if self._config.add_folder(folder):
                self._scheduler.refresh_settings()
                self._refresh_folder_list()
                self._refresh_preview()
                self._refresh_filmstrip()
                QMessageBox.information(self, "成功", f"已添加文件夹：{folder}")
            else:
                QMessageBox.warning(self, "提示", "文件夹已存在或无效")

    def _remove_folder(self):
        current = self.folder_list.currentItem()
        if not current:
            QMessageBox.information(self, "提示", "请先选择要移除的文件夹")
            return
        folder = current.data(Qt.UserRole)
        if QMessageBox.question(self, "确认", f"确定要移除文件夹？\n{folder}") == QMessageBox.Yes:
            if self._config.remove_folder(folder):
                self._scheduler.refresh_settings()
                self._refresh_folder_list()
                self._refresh_preview()
                self._refresh_filmstrip()

    def _on_interval_changed(self, minutes: int, selected_btn):
        for btn in self.interval_buttons:
            btn.setChecked(btn is selected_btn)
        self._config.switch_interval_minutes = minutes
        self._config.save()
        self._scheduler.refresh_settings()

    def _on_mode_changed(self, mode: str, selected_btn):
        for btn in self.mode_buttons:
            btn.setChecked(btn is selected_btn)
        self._config.switch_mode = mode
        self._config.save()
        self._scheduler.rebuild_browse()
        self._refresh_preview()
        self._refresh_filmstrip()
        self._update_position_label()

    def _on_per_monitor_toggle(self):
        checked = self.chk_per_monitor.isChecked()
        self._config.per_monitor_wallpaper = checked
        self._config.save()
        self.chk_per_monitor.setText(
            "🖥️ 多显示器独立壁纸：" + ("开启" if checked else "关闭")
        )
        self._scheduler.refresh_settings()
        self._refresh_preview()
        self._refresh_filmstrip()

    def _on_browse(self, forward: bool):
        if self._scheduler.get_pool_size() == 0:
            QMessageBox.information(self, "提示", "请先添加壁纸文件夹")
            return
        mid = self._selected_monitor_id if self._config.per_monitor_wallpaper else None
        if forward:
            self._scheduler.peek_next(mid)
        else:
            self._scheduler.peek_prev(mid)

    def _on_skip(self):
        if self._scheduler.get_pool_size() == 0:
            QMessageBox.information(self, "提示", "请先添加壁纸文件夹")
            return
        if self._config.per_monitor_wallpaper:
            self._scheduler.switch_next(self._selected_monitor_id)
        else:
            self._scheduler.switch_next()

    def _on_apply_selected(self):
        mid = self._selected_monitor_id if self._config.per_monitor_wallpaper else None
        applied = self._scheduler.apply_preview(mid)
        if applied:
            return
        path_text = self.lbl_current_path.text()
        if not path_text:
            return
        path = path_text.split("  [", 1)[0].replace("📄 ", "").strip()
        if path and os.path.exists(path):
            if self._config.per_monitor_wallpaper:
                self._scheduler.switch_to(path, self._selected_monitor_id)
            else:
                self._scheduler.switch_to(path)

    def _on_thumb_clicked(self, idx: int):
        mid = self._selected_monitor_id or "0"
        self._scheduler.peek_at_index(mid, idx)

    def _toggle_scheduler(self):
        if self._scheduler.is_running():
            self._scheduler.stop()
            self.btn_toggle_run.setText("▶️ 启动自动切换")
            self.btn_toggle_run.setStyleSheet(self._btn_style("#4caf50", "#388e3c"))
            self.lbl_status.setText("状态：已停止")
            self.lbl_status.setStyleSheet("color: #f44336; padding: 4px; font-weight: bold;")
            self.lbl_countdown.setText("")
        else:
            if self._scheduler.get_pool_size() == 0:
                QMessageBox.warning(self, "提示", "请先添加壁纸文件夹")
                return
            self._scheduler.start()
            self.btn_toggle_run.setText("⏸️ 停止自动切换")
            self.btn_toggle_run.setStyleSheet(self._btn_style("#ff9800", "#f57c00"))
            self.lbl_status.setText("状态：运行中")
            self.lbl_status.setStyleSheet("color: #4caf50; padding: 4px; font-weight: bold;")
            self._update_countdown()

    def _update_countdown(self):
        if not self._scheduler.is_running():
            return
        remaining_ms = self._scheduler._timer.remainingTime()
        if remaining_ms > 0:
            mins = remaining_ms // 60000
            secs = (remaining_ms % 60000) // 1000
            self.lbl_countdown.setText(f"下次切换：{mins}分{secs}秒后")
        QTimer.singleShot(1000, self._update_countdown)

    def _on_wallpaper_changed(self, wallpapers: dict):
        self._scheduler.reset_preview()
        self._refresh_preview()
        self._refresh_filmstrip()
        self._refresh_history()

    def _on_preview_changed(self, monitor_id: str, file_path: str):
        if monitor_id == self._selected_monitor_id or not self._config.per_monitor_wallpaper:
            self._render_preview(file_path)
            self._update_position_label()
            mid = self._selected_monitor_id or "0"
            pos = self._scheduler.get_browse_position(mid)
            applied = self._scheduler.get_current_wallpaper(mid)
            self.filmstrip.update_highlight(pos, applied)

    def _on_browse_sequence_changed(self, monitor_id: str):
        if monitor_id == self._selected_monitor_id or not self._config.per_monitor_wallpaper:
            self._refresh_filmstrip()

    def _on_schedule_updated(self, minutes: int):
        pass

    def _on_history_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if not path or not os.path.exists(path):
            return
        mid = self._selected_monitor_id if self._config.per_monitor_wallpaper else None
        if mid is not None:
            self._scheduler.reset_preview(mid)
        else:
            self._scheduler.reset_preview()
        self._render_preview(path)
        self.lbl_current_path.setText(f"📄 {path}  [从历史预览 - 尚未应用]")
        mid = self._selected_monitor_id or "0"
        pos = self._scheduler.get_browse_position(mid)
        applied = self._scheduler.get_current_wallpaper(mid)
        self.filmstrip.update_highlight(pos, applied)

    def _on_history_double_clicked(self, item: QListWidgetItem):
        path = item.data(Qt.UserRole)
        if path and os.path.exists(path):
            if QMessageBox.question(self, "确认", f"应用此壁纸到桌面？\n{path}") == QMessageBox.Yes:
                if self._config.per_monitor_wallpaper:
                    self._scheduler.switch_to(path, self._selected_monitor_id)
                else:
                    self._scheduler.switch_to(path)

    def _clear_history(self):
        if QMessageBox.question(self, "确认", "确定要清空切换历史？") == QMessageBox.Yes:
            self._history.clear()
            self._refresh_history()

    def _clear_cache(self):
        from core.cache_manager import WallpaperCache
        cache = WallpaperCache()
        cache.clear()
        QMessageBox.information(self, "成功", "壁纸缓存已清空")

    def closeEvent(self, event):
        if self._config.min_to_tray:
            event.ignore()
            self.hide()
        else:
            event.accept()
