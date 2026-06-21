"""
财务数据缓存模块 — 按需拉取 ROE 等核心指标存到本地 JSON，选股器直接查缓存

数据来源: AKShare stock_financial_abstract
缓存策略: TTL 24小时，首次访问时按需拉取单只股票，后续从缓存读取
并发: DiskCacheStore 内部有文件级锁，网络请求在锁外执行
"""

from __future__ import annotations
import os
import time
from typing import Any

from mcp_finance.cache import CacheManager

_CACHE_TTL = 86400  # 24 小时

_fin_cache = CacheManager(
    disk_dir=os.path.join(os.path.dirname(__file__), ".financial_cache"),
    disk_ttl=_CACHE_TTL,
)


def get_financial_indicators(code: str) -> dict[str, Any]:
    """获取单只股票的核心财务指标（带缓存）

    返回: {"roe": float|None, "_ts": float, ...}
    """
    return _fin_cache.get_or_fetch(
        f"fin:{code}",
        lambda: _fetch_from_akshare(code),
        layer="disk",
    )


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
    """清空所有财务缓存"""
    if _fin_cache.disk is not None:
        _fin_cache.disk.clear()
