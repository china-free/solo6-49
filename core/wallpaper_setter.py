import os
import sys
import ctypes
import tempfile
from pathlib import Path
from typing import List, Optional, Dict
from PIL import Image

from .monitor_manager import MonitorManager, MonitorInfo


def _is_windows() -> bool:
    return sys.platform == "win32"


class WallpaperSetter:
    SPI_SETDESKWALLPAPER = 0x0014
    SPIF_UPDATEINIFILE = 0x01
    SPIF_SENDCHANGE = 0x02

    def __init__(self, monitor_manager: MonitorManager):
        self._monitor_manager = monitor_manager
        self._com_initialized = False
        self._desktop_wallpaper = None
        if _is_windows():
            try:
                self._init_com()
            except Exception:
                self._desktop_wallpaper = None

    def _init_com(self):
        try:
            import pythoncom
            import win32com.client
            pythoncom.CoInitialize()
            self._desktop_wallpaper = win32com.client.Dispatch(
                "CLSID_DesktopWallpaper"
                if False else "DesktopWallpaper"
            )
            try:
                clsid = "{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}"
                self._desktop_wallpaper = win32com.client.Dispatch(
                    clsid, clsid_ctx=1
                )
            except Exception:
                try:
                    from win32com.client import gencache
                    self._desktop_wallpaper = gencache.EnsureModule(
                        "{7C4BFB39-4A3B-476A-90E5-358CE9A7107C}", 0, 1, 0
                    ).CreateInstance("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
                except Exception:
                    self._desktop_wallpaper = None
            self._com_initialized = True
        except ImportError:
            self._desktop_wallpaper = None
        except Exception:
            self._desktop_wallpaper = None

    def set_wallpaper_all(self, image_path: str) -> bool:
        path = str(Path(image_path).resolve())
        if not os.path.exists(path):
            return False
        if not _is_windows():
            return self._set_wallpaper_nix(path)
        return self._set_system_wallpaper(path)

    def _set_system_wallpaper(self, image_path: str) -> bool:
        try:
            user32 = ctypes.windll.user32
            result = user32.SystemParametersInfoW(
                self.SPI_SETDESKWALLPAPER,
                0,
                image_path,
                self.SPIF_UPDATEINIFILE | self.SPIF_SENDCHANGE
            )
            return bool(result)
        except Exception:
            return False

    def _set_wallpaper_nix(self, image_path: str) -> bool:
        try:
            import subprocess
            if sys.platform == "darwin":
                subprocess.run([
                    "osascript",
                    "-e", f'tell application "Finder" to set desktop picture to POSIX file "{image_path}"'
                ])
                return True
            else:
                subprocess.run(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", f"file://{image_path}"])
                return True
        except Exception:
            return False

    def set_wallpaper_single(self, monitor_id: str, image_path: str) -> bool:
        if not _is_windows():
            return self.set_wallpaper_all(image_path)
        monitors = self._monitor_manager.get_monitors()
        if len(monitors) <= 1:
            return self.set_wallpaper_all(image_path)
        return self._set_wallpaper_per_monitor({monitor_id: image_path})

    def set_wallpaper_multiple(self, monitor_wallpapers: Dict[str, str]) -> bool:
        if not monitor_wallpapers:
            return False
        if not _is_windows():
            first_path = list(monitor_wallpapers.values())[0]
            return self.set_wallpaper_all(first_path)
        return self._set_wallpaper_per_monitor(monitor_wallpapers)

    def _set_wallpaper_per_monitor(self, monitor_wallpapers: Dict[str, str]) -> bool:
        try:
            monitors = self._monitor_manager.get_monitors()
            all_paths = {}
            for m in monitors:
                path = monitor_wallpapers.get(m.monitor_id)
                if path and os.path.exists(path):
                    all_paths[m.monitor_id] = str(Path(path).resolve())
            if not all_paths:
                return False
            success = self._set_via_com(all_paths)
            if not success:
                success = self._set_via_combined_image(monitor_wallpapers)
            return success
        except Exception:
            return self._set_via_combined_image(monitor_wallpapers)

    def _set_via_com(self, monitor_wallpapers: Dict[str, str]) -> bool:
        if not self._desktop_wallpaper:
            return False
        try:
            monitors = self._monitor_manager.get_monitors()
            for i, m in enumerate(monitors):
                if m.monitor_id in monitor_wallpapers:
                    try:
                        self._desktop_wallpaper.SetWallpaper(
                            m.device_name, monitor_wallpapers[m.monitor_id]
                        )
                    except Exception:
                        pass
            try:
                self._desktop_wallpaper.SetPosition(0)
            except Exception:
                pass
            return True
        except Exception:
            return False

    def _set_via_combined_image(self, monitor_wallpapers: Dict[str, str]) -> bool:
        try:
            monitors = self._monitor_manager.get_monitors()
            min_x = min(m.left for m in monitors)
            min_y = min(m.top for m in monitors)
            max_x = max(m.right for m in monitors)
            max_y = max(m.bottom for m in monitors)
            total_w = max_x - min_x
            total_h = max_y - min_y
            if total_w <= 0 or total_h <= 0:
                return False
            combined = Image.new("RGB", (total_w, total_h), (0, 0, 0))
            for m in monitors:
                path = monitor_wallpapers.get(m.monitor_id)
                if not path or not os.path.exists(path):
                    continue
                try:
                    img = Image.open(path)
                    img_w, img_h = img.size
                    m_w, m_h = m.width, m.height
                    scale = max(m_w / img_w, m_h / img_h)
                    new_w = int(img_w * scale)
                    new_h = int(img_h * scale)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    left = (new_w - m_w) // 2
                    top = (new_h - m_h) // 2
                    img = img.crop((left, top, left + m_w, top + m_h))
                    if img.mode != "RGB":
                        img = img.convert("RGB")
                    combined.paste(img, (m.left - min_x, m.top - min_y))
                except Exception:
                    continue
            tmp_path = os.path.join(tempfile.gettempdir(), "wallpaper_combined.jpg")
            combined.save(tmp_path, "JPEG", quality=95)
            return self._set_system_wallpaper(tmp_path)
        except Exception:
            return False

    def prepare_image_for_monitor(self, image_path: str, monitor: MonitorInfo) -> str:
        try:
            img = Image.open(image_path)
            img_w, img_h = img.size
            m_w, m_h = monitor.width, monitor.height
            scale = max(m_w / img_w, m_h / img_h)
            new_w = int(img_w * scale)
            new_h = int(img_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - m_w) // 2
            top = (new_h - m_h) // 2
            img = img.crop((left, top, left + m_w, top + m_h))
            if img.mode != "RGB":
                img = img.convert("RGB")
            import hashlib
            file_hash = hashlib.md5(image_path.encode()).hexdigest()
            tmp_name = f"wp_{monitor.monitor_id}_{file_hash}.jpg"
            tmp_path = os.path.join(tempfile.gettempdir(), tmp_name)
            img.save(tmp_path, "JPEG", quality=95)
            return tmp_path
        except Exception:
            return image_path
