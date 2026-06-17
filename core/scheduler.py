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
    preview_changed = Signal(str, str)
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
        self._preview_wallpapers: Dict[str, str] = {}
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

    def get_preview_wallpaper(self, monitor_id: str) -> Optional[str]:
        if monitor_id in self._preview_wallpapers:
            return self._preview_wallpapers[monitor_id]
        return self.get_current_wallpaper(monitor_id)

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

    def _resolve_preview_monitor(self, monitor_id: Optional[str]) -> Optional[str]:
        if monitor_id is not None:
            return monitor_id
        if self._config.per_monitor_wallpaper:
            primary = self._monitor_manager.get_primary_monitor()
            return primary.monitor_id if primary else None
        monitors = self._monitor_manager.get_monitors()
        return monitors[0].monitor_id if monitors else None

    def _get_index(self, monitor_id: str, default: int = -1) -> int:
        idx_key = f"idx_{monitor_id}"
        idx = self._config.current_indexes.get(idx_key, default)
        if not isinstance(idx, int):
            return default
        return idx

    def _set_index(self, monitor_id: str, idx: int):
        n = len(self._wallpaper_pool)
        if n <= 0:
            return
        idx_key = f"idx_{monitor_id}"
        self._config.current_indexes[idx_key] = idx % n
        self._config.save()

    def _get_preview_index(self, monitor_id: str) -> int:
        idx_key = f"preview_idx_{monitor_id}"
        idx = self._config.current_indexes.get(idx_key)
        if isinstance(idx, int):
            return idx
        ci = self._get_index(monitor_id, 0)
        return ci

    def _set_preview_index(self, monitor_id: str, idx: int):
        n = len(self._wallpaper_pool)
        if n <= 0:
            return
        idx_key = f"preview_idx_{monitor_id}"
        self._config.current_indexes[idx_key] = idx % n
        self._config.save()

    def _path_at(self, idx: int) -> Optional[str]:
        if not self._wallpaper_pool:
            return None
        n = len(self._wallpaper_pool)
        return self._wallpaper_pool[idx % n]

    def _index_of(self, path: Optional[str]) -> int:
        if not path or not self._wallpaper_pool:
            return -1
        try:
            return self._wallpaper_pool.index(path)
        except ValueError:
            return -1

    def _peek(self, monitor_id: str, forward: bool) -> Optional[str]:
        if not self._wallpaper_pool:
            return None
        mode = self._config.switch_mode
        n = len(self._wallpaper_pool)
        if mode == "random":
            current = self._preview_wallpapers.get(
                monitor_id, self._current_wallpapers.get(monitor_id)
            )
            candidates = [p for p in self._wallpaper_pool if p != current]
            if not candidates:
                candidates = self._wallpaper_pool
            return random.choice(candidates)
        else:
            preview_idx = self._get_preview_index(monitor_id)
            if preview_idx < 0 or preview_idx >= n:
                preview_idx = self._index_of(self._current_wallpapers.get(monitor_id))
                if preview_idx < 0:
                    preview_idx = 0
            step = 1 if forward else -1
            new_idx = (preview_idx + step) % n
            if new_idx == preview_idx and n > 1:
                new_idx = (new_idx + step) % n
            self._set_preview_index(monitor_id, new_idx)
            return self._path_at(new_idx)

    def peek_next(self, monitor_id: Optional[str] = None) -> Optional[str]:
        mid = self._resolve_preview_monitor(monitor_id)
        if mid is None:
            return None
        path = self._peek(mid, forward=True)
        if path:
            self._preview_wallpapers[mid] = path
            self.preview_changed.emit(mid, path)
        return path

    def peek_prev(self, monitor_id: Optional[str] = None) -> Optional[str]:
        mid = self._resolve_preview_monitor(monitor_id)
        if mid is None:
            return None
        path = self._peek(mid, forward=False)
        if path:
            self._preview_wallpapers[mid] = path
            self.preview_changed.emit(mid, path)
        return path

    def reset_preview(self, monitor_id: Optional[str] = None):
        if monitor_id is None:
            for mid in list(self._preview_wallpapers.keys()):
                cur = self._current_wallpapers.get(mid)
                if cur is not None:
                    self._set_preview_index(mid, self._index_of(cur))
                    self.preview_changed.emit(mid, cur)
            self._preview_wallpapers.clear()
        else:
            self._preview_wallpapers.pop(monitor_id, None)
            cur = self._current_wallpapers.get(monitor_id)
            if cur is not None:
                self._set_preview_index(monitor_id, self._index_of(cur))
                self.preview_changed.emit(monitor_id, cur)

    def apply_preview(self, monitor_id: Optional[str] = None) -> bool:
        if monitor_id is not None:
            path = self._preview_wallpapers.get(monitor_id)
            if not path:
                return False
            ok = self.switch_to(path, monitor_id)
            if ok:
                self._preview_wallpapers.pop(monitor_id, None)
            return ok
        applied_any = False
        for mid in list(self._preview_wallpapers.keys()):
            path = self._preview_wallpapers[mid]
            if self.switch_to(path, mid):
                applied_any = True
        self._preview_wallpapers.clear()
        return applied_any

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
            idx = self._get_index(monitor_id, -1)
            if idx < 0 or idx >= len(self._wallpaper_pool):
                idx = self._index_of(self._current_wallpapers.get(monitor_id))
            idx = (idx + 1) % len(self._wallpaper_pool)
            self._set_index(monitor_id, idx)
            path = self._path_at(idx)
            self._set_preview_index(monitor_id, idx)
            return path

    def _select_prev(self, monitor_id: str) -> Optional[str]:
        if not self._wallpaper_pool:
            return None
        mode = self._config.switch_mode
        if mode == "random":
            candidates = [p for p in self._wallpaper_pool if p != self._current_wallpapers.get(monitor_id)]
            if not candidates:
                candidates = self._wallpaper_pool
            return random.choice(candidates)
        else:
            idx = self._get_index(monitor_id, 0)
            if idx <= 0 or idx >= len(self._wallpaper_pool):
                idx = self._index_of(self._current_wallpapers.get(monitor_id))
                if idx < 0:
                    idx = 0
            idx = (idx - 1) % len(self._wallpaper_pool)
            self._set_index(monitor_id, idx)
            path = self._path_at(idx)
            self._set_preview_index(monitor_id, idx)
            return path

    def _select_next_for_all(self, forward: bool = True) -> Dict[str, str]:
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
                    idx = self._get_index(m.monitor_id, -1)
                    step = 1 if forward else -1
                    if idx < 0 or idx >= len(self._wallpaper_pool):
                        idx = self._index_of(self._current_wallpapers.get(m.monitor_id))
                        if idx < 0:
                            idx = -1 if forward else 0
                    idx = (idx + step) % max(1, len(self._wallpaper_pool))
                    self._set_index(m.monitor_id, idx)
                    self._set_preview_index(m.monitor_id, idx)
                    path = self._path_at(idx)
                if path:
                    wallpapers[m.monitor_id] = path
                    used_paths.add(path)
        else:
            selector = self._select_next if forward else self._select_prev
            first_mid = monitors[0].monitor_id if monitors else None
            path = selector(first_mid) if first_mid is not None else None
            if path:
                for m in monitors:
                    wallpapers[m.monitor_id] = path
        return wallpapers

    def switch_next(self, monitor_id: Optional[str] = None) -> bool:
        return self._apply_switch(forward=True, monitor_id=monitor_id)

    def switch_prev(self, monitor_id: Optional[str] = None) -> bool:
        return self._apply_switch(forward=False, monitor_id=monitor_id)

    def skip_current(self, monitor_id: Optional[str] = None) -> bool:
        return self.switch_next(monitor_id)

    def _apply_switch(self, forward: bool, monitor_id: Optional[str] = None) -> bool:
        self._refresh_pool()
        if not self._wallpaper_pool:
            return False
        selector = self._select_next if forward else self._select_prev
        if monitor_id:
            path = selector(monitor_id)
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
                self._preview_wallpapers.pop(monitor_id, None)
                self._history.add_record(monitor_id, path)
                self.wallpaper_changed.emit({monitor_id: path})
            return result
        else:
            wallpapers = self._select_next_for_all(forward=forward)
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
                for mid in wallpapers:
                    self._preview_wallpapers.pop(mid, None)
                    self._history.add_record(mid, wallpapers[mid])
                self.wallpaper_changed.emit(wallpapers)
            return result

    def switch_to(self, file_path: str, monitor_id: Optional[str] = None) -> bool:
        if not os.path.exists(file_path):
            return False
        file_path = str(Path(file_path).resolve())
        monitors = self._monitor_manager.get_monitors()
        if monitor_id:
            pool_idx = self._index_of(file_path)
            if pool_idx >= 0:
                self._set_index(monitor_id, pool_idx)
                self._set_preview_index(monitor_id, pool_idx)
            self.next_wallpaper_selected.emit(monitor_id, file_path)
            monitor = self._monitor_manager.get_monitor_by_id(monitor_id)
            prepared = self._setter.prepare_image_for_monitor(file_path, monitor) if monitor else file_path
            result = self._setter.set_wallpaper_single(monitor_id, prepared)
            if result:
                self._current_wallpapers[monitor_id] = file_path
                self._preview_wallpapers.pop(monitor_id, None)
                self._history.add_record(monitor_id, file_path)
                self.wallpaper_changed.emit({monitor_id: file_path})
            return result
        else:
            wallpapers = {}
            prepared_wps = {}
            for m in monitors:
                pool_idx = self._index_of(file_path)
                if pool_idx >= 0:
                    self._set_index(m.monitor_id, pool_idx)
                    self._set_preview_index(m.monitor_id, pool_idx)
                wallpapers[m.monitor_id] = file_path
                self.next_wallpaper_selected.emit(m.monitor_id, file_path)
                prepared_wps[m.monitor_id] = self._setter.prepare_image_for_monitor(file_path, m)
            result = self._setter.set_wallpaper_multiple(prepared_wps)
            if result:
                self._current_wallpapers.update(wallpapers)
                for mid in wallpapers:
                    self._preview_wallpapers.pop(mid, None)
                    self._history.add_record(mid, file_path)
                self.wallpaper_changed.emit(wallpapers)
            return result
