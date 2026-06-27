"""cache.py 单元测试 — TTL 缓存、磁盘缓存、防惊群

覆盖第三轮修复的 H5（get_or_fetch TOCTOU 竞态）。
"""
import sys, os, time, threading, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from mcp_finance.cache import TTLCache, CacheManager, DiskCacheStore


class TestTTLCache:
    def test_set_get_basic(self):
        c = TTLCache(default_ttl=60)
        c.set("k1", "v1")
        assert c.get("k1") == "v1"

    def test_get_missing_returns_default(self):
        c = TTLCache()
        assert c.get("nope") is None
        assert c.get("nope", "fallback") == "fallback"

    def test_ttl_expiry(self):
        c = TTLCache(default_ttl=0.1)
        c.set("k", "v")
        assert c.get("k") == "v"
        time.sleep(0.15)
        assert c.get("k") is None

    def test_clear(self):
        c = TTLCache()
        c.set("k", "v")
        c.clear()
        assert c.get("k") is None

    def test_thread_safe_concurrent_set_get(self):
        """并发读写不应抛异常"""
        c = TTLCache(default_ttl=60)
        errors = []
        def writer():
            try:
                for i in range(200):
                    c.set(f"k{i}", i)
            except Exception as e:
                errors.append(e)
        def reader():
            try:
                for i in range(200):
                    c.get(f"k{i}")
            except Exception as e:
                errors.append(e)
        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=reader)
        t1.start(); t2.start()
        t1.join(); t2.join()
        assert not errors


class TestCacheManagerGetOrFetch:
    """H5 修复验证：get_or_fetch 必须防止缓存惊群"""

    def test_single_fetch_under_concurrency(self):
        """20 个线程并发 get_or_fetch 同一 key，fetch_fn 只应被调用 1 次"""
        cm = CacheManager()
        call_count = [0]
        lock = threading.Lock()

        def fetch():
            with lock:
                call_count[0] += 1
            time.sleep(0.05)  # 模拟慢查询，放大竞态窗口
            return "value"

        threads = [threading.Thread(target=lambda: cm.get_or_fetch("k", fetch)) for _ in range(20)]
        [t.start() for t in threads]
        [t.join() for t in threads]

        assert call_count[0] == 1, f"fetch_fn 被调用 {call_count[0]} 次，应为 1（防惊群失败）"
        assert cm.get("k") == "value"

    def test_different_keys_fetch_independently(self):
        """不同 key 各自独立 fetch"""
        cm = CacheManager()
        calls = {"a": 0, "b": 0}

        def make_fetch(k):
            def fetch():
                calls[k] += 1
                return f"val_{k}"
            return fetch

        cm.get_or_fetch("a", make_fetch("a"))
        cm.get_or_fetch("b", make_fetch("b"))
        cm.get_or_fetch("a", make_fetch("a"))  # 命中缓存，不调用
        cm.get_or_fetch("b", make_fetch("b"))  # 命中缓存，不调用

        assert calls == {"a": 1, "b": 1}

    def test_fetch_returns_none_not_cached(self):
        """fetch_fn 返回 None 时不缓存，下次仍会调用"""
        cm = CacheManager()
        count = [0]
        def fetch():
            count[0] += 1
            return None
        cm.get_or_fetch("k", fetch)
        cm.get_or_fetch("k", fetch)
        assert count[0] == 2  # 两次都调用了，因为 None 不缓存

    def test_ttl_respected(self):
        """TTL 过期后重新 fetch"""
        cm = CacheManager(mem_ttl=0.1)
        count = [0]
        def fetch():
            count[0] += 1
            return "v"
        cm.get_or_fetch("k", fetch, ttl=0.1)
        assert count[0] == 1
        time.sleep(0.15)
        cm.get_or_fetch("k", fetch, ttl=0.1)
        assert count[0] == 2  # 过期后重新 fetch


class TestDiskCache:
    def test_disk_persistence(self):
        """磁盘缓存跨实例持久化"""
        with tempfile.TemporaryDirectory() as d:
            c1 = DiskCacheStore(d, default_ttl=60)
            c1.set("k", "v")
            c2 = DiskCacheStore(d, default_ttl=60)  # 新实例
            assert c2.get("k") == "v"
