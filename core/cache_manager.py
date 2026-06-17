import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple, Union
from collections import OrderedDict
from PIL import Image


HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".wallpaperswitcher", "history.json")
CACHE_DIR = os.path.join(os.path.expanduser("~"), ".wallpaperswitcher", "cache")
MAX_CACHE_SIZE = 200
MAX_HISTORY_ITEMS = 100


def _make_key(*parts: str) -> str:
    return "|".join(str(p) for p in parts)


class WallpaperCache:
    def __init__(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        self._cache_index_file = os.path.join(CACHE_DIR, "index.json")
        self._cache: "OrderedDict[str, str]" = OrderedDict()
        self._load_index()

    def _load_index(self):
        if os.path.exists(self._cache_index_file):
            try:
                with open(self._cache_index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._cache = OrderedDict(data)
                elif isinstance(data, dict):
                    self._cache = OrderedDict(data.items())
                else:
                    self._cache = OrderedDict()
            except (json.JSONDecodeError, TypeError):
                self._cache = OrderedDict()

    def _save_index(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(self._cache_index_file, "w", encoding="utf-8") as f:
            json.dump(list(self._cache.items()), f, ensure_ascii=False, indent=2)

    def _hash_key(self, key: str) -> str:
        return hashlib.md5(key.encode("utf-8")).hexdigest()

    def _cache_path_for(self, key: str) -> str:
        return os.path.join(CACHE_DIR, f"{self._hash_key(key)}.jpg")

    def _evict_if_needed(self):
        while len(self._cache) > MAX_CACHE_SIZE:
            _, old_cache_path = self._cache.popitem(last=False)
            if old_cache_path and os.path.exists(old_cache_path):
                try:
                    os.remove(old_cache_path)
                except Exception:
                    pass

    def get_image(self, file_path: str) -> Optional[Image.Image]:
        cache_path = self.get_path(file_path)
        if cache_path and os.path.exists(cache_path):
            try:
                return Image.open(cache_path)
            except Exception:
                return None
        return None

    def get_path(self, *key_parts: str) -> Optional[str]:
        key = _make_key(*key_parts)
        if key in self._cache:
            self._cache.move_to_end(key)
            cache_path = self._cache[key]
            if os.path.exists(cache_path):
                self._save_index()
                return cache_path
            else:
                del self._cache[key]
        return None

    def put_image(self, file_path: str, image: Image.Image) -> str:
        return self.put(file_path, image)

    def put(self, *key_parts_or_image: Union[str, Image.Image]) -> str:
        if len(key_parts_or_image) < 2:
            raise ValueError("put() 需要 key 部分和一个 PIL Image")
        image = key_parts_or_image[-1]
        key_parts = key_parts_or_image[:-1]
        if not isinstance(image, Image.Image):
            raise ValueError("put() 最后一个参数必须是 PIL Image")
        key = _make_key(*key_parts)
        cache_path = self._cache_path_for(key)
        try:
            img = image
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(cache_path, "JPEG", quality=92)
            self._cache[key] = cache_path
            self._cache.move_to_end(key)
            self._evict_if_needed()
            self._save_index()
            return cache_path
        except Exception:
            return ""

    def load_or_process(
        self,
        *key_parts: str,
        processor,
    ) -> Tuple[Optional[str], Optional[Image.Image]]:
        key = _make_key(*key_parts)
        cached_path = self.get_path(key)
        if cached_path:
            try:
                return cached_path, Image.open(cached_path)
            except Exception:
                pass
        result_img = processor()
        if result_img is None:
            return None, None
        saved_path = self.put(key, result_img)
        return saved_path or None, result_img

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
                if not isinstance(self._history, list):
                    self._history = []
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
