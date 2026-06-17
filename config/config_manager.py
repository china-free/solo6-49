import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List


APP_NAME = "WallpaperSwitcher"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), f".{APP_NAME.lower()}")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


@dataclass
class AppConfig:
    source_folders: List[str] = field(default_factory=list)
    switch_interval_minutes: int = 30
    switch_mode: str = "random"
    per_monitor_wallpaper: bool = False
    startup_with_system: bool = False
    min_to_tray: bool = True
    current_indexes: dict = field(default_factory=dict)

    @classmethod
    def load(cls) -> "AppConfig":
        if not os.path.exists(CONFIG_FILE):
            return cls()
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls(**data)
        except (json.JSONDecodeError, TypeError):
            return cls()

    def save(self) -> None:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    def add_folder(self, folder_path: str) -> bool:
        folder = str(Path(folder_path).resolve())
        if folder not in self.source_folders and os.path.isdir(folder):
            self.source_folders.append(folder)
            self.save()
            return True
        return False

    def remove_folder(self, folder_path: str) -> bool:
        folder = str(Path(folder_path).resolve())
        if folder in self.source_folders:
            self.source_folders.remove(folder)
            self.save()
            return True
        return False


VALID_INTERVALS = {
    "5 分钟": 5,
    "30 分钟": 30,
    "1 小时": 60,
    "1 天": 1440,
}

VALID_MODES = ["顺序", "随机", "按修改时间"]
VALID_MODES_MAP = {
    "顺序": "sequential",
    "随机": "random",
    "按修改时间": "mtime",
}
