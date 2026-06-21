"""TTL 缓存工具 — 内存缓存 + 磁盘缓存 + 统一缓存管理器"""

from __future__ import annotations
import json
import os
import re
import threading
import time
from typing import Any, Callable

_SENTINEL = object()


# ═══════════════════════════════════════════════════════════════
# 内存缓存
# ═══════════════════════════════════════════════════════════════

class TTLCache:
    """带 TTL 的线程安全内存缓存"""

    def __init__(self, default_ttl: float = 60.0):
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str, default: Any | None = None) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return default
            expiry, value = entry
            if time.time() > expiry:
                del self._store[key]
                return default
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = (time.time() + ttl, value)
            # 惰性清理：每次 set 时随机清理过期 key（最多 10 个避免全量扫描）
            now = time.time()
            cleaned = 0
            for k, (exp, _) in list(self._store.items()):
                if now > exp:
                    del self._store[k]
                    cleaned += 1
                    if cleaned >= 10:
                        break

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        with self._lock:
            now = time.time()
            # 清理过期条目
            expired = [k for k, (exp, _) in self._store.items() if now > exp]
            for k in expired:
                del self._store[k]
            return len(self._store)


# ═══════════════════════════════════════════════════════════════
# 磁盘缓存
# ═══════════════════════════════════════════════════════════════

class DiskCacheStore:
    """线程安全的磁盘 JSON 缓存，按 key → 文件映射

    每个 key 对应一个 JSON 文件，TTL 通过文件 mtime 判断。
    """

    def __init__(self, cache_dir: str, default_ttl: float = 21600.0):
        self._dir = cache_dir
        self._default_ttl = default_ttl
        self._lock = threading.Lock()
        os.makedirs(self._dir, exist_ok=True)

    def _safe_key(self, key: str) -> str:
        """将 key 中的非法文件名字符替换为 _"""
        return re.sub(r'[<>:"/\\|?*]', "_", key)

    def _path(self, key: str) -> str:
        return os.path.join(self._dir, f"{self._safe_key(key)}.json")

    def get(self, key: str, default: Any = None) -> Any:
        path = self._path(key)
        with self._lock:
            if not os.path.exists(path):
                return default
            age = time.time() - os.path.getmtime(path)
            if age > self._default_ttl:
                try:
                    os.remove(path)
                except OSError:
                    pass
                return default
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return default

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """写入磁盘缓存。ttl 参数已弃用（TTL 由 mtime + default_ttl 决定），保留兼容"""
        path = self._path(key)
        with self._lock:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(value, f, ensure_ascii=False)

    def clear(self) -> None:
        with self._lock:
            for fname in os.listdir(self._dir):
                try:
                    os.remove(os.path.join(self._dir, fname))
                except OSError:
                    pass


# ═══════════════════════════════════════════════════════════════
# 统一缓存管理器
# ═══════════════════════════════════════════════════════════════

class CacheManager:
    """统一缓存管理器：内存 + 磁盘两级，调用方显式选择后端

    用法:
        cache = CacheManager(disk_dir=\"/tmp/cache\", disk_ttl=21600)
        cache.get(\"mykey\", layer=\"disk\")
        cache.set(\"mykey\", value, layer=\"disk\")
        cache.get_or_fetch(\"mykey\", fetch_fn, layer=\"disk\")
    """

    def __init__(
        self,
        mem_ttl: float = 60.0,
        disk_dir: str | None = None,
        disk_ttl: float = 21600.0,
    ):
        self.memory = TTLCache(default_ttl=mem_ttl)
        self.disk = DiskCacheStore(disk_dir, default_ttl=disk_ttl) if disk_dir else None

    def get(self, key: str, default: Any = None, layer: str = "mem") -> Any:
        if layer == "mem":
            return self.memory.get(key, default)
        if layer == "disk" and self.disk is not None:
            return self.disk.get(key, default)
        return default

    def set(self, key: str, value: Any, layer: str = "mem", ttl: float | None = None) -> None:
        if layer == "mem":
            self.memory.set(key, value, ttl=ttl)
        elif layer == "disk" and self.disk is not None:
            self.disk.set(key, value, ttl=ttl)

    def get_or_fetch(
        self,
        key: str,
        fetch_fn: Callable[[], Any],
        layer: str = "mem",
        ttl: float | None = None,
    ) -> Any:
        """缓存未命中时自动调用 fetch_fn 并缓存"""
        val = self.get(key, layer=layer)
        if val is not None:
            return val
        val = fetch_fn()
        if val is not None:
            self.set(key, val, layer=layer, ttl=ttl)
        return val
