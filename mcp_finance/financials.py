"""
财务数据缓存模块 v2 — 按需拉取 10+ 核心财务指标存到本地 JSON

数据来源: AKShare stock_financial_abstract (东方财富, 80+指标)
缓存策略: TTL 24小时，首次访问时按需拉取单只股票，后续从缓存读取

指标分类:
  核心指标: 营业总收入, 归母净利润, 基本每股收益, 每股净资产, 每股经营现金流
  盈利能力: ROE, ROA, 毛利率, 销售净利率, 营业利润率
  成长能力: 营收增长率, 归母净利润增长率
  财务风险: 资产负债率, 流动比率, 速动比率
  营运能力: 总资产周转率, 存货周转率
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

# 需要提取的指标名 → 缓存 key 映射
_INDICATOR_MAP: dict[str, str] = {
    "营业总收入": "revenue",
    "归母净利润": "net_profit",
    "基本每股收益": "eps",
    "每股净资产": "bvps",
    "每股经营现金流": "cfps",
    "净资产收益率(ROE)": "roe",
    "总资产报酬率(ROA)": "roa",
    "毛利率": "gross_margin",
    "销售净利率": "net_margin",
    "营业利润率": "operating_margin",
    "营业总收入增长率": "revenue_growth",
    "归属母公司净利润增长率": "net_profit_growth",
    "资产负债率": "debt_ratio",
    "流动比率": "current_ratio",
    "速动比率": "quick_ratio",
    "总资产周转率": "asset_turnover",
    "存货周转率": "inventory_turnover",
    "股东权益合计(净资产)": "equity",
    "经营现金流量净额": "operating_cf",
}

# 为向后兼容保留的 key 映射
_ALIAS_MAP: dict[str, str] = {
    "revenue": "revenue",
    "net_profit": "net_profit",
    "eps": "eps",
    "bvps": "bvps",
    "cfps": "cfps",
    "roe": "roe",
    "roa": "roa",
    "gross_margin": "gross_margin",
    "net_margin": "net_margin",
    "operating_margin": "operating_margin",
    "revenue_growth": "revenue_growth",
    "net_profit_growth": "net_profit_growth",
    "debt_ratio": "debt_ratio",
    "current_ratio": "current_ratio",
    "quick_ratio": "quick_ratio",
    "asset_turnover": "asset_turnover",
    "inventory_turnover": "inventory_turnover",
    "equity": "equity",
    "operating_cf": "operating_cf",
}


def get_financial_indicators(code: str) -> dict[str, Any]:
    """获取单只股票的核心财务指标（带缓存）

    返回: {"roe": float|None, "gross_margin": float|None, ..., "_ts": float, ...}
    """
    return _fin_cache.get_or_fetch(
        f"fin:{code}",
        lambda: _fetch_from_akshare(code),
        layer="disk",
    )


def _fetch_from_akshare(code: str) -> dict[str, Any]:
    """从 AKShare 东方财富拉取单只股票的核心财务指标（带超时保护）"""
    from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

    def _do_fetch() -> dict[str, Any]:
        result: dict[str, Any] = {"_ts": time.time()}
        for alias in _ALIAS_MAP:
            result[alias] = None

        try:
            import akshare as ak
            df = ak.stock_financial_abstract(symbol=code)
        except Exception as e:
            result["_error"] = f"akshare_failed:{e}"
            return result

        if df is None or df.empty:
            result["_error"] = "empty_data"
            return result

        try:
            # df 结构: 列 = ["选项", "指标", "20260331", "20251231", ...]
            # 行: 每行一个指标，第0列是分类，第1列是指标名，第2列起是各期数据
            date_cols = [c for c in df.columns[2:]]

            for _, row in df.iterrows():
                indicator_name = str(row.iloc[1]) if len(row) > 1 else ""
                if indicator_name not in _INDICATOR_MAP:
                    continue
                key = _INDICATOR_MAP[indicator_name]
                # 取最新一期非空值
                for col in date_cols:
                    val = row.get(col)
                    if val is None or (isinstance(val, float) and str(val) == "nan"):
                        continue
                    try:
                        result[key] = round(float(val), 2)
                        break
                    except (ValueError, TypeError):
                        continue
        except Exception as e:
            result["_error"] = f"parse_failed:{e}"

        return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_do_fetch)
        try:
            return future.result(timeout=30)
        except FuturesTimeoutError:
            future.cancel()
            result: dict[str, Any] = {"_ts": time.time(), "_error": "timeout"}
            for alias in _ALIAS_MAP:
                result[alias] = None
            return result


def preload_financials(codes: list[str], max_workers: int = 4) -> dict[str, dict]:
    """批量预热缓存（后台任务用，多线程并行）"""
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
