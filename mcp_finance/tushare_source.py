"""
Tushare 数据源 — 主数据源（财务数据 / 股票基础信息 / 日线行情）

Token 通过环境变量 TUSHARE_TOKEN 传入，不硬编码。
免费版限制：日线行情延迟15分钟，每分钟最多200次调用。

使用说明：
    export TUSHARE_TOKEN=你的token  # Linux/Mac
    set TUSHARE_TOKEN=你的token      # Windows CMD
    $env:TUSHARE_TOKEN="你的token"   # Windows PowerShell
"""

from __future__ import annotations
import os
import time
import logging
from typing import Any
from functools import lru_cache

_log = logging.getLogger("tushare")

# ── 全局 tushare 客户端 ──
_ts_client = None
_ts_available = None  # None=未检测, True=可用, False=不可用


def get_ts():
    """获取 tushare pro 客户端（懒加载 + 环境变量）"""
    global _ts_client, _ts_available
    
    if _ts_available is False:
        return None
    if _ts_client is not None:
        return _ts_client
    
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if not token:
        _log.info("TUSHARE_TOKEN 未设置，Tushare 不可用。注册地址: https://tushare.pro")
        _ts_available = False
        return None
    
    try:
        import tushare as ts
        ts.set_token(token)
        _ts_client = ts.pro_api()
        # 快速连接测试
        _ts_available = True
        _log.info("Tushare 客户端初始化成功")
        return _ts_client
    except Exception as e:
        _log.warning(f"Tushare 连接失败: {e}")
        _ts_available = False
        return None


def is_available() -> bool:
    """检查 Tushare 是否可用"""
    return get_ts() is not None


# ═══════════════════════════════════════════════════════════════
# 日线行情（延迟15分钟 — Tushare 免费版限制）
# ═══════════════════════════════════════════════════════════════

def get_daily(ts_code: str, start_date: str = None, end_date: str = None, limit: int = 250) -> list[dict]:
    """获取日线行情数据
    
    Args:
        ts_code: Tushare 格式代码（如 '600519.SH'）
        start_date: 开始日期 'YYYYMMDD'
        end_date: 结束日期 'YYYYMMDD'
        limit: 返回条数上限
    """
    ts = get_ts()
    if not ts:
        return []
    
    try:
        kwargs = {"ts_code": ts_code, "limit": min(limit, 5000)}
        if start_date:
            kwargs["start_date"] = start_date.replace("-", "")
        if end_date:
            kwargs["end_date"] = end_date.replace("-", "")
        
        df = ts.daily(**kwargs)
        if df is None or df.empty:
            return []
        
        records = []
        for _, row in df.iterrows():
            records.append({
                "日期": str(row.get("trade_date", "")),
                "开盘价": _safe_float(row.get("open")),
                "最高价": _safe_float(row.get("high")),
                "最低价": _safe_float(row.get("low")),
                "收盘价": _safe_float(row.get("close")),
                "成交量(手)": _safe_float(row.get("vol")),
                "成交额": _safe_float(row.get("amount")),
            })
        records.sort(key=lambda x: x["日期"])
        return records
    except Exception as e:
        _log.warning(f"Tushare daily {ts_code}: {e}")
        return []


def get_realtime_quote(ts_code: str) -> dict | None:
    """获取实时行情（免费版延迟15分钟）"""
    data = get_daily(ts_code, limit=1)
    if data:
        return data[0]
    return None


# ═══════════════════════════════════════════════════════════════
# 股票基础信息
# ═══════════════════════════════════════════════════════════════

@lru_cache(maxsize=1)
def get_stock_basic() -> list[dict]:
    """获取全市场A股基础信息列表（缓存）"""
    ts = get_ts()
    if not ts:
        return []
    
    try:
        dfs = []
        for market in ["SSE", "SZSE", "BSE"]:
            try:
                df = ts.stock_basic(exchange=market, list_status="L", 
                    fields="ts_code,symbol,name,area,industry,market,list_date")
                if df is not None and not df.empty:
                    dfs.append(df)
            except Exception:
                continue
        
        if not dfs:
            return []
        
        import pandas as pd
        df_all = pd.concat(dfs, ignore_index=True)
        records = []
        for _, row in df_all.iterrows():
            records.append({
                "代码": str(row.get("symbol", "")),
                "ts_code": str(row.get("ts_code", "")),
                "名称": str(row.get("name", "")),
                "行业": str(row.get("industry", "")),
                "地区": str(row.get("area", "")),
                "上市日期": str(row.get("list_date", "")),
            })
        _log.info(f"Tushare stock_basic: {len(records)} 只")
        return records
    except Exception as e:
        _log.warning(f"Tushare stock_basic: {e}")
        return []


def code_to_tscode(code: str) -> str:
    """将6位代码转为 Tushare 格式
    
    Args:
        code: 6位数字代码，如 '600519'
    Returns:
        Tushare 格式，如 '600519.SH'
    """
    code = code.strip().zfill(6)
    if code.startswith(("6", "9")):
        return f"{code}.SH"
    elif code.startswith(("0", "3")):
        return f"{code}.SZ"
    elif code.startswith(("8", "4")):
        return f"{code}.BJ"
    return f"{code}.SZ"


def tscode_to_code(ts_code: str) -> str:
    """Tushare 格式转6位代码"""
    return ts_code.split(".")[0].zfill(6)


# ═══════════════════════════════════════════════════════════════
# 财务数据（PE / PB / ROE / 净利润 等）
# ═══════════════════════════════════════════════════════════════

def get_financial_basic(ts_code: str) -> dict | None:
    """获取最新一期核心财务指标
    
    Returns:
        {"pe": float, "pb": float, "roe": float, "eps": float,
         "total_mv": float, "circ_mv": float}
    """
    ts = get_ts()
    if not ts:
        return None
    
    try:
        df = ts.daily_basic(
            ts_code=ts_code,
            fields="ts_code,trade_date,pe,pb,pe_ttm,pb_ttm,total_mv,circ_mv,turnover_rate,volume_ratio",
            limit=1
        )
        if df is None or df.empty:
            return None
        
        row = df.iloc[0]
        return {
            "日期": str(row.get("trade_date", "")),
            "pe": _safe_float(row.get("pe")),
            "pb": _safe_float(row.get("pb")),
            "pe_ttm": _safe_float(row.get("pe_ttm")),
            "pb_ttm": _safe_float(row.get("pb_ttm")),
            "总市值(元)": _safe_float(row.get("total_mv")) * 10000 if row.get("total_mv") else None,
            "流通市值(元)": _safe_float(row.get("circ_mv")) * 10000 if row.get("circ_mv") else None,
            "换手率(%)": _safe_float(row.get("turnover_rate")),
            "量比": _safe_float(row.get("volume_ratio")),
        }
    except Exception as e:
        _log.warning(f"Tushare daily_basic {ts_code}: {e}")
        return None


def get_financial_indicators_batch(codes: list[str]) -> dict[str, dict]:
    """批量获取多只股票的财务指标
    
    Args:
        codes: 6位代码列表（如 ['600519', '000858']）
    
    Returns:
        {code: {pe: ..., pb: ..., roe: ...}, ...}
    """
    ts = get_ts()
    if not ts or not codes:
        return {}
    
    ts_codes = [code_to_tscode(c) for c in codes]
    ts_code_str = ",".join(ts_codes[:200])  # Tushare 单次查询上限约200只
    
    results = {}
    
    # 1. 获取 PE/PB/市值/换手率
    try:
        df = ts.daily_basic(
            ts_code=ts_code_str,
            fields="ts_code,trade_date,pe,pb,pe_ttm,total_mv,circ_mv,turnover_rate,volume_ratio",
            limit=len(ts_codes)
        )
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                code = tscode_to_code(str(row.get("ts_code", "")))
                results[code] = {
                    "pe": _safe_float(row.get("pe")),
                    "pb": _safe_float(row.get("pb")),
                    "pe_ttm": _safe_float(row.get("pe_ttm")),
                    "总市值(元)": _safe_float(row.get("total_mv")) * 10000 if row.get("total_mv") else None,
                    "流通市值(元)": _safe_float(row.get("circ_mv")) * 10000 if row.get("circ_mv") else None,
                    "换手率(%)": _safe_float(row.get("turnover_rate")),
                    "量比": _safe_float(row.get("volume_ratio")),
                }
    except Exception as e:
        _log.warning(f"Tushare daily_basic batch: {e}")
    
    # 2. 获取 ROE
    for ts_c in ts_codes[:50]:  # ROE 逐个查询，限制数量
        try:
            code = tscode_to_code(ts_c)
            df_roe = ts.fina_indicator(ts_code=ts_c, fields="ts_code,roe,roe_dt", limit=1)
            if df_roe is not None and not df_roe.empty:
                roe_val = _safe_float(df_roe.iloc[0].get("roe"))
                if code in results:
                    results[code]["roe"] = roe_val
                else:
                    results[code] = {"roe": roe_val}
            time.sleep(0.15)  # 免费版频率限制
        except Exception:
            continue
    
    return results


def get_quarterly_financials(ts_code: str, periods: int = 4) -> list[dict]:
    """获取季度财务数据（利润表 + 资产负债表摘要）
    
    Returns:
        按报告期降序排列的财务数据列表
    """
    ts = get_ts()
    if not ts:
        return []
    
    results = []
    try:
        # 利润表关键指标
        df_income = ts.income(
            ts_code=ts_code,
            fields="ts_code,end_date,revenue,operate_profit,total_profit,n_income,basic_eps",
            limit=periods
        )
        
        # 资产负债表关键指标
        df_balance = ts.balancesheet(
            ts_code=ts_code,
            fields="ts_code,end_date,total_assets,total_liab,total_hldr_eqy_exc_min_int",
            limit=periods
        )
        
        # 合并
        income_map = {}
        if df_income is not None and not df_income.empty:
            for _, row in df_income.iterrows():
                income_map[str(row.get("end_date", ""))] = row
        
        if df_balance is not None and not df_balance.empty:
            for _, row in df_balance.iterrows():
                date_str = str(row.get("end_date", ""))
                income_row = income_map.get(date_str)
                item = {
                    "报告期": date_str[:10] if len(date_str) > 10 else date_str,
                    "营业收入": _safe_float(row.get("revenue")) if income_row is not None else None,
                    "营业利润": _safe_float(row.get("operate_profit")) if income_row is not None else None,
                    "净利润": _safe_float(row.get("n_income")) if income_row is not None else None,
                    "基本每股收益": _safe_float(row.get("basic_eps")) if income_row is not None else None,
                    "总资产": _safe_float(row.get("total_assets")),
                    "总负债": _safe_float(row.get("total_liab")),
                    "股东权益": _safe_float(row.get("total_hldr_eqy_exc_min_int")),
                }
                results.append(item)
        
        results.sort(key=lambda x: x["报告期"], reverse=True)
        return results[:periods]
    except Exception as e:
        _log.warning(f"Tushare quarterly {ts_code}: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def _safe_float(v) -> float | None:
    """安全转换为 float"""
    try:
        if v is None:
            return None
        f = float(v)
        import math
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 4)
    except (ValueError, TypeError):
        return None


def check_data_source() -> dict:
    """诊断 Tushare 数据源状态"""
    ts = get_ts()
    if not ts:
        token = os.environ.get("TUSHARE_TOKEN", "")
        return {
            "available": False,
            "reason": "TUSHARE_TOKEN 未设置" if not token else "连接失败",
            "setup": "export TUSHARE_TOKEN=你的token  # 注册地址: https://tushare.pro"
        }
    
    try:
        # 使用 trade_cal 做轻量连接测试（不限频）
        df = ts.trade_cal(exchange="SSE", start_date="20250101", end_date="20250101")
        return {
            "available": True,
            "test": "ok",
            "note": "免费版：日线延迟15分钟，每分钟约200次调用"
        }
    except Exception as e:
        return {
            "available": False,
            "reason": str(e)
        }
