"""TTL 缓存工具 — 基于内存字典 + 时间戳的轻量缓存"""

from __future__ import annotations
import time
import threading
from functools import wraps
from typing import Any, Callable

_SENTINEL = object()


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


# 全局缓存实例
cache = TTLCache()


def cached(ttl: float = 60.0, key_fn: Callable[..., str] | None = None):
    """函数结果缓存装饰器

    Args:
        ttl: 缓存有效期（秒）
        key_fn: 自定义缓存键生成函数，默认用 (func_name, args, kwargs)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if key_fn is not None:
                cache_key = key_fn(*args, **kwargs)
            else:
                cache_key = f"{func.__module__}.{func.__qualname__}:{args}:{sorted(kwargs.items(), key=lambda x: str(x[0]))}"

            result = cache.get(cache_key, default=_SENTINEL)
            if result is not _SENTINEL:
                return result

            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl=ttl)
            return result

        return wrapper
    return decorator
