import json
import os
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
from collections import OrderedDict
from PIL import Image


HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".wallpaperswitcher", "history.json")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".wallpaperswitcher", "cache")
MAX_CACHE_SIZE = 200
MAX_HISTORY_ITEMS = 100


class WallpaperCache:
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._cache_index_file = os.path.join(CACHE_DIR, "index.json")
        self._cache: OrderedDict = OrderedDict()
        self._load_index()

    def _load_index(self):
        if os.path.exists(self._cache_index_file):
            try:
                with open(self._cache_index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._cache = OrderedDict(data)
            except (json.JSONDecodeError, TypeError):
                self._cache = OrderedDict()

    def _save_index(self):
        with open(self._cache_index_file, "w", encoding="utf-8") as f:
            json.dump(list(self._cache.items()), f, ensure_ascii=False, indent=2)

    def _get_cache_path(self, file_path: str) -> str:
        import hashlib
        file_hash = hashlib.md5(file_path.encode("utf-8")).hexdigest()
        return os.path.join(CACHE_DIR, f"{file_hash}.jpg")

    def get(self, file_path: str) -> Optional[Image.Image]:
        if file_path in self._cache:
            self._cache.move_to_end(file_path)
            cache_path = self._cache[file_path]
            if os.path.exists(cache_path):
                try:
                    return Image.open(cache_path)
                except Exception:
                    pass
        return None

    def put(self, file_path: str, image: Image.Image) -> str:
        cache_path = self._get_cache_path(file_path)
        try:
            if image.mode in ("RGBA", "P"):
                image = image.convert("RGB")
            image.save(cache_path, "JPEG", quality=90)
            self._cache[file_path] = cache_path
            if len(self._cache) > MAX_CACHE_SIZE:
                old_path, old_cache = self._cache.popitem(last=False)
                if os.path.exists(old_cache):
                    try:
                        os.remove(old_cache)
                    except Exception:
                        pass
            self._save_index()
            return cache_path
        except Exception:
            return file_path

    def clear(self):
        self._cache.clear()
        self._save_index()
        for file in os.listdir(CACHE_DIR):
            if file.endswith(".jpg"):
                try:
                    os.remove(os.path.join(CACHE_DIR, file))
                except Exception:
                    pass


class WallpaperHistory:
    def __init__(self):
        self._history: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
            except (json.JSONDecodeError, TypeError):
                self._history = []

    def save(self):
        os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self._history[-MAX_HISTORY_ITEMS:], f, ensure_ascii=False, indent=2)

    def add_record(self, monitor_id: str, file_path: str):
        record = {
            "monitor": monitor_id,
            "path": str(Path(file_path).resolve()),
            "time": datetime.now().isoformat(),
        }
        self._history.append(record)
        self._history = self._history[-MAX_HISTORY_ITEMS:]
        self.save()

    def get_history(self, monitor_id: str = None) -> List[Dict]:
        if monitor_id:
            return [r for r in self._history if r["monitor"] == monitor_id]
        return list(reversed(self._history))

    def clear(self):
        self._history.clear()
        self.save()
