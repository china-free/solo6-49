import os
import random
from pathlib import Path
from typing import List, Optional, Dict, Tuple
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
    browse_sequence_changed = Signal(str)
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
        self._browse_sequences: Dict[str, List[str]] = {}
        self._browse_positions: Dict[str, int] = {}
        self._refresh_pool()
        self._rebuild_browse_sequences()
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

    def _sort_pool_by_mode(self, pool: List[str]) -> List[str]:
        result = list(pool)
        if self._config.switch_mode == "mtime":
            result.sort(key=lambda p: os.path.getmtime(p) if os.path.exists(p) else 0)
        elif self._config.switch_mode == "sequential":
            result.sort()
        elif self._config.switch_mode == "random":
            random.shuffle(result)
        return result

    def _rebuild_browse_sequences(self):
        old_seqs = dict(self._browse_sequences)
        old_pos = dict(self._browse_positions)
        self._browse_sequences.clear()
        self._browse_positions.clear()
        monitors = self._monitor_manager.get_monitors()
        if not monitors:
            monitors = [type('M', (), {'monitor_id': '0'})()]
        for m in monitors:
            mid = m.monitor_id
            seq = self._sort_pool_by_mode(self._wallpaper_pool)
            self._browse_sequences[mid] = seq
            cur = self._current_wallpapers.get(mid)
            if cur and cur in seq:
                self._browse_positions[mid] = seq.index(cur)
            elif mid in old_pos and mid in old_seqs:
                old_path = old_seqs[mid][old_pos[mid]] if old_pos[mid] < len(old_seqs[mid]) else None
                if old_path and old_path in seq:
                    self._browse_positions[mid] = seq.index(old_path)
                else:
                    self._browse_positions[mid] = 0
            else:
                self._browse_positions[mid] = 0
            self.browse_sequence_changed.emit(mid)

    def _apply_interval(self):
        minutes = self._config.switch_interval_minutes
        self._timer.setInterval(max(1, minutes) * 60 * 1000)
        self.schedule_updated.emit(minutes)

    def get_pool_size(self) -> int:
        return len(self._wallpaper_pool)

    def get_pool(self) -> List[str]:
        return list(self._wallpaper_pool)

    def get_browse_sequence(self, monitor_id: str) -> List[str]:
        return list(self._browse_sequences.get(monitor_id, []))

    def get_browse_position(self, monitor_id: str) -> int:
        return self._browse_positions.get(monitor_id, 0)

    def get_browse_total(self, monitor_id: str) -> int:
        return len(self._browse_sequences.get(monitor_id, []))

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
        self._rebuild_browse_sequences()
        self._apply_interval()
        if self._is_running and not self._timer.isActive():
            self._timer.start()

    def rebuild_browse(self):
        self._refresh_pool()
        self._rebuild_browse_sequences()

    def _resolve_preview_monitor(self, monitor_id: Optional[str]) -> Optional[str]:
        if monitor_id is not None:
            return monitor_id
        if self._config.per_monitor_wallpaper:
            primary = self._monitor_manager.get_primary_monitor()
            return primary.monitor_id if primary else None
        monitors = self._monitor_manager.get_monitors()
        return monitors[0].monitor_id if monitors else None

    def _path_at_browse(self, monitor_id: str, idx: int) -> Optional[str]:
        seq = self._browse_sequences.get(monitor_id, [])
        if not seq:
            return None
        return seq[idx % len(seq)]

    def peek_at_index(self, monitor_id: str, idx: int) -> Optional[str]:
        seq = self._browse_sequences.get(monitor_id, [])
        if not seq:
            return None
        idx = max(0, min(idx, len(seq) - 1))
        path = seq[idx]
        self._browse_positions[monitor_id] = idx
        self._preview_wallpapers[monitor_id] = path
        self.preview_changed.emit(monitor_id, path)
        return path

    def peek_next(self, monitor_id: Optional[str] = None) -> Optional[str]:
        mid = self._resolve_preview_monitor(monitor_id)
        if mid is None:
            return None
        seq = self._browse_sequences.get(mid, [])
        if not seq:
            return None
        pos = self._browse_positions.get(mid, 0)
        new_pos = (pos + 1) % len(seq)
        self._browse_positions[mid] = new_pos
        path = seq[new_pos]
        self._preview_wallpapers[mid] = path
        self.preview_changed.emit(mid, path)
        return path

    def peek_prev(self, monitor_id: Optional[str] = None) -> Optional[str]:
        mid = self._resolve_preview_monitor(monitor_id)
        if mid is None:
            return None
        seq = self._browse_sequences.get(mid, [])
        if not seq:
            return None
        pos = self._browse_positions.get(mid, 0)
        new_pos = (pos - 1) % len(seq)
        self._browse_positions[mid] = new_pos
        path = seq[new_pos]
        self._preview_wallpapers[mid] = path
        self.preview_changed.emit(mid, path)
        return path

    def reset_preview(self, monitor_id: Optional[str] = None):
        if monitor_id is None:
            for mid in list(self._preview_wallpapers.keys()):
                self._preview_wallpapers.pop(mid, None)
                cur = self._current_wallpapers.get(mid)
                if cur:
                    seq = self._browse_sequences.get(mid, [])
                    if cur in seq:
                        self._browse_positions[mid] = seq.index(cur)
                    self.preview_changed.emit(mid, cur)
        else:
            self._preview_wallpapers.pop(monitor_id, None)
            cur = self._current_wallpapers.get(monitor_id)
            if cur:
                seq = self._browse_sequences.get(monitor_id, [])
                if cur in seq:
                    self._browse_positions[monitor_id] = seq.index(cur)
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
            seq = self._browse_sequences.get(monitor_id, self._wallpaper_pool)
            pos = self._browse_positions.get(monitor_id, 0)
            new_pos = (pos + 1) % max(1, len(seq))
            self._browse_positions[monitor_id] = new_pos
            if seq:
                return seq[new_pos]
            return self._wallpaper_pool[new_pos % len(self._wallpaper_pool)] if self._wallpaper_pool else None

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
            seq = self._browse_sequences.get(monitor_id, self._wallpaper_pool)
            pos = self._browse_positions.get(monitor_id, 0)
            new_pos = (pos - 1) % max(1, len(seq))
            self._browse_positions[monitor_id] = new_pos
            if seq:
                return seq[new_pos]
            pos2 = (pos - 1) % len(self._wallpaper_pool)
            return self._wallpaper_pool[pos2]

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
                    path = self._select_next(m.monitor_id) if forward else self._select_prev(m.monitor_id)
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
                seq = self._browse_sequences.get(monitor_id, [])
                if path in seq:
                    self._browse_positions[monitor_id] = seq.index(path)
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
                for mid, path in wallpapers.items():
                    self._preview_wallpapers.pop(mid, None)
                    seq = self._browse_sequences.get(mid, [])
                    if path in seq:
                        self._browse_positions[mid] = seq.index(path)
                    self._history.add_record(mid, path)
                self.wallpaper_changed.emit(wallpapers)
            return result

    def switch_to(self, file_path: str, monitor_id: Optional[str] = None) -> bool:
        if not os.path.exists(file_path):
            return False
        file_path = str(Path(file_path).resolve())
        monitors = self._monitor_manager.get_monitors()
        if monitor_id:
            self.next_wallpaper_selected.emit(monitor_id, file_path)
            seq = self._browse_sequences.get(monitor_id, [])
            if file_path in seq:
                self._browse_positions[monitor_id] = seq.index(file_path)
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
                wallpapers[m.monitor_id] = file_path
                self.next_wallpaper_selected.emit(m.monitor_id, file_path)
                seq = self._browse_sequences.get(m.monitor_id, [])
                if file_path in seq:
                    self._browse_positions[m.monitor_id] = seq.index(file_path)
                prepared_wps[m.monitor_id] = self._setter.prepare_image_for_monitor(file_path, m)
            result = self._setter.set_wallpaper_multiple(prepared_wps)
            if result:
                self._current_wallpapers.update(wallpapers)
                for mid in wallpapers:
                    self._preview_wallpapers.pop(mid, None)
                    self._history.add_record(mid, file_path)
                self.wallpaper_changed.emit(wallpapers)
            return result
