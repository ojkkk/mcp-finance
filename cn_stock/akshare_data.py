"""
AKShare 数据源 — 龙虎榜 / 大宗交易 / 两融

作为 mcp-stock-cn 的第四数据源，补充现有三源（腾讯/东方财富/Baostock）
不能覆盖的高端数据。

采用懒加载模式，首次调用时 import akshare。
"""

from __future__ import annotations
from typing import Any

import pandas as pd

_ak_available: bool | None = None


def _ensure_akshare() -> bool:
    """懒加载检查 akshare 是否可用"""
    global _ak_available
    if _ak_available is not None:
        return _ak_available
    try:
        import akshare as ak  # noqa: F401
        _ak_available = True
        return True
    except ImportError:
        _ak_available = False
        return False


def _df_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """DataFrame → list[dict]，确保所有值都是 JSON 可序列化的 Python 原生类型"""
    df = df.where(pd.notna(df), None)
    records = df.to_dict(orient="records")
    # 清理嵌套类型（Timestamp, date 等）
    cleaned: list[dict[str, Any]] = []
    for row in records:
        clean_row: dict[str, Any] = {}
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                clean_row[k] = str(v)
            elif hasattr(v, "item"):
                clean_row[k] = v.item()
            else:
                clean_row[k] = v
        cleaned.append(clean_row)
    return cleaned


# ── 1. 龙虎榜 ──

def get_dragon_tiger(date: str | None = None) -> dict[str, Any]:
    """
    龙虎榜每日明细

    Args:
        date: 日期 "YYYYMMDD"，默认最近交易日

    Returns:
        包含日期、股票列表、上榜原因等
    """
    if not _ensure_akshare():
        return {"error": "akshare 未安装", "提示": "pip install akshare"}
    import akshare as ak
    try:
        from datetime import datetime
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        df = ak.stock_lhb_detail_daily_sina(date=date)
        if df.empty:
            return {"日期": date, "数据": [], "提示": "当日无龙虎榜数据或非交易日"}
        records = _df_to_records(df)
        return {
            "日期": date,
            "上榜数": len(records),
            "数据": records,
            "数据源": "AKShare-新浪",
        }
    except Exception as e:
        return {"error": f"获取龙虎榜失败: {e}"}


# ── 2. 大宗交易 ──

def get_block_trades(
    symbol: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict[str, Any]:
    """
    大宗交易数据

    Args:
        symbol:    股票代码（如 "000333"），留空返回全市场
        start_date: 开始日期 "YYYY-MM-DD"，默认 30 天前
        end_date:   结束日期 "YYYY-MM-DD"，默认今天
    """
    if not _ensure_akshare():
        return {"error": "akshare 未安装", "提示": "pip install akshare"}
    import akshare as ak
    try:
        from datetime import datetime, timedelta
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

        start = start_date.replace("-", "")
        end = end_date.replace("-", "")

        if symbol:
            df = ak.stock_dzjy_mrmx(symbol=symbol, start_date=start, end_date=end)
        else:
            df = ak.stock_dzjy_mrtj(start_date=start, end_date=end)

        records = _df_to_records(df) if not df.empty else []
        return {
            "时间范围": f"{start_date} ~ {end_date}",
            "股票": symbol or "全市场",
            "成交笔数": len(records),
            "数据": records,
            "数据源": "AKShare-东方财富",
        }
    except Exception as e:
        return {"error": f"获取大宗交易失败: {e}"}


# ── 3. 融资融券 ──

def get_margin_trading(
    market: str = "all",
    date: str | None = None,
) -> dict[str, Any]:
    """
    融资融券（两融）数据

    Args:
        market: "sh" 上证 / "sz" 深证 / "all" 两市
        date:   日期 "YYYYMMDD"，默认最近交易日
    """
    if not _ensure_akshare():
        return {"error": "akshare 未安装", "提示": "pip install akshare"}
    import akshare as ak
    try:
        from datetime import datetime
        if date is None:
            date = datetime.now().strftime("%Y%m%d")

        result: dict[str, Any] = {"日期": date, "数据源": "AKShare-交易所"}
        if market in ("sh", "all"):
            try:
                df_sh = ak.stock_margin_detail_sse(date=date)
                result["上海"] = _df_to_records(df_sh)
                result["上证个股数"] = len(df_sh)
            except Exception:
                result["上海"] = []
        if market in ("sz", "all"):
            try:
                df_sz = ak.stock_margin_detail_szse(date=date)
                result["深圳"] = _df_to_records(df_sz)
                result["深证个股数"] = len(df_sz)
            except Exception:
                result["深圳"] = []

        return result
    except Exception as e:
        return {"error": f"获取两融数据失败: {e}"}