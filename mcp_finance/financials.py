"""
财务数据缓存模块 — 按需拉取 ROE 等核心指标存到本地 JSON，选股器直接查缓存

数据来源: AKShare stock_financial_abstract
缓存策略: TTL 24小时，首次访问时按需拉取单只股票，后续从缓存读取
并发: 缓存读写锁，网络请求在锁外执行，避免阻塞并发读取
"""

from __future__ import annotations
import json, os, time, threading
from typing import Any

_CACHE_DIR = os.path.join(os.path.dirname(__file__), ".financial_cache")
_CACHE_TTL = 86400  # 24 小时
_cache_lock = threading.Lock()


def _ensure_cache_dir():
    os.makedirs(_CACHE_DIR, exist_ok=True)


def _cache_path(code: str) -> str:
    return os.path.join(_CACHE_DIR, f"{code}.json")


def _read_cache(code: str) -> dict[str, Any] | None:
    """读取缓存（带锁），有效则返回，否则返回 None"""
    path = _cache_path(code)
    with _cache_lock:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cached = json.load(f)
                if time.time() - cached.get("_ts", 0) < _CACHE_TTL:
                    return cached
            except (json.JSONDecodeError, KeyError):
                pass
    return None


def _write_cache(code: str, data: dict[str, Any]):
    """写入缓存（带锁）"""
    path = _cache_path(code)
    with _cache_lock:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except OSError:
            pass


def get_financial_indicators(code: str) -> dict[str, Any]:
    """获取单只股票的核心财务指标（带缓存）

    返回: {"roe": float|None, "_ts": float, ...}
    """
    _ensure_cache_dir()

    # 先读缓存（锁内操作很快）
    cached = _read_cache(code)
    if cached is not None:
        return cached

    # 缓存未命中 — 从 AKShare 拉取（锁外，不阻塞其他线程读缓存）
    result = _fetch_from_akshare(code)

    # 写入缓存
    _write_cache(code, result)

    return result


def _fetch_from_akshare(code: str) -> dict[str, Any]:
    """从 AKShare 拉取单只股票的 ROE 等指标（带超时保护）"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    def _do_fetch() -> dict[str, Any]:
        try:
            import akshare as ak
            df = ak.stock_financial_abstract(symbol=code)
        except Exception:
            return {"roe": None, "_ts": time.time(), "_error": "akshare_import_failed"}

        result: dict[str, Any] = {"roe": None, "_ts": time.time()}
        try:
            for _, row in df.iterrows():
                indicator = str(row.get("指标", ""))
                if "净资产收益率(ROE)" in indicator or "ROE" in indicator.upper():
                    val = row.iloc[2] if len(row) > 2 else None
                    if val is not None and str(val) != "nan":
                        try:
                            result["roe"] = round(float(val), 2)
                        except (ValueError, TypeError):
                            pass
                    break
        except Exception:
            pass
        return result

    # 30 秒超时保护（单只股票拉取）
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_do_fetch)
        try:
            return future.result(timeout=30)
        except FuturesTimeoutError:
            future.cancel()
            return {"roe": None, "_ts": time.time(), "_error": "timeout"}


def preload_financials(codes: list[str], max_workers: int = 4) -> dict[str, dict]:
    """批量预热缓存（后台任务用，多线程并行）

    Returns: {code: {roe: ...}, ...}
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(get_financial_indicators, c): c for c in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                results[code] = future.result(timeout=60)
            except Exception:
                results[code] = {"roe": None}
    return results


def clear_cache():
    """清空所有缓存"""
    import shutil
    if os.path.exists(_CACHE_DIR):
        shutil.rmtree(_CACHE_DIR)
