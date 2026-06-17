import os
import random
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime
from PySide6.QtCore import QObject, QTimer, Signal

from config.config_manager import AppConfig
from core.monitor_manager import MonitorManager
from core.wallpaper_setter import WallpaperSetter
from core.cache_manager import WallpaperCache, WallpaperHistory


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tiff", ".tif"}


class WallpaperScheduler(QObject):
    wallpaper_changed = Signal(dict)
    next_wallpaper_selected = Signal(str, str)
    schedule_updated = Signal(int)

    def __init__(
        self,
        config: AppConfig,
        monitor_manager: MonitorManager,
        wallpaper_setter: WallpaperSetter,
        cache: WallpaperCache,
        history: WallpaperHistory,
    ):
        super().__init__()
        self._config = config
        self._monitor_manager = monitor_manager
        self._setter = wallpaper_setter
        self._cache = cache
        self._history = history
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.switch_next)
        self._is_running = False
        self._wallpaper_pool: List[str] = []
        self._current_wallpapers: Dict[str, str] = {}
        self._refresh_pool()
        self._apply_interval()

    def _refresh_pool(self):
        self._wallpaper_pool = []
        for folder in self._config.source_folders:
            if not os.path.isdir(folder):
                continue
            for root, dirs, files in os.walk(folder):
                for f in files:
                    ext = Path(f).suffix.lower()
                    if ext in IMAGE_EXTENSIONS:
                        self._wallpaper_pool.append(os.path.join(root, f))
        if self._config.switch_mode == "mtime":
            self._wallpaper_pool.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
        elif self._config.switch_mode == "sequential":
            self._wallpaper_pool.sort()

    def _apply_interval(self):
        minutes = self._config.switch_interval_minutes
        self._timer.setInterval(max(1, minutes) * 60 * 1000)
        self.schedule_updated.emit(minutes)

    def get_pool_size(self) -> int:
        return len(self._wallpaper_pool)

    def get_pool(self) -> List[str]:
        return list(self._wallpaper_pool)

    def get_current_wallpaper(self, monitor_id: str) -> Optional[str]:
        return self._current_wallpapers.get(monitor_id)

    def get_all_current(self) -> Dict[str, str]:
        return dict(self._current_wallpapers)

    def is_running(self) -> bool:
        return self._is_running

    def start(self):
        if not self._wallpaper_pool:
            return
        if not self._is_running:
            self._is_running = True
            self._apply_interval()
            self._timer.start()

    def stop(self):
        self._is_running = False
        self._timer.stop()

    def refresh_settings(self):
        self._refresh_pool()
        self._apply_interval()
        if self._is_running and not self._timer.isActive():
            self._timer.start()

    def _select_next(self, monitor_id: str) -> Optional[str]:
        if not self._wallpaper_pool:
            return None
        mode = self._config.switch_mode
        if mode == "random":
            candidates = [p for p in self._wallpaper_pool if p != self._current_wallpapers.get(monitor_id)]
            if not candidates:
                candidates = self._wallpaper_pool
            return random.choice(candidates)
        else:
            idx_key = str(monitor_id)
            idx = self._config.current_indexes.get(idx_key, 0)
            if not isinstance(idx, int):
                idx = 0
            idx = (idx + 1) % len(self._wallpaper_pool)
            self._config.current_indexes[idx_key] = idx
            self._config.save()
            return self._wallpaper_pool[idx]

    def _select_next_for_all(self) -> Dict[str, str]:
        monitors = self._monitor_manager.get_monitors()
        wallpapers = {}
        if self._config.per_monitor_wallpaper:
            used_paths = set(self._current_wallpapers.values())
            for m in monitors:
                candidates = [p for p in self._wallpaper_pool if p not in used_paths]
                if not candidates:
                    candidates = self._wallpaper_pool
                    used_paths.clear()
                if self._config.switch_mode == "random":
                    path = random.choice(candidates) if candidates else None
                else:
                    idx_key = str(m.monitor_id)
                    idx = self._config.current_indexes.get(idx_key, -1)
                    if not isinstance(idx, int):
                        idx = -1
                    idx = (idx + 1) % len(self._wallpaper_pool)
                    self._config.current_indexes[idx_key] = idx
                    path = self._wallpaper_pool[idx]
                if path:
                    wallpapers[m.monitor_id] = path
                    used_paths.add(path)
            self._config.save()
        else:
            path = self._select_next(monitors[0].monitor_id) if monitors else None
            if path:
                for m in monitors:
                    wallpapers[m.monitor_id] = path
        return wallpapers

    def switch_next(self, monitor_id: Optional[str] = None) -> bool:
        self._refresh_pool()
        if not self._wallpaper_pool:
            return False
        if monitor_id:
            path = self._select_next(monitor_id)
            if not path:
                return False
            self.next_wallpaper_selected.emit(monitor_id, path)
            monitor = self._monitor_manager.get_monitor_by_id(monitor_id)
            if monitor:
                prepared = self._setter.prepare_image_for_monitor(path, monitor)
            else:
                prepared = path
            result = self._setter.set_wallpaper_single(monitor_id, prepared)
            if result:
                self._current_wallpapers[monitor_id] = path
                self._history.add_record(monitor_id, path)
                self.wallpaper_changed.emit({monitor_id: path})
            return result
        else:
            wallpapers = self._select_next_for_all()
            if not wallpapers:
                return False
            prepared_wps = {}
            monitors = self._monitor_manager.get_monitors()
            for mid, path in wallpapers.items():
                self.next_wallpaper_selected.emit(mid, path)
                monitor = next((m for m in monitors if m.monitor_id == mid), None)
                if monitor:
                    prepared_wps[mid] = self._setter.prepare_image_for_monitor(path, monitor)
                else:
                    prepared_wps[mid] = path
            result = self._setter.set_wallpaper_multiple(prepared_wps)
            if result:
                self._current_wallpapers.update(wallpapers)
                for mid, path in wallpapers.items():
                    self._history.add_record(mid, path)
                self.wallpaper_changed.emit(wallpapers)
            return result

    def switch_to(self, file_path: str, monitor_id: Optional[str] = None) -> bool:
        if not os.path.exists(file_path):
            return False
        monitors = self._monitor_manager.get_monitors()
        if monitor_id:
            self.next_wallpaper_selected.emit(monitor_id, file_path)
            monitor = self._monitor_manager.get_monitor_by_id(monitor_id)
            prepared = self._setter.prepare_image_for_monitor(file_path, monitor) if monitor else file_path
            result = self._setter.set_wallpaper_single(monitor_id, prepared)
            if result:
                self._current_wallpapers[monitor_id] = file_path
                self._history.add_record(monitor_id, file_path)
                self.wallpaper_changed.emit({monitor_id: file_path})
            return result
        else:
            wallpapers = {}
            prepared_wps = {}
            for m in monitors:
                wallpapers[m.monitor_id] = file_path
                self.next_wallpaper_selected.emit(m.monitor_id, file_path)
                prepared_wps[m.monitor_id] = self._setter.prepare_image_for_monitor(file_path, m)
            result = self._setter.set_wallpaper_multiple(prepared_wps)
            if result:
                self._current_wallpapers.update(wallpapers)
                for mid in wallpapers:
                    self._history.add_record(mid, file_path)
                self.wallpaper_changed.emit(wallpapers)
            return result

    def skip_current(self, monitor_id: Optional[str] = None) -> bool:
        return self.switch_next(monitor_id)
